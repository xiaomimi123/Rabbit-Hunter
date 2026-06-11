"""V5 数据类 sanity test。"""
import pytest
from v5_types import EnrichedItem, Indicators, Decision, RiskPlan, AIResult


def test_indicators_frozen():
    ind = Indicators(
        rsi_15m=72.0, macd_15m=0.001, macd_signal_15m=0.0005,
        macd_hist_15m=0.0005, macd_hist_prev_15m=-0.0002,
        rsi_4h=65.0, macd_hist_4h=0.003, atr_15m=0.0015,
    )
    with pytest.raises(Exception):
        ind.rsi_15m = 99.0  # frozen,改不动


def test_decision_optional_side():
    d = Decision(should_trade=False, side=None, reasoning="rsi 未达极值", block_reason="NOT_RSI_AND_MACD")
    assert d.side is None
    assert d.should_trade is False


def test_risk_plan_rr_positive():
    p = RiskPlan(entry_price=100.0, sl_price=98.0, tp_price=104.0, size_usdt=15.0, leverage=10, expected_rr=2.0)
    assert p.expected_rr > 0
