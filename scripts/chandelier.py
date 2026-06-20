"""M5 Chandelier 移动止损 — 让利润奔跑。

依据:Rabbit-Hunter 完整开发设计文档 v1.0 §7。

逻辑:
- LONG:trailing_sl = max(prev_trailing_sl, highest_seen - k × ATR)
- SHORT:trailing_sl = min(prev_trailing_sl, lowest_seen + k × ATR)
- 始终只收紧、不放宽。
- 退出时取 effective_sl = 更靠近当前价的那个(LONG 取 max, SHORT 取 min)。

k 默认 = v5_sl_atr_mult(1.5),与初始 SL 同步。
"""
from __future__ import annotations

from typing import Optional


def update_chandelier(
    *,
    side: str,
    current_price: float,
    entry_atr: float,
    highest_seen: Optional[float],
    lowest_seen: Optional[float],
    trailing_sl: Optional[float],
    k: float = 1.5,
) -> tuple[float, float, float]:
    """更新 trailing 状态。

    返回 (new_highest_seen, new_lowest_seen, new_trailing_sl)。
    """
    side_u = side.upper()
    if entry_atr <= 0:
        # ATR 缺失/异常:不更新 trailing,保持原值
        return (
            highest_seen if highest_seen is not None else current_price,
            lowest_seen if lowest_seen is not None else current_price,
            trailing_sl if trailing_sl is not None else 0.0,
        )

    new_high = max(highest_seen or current_price, current_price)
    new_low = min(lowest_seen or current_price, current_price)

    if side_u == "LONG":
        candidate = new_high - k * entry_atr
        if trailing_sl is None:
            new_trail = candidate
        else:
            new_trail = max(trailing_sl, candidate)  # 只收紧
    else:  # SHORT
        candidate = new_low + k * entry_atr
        if trailing_sl is None:
            new_trail = candidate
        else:
            new_trail = min(trailing_sl, candidate)

    return new_high, new_low, new_trail


def effective_sl_price(
    *,
    side: str,
    static_sl: float,
    trailing_sl: Optional[float],
) -> float:
    """退出时使用的实际 SL = 更靠近当前价的那个。

    LONG:max(static, trailing)(都比 entry 低,取大值=更近)
    SHORT:min(static, trailing)(都比 entry 高,取小值=更近)
    """
    if trailing_sl is None:
        return static_sl
    side_u = side.upper()
    if side_u == "LONG":
        return max(static_sl, trailing_sl)
    return min(static_sl, trailing_sl)
