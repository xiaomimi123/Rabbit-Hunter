"""V5 策略决策器 — RSI 极值 ∩ MACD 同向拐点 AND 合谋。

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


def decide(enriched: EnrichedItem, indicators: Indicators) -> Decision:
    """V5 AND 合谋决策。"""
    overbought = _f("V5_RSI_OVERBOUGHT", 70.0)
    oversold = _f("V5_RSI_OVERSOLD", 30.0)

    rsi = indicators.rsi_15m
    hist = indicators.macd_hist_15m
    hist_prev = indicators.macd_hist_prev_15m

    # SHORT:RSI 超买 + MACD 死叉拐点
    if rsi > overbought and _bearish_cross(hist, hist_prev):
        return Decision(
            should_trade=True,
            side="SHORT",
            reasoning=(
                f"RSI={rsi:.1f} 超买(>{overbought})"
                f" 且 MACD hist {hist_prev:+.4f}→{hist:+.4f} 死叉拐点"
            ),
            block_reason=None,
        )

    # LONG:RSI 超卖 + MACD 金叉拐点
    if rsi < oversold and _bullish_cross(hist, hist_prev):
        return Decision(
            should_trade=True,
            side="LONG",
            reasoning=(
                f"RSI={rsi:.1f} 超卖(<{oversold})"
                f" 且 MACD hist {hist_prev:+.4f}→{hist:+.4f} 金叉拐点"
            ),
            block_reason=None,
        )

    # 拒:讲清楚哪一边没满足
    return Decision(
        should_trade=False,
        side=None,
        reasoning=(
            f"RSI={rsi:.1f}, MACD hist {hist_prev:+.4f}→{hist:+.4f} —"
            f" 不满足 RSI∈(<{oversold} or >{overbought}) ∩ MACD 同向拐点"
        ),
        block_reason="NOT_RSI_AND_MACD",
    )
