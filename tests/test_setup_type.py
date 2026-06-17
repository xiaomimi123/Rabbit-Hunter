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


# === V6 funding_extreme tests ===

def test_funding_extreme_short_rsi_overbought():
    """funding |z| >= 2.0 + 正向(long_crowded) + RSI 超买 → funding_extreme_short_rsi_overbought."""
    from scripts.ai.setup_type import derive_setup_type
    out = derive_setup_type({
        "side": "SHORT", "strategy_id": "v5_rsi_macd",
        "rsi_15m": 72.0, "macd_hist": -0.0012, "macd_hist_prev": 0.0008,
        "funding_z_score": 2.5,
    })
    assert out == "funding_extreme_short_rsi_overbought"


def test_funding_extreme_long_rsi_oversold():
    from scripts.ai.setup_type import derive_setup_type
    out = derive_setup_type({
        "side": "LONG", "strategy_id": "v5_rsi_macd",
        "rsi_15m": 25.0, "macd_hist": 0.0008, "macd_hist_prev": -0.0004,
        "funding_z_score": -2.8,
    })
    assert out == "funding_extreme_long_rsi_oversold"


def test_funding_z_below_2_falls_back_to_rsi_macd():
    """|z| < 2.0 → 退回 RSI×MACD 派生,不进 funding_extreme."""
    from scripts.ai.setup_type import derive_setup_type
    out = derive_setup_type({
        "side": "SHORT", "strategy_id": "v5_rsi_macd",
        "rsi_15m": 72.0, "macd_hist": -0.0012, "macd_hist_prev": 0.0008,
        "funding_z_score": 1.5,                  # 不够极端
    })
    assert out == "rsi_overbought_macd_bearish_short"


def test_funding_extreme_handles_neutral_rsi():
    """funding 极端但 RSI 中性 → funding_extreme_<dir>_rsi_neutral."""
    from scripts.ai.setup_type import derive_setup_type
    out = derive_setup_type({
        "side": "SHORT", "strategy_id": "v5_rsi_macd",
        "rsi_15m": 55.0, "macd_hist": -0.0001, "macd_hist_prev": -0.00005,
        "funding_z_score": 2.3,
    })
    assert out == "funding_extreme_short_rsi_neutral"


def test_funding_extreme_overrides_manual_check():
    """v5_manual 仍然短路返回 manual_*,不受 funding 影响."""
    from scripts.ai.setup_type import derive_setup_type
    out = derive_setup_type({
        "side": "SHORT", "strategy_id": "v5_manual",
        "rsi_15m": 72.0, "macd_hist": -0.0012, "macd_hist_prev": 0.0008,
        "funding_z_score": 3.0,
    })
    assert out == "manual_short"
