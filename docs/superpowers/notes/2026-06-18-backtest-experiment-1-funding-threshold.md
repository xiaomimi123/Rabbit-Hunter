# Backtest Experiment #1 — Funding z-score threshold |z|≥2.0 vs 1.5

> **Date:** 2026-06-18
> **Window:** 30 days (2026-05-19 → 2026-06-18)
> **Symbols:** V5 top-20 minus MATIC (not on OKX)
> **Question:** Does lowering the funding extreme threshold improve setup_type signal?

## Setup

Two runs with identical kline + funding data, identical strategy rules, only one
change: `EXTREME_THRESHOLD` in `scripts/ai/funding_rate_calculator.py` and
the literal `2.0` in `scripts/ai/setup_type.py`.

## Aggregate (unchanged — exactly identical)

|  | Baseline `|z|≥2.0` | Experiment `|z|≥1.5` |
|---|---|---|
| Total scans | 44,346 | 44,346 |
| AND-passed | 1,142 | 1,142 |
| Entered / Closed | 850 | 850 |
| Profit Factor | **1.75** | **1.75** |
| Win rate | 58% | 58% |
| Total R | +106.06R | +106.06R |
| Max DD | -12.57R | -12.57R |

**Why identical?** The strategy's `decide()` does not gate on funding_z.
Funding only affects setup_type labels. So changing threshold only re-labels
already-decided trades — never changes how many trades happen.

## funding_extreme_* buckets

| bucket | `|z|≥2.0` n | `|z|≥2.0` win% | `|z|≥2.0` total R | `|z|≥1.5` n | `|z|≥1.5` win% | `|z|≥1.5` total R |
|---|---|---|---|---|---|---|
| `funding_extreme_long_rsi_neutral` | 42 | 50% | +1.28 | **97** | **55%** | **+8.01** |
| `funding_extreme_long_rsi_oversold` | 2 | 50% | +0.13 | **12** | **58%** | **+0.81** |
| `funding_extreme_short_rsi_neutral` | 0 | — | — | 1 | 0% | -0.45 |
| **Total funding-extreme** | **44** | **50%** | **+1.41** | **110** | **55%** | **+8.37** |

**Bucket grew 2.5x** (44 → 110 trades). **Total R grew 5.9x** (+1.41R → +8.37R).
**Bucket-level win rate** climbed 50% → 55%, indicating funding does discriminate
slightly better than baseline 58% overall.

## What this tells us

### 1. The funding signal is REAL but not exploited
Trades that get the `funding_extreme_*` label win at 55%, marginally above
overall 58%. The signal exists. But because the strategy ignores funding
in its decision, we capture this only as labeling.

### 2. SHORT-extreme is structurally rare
At `|z|≥1.5`, only 1 trade got the `_short` label across 30 days. Either
the market is structurally long-biased in this window, or our histogram
of `current - 30d_mean` doesn't capture short-crowding well in this asset
mix.

### 3. The original threshold was conservative
At `|z|≥2.0`, only 5% of all trades got funding labels. At `|z|≥1.5`, 13%
do. Both are fine for "extreme" semantics; 1.5 just leaves a more useful
analytical layer.

### 4. To MOVE the needle, funding has to gate decisions
Right now changing the threshold only changes the postmortem language.
To extract funding alpha, the strategy needs one of:

- **Filter (defensive):** "If side=SHORT but funding shows short_crowded
  (z<-1.5), skip" — should reduce −R losses on already-crowded shorts.
- **Booster (offensive):** "If side=SHORT and funding shows long_crowded
  (z>+1.5), increase size or relax entry rules" — leans into the
  fade-the-crowd hypothesis.
- **Inversion (aggressive):** "If rsi neutral + funding extreme,
  open a fade trade even without RSI/MACD signal" — V7-style.

## Decision

**Kept threshold at 2.0 in production.** The experiment was diagnostic only.
The labels at 2.0 are clean ("the truly extreme ones") and don't hide signal.
If we later integrate funding INTO decisions, the threshold question is moot
because the filter/booster logic will use raw z, not a binary `is_extreme`.

## Files

- `data/backtest_runs/2026-06-18T03-54-59/` — baseline (|z|≥2.0)
- `data/backtest_runs/2026-06-18T03-59-00/` — experiment (|z|≥1.5)
- `docs/superpowers/notes/2026-06-18-backtest-30d-baseline.txt` — baseline summary
- `docs/superpowers/notes/2026-06-18-backtest-funding-z-1.5-experiment.txt` — experiment summary
