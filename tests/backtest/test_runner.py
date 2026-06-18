"""Tests for BacktestRunner — timestamp iteration, slot limit, end-to-end smoke.

The runner stitches together kline_fetcher → indicator engine → strategy →
risk calculator → setup_type → position_sim. Tests patch the strategy decision
(and risk plan) where appropriate so we exercise the runner's plumbing —
slot enforcement, exit ticking, force-close at horizon — without needing to
hand-craft klines that trip the real RSI/MACD rule.
"""
from __future__ import annotations

from unittest.mock import patch

from scripts.backtest.runner import (
    BacktestConfig,
    BacktestRunner,
    INTERVAL_15M_MS,
    MAX_CONCURRENT,
)
from scripts.v5_types import Decision, Indicators, RiskPlan


# ── synthetic kline helpers ────────────────────────────────────────────────

def _flat_klines(start_ms: int, n: int, interval_ms: int = INTERVAL_15M_MS,
                 base: float = 100.0) -> list:
    """Synthesize n flat OHLCV bars starting at start_ms.

    All bars sit at `base` (tight range) so neither SL nor TP is hit by random
    noise — tests that need exits will craft their own kline series.
    """
    out = []
    for i in range(n):
        ts = start_ms + i * interval_ms
        out.append([ts, base, base + 0.01, base - 0.01, base, 10.0])
    return out


def _kl_window(end_ms: int, n: int, interval_ms: int = INTERVAL_15M_MS,
                base: float = 100.0) -> list:
    """n flat bars whose last bar has ts == end_ms - interval_ms (i.e. all < end_ms)."""
    first = end_ms - n * interval_ms
    return _flat_klines(first, n, interval_ms=interval_ms, base=base)


def _fake_indicators(rsi=50.0, atr=1.0, macd_hist=0.0) -> Indicators:
    return Indicators(
        rsi_15m=rsi,
        macd_15m=0.0,
        macd_signal_15m=0.0,
        macd_hist_15m=macd_hist,
        macd_hist_prev_15m=0.0,
        rsi_4h=50.0,
        macd_hist_4h=0.0,
        atr_15m=atr,
    )


def _fake_risk(entry: float, side: str = "LONG", sl_dist: float = 1.5,
               tp_dist: float = 2.5) -> RiskPlan:
    if side == "LONG":
        sl = entry - sl_dist
        tp = entry + tp_dist
    else:
        sl = entry + sl_dist
        tp = entry - tp_dist
    return RiskPlan(
        entry_price=entry, sl_price=sl, tp_price=tp,
        size_usdt=100.0, leverage=10, expected_rr=tp_dist / sl_dist,
    )


# ── timestamp iterator ─────────────────────────────────────────────────────

def test_timestamp_iterator_yields_15m_steps():
    """A 1-hour window aligned on the boundary → exactly 4 15-min steps."""
    cfg = BacktestConfig(
        start_iso="2026-05-19T00:00:00+00:00",
        end_iso="2026-05-19T01:00:00+00:00",
        symbols=["BTCUSDT"],
        cache_root="/tmp/bt_test",
        db_path=":memory:",
    )
    runner = BacktestRunner(cfg)
    steps = list(runner._iter_timestamps())
    assert len(steps) == 4
    # Strictly increasing, exactly 15m apart
    for a, b in zip(steps, steps[1:]):
        assert b - a == INTERVAL_15M_MS
    # All aligned to 15m
    for s in steps:
        assert s % INTERVAL_15M_MS == 0


def test_timestamp_iterator_aligns_unaligned_start():
    """Start at :07 → first yielded step is at :15, not :07."""
    cfg = BacktestConfig(
        start_iso="2026-05-19T00:07:00+00:00",
        end_iso="2026-05-19T01:00:00+00:00",
        symbols=["BTCUSDT"],
    )
    runner = BacktestRunner(cfg)
    steps = list(runner._iter_timestamps())
    # First step is at 00:15, then 00:30, 00:45 → 3 steps before 01:00
    assert len(steps) == 3
    first_iso = runner._ts_to_iso(steps[0])
    assert "00:15" in first_iso


def test_timestamp_iterator_handles_zulu_z_suffix():
    """ISO with trailing 'Z' (UTC) should parse identically to +00:00."""
    cfg = BacktestConfig(
        start_iso="2026-05-19T00:00:00Z",
        end_iso="2026-05-19T01:00:00Z",
        symbols=["BTCUSDT"],
    )
    runner = BacktestRunner(cfg)
    assert len(list(runner._iter_timestamps())) == 4


# ── helpers in isolation ───────────────────────────────────────────────────

def test_klines_up_to_filters_strictly_less_than():
    kl = [[1000, 1, 1, 1, 1, 1], [2000, 1, 1, 1, 1, 1], [3000, 1, 1, 1, 1, 1]]
    out = BacktestRunner._klines_up_to(kl, 2000)
    assert [k[0] for k in out] == [1000]   # 2000 itself excluded (strict <)


def test_klines_up_to_respects_max_bars_cap():
    kl = [[i, 1, 1, 1, 1, 1] for i in range(500)]
    out = BacktestRunner._klines_up_to(kl, 1000, max_bars=10)
    assert len(out) == 10
    assert out[-1][0] == 499        # most recent ones kept


# ── load() loads via fetcher ───────────────────────────────────────────────

def test_load_calls_fetcher_for_each_symbol_and_interval():
    cfg = BacktestConfig(
        start_iso="2026-05-19T00:00:00Z",
        end_iso="2026-05-19T01:00:00Z",
        symbols=["BTCUSDT", "ETHUSDT"],
    )
    runner = BacktestRunner(cfg)

    with patch("scripts.backtest.runner.fetch_klines_with_cache") as mfetch:
        mfetch.return_value = []
        runner.load()
    # 2 symbols × 2 intervals = 4 calls
    assert mfetch.call_count == 4


# ── end-to-end smoke ───────────────────────────────────────────────────────

def test_runner_smoke_with_mocked_strategy_opens_and_closes(monkeypatch):
    """End-to-end: mock strategy to always trigger LONG; verify .entries fills
    and positions get closed via simulate_exit on the next bar.
    """
    start_ms = 1_716_076_800_000        # arbitrary 15m-aligned ms
    # 60 15m bars BEFORE start_ms (all ts < start_ms).
    base_kl15 = _kl_window(start_ms, 60, base=100.0)
    # Inject a spike bar AT start_ms + 15m so simulate_exit hits TP=102.5.
    spike_bar = [start_ms + INTERVAL_15M_MS, 100.0, 110.0, 99.5, 105.0, 50.0]
    kl15 = base_kl15 + [spike_bar]
    # 4h klines: need ≥ 30 with ts < start_ms.
    kl4h = _kl_window(start_ms, 60, interval_ms=4 * 3600 * 1000, base=100.0)

    cfg = BacktestConfig(
        start_iso=BacktestRunner._ts_to_iso(start_ms),
        # Single step: 00:00 only. The TP-touching bar at start+15m gets
        # discovered via the next exit-tick (no second new-entry).
        end_iso=BacktestRunner._ts_to_iso(start_ms + INTERVAL_15M_MS),
        symbols=["BTCUSDT"],
        db_path=":memory:",
    )

    runner = BacktestRunner(cfg)
    runner._kl15["BTCUSDT"] = kl15
    runner._kl4h["BTCUSDT"] = kl4h

    long_decision = Decision(should_trade=True, side="LONG",
                              reasoning="forced LONG (test)", block_reason=None)

    def fake_indicators(_kl15, _kl4h):
        return _fake_indicators(rsi=35.0, atr=1.0)

    def fake_decide(_enriched, _indicators, funding_z=None):
        return long_decision

    def fake_plan(*, side, entry, atr, balance, risk_pct, leverage):
        return _fake_risk(entry=entry, side=side)

    monkeypatch.setattr(
        "scripts.backtest.runner.v5_indicator_engine.calculate_indicators",
        fake_indicators,
    )
    monkeypatch.setattr(
        "scripts.backtest.runner.v5_strategy.decide", fake_decide
    )
    monkeypatch.setattr(
        "scripts.backtest.runner.v5_risk_calculator.plan", fake_plan
    )
    monkeypatch.setattr(
        "scripts.backtest.runner.compute_zscore_as_of",
        lambda *a, **kw: None,
    )

    runner.run()

    # Should have opened exactly one entry at the (single) step.
    assert len(runner.entries) == 1, runner.entries
    e = runner.entries[0]
    assert e.symbol == "BTCUSDT"
    assert e.side == "LONG"
    # Force-closed at end of window — the spike bar at start+15m is the last
    # available bar, so exit_price = its close (105.0). R = (105 - 100) / 1.5.
    assert e.exit_reason == "HORIZON_TIMEOUT"
    assert e.exit_price == 105.0
    assert e.realized_r is not None
    assert e.realized_r > 0       # winner
    assert runner.total_signals == 1
    assert runner.total_passed == 1
    assert runner.max_concurrent == 1
    # After force-close, no positions remain open.
    assert runner.open == []


def test_runner_respects_slot_limit_with_5_qualifying_symbols(monkeypatch):
    """5 symbols all return should_trade=True at the same t → only 3 entered."""
    start_ms = 1_716_076_800_000
    kl15 = _kl_window(start_ms, 60, base=100.0)
    kl4h = _kl_window(start_ms, 60, interval_ms=4 * 3600 * 1000, base=100.0)

    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    cfg = BacktestConfig(
        start_iso=BacktestRunner._ts_to_iso(start_ms),
        end_iso=BacktestRunner._ts_to_iso(start_ms + INTERVAL_15M_MS),
        symbols=symbols,
        db_path=":memory:",
    )
    runner = BacktestRunner(cfg)
    for s in symbols:
        runner._kl15[s] = list(kl15)
        runner._kl4h[s] = list(kl4h)

    monkeypatch.setattr(
        "scripts.backtest.runner.v5_indicator_engine.calculate_indicators",
        lambda a, b: _fake_indicators(rsi=35.0, atr=1.0),
    )
    monkeypatch.setattr(
        "scripts.backtest.runner.v5_strategy.decide",
        lambda e, i, funding_z=None: Decision(should_trade=True, side="LONG",
                               reasoning="forced", block_reason=None),
    )
    monkeypatch.setattr(
        "scripts.backtest.runner.v5_risk_calculator.plan",
        lambda **kw: _fake_risk(entry=kw["entry"], side=kw["side"]),
    )
    monkeypatch.setattr(
        "scripts.backtest.runner.compute_zscore_as_of", lambda *a, **kw: None
    )

    runner.run()

    # Exactly MAX_CONCURRENT entries opened, even though 5 qualified.
    assert len(runner.entries) == MAX_CONCURRENT
    # Deterministic alphabetical: AAA, BBB, CCC win the slots.
    assert sorted(e.symbol for e in runner.entries) == ["AAA", "BBB", "CCC"]
    # The decision pass count records ALL 5 (slot enforcement is post-decision).
    assert runner.total_passed == 5
    assert runner.total_signals == 5
    assert runner.max_concurrent == MAX_CONCURRENT


def test_runner_skips_symbols_with_insufficient_klines(monkeypatch):
    """A symbol with < 30 bars must be skipped silently (no exception, no entry)."""
    start_ms = 1_716_076_800_000
    # Only 10 bars — below MIN_BARS_FOR_INDICATORS (30).
    short_kl = _flat_klines(start_ms - 10 * INTERVAL_15M_MS, 10, base=100.0)
    cfg = BacktestConfig(
        start_iso=BacktestRunner._ts_to_iso(start_ms),
        end_iso=BacktestRunner._ts_to_iso(start_ms + INTERVAL_15M_MS),
        symbols=["BTCUSDT"],
        db_path=":memory:",
    )
    runner = BacktestRunner(cfg)
    runner._kl15["BTCUSDT"] = short_kl
    runner._kl4h["BTCUSDT"] = short_kl

    # Strategy should never be called.
    decide_called = []
    monkeypatch.setattr(
        "scripts.backtest.runner.v5_strategy.decide",
        lambda *a, **kw: decide_called.append(1) or Decision(
            should_trade=False, side=None, reasoning="x", block_reason=None,
        ),
    )
    monkeypatch.setattr(
        "scripts.backtest.runner.compute_zscore_as_of", lambda *a, **kw: None
    )

    runner.run()
    assert runner.entries == []
    assert decide_called == []      # confirms we short-circuit before strategy


def test_runner_force_closes_still_open_at_end(monkeypatch):
    """If a position never hits SL/TP, end-of-window force-closes with HORIZON_TIMEOUT."""
    start_ms = 1_716_076_800_000
    # Flat klines = no SL/TP hit possible. Need bars BEFORE start_ms for entry
    # and AFTER start_ms for the force-close to find a "last bar".
    kl15_pre = _kl_window(start_ms, 60, base=100.0)
    kl15_post = _flat_klines(start_ms, 5, base=100.0)
    kl15 = kl15_pre + kl15_post
    kl4h = _kl_window(start_ms, 60, interval_ms=4 * 3600 * 1000, base=100.0)
    cfg = BacktestConfig(
        start_iso=BacktestRunner._ts_to_iso(start_ms),
        end_iso=BacktestRunner._ts_to_iso(start_ms + INTERVAL_15M_MS),  # 1 step
        symbols=["BTCUSDT"],
        db_path=":memory:",
    )
    runner = BacktestRunner(cfg)
    runner._kl15["BTCUSDT"] = kl15
    runner._kl4h["BTCUSDT"] = kl4h

    monkeypatch.setattr(
        "scripts.backtest.runner.v5_indicator_engine.calculate_indicators",
        lambda a, b: _fake_indicators(rsi=35.0, atr=1.0),
    )
    monkeypatch.setattr(
        "scripts.backtest.runner.v5_strategy.decide",
        lambda e, i, funding_z=None: Decision(should_trade=True, side="LONG",
                               reasoning="forced", block_reason=None),
    )
    monkeypatch.setattr(
        "scripts.backtest.runner.v5_risk_calculator.plan",
        lambda **kw: _fake_risk(entry=kw["entry"], side=kw["side"]),
    )
    monkeypatch.setattr(
        "scripts.backtest.runner.compute_zscore_as_of", lambda *a, **kw: None
    )

    runner.run()

    assert len(runner.entries) == 1
    e = runner.entries[0]
    assert e.exit_reason == "HORIZON_TIMEOUT"
    assert e.realized_r is not None
    assert runner.open == []


# ── setup_type derivation flows through ────────────────────────────────────

def test_runner_funding_extreme_flows_into_setup_type(monkeypatch):
    """When |funding_z| ≥ 2.0, setup_type must reflect funding_extreme bucket."""
    start_ms = 1_716_076_800_000
    kl15_pre = _kl_window(start_ms, 60, base=100.0)
    kl15_post = _flat_klines(start_ms, 5, base=100.0)
    kl15 = kl15_pre + kl15_post
    kl4h = _kl_window(start_ms, 60, interval_ms=4 * 3600 * 1000, base=100.0)
    cfg = BacktestConfig(
        start_iso=BacktestRunner._ts_to_iso(start_ms),
        end_iso=BacktestRunner._ts_to_iso(start_ms + INTERVAL_15M_MS),
        symbols=["BTCUSDT"],
        db_path=":memory:",
    )
    runner = BacktestRunner(cfg)
    runner._kl15["BTCUSDT"] = kl15
    runner._kl4h["BTCUSDT"] = kl4h

    monkeypatch.setattr(
        "scripts.backtest.runner.v5_indicator_engine.calculate_indicators",
        lambda a, b: _fake_indicators(rsi=75.0, atr=1.0),
    )
    monkeypatch.setattr(
        "scripts.backtest.runner.v5_strategy.decide",
        lambda e, i, funding_z=None: Decision(should_trade=True, side="SHORT",
                               reasoning="x", block_reason=None),
    )
    monkeypatch.setattr(
        "scripts.backtest.runner.v5_risk_calculator.plan",
        lambda **kw: _fake_risk(entry=kw["entry"], side=kw["side"]),
    )
    monkeypatch.setattr(
        "scripts.backtest.runner.compute_zscore_as_of",
        lambda *a, **kw: {"zscore_30d": 2.5,
                           "current_funding_rate": 0.0,
                           "mean_30d": 0.0, "std_30d": 0.0,
                           "sample_size_30d": 30,
                           "is_extreme": True,
                           "extreme_direction": "long_crowded"},
    )

    runner.run()
    assert len(runner.entries) == 1
    e = runner.entries[0]
    assert e.setup_type.startswith("funding_extreme_short_"), e.setup_type
    assert e.funding_z_at_entry == 2.5
