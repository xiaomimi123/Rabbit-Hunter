# Bug Fix Batch 4 · F2 close_position 吞 broker 失败 · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 2；Batch 1 (F4) 让 broker.close_position 现在返 dict 而非抛异常

---

## 一、问题陈述

`scripts/v5_position_manager.py:234-268` `close_position(position_id, exit_price, exit_reason)` 现状：

```python
try:
    self.broker.close_position(symbol)   # broker 现在返 dict,不抛
except Exception as e:
    print(...)                            # 抓意外异常,但不改行为

# 无论 broker 结果如何 ↓ 全部继续 ↓
UPDATE positions_v5 SET status='CLOSED', pnl_usdt=..., ...
```

**两个真 bug**：
1. broker 返 `{"success": False, "error_kind": ..., "error": ...}` → 代码不查 `success` → 视为成功 → DB 标 `CLOSED`，但**交易所仍持仓**。真钱裸奔。
2. broker 抛异常（罕见，网络层深处）→ `except` 吞掉 → 同上，DB 标 CLOSED，交易所仓位没人管。

**后果**：DB 认为已平仓 → monitor 不再监控（monitor 只监控 `OPEN`/`OPEN_DEGRADED`）→ 交易所那笔仓位在 SL/TP 触发时不影响 DB → 真钱风险。

## 二、目标

按 broker 返回的 `error_kind` 分支，分别写 DB：

| broker 结果 | DB 状态 | 后续动作 |
|---|---|---|
| success=True | `CLOSED` + 计算 PnL | 完成 |
| PERMANENT (仓位不存在/已强平/币对下架) | `CLOSED` + exit_reason 追加 `\|broker_permanent:<msg>` | 完成（DB 补记账，PnL 用最后信号价） |
| RETRYABLE (网络/超时) | 保持 `OPEN` + `error_context` merge 一条 close_error | monitor 下 tick 重新检测 → 重试 close_position |
| UNKNOWN (无 error_kind / broker 抛异常 / 无 success 字段) | `ERROR_RECONCILE_NEEDED` + `error_context` | 人工对账 |

## 三、范围

**In scope**:
- `scripts/v5_position_manager.py` `close_position` 方法重写（约 30 行 → 约 60 行）
- 抽 3 private helper：`_update_closed(...)`, `_append_close_error(...)`, `_mark_reconcile_needed(...)`
- `tests/test_v5_position_manager.py` 追加 4 个新 test（覆盖 4 个分支）

**Out of scope**:
- `V5PositionMonitor` 不动 —— 它天然只 tick `OPEN`/`OPEN_DEGRADED`，会自动重试 RETRYABLE 分支，会自动放过 `ERROR_RECONCILE_NEEDED`
- `scripts/paper_position_manager.py` 不动（SHADOW 路径无 broker，走虚拟平仓）
- `scripts/okx_trader.py` / `scripts/binance_trader.py` 的 `close_position` 现有 return dict shape 不改
- 不加 backoff / retry state（30s tick 已足够慢）
- 其他 P0（F3、SIGNAL_REVERSE fail）
- `.githooks/` / dev-log 机制

## 四、`positions_v5` schema 参照

已有列（来自 `scripts/local_db.py:80+`）：
- `status TEXT` — 值域: OPEN | OPEN_DEGRADED | CLOSED | ERROR_RECONCILE_NEEDED（Batch 1 已用）
- `error_context TEXT` — JSON 编码，Batch 1 open 失败已用
- `exit_price REAL`, `exit_time TEXT`, `exit_reason TEXT`, `pnl_usdt REAL`, `pnl_pct REAL`, `holding_minutes REAL`, `updated_at TEXT`

`error_context` 已经是 JSON blob；本 spec 只是给它加 close-side 字段。schema 不动。

## 五、Change 1 — `close_position` 重写

**新 `close_position`（替换现有 L234-268）**：

```python
def close_position(self, position_id: int, *, exit_price: float, exit_reason: str) -> None:
    conn = self._conn()
    try:
        row = conn.execute(
            "SELECT symbol, side, entry_price, size_usdt, leverage, entry_time, error_context "
            "FROM positions_v5 WHERE id=?", (position_id,)).fetchone()
        if not row:
            return
        symbol, side, entry_price, size_usdt, leverage, entry_time_str, existing_ctx_json = row

        # ── broker.close_position 结果分类 ──────────────
        broker_error_kind: Optional[str] = None
        broker_error_msg: Optional[str] = None
        try:
            rb_result = self.broker.close_position(symbol)
            if isinstance(rb_result, dict) and not rb_result.get("success"):
                broker_error_kind = rb_result.get("error_kind", "UNKNOWN")
                broker_error_msg = rb_result.get("error", "unknown")
        except Exception as e:
            broker_error_kind = "UNKNOWN"
            broker_error_msg = f"{type(e).__name__}: {e}"

        # ── 决策分支 ────────────────────────────────
        if broker_error_kind is None:
            # 成功 → 正常 CLOSED
            self._update_closed(
                conn, position_id, side, entry_price, size_usdt, leverage,
                entry_time_str, exit_price, exit_reason,
            )
        elif broker_error_kind == "PERMANENT":
            # 交易所已平（仓位不存在/币对下架/等）→ DB 补记账
            print(
                f"[V5PositionManager] close broker PERMANENT: {broker_error_msg}; "
                f"position {position_id} 交易所已平,DB 补记 CLOSED"
            )
            self._update_closed(
                conn, position_id, side, entry_price, size_usdt, leverage,
                entry_time_str, exit_price,
                f"{exit_reason}|broker_permanent:{broker_error_msg}",
            )
        elif broker_error_kind == "RETRYABLE":
            # 保持 OPEN + error_context,让 monitor 下 tick 重试
            print(
                f"[V5PositionManager] close broker RETRYABLE: {broker_error_msg}; "
                f"position {position_id} 保持 OPEN 待重试"
            )
            self._append_close_error(
                conn, position_id, "RETRYABLE", broker_error_msg, existing_ctx_json,
            )
        else:
            # UNKNOWN / 无 kind / 未预期异常 → 保守 → 需人工对账
            print(
                f"[V5PositionManager] close broker UNKNOWN error: {broker_error_msg}; "
                f"position {position_id} → ERROR_RECONCILE_NEEDED"
            )
            self._mark_reconcile_needed(
                conn, position_id, broker_error_msg, existing_ctx_json,
            )

        conn.commit()
    finally:
        conn.close()
```

## 六、Change 2 — 3 个 private helper

放在 `close_position` 上方（约 L230 位置）：

```python
def _update_closed(
    self, conn: sqlite3.Connection, position_id: int, side: str,
    entry_price: float, size_usdt: float, leverage: int,
    entry_time_str: str, exit_price: float, exit_reason: str,
) -> None:
    """成功平仓 or PERMANENT 补记账 —— 计算 PnL 并写 CLOSED。"""
    entry_time = datetime.fromisoformat(entry_time_str)
    exit_time = _utcnow()
    holding_minutes = (exit_time - entry_time).total_seconds() / 60
    notional = (size_usdt or 0) * (leverage or 1)
    if side == "LONG":
        pnl_pct = (exit_price - entry_price) / entry_price
    else:
        pnl_pct = (entry_price - exit_price) / entry_price
    pnl_usdt = notional * pnl_pct
    conn.execute("""
        UPDATE positions_v5 SET status='CLOSED', exit_price=?, exit_time=?,
          exit_reason=?, pnl_usdt=?, pnl_pct=?, holding_minutes=?, updated_at=?
        WHERE id=?
    """, (
        exit_price, exit_time.isoformat(), exit_reason,
        pnl_usdt, pnl_pct * 100, holding_minutes, exit_time.isoformat(), position_id,
    ))


def _append_close_error(
    self, conn: sqlite3.Connection, position_id: int, kind: str,
    msg: str, existing_ctx_json: Optional[str],
) -> None:
    """RETRYABLE:保持 status,合并 close_error 到 error_context。"""
    ctx = self._parse_error_context(existing_ctx_json)
    ctx["close_error"] = {
        "kind": kind, "msg": msg, "at": _utcnow().isoformat(),
    }
    conn.execute(
        "UPDATE positions_v5 SET error_context=?, updated_at=? WHERE id=?",
        (json.dumps(ctx), _utcnow().isoformat(), position_id),
    )


def _mark_reconcile_needed(
    self, conn: sqlite3.Connection, position_id: int, msg: str,
    existing_ctx_json: Optional[str],
) -> None:
    """UNKNOWN:标 ERROR_RECONCILE_NEEDED,合并 close_error。"""
    ctx = self._parse_error_context(existing_ctx_json)
    ctx["close_error"] = {
        "kind": "UNKNOWN", "msg": msg, "at": _utcnow().isoformat(),
    }
    conn.execute(
        "UPDATE positions_v5 SET status='ERROR_RECONCILE_NEEDED', "
        "error_context=?, updated_at=? WHERE id=?",
        (json.dumps(ctx), _utcnow().isoformat(), position_id),
    )


@staticmethod
def _parse_error_context(existing: Optional[str]) -> dict:
    """把已有 error_context JSON 反序列化 or 空 dict。"""
    if not existing:
        return {}
    try:
        v = json.loads(existing)
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        return {}
```

## 七、Change 3 — `tests/test_v5_position_manager.py` 追加 4 tests

复用 Batch 1 建的 `MagicMock(spec=OkxTrader)` 模式：

```python
import json


def _seeded_open_position(db_path: str) -> int:
    """辅助:插一条 OPEN LIVE 记录,返回 position_id。"""
    from unittest.mock import MagicMock
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.open_position.return_value = {"success": True, "order_id": "x"}
    mock_broker.set_stop_loss.return_value = {"success": True, "order_id": "sl"}
    mock_broker.set_take_profit.return_value = {"success": True, "order_id": "tp"}
    pm = V5PositionManager(broker=mock_broker, db_path=db_path)
    return pm.open_position(
        symbol="H/USDT", side="SHORT", entry_price=0.166,
        sl_price=0.169, tp_price=0.162, size_usdt=15, leverage=10,
    )


def test_close_success_marks_closed(tmp_path):
    import sqlite3, tempfile
    from unittest.mock import MagicMock
    from scripts.local_db import init_local_db
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    db = str(tmp_path / "x.db")
    init_local_db(db)
    pid = _seeded_open_position(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.close_position.return_value = {"success": True, "order_id": "rb"}
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, exit_price, exit_reason FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == "CLOSED"
    assert row[1] == 0.163
    assert row[2] == "TP_HIT"


def test_close_broker_permanent_still_marks_closed(tmp_path):
    """PERMANENT (交易所已平) → DB 补记 CLOSED,exit_reason 追加 broker_permanent。"""
    import sqlite3
    from unittest.mock import MagicMock
    from scripts.local_db import init_local_db
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    db = str(tmp_path / "x.db")
    init_local_db(db)
    pid = _seeded_open_position(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.close_position.return_value = {
        "success": False, "error_kind": "PERMANENT",
        "error": "position not found on exchange",
    }
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, exit_reason FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == "CLOSED"
    assert "broker_permanent" in row[1]
    assert "not found" in row[1]


def test_close_broker_retryable_keeps_open(tmp_path):
    """RETRYABLE → 保持 OPEN + error_context 有 RETRYABLE close_error。"""
    import sqlite3, json
    from unittest.mock import MagicMock
    from scripts.local_db import init_local_db
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    db = str(tmp_path / "x.db")
    init_local_db(db)
    pid = _seeded_open_position(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.close_position.return_value = {
        "success": False, "error_kind": "RETRYABLE",
        "error": "network timeout",
    }
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, error_context FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == "OPEN"
    ctx = json.loads(row[1])
    assert ctx["close_error"]["kind"] == "RETRYABLE"
    assert "network timeout" in ctx["close_error"]["msg"]


def test_close_broker_exception_marks_reconcile(tmp_path):
    """broker.close_position 抛异常 → ERROR_RECONCILE_NEEDED + error_context 含 UNKNOWN。"""
    import sqlite3, json
    from unittest.mock import MagicMock
    from scripts.local_db import init_local_db
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    db = str(tmp_path / "x.db")
    init_local_db(db)
    pid = _seeded_open_position(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.close_position.side_effect = RuntimeError("unexpected explode")
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, error_context FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == "ERROR_RECONCILE_NEEDED"
    ctx = json.loads(row[1])
    assert ctx["close_error"]["kind"] == "UNKNOWN"
    assert "unexpected explode" in ctx["close_error"]["msg"]
```

## 八、验收标准

- `python3 -m pytest tests/test_v5_position_manager.py -v` → 7/7 pass（3 existing + 4 new）
- 邻近 tests 无回归：
  - `tests/test_paper_position_manager_v5.py` 全 pass
  - `tests/test_v5_position_monitor.py` 15 pass / 3 pre-existing fail 数量不变
- 只 stage 1 文件（`scripts/v5_position_manager.py`）+ 1 modified test 文件
- 无其他文件误改
- Commit message subject exact match: `fix(v5_pm): close_position 分 error_kind 分支,不再吞 broker 失败 (F2)`

## 九、失效模式与降级

- **broker 返回不是 dict**（架构变了）：`isinstance(rb_result, dict)` 检查为 False → `broker_error_kind` 保持 None → 视为成功 → 老路径 CLOSED。行为等价于修前，可接受。
- **error_kind 是没预期的字符串**（比如 "TRANSIENT"）：不匹配 PERMANENT/RETRYABLE → 走 else 分支 → ERROR_RECONCILE_NEEDED（保守）
- **error_context 已有 open_error**（Batch 1 fail-open 场景）：新的 `close_error` 键 merge 进去，不覆盖 open_error
- **broker 返回 dict 但无 success 键**：`get("success")` 返 None → truthy False → 走失败分支 → error_kind 默认 UNKNOWN → ERROR_RECONCILE_NEEDED
- **broker 抛的异常里含 sensitive 数据（如 API key）**：`f"{type(e).__name__}: {e}"` 会打印到 error_context —— 应该 OK 因为已 catch 走的都是 broker 层，不太可能夹密钥；若发现风险再抽 exception sanitizer

## 十、超范围声明

- 不改 monitor 侧行为
- 不改 SHADOW `PaperPositionManager.close_position`（无 broker）
- 不改 broker 侧 `close_position` return shape（沿用 Batch 1 建立的约定）
- 不加 backoff / retry state
- 不改 F3 / SIGNAL_REVERSE
- 不动 dev-log 机制

## 十一、相关

- Bug audit `docs/audit-2026-07/bug-fix-list.md` Finding 2
- Batch 1 spec (让 broker 返 dict 而非抛)：`docs/superpowers/specs/2026-07-03-bug-fix-batch-1-F4-design.md`
- Batch 3 spec (settings_db helper 抽取模式)：`docs/superpowers/specs/2026-07-04-bug-fix-batch-3-F1-design.md`
- 引用文件：
  - `scripts/v5_position_manager.py:234-268`（当前 close_position）
  - `scripts/v5_position_manager.py:44-58`（`_insert_position` 里 error_context JSON 写入的既有模式，本 spec 借鉴）
