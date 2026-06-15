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
