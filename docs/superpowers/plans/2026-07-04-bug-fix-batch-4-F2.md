# Bug Fix Batch 4 · F2 close_position 分 error_kind 分支 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修 `V5PositionManager.close_position` —— 按 broker 返回的 `error_kind` 分 4 支写 DB（success + PERMANENT → CLOSED；RETRYABLE → 保持 OPEN + error_context；UNKNOWN → ERROR_RECONCILE_NEEDED），而不是无脑标 CLOSED。

**Architecture:** 单 task TDD 循环：先写 4 个 close-scenario unit test（RED —— 现有代码全部标 CLOSED，非 success/UNKNOWN 断言失败）→ 重写 close_position + 抽 3 helper → GREEN → 邻近 tests 回归 → 单 commit。

**Tech Stack:** Python stdlib（json, sqlite3, datetime）+ pytest + `unittest.mock.MagicMock(spec=OkxTrader)`（Batch 1 建立的模式）。无新增 pip 依赖。

## Global Constraints

- Only 2 files touched: `scripts/v5_position_manager.py` + `tests/test_v5_position_manager.py`
- **`V5PositionManager.close_position(position_id, *, exit_price, exit_reason) -> None` 公开签名不变**
- **`V5PositionManager.__init__` 签名不变**
- **broker 返回契约不变**：`Dict[str, Any]` with `success`, `error`, `error_kind`（Batch 1 已建立）
- Error kind 值域：`PERMANENT` / `RETRYABLE` / `UNKNOWN`（其他值一律走 UNKNOWN 分支保守）
- `error_context` 用 JSON 字符串存 dict，新增 close_error 键，不覆盖 open_error（Batch 1 已用）
- Do NOT touch: `scripts/tasks/scorer.py`, `scripts/paper_position_manager.py`, `scripts/v5_position_monitor.py`, `scripts/okx_trader.py`, `scripts/binance_trader.py`, `.githooks/`, dev-log
- 现有 3 tests (`test_sl_tp_failure_rollbacks_main` / `test_successful_open_writes_positions_v5` / `test_broker_missing_method_fails_fast`) 必须依旧全 pass
- `tests/test_v5_position_monitor.py` 15 pass / 3 pre-existing SIGNAL_REVERSE fail 数量不变
- 需要 `from typing import Optional` import
- Single commit, subject: `fix(v5_pm): close_position 分 error_kind 分支,不再吞 broker 失败 (F2)`

---

## File Structure

| 路径 | 动作 |
|---|---|
| `scripts/v5_position_manager.py` | Modify — 加 `from typing import Optional` import；重写 `close_position` (原 L234-268)；紧邻新增 3 helper 方法（`_update_closed` / `_append_close_error` / `_mark_reconcile_needed`）+ 1 static helper（`_parse_error_context`） |
| `tests/test_v5_position_manager.py` | Modify — 追加 1 test helper `_seeded_open_position(db_path)` + 4 新 test cases 覆盖 4 分支 |

---

# Task 1: close_position 4-支重写 + 4 unit tests（single atomic commit）

**Files:**
- Modify: `scripts/v5_position_manager.py`
- Modify: `tests/test_v5_position_manager.py`

**Interfaces:**
- Consumes: `MagicMock(spec=OkxTrader)` 模式（Batch 1 已建）；`scripts.local_db.init_local_db` 建表；`json`, `sqlite3` stdlib
- Produces: 无对外新 API；公开签名 `close_position(position_id, *, exit_price, exit_reason)` 保持不变

## RED phase — 先写 4 tests 让它 fail

- [ ] **Step 1: 追加 test helper 到 `tests/test_v5_position_manager.py`**

在 test 文件末尾（现有 3 tests 之后）追加：

```python


# ── F2 close_position 分支测试 ─────────────────

def _seeded_open_position(db_path: str) -> int:
    """辅助:插一条 status=OPEN 的 LIVE 记录,返回 position_id。"""
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
```

- [ ] **Step 2: 追加 test 1 — success → CLOSED**

```python


def test_close_success_marks_closed(tmp_path):
    """broker.close_position 返 success=True → DB 标 CLOSED,PnL 有值。"""
    import sqlite3
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
```

- [ ] **Step 3: 追加 test 2 — PERMANENT → CLOSED with 特殊 exit_reason**

```python


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
```

- [ ] **Step 4: 追加 test 3 — RETRYABLE → 保持 OPEN + error_context**

```python


def test_close_broker_retryable_keeps_open(tmp_path):
    """RETRYABLE → 保持 OPEN + error_context 有 RETRYABLE close_error。"""
    import sqlite3
    import json
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
```

- [ ] **Step 5: 追加 test 4 — 抛异常 → ERROR_RECONCILE_NEEDED**

```python


def test_close_broker_exception_marks_reconcile(tmp_path):
    """broker.close_position 抛异常 → ERROR_RECONCILE_NEEDED + error_context 含 UNKNOWN。"""
    import sqlite3
    import json
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

- [ ] **Step 6: 跑测试 —— 期望 RED**

Run:
```bash
python3 -m pytest tests/test_v5_position_manager.py -v
```

Expected:
- 现有 3 tests PASS
- **`test_close_success_marks_closed` PASS**（现有代码在 success 分支下行为正确 —— 现代码里 broker 返成功 dict 时确实标 CLOSED）
- **`test_close_broker_permanent_still_marks_closed` FAIL** —— 现代码不追加 `broker_permanent` 到 exit_reason
- **`test_close_broker_retryable_keeps_open` FAIL** —— 现代码无论如何都标 CLOSED，断言 status="OPEN" 失败
- **`test_close_broker_exception_marks_reconcile` FAIL** —— 现代码抛异常后仍标 CLOSED

3 fails 就是 F2 bug 的运行证据。若 test 1 (`test_close_success_marks_closed`) 也 fail，说明 open_position 或 seed 有问题，先修那个。

## GREEN phase — 重写 close_position + 3 helper

- [ ] **Step 7: 加 `from typing import Optional` import**

在 `scripts/v5_position_manager.py` 文件顶部（现有 imports 后面）：

```python
import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional   # ← 新加
```

- [ ] **Step 8: 用替换重写 `close_position` (L234-268 现有代码)**

用 Edit 工具替换整个 `close_position` 方法体。用 unique substring `def close_position(self, position_id: int, *, exit_price: float, exit_reason: str) -> None:` 定位方法开头。替换为：

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
                # 交易所已平 → DB 补记账
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
                # 保持 OPEN + error_context, monitor 下 tick 重试
                print(
                    f"[V5PositionManager] close broker RETRYABLE: {broker_error_msg}; "
                    f"position {position_id} 保持 OPEN 待重试"
                )
                self._append_close_error(
                    conn, position_id, "RETRYABLE", broker_error_msg, existing_ctx_json,
                )
            else:
                # UNKNOWN → 保守 → 人工对账
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

- [ ] **Step 9: 在 `close_position` 上方追加 3 helper + 1 static helper**

在 `def close_position` 之前、上一个方法（可能是 `extend_position` 或 `get_open_positions`）之后，插入：

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

- [ ] **Step 10: 跑测试 —— 期望 GREEN**

```bash
python3 -m pytest tests/test_v5_position_manager.py -v
```

Expected: 7/7 PASS
- 现有 3 tests continue PASS
- 4 new tests PASS

若失败：
- `test_close_broker_retryable_keeps_open`：检查 Step 8 `RETRYABLE` 分支是否漏调 `_append_close_error`
- `test_close_broker_exception_marks_reconcile`：检查 Step 8 `except Exception` 分支是否把 `broker_error_kind` 设为 "UNKNOWN"（而非 None）
- `test_close_broker_permanent_still_marks_closed`：检查 exit_reason 拼接格式 `f"{exit_reason}|broker_permanent:{broker_error_msg}"`

## Sanity + commit

- [ ] **Step 11: 邻近 tests 无回归**

```bash
python3 -m pytest tests/test_paper_position_manager_v5.py tests/test_v5_position_monitor.py tests/test_settings_db.py -v 2>&1 | tail -15
```

Expected:
- `test_paper_position_manager_v5.py` 全 PASS
- `test_v5_position_monitor.py` 15 PASS / 3 pre-existing FAIL（SIGNAL_REVERSE 数量不变）
- `test_settings_db.py` 6/6 PASS

- [ ] **Step 12: sanity greps**

```bash
# 4 个新方法都存在
grep -n "def _update_closed\|def _append_close_error\|def _mark_reconcile_needed\|def _parse_error_context" scripts/v5_position_manager.py
# 期望：4 hits

# Optional import 已加
grep -n "from typing import Optional" scripts/v5_position_manager.py
# 期望：1 hit

# close_position 里 4 个分支的关键词都存在
grep -c "PERMANENT\|RETRYABLE\|ERROR_RECONCILE_NEEDED\|broker_error_kind" scripts/v5_position_manager.py
# 期望：≥ 4（这些字符串在新 close_position 里都出现）
```

- [ ] **Step 13: Commit**

```bash
git add scripts/v5_position_manager.py tests/test_v5_position_manager.py
git commit -m "$(cat <<'EOF'
fix(v5_pm): close_position 分 error_kind 分支,不再吞 broker 失败 (F2)

修 bug-fix-list.md Finding 2:V5PositionManager.close_position 之前
无论 broker.close_position 成不成功都无脑 UPDATE status='CLOSED',
交易所仍持仓时 DB 认为已平 → monitor 不再监控 → 真钱裸奔。

Change:
- close_position 读 broker 返 dict,按 error_kind 分 4 支:
  * success=True → CLOSED + PnL (老路径)
  * PERMANENT (仓位不存在/已强平) → CLOSED + exit_reason 追加
    "|broker_permanent:<msg>"
  * RETRYABLE (网络) → 保持 OPEN + error_context merge close_error,
    monitor 下 tick 天然重试 (只监控 OPEN/OPEN_DEGRADED)
  * UNKNOWN (无 kind / broker 抛异常 / 无 success 字段) →
    ERROR_RECONCILE_NEEDED + error_context,人工对账
- 抽 3 private helper: _update_closed / _append_close_error /
  _mark_reconcile_needed + 1 static _parse_error_context
- V5PositionManager.close_position 公开签名不变
- V5PositionManager.__init__ 签名不变
- monitor / paper_pm / broker 侧不改

Tests:
- 追加 4 unit tests 覆盖 4 分支 (success/PERMANENT/RETRYABLE/exception)
- 复用 Batch 1 建立的 MagicMock(spec=OkxTrader) 模式
- 现有 3 tests 无回归

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

# Self-Review 记录

- **spec § 五 Change 1 (close_position 4 分支)**：Step 8 完整替换 ✓
- **spec § 六 Change 2 (3 helper + 1 static)**：Step 9 完整实现 ✓
- **spec § 七 Change 3 (4 unit tests)**：Steps 2/3/4/5 分别对应 4 tests ✓
- **spec § 八 验收标准**：Step 10 (7/7 pass) + Step 11 (邻近无回归) + Step 12 (sanity) ✓
- **spec § 九 失效模式**：`isinstance(rb_result, dict)` 检查 + 意料外 error_kind 走 else UNKNOWN + 抛异常兜底 → 全部通过 close_position 内的分支逻辑覆盖 ✓
- **spec § 十 超范围**：文件严格 2 个 (v5_position_manager.py + test_v5_position_manager.py)，plan 不动 monitor/scorer/paper/broker ✓
- **Placeholder scan**：无 TBD / TODO / "similar to Task N"；每 step 有完整代码 ✓
- **Type consistency**：`Optional[str]`、`Dict`、helper 签名（第一参数 `conn: sqlite3.Connection`）在 spec + plan 一致 ✓
- **测试 RED→GREEN**：Step 6 = RED（3 fail），Step 10 = GREEN（7/7）✓
- **atomicity**：单 commit at Step 13，避免 git bisect 踩坏 commit ✓
