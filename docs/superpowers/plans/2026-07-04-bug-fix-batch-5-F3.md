# Bug Fix Batch 5 · F3 LIVE 余额拉失败不再 fallback · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `_fetch_balance()` LIVE 失败时返 `None`（不再 fallback 1000 USDT）；`process_enriched_v5` 见 `balance_usdt is None` 时写 `trade_scores_v5 block_reason='BALANCE_UNAVAILABLE'` 并 skip 开仓。

**Architecture:** 单 task TDD 循环：先写 4 tests → RED (`Optional[float]` 签名 + None 返回未实现) → 改 collector_main + scorer + 加 balance gate → GREEN → 邻近 tests 回归 → 单 commit。

**Tech Stack:** Python stdlib + pytest + monkeypatch。无新增 pip 依赖。

## Global Constraints

- 4 files touched: `scripts/tasks/collector_main.py` (modify) + `scripts/tasks/scorer.py` (modify) + `tests/test_collector_main_v5.py` (create) + `tests/test_v5_scorer.py` (create)
- `_fetch_balance` 签名 EXACT: `() -> Optional[float]`
- `process_enriched_v5` 签名 EXACT: `balance_usdt: Optional[float]`（其他参数保持）
- 新 gate 位置：紧接 `decision = decide(...)` 后、`MAX_CONCURRENT` 检查之前（early return，跳过所有下游）
- `block_reason` 值 EXACT: `"BALANCE_UNAVAILABLE"`
- LIVE 失败**不抛异常**（避开 scorer L464 广谱 catch/Finding 8）
- SHADOW 分支不变（继续返 `_PAPER_BALANCE`）
- 不改 `V5Scorer.run()` L458-465 结构
- 不改前端 / 不新增 ws 事件（`trade_scores_v5` 记录已足够审计）
- 不加 balance 缓存 / retry
- 现有测试无回归：`test_v5_position_manager.py` 8/8、`test_v5_position_monitor.py` 15/3、`test_paper_position_manager_v5.py` 4/4、`test_settings_db.py` 6/6、`test_v5_position_close_api.py` 全 pass
- Single commit, subject: `fix(collector+scorer): LIVE 余额拉失败不再 fallback,scorer 写 BALANCE_UNAVAILABLE (F3)`

---

## File Structure

| 路径 | 动作 |
|---|---|
| `scripts/tasks/collector_main.py` | Modify — 顶部加 `from typing import Optional`；`_fetch_balance` 签名改 `-> Optional[float]`；L89 最外层 `return _PAPER_BALANCE` 改 `return None`；docstring 更新；日志文案更新 |
| `scripts/tasks/scorer.py` | Modify — `process_enriched_v5` 签名 `balance_usdt: Optional[float]`；在 `decision = decide(...)` 后紧接插入 balance-None gate |
| `tests/test_collector_main_v5.py` | Create — 3 tests 覆盖 SHADOW / LIVE success / LIVE fail |
| `tests/test_v5_scorer.py` | Create — 1 test 覆盖 `process_enriched_v5(balance_usdt=None)` |

---

# Task 1: `_fetch_balance` Optional + scorer balance gate + 4 tests

**Files:**
- Modify: `scripts/tasks/collector_main.py`
- Modify: `scripts/tasks/scorer.py`
- Create: `tests/test_collector_main_v5.py`
- Create: `tests/test_v5_scorer.py`

**Interfaces:**
- Consumes: `MagicMock` + `monkeypatch.setattr` (test 内)；`sys.modules["ccxt"]` stub (Batch 1 已确认 ccxt 未装)
- Produces:
  - `scripts.tasks.collector_main._fetch_balance() -> Optional[float]`
  - `scripts.tasks.scorer.process_enriched_v5(..., balance_usdt: Optional[float]) -> None`
  - trade_scores_v5 新 block_reason 值 `"BALANCE_UNAVAILABLE"`

## RED phase — 先写 4 tests

- [ ] **Step 1: 建 `tests/test_collector_main_v5.py`**

```python
"""V5 collector_main._fetch_balance 分支测试 (F3)."""
import sys
from unittest.mock import MagicMock


def _stub_ccxt():
    """ccxt 在测试环境未装,先 stub 避免 collector_main import 时崩。"""
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = MagicMock()


def test_fetch_balance_shadow_returns_paper(monkeypatch):
    """SHADOW → 返 _PAPER_BALANCE。"""
    _stub_ccxt()
    from scripts.tasks import collector_main

    monkeypatch.setattr(collector_main, "_resolve_mode_db", lambda: "SHADOW")
    monkeypatch.setattr(collector_main, "_PAPER_BALANCE", 1000.0)

    result = collector_main._fetch_balance()
    assert result == 1000.0


def test_fetch_balance_live_success_returns_real(monkeypatch):
    """LIVE + trader.fetch_balance 返可 parse 的 USDT free → 返真实值。"""
    _stub_ccxt()
    from scripts.tasks import collector_main

    monkeypatch.setattr(collector_main, "_resolve_mode_db", lambda: "LIVE")

    fake_trader = MagicMock()
    fake_trader.fetch_balance.return_value = {"USDT": {"free": 500.5, "available": 500.5}}
    monkeypatch.setattr(collector_main, "_get_live_trader", lambda: fake_trader)

    result = collector_main._fetch_balance()
    assert result == 500.5


def test_fetch_balance_live_failure_returns_none(monkeypatch):
    """LIVE + trader.fetch_balance 抛 → 返 None(不再 fallback 到 1000)。"""
    _stub_ccxt()
    from scripts.tasks import collector_main

    monkeypatch.setattr(collector_main, "_resolve_mode_db", lambda: "LIVE")

    fake_trader = MagicMock()
    fake_trader.fetch_balance.side_effect = RuntimeError("network error")
    monkeypatch.setattr(collector_main, "_get_live_trader", lambda: fake_trader)

    result = collector_main._fetch_balance()
    assert result is None
```

- [ ] **Step 2: 建 `tests/test_v5_scorer.py`**

```python
"""V5 Scorer process_enriched_v5 分支测试 (F3 balance=None)."""
import asyncio
import sqlite3
import sys
from unittest.mock import MagicMock


def _stub_ccxt():
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = MagicMock()


def _fake_klines(n: int = 30):
    """构造 n 条最小 kline,足够 IndicatorEngine (RSI/MACD 需 ≥ 26)。"""
    return [(i * 900_000, 0.166, 0.167, 0.165, 0.166, 100.0) for i in range(n)]


def _make_enriched():
    """构造最小 EnrichedItem。klines 30 条 flat, decide() 通常返 should_trade=False,
    我们用 monkeypatch decide 让它 True 才能触达 balance gate。"""
    _stub_ccxt()
    from scripts.v5_types import EnrichedItem
    return EnrichedItem(
        symbol="H/USDT",
        current_price=0.166,
        delta_15m_pct=0.03,
        volume_24h_usdt=1_500_000.0,
        klines_15m=_fake_klines(),
        klines_4h=_fake_klines(),
    )


def test_process_enriched_none_balance_writes_block(tmp_path, monkeypatch):
    """balance_usdt=None → 写 trade_scores_v5 block_reason=BALANCE_UNAVAILABLE, skip 开仓。"""
    _stub_ccxt()
    from scripts.local_db import init_local_db
    from scripts.tasks import scorer

    db = str(tmp_path / "x.db")
    init_local_db(db)

    enriched = _make_enriched()

    # monkeypatch decide() 让它返 should_trade=True,才能穿过 "not should_trade" 早期 return,
    # 触达紧接其后的 balance-None gate
    from scripts.v5_types import Decision
    monkeypatch.setattr(
        scorer, "decide",
        lambda enr, ind, funding_z=None: Decision(
            should_trade=True, side="LONG",
            reasoning="test-strong-signal", block_reason=None,
        ),
    )

    paper_pm = MagicMock()
    live_pm = MagicMock()
    ai = MagicMock()

    asyncio.run(scorer.process_enriched_v5(
        enriched=enriched, ai=ai, paper_pm=paper_pm, live_pm=live_pm,
        mode="LIVE", db_path=db, balance_usdt=None,
    ))

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT block_reason FROM trade_scores_v5 WHERE symbol=?", (enriched.symbol,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "BALANCE_UNAVAILABLE"

    # skip 开仓 → paper_pm / live_pm 未被调
    paper_pm.open_position.assert_not_called()
    live_pm.open_position.assert_not_called()
```

**Note**: `Decision` 数据类可能有更多 required 字段（如 setup_type / stop_reason 等）。若 test 报 `TypeError: missing X argument`，按 `scripts/v5_types.py` 里 `class Decision` 定义补齐即可。

- [ ] **Step 3: 跑 tests —— 期望 RED**

```bash
python3 -m pytest tests/test_collector_main_v5.py tests/test_v5_scorer.py -v
```

Expected:
- `test_fetch_balance_shadow_returns_paper` **PASS**（SHADOW 分支现有代码已正确）
- `test_fetch_balance_live_success_returns_real` **PASS**（LIVE 成功分支现有代码已正确）
- `test_fetch_balance_live_failure_returns_none` **FAIL** —— 现代码返 `_PAPER_BALANCE` 不是 None，断言 `is None` 失败
- `test_process_enriched_none_balance_writes_block` **FAIL** —— 现代码传 `balance_usdt=None` 会崩（`equity_usdt=None` 无法算），或写不出 BALANCE_UNAVAILABLE 记录

2 FAIL 就是 F3 的具体运行证据。

## GREEN phase — 改 collector_main + scorer

- [ ] **Step 4: 加 `from typing import Optional` 到 `scripts/tasks/collector_main.py` 顶部**

在现有 imports 之后追加：

```python
from typing import Optional
```

- [ ] **Step 5: 改 `_fetch_balance` 签名 + docstring + LIVE 失败分支**

用 Edit 替换整个 `_fetch_balance` 函数（用现有函数体做 unique substring anchor）。新代码：

```python
def _fetch_balance() -> Optional[float]:
    """SHADOW 模式直接返回 PAPER_INITIAL_BALANCE_USDT
    (避免每次 scoring 都打一堆 fetch_balance / load_markets 失败的日志)。
    LIVE 模式才真正去拉真实余额。LIVE 失败返 None (由 scorer 端写
    BALANCE_UNAVAILABLE block 记录,不伪造成 1000 USDT 假余额,防止风险
    计算被误导 —— F3)."""
    if _resolve_mode_db() != "LIVE":
        return _PAPER_BALANCE
    try:
        trader = _get_live_trader()
        if trader is not None:
            bal = trader.fetch_balance()
            usdt = None
            if isinstance(bal, dict):
                if "USDT" in bal and isinstance(bal["USDT"], dict):
                    usdt = bal["USDT"].get("free") or bal["USDT"].get("available")
                elif "free" in bal:
                    usdt = bal["free"]
                elif "available" in bal:
                    usdt = bal["available"]
            if usdt is not None and float(usdt) > 0:
                return float(usdt)
    except Exception as e:
        print(f"[collector_main] LIVE 余额拉取失败,scorer 侧将写 BALANCE_UNAVAILABLE: {e}")
    return None
```

- [ ] **Step 6: 改 `process_enriched_v5` 签名 (L191-192)**

用 Edit 替换签名：

```python
async def process_enriched_v5(*, enriched: EnrichedItem, ai, paper_pm, live_pm,
                              mode: str, db_path: str,
                              balance_usdt: Optional[float]) -> None:
```

（`Optional` 已 imported at L11）

- [ ] **Step 7: 插新 balance-None gate**

用 unique substring `decision = decide(enriched, indicators, funding_z=funding_z_score)` 找到位置。在紧接其后（`decision = decide(...)` 之后、`if not decision.should_trade:` 之前）插入：

```python
    # F3:LIVE 余额拉取失败(_fetch_balance 返 None) → 不能可靠算风险,skip 本次开仓
    if balance_usdt is None:
        _write_trade_score(db_path, enriched, indicators, decision,
                          block_reason="BALANCE_UNAVAILABLE",
                          funding_z_score=funding_z_score,
                          funding_rate_8h=funding_rate_8h)
        return
```

**注意**：放在 `decision = decide(...)` 之后是因为 `_write_trade_score` 需要 `indicators` 和 `decision`（都是 required positional）。放在 `if not decision.should_trade:` **之前**是因为我们要覆盖"decision 是 open 意图但 balance 拉不到"的场景。若 decision 本身就是 no-trade，本 gate 不 hit（正常路径处理）。

- [ ] **Step 8: 跑 tests —— 期望 GREEN**

```bash
python3 -m pytest tests/test_collector_main_v5.py tests/test_v5_scorer.py -v
```

Expected: 4/4 PASS。

若失败：
- `test_fetch_balance_live_failure_returns_none`：检查 Step 5 最后 `return None`（不是 `return _PAPER_BALANCE`）
- `test_process_enriched_none_balance_writes_block`：
  - 检查 Step 7 插入位置正确（`decision = decide(...)` 之后）
  - 检查 `_write_trade_score` 调用参数完整
  - 若 `Decision(...)` 构造报缺字段 → 按 `scripts/v5_types.py` 实际字段补齐

## 邻近回归

- [ ] **Step 9: 跑邻近 tests**

```bash
python3 -m pytest tests/test_v5_position_manager.py tests/test_v5_position_monitor.py tests/test_paper_position_manager_v5.py tests/test_settings_db.py tests/test_v5_position_close_api.py -v 2>&1 | tail -15
```

Expected:
- `test_v5_position_manager.py` 8/8 PASS（Batch 1 + Batch 4）
- `test_v5_position_monitor.py` 15 PASS / 3 pre-existing FAIL（SIGNAL_REVERSE 数量不变）
- `test_paper_position_manager_v5.py` 全 PASS
- `test_settings_db.py` 6/6 PASS
- `test_v5_position_close_api.py` 全 PASS

## Sanity + commit

- [ ] **Step 10: sanity greps**

```bash
# _fetch_balance 签名改成 Optional
grep -n "def _fetch_balance" scripts/tasks/collector_main.py
# 期望：1 hit,签名 -> Optional[float]

# LIVE 失败分支返 None (不再 _PAPER_BALANCE)
grep -c "return _PAPER_BALANCE" scripts/tasks/collector_main.py
# 期望：1 hit(只剩 SHADOW 分支)

# process_enriched_v5 签名有 Optional[float]
grep -n "balance_usdt: Optional\[float\]" scripts/tasks/scorer.py
# 期望：1 hit

# BALANCE_UNAVAILABLE gate 存在
grep -n "BALANCE_UNAVAILABLE" scripts/tasks/scorer.py
# 期望：1 hit
```

- [ ] **Step 11: Commit**

```bash
git add scripts/tasks/collector_main.py scripts/tasks/scorer.py tests/test_collector_main_v5.py tests/test_v5_scorer.py
git commit -m "$(cat <<'EOF'
fix(collector+scorer): LIVE 余额拉失败不再 fallback,scorer 写 BALANCE_UNAVAILABLE (F3)

修 bug-fix-list.md Finding 3:_fetch_balance() LIVE 拉不到真实余额时
之前 fallback 到 _PAPER_BALANCE(1000 USDT),真账户余额假设是 100 USDT
时风险计算被误导 10 倍。gate_per_trade_risk 允许的 15 USDT 单笔风险
在真账户上是 15% 风险,一次 SL 打掉 15%。

Change:
- _fetch_balance() -> Optional[float]; LIVE 失败返 None(不再兜底 1000)
- SHADOW 分支不变(继续返 _PAPER_BALANCE,SHADOW = 纸面交易设计)
- process_enriched_v5(balance_usdt: Optional[float]); 在 decide(...) 后
  新增 gate: balance_usdt=None → 写 trade_scores_v5
  block_reason='BALANCE_UNAVAILABLE' + skip 开仓
- 避开 scorer L464 广谱 catch(F8): 返 None 不抛异常

Tests:
- 新增 test_collector_main_v5.py 3 tests
  (SHADOW/LIVE success/LIVE fail=None)
- 新增 test_v5_scorer.py 1 test
  (process_enriched_v5(balance=None) 写 BLOCK 且 skip 开仓)
- 现有 8/15/4/6/N tests 无回归(SIGNAL_REVERSE 3 pre-existing 仍在)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

# Self-Review 记录

- **spec § 四 Change 1 (_fetch_balance)**: Step 4 (Optional import) + Step 5 (签名 + LIVE 失败返 None) ✓
- **spec § 五 Change 2 (process_enriched_v5)**: Step 6 (签名) + Step 7 (balance-None gate 插入)  ✓
- **spec § 六 Change 3 (4 tests)**: Step 1 (3 tests for collector_main) + Step 2 (1 test for scorer) ✓
- **spec § 七 验收标准**: Step 8 (4/4 pass) + Step 9 (邻近回归) + Step 10 (sanity) ✓
- **spec § 八 失效模式**: 各分支（SHADOW / LIVE success / trader None / fetch_balance 抛 / usdt=None / usdt≤0）在 Step 5 里都被覆盖 ✓
- **spec § 九 超范围**: 只 4 files 触碰；`V5Scorer.run()` 不动；不新增 ws 事件；不加 caching ✓
- **placeholder scan**: 无 TBD / TODO / "similar to Task N"；每 step 有完整代码 ✓
- **type consistency**: `Optional[float]` 在 collector_main / scorer / 4 tests 都一致 ✓
- **F8 避让**: `_fetch_balance` 返 None 不抛异常，scorer L464 广 catch 不触发 ✓
- **测试 RED→GREEN**: Step 3 = RED (2 fail)；Step 8 = GREEN (4/4) ✓
- **atomicity**: 单 commit at Step 11 ✓
