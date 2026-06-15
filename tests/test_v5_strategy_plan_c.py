"""V5.1 Plan C — trend_aligned mode."""
import pytest
from v5_types import EnrichedItem, Indicators
from v5_strategy import decide


def _enriched(symbol="HUSDT", current_price=0.166, klines_15m=None):
    """klines_15m: list of (ts, o, h, l, c, v) tuples or None for default."""
    if klines_15m is None:
        # 10 normal candles around 0.166 ± 0.001
        klines_15m = [(1717200000000 + i * 900_000, 0.166, 0.167, 0.165, 0.166, 1000) for i in range(10)]
    return EnrichedItem(
        symbol=symbol, current_price=current_price,
        delta_15m_pct=0.005, volume_24h_usdt=5e7,
        klines_15m=klines_15m, klines_4h=[],
    )


def _indicators(rsi_15m=65.0, rsi_4h=50.0, macd_hist_15m=-0.001,
                macd_hist_prev_15m=0.0, macd_hist_4h=-0.005, atr_15m=0.0015):
    return Indicators(
        rsi_15m=rsi_15m, macd_15m=0, macd_signal_15m=0,
        macd_hist_15m=macd_hist_15m, macd_hist_prev_15m=macd_hist_prev_15m,
        rsi_4h=rsi_4h, macd_hist_4h=macd_hist_4h, atr_15m=atr_15m,
    )


def test_and_strict_mode_preserves_old_behavior(monkeypatch):
    """显式设回老模式 → 旧 AND 行为还在(回归保护)。"""
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    # Old logic: rsi > 70 AND macd_hist_prev > 0 AND macd_hist < 0
    d = decide(_enriched(), _indicators(rsi_15m=72.0, macd_hist_prev_15m=0.0005,
                                          macd_hist_15m=-0.0006))
    assert d.should_trade is True
    assert d.side == "SHORT"


def test_and_strict_does_not_fire_when_no_macd_cross(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=72.0, macd_hist_prev_15m=-0.0005,
                                          macd_hist_15m=-0.0006))    # extending, no flip
    assert d.should_trade is False
    assert d.block_reason == "NOT_RSI_AND_MACD"


def test_trend_aligned_short_fires_when_4h_down_and_rsi_high(monkeypatch):
    """default mode = trend_aligned。4h MACD < 0 + 15m RSI 65 + not at top → SHORT。"""
    monkeypatch.setenv("V5_STRATEGY_MODE", "trend_aligned")
    # 10 candles with high = 0.170, current_price = 0.166 (>0.5% below 0.170)
    klines = [(1717200000000 + i * 900_000, 0.168, 0.170, 0.165, 0.166, 1000) for i in range(10)]
    d = decide(
        _enriched(current_price=0.166, klines_15m=klines),
        _indicators(rsi_15m=65.0, macd_hist_4h=-0.005),
    )
    assert d.should_trade is True
    assert d.side == "SHORT"
    assert "trend_aligned" in d.reasoning.lower() or "4h" in d.reasoning


def test_trend_aligned_short_blocked_when_at_recent_high(monkeypatch):
    """RSI 65 + 4h 下行 + 当前价 ≥ 0.5% of recent high → 拒(anti-chase)。"""
    monkeypatch.setenv("V5_STRATEGY_MODE", "trend_aligned")
    # 10 candles with high = 0.170, current_price = 0.1695 (within 0.5%)
    klines = [(1717200000000 + i * 900_000, 0.168, 0.170, 0.165, 0.169, 1000) for i in range(10)]
    d = decide(
        _enriched(current_price=0.1695, klines_15m=klines),
        _indicators(rsi_15m=65.0, macd_hist_4h=-0.005),
    )
    assert d.should_trade is False
    assert "ANTI_CHASE" in (d.block_reason or "") or "anti_chase" in (d.reasoning or "").lower()


def test_trend_aligned_short_blocked_when_4h_up(monkeypatch):
    """RSI 高但 4h MACD > 0(上行)→ 不允许 SHORT(逆 4h 趋势)。"""
    monkeypatch.setenv("V5_STRATEGY_MODE", "trend_aligned")
    klines = [(1717200000000 + i * 900_000, 0.168, 0.170, 0.165, 0.166, 1000) for i in range(10)]
    d = decide(
        _enriched(current_price=0.166, klines_15m=klines),
        _indicators(rsi_15m=65.0, macd_hist_4h=+0.005),   # 4h 上行
    )
    assert d.should_trade is False


def test_trend_aligned_long_fires_when_4h_up_and_rsi_low(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "trend_aligned")
    klines = [(1717200000000 + i * 900_000, 0.167, 0.168, 0.160, 0.166, 1000) for i in range(10)]
    d = decide(
        _enriched(current_price=0.166, klines_15m=klines),
        _indicators(rsi_15m=35.0, macd_hist_4h=+0.005),
    )
    assert d.should_trade is True
    assert d.side == "LONG"


def test_trend_aligned_long_blocked_when_at_recent_low(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "trend_aligned")
    # low = 0.160, current 0.1605 = within 0.5% of low
    klines = [(1717200000000 + i * 900_000, 0.167, 0.168, 0.160, 0.165, 1000) for i in range(10)]
    d = decide(
        _enriched(current_price=0.1605, klines_15m=klines),
        _indicators(rsi_15m=35.0, macd_hist_4h=+0.005),
    )
    assert d.should_trade is False
