# Bug Fix Batch 1 · F4 broker method mismatch · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修 `V5PositionManager.open_position()` 3 处对不存在方法 `self.broker.create_order()` 的调用（换成实际存在的 `open_position` / `set_stop_loss` / `set_take_profit`），并把 `tests/test_v5_position_manager.py` 的 MagicMock 加上 `spec=OkxTrader` 防止同类回归。

**Architecture:** 单 task TDD 循环：先重构测试（存根换新 method + 加 spec）→ 跑测试确认 RED（因为生产代码还调 `create_order`）→ 改生产代码 3 stage 与 rollback 路径 → 跑测试确认 GREEN → sanity grep → 单 commit。

**Tech Stack:** Python + pytest + unittest.mock。无新增 pip 依赖。

## Global Constraints

- Only 2 files touched: `scripts/v5_position_manager.py` + `tests/test_v5_position_manager.py`
- **3 stage 状态机保留**（main / SL / TP 独立 try/except，fail-open / fail-closed 分支 + `ERROR_RECONCILE_NEEDED` 不变）
- **broker methods 已核实存在**：`open_position(symbol, side, quantity, ...)`, `set_stop_loss(symbol, stop_price, side)`, `set_take_profit(symbol, take_profit_price, side)`, `close_position(symbol, ...)` —— 全返回 `Dict[str, Any]` 含 `success: bool`, `error`, `error_kind`
- **不改**：`scripts/tasks/scorer.py`, `scripts/paper_position_manager.py`, dev-log 机制, `.githooks/`
- **测试 spec 加固**：所有 `MagicMock()` → `MagicMock(spec=OkxTrader)` （不新增 broker Protocol 抽象）
- **新增 1 条测试**：`test_broker_missing_method_fails_fast` 证明 spec 拦截生效
- **v5_position_manager.open_position() 上游签名保持**：scorer 侧不用改
- Commit message subject: `fix(v5_pm): 3 处 create_order → 真实 broker method + tests spec 加固 (F4)`

---

## File Structure

| 路径 | 动作 |
|---|---|
| `scripts/v5_position_manager.py` | Modify L80/L94/L135（3 处 create_order 换 method）+ L104/L145（rollback close_position 返回值处理）|
| `tests/test_v5_position_manager.py` | Modify（2 个测试 mock 加 spec + 存根重写）+ Add（1 个新测试 `test_broker_missing_method_fails_fast`）|

---

# Task 1: 用 broker 真实方法 + spec 加固测试

**Files:**
- Modify: `scripts/v5_position_manager.py`（L80, L94, L104-108, L135, L145-149）
- Modify + Add: `tests/test_v5_position_manager.py`（现 50 行 → 约 100 行）

**Interfaces:**
- Consumes: `scripts.okx_trader.OkxTrader` （import spec source）
- Produces: unchanged public signature of `V5PositionManager.open_position()`

## RED phase — 先改测试让它 fail

- [ ] **Step 1: 顶部 import OkxTrader**

在 `tests/test_v5_position_manager.py` 第 3 行后加：

```python
from scripts.okx_trader import OkxTrader
```

- [ ] **Step 2: 改 `test_sl_tp_failure_rollbacks_main` 的 mock**

替换（L6-24 区间的现有测试）：

```python
def test_sl_tp_failure_rollbacks_main():
    """主仓开成功,SL 单失败 → 立刻市价平回滚。"""
    from scripts.v5_position_manager import V5PositionManager

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.open_position.return_value = {
        "success": True, "order_id": "main", "symbol": "H/USDT", "side": "SHORT",
    }
    mock_broker.set_stop_loss.return_value = {
        "success": False, "error": "insufficient margin", "error_kind": "PERMANENT",
    }
    mock_broker.close_position.return_value = {
        "success": True, "order_id": "rb", "symbol": "H/USDT",
    }

    pm = V5PositionManager(broker=mock_broker, db_path=":memory:")

    with pytest.raises(Exception, match="SL"):
        pm.open_position(
            symbol="H/USDT", side="SHORT", entry_price=0.166,
            sl_price=0.169, tp_price=0.162, size_usdt=15, leverage=10,
        )
    mock_broker.close_position.assert_called_once()
```

- [ ] **Step 3: 改 `test_successful_open_writes_positions_v5` 的 mock**

替换（L27-50 区间的现有测试）：

```python
def test_successful_open_writes_positions_v5():
    """都成功 → 写 positions_v5 一行,status=OPEN。"""
    import sqlite3, tempfile
    from scripts.local_db import init_local_db
    from scripts.v5_position_manager import V5PositionManager

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    init_local_db(tmp.name)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.open_position.return_value = {
        "success": True, "order_id": "main", "symbol": "H/USDT", "side": "SHORT",
    }
    mock_broker.set_stop_loss.return_value = {
        "success": True, "order_id": "sl", "symbol": "H/USDT",
    }
    mock_broker.set_take_profit.return_value = {
        "success": True, "order_id": "tp", "symbol": "H/USDT",
    }

    pm = V5PositionManager(broker=mock_broker, db_path=tmp.name)
    pid = pm.open_position(
        symbol="H/USDT", side="SHORT", entry_price=0.166,
        sl_price=0.169, tp_price=0.162, size_usdt=15, leverage=10,
    )

    conn = sqlite3.connect(tmp.name)
    row = conn.execute("SELECT symbol, side, status FROM positions_v5 WHERE id=?",
                       (pid,)).fetchone()
    conn.close()
    assert row == ("H/USDT", "SHORT", "OPEN")
```

- [ ] **Step 4: 在文件末尾追加新测试 `test_broker_missing_method_fails_fast`**

```python


def test_broker_missing_method_fails_fast():
    """spec=OkxTrader 拦住任何 attribute 打错的 bug（F4 类回归防护）."""
    mock_broker = MagicMock(spec=OkxTrader)
    # OkxTrader 上没有 create_order 方法。spec mock 应拒绝这个访问。
    with pytest.raises(AttributeError):
        mock_broker.create_order(symbol="H/USDT", side="sell")
```

- [ ] **Step 5: 跑测试 —— 期望 RED**

Run:
```bash
python3 -m pytest tests/test_v5_position_manager.py -v
```

Expected: 
- `test_broker_missing_method_fails_fast` PASS（spec 生效证明）
- `test_sl_tp_failure_rollbacks_main` FAIL —— 因为 `v5_position_manager.py` 仍调 `self.broker.create_order(...)` → 触发 AttributeError（spec 拦截）→ 不匹配 `match="SL"`
- `test_successful_open_writes_positions_v5` FAIL —— 同样 AttributeError

**这就是我们要证明的 bug**：spec 加固后，现有生产代码在测试里立刻暴露。

## GREEN phase — 改生产代码让测试通过

- [ ] **Step 6: 改 Stage 1 (main) L78-86**

Read L78-86 of `scripts/v5_position_manager.py`，把 try 块内的 `create_order` 调用替换为：

```python
try:
    result = self.broker.open_position(
        symbol=symbol, side=side, quantity=position_size_coins,
    )
    if not result.get("success"):
        raise Exception(
            f"主仓下单失败: {result.get('error_kind', 'PERMANENT')}: {result.get('error', 'unknown')}"
        )
except Exception as e:
    if str(e).startswith("主仓下单失败:"):
        raise
    raise Exception(f"主仓下单失败: {type(e).__name__}: {e}")
```

- [ ] **Step 7: 改 Stage 2 (SL) L92-100**

替换 try 块内的 `create_order`：

```python
try:
    result = self.broker.set_stop_loss(
        symbol=symbol, stop_price=sl_price, side=side,
    )
    if not result.get("success"):
        raise Exception(
            f"{result.get('error_kind', 'PERMANENT')}: {result.get('error', 'unknown')}"
        )
except Exception as e_sl:
    # 下游 fail-open / fail-closed / ERROR_RECONCILE_NEEDED 逻辑保持不变
```

**只替换 try 块内那 5 行**，下面的 `except e_sl:` 块及后续 rollback / fail-open 逻辑一字不改。

- [ ] **Step 8: 改 Stage 3 (TP) L133-141**

替换 try 块内的 `create_order`：

```python
try:
    result = self.broker.set_take_profit(
        symbol=symbol, take_profit_price=tp_price, side=side,
    )
    if not result.get("success"):
        raise Exception(
            f"{result.get('error_kind', 'PERMANENT')}: {result.get('error', 'unknown')}"
        )
except Exception as e_tp:
    # 下游 fail-open / fail-closed / ERROR_RECONCILE_NEEDED 逻辑保持不变
```

- [ ] **Step 9: 改 rollback path (L104-108 for SL fail-closed)**

原代码：
```python
try:
    self.broker.close_position(symbol)
    raise Exception(f"SL 下单失败,主仓已回滚: {e_sl}")
except Exception as e_rb:
    if "已回滚" in str(e_rb):
        raise
    ...
```

改成：
```python
try:
    rb_result = self.broker.close_position(symbol)
    if isinstance(rb_result, dict) and not rb_result.get("success"):
        raise Exception(
            f"{rb_result.get('error_kind', 'PERMANENT')}: {rb_result.get('error', 'unknown')}"
        )
    raise Exception(f"SL 下单失败,主仓已回滚: {e_sl}")
except Exception as e_rb:
    if "已回滚" in str(e_rb):
        raise
    ...
```

对 TP fail-closed 分支（约 L145-149）做**相同**的修改（把 `close_position` 的返回处理 + `"TP 下单失败,主仓已回滚"` 消息）。

- [ ] **Step 10: 跑测试 —— 期望 GREEN**

Run:
```bash
python3 -m pytest tests/test_v5_position_manager.py -v
```

Expected: 3/3 PASS
- `test_sl_tp_failure_rollbacks_main` PASS
- `test_successful_open_writes_positions_v5` PASS
- `test_broker_missing_method_fails_fast` PASS

若任一 FAIL：
- `test_sl_tp_failure_rollbacks_main`：可能 rollback 消息模式错，检查 Step 9 分支
- `test_successful_open_writes_positions_v5`：检查 Step 6/7/8 是否 3 个 method 都成功返回值
- `test_broker_missing_method_fails_fast`：spec 未生效，检查 Step 4 的 import OkxTrader

## Sanity + commit

- [ ] **Step 11: sanity grep 确认无残留 & 全项目回归**

```bash
# 生产代码不应还有 create_order 引用
grep -n "create_order" scripts/v5_position_manager.py
# 期望：0 hits

# 测试全部用 spec 加固
grep -n "MagicMock()" tests/test_v5_position_manager.py
# 期望：0 hits（应该全是 MagicMock(spec=OkxTrader)）

# 关联单测（paper monitor / position close API）没被误伤
python3 -m pytest tests/test_paper_position_manager_v5.py tests/test_v5_position_close_api.py tests/test_v5_position_monitor.py -v 2>&1 | tail -10
# 期望：全 PASS
```

- [ ] **Step 12: Commit**

```bash
git add scripts/v5_position_manager.py tests/test_v5_position_manager.py
git commit -m "$(cat <<'EOF'
fix(v5_pm): 3 处 create_order → 真实 broker method + tests spec 加固 (F4)

修 bug-fix-list.md Finding 4：V5PositionManager 之前调 broker.create_order
(方法不存在于 OkxTrader/BinanceTrader)，导致所有 LIVE 开仓 AttributeError
静默失败 —— positions_v5 从来 0 行。

Change:
- L80 create_order → broker.open_position(symbol, side, quantity)
- L94 create_order → broker.set_stop_loss(symbol, stop_price, side)
- L135 create_order → broker.set_take_profit(symbol, take_profit_price, side)
- rollback path close_position 返回值加 success 检查
- 3 stage 状态机 / fail-open / fail-closed / ERROR_RECONCILE_NEEDED 保留

Tests:
- MagicMock() → MagicMock(spec=OkxTrader)（同类 bug 未来立刻被拦截）
- 存根重写为 open_position / set_stop_loss / set_take_profit
- 新增 test_broker_missing_method_fails_fast 证明 spec 生效

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

# Self-Review 记录

- **spec § 五 Change 1 三段**：Step 6 / 7 / 8 分别对应 main / SL / TP ✓
- **spec § 五.4 rollback path**：Step 9 覆盖 SL 和 TP fail-closed 两处 ✓
- **spec § 六 Change 2 mock + spec**：Step 1（import）+ Step 2/3（现有 2 测试改 mock）+ Step 4（新增 fails_fast）✓
- **spec § 八 验收标准**：Step 11 sanity greps + `pytest -v` 3/3 ✓
- **spec § 十 超范围**：文件清单严格 2 个（scripts/v5_position_manager.py + tests/test_v5_position_manager.py），plan 不动 scorer / paper_pm ✓
- **Placeholder scan**：无 TBD / TODO；每 step 有完整代码或命令 ✓
- **Type consistency**：`open_position(symbol, side, quantity)` 用同一 signature；返回 `Dict[str, Any]` 一致 ✓
- **测试 RED→GREEN**：Step 5 = RED（生产代码未改）；Step 10 = GREEN（生产改后）；Step 4 的 `test_broker_missing_method_fails_fast` 从头 PASS（因为 mock 内部行为，与生产代码无关）✓
