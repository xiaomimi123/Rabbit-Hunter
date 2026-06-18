"""Tests for backtest schemas."""
import pytest
from scripts.backtest.schemas import BacktestEntry, SetupStats, BacktestSummary


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


def test_entry_to_dict_preserves_all_fields():
    e = _entry(realized_r=2.0)
    d = e.to_dict()
    assert d["symbol"] == "BTC"
    assert d["realized_r"] == 2.0
    assert d["entry_time"] == "2026-05-19T10:00:00+00:00"


def test_setup_stats_empty_on_no_entries():
    s = SetupStats.from_entries([])
    assert s.n == 0
    assert s.win_rate == 0.0


def test_setup_stats_empty_when_only_unclosed():
    s = SetupStats.from_entries([_entry(realized_r=None)])
    assert s.n == 0


def test_setup_stats_aggregates_basic():
    es = [_entry(2.0), _entry(-1.0), _entry(1.0)]
    s = SetupStats.from_entries(es)
    assert s.n == 3
    assert s.wins == 2
    assert s.losses == 1
    assert abs(s.win_rate - 2 / 3) < 1e-6
    assert s.total_r == 2.0
    assert abs(s.avg_r - 2.0 / 3) < 1e-6
    assert s.median_r == 1.0
    assert s.best_r == 2.0
    assert s.worst_r == -1.0


def test_setup_stats_median_even_n():
    es = [_entry(1.0), _entry(2.0), _entry(3.0), _entry(4.0)]
    s = SetupStats.from_entries(es)
    assert s.median_r == 2.5


def test_summary_to_dict_walks_nested_stats():
    es = [_entry(2.0, "LONG", "X", "BTC"), _entry(-1.0, "SHORT", "Y", "ETH")]
    summary = BacktestSummary(
        period_start="s", period_end="e",
        total_signals=10, total_passed=2, total_entries=2, total_closed=2,
        by_setup_type={"X": SetupStats.from_entries([es[0]]),
                       "Y": SetupStats.from_entries([es[1]])},
        by_side={"LONG": SetupStats.from_entries([es[0]]),
                 "SHORT": SetupStats.from_entries([es[1]])},
        by_symbol={"BTC": SetupStats.from_entries([es[0]]),
                   "ETH": SetupStats.from_entries([es[1]])},
        overall=SetupStats.from_entries(es),
        max_concurrent_reached=2, profit_factor=2.0, max_drawdown_r=-1.0,
    )
    d = summary.to_dict()
    assert d["by_setup_type"]["X"]["total_r"] == 2.0
    assert d["overall"]["n"] == 2
    assert d["profit_factor"] == 2.0
