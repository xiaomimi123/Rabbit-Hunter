"""Tests for OHLC-touch position simulator."""
from scripts.backtest.position_sim import simulate_exit


# kline: [ts_ms, open, high, low, close, volume]

def test_long_tp_hit_first():
    klines_after = [[2000, 100, 112, 99, 105, 50]]
    exit_ts, exit_p, reason, r = simulate_exit(
        entry_ts=1000, entry_price=100, sl_price=95, tp_price=110,
        side="LONG", klines_after=klines_after, max_hold_minutes=480, interval_min=15,
    )
    assert exit_ts == 2000
    assert exit_p == 110
    assert reason == "TP_HIT"
    assert r == 2.0


def test_long_sl_hit_first():
    klines_after = [[2000, 100, 105, 94, 102, 50]]
    _, exit_p, reason, r = simulate_exit(
        1000, 100, 95, 110, "LONG", klines_after, 480, 15)
    assert exit_p == 95
    assert reason == "SL_HIT"
    assert r == -1.0


def test_long_same_candle_both_hits_assume_sl_first():
    klines_after = [[2000, 100, 112, 94, 105, 50]]   # touches both
    _, exit_p, reason, r = simulate_exit(
        1000, 100, 95, 110, "LONG", klines_after, 480, 15)
    assert reason == "SL_HIT"            # conservative: SL first
    assert r == -1.0


def test_short_tp_hit():
    klines_after = [[2000, 100, 102, 88, 95, 50]]   # low=88 → TP
    _, exit_p, reason, r = simulate_exit(
        1000, 100, 105, 90, "SHORT", klines_after, 480, 15)
    assert exit_p == 90
    assert reason == "TP_HIT"
    assert r == 2.0


def test_short_sl_hit():
    klines_after = [[2000, 100, 108, 99, 102, 50]]   # high=108 → SL
    _, exit_p, reason, r = simulate_exit(
        1000, 100, 105, 90, "SHORT", klines_after, 480, 15)
    assert exit_p == 105
    assert reason == "SL_HIT"
    assert r == -1.0


def test_horizon_timeout_long():
    # 40 calm candles, neither SL nor TP touched. Max hold 480 / 15 = 32 bars.
    klines_after = [
        [1000 + (i + 1) * 900_000, 100, 100.5, 99.5, 100.0, 10]
        for i in range(40)
    ]
    _, exit_p, reason, r = simulate_exit(
        1000, 100, 95, 110, "LONG", klines_after, 480, 15)
    assert reason == "HORIZON_TIMEOUT"
    assert exit_p == 100.0
    # close == entry → R = 0
    assert r == 0.0


def test_horizon_timeout_evaluates_at_32nd_candle():
    """At max_hold=480, interval=15 → 32 bars. Should exit at bar 31 (0-indexed)."""
    klines_after = [
        [1000 + (i + 1) * 900_000, 100, 100.5, 99.5, 100.0 + i * 0.1, 10]
        for i in range(40)
    ]
    exit_ts, exit_p, reason, _ = simulate_exit(
        1000, 100, 95, 110, "LONG", klines_after, 480, 15)
    assert reason == "HORIZON_TIMEOUT"
    # bar index 31 (32nd candle)
    assert exit_p == 100.0 + 31 * 0.1


def test_no_klines_returns_all_none():
    out = simulate_exit(1000, 100, 95, 110, "LONG", [], 480, 15)
    assert out == (None, None, None, None)


def test_zero_risk_returns_all_none():
    klines_after = [[2000, 100, 105, 95, 100, 10]]
    out = simulate_exit(1000, 100, 100, 110, "LONG", klines_after, 480, 15)
    assert out == (None, None, None, None)


def test_few_klines_no_touch_returns_none_NOT_horizon_timeout():
    """Regression: walking one candle at a time, neither SL nor TP hit, the sim
    must return (None,None,None,None) to mean 'still open, check next tick'.
    Earlier bug returned HORIZON_TIMEOUT after just 1 candle."""
    klines_after = [[2000, 100, 100.5, 99.5, 100.0, 10]]   # 1 calm candle
    out = simulate_exit(1000, 100, 95, 110, "LONG", klines_after,
                        max_hold_minutes=480, interval_min=15)
    assert out == (None, None, None, None)


def test_short_sl_realized_r_sign():
    """SHORT SL hit: entry 100, sl 105 (price rose). Realized R should be -1.0."""
    klines_after = [[2000, 100, 108, 99, 102, 50]]
    _, _, reason, r = simulate_exit(1000, 100, 105, 90, "SHORT", klines_after, 480, 15)
    assert reason == "SL_HIT"
    assert r == -1.0   # loss for SHORT
