# Bug Fix Batch 14 · Finding 14 · LIVE exit_price 用 broker 实际成交价 · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 14 (P1)

---

## 一、问题陈述

`V5PositionManager.close_position()` (scripts/v5_position_manager.py:310-372) 接收上游(通常 `V5PositionMonitor._tick()` — scripts/v5_position_monitor.py:256)传入的 `exit_price`,该 price 是 **monitor tick 时的市价**,不是交易所实际 SL/TP 触发价。

- BTC 下跌至 SL=60000,交易所 stop_market 以 59990 成交(滑点 -0.017%)
- Monitor 30s 后 tick,当前价已回升到 60050
- `V5PositionManager.close_position` 收到 exit_price=59800(monitor 判 SL_HIT 时的实时价)或类似值
- `broker.close_position(symbol)` 若返 `PERMANENT`("无持仓") → DB 补记账时用 monitor tick 价
- **DB exit_price 与实际成交价永久偏差**,PnL 不准

但 `broker.close_position()`(scripts/okx_trader.py:646-657 / binance_trader.py:777)成功时的返回值里,已含 `"price": filled_px` 即实际成交价。当前 `V5PositionManager` **完全忽略**该字段。

## 二、目标

- **成功平仓**(V5PositionManager 主动触发)时,优先用 broker 返回的 `price`(真·成交价);无则 fallback caller's 传入(monitor tick)
- **PERMANENT** (交易所已提前平)时,broker 返 no fill data → 保留 caller's 传入(monitor tick),显式标记来源
- 所有 CLOSED / PERMANENT 补记账在 `positions_v5.error_context` 记 `"exit_price_source": "broker_fill"|"monitor_tick"|"monitor_tick_permanent"` —— 后续对账 / audit / debug 可见

## 三、范围

**In scope**:
- `scripts/v5_position_manager.py`:
  - `_update_closed()` 加 `exit_price_source: str = "monitor_tick"` 参数,写入 error_context
  - `close_position()` 成功分支从 `rb_result["price"]` 取实际 fill price
  - `close_position()` PERMANENT 分支标记 source
- `tests/test_v5_position_manager.py` 追加 3 tests(broker_fill / monitor_tick fallback / permanent 标记)

**Out of scope**:
- 不动 `V5PositionMonitor._tick()` —— 仍传入 tick 价作为 fallback,不 regress paper 路径
- 不动 paper 路径 —— paper 是仿真,exit_price 就是市价语义
- 不加 broker `fetch_my_trades` / `fetch_orders` 查询回填 —— YAGNI,broker 成功返回已含 price 字段,只 PERMANENT 场景无法拿到,标记 source 已足够审计
- 不改 error_context 的 close_error 清理逻辑
- 不改 PnL 计算逻辑本身
- 不改前端

## 四、Change 1 — `_update_closed` 加 source 参数

**Before**(scripts/v5_position_manager.py:235-270):
```python
def _update_closed(
    self, conn, position_id, side, entry_price, size_usdt, leverage,
    entry_time_str, exit_price, exit_reason, existing_ctx_json,
) -> None:
    ...
    ctx = self._parse_error_context(existing_ctx_json)
    ctx.pop("close_error", None)
    ctx_json = json.dumps(ctx) if ctx else None
    conn.execute("UPDATE positions_v5 SET status='CLOSED', ... error_context=?, ...")
```

**After**:
```python
def _update_closed(
    self, conn, position_id, side, entry_price, size_usdt, leverage,
    entry_time_str, exit_price, exit_reason, existing_ctx_json,
    exit_price_source: str = "monitor_tick",
) -> None:
    ...
    ctx = self._parse_error_context(existing_ctx_json)
    ctx.pop("close_error", None)
    ctx["exit_price_source"] = exit_price_source  # F14: audit trail
    ctx_json = json.dumps(ctx)  # ctx 至少含 source, 不再判空
    conn.execute("UPDATE positions_v5 SET status='CLOSED', ... error_context=?, ...")
```

## 五、Change 2 — `close_position` 成功分支用 broker fill price

**Before**(scripts/v5_position_manager.py:332-338 大致):
```python
if broker_error_kind is None:
    self._update_closed(
        conn, position_id, side, entry_price, size_usdt, leverage,
        entry_time_str, exit_price, exit_reason, existing_ctx_json,
    )
```

**After**:
```python
if broker_error_kind is None:
    # F14: broker 成功成交时优先用 fill price
    broker_price: Optional[float] = None
    if isinstance(rb_result, dict):
        raw = rb_result.get("price")
        if raw is not None:
            try:
                broker_price = float(raw)
            except (TypeError, ValueError):
                broker_price = None
    actual_exit = broker_price if broker_price is not None else exit_price
    source = "broker_fill" if broker_price is not None else "monitor_tick"
    self._update_closed(
        conn, position_id, side, entry_price, size_usdt, leverage,
        entry_time_str, actual_exit, exit_reason, existing_ctx_json,
        exit_price_source=source,
    )
```

## 六、Change 3 — `close_position` PERMANENT 分支标记 source

**Before**(scripts/v5_position_manager.py:339-350 大致):
```python
elif broker_error_kind == "PERMANENT":
    print(...)
    self._update_closed(
        conn, position_id, side, entry_price, size_usdt, leverage,
        entry_time_str, exit_price,
        f"{exit_reason}|broker_permanent:{broker_error_msg}",
        existing_ctx_json,
    )
```

**After**:
```python
elif broker_error_kind == "PERMANENT":
    print(...)
    # F14: 交易所已提前平,无 fill data,用 monitor tick 价 + 标记 source 让 audit 可见
    self._update_closed(
        conn, position_id, side, entry_price, size_usdt, leverage,
        entry_time_str, exit_price,
        f"{exit_reason}|broker_permanent:{broker_error_msg}",
        existing_ctx_json,
        exit_price_source="monitor_tick_permanent",
    )
```

## 七、Change 4 — 3 新 tests 追加到 `tests/test_v5_position_manager.py`

```python
def test_close_success_uses_broker_fill_price(tmp_path):
    """F14: broker 返 {'success':True, 'price':0.99} → DB exit_price=0.99 (非 caller 0.163) + source=broker_fill。"""
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
    mock_broker.close_position.return_value = {"success": True, "price": 0.99, "order_id": "rb"}
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT exit_price, error_context FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == 0.99  # broker fill, 非 caller's 0.163
    ctx = json.loads(row[1])
    assert ctx["exit_price_source"] == "broker_fill"


def test_close_success_no_broker_price_falls_back_to_caller(tmp_path):
    """F14: broker 返 success 但无 price 字段 → fallback caller's exit_price + source=monitor_tick。"""
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
    mock_broker.close_position.return_value = {"success": True, "order_id": "rb"}  # 无 price
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT exit_price, error_context FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == 0.163  # fallback caller's
    ctx = json.loads(row[1])
    assert ctx["exit_price_source"] == "monitor_tick"


def test_close_permanent_marks_monitor_tick_permanent_source(tmp_path):
    """F14: PERMANENT (交易所已平) → 用 caller exit_price + source=monitor_tick_permanent。"""
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
        "success": False, "error_kind": "PERMANENT",
        "error": "position not found on exchange",
    }
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, exit_price, error_context FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == "CLOSED"
    assert row[1] == 0.163
    ctx = json.loads(row[2])
    assert ctx["exit_price_source"] == "monitor_tick_permanent"
```

## 八、验收标准

- `python3 -m pytest tests/test_v5_position_manager.py -v` → 8/8 pass(现有 5 + 新 3)
- 邻近回归:`test_v5_position_close.py` 3/3(F12 baseline)
- `grep -c "exit_price_source" scripts/v5_position_manager.py` → ≥3(default param + 2 explicit passes + 1 write to ctx)
- `grep -c "broker_fill\|monitor_tick" scripts/v5_position_manager.py` → ≥3
- 只 stage 2 文件(`scripts/v5_position_manager.py` + `tests/test_v5_position_manager.py`)
- Commit subject EXACT: `fix(v5_position_manager): close 用 broker 实际成交价 + error_context 标 exit_price_source (Finding 14)`

## 九、失效模式

- **broker 返回 `price=None` 或非数值**:fallback 到 caller exit_price + source="monitor_tick"。已在 try/except (TypeError, ValueError) 兜。
- **PERMANENT 时交易所真实成交价永久丢失**:audit 建议 fallback `fetch_my_trades`,scope 太大;当前设计是"标 source 让审计层能识别到 monitor_tick 值不可信"。可接受降级。
- **error_context 从此永远非空**(至少含 exit_price_source)→ ctx_json 不再 NULL。DB 消费方(前端 / audit)如果曾用 `error_context IS NULL` 判"无异常",会误报。检查前端 / SQL 查询,若发现耦合,则加"过滤 exit_price_source 以外的 keys 才判是否异常"。**Spec check**:前端目前无消费 error_context IS NULL 的路径(V5ActivePositionsPage / DashboardPage 均未处理);后端 audit 层若有则单独 fix。
- **existing PermitTest 或 SuccessTest 现有断言 exit_price**:test line 98-122 mock 无 price → fallback → 断言仍 pass。line 125-152 PERMANENT → 断言 exit_reason 含 "broker_permanent"、"not found",不查 error_context → 仍 pass。**Verified: no regressions**。

## 十、超范围声明

- 不改 monitor 路径
- 不加 broker.fetch_my_trades 查询
- 不改 paper close_position
- 不改前端消费 error_context
- 不改 PnL 计算公式

## 十一、相关

- Bug audit: `docs/audit-2026-07/bug-fix-list.md` Finding 14 (P1)
- 引用:
  - `scripts/v5_position_manager.py:235-270`(_update_closed)
  - `scripts/v5_position_manager.py:310-372`(close_position)
  - `scripts/okx_trader.py:646-657`(broker close result 含 price)
  - `scripts/v5_position_monitor.py:256`(monitor tick 传 exit_price)
- 相关 Finding:F5(monitor 自愈)、F12(v5_position_close 端点也走 V5PositionManager)
