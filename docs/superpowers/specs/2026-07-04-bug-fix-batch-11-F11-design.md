# Bug Fix Batch 11 · Finding 11 · open_position BEGIN IMMEDIATE 二次 count 检查 · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 11 (P1)

---

## 一、问题陈述

`scripts/tasks/scorer.py:241` 先做 `_count_open_positions(db_path) >= _max_concurrent()` 预检,通过后才走到 `paper_pm.open_position()` (L410) —— 中间隔了 `await ai.decide()` (L313) 等待,期间 count 可能失效。

当前单 scorer 实例串行处理,理论上无并发。但:
- 未来多 scorer 实例 / 多进程 scorer 时,两实例都读 count=2(上限 3),都通过检查,都完成 AI 调用后各自 INSERT,最终 count=4 → 超限
- SQLite 层没有跨越 `await` 的事务锁

## 二、目标

在 `PaperPositionManager.open_position()` 内部用 `BEGIN IMMEDIATE`(SQLite 悲观写锁)包一层:进入事务后**再次 count paper_trades OPEN + positions_v5 OPEN**,超限则抛 `ConcurrencyLimitExceeded`;否则同事务 INSERT + COMMIT。scorer 侧在开仓 catch 该异常,写 `MAX_CONCURRENT_POSITIONS_RACE` block reason。

## 三、范围

**In scope**:
- 新增 `ConcurrencyLimitExceeded` 异常类(定义在 `scripts/paper_position_manager.py` 顶层)
- `PaperPositionManager.open_position()` 加可选参数 `max_concurrent: Optional[int] = None`
- 若传入 `max_concurrent`,方法内 BEGIN IMMEDIATE + count 双表(paper_trades + positions_v5 均计 OPEN)+ 校验 + INSERT + COMMIT
- `scripts/tasks/scorer.py:410` SHADOW 分支的 `paper_pm.open_position(...)` 加 `max_concurrent=_max_concurrent()`
- `scripts/tasks/scorer.py` L421 catch 处,专门 catch `ConcurrencyLimitExceeded` 前置,写 `MAX_CONCURRENT_POSITIONS_RACE`
- 新增 2 tests 到 `tests/test_paper_position_manager_v5.py`

**Out of scope**:
- 不改 LIVE 路径(`V5PositionManager.open_position`)—— broker 调用秒级延迟,DB 锁跨 broker 无意义。LIVE 现有 pre-check(scorer L241)对单 scorer 已够,多 scorer LIVE 是后续更大改动。**留 comment 标注**。
- 不改 `_count_open_positions()` helper —— 现有 pre-check 保留(早退优化)
- 不改前端
- 不加索引(paper_trades / positions_v5 均已有 status 索引)
- 不改 max_concurrent 参数读取逻辑

## 四、Change 1 — `scripts/paper_position_manager.py` 顶层加异常

```python
class ConcurrencyLimitExceeded(Exception):
    """开仓时检测到当前 OPEN 数已达 max_concurrent 上限(TOCTOU 二次校验)。

    Finding 11: BEGIN IMMEDIATE 事务内二次 count 双表(paper_trades + positions_v5),
    上层 catch 后应写 block_reason=MAX_CONCURRENT_POSITIONS_RACE,不重试。
    """
```

## 五、Change 2 — `PaperPositionManager.open_position` 签名 + 事务

**Before**(L104-156 摘要):
```python
def open_position(self, *, enriched, indicators, decision, risk, ai) -> int:
    ...
    conn = self._conn()
    try:
        cur = conn.execute("""INSERT INTO paper_trades ...""", (...))
        pid = cur.lastrowid
        conn.commit()
        return pid
    finally:
        conn.close()
```

**After**:
```python
def open_position(self, *, enriched, indicators, decision, risk, ai,
                  max_concurrent: Optional[int] = None) -> int:
    """Finding 11: 若给 max_concurrent,BEGIN IMMEDIATE 内二次校验 count(paper+live)。"""
    ...  # 计算 sl/tp/size 等,不变
    conn = self._conn()
    try:
        if max_concurrent is not None:
            # 悲观写锁 —— 阻止其他连接进入 write txn 直到 COMMIT
            conn.execute("BEGIN IMMEDIATE")
            n_paper = conn.execute(
                "SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'").fetchone()[0]
            n_live = conn.execute(
                "SELECT COUNT(*) FROM positions_v5 WHERE status='OPEN'").fetchone()[0]
            if n_paper + n_live >= max_concurrent:
                conn.rollback()
                raise ConcurrencyLimitExceeded(
                    f"open_position 并发上限已达:{n_paper}(paper)+{n_live}(live)"
                    f">={max_concurrent},拒绝开仓")
        cur = conn.execute("""INSERT INTO paper_trades ...""", (...))
        pid = cur.lastrowid
        conn.commit()
        return pid
    finally:
        conn.close()
```

注意:
- `positions_v5` 表可能在测试环境不存在 → `try/except sqlite3.OperationalError` 兜住并视为 0
- `conn.rollback()` 后 raise —— finally 里的 close 仍会跑
- INSERT SQL 主体保持不变

## 六、Change 3 — `scripts/tasks/scorer.py` SHADOW 开仓传参 + catch

**Before**(L408-427):
```python
try:
    if mode == "SHADOW":
        position_id = paper_pm.open_position(
            enriched=enriched, indicators=indicators,
            decision=decision, risk=risk, ai=ai_result,
        )
    else:
        position_id = live_pm.open_position(...)
except Exception as e:
    _write_trade_score(db_path, enriched, indicators, decision,
                      ai=ai_result, risk=risk,
                      block_reason=f"OPEN_FAILED:{type(e).__name__}",
                      funding_z_score=funding_z_score,
                      funding_rate_8h=funding_rate_8h)
    return
```

**After**:
```python
try:
    if mode == "SHADOW":
        position_id = paper_pm.open_position(
            enriched=enriched, indicators=indicators,
            decision=decision, risk=risk, ai=ai_result,
            max_concurrent=_max_concurrent(),
        )
    else:
        position_id = live_pm.open_position(...)  # LIVE 路径不变,后续 batch 处理
except ConcurrencyLimitExceeded as e:
    _write_trade_score(db_path, enriched, indicators, decision,
                      ai=ai_result, risk=risk,
                      block_reason="MAX_CONCURRENT_POSITIONS_RACE",
                      funding_z_score=funding_z_score,
                      funding_rate_8h=funding_rate_8h)
    print(f"[V5Scorer] {enriched.symbol} 并发二次校验拒开: {e}")
    return
except Exception as e:
    _write_trade_score(db_path, enriched, indicators, decision,
                      ai=ai_result, risk=risk,
                      block_reason=f"OPEN_FAILED:{type(e).__name__}",
                      funding_z_score=funding_z_score,
                      funding_rate_8h=funding_rate_8h)
    return
```

顶部加 import: `from scripts.paper_position_manager import ConcurrencyLimitExceeded`。

## 七、Change 4 — 追加 2 tests 到 `tests/test_paper_position_manager_v5.py`

```python
def test_open_position_race_double_check_rejects_when_at_limit(tmp_path):
    """Finding 11: max_concurrent=3, 已有 3 OPEN → 二次校验抛 ConcurrencyLimitExceeded, 无 INSERT。"""
    import sqlite3
    from scripts.paper_position_manager import (
        PaperPositionManager, ConcurrencyLimitExceeded,
    )
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, side TEXT, entry_price REAL, status TEXT,
            strategy_id TEXT, created_at TEXT, entry_time TEXT,
            target_close_at TEXT, extension_count INTEGER DEFAULT 0,
            current_price REAL, stop_loss REAL, take_profit REAL,
            position_size_usdt REAL, leverage INTEGER,
            ai_confidence REAL, ai_sl_multiplier REAL, ai_tp_multiplier REAL,
            ai_reason TEXT, entry_rsi_15m REAL, entry_macd_hist_15m REAL,
            entry_rsi_4h REAL, entry_atr_15m REAL, signal_score REAL
        );
        CREATE TABLE positions_v5 (id INTEGER PRIMARY KEY, status TEXT);
    ''')
    # 3 OPEN paper 已存在
    for _ in range(3):
        conn.execute(
            "INSERT INTO paper_trades (symbol, side, status, strategy_id, created_at, entry_time) "
            "VALUES ('BTC/USDT', 'LONG', 'OPEN', 'v5', datetime('now'), datetime('now'))"
        )
    conn.commit()
    conn.close()

    pm = PaperPositionManager(db_path=db_path)
    enriched = _mk_enriched()  # 现有 test helper
    indicators = _mk_indicators()
    decision = _mk_decision()
    risk = _mk_risk()
    ai = _mk_ai()

    import pytest
    with pytest.raises(ConcurrencyLimitExceeded, match="并发上限已达"):
        pm.open_position(
            enriched=enriched, indicators=indicators, decision=decision,
            risk=risk, ai=ai, max_concurrent=3,
        )

    # 验证无新 INSERT
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'").fetchone()[0]
    conn.close()
    assert n == 3


def test_open_position_no_max_concurrent_bypasses_check(tmp_path):
    """Finding 11: max_concurrent=None(默认)→ 不校验,行为与原来完全一致。"""
    import sqlite3
    from scripts.paper_position_manager import PaperPositionManager
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, side TEXT, entry_price REAL, status TEXT,
            strategy_id TEXT, created_at TEXT, entry_time TEXT,
            target_close_at TEXT, extension_count INTEGER DEFAULT 0,
            current_price REAL, stop_loss REAL, take_profit REAL,
            position_size_usdt REAL, leverage INTEGER,
            ai_confidence REAL, ai_sl_multiplier REAL, ai_tp_multiplier REAL,
            ai_reason TEXT, entry_rsi_15m REAL, entry_macd_hist_15m REAL,
            entry_rsi_4h REAL, entry_atr_15m REAL, signal_score REAL
        );
    ''')
    # 塞 100 条已 OPEN
    for _ in range(100):
        conn.execute(
            "INSERT INTO paper_trades (symbol, side, status, strategy_id, created_at, entry_time) "
            "VALUES ('BTC/USDT', 'LONG', 'OPEN', 'v5', datetime('now'), datetime('now'))"
        )
    conn.commit()
    conn.close()

    pm = PaperPositionManager(db_path=db_path)
    pid = pm.open_position(
        enriched=_mk_enriched(), indicators=_mk_indicators(),
        decision=_mk_decision(), risk=_mk_risk(), ai=_mk_ai(),
        # 无 max_concurrent 参数 → 默认 None → 不校验
    )
    assert pid > 0  # INSERT 成功
```

`_mk_enriched` 等 helper 参考现有测试文件中的 fixture(pattern 应已在 batch-1 F4 fix 时建立)。若不存在,test 顶部直接构造 dataclass。

## 八、验收标准

- `python3 -m pytest tests/test_paper_position_manager_v5.py -v` → 现有 4/4 + 新 2/2 = 6/6 pass
- `python3 -m pytest tests/test_v5_scorer.py tests/test_v5_scorer_run_catches.py -v` → 无回归
- `grep -c "ConcurrencyLimitExceeded" scripts/tasks/scorer.py` → ≥1(import + catch 各算,严格 2)
- `grep -c "BEGIN IMMEDIATE" scripts/paper_position_manager.py` → 1
- `grep -c "MAX_CONCURRENT_POSITIONS_RACE" scripts/tasks/scorer.py` → 1
- 只 stage 3 文件
- Commit subject EXACT: `fix(paper_position_manager): open_position BEGIN IMMEDIATE + 二次 count 校验 (Finding 11)`

## 九、失效模式

- **positions_v5 表不存在**(测试环境 mig 未跑):`conn.execute("SELECT COUNT(*) FROM positions_v5 ...")` 抛 `sqlite3.OperationalError`。缓解:try/except 兜住,`n_live=0`。
- **BEGIN IMMEDIATE 被别的写锁挡住**:sqlite3 默认 5s timeout → 超时抛 `OperationalError("database is locked")`。若真发生并发热点,是可接受的降级(单笔延迟),再不济 scorer 顶层的 catch-all 会捕获并写 OPEN_FAILED。
- **max_concurrent=0**:立即被拦(0 OPEN < 0 不成立)。属于配置错误,fail-fast 合理。
- **LIVE 路径未加锁**:留待后续 batch。单 scorer 场景 pre-check + 立即调 broker 无 await 让锁,风险窗口极小。已在 spec § 三 & § 六 明确说明。

## 十、超范围声明

- 不改 LIVE 路径(V5PositionManager.open_position)
- 不改 _count_open_positions() helper 语义
- 不加 asyncio 并发测试(单元级 double-check 已够,并发压测未来做)
- 不改前端
- 不改 max_concurrent 默认值

## 十一、相关

- Bug audit: `docs/audit-2026-07/bug-fix-list.md` Finding 11 (P1)
- 引用:
  - `scripts/tasks/scorer.py:241`(pre-check 保持不动)
  - `scripts/tasks/scorer.py:408-427`(catch 分支)
  - `scripts/paper_position_manager.py:104-156`(open_position 实现)
- 相关 Finding:Finding 10 (Batch 6, scorer.run ws) —— 同 catch 位置改动;Finding 3 (Batch 5, balance) —— pre-check 早退模式已固化
