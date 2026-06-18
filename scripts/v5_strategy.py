"""V5 策略决策器 — RSI 极值 ∩ MACD 同向拐点 AND 合谋(legacy)
                  + V5.1 trend_aligned 多周期对齐模式(default)。

入参纯数据(EnrichedItem + Indicators),出参 Decision。
无副作用、无 I/O。
"""
import os
from typing import Optional

from v5_types import Decision, EnrichedItem, Indicators


def _f(env: str, default: float) -> float:
    raw = os.environ.get(env, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bearish_cross(hist: float, hist_prev: float) -> bool:
    """MACD 由正变负(死叉拐点):上一根 ≥ 0,这一根 < 0。"""
    return hist_prev >= 0 and hist < 0


def _bullish_cross(hist: float, hist_prev: float) -> bool:
    """MACD 由负变正(金叉拐点):上一根 ≤ 0,这一根 > 0。"""
    return hist_prev <= 0 and hist > 0


# ──────────────────────────────────────────────────────────────────────────────
# Anti-chase helpers
# ──────────────────────────────────────────────────────────────────────────────

def _max_high_recent(klines, bars: int) -> float:
    """klines: list of (ts, o, h, l, c, v) tuples. Returns max high in last `bars`."""
    if not klines or bars <= 0:
        return float("inf")
    tail = klines[-bars:] if len(klines) >= bars else klines
    return max(k[2] for k in tail)


def _min_low_recent(klines, bars: int) -> float:
    if not klines or bars <= 0:
        return float("-inf")
    tail = klines[-bars:] if len(klines) >= bars else klines
    return min(k[3] for k in tail)


def _is_at_top(current_close: float, klines, bars: int, buffer_pct: float) -> bool:
    """Returns True if current_close is within buffer_pct of the recent high."""
    if buffer_pct <= 0 or bars <= 0:
        return False
    max_high = _max_high_recent(klines, bars)
    if max_high == float("inf"):
        return False
    return current_close >= max_high * (1 - buffer_pct)


def _is_at_bottom(current_close: float, klines, bars: int, buffer_pct: float) -> bool:
    if buffer_pct <= 0 or bars <= 0:
        return False
    min_low = _min_low_recent(klines, bars)
    if min_low == float("-inf"):
        return False
    return current_close <= min_low * (1 + buffer_pct)


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def decide(enriched: EnrichedItem, indicators: Indicators,
           funding_z: Optional[float] = None) -> Decision:
    """V5 决策。两种模式:and_strict (legacy) 或 trend_aligned (default)。

    funding_z(可选):当前 symbol 的 30d funding z-score。若 v5_params 里
    v5_funding_anti_pile_threshold > 0,trend_aligned 模式会在最终通过前
    检查 funding 拥挤度,反向加仓被阻塞。
    """
    from scripts.v5_params import get_param

    mode = get_param("v5_strategy_mode", "trend_aligned", str)

    if mode == "and_strict":
        return _decide_and_strict(enriched, indicators)
    return _decide_trend_aligned(enriched, indicators, funding_z=funding_z)


# ──────────────────────────────────────────────────────────────────────────────
# Legacy AND mode
# ──────────────────────────────────────────────────────────────────────────────

def _decide_and_strict(enriched: EnrichedItem, indicators: Indicators) -> Decision:
    """V5 legacy 严格 AND 模式."""
    from scripts.v5_params import get_param
    overbought = get_param("v5_rsi_overbought", 70.0, float)
    oversold = get_param("v5_rsi_oversold", 30.0, float)

    rsi = indicators.rsi_15m
    hist = indicators.macd_hist_15m
    hist_prev = indicators.macd_hist_prev_15m

    if rsi > overbought and _bearish_cross(hist, hist_prev):
        return Decision(
            should_trade=True, side="SHORT",
            reasoning=(
                f"[and_strict] RSI={rsi:.1f} 超买(>{overbought}) 且"
                f" MACD hist {hist_prev:+.4f}->{hist:+.4f} 死叉拐点"
            ),
            block_reason=None,
        )
    if rsi < oversold and _bullish_cross(hist, hist_prev):
        return Decision(
            should_trade=True, side="LONG",
            reasoning=(
                f"[and_strict] RSI={rsi:.1f} 超卖(<{oversold}) 且"
                f" MACD hist {hist_prev:+.4f}->{hist:+.4f} 金叉拐点"
            ),
            block_reason=None,
        )
    return Decision(
        should_trade=False, side=None,
        reasoning=(
            f"[and_strict] RSI={rsi:.1f}, MACD {hist_prev:+.4f}->{hist:+.4f}"
            f" — 不满足 RSI 极端 ∩ MACD 同向拐点"
        ),
        block_reason="NOT_RSI_AND_MACD",
    )


# ──────────────────────────────────────────────────────────────────────────────
# V5.1 trend_aligned mode
# ──────────────────────────────────────────────────────────────────────────────

def _decide_trend_aligned(enriched: EnrichedItem, indicators: Indicators,
                            *, funding_z: Optional[float] = None) -> Decision:
    """V5.1 trend_aligned 模式:4h MACD 锁方向 + 15m RSI 触发 + anti-chase
    + (可选)funding-anti-pile:拒绝同方向已经拥挤的开仓。"""
    from scripts.v5_params import get_param
    rsi_short_th = get_param("v5_trend_rsi_short_threshold", 60.0, float)
    rsi_long_th = get_param("v5_trend_rsi_long_threshold", 40.0, float)
    anti_chase_pct = get_param("v5_anti_chase_pct", 0.005, float)
    anti_chase_bars = get_param("v5_anti_chase_window_bars", 5, int)
    funding_anti_pile_th = get_param("v5_funding_anti_pile_threshold", 0.0, float)

    rsi_15m = indicators.rsi_15m
    macd_4h = indicators.macd_hist_4h
    current_close = enriched.current_price
    klines = enriched.klines_15m

    short_ok = (
        macd_4h is not None and macd_4h < 0
        and rsi_15m > rsi_short_th
    )
    long_ok = (
        macd_4h is not None and macd_4h > 0
        and rsi_15m < rsi_long_th
    )

    if short_ok:
        if _is_at_top(current_close, klines, anti_chase_bars, anti_chase_pct):
            return Decision(
                should_trade=False, side=None,
                reasoning=(
                    f"[trend_aligned] SHORT 候选 但 anti_chase 触发 — "
                    f"current {current_close:.4f} 距 {anti_chase_bars} 根高点 < {anti_chase_pct*100:.1f}%"
                ),
                block_reason="ANTI_CHASE_TOP",
            )
        if (funding_anti_pile_th > 0 and funding_z is not None
                and funding_z <= -funding_anti_pile_th):
            return Decision(
                should_trade=False, side=None,
                reasoning=(
                    f"[trend_aligned] SHORT 候选 但 funding-anti-pile 触发 — "
                    f"z={funding_z:+.2f} (空头已拥挤,加仓低 EV)"
                ),
                block_reason="FUNDING_SHORTS_CROWDED",
            )
        return Decision(
            should_trade=True, side="SHORT",
            reasoning=(
                f"[trend_aligned] 4h MACD hist {macd_4h:+.4f} (下行) "
                f"+ 15m RSI={rsi_15m:.1f}>{rsi_short_th} (回弹乏力) "
                f"+ 距高点 ≥ {anti_chase_pct*100:.1f}%"
            ),
            block_reason=None,
        )

    if long_ok:
        if _is_at_bottom(current_close, klines, anti_chase_bars, anti_chase_pct):
            return Decision(
                should_trade=False, side=None,
                reasoning=(
                    f"[trend_aligned] LONG 候选 但 anti_chase 触发 — "
                    f"current {current_close:.4f} 距 {anti_chase_bars} 根低点 < {anti_chase_pct*100:.1f}%"
                ),
                block_reason="ANTI_CHASE_BOTTOM",
            )
        if (funding_anti_pile_th > 0 and funding_z is not None
                and funding_z >= funding_anti_pile_th):
            return Decision(
                should_trade=False, side=None,
                reasoning=(
                    f"[trend_aligned] LONG 候选 但 funding-anti-pile 触发 — "
                    f"z={funding_z:+.2f} (多头已拥挤,加仓低 EV)"
                ),
                block_reason="FUNDING_LONGS_CROWDED",
            )
        return Decision(
            should_trade=True, side="LONG",
            reasoning=(
                f"[trend_aligned] 4h MACD hist {macd_4h:+.4f} (上行) "
                f"+ 15m RSI={rsi_15m:.1f}<{rsi_long_th} (回调乏力) "
                f"+ 距低点 ≥ {anti_chase_pct*100:.1f}%"
            ),
            block_reason=None,
        )

    # 都不满足,解释清楚
    reasons = []
    if macd_4h is None or macd_4h == 0:
        reasons.append("4h MACD 中性")
    elif macd_4h < 0 and rsi_15m <= rsi_short_th:
        reasons.append(f"15m RSI={rsi_15m:.1f} 不到 SHORT 阈值 {rsi_short_th}")
    elif macd_4h > 0 and rsi_15m >= rsi_long_th:
        reasons.append(f"15m RSI={rsi_15m:.1f} 不到 LONG 阈值 {rsi_long_th}")

    return Decision(
        should_trade=False, side=None,
        reasoning=(
            f"[trend_aligned] 4h MACD={macd_4h:+.4f} 15m RSI={rsi_15m:.1f}"
            f" — {' / '.join(reasons) if reasons else '无满足条件'}"
        ),
        block_reason="NOT_TREND_ALIGNED",
    )
