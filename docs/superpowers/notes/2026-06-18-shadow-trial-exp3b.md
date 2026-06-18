# SHADOW Trial — exp3b config (2-week verification)

> **Started:** 2026-06-18 12:32 UTC+8
> **Review by:** 2026-07-02 (T+14 days)
> **Question being answered:** Does the backtest's PF 1.22 net edge translate to live paper trading?

## Live config (applied to production DB)

```sql
-- Already set in /app/data/rabbit_hunter.db:
v5_trend_rsi_long_threshold       = 35.0    -- was default 40.0
v5_funding_anti_pile_threshold    = 1.5     -- was default 0.0 (off)
```

Both read by `scripts/v5_params.get_param()` with 5s cache. Code shipped in
commits `cc8f46b` (filter implementation) and follow-up scorer wiring.

## Backtest predictions (the bar we're checking against)

| Metric | Backtest 30d | Realistic threshold @ 0.20% cost |
|---|---|---|
| Total trades | ~261 | 250-280 |
| Win rate | 47% (gross) | ~46-48% |
| Profit Factor (gross) | 1.65 | — |
| Total R (net @ 0.20%) | +33.46 | +20 to +45 acceptable |
| Avg R / trade (net) | +0.128 | +0.08 to +0.17 acceptable |
| % by main alpha | rsi_neutral_macd_extending_short carries 100% | — |

If 2-week SHADOW shows:
- Net R clearly positive → PROMOTE: consider LIVE small-size trial
- Net R near zero → INCONCLUSIVE: extend trial or refine
- Net R clearly negative → REVERT: backtest edge was illusory

## Daily checks (manual via /v5/reflection + /v5/dashboard)

- **Setup type distribution** — is `rsi_neutral_macd_extending_short` still the workhorse? (~40% of entries)
- **block_reason counts** — are FUNDING_LONGS_CROWDED / FUNDING_SHORTS_CROWDED firing? (filter alive)
- **rsi_neutral_macd_extending_long count** — should be ~30% lower than pre-trial. If unchanged, the threshold change isn't propagating.
- **PnL trajectory** — Dashboard "PnL 累计 24h" should be net positive on average

## Mid-trial pulse (2026-06-25, T+7)

- [ ] Pull `python -m scripts.backtest` reflection of the last 7 days (real trades, not backtest)
- [ ] Compute net R at 0.20% cost over those 7 days
- [ ] Compare to backtest 30d-prorated-to-7d (~+7-10R)
- [ ] If wildly different (>3σ off): investigate before continuing

## End-of-trial review (2026-07-02, T+14)

- [ ] Sum 14d real PnL, win rate, by-setup breakdown
- [ ] Compare to backtest predictions above
- [ ] Decision tree:
  - Match within ±25% → edge confirmed, plan next move (LIVE micro / further refinement)
  - Net positive but smaller → edge is real but thinner; consider lower freq
  - Near zero → reflection: which assumption broke? Cost? Setup quality? Market regime?
  - Net negative → revert + diagnose

## How to revert immediately if needed

```bash
docker exec rabbit-hunter-api python -c "
import sqlite3
c = sqlite3.connect('/app/data/rabbit_hunter.db')
c.execute(\"DELETE FROM system_settings WHERE key='v5_funding_anti_pile_threshold'\")
c.execute(\"DELETE FROM system_settings WHERE key='v5_trend_rsi_long_threshold'\")
c.commit()
print('reverted to defaults: rsi_long=40, funding_filter=off')
"
docker compose restart api collector
```

## Things that DON'T count as edge being real

- 2 weeks of unusual market behavior (single big trend or chop period)
- One winning streak in `rsi_neutral_macd_extending_short` (could be lucky run)
- Win rate up but volume way down (you can win small samples)

To declare success, want:
- n ≥ 30 trades in `rsi_neutral_macd_extending_short` (main alpha)
- n ≥ 100 trades total (statistical sanity)
- Net R per trade ≥ +0.08 AT REAL OBSERVED COST (track fills, not assumed 0.20%)

## Honest caveat (re-read at T+7)

PF 1.22 net is a thin edge. Many "successful backtests" land here. Most don't survive live trading because:
1. Slippage on volatile breaks is non-linear (worse than the average assumed)
2. The main alpha setup might be regime-specific (worked in last 30d because of specific market shape)
3. AI gate (currently active in live, skipped in backtest) might either help or hurt — unknown

Be ready to find the edge isn't there. That's also a real result.
