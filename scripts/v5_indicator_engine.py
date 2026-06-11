"""V5 指标引擎 — 纯函数,无副作用,易测试。

提供 RSI / MACD / ATR 三个核心指标,以及一个集成入口 calculate_indicators
接受 15min + 4h 两组 K 线,返回 Indicators 数据类。

K 线格式约定:list[(ts_ms, open, high, low, close, volume)]
"""
from typing import List, Tuple

from v5_types import Indicators


Kline = Tuple[int, float, float, float, float, float]


def _closes(klines: List[Kline]) -> List[float]:
    return [k[4] for k in klines]


def _highs_lows_closes(klines: List[Kline]) -> Tuple[List[float], List[float], List[float]]:
    highs = [k[2] for k in klines]
    lows = [k[3] for k in klines]
    closes = [k[4] for k in klines]
    return highs, lows, closes


# ===== RSI =====

def calculate_rsi(klines: List[Kline], period: int = 14) -> float:
    """Wilder's RSI on close prices。"""
    if len(klines) < period + 1:
        raise ValueError(f"InsufficientKlines: need ≥ {period + 1}, got {len(klines)}")

    closes = _closes(klines)
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    # 初始平均:前 period 个的简单平均
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder smoothing:之后用 (prev*(period-1) + curr) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


# ===== MACD =====

def _ema(values: List[float], period: int) -> List[float]:
    """指数移动平均,返回逐根的 EMA 序列(长度等于 values)。"""
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1.0 - k))
    return ema


def calculate_macd(
    klines: List[Kline],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[float, float, float, float]:
    """返回 (macd, signal, hist, hist_prev)。
    hist_prev 是倒数第二根的 hist,用来检测拐点(变号)。
    """
    if len(klines) < slow + signal:
        raise ValueError(
            f"InsufficientKlines: MACD need ≥ {slow + signal}, got {len(klines)}"
        )
    closes = _closes(klines)
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_series = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_series = _ema(macd_series, signal)
    hist_series = [m - s for m, s in zip(macd_series, signal_series)]
    return (
        float(macd_series[-1]),
        float(signal_series[-1]),
        float(hist_series[-1]),
        float(hist_series[-2]),
    )


# ===== ATR =====

def calculate_atr(klines: List[Kline], period: int = 14) -> float:
    """Wilder's ATR。"""
    if len(klines) < period + 1:
        raise ValueError(f"InsufficientKlines: ATR need ≥ {period + 1}, got {len(klines)}")

    highs, lows, closes = _highs_lows_closes(klines)
    trs = []
    for i in range(1, len(klines)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return float(atr)


# ===== 集成入口 =====

def calculate_indicators(
    klines_15m: List[Kline],
    klines_4h: List[Kline],
) -> Indicators:
    """从 15min + 4h K 线一次性算出所有 V5 需要的指标。"""
    macd_15m, sig_15m, hist_15m, hist_prev_15m = calculate_macd(klines_15m)
    _, _, hist_4h, _ = calculate_macd(klines_4h)
    return Indicators(
        rsi_15m=calculate_rsi(klines_15m),
        macd_15m=macd_15m,
        macd_signal_15m=sig_15m,
        macd_hist_15m=hist_15m,
        macd_hist_prev_15m=hist_prev_15m,
        rsi_4h=calculate_rsi(klines_4h),
        macd_hist_4h=hist_4h,
        atr_15m=calculate_atr(klines_15m),
    )
