"""V5 风险计算器 — SL/TP 价格 + position size。

公式:
- SL 距离 = V5_SL_ATR_MULT × atr   (默认 1.5)
- TP 距离 = V5_TP_ATR_MULT × atr   (默认 2.5)
- size_usdt:让"价到 SL"亏损 = balance × risk_pct
    亏损 = sl_distance_pct × notional = sl_distance_pct × size_usdt × leverage
    → size_usdt = (balance × risk_pct) / (sl_distance_pct × leverage)
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
