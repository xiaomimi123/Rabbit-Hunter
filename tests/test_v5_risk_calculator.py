"""V5 RiskCalculator 测试。

约定:
- SL 默认 1.5 × ATR(短线收紧)
- TP 默认 2.5 × ATR
- size_usdt 让"价格走到 SL"的损失正好 = balance × risk_pct
"""
import pytest
from v5_types import RiskPlan
from v5_risk_calculator import plan


def test_long_sl_below_entry_tp_above():
    p = plan(side="LONG", entry=100.0, atr=2.0, balance=1000.0, risk_pct=0.015, leverage=10)
    assert p.sl_price < p.entry_price < p.tp_price


def test_short_sl_above_entry_tp_below():
    p = plan(side="SHORT", entry=100.0, atr=2.0, balance=1000.0, risk_pct=0.015, leverage=10)
    assert p.tp_price < p.entry_price < p.sl_price


def test_long_size_respects_risk_budget():
    balance, risk_pct, atr, entry = 1000.0, 0.015, 2.0, 100.0
    p = plan(side="LONG", entry=entry, atr=atr, balance=balance,
             risk_pct=risk_pct, leverage=10)
    sl_distance_pct = (entry - p.sl_price) / entry
    notional = p.size_usdt * p.leverage
    max_loss = notional * sl_distance_pct
    expected_max_loss = balance * risk_pct
    assert abs(max_loss - expected_max_loss) < 0.05


def test_short_size_respects_risk_budget():
    balance, risk_pct, atr, entry = 1000.0, 0.015, 2.0, 100.0
    p = plan(side="SHORT", entry=entry, atr=atr, balance=balance,
             risk_pct=risk_pct, leverage=10)
    sl_distance_pct = (p.sl_price - entry) / entry
    notional = p.size_usdt * p.leverage
    max_loss = notional * sl_distance_pct
    assert abs(max_loss - balance * risk_pct) < 0.05


def test_expected_rr_is_tp_over_sl_distance():
    p = plan(side="LONG", entry=100.0, atr=2.0, balance=1000.0, risk_pct=0.015, leverage=10)
    assert 1.6 < p.expected_rr < 1.7


def test_zero_atr_raises():
    with pytest.raises(ValueError, match="atr"):
        plan(side="LONG", entry=100.0, atr=0.0, balance=1000.0, risk_pct=0.015, leverage=10)


def test_size_does_not_exceed_balance_with_leverage():
    p = plan(side="LONG", entry=100.0, atr=2.0, balance=1000.0, risk_pct=0.015, leverage=10)
    assert p.size_usdt >= 1.0
    assert p.size_usdt <= p.entry_price


def test_custom_sl_tp_multipliers_from_env(monkeypatch):
    monkeypatch.setenv("V5_SL_ATR_MULT", "2.0")
    monkeypatch.setenv("V5_TP_ATR_MULT", "4.0")
    p = plan(side="LONG", entry=100.0, atr=2.0, balance=1000.0, risk_pct=0.015, leverage=10)
    assert abs(p.sl_price - 96.0) < 0.01
    assert abs(p.tp_price - 108.0) < 0.01
