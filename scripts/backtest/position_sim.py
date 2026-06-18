"""OHLC-touch position simulator for backtest.

Given an entry + risk plan + future klines, walks forward bar-by-bar to
detect when SL or TP price is touched by the candle's high/low. Conservative
when both touched in the same candle: assumes SL first (intra-candle path
unknowable).

Returns (exit_ts_ms, exit_price, exit_reason, realized_r) or all-None when
klines_after is empty / no risk distance.

R-value semantics:
  risk = |entry - sl|
  LONG:  r = (exit - entry) / risk     (positive when price rose)
  SHORT: r = (entry - exit) / risk     (positive when price fell)
"""
from __future__ import annotations

from typing import List, Literal, Optional, Tuple

Side = Literal["LONG", "SHORT"]
ExitReason = Literal["SL_HIT", "TP_HIT", "HORIZON_TIMEOUT"]


def simulate_exit(
    entry_ts: int,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    side: Side,
    klines_after: List[List[float]],
    max_hold_minutes: int,
    interval_min: int,
) -> Tuple[Optional[int], Optional[float], Optional[ExitReason], Optional[float]]:
    """Walk forward through klines_after; return first SL or TP hit, else timeout."""
    max_bars = max_hold_minutes // interval_min
    risk = abs(entry_price - sl_price)
    if risk == 0:
        return None, None, None, None
    if not klines_after:
        return None, None, None, None

    for k in klines_after[:max_bars]:
        ts, _o, high, low, _c, _v = k
        if side == "LONG":
            sl_hit = low <= sl_price
            tp_hit = high >= tp_price
            if sl_hit:
                return int(ts), sl_price, "SL_HIT", (sl_price - entry_price) / risk
            if tp_hit:
                return int(ts), tp_price, "TP_HIT", (tp_price - entry_price) / risk
        else:                                   # SHORT
            sl_hit = high >= sl_price
            tp_hit = low <= tp_price
            if sl_hit:
                return int(ts), sl_price, "SL_HIT", (sl_price - entry_price) / risk * -1.0
            if tp_hit:
                return int(ts), tp_price, "TP_HIT", (entry_price - tp_price) / risk

    # Only declare HORIZON_TIMEOUT when we've actually walked max_bars candles.
    # Otherwise the position is still open — caller should re-check on next tick.
    if len(klines_after) < max_bars:
        return None, None, None, None

    last = klines_after[max_bars - 1]
    exit_ts = int(last[0])
    exit_p = float(last[4])
    if side == "LONG":
        r = (exit_p - entry_price) / risk
    else:
        r = (entry_price - exit_p) / risk
    return exit_ts, exit_p, "HORIZON_TIMEOUT", r
