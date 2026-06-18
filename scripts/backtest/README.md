# Backtest Engine

Replay V5.1 + V6 strategy rules over historical OKX kline + funding data.
Answers: **"Are my current rules making money?"** — in hours, not weeks.

## Quick start

```bash
# 30-day default (most useful baseline)
docker exec rabbit-hunter-api python -m scripts.backtest run --days 30

# 7-day quick check
docker exec rabbit-hunter-api python -m scripts.backtest run --days 7

# Custom window
docker exec rabbit-hunter-api python -m scripts.backtest run \
    --start 2026-05-01T00:00:00Z \
    --end   2026-06-01T00:00:00Z

# Restrict symbols
docker exec rabbit-hunter-api python -m scripts.backtest run \
    --days 30 --symbols BTCUSDT,ETHUSDT,SOLUSDT
```

> **Note:** Run inside the `rabbit-hunter-api` Docker container. Host macOS has
> intermittent SSL EOF errors against `www.okx.com`. The container's network
> is reliable, and it already has `requests` installed for retries.

## Output

Three files in `data/backtest_runs/<timestamp>/`:

- `report.txt` — human-readable summary (also printed to stdout)
- `summary.json` — aggregate metrics (PF, max DD, by_setup_type, etc.)
- `entries.json` — every trade record (entry/exit/realized R/funding z/etc.)

## How to read the report

```
=== Backtest: 2026-05-19 → 2026-06-18 (30 days) ===
Total scans: 44,346  AND-passed: 1,142  Entered: 850  Closed: 850

Aggregate:
  Profit Factor: 1.75    Max DD: -12.57R   Max concurrent: 3
  Overall: n=850  win 58%  total +106.06R   avg +0.12R
```

- **Total scans** — every `(symbol, 15m timestamp)` that ran through the scorer
- **AND-passed** — rule engine said `should_trade=true`
- **Entered** — actually opened (≤AND-passed because of 3-slot concurrency)
- **Closed** — exited via SL / TP / 8h timeout

**Profit Factor (PF)** = sum(positive R) / |sum(negative R)|. PF > 1 means
the rule has positive expectancy. PF > 1.5 is meaningful; PF > 2 is rare.

**R** = multiples of risk taken. R=2 means the trade made 2× the SL distance.
R is size-invariant: makes Apples-to-apples comparison across symbols.

**Max DD** = peak-to-trough drop on cumulative R curve. Lower (more negative)
is worse. Important for understanding tail risk.

## Reading the by_setup_type table

Sorted by total R descending. Star (★) marks `funding_extreme_*` buckets
(V6 alpha dimension).

When deciding:
- **n ≥ 30**: statistically meaningful, win rate + avg R are signal
- **n < 30**: noise; don't trust the numbers
- **avg R > 0**: setup has positive expectancy
- **win rate**: lower bound for setups where TP : SL ratio > 1; e.g. 2 R TP /
  1 R SL means win 33% break-even

## Design choices (MVP)

- **AI gate is SKIPPED** — we measure rule alpha alone. If you want AI gate
  effects too, the V2 backtest will replay historical `v5_ai_decisions`.
- **OHLC-touch exits** — for each 15m candle after entry, check whether
  `high`/`low` crossed `sl_price` / `tp_price`. Same-candle both-touch
  defaults to **SL first** (conservative; intra-candle path unknowable).
- **Max hold 8 hours** = 32 candles. After that, exit at close with
  `HORIZON_TIMEOUT`.
- **Fixed sizing 1.0x** — Kelly multipliers don't affect R-value.
- **Funding z-score AS-OF** — recomputed at every signal time using only
  `funding_rates` rows with `funding_time < as_of` (excludes future).

## Caches

- `data/backtest_cache/<symbol>_<interval>_<from>_<to>.json` — fetched OKX
  klines. Same range = cache hit. Different range = new fetch.
- Delete the cache dir to force re-fetch.

## What's NOT in MVP (defer to V2)

- Web UI at `/v5/backtest`
- Parameter grid search
- Walk-forward train/test split
- AI gate replay
- Slippage / fee modeling
- Persistent klines DB table (we fetch on-demand each run)

## Modules

| File | Role |
|---|---|
| `__main__.py` | CLI entry point + arg parsing + JSON artifact writer |
| `runner.py` | BacktestRunner: orchestrates load → iterate → score → simulate exit |
| `kline_fetcher.py` | OKX paginated history fetch + JSON disk cache |
| `position_sim.py` | OHLC-touch SL/TP exit simulator |
| `reporter.py` | Aggregate entries → BacktestSummary, render to text |
| `schemas.py` | Dataclasses: BacktestEntry / SetupStats / BacktestSummary |

## Baseline results

`docs/superpowers/notes/2026-06-18-backtest-30d-baseline.txt`
contains the first successful 30-day baseline. PF 1.75, +106R over 850 trades.
Use it as the comparator for future strategy changes.
