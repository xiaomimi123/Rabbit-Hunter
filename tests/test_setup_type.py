"""setup_type 派生 — 确定性,不依赖 AI。"""
from scripts.ai.setup_type import derive_setup_type


def _entry(**over):
    base = dict(
        side="SHORT", strategy_id="v5_rsi_macd",
        rsi_15m=72.0, macd_hist=-0.0012, macd_hist_prev=0.0008,
        funding_z_score=None,
    )
    base.update(over)
    return base


def test_manual_short_returns_manual_short():
    assert derive_setup_type(_entry(strategy_id="v5_manual", side="SHORT")) == "manual_short"


def test_rsi_overbought_macd_bearish_short():
    assert derive_setup_type(_entry()) == "rsi_overbought_macd_bearish_short"


def test_rsi_oversold_macd_bullish_long():
    assert derive_setup_type(_entry(
        side="LONG", rsi_15m=28.0,
        macd_hist=0.0005, macd_hist_prev=-0.0004,
    )) == "rsi_oversold_macd_bullish_long"


def test_rsi_neutral_macd_extending_short():
    assert derive_setup_type(_entry(rsi_15m=55.0,
        macd_hist=-0.001, macd_hist_prev=-0.0008)) == "rsi_neutral_macd_extending_short"


def test_funding_extreme_short_overrides_when_zscore_high():
    assert derive_setup_type(_entry(funding_z_score=2.3)) == "funding_extreme_short_rsi_overbought"


def test_funding_extreme_long_when_negative():
    assert derive_setup_type(_entry(
        side="LONG", rsi_15m=25.0,
        macd_hist=0.0005, macd_hist_prev=-0.0004,
        funding_z_score=-2.5,
    )) == "funding_extreme_long_rsi_oversold"
