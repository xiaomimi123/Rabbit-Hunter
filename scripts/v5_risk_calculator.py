"""V5 风险计算器 — SL/TP 价格 + position size + 杠杆反推。

公式:
- SL 距离 = V5_SL_ATR_MULT × atr   (默认 1.5)
- TP 距离 = V5_TP_ATR_MULT × atr   (默认 2.5)
- size_usdt:让"价到 SL"亏损 = balance × risk_pct
    亏损 = sl_distance_pct × notional = sl_distance_pct × size_usdt × leverage
    → size_usdt = (balance × risk_pct) / (sl_distance_pct × leverage)
- 杠杆反推:按 SL 距离让"强平距 ≥ 2 × SL 距"成立的最大整数 leverage,
    再 cap 到用户配置(默认 5)。详见 derive_safe_leverage()。
"""
import os
from typing import Literal

from v5_types import RiskPlan

Side = Literal["LONG", "SHORT"]


def _f(env: str, default: float) -> float:
    raw = os.environ.get(env, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def derive_safe_leverage(*, entry: float, atr: float, leverage_cap: int) -> int:
    """按 SL 距离反推安全杠杆,使预期强平距 ≥ MIN_LIQ_TO_SL_DISTANCE_RATIO × SL 距。

    宪法 §5:强平价距 ≥ 止损价距的 2 倍。当 leverage_cap 已满足该约束,原样返回;
    否则降低到刚好满足。返回值至少为 1(无杠杆——理论上不会爆,gate 总会通过)。

    简化模型(isolated margin, 忽略 maintenance margin):
        liq_dist ≈ entry / leverage
        要 liq_dist ≥ R × sl_dist
        → leverage ≤ entry / (R × sl_dist)
    """
    from scripts.risk_constitution import MIN_LIQ_TO_SL_DISTANCE_RATIO
    from scripts.v5_params import get_param

    if entry <= 0 or atr <= 0 or leverage_cap <= 0:
        return max(1, leverage_cap)

    sl_mult = get_param("v5_sl_atr_mult", 1.5, float)
    sl_distance = sl_mult * atr
    if sl_distance <= 0:
        return max(1, leverage_cap)

    max_safe_float = entry / (MIN_LIQ_TO_SL_DISTANCE_RATIO * sl_distance)
    max_safe = max(1, int(max_safe_float))  # floor + 至少 1
    return min(leverage_cap, max_safe)


def plan(
    *,
    side: Side,
    entry: float,
    atr: float,
    balance: float,
    risk_pct: float,
    leverage: int,
) -> RiskPlan:
    """根据 ATR 和风险预算算出完整 RiskPlan。"""
    if atr <= 0:
        raise ValueError(f"atr must be > 0, got {atr}")
    if entry <= 0:
        raise ValueError(f"entry must be > 0, got {entry}")

    from scripts.v5_params import get_param
    sl_mult = get_param("v5_sl_atr_mult", 1.5, float)
    tp_mult = get_param("v5_tp_atr_mult", 2.5, float)

    sl_distance = sl_mult * atr
    tp_distance = tp_mult * atr

    if side == "LONG":
        sl_price = entry - sl_distance
        tp_price = entry + tp_distance
    else:  # SHORT
        sl_price = entry + sl_distance
        tp_price = entry - tp_distance

    sl_distance_pct = sl_distance / entry
    size_usdt = (balance * risk_pct) / (sl_distance_pct * leverage)
    size_usdt = max(1.0, size_usdt)

    expected_rr = tp_distance / sl_distance

    return RiskPlan(
        entry_price=entry,
        sl_price=sl_price,
        tp_price=tp_price,
        size_usdt=size_usdt,
        leverage=leverage,
        expected_rr=expected_rr,
    )
