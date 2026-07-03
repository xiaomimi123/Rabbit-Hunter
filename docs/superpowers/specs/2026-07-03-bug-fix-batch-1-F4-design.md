# Bug Fix Batch 1 · F4 broker method mismatch · Design

> 日期: 2026-07-03
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 4

---

## 一、问题陈述

`V5PositionManager.open_position()` 在 `scripts/v5_position_manager.py:80` / `:94` / `:135` 三处调用 `self.broker.create_order(...)`，但 `OkxTrader` 与 `BinanceTrader` **都没有 `create_order` 方法**（它们暴露 `open_position` / `set_stop_loss` / `set_take_profit`）。所有 LIVE 开仓请求会以 `AttributeError` 静默失败，scorer 记录 `OPEN_FAILED`。这就是 `positions_v5` 从来 0 行的真实原因 —— 不是 "SHADOW 兜底了" 而是 "LIVE 想开也开不了"。

Bug 未被单测拦截的根因：`tests/test_v5_position_manager.py` 用**无 spec 的 `MagicMock()`**，任何 attribute 访问都自动创建，broker method 打错也伪装成功。

## 二、目标

1. 让 LIVE 开仓真正能落地：把 3 处 `create_order` 换成实际的 broker method
2. **同时加固测试**：`MagicMock(spec=OkxTrader)` 使未来同类 attribute mismatch 立刻被捕捉

## 三、范围

**In scope**：
- `scripts/v5_position_manager.py` 三处 broker 调用替换 + 每处返回值的 `.get("success")` 检查（broker method 用 dict 结果，不抛异常）
- `tests/test_v5_position_manager.py` mock 加 `spec=OkxTrader`、stub 换成新 method、新增 1 条"spec 拦截生效"测试
- 保留 3 stage 状态机（main / SL / TP 独立 try/except）
- 保留 fail-open / fail-closed / `ERROR_RECONCILE_NEEDED` 全部分支
- 保留 `open_position()` 上游签名（scorer 不动）

**Out of scope**：
- 不改 `scripts/tasks/scorer.py`（scorer 只调 `pm.open_position()`，接口不变）
- 不改 `PaperPositionManager`（SHADOW 路径不涉及 broker）
- 不修 F5（依赖 F4 修复后才成为真实触发；下一批处理）
- 不修其他 P0（F1 / F2 / F3 各自单独批次）
- 不加真实 OKX/Binance testnet 集成测试（独立故事）
- 不改 dev-log 机制 / `.githooks/`

## 四、broker method signatures（已核实）

- `open_position(symbol: str, side: str, quantity: float, ...) -> Dict` —— `side` 接受 "LONG" / "SHORT"（内部转 "buy"/"sell"）
- `set_stop_loss(symbol: str, stop_price: float, side: str) -> Dict`
- `set_take_profit(symbol: str, take_profit_price: float, side: str) -> Dict`
- 返回 dict：`{"success": bool, "error": str, "error_kind": str, "order_id": ..., ...}`
- **不抛异常**（哪怕失败），失败通过 `result.get("success") == False` 表达

两个 trader 的 surface 完全对称（`okx_trader.py:465` / `binance_trader.py:645`）。

## 五、Change 1 — `scripts/v5_position_manager.py`

### 5.1 Stage 1 (main) L78-86

**Before**：
```python
try:
    self.broker.create_order(
        symbol=symbol, side="sell" if side == "SHORT" else "buy",
        type="market", amount=position_size_coins,
    )
except Exception as e:
    raise Exception(f"主仓下单失败: {type(e).__name__}: {e}")
```

**After**：
```python
try:
    result = self.broker.open_position(
        symbol=symbol, side=side, quantity=position_size_coins,
    )
    if not result.get("success"):
        raise Exception(
            f"主仓下单失败: {result.get('error_kind')}: {result.get('error')}"
        )
except Exception as e:
    if str(e).startswith("主仓下单失败:"):
        raise
    raise Exception(f"主仓下单失败: {type(e).__name__}: {e}")
```

理由：broker.open_position **不抛异常**，用 dict 表达失败。外层 try 保留以捕捉真意外（比如 broker 实例为 None）；内层 raise 保持原有的错误消息格式，scorer 侧的 `OPEN_FAILED:` 前缀逻辑不变。

### 5.2 Stage 2 (SL) L92-131

**Before**：
```python
try:
    self.broker.create_order(
        symbol=symbol, side="buy" if side == "SHORT" else "sell",
        type="stop_market", amount=position_size_coins,
        params={"stopPrice": sl_price, "reduceOnly": True},
    )
except Exception as e_sl:
    ...
```

**After**：
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
    ...  # 全部下游逻辑（sl_attached=False、rollback、ERROR_RECONCILE_NEEDED）保持不变
```

### 5.3 Stage 3 (TP) L133-168

同 Stage 2 pattern：`self.broker.create_order(...)` → `self.broker.set_take_profit(symbol=symbol, take_profit_price=tp_price, side=side)` + success 检查。

### 5.4 rollback path L104-105 / L145-146

`self.broker.close_position(symbol)` —— **broker.close_position 已存在**（L572 / L777），签名保留不改。若返回 dict 且 success=False，处理逻辑同前（记入 error_context.rollback_error）。

新增（微调）：
```python
# 回滚从 broker.close_position 提取结构化错误
rb_result = self.broker.close_position(symbol)
if isinstance(rb_result, dict) and not rb_result.get("success"):
    raise Exception(
        f"{rb_result.get('error_kind', 'PERMANENT')}: {rb_result.get('error')}"
    )
```

## 六、Change 2 — `tests/test_v5_position_manager.py`

### 6.1 所有 `MagicMock()` → `MagicMock(spec=OkxTrader)`

```python
from scripts.okx_trader import OkxTrader
# ...
mock_broker = MagicMock(spec=OkxTrader)
```

`spec=OkxTrader` 使 `mock_broker.create_order` 抛 `AttributeError`（因为 OkxTrader 上没这方法）。所有对 `.open_position` / `.set_stop_loss` / `.set_take_profit` / `.close_position` 的调用仍然自动 stub。

### 6.2 存根重写

**Before**：
```python
mock_broker.create_order.side_effect = [
    {"orderId": "main", "status": "filled"},
    Exception("SL order failed: insufficient margin"),
]
```

**After**：
```python
mock_broker.open_position.return_value = {
    "success": True, "order_id": "main", "symbol": "H/USDT", "side": "SHORT",
}
mock_broker.set_stop_loss.return_value = {
    "success": False, "error": "insufficient margin", "error_kind": "PERMANENT",
}
```

各测试的存根按其模拟场景对应设置（happy path 全 success=True，SL fail 让 set_stop_loss 返 success=False 等）。

### 6.3 新增测试

```python
def test_broker_missing_method_fails_fast():
    """spec=OkxTrader 会拦住任何 attribute 打错的 bug（F4 类回归）."""
    from scripts.okx_trader import OkxTrader
    mock_broker = MagicMock(spec=OkxTrader)
    # OkxTrader 上没有 create_order，spec mock 应拒绝
    with pytest.raises(AttributeError):
        mock_broker.create_order(symbol="X", side="buy")
```

## 七、覆盖场景

现有 4 条测试骨架保留，只改 mock 层的存根：

| 测试 | 主仓 | SL | TP | 期望 |
|---|---|---|---|---|
| `test_sl_tp_failure_rollbacks_main` | success | fail | - | broker.close_position 被调，抛 `SL 下单失败,主仓已回滚` |
| `test_successful_open_writes_positions_v5` | success | success | success | positions_v5 status=OPEN |
| (新增) `test_broker_missing_method_fails_fast` | - | - | - | AttributeError on create_order via spec mock |

若原文件已有 fail-open 或 TP-fail 测试，同样调整存根 —— 我未看全文；实施 plan 阶段执行者按实际测试数目调整。

## 八、验收标准

- `pytest tests/test_v5_position_manager.py -v` 全 pass（现有测试数 + 1 新）
- `grep -n "create_order" scripts/v5_position_manager.py` → 0 hits
- `grep -n "MagicMock()" tests/test_v5_position_manager.py` → 0 hits（全部带 spec）
- `grep -q "spec=OkxTrader" tests/test_v5_position_manager.py` → hit
- 只 stage 2 个文件（`scripts/v5_position_manager.py` + `tests/test_v5_position_manager.py`）
- 无其他文件被误改

## 九、失效模式与降级

- **broker.open_position 返回 dict 里的 error_kind 值域**：当前 OkxTrader 只输出 `PERMANENT` / `DUPLICATE` / `RETRYABLE`。新代码用 `.get('error_kind', 'PERMANENT')` fallback 兜底，确保任何未知 kind 也能拼出错误消息。
- **broker.open_position 抛非预期异常**（比如 broker 实例为 None）：外层 try 仍能捕获，走原 `raise Exception(f"主仓下单失败: {type(e).__name__}: {e}")` 兜底。
- **broker.close_position 返回不是 dict**（旧签名兼容）：`isinstance(rb_result, dict)` 检查跳过 success 检查，走原有 try/except 机制。

## 十、超范围声明

- 不改 scorer.py（不涉及 V5Scorer.process_enriched_v5 的调用点）
- 不动 paper_position_manager.py（不涉及 broker）
- 不新增 broker Protocol 抽象基类（另一个更大的重构决策，本次 YAGNI）
- 不加 testnet 集成测试（需要真实密钥、网络、CI 环境，独立 spec）

## 十一、相关

- Bug audit 交付：`docs/audit-2026-07/bug-fix-list.md` Finding 4
- 关联 Finding 5（LIVE monitor 静默停止）—— 修好 F4 后才成真触发，下一批处理
- Broker method 定义源：`scripts/okx_trader.py:465` (open_position), `:708` (set_stop_loss), `:711` (set_take_profit); `scripts/binance_trader.py:645` / `:948` / `:959`
