"""Tests for backtest reporter/aggregator."""
from scripts.backtest.schemas import BacktestEntry
from scripts.backtest.reporter import build_summary, format_report


def _entry(realized_r=None, side="LONG", setup="A", symbol="BTC"):
    return BacktestEntry(
        symbol=symbol, side=side, setup_type=setup,
        entry_time="2026-05-19T10:00:00+00:00", entry_price=100.0,
        sl_price=95.0, tp_price=110.0,
        exit_time=("2026-05-19T11:00:00+00:00" if realized_r is not None else None),
        exit_price=(110.0 if realized_r and realized_r > 0 else 95.0 if realized_r else None),
        exit_reason=("TP_HIT" if realized_r and realized_r > 0 else
                     "SL_HIT" if realized_r else None),
        realized_r=realized_r,
        holding_minutes=(60 if realized_r is not None else None),
        funding_z_at_entry=None,
        rsi_15m_at_entry=70.0,
        macd_hist_15m_at_entry=0.0,
    )


def test_build_summary_aggregates_by_setup_side_symbol():
    es = [
        _entry(2.0, "LONG", "A", "BTC"),
        _entry(-1.0, "LONG", "A", "ETH"),
        _entry(2.0, "SHORT", "B", "SOL"),
    ]
    summary = build_summary(es, total_signals=10, total_passed=3,
                             period_start="t0", period_end="t9",
                             max_concurrent_reached=2)
    assert summary.by_setup_type["A"].n == 2
    assert summary.by_setup_type["B"].n == 1
    assert summary.by_side["LONG"].n == 2
    assert summary.by_side["SHORT"].n == 1
    assert summary.by_symbol["BTC"].total_r == 2.0
    assert summary.by_symbol["ETH"].total_r == -1.0
    assert summary.overall.n == 3


def test_build_summary_profit_factor_calculation():
    es = [_entry(2.0), _entry(2.0), _entry(-1.0)]
    summary = build_summary(es, 3, 3, "t0", "t1", 1)
    # PF = 4 / 1 = 4.0
    assert summary.profit_factor == 4.0


def test_build_summary_profit_factor_none_when_no_losses():
    es = [_entry(2.0), _entry(1.0)]
    summary = build_summary(es, 2, 2, "t0", "t1", 1)
    assert summary.profit_factor is None


def test_build_summary_max_drawdown():
    """Cumulative R: 2, 1, 4, 2, 0 → drawdown from peak 4 to trough 0 = -4."""
    es = [_entry(2.0), _entry(-1.0), _entry(3.0), _entry(-2.0), _entry(-2.0)]
    summary = build_summary(es, 5, 5, "t0", "t1", 1)
    assert summary.max_drawdown_r == -4.0


def test_build_summary_max_drawdown_zero_if_only_wins():
    es = [_entry(1.0), _entry(2.0), _entry(1.0)]
    summary = build_summary(es, 3, 3, "t0", "t1", 1)
    assert summary.max_drawdown_r == 0.0


def test_format_report_includes_setup_table():
    es = [_entry(2.0, "LONG", "rsi_oversold_macd_bullish_long", "BTC")]
    summary = build_summary(es, 1, 1, "t0", "t1", 1)
    out = format_report(summary)
    assert "rsi_oversold_macd_bullish_long" in out
    assert "Profit Factor" in out or "no losses" in out


def test_format_report_marks_funding_extreme_setups():
    es = [_entry(2.0, "LONG", "funding_extreme_long_rsi_oversold", "BTC")]
    summary = build_summary(es, 1, 1, "t0", "t1", 1)
    out = format_report(summary)
    assert "★" in out


def test_format_report_handles_empty_summary():
    summary = build_summary([], total_signals=100, total_passed=0,
                             period_start="t0", period_end="t1",
                             max_concurrent_reached=0)
    out = format_report(summary)
    assert "no closed trades" in out
    assert "Profit Factor" in out or "no losses" in out
