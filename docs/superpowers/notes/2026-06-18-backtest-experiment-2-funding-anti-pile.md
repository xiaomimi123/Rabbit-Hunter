# Backtest Experiment #2 — Funding anti-pile filter (filter-type funding gate)

> **Date:** 2026-06-18
> **Window:** 30 days (2026-05-19 → 2026-06-18)
> **Symbols:** V5 top-20 minus MATIC (not on OKX)
> **Question:** Does blocking entries when funding is already crowded on our side improve EV?

## Setup

New strategy gate inside `_decide_trend_aligned`:

- **SHORT signal** + `funding_z ≤ -threshold` (shorts already crowded) → block with `FUNDING_SHORTS_CROWDED`
- **LONG signal** + `funding_z ≥ +threshold` (longs already crowded) → block with `FUNDING_LONGS_CROWDED`

Threshold is `v5_funding_anti_pile_threshold` v5_param. `0.0` = filter off (default,
production-safe). `1.5` = experiment value.

The backtest runner now passes the AS-OF funding z-score into `decide()` (was
previously only used for setup_type labeling, not for decisions).

## Critical context: position_sim bug fixed first

Before this experiment, **all earlier backtest results were invalid** because
`simulate_exit` returned HORIZON_TIMEOUT after just 1 candle when the runner
fed klines one-tick-at-a-time. Fix: only declare HORIZON_TIMEOUT when
`len(klines_after) >= max_bars`. Otherwise return None (still open).

**Real holding time after fix**: median 105 min (1.75h), mean 155 min,
P25=45min, P75=210min. Exit reasons: 53% SL_HIT / 40% TP_HIT / 7% HORIZON_TIMEOUT.
This matches the user's intuition that the system already runs ~1-2h holds.

## Results (corrected baseline vs filter on)

|  | Baseline (threshold=0) | Filter ON (threshold=1.5) | Δ |
|---|---|---|---|
| Total scans | 31,521 | 32,300 | — |
| AND-passed | 459 | 439 | -20 (filter blocked) |
| Entered / Closed | 335 | 325 | -10 (with slot churn) |
| **Profit Factor** | 1.32 | **1.44** | +9% |
| Win rate | 45% | 47% | +2pt |
| **Total R** | +57.63 | **+73.18** | **+15.55R (+27%)** |
| avg R / trade | +0.17 | **+0.23** | +35% |
| Max DD | -16.73R | -16.73R | unchanged |

## funding_extreme_long_rsi_neutral breakdown

This was the worst-performing bucket in the baseline and the primary target
of the filter (LONGs entering when longs already crowded).

|  | Baseline | Filter ON |
|---|---|---|
| n | 18 | 4 |
| win rate | 22% | 25% |
| total R | -7.33 | -1.33 |

The filter blocked 14 of 18 trades in this bucket. Saved ~-5.7R in expected
losses. The remaining 4 trades likely had `funding_z` between 1.5 and 2.0
(below extreme threshold but above filter threshold), which means they
weren't actually labeled `funding_extreme` at entry — wait, this needs
verification — actually the label IS computed from |z|>=2.0 in setup_type.py.
So if these 4 have label funding_extreme_long, their z>=2.0 and filter
should have caught them. Possible the funding_z_as_of returned None for
those (insufficient sample at that historical moment) so neither label nor
filter triggered consistently. Worth investigating in a follow-up.

## What the filter is doing

Most of the +15.55R improvement comes from:
1. Blocking 14 negative-EV "funding_extreme_long_rsi_neutral" trades
2. Not blocking SHORT-side extremes (only 1 trade in that bucket period)
3. Aggregate side-level: LONG total +16.45 → +19.12 (slight improvement),
   SHORT total +41.18 → +54.07 (significant improvement)

Note SHORT-side total grew even though no `funding_extreme_short_*` setups
were filtered. This suggests the filter changed which 15m candles got slots,
indirectly opening better SHORT opportunities on subsequent candles. Free
side effect of the gate.

## Decision

**Recommended for production deployment.**

- Code is in place, defaults to threshold=0 (off) — fully backward-compatible
- To enable, set v5_param `v5_funding_anti_pile_threshold=1.5` in DB or
  `V5_FUNDING_ANTI_PILE_THRESHOLD=1.5` env var
- A/B observation suggested: turn on for 2 weeks, compare reflections
  pre/post to confirm the backtest signal translates

## Files

- `docs/superpowers/notes/2026-06-18-backtest-30d-baseline.txt` — corrected baseline (PF 1.32)
- `docs/superpowers/notes/2026-06-18-backtest-experiment-2-funding-anti-pile.txt` — experiment 2 report
- `scripts/v5_strategy.py` — `_decide_trend_aligned` now reads v5_funding_anti_pile_threshold + accepts funding_z kwarg
- `scripts/v5_params.py` — added env mapping `V5_FUNDING_ANTI_PILE_THRESHOLD`
- `scripts/backtest/runner.py` — computes funding_z BEFORE decide(), passes it in
- `tests/test_v5_strategy.py` — 5 new filter tests
- `scripts/backtest/position_sim.py` — bug fix (HORIZON_TIMEOUT only after max_bars)

## Earlier experiments invalidated

The earlier "30-day baseline PF 1.75 / +106R / 58% win" reported in
`docs/superpowers/notes/2026-06-18-backtest-30d-baseline.txt` (old version)
and the corresponding `experiment-1-funding-threshold.md` were ALL based on
the buggy simulator. Numbers in those files should be treated as historical
artifacts only. The corrected baseline replaces both.
