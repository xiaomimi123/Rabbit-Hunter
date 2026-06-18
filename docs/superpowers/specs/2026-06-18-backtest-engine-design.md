# Backtest Engine Design — V1 MVP

> **Version:** 2026-06-18 · MVP scope · CLI only
> **Goal:** Run current V5.1 + V6 strategy rules against the last 7-60 days of historical kline + funding data and output an aggregate performance report. Answer: **"Are my current rules making money?"**

---

## 1. Problem Statement

The operator has been running V5.1 (trend_aligned) + V6 (funding rate) for a few weeks but lacks enough reflections (each setup bucket < 30 samples) to know which strategies actually work. Backtesting against historical data gives statistically meaningful answers in hours instead of weeks.

**The single question this MVP must answer:**

> "Take my current rules as-is, apply them to N days of historical market data, simulate paper trades with SL/TP exits — what would my total R have been? Broken down by setup_type?"

---

## 2. Scope

### In Scope (MVP)

- Re-runs the EXACT current scoring logic (`v5_strategy.decide()` + `v5_risk_calculator.plan()`) on historical data
- Computes funding z-score AS-OF each historical signal time (not "now")
- Simulates entry at signal candle close
- Simulates exit via OHLC touch on subsequent 15m candles (SL or TP, whichever first; conservative = SL first if same candle)
- Honors MAX_CONCURRENT = 3 (don't double-count when slots full)
- Aggregates by setup_type / side / symbol
- Outputs: stdout table + JSON dump
- Fetches historical klines on-demand from OKX, caches to disk

### Out of Scope (defer to V2)

- AI gate replay (assume rule-only — gives upper bound)
- Parameter grid search
- Walk-forward train/test split
- Web UI (`/v5/backtest` page)
- Slippage / fee modeling
- Multi-strategy A/B comparison
- Live re-validation (paper run with same period)

### Explicitly Different from Live

| Concern | Live | Backtest MVP |
|---|---|---|
| Signal cadence | every ~10s scan | one entry per closed 15m candle |
| AI gate | DeepSeek call | **skipped** (rule-only) |
| Exit detection | real-time price tick polling | OHLC touch on next candles |
| Sizing | Kelly multipliers | fixed 1.0x (R is size-invariant) |
| Same-candle SL+TP | impossible (live = ticks) | assume SL hit first (conservative) |

---

## 3. Architecture

### 3.1 Components

```
┌──────────────────────────────────────────────────────────────┐
│  scripts/backtest/                                            │
│  ├─ __main__.py        ← CLI entry: python -m scripts.backtest│
│  ├─ runner.py          ← BacktestRunner: orchestration        │
│  ├─ kline_fetcher.py   ← OKX history fetch + JSON cache       │
│  ├─ funding_as_of.py   ← compute_zscore_as_of(symbol, t)      │
│  ├─ position_sim.py    ← OHLC-touch SL/TP exit simulator      │
│  ├─ reporter.py        ← aggregate metrics + stdout table     │
│  └─ schemas.py         ← BacktestEntry/Result Pydantic models │
│                                                                │
│  scripts/v5_strategy.py     ← REUSED (pure function)          │
│  scripts/v5_indicator_engine.py ← REUSED                       │
│  scripts/v5_risk_calculator.py  ← REUSED                       │
│  scripts/v5_params.py       ← REUSED (reads system_settings)  │
│  scripts/ai/setup_type.py   ← REUSED (setup_type derivation)  │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow

```
1. CLI args parsed (start, end, symbols)
              ↓
2. kline_fetcher: for each symbol, fetch 15m + 4h klines from OKX
                  caches to data/backtest_cache/<sym>_<int>_<from>_<to>.json
              ↓
3. funding_as_of: build per-symbol pre-computed z-score timeline
                  (one z-value per 8h funding event)
              ↓
4. runner: for each 15m candle close timestamp t in [start, end]:
   ├─ for each symbol:
   │   ├─ get klines_15m[..t]      (in-memory slice)
   │   ├─ get klines_4h[..t]
   │   ├─ get funding_z_as_of(t)
   │   ├─ run v5_indicator_engine.calculate_indicators(klines)
   │   ├─ run v5_strategy.decide(enriched, indicators, funding_z)
   │   │       → decision (should_trade, side, block_reason)
   │   ├─ if should_trade and open_slots < 3:
   │   │   ├─ run v5_risk_calculator.plan(...)
   │   │   ├─ derive setup_type via ai/setup_type.derive()
   │   │   ├─ create BacktestEntry(open at t, entry=close[t], sl, tp)
   │   │   └─ enqueue to position_sim
   │   ├─ for each open entry from prior steps:
   │   │   └─ run position_sim.check_exit(klines_after_entry)
   │   │       → maybe exit (SL_HIT / TP_HIT / TIMEOUT)
   │   └─ (no DB writes — everything in memory)
              ↓
5. reporter: aggregate all closed entries
   → stdout: table by setup_type + side + symbol
   → JSON: data/backtest_runs/<timestamp>/entries.json + summary.json
```

### 3.3 Key Design Decisions

**D1. Skip AI gate.** We're measuring the rule alpha. AI is a filter that approves or denies what the rule proposes. To know "does the rule have edge," strip AI. Future V2 can replay historical AI decisions from `v5_ai_decisions`.

**D2. OHLC-touch exit semantics.** For each 15m candle after entry:
- LONG: if `low ≤ sl_price` → SL hit at `sl_price` (or candle's `low`, whichever was hit first — assume sl_price)
- LONG: if `high ≥ tp_price` → TP hit at `tp_price`
- If both true in same candle: SL first (conservative; defensible because intra-candle path is unknown)
- SHORT: mirror (`high ≥ sl` → SL hit; `low ≤ tp` → TP hit)

**D3. Max hold = 8 hours (32 candles).** If neither SL nor TP hit within 8h, exit at last candle's close with `exit_reason='HORIZON_TIMEOUT'`. (Matches live system's HORIZON_TIMEOUT.)

**D4. Concurrent slot limit honored.** Track open entries; only open new if `len(open) < 3`. If hit at same `t`, deterministic ordering: by symbol alphabetical.

**D5. R-value, not USDT, is the primary metric.** R = (exit_price - entry_price) / (entry_price - sl_price), signed by side. R is size-invariant. Total R across all trades is the alpha proxy. USDT requires sizing assumptions that don't matter for "does the rule work?"

**D6. Funding z-score computed AS-OF.** New helper `compute_zscore_as_of(symbol, t, db_path)` — SQL query:
```sql
SELECT funding_rate FROM funding_rates
WHERE symbol = ? AND funding_time < ? AND funding_time >= datetime(?, '-30 days')
```
Same logic as `compute_zscore_30d` but excludes the current/future funding event.

**D7. Kline cache.** First run: ~40 API calls to OKX (20 symbols × 2 intervals), cached as JSON. Subsequent runs reuse cache. Cache key includes start/end so partial overlap reuses what it can.

---

## 4. Data Schemas

### 4.1 Cached Kline File

`data/backtest_cache/{symbol}_{interval}_{from_iso}_{to_iso}.json`

```json
{
  "symbol": "BTCUSDT",
  "interval": "15m",
  "from": "2026-05-19T00:00:00Z",
  "to":   "2026-06-18T00:00:00Z",
  "fetched_at": "2026-06-18T08:30:00Z",
  "klines": [
    [1716076800000, 65432.10, 65450.00, 65420.00, 65445.10, 12345.67],
    ...
  ]
}
```

(Same `(ts_ms, open, high, low, close, volume)` tuple format as in-memory.)

### 4.2 BacktestEntry (per-trade record)

```python
@dataclass
class BacktestEntry:
    symbol: str
    side: Literal['LONG', 'SHORT']
    setup_type: str
    entry_time: str       # ISO
    entry_price: float
    sl_price: float
    tp_price: float
    exit_time: str | None
    exit_price: float | None
    exit_reason: Literal['SL_HIT', 'TP_HIT', 'HORIZON_TIMEOUT'] | None
    realized_r: float | None       # filled at exit
    holding_minutes: int | None
    funding_z_at_entry: float | None
    rsi_15m_at_entry: float
    macd_hist_15m_at_entry: float
```

### 4.3 BacktestSummary (aggregate)

```python
@dataclass
class BacktestSummary:
    period_start: str
    period_end: str
    total_signals: int          # all decisions made
    total_passed: int           # should_trade=True
    total_entries: int          # actually opened (slot limit)
    total_closed: int
    by_setup_type: dict[str, SetupStats]
    by_side: dict[str, SetupStats]
    by_symbol: dict[str, SetupStats]
    overall: SetupStats
    max_concurrent_reached: int
    profit_factor: float | None
    max_drawdown_r: float

@dataclass
class SetupStats:
    n: int
    wins: int
    losses: int
    win_rate: float
    total_r: float
    avg_r: float
    median_r: float
    best_r: float
    worst_r: float
```

---

## 5. CLI Interface

```
python -m scripts.backtest run [OPTIONS]

Options:
  --days N              Backtest the most recent N days (default 30)
  --start ISO           Explicit start datetime (overrides --days)
  --end ISO             Explicit end datetime (default = now)
  --symbols S1,S2,...   Restrict to specific symbols (default = V5 whitelist top-20)
  --no-cache            Force re-fetch klines (default uses cache when available)
  --output PATH         Output dir (default data/backtest_runs/<timestamp>/)
  --quiet               Suppress per-trade log lines, only show final report
  --verbose             Print every entry as it closes
```

**Stdout report shape:**

```
=== Backtest: 2026-05-19 → 2026-06-18 (30 days) ===
Symbols: 20 (V5 whitelist) · Total scans: 57,600

Signal funnel:
  Scanner candidates           1,247
  AND-passed (rule yes)          287
  Entered (slot available)       142
  Closed                         142
  Still open at end                0

Aggregate:
  Profit Factor: 1.24    Max DD: -8.2R    Sharpe (R-only): 1.1

By setup_type:
  setup_type                                    n   win%   avg R   total R   share
  ─────────────────────────────────────────────────────────────────────────────────
  funding_extreme_short_rsi_overbought         11    73%   +1.24    +13.6     8%   ★
  funding_extreme_long_rsi_oversold             6    67%   +0.91     +5.5     4%   ★
  rsi_oversold_macd_bullish_long               38    53%   +0.31    +11.8    27%
  rsi_overbought_macd_bearish_short            42    38%   -0.18     -7.5    30%
  rsi_neutral_macd_extending_long              28    32%   -0.21     -5.9    20%
  rsi_neutral_macd_extending_short             17    29%   -0.24     -4.1    12%

By side:                LONG  n=72  win 47%  total +11.4
                       SHORT  n=70  win 41%  total -2.1

Best symbol: BTCUSDT (+8.4R, 14 trades)
Worst symbol: AVAXUSDT (-4.1R, 11 trades)

Report written to: data/backtest_runs/2026-06-18T08-30-15/
  ├─ entries.json     (142 trade records)
  ├─ summary.json     (aggregate metrics)
  └─ report.txt       (this report)
```

---

## 6. Error Handling

- **Missing klines (gap in OKX data)**: skip that timestamp, log warning, continue
- **Missing funding rate as-of**: treat z=None (signal eligibility falls back to non-V6 path)
- **Insufficient klines for indicators (< 30 bars)**: skip
- **Symbol not in whitelist**: filter out at fetch stage
- **OKX API rate limit hit**: exponential backoff (3 retries, 2s/4s/8s)
- **No data in period**: emit empty summary, exit code 0

---

## 7. Testing Strategy

- Unit tests per module:
  - `funding_as_of.py`: test against fixture data, verify z-score excludes future
  - `position_sim.py`: test SL hit / TP hit / both-in-same-candle / timeout
  - `reporter.py`: test aggregate math with hand-crafted entry list
- Integration: golden file test — known historical period + known expected output, fail if drift
- Manual smoke: run against last 7 days, verify reasonable output (not all losses, not all wins)

---

## 8. Future Extensions (NOT in MVP)

- **V2.1**: Web UI at `/v5/backtest`, shows historical runs + stdin params
- **V2.2**: Replay historical AI decisions (true signal-to-outcome)
- **V2.3**: Parameter grid search — N runs over param space, find Pareto front
- **V2.4**: Walk-forward — train on rolling 30d, test on next 7d, repeat
- **V2.5**: Multi-strategy A/B — compare V5.1 vs V5.1+V6 vs hypothetical V7
- **V2.6**: Persistent klines table — collector that snapshots klines daily, removes the API fetch step

---

## 9. Open Questions (none — all resolved with user)

- AI gate: skip (D1) ✓
- Exit semantics: OHLC touch + SL-first (D2) ✓
- Output: CLI + JSON (no UI) ✓

---

**End of spec. Plan in `docs/superpowers/plans/2026-06-18-backtest-engine.md`.**
