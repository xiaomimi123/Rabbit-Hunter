"""V5 IndicatorEngine 单元测试。

参考值用业内通用公式手算 + Wilder's smoothing。
"""
import pytest
from tests.conftest import _build_klines
from v5_indicator_engine import (
    calculate_rsi,
    calculate_macd,
    calculate_atr,
    calculate_indicators,
)


# ---------- RSI ----------

def test_rsi_all_up_returns_100():
    """连续上涨 30 根 → RSI 接近 100。"""
    klines = _build_klines([100 + i for i in range(30)])
    rsi = calculate_rsi(klines, period=14)
    assert 95 <= rsi <= 100


def test_rsi_all_down_returns_0():
    klines = _build_klines([100 - i for i in range(30)])
    rsi = calculate_rsi(klines, period=14)
    assert 0 <= rsi <= 5


def test_rsi_oscillating_around_50():
    """交替涨跌 → RSI 约 50。"""
    prices = [100 + (1 if i % 2 == 0 else -1) for i in range(30)]
    klines = _build_klines(prices)
    rsi = calculate_rsi(klines, period=14)
    assert 40 <= rsi <= 60


def test_rsi_insufficient_klines_raises():
    klines = _build_klines([100, 101, 102])  # 只有 3 根,< period+1
    with pytest.raises(ValueError, match="InsufficientKlines"):
        calculate_rsi(klines, period=14)


# ---------- MACD ----------

def test_macd_uptrend_positive_hist():
    """上涨趋势 → macd > signal,hist 为正。"""
    klines = _build_klines([100 + i * 0.5 for i in range(50)])
    macd, signal, hist, hist_prev = calculate_macd(klines)
    assert macd > signal, f"上涨 MACD 应 > signal,实际 {macd=} {signal=}"
    assert hist > 0


def test_macd_downtrend_negative_hist():
    klines = _build_klines([100 - i * 0.5 for i in range(50)])
    macd, signal, hist, hist_prev = calculate_macd(klines)
    assert macd < signal
    assert hist < 0


def test_macd_returns_four_values():
    klines = _build_klines([100 + i * 0.3 for i in range(50)])
    result = calculate_macd(klines)
    assert len(result) == 4
    for v in result:
        assert isinstance(v, float)


# ---------- ATR ----------

def test_atr_positive_for_volatile_series():
    klines = _build_klines([100 + ((-1) ** i) * 2 for i in range(30)])
    atr = calculate_atr(klines, period=14)
    assert atr > 0


def test_atr_proportional_to_volatility():
    """波动大的 ATR > 波动小的 ATR。"""
    low_vol = _build_klines([100 + 0.1 * i for i in range(30)])
    high_vol = _build_klines([100 + ((-1) ** i) * 5 for i in range(30)])
    assert calculate_atr(high_vol) > calculate_atr(low_vol)


# ---------- calculate_indicators 集成 ----------

def test_calculate_indicators_returns_full_struct():
    from v5_types import Indicators
    klines_15m = _build_klines([100 + i * 0.3 for i in range(50)])
    klines_4h  = _build_klines([100 + i * 0.5 for i in range(40)])
    ind = calculate_indicators(klines_15m, klines_4h)
    assert isinstance(ind, Indicators)
    assert 0 <= ind.rsi_15m <= 100
    assert 0 <= ind.rsi_4h <= 100
    assert ind.atr_15m > 0


def test_calculate_indicators_propagates_insufficient():
    """K 线不足时,集成函数也要透出 ValueError。"""
    klines_15m = _build_klines([100, 101])  # 只有 2 根
    klines_4h  = _build_klines([100 + i for i in range(40)])
    with pytest.raises(ValueError):
        calculate_indicators(klines_15m, klines_4h)
