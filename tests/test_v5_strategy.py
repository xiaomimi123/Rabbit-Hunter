"""V5Strategy AND 合谋决策器测试 — and_strict 模式回归保护。

边界:
- RSI > 70 且 MACD hist 由正变负 → SHORT
- RSI < 30 且 MACD hist 由负变正 → LONG
- 任一条件不满足 → 不开单 + 给清晰 block_reason

所有测试显式设 V5_STRATEGY_MODE=and_strict 以保留旧行为覆盖。
"""
import pytest
from v5_types import Decision, EnrichedItem, Indicators
from v5_strategy import decide


def _enriched(symbol="H/USDT", price=0.166, delta=0.035):
    return EnrichedItem(
        symbol=symbol, current_price=price, delta_15m_pct=delta,
        volume_24h_usdt=50_000_000, klines_15m=[], klines_4h=[],
    )


def _indicators(rsi_15m=50.0, hist=0.0, hist_prev=0.0,
                rsi_4h=50.0, hist_4h=0.0, atr_15m=0.001):
    return Indicators(
        rsi_15m=rsi_15m, macd_15m=0.0, macd_signal_15m=0.0,
        macd_hist_15m=hist, macd_hist_prev_15m=hist_prev,
        rsi_4h=rsi_4h, macd_hist_4h=hist_4h, atr_15m=atr_15m,
    )


def test_short_when_rsi_overbought_and_macd_bearish_cross(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=72.0, hist=-0.001, hist_prev=0.001))
    assert d.should_trade is True
    assert d.side == "SHORT"
    assert "RSI" in d.reasoning


def test_long_when_rsi_oversold_and_macd_bullish_cross(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=28.0, hist=0.001, hist_prev=-0.001))
    assert d.should_trade is True
    assert d.side == "LONG"


def test_reject_when_rsi_not_extreme(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=50.0, hist=-0.001, hist_prev=0.001))
    assert d.should_trade is False
    assert d.side is None
    assert d.block_reason == "NOT_RSI_AND_MACD"


def test_reject_when_rsi_overbought_but_macd_no_bearish_cross(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=72.0, hist=0.001, hist_prev=0.0005))
    assert d.should_trade is False
    assert d.block_reason == "NOT_RSI_AND_MACD"


def test_reject_when_rsi_oversold_but_macd_no_bullish_cross(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=28.0, hist=-0.001, hist_prev=-0.0005))
    assert d.should_trade is False


def test_rsi_exactly_70_does_not_trigger_short(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=70.0, hist=-0.001, hist_prev=0.001))
    assert d.should_trade is False


def test_rsi_exactly_30_does_not_trigger_long(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=30.0, hist=0.001, hist_prev=-0.001))
    assert d.should_trade is False


def test_custom_thresholds_from_env(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "65")
    monkeypatch.setenv("V5_RSI_OVERSOLD", "35")
    d = decide(_enriched(), _indicators(rsi_15m=66.0, hist=-0.001, hist_prev=0.001))
    assert d.should_trade is True
    assert d.side == "SHORT"


# ── Funding anti-pile filter (trend_aligned mode) ─────────────────────────


def _setup_trend_aligned_env(monkeypatch):
    """Force trend_aligned mode AND a known LONG/SHORT threshold so tests are
    isolated from DB / cache state (CI or prod DB may have non-default values)."""
    monkeypatch.setenv("V5_STRATEGY_MODE", "trend_aligned")
    monkeypatch.setenv("V5_TREND_RSI_LONG_THRESHOLD", "40.0")
    monkeypatch.setenv("V5_TREND_RSI_SHORT_THRESHOLD", "60.0")
    from scripts.v5_params import _CACHE
    _CACHE.clear()   # nuke any stale DB-derived values


def test_funding_anti_pile_blocks_long_when_longs_crowded(monkeypatch):
    """trend_aligned + LONG signal + funding_z >= threshold → blocked."""
    _setup_trend_aligned_env(monkeypatch)
    monkeypatch.setenv("V5_FUNDING_ANTI_PILE_THRESHOLD", "1.5")
    ind = _indicators(rsi_15m=35.0, hist_4h=0.001)
    d = decide(_enriched(), ind, funding_z=2.0)
    assert d.should_trade is False
    assert d.block_reason == "FUNDING_LONGS_CROWDED"


def test_funding_anti_pile_blocks_short_when_shorts_crowded(monkeypatch):
    _setup_trend_aligned_env(monkeypatch)
    monkeypatch.setenv("V5_FUNDING_ANTI_PILE_THRESHOLD", "1.5")
    ind = _indicators(rsi_15m=65.0, hist_4h=-0.001)
    d = decide(_enriched(), ind, funding_z=-2.0)
    assert d.should_trade is False
    assert d.block_reason == "FUNDING_SHORTS_CROWDED"


def test_funding_anti_pile_allows_when_threshold_zero(monkeypatch):
    _setup_trend_aligned_env(monkeypatch)
    monkeypatch.delenv("V5_FUNDING_ANTI_PILE_THRESHOLD", raising=False)
    ind = _indicators(rsi_15m=35.0, hist_4h=0.001)
    d = decide(_enriched(), ind, funding_z=5.0)
    assert d.should_trade is True
    assert d.side == "LONG"


def test_funding_anti_pile_allows_below_threshold(monkeypatch):
    _setup_trend_aligned_env(monkeypatch)
    monkeypatch.setenv("V5_FUNDING_ANTI_PILE_THRESHOLD", "1.5")
    ind = _indicators(rsi_15m=35.0, hist_4h=0.001)
    d = decide(_enriched(), ind, funding_z=0.5)
    assert d.should_trade is True
    assert d.side == "LONG"


def test_funding_anti_pile_allows_when_funding_z_none(monkeypatch):
    _setup_trend_aligned_env(monkeypatch)
    monkeypatch.setenv("V5_FUNDING_ANTI_PILE_THRESHOLD", "1.5")
    ind = _indicators(rsi_15m=35.0, hist_4h=0.001)
    d = decide(_enriched(), ind, funding_z=None)
    assert d.should_trade is True
    assert d.side == "LONG"
