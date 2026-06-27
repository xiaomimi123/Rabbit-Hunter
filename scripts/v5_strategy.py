"""V5 策略决策器 — 三种 mode:
  - and_strict (legacy):       RSI 极值 ∩ MACD 同向拐点 AND 合谋
  - trend_aligned (default):   4h MACD 方向 + 15m RSI 极端 + anti-chase
  - macd_reversal_long:        4h MACD 在零线下方金叉 → LONG only (反转打法)

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
    """V5 决策。三种模式:
      and_strict        — legacy RSI + MACD AND 合谋
      trend_aligned     — default,4h 趋势 + 15m RSI 极端 + anti-chase
      macd_reversal_long — 4h 收盘金叉(交叉前两线 < 0)→ LONG only

    funding_z(可选):当前 symbol 的 30d funding z-score。仅 trend_aligned
    模式使用(funding-anti-pile)。
    """
    from scripts.v5_params import get_param

    mode = get_param("v5_strategy_mode", "trend_aligned", str)

    if mode == "and_strict":
        return _decide_and_strict(enriched, indicators)
    if mode == "macd_reversal_long":
        return _decide_macd_reversal_long(enriched, indicators)
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


# ──────────────────────────────────────────────────────────────────────────────
# macd_reversal_long mode (Variant B from MACD entry timing experiment)
# ──────────────────────────────────────────────────────────────────────────────

def _decide_macd_reversal_long(
    enriched: EnrichedItem, indicators: Indicators,
) -> Decision:
    """4h MACD 在零线下方金叉 → LONG only。

    严格条件:
      1. 当根 4h dif > dea (上穿)
      2. 上一根 4h dif <= dea (确认刚交叉)
      3. 交叉前一根 dif < 0 且 dea < 0 (反转打法,只做零线下方金叉)

    SHORT 信号永远不放(本 mode 不做空)。

    依据 scripts/experiments/macd_cross_entry_wf.py 验证:
      - 主实验 (2026-03→2026-06 OOS, 17 symbol): n=165 win=64% net PF=2.08
      - Q1 stress (2026-Q1 完全独立 OOS): n=269 win=65% net PF=2.25
      两个不重叠 6 个月 OOS 窗口稳定 PF 2.0+,无过拟合迹象。
    """
    # 复用 v5_indicator_engine._ema 保证公式与 indicators 计算一致
    from v5_indicator_engine import _ema

    klines_4h = enriched.klines_4h
    # 至少需 slow(26) + signal(9) 个 bar 算 dif/dea
    if len(klines_4h) < 35:
        return Decision(
            should_trade=False, side=None,
            reasoning=(
                f"[macd_reversal] 4h K 线={len(klines_4h)} 根 "
                f"不足 35(slow=26+signal=9),无法判断"
            ),
            block_reason="INSUFFICIENT_4H_KLINES",
        )

    closes = [float(k[4]) for k in klines_4h]
    ema_fast = _ema(closes, 12)
    ema_slow = _ema(closes, 26)
    dif = [f - s for f, s in zip(ema_fast, ema_slow)]
    dea = _ema(dif, 9)

    d_now, d_prev = dif[-1], dif[-2]
    e_now, e_prev = dea[-1], dea[-2]

    # 条件 1+2: 当根金叉
    if not (d_now > e_now and d_prev <= e_prev):
        return Decision(
            should_trade=False, side=None,
            reasoning=(
                f"[macd_reversal] 当根 dif={d_now:+.5f} dea={e_now:+.5f} "
                f"prev dif={d_prev:+.5f} dea={e_prev:+.5f} — 未出现金叉"
            ),
            block_reason="NO_4H_GOLDEN_CROSS",
        )

    # 条件 3: 交叉前两线都 < 0 (零下金叉,反转打法)
    if not (d_prev < 0 and e_prev < 0):
        return Decision(
            should_trade=False, side=None,
            reasoning=(
                f"[macd_reversal] 4h 金叉成立但交叉前 dif={d_prev:+.5f} "
                f"dea={e_prev:+.5f} 不全 < 0 (本 mode 要求零线下方金叉)"
            ),
            block_reason="CROSS_NOT_BELOW_ZERO",
        )

    return Decision(
        should_trade=True, side="LONG",
        reasoning=(
            f"[macd_reversal] 4h 收盘金叉成立 "
            f"dif {d_prev:+.5f}→{d_now:+.5f} 上穿 dea {e_prev:+.5f}→{e_now:+.5f} "
            f"且交叉前两线 < 0"
        ),
        block_reason=None,
    )
