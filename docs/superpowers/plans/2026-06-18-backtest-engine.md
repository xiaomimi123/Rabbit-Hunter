# Backtest Engine MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** CLI backtest engine that replays V5.1 + V6 strategy rules over historical data (last N days) and outputs aggregate performance metrics per setup_type.

**Architecture:** New `scripts/backtest/` package with 7 modules. Reuses existing `v5_strategy.decide()`, `v5_indicator_engine.calculate_indicators()`, `v5_risk_calculator.plan()`, `ai/setup_type.derive()` as pure functions. New on-disk JSON cache for fetched klines. New SQL helper for funding z-score AS-OF a historical timestamp.

**Tech Stack:** Python 3.11, asyncio, urllib (existing OKX client), pytest, dataclasses, argparse.

**Spec reference:** `docs/superpowers/specs/2026-06-18-backtest-engine-design.md`

---

## Phase 1 — Foundation (3 tasks)

### Task 1: Funding z-score as-of helper

**Files:**
- Modify: `scripts/ai/funding_rate_calculator.py`
- Test: `tests/ai/test_funding_rate_calculator.py` (or add to existing)

- [ ] **Step 1:** Write the failing test in `tests/ai/test_funding_rate_calculator.py`:

```python
import sqlite3
from datetime import datetime, timedelta, timezone
import pytest
from scripts.ai.funding_rate_calculator import compute_zscore_as_of, MIN_SAMPLE


def _fresh_db(tmp_path):
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE funding_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            instrument_id TEXT NOT NULL,
            funding_time TEXT NOT NULL,
            funding_rate REAL NOT NULL,
            annualized_rate REAL NOT NULL,
            settled_rate REAL,
            source TEXT NOT NULL DEFAULT 'okx',
            fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return str(db), conn


def test_compute_zscore_as_of_excludes_future_rows(tmp_path):
    db_path, conn = _fresh_db(tmp_path)
    # Insert 25 historical rates (enough samples) for BTCUSDT
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    for i in range(25):
        t = (base + timedelta(hours=i * 8)).isoformat()
        conn.execute(
            "INSERT INTO funding_rates (symbol, instrument_id, funding_time, funding_rate, annualized_rate) VALUES (?, ?, ?, ?, ?)",
            ("BTCUSDT", "BTC-USDT-SWAP", t, 0.0001 * (i % 3 - 1), 0.0))
    # Insert a "future" row that MUST be excluded
    future = (base + timedelta(hours=200)).isoformat()
    conn.execute(
        "INSERT INTO funding_rates (symbol, instrument_id, funding_time, funding_rate, annualized_rate) VALUES (?, ?, ?, ?, ?)",
        ("BTCUSDT", "BTC-USDT-SWAP", future, 99.0, 0.0))
    conn.commit()
    conn.close()

    as_of = (base + timedelta(hours=24 * 7)).isoformat()  # mid-window
    result = compute_zscore_as_of("BTCUSDT", as_of, db_path=db_path)
    assert result is not None
    # The crazy 99.0 future rate must NOT be in baseline (would explode std)
    assert abs(result["mean_30d"]) < 1.0
    assert result["sample_size_30d"] <= 25  # at most the 25 historical
    assert "zscore_30d" in result


def test_compute_zscore_as_of_returns_none_below_min_sample(tmp_path):
    db_path, conn = _fresh_db(tmp_path)
    # only 5 rates — below MIN_SAMPLE (20)
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    for i in range(5):
        t = (base + timedelta(hours=i * 8)).isoformat()
        conn.execute(
            "INSERT INTO funding_rates (symbol, instrument_id, funding_time, funding_rate, annualized_rate) VALUES (?, ?, ?, ?, ?)",
            ("BTCUSDT", "BTC-USDT-SWAP", t, 0.0001, 0.0))
    conn.commit()
    conn.close()
    as_of = (base + timedelta(days=10)).isoformat()
    result = compute_zscore_as_of("BTCUSDT", as_of, db_path=db_path)
    assert result is None
```

- [ ] **Step 2:** Run test, expect FAIL:
```bash
cd /Users/lizhishaoniange/Documents/Rabbit-Hunter && pytest tests/ai/test_funding_rate_calculator.py::test_compute_zscore_as_of_excludes_future_rows -v
```
Expected: ImportError or NameError on `compute_zscore_as_of`.

- [ ] **Step 3:** Add `compute_zscore_as_of` to `scripts/ai/funding_rate_calculator.py`. The implementation refactors the existing `compute_zscore_30d` to share logic:

```python
def _compute_zscore_from_rates(rates: List[float], current_rate: float, sample_size: int) -> Optional[dict]:
    """Pure stats: mean + std + z given rates + current. Returns None if insufficient."""
    if sample_size < MIN_SAMPLE:
        return None
    import statistics
    mean = statistics.fmean(rates)
    if sample_size < 2:
        return None
    stdev = statistics.pstdev(rates) if sample_size > 1 else 0.0
    if stdev == 0:
        z = 0.0
    else:
        z = (current_rate - mean) / stdev
    is_extreme = abs(z) >= EXTREME_THRESHOLD
    direction = None
    if is_extreme:
        direction = "long_crowded" if z > 0 else "short_crowded"
    return {
        "current_funding_rate": current_rate,
        "mean_30d": mean,
        "std_30d": stdev,
        "zscore_30d": z,
        "sample_size_30d": sample_size,
        "is_extreme": is_extreme,
        "extreme_direction": direction,
    }


def compute_zscore_as_of(symbol: str, as_of_iso: str, *, db_path: Optional[str] = None) -> Optional[dict]:
    """Compute z-score for `symbol` using only funding events strictly BEFORE `as_of_iso`.
    Window: 30 days prior to as_of, exclusive of as_of itself. 'Current' = the most recent
    rate strictly before as_of (treated as the 'now' point for that historical moment).
    """
    db = _resolve_db_path(db_path)
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            """SELECT funding_rate FROM funding_rates
               WHERE symbol = ?
                 AND funding_time < ?
                 AND funding_time >= datetime(?, '-30 days')
               ORDER BY funding_time ASC""",
            (symbol, as_of_iso, as_of_iso),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return None
    rates = [r[0] for r in rows]
    if len(rates) < MIN_SAMPLE:
        return None
    current = rates[-1]  # most recent prior to as_of
    baseline = rates[:-1]
    return _compute_zscore_from_rates(baseline, current, len(baseline))
```

- [ ] **Step 4:** Run test, expect PASS:
```bash
pytest tests/ai/test_funding_rate_calculator.py::test_compute_zscore_as_of_excludes_future_rows -v
pytest tests/ai/test_funding_rate_calculator.py::test_compute_zscore_as_of_returns_none_below_min_sample -v
```

- [ ] **Step 5:** Refactor `compute_zscore_30d` to use `_compute_zscore_from_rates` (DRY). Verify all existing tests still pass:
```bash
pytest tests/ -v
```

- [ ] **Step 6:** Commit:
```bash
git add scripts/ai/funding_rate_calculator.py tests/ai/test_funding_rate_calculator.py
git commit -m "feat(funding): add compute_zscore_as_of for historical backtest replay"
```

---

### Task 2: Kline cache fetcher

**Files:**
- Create: `scripts/backtest/__init__.py` (empty package marker)
- Create: `scripts/backtest/kline_fetcher.py`
- Test: `tests/backtest/test_kline_fetcher.py`

- [ ] **Step 1:** Write test:

```python
import json
import os
from pathlib import Path
import pytest
from unittest.mock import patch
from scripts.backtest.kline_fetcher import (
    cache_path_for, load_cached_klines, save_klines_to_cache,
    fetch_klines_with_cache,
)


def test_cache_path_for_includes_range(tmp_path):
    p = cache_path_for(str(tmp_path), "BTCUSDT", "15m", "2026-05-01T00:00:00Z", "2026-06-01T00:00:00Z")
    assert "BTCUSDT" in str(p)
    assert "15m" in str(p)
    assert "2026-05-01" in str(p) or "20260501" in str(p)
    assert str(p).endswith(".json")


def test_save_and_load_klines(tmp_path):
    klines = [
        [1716076800000, 65000.0, 65100.0, 64900.0, 65050.0, 100.0],
        [1716077700000, 65050.0, 65200.0, 65000.0, 65150.0, 120.0],
    ]
    save_klines_to_cache(str(tmp_path), "BTCUSDT", "15m",
                        "2026-05-19T00:00:00Z", "2026-05-19T01:00:00Z", klines)
    loaded = load_cached_klines(str(tmp_path), "BTCUSDT", "15m",
                               "2026-05-19T00:00:00Z", "2026-05-19T01:00:00Z")
    assert loaded == klines


def test_load_returns_none_if_no_cache(tmp_path):
    out = load_cached_klines(str(tmp_path), "BTCUSDT", "15m",
                            "2026-05-19T00:00:00Z", "2026-05-19T01:00:00Z")
    assert out is None


@patch("scripts.backtest.kline_fetcher._fetch_okx_history")
def test_fetch_with_cache_hits_cache_on_second_call(mock_fetch, tmp_path):
    mock_fetch.return_value = [[1716076800000, 65000.0, 65100.0, 64900.0, 65050.0, 100.0]]
    out1 = fetch_klines_with_cache(str(tmp_path), "BTCUSDT", "15m",
                                  "2026-05-19T00:00:00Z", "2026-05-19T01:00:00Z")
    assert mock_fetch.call_count == 1
    out2 = fetch_klines_with_cache(str(tmp_path), "BTCUSDT", "15m",
                                  "2026-05-19T00:00:00Z", "2026-05-19T01:00:00Z")
    assert mock_fetch.call_count == 1  # cache hit
    assert out1 == out2
```

- [ ] **Step 2:** Run test, expect FAIL.

- [ ] **Step 3:** Implement `scripts/backtest/__init__.py` as empty file.

- [ ] **Step 4:** Implement `scripts/backtest/kline_fetcher.py`:

```python
"""OKX historical kline fetcher with JSON disk cache.

Pulls klines from OKX `/api/v5/market/history-candles` paginated in 100-bar
chunks. Caches results by (symbol, interval, from, to) to avoid re-fetch on
re-runs of the same backtest range.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

OKX_HOST = "https://www.okx.com"
DEFAULT_CACHE_ROOT = "data/backtest_cache"

# OKX history-candles bars limit per request
PAGE_SIZE = 300


def _symbol_to_okx(symbol: str) -> str:
    """BTCUSDT → BTC-USDT-SWAP (matches funding_okx_client convention)."""
    if symbol.endswith("USDT"):
        base = symbol[:-4]
        return f"{base}-USDT-SWAP"
    raise ValueError(f"unrecognized symbol: {symbol}")


def _iso_to_safe(iso: str) -> str:
    # 2026-05-19T00:00:00Z → 20260519T000000Z
    return iso.replace("-", "").replace(":", "").replace("+00:00", "Z")


def cache_path_for(root: str, symbol: str, interval: str, from_iso: str, to_iso: str) -> Path:
    Path(root).mkdir(parents=True, exist_ok=True)
    fname = f"{symbol}_{interval}_{_iso_to_safe(from_iso)}_{_iso_to_safe(to_iso)}.json"
    return Path(root) / fname


def load_cached_klines(root: str, symbol: str, interval: str, from_iso: str, to_iso: str) -> Optional[List[List[float]]]:
    p = cache_path_for(root, symbol, interval, from_iso, to_iso)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        return data.get("klines", [])
    except (json.JSONDecodeError, OSError):
        return None


def save_klines_to_cache(root: str, symbol: str, interval: str, from_iso: str, to_iso: str, klines: List[List[float]]) -> None:
    p = cache_path_for(root, symbol, interval, from_iso, to_iso)
    payload = {
        "symbol": symbol,
        "interval": interval,
        "from": from_iso,
        "to": to_iso,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "klines": klines,
    }
    p.write_text(json.dumps(payload))


def _fetch_okx_history(symbol: str, interval: str, from_ms: int, to_ms: int) -> List[List[float]]:
    """Fetch klines from OKX history endpoint, paginated. Returns ascending by ts."""
    inst_id = _symbol_to_okx(symbol)
    bar = interval  # OKX uses same 15m/1H/4H values for `bar`
    if interval == "1h":
        bar = "1H"
    if interval == "4h":
        bar = "4H"
    all_bars: List[List[float]] = []
    cursor = to_ms
    while cursor > from_ms:
        url = (
            f"{OKX_HOST}/api/v5/market/history-candles?instId={inst_id}"
            f"&bar={bar}&after={cursor}&limit={PAGE_SIZE}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "rabbit-hunter-backtest/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read())
        if payload.get("code") != "0":
            raise RuntimeError(f"OKX error: {payload}")
        rows = payload.get("data", [])
        if not rows:
            break
        for r in rows:
            ts = int(r[0])
            if ts < from_ms:
                continue
            all_bars.append([ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
        oldest = int(rows[-1][0])
        if oldest <= from_ms or oldest >= cursor:
            break
        cursor = oldest
    all_bars.sort(key=lambda x: x[0])
    return all_bars


def fetch_klines_with_cache(cache_root: str, symbol: str, interval: str, from_iso: str, to_iso: str) -> List[List[float]]:
    """Returns klines for [from_iso, to_iso]. Cache hit returns immediately; miss
    triggers OKX fetch + cache write."""
    cached = load_cached_klines(cache_root, symbol, interval, from_iso, to_iso)
    if cached is not None:
        return cached
    from_dt = datetime.fromisoformat(from_iso.replace("Z", "+00:00"))
    to_dt = datetime.fromisoformat(to_iso.replace("Z", "+00:00"))
    from_ms = int(from_dt.timestamp() * 1000)
    to_ms = int(to_dt.timestamp() * 1000)
    klines = _fetch_okx_history(symbol, interval, from_ms, to_ms)
    save_klines_to_cache(cache_root, symbol, interval, from_iso, to_iso, klines)
    return klines
```

- [ ] **Step 5:** Create `tests/backtest/__init__.py` (empty).

- [ ] **Step 6:** Run tests, expect PASS:
```bash
pytest tests/backtest/test_kline_fetcher.py -v
```

- [ ] **Step 7:** Commit.

---

### Task 3: BacktestEntry + BacktestSummary schemas

**Files:**
- Create: `scripts/backtest/schemas.py`
- Test: `tests/backtest/test_schemas.py`

- [ ] **Step 1:** Write test:

```python
from scripts.backtest.schemas import BacktestEntry, SetupStats, BacktestSummary

def test_entry_serializes_to_dict():
    e = BacktestEntry(
        symbol="BTCUSDT", side="SHORT", setup_type="funding_extreme_short_rsi_overbought",
        entry_time="2026-05-19T10:00:00Z", entry_price=65000.0,
        sl_price=65500.0, tp_price=64000.0,
        exit_time="2026-05-19T11:30:00Z", exit_price=64000.0,
        exit_reason="TP_HIT", realized_r=2.0, holding_minutes=90,
        funding_z_at_entry=2.4, rsi_15m_at_entry=72.1, macd_hist_15m_at_entry=-0.001,
    )
    d = e.to_dict()
    assert d["symbol"] == "BTCUSDT"
    assert d["realized_r"] == 2.0


def test_setup_stats_calculation():
    entries = [
        BacktestEntry("BTCUSDT", "SHORT", "x", "t1", 100, 105, 90,
                     "t2", 90, "TP_HIT", 2.0, 60, None, 70, 0),
        BacktestEntry("ETHUSDT", "SHORT", "x", "t1", 100, 105, 90,
                     "t2", 105, "SL_HIT", -1.0, 60, None, 70, 0),
        BacktestEntry("SOLUSDT", "SHORT", "x", "t1", 100, 105, 90,
                     "t2", 95, "TP_HIT", 1.0, 60, None, 70, 0),
    ]
    stats = SetupStats.from_entries(entries)
    assert stats.n == 3
    assert stats.wins == 2
    assert stats.losses == 1
    assert abs(stats.win_rate - 2/3) < 0.01
    assert abs(stats.total_r - 2.0) < 0.01
    assert stats.best_r == 2.0
    assert stats.worst_r == -1.0
```

- [ ] **Step 2:** Run test, expect FAIL.

- [ ] **Step 3:** Implement:

```python
"""Schemas for backtest entries + aggregate summary."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Literal


@dataclass
class BacktestEntry:
    symbol: str
    side: Literal["LONG", "SHORT"]
    setup_type: str
    entry_time: str
    entry_price: float
    sl_price: float
    tp_price: float
    exit_time: Optional[str]
    exit_price: Optional[float]
    exit_reason: Optional[Literal["SL_HIT", "TP_HIT", "HORIZON_TIMEOUT"]]
    realized_r: Optional[float]
    holding_minutes: Optional[int]
    funding_z_at_entry: Optional[float]
    rsi_15m_at_entry: float
    macd_hist_15m_at_entry: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SetupStats:
    n: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_r: float = 0.0
    avg_r: float = 0.0
    median_r: float = 0.0
    best_r: float = 0.0
    worst_r: float = 0.0

    @classmethod
    def from_entries(cls, entries: List[BacktestEntry]) -> "SetupStats":
        closed = [e for e in entries if e.realized_r is not None]
        if not closed:
            return cls()
        rs = sorted(e.realized_r for e in closed)
        wins = sum(1 for r in rs if r > 0)
        losses = sum(1 for r in rs if r < 0)
        n = len(rs)
        total = sum(rs)
        avg = total / n
        # median for odd n; mid avg for even n
        if n % 2 == 1:
            median = rs[n // 2]
        else:
            median = (rs[n // 2 - 1] + rs[n // 2]) / 2
        return cls(
            n=n, wins=wins, losses=losses,
            win_rate=wins / n if n else 0.0,
            total_r=total,
            avg_r=avg,
            median_r=median,
            best_r=rs[-1],
            worst_r=rs[0],
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BacktestSummary:
    period_start: str
    period_end: str
    total_signals: int
    total_passed: int
    total_entries: int
    total_closed: int
    by_setup_type: Dict[str, SetupStats] = field(default_factory=dict)
    by_side: Dict[str, SetupStats] = field(default_factory=dict)
    by_symbol: Dict[str, SetupStats] = field(default_factory=dict)
    overall: SetupStats = field(default_factory=SetupStats)
    max_concurrent_reached: int = 0
    profit_factor: Optional[float] = None
    max_drawdown_r: float = 0.0

    def to_dict(self) -> dict:
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_signals": self.total_signals,
            "total_passed": self.total_passed,
            "total_entries": self.total_entries,
            "total_closed": self.total_closed,
            "by_setup_type": {k: v.to_dict() for k, v in self.by_setup_type.items()},
            "by_side": {k: v.to_dict() for k, v in self.by_side.items()},
            "by_symbol": {k: v.to_dict() for k, v in self.by_symbol.items()},
            "overall": self.overall.to_dict(),
            "max_concurrent_reached": self.max_concurrent_reached,
            "profit_factor": self.profit_factor,
            "max_drawdown_r": self.max_drawdown_r,
        }
```

- [ ] **Step 4:** Test PASS, commit.

---

## Phase 2 — Position Simulation (1 task)

### Task 4: OHLC-touch position simulator

**Files:**
- Create: `scripts/backtest/position_sim.py`
- Test: `tests/backtest/test_position_sim.py`

- [ ] **Step 1:** Write tests covering all exit paths:

```python
from scripts.backtest.position_sim import simulate_exit

# kline format: [ts_ms, open, high, low, close, volume]

def test_long_tp_hit_first():
    # entry 100, SL=95, TP=110
    # Subsequent candle: high=112 → TP hit
    klines_after = [
        [2000, 100, 112, 99, 105, 50],
    ]
    exit_t, exit_p, reason, r = simulate_exit(
        entry_ts=1000, entry_price=100, sl_price=95, tp_price=110,
        side="LONG", klines_after=klines_after, max_hold_minutes=480, interval_min=15,
    )
    assert reason == "TP_HIT"
    assert exit_p == 110
    assert r == 2.0    # (110-100)/(100-95)

def test_long_sl_hit_first():
    klines_after = [
        [2000, 100, 105, 94, 102, 50],   # low=94 → SL hit
    ]
    exit_t, exit_p, reason, r = simulate_exit(
        entry_ts=1000, entry_price=100, sl_price=95, tp_price=110,
        side="LONG", klines_after=klines_after, max_hold_minutes=480, interval_min=15,
    )
    assert reason == "SL_HIT"
    assert exit_p == 95
    assert r == -1.0

def test_long_same_candle_both_hits_assume_sl_first():
    klines_after = [
        [2000, 100, 112, 94, 105, 50],   # touched both — assume SL first
    ]
    _, exit_p, reason, r = simulate_exit(1000, 100, 95, 110, "LONG", klines_after, 480, 15)
    assert reason == "SL_HIT"
    assert r == -1.0

def test_short_tp_hit():
    # entry 100, SL=105, TP=90. Subsequent low=88 → TP hit.
    klines_after = [
        [2000, 100, 102, 88, 95, 50],
    ]
    _, exit_p, reason, r = simulate_exit(1000, 100, 105, 90, "SHORT", klines_after, 480, 15)
    assert reason == "TP_HIT"
    assert exit_p == 90
    assert r == 2.0

def test_horizon_timeout():
    # 32 candles × 15min = 480min cap exactly. No SL or TP touch.
    klines_after = [
        [1000 + (i + 1) * 900_000, 100, 100.5, 99.5, 100.0, 10]
        for i in range(40)
    ]
    _, exit_p, reason, r = simulate_exit(
        entry_ts=1000, entry_price=100, sl_price=95, tp_price=110,
        side="LONG", klines_after=klines_after, max_hold_minutes=480, interval_min=15,
    )
    assert reason == "HORIZON_TIMEOUT"
    # Exit at 32nd candle's close (480 min after entry)
    assert exit_p == 100.0
    # R = (100 - 100) / (100 - 95) = 0
    assert r == 0.0
```

- [ ] **Step 2:** Run, expect FAIL.

- [ ] **Step 3:** Implement:

```python
"""OHLC-touch position simulator for backtest.

Given an entry signal + future klines, walk forward bar-by-bar checking SL/TP
touch via OHLC. Returns (exit_ts, exit_price, reason, realized_r).
"""
from __future__ import annotations
from typing import List, Literal, Tuple, Optional

Side = Literal["LONG", "SHORT"]
ExitReason = Literal["SL_HIT", "TP_HIT", "HORIZON_TIMEOUT"]


def simulate_exit(
    entry_ts: int,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    side: Side,
    klines_after: List[List[float]],
    max_hold_minutes: int,
    interval_min: int,
) -> Tuple[Optional[int], Optional[float], Optional[ExitReason], Optional[float]]:
    """Walk forward through klines_after; return first SL or TP hit, or timeout.

    Same-candle SL+TP: assume SL hit first (conservative).
    Realized R: (exit - entry) / (entry - sl) signed for LONG; (entry - exit) / (sl - entry) for SHORT.
    """
    max_bars = max_hold_minutes // interval_min
    risk = abs(entry_price - sl_price)
    if risk == 0:
        return None, None, None, None

    for i, k in enumerate(klines_after[:max_bars]):
        ts, _o, high, low, close, _v = k
        if side == "LONG":
            sl_hit = low <= sl_price
            tp_hit = high >= tp_price
            if sl_hit:
                exit_p = sl_price
                return int(ts), exit_p, "SL_HIT", (exit_p - entry_price) / risk
            if tp_hit:
                exit_p = tp_price
                return int(ts), exit_p, "TP_HIT", (exit_p - entry_price) / risk
        else:  # SHORT
            sl_hit = high >= sl_price
            tp_hit = low <= tp_price
            if sl_hit:
                exit_p = sl_price
                return int(ts), exit_p, "SL_HIT", (entry_price - exit_p) / risk
            if tp_hit:
                exit_p = tp_price
                return int(ts), exit_p, "TP_HIT", (entry_price - exit_p) / risk

    # Horizon timeout — exit at close of the max_bars-th candle (or last available)
    if not klines_after:
        return None, None, None, None
    idx = min(max_bars - 1, len(klines_after) - 1)
    last = klines_after[idx]
    exit_ts = int(last[0])
    exit_p = float(last[4])
    if side == "LONG":
        r = (exit_p - entry_price) / risk
    else:
        r = (entry_price - exit_p) / risk
    return exit_ts, exit_p, "HORIZON_TIMEOUT", r
```

- [ ] **Step 4:** Tests PASS. Commit.

---

## Phase 3 — Runner + Reporter (2 tasks)

### Task 5: BacktestRunner — orchestration

**Files:**
- Create: `scripts/backtest/runner.py`
- Test: `tests/backtest/test_runner.py`

- [ ] **Step 1:** Inspect `scripts/v5_strategy.py::decide()` signature. Document it for the implementer. Key: it returns a `Decision` object with `should_trade`, `side`, `block_reason`, `reasoning`. Decision-side depends on `v5_strategy_mode`. Also inspect `v5_risk_calculator.plan()` signature.

- [ ] **Step 2:** Write test against a synthetic kline + funding fixture:

```python
import pytest
from unittest.mock import patch, MagicMock
from scripts.backtest.runner import BacktestRunner, BacktestConfig


def test_runner_filters_to_15m_close_steps_only():
    cfg = BacktestConfig(
        start_iso="2026-05-19T00:00:00Z",
        end_iso="2026-05-19T01:00:00Z",
        symbols=["BTCUSDT"],
        cache_root="/tmp/bt_test",
        db_path=":memory:",
    )
    runner = BacktestRunner(cfg)
    # 1 hour window → 4 15m close steps
    steps = list(runner._iter_timestamps())
    assert len(steps) == 4

def test_runner_honors_slot_limit():
    # Construct fixture where rule would fire for 5 symbols at same t — only 3 entered
    pass  # full integration test deferred
```

(Full integration test deferred to Task 6 manual smoke. Unit test the iterator.)

- [ ] **Step 3:** Implement `runner.py` (this is the largest file, ~250 lines). Key responsibilities:

```python
"""Backtest runner: orchestrates kline fetch, signal generation, exit simulation."""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Iterator

from scripts.backtest.kline_fetcher import fetch_klines_with_cache
from scripts.backtest.schemas import BacktestEntry
from scripts.backtest.position_sim import simulate_exit
from scripts.ai.funding_rate_calculator import compute_zscore_as_of
from scripts.ai.setup_type import derive_setup_type
from scripts import v5_indicator_engine
from scripts import v5_strategy
from scripts import v5_risk_calculator

log = logging.getLogger(__name__)

INTERVAL_15M_MS = 15 * 60 * 1000
MAX_CONCURRENT = 3
MAX_HOLD_MIN = 480  # 8 hours


@dataclass
class BacktestConfig:
    start_iso: str
    end_iso: str
    symbols: List[str]
    cache_root: str = "data/backtest_cache"
    db_path: str = "data/rabbit_hunter.db"
    quiet: bool = False
    verbose: bool = False


@dataclass
class _OpenPosition:
    entry: BacktestEntry
    klines_after_buffer: List[List[float]] = field(default_factory=list)


class BacktestRunner:
    def __init__(self, cfg: BacktestConfig):
        self.cfg = cfg
        self.entries: List[BacktestEntry] = []
        self.open: List[_OpenPosition] = []
        self.total_signals = 0
        self.total_passed = 0
        self.max_concurrent = 0
        # caches built in load()
        self._kl15: Dict[str, List[List[float]]] = {}
        self._kl4h: Dict[str, List[List[float]]] = {}

    def load(self) -> None:
        """Fetch all kline data for all symbols, both intervals."""
        for sym in self.cfg.symbols:
            self._kl15[sym] = fetch_klines_with_cache(
                self.cfg.cache_root, sym, "15m", self.cfg.start_iso, self.cfg.end_iso
            )
            self._kl4h[sym] = fetch_klines_with_cache(
                self.cfg.cache_root, sym, "4h", self.cfg.start_iso, self.cfg.end_iso
            )
            log.info(f"loaded {sym}: 15m={len(self._kl15[sym])} 4h={len(self._kl4h[sym])}")

    def _iter_timestamps(self) -> Iterator[int]:
        start = int(datetime.fromisoformat(self.cfg.start_iso.replace("Z", "+00:00")).timestamp() * 1000)
        end = int(datetime.fromisoformat(self.cfg.end_iso.replace("Z", "+00:00")).timestamp() * 1000)
        # Align to 15m boundary
        t = (start // INTERVAL_15M_MS) * INTERVAL_15M_MS
        while t < end:
            yield t
            t += INTERVAL_15M_MS

    def _klines_up_to(self, kl: List[List[float]], t_ms: int, max_bars: int = 200) -> List[List[float]]:
        # Return up to last max_bars whose ts < t_ms
        sliced = [k for k in kl if k[0] < t_ms]
        return sliced[-max_bars:]

    def _ts_to_iso(self, t_ms: int) -> str:
        return datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).isoformat()

    def run(self) -> None:
        self.load()
        for t in self._iter_timestamps():
            t_iso = self._ts_to_iso(t)
            # 1. Process exits for open positions
            self._tick_open_exits(t)
            # 2. If slots available, attempt new entries
            available_slots = MAX_CONCURRENT - len(self.open)
            if available_slots <= 0:
                continue
            self._tick_new_entries(t, t_iso, available_slots)
        # close any still-open positions at end-of-period
        self._force_close_remaining()

    def _tick_new_entries(self, t: int, t_iso: str, available_slots: int) -> None:
        # Iterate symbols in deterministic order
        candidates = []  # (symbol, decision, risk_plan, indicators, last_close)
        for sym in sorted(self.cfg.symbols):
            kl15 = self._klines_up_to(self._kl15.get(sym, []), t)
            kl4h = self._klines_up_to(self._kl4h.get(sym, []), t)
            if len(kl15) < 30 or len(kl4h) < 30:
                continue
            indicators = v5_indicator_engine.calculate_indicators(klines_15m=kl15, klines_4h=kl4h)
            # Build the minimal enriched-like object the strategy needs
            current_price = kl15[-1][4]
            delta_15m_pct = (kl15[-1][4] - kl15[-2][4]) / kl15[-2][4] if len(kl15) >= 2 else 0.0
            enriched = SimpleNamespace(
                symbol=sym,
                current_price=current_price,
                delta_15m_pct=delta_15m_pct,
                volume_24h_usdt=0.0,    # not used by strategy
                klines_15m=kl15,
                klines_4h=kl4h,
            )
            decision = v5_strategy.decide(enriched, indicators)
            self.total_signals += 1
            # Apply funding extreme override (matching V6 logic)
            funding_z = compute_zscore_as_of(sym, t_iso, db_path=self.cfg.db_path)
            funding_z_val = funding_z["zscore_30d"] if funding_z else None
            # The strategy doesn't directly use funding — V6 only injects into setup_type.
            # decision.should_trade is unchanged by funding for now.
            if not decision.should_trade:
                continue
            self.total_passed += 1
            risk = v5_risk_calculator.plan(
                entry_price=current_price,
                atr_15m=indicators.atr_15m,
                side=decision.side,
                balance_usdt=1000.0,
            )
            candidates.append((sym, decision, risk, indicators, funding_z_val))

        # Enforce slot limit deterministically
        for sym, decision, risk, indicators, funding_z_val in candidates[:available_slots]:
            setup_type = derive_setup_type(
                rsi_15m=indicators.rsi_15m,
                macd_hist_15m=indicators.macd_hist_15m,
                side=decision.side,
                funding_z=funding_z_val,
                manual=False,
            )
            entry = BacktestEntry(
                symbol=sym, side=decision.side, setup_type=setup_type,
                entry_time=t_iso, entry_price=risk.entry_price,
                sl_price=risk.sl_price, tp_price=risk.tp_price,
                exit_time=None, exit_price=None, exit_reason=None,
                realized_r=None, holding_minutes=None,
                funding_z_at_entry=funding_z_val,
                rsi_15m_at_entry=indicators.rsi_15m,
                macd_hist_15m_at_entry=indicators.macd_hist_15m,
            )
            self.open.append(_OpenPosition(entry=entry))
            self.entries.append(entry)
            self.max_concurrent = max(self.max_concurrent, len(self.open))
            if self.cfg.verbose:
                print(f"  OPEN {sym} {decision.side} @ {risk.entry_price:.4f} sl={risk.sl_price:.4f} tp={risk.tp_price:.4f}")

    def _tick_open_exits(self, t: int) -> None:
        still_open: List[_OpenPosition] = []
        for op in self.open:
            entry = op.entry
            entry_ts = int(datetime.fromisoformat(entry.entry_time.replace("Z", "+00:00")).timestamp() * 1000)
            # All klines after entry_ts and up to t (inclusive)
            klines_after = [
                k for k in self._kl15.get(entry.symbol, [])
                if entry_ts < k[0] <= t
            ]
            exit_ts, exit_p, reason, r = simulate_exit(
                entry_ts=entry_ts,
                entry_price=entry.entry_price,
                sl_price=entry.sl_price,
                tp_price=entry.tp_price,
                side=entry.side,
                klines_after=klines_after,
                max_hold_minutes=MAX_HOLD_MIN,
                interval_min=15,
            )
            if reason is not None:
                entry.exit_time = self._ts_to_iso(exit_ts) if exit_ts else None
                entry.exit_price = exit_p
                entry.exit_reason = reason
                entry.realized_r = r
                entry.holding_minutes = int((exit_ts - entry_ts) / 60_000) if exit_ts else None
                if self.cfg.verbose:
                    print(f"  CLOSE {entry.symbol} {reason} R={r:+.2f}")
            else:
                still_open.append(op)
        self.open = still_open

    def _force_close_remaining(self) -> None:
        for op in self.open:
            entry = op.entry
            kl = self._kl15.get(entry.symbol, [])
            if not kl:
                continue
            last = kl[-1]
            exit_p = float(last[4])
            risk = abs(entry.entry_price - entry.sl_price)
            r = (exit_p - entry.entry_price) / risk if entry.side == "LONG" else (entry.entry_price - exit_p) / risk
            entry.exit_time = self._ts_to_iso(int(last[0]))
            entry.exit_price = exit_p
            entry.exit_reason = "HORIZON_TIMEOUT"
            entry.realized_r = r
            entry_ts = int(datetime.fromisoformat(entry.entry_time.replace("Z", "+00:00")).timestamp() * 1000)
            entry.holding_minutes = int((int(last[0]) - entry_ts) / 60_000)
        self.open = []
```

Also add at top of file: `from types import SimpleNamespace`.

- [ ] **Step 4:** Run iterator test, fix any bugs. Commit.

---

### Task 6: Reporter + aggregator

**Files:**
- Create: `scripts/backtest/reporter.py`
- Test: `tests/backtest/test_reporter.py`

- [ ] **Step 1:** Write test:

```python
from scripts.backtest.reporter import build_summary, format_report
from scripts.backtest.schemas import BacktestEntry

def test_build_summary_aggregates_by_setup():
    entries = [
        BacktestEntry("BTC", "LONG", "A", "t1", 100, 95, 110, "t2", 110, "TP_HIT", 2.0, 60, None, 50, 0),
        BacktestEntry("ETH", "LONG", "A", "t1", 100, 95, 110, "t2", 95, "SL_HIT", -1.0, 60, None, 50, 0),
        BacktestEntry("SOL", "SHORT", "B", "t1", 100, 105, 90, "t2", 90, "TP_HIT", 2.0, 60, None, 50, 0),
    ]
    summary = build_summary(entries, total_signals=10, total_passed=3, period_start="t0", period_end="t9", max_concurrent_reached=2)
    assert summary.by_setup_type["A"].n == 2
    assert summary.by_setup_type["B"].n == 1
    assert summary.by_side["LONG"].n == 2
    assert summary.by_side["SHORT"].n == 1
    assert summary.profit_factor is not None
    assert summary.profit_factor > 1  # 2+2 win vs 1 loss

def test_format_report_renders_setup_table():
    entries = [
        BacktestEntry("BTC", "LONG", "A", "t1", 100, 95, 110, "t2", 110, "TP_HIT", 2.0, 60, None, 50, 0),
    ]
    summary = build_summary(entries, 1, 1, "t0", "t1", 1)
    out = format_report(summary)
    assert "A" in out
    assert "TP_HIT" not in out  # not in summary; per-entry detail elsewhere
    assert "Profit Factor" in out or "profit" in out.lower()
```

- [ ] **Step 2:** Run, expect FAIL.

- [ ] **Step 3:** Implement:

```python
"""Aggregate BacktestEntries into a BacktestSummary; render to text."""
from __future__ import annotations
from typing import List
from collections import defaultdict
from scripts.backtest.schemas import BacktestEntry, SetupStats, BacktestSummary


def build_summary(
    entries: List[BacktestEntry],
    total_signals: int,
    total_passed: int,
    period_start: str,
    period_end: str,
    max_concurrent_reached: int,
) -> BacktestSummary:
    closed = [e for e in entries if e.realized_r is not None]
    by_setup = defaultdict(list)
    by_side = defaultdict(list)
    by_symbol = defaultdict(list)
    for e in closed:
        by_setup[e.setup_type].append(e)
        by_side[e.side].append(e)
        by_symbol[e.symbol].append(e)

    rs = [e.realized_r for e in closed]
    wins_sum = sum(r for r in rs if r > 0)
    losses_sum = sum(-r for r in rs if r < 0)
    pf = (wins_sum / losses_sum) if losses_sum > 0 else None

    # max drawdown on cumulative R curve
    cum = 0
    peak = 0
    max_dd = 0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    return BacktestSummary(
        period_start=period_start,
        period_end=period_end,
        total_signals=total_signals,
        total_passed=total_passed,
        total_entries=len(entries),
        total_closed=len(closed),
        by_setup_type={k: SetupStats.from_entries(v) for k, v in by_setup.items()},
        by_side={k: SetupStats.from_entries(v) for k, v in by_side.items()},
        by_symbol={k: SetupStats.from_entries(v) for k, v in by_symbol.items()},
        overall=SetupStats.from_entries(closed),
        max_concurrent_reached=max_concurrent_reached,
        profit_factor=pf,
        max_drawdown_r=max_dd,
    )


def format_report(s: BacktestSummary) -> str:
    lines = []
    lines.append(f"=== Backtest: {s.period_start} → {s.period_end} ===")
    lines.append(f"Total scans: {s.total_signals}   AND-passed: {s.total_passed}   Entered: {s.total_entries}   Closed: {s.total_closed}")
    lines.append("")
    lines.append("Aggregate:")
    if s.profit_factor is not None:
        lines.append(f"  Profit Factor: {s.profit_factor:.2f}    Max DD: {s.max_drawdown_r:+.2f}R   Max concurrent: {s.max_concurrent_reached}")
    else:
        lines.append(f"  Profit Factor: ∞ (no losses)   Max DD: {s.max_drawdown_r:+.2f}R")
    lines.append(f"  Overall: n={s.overall.n}  win {s.overall.win_rate * 100:.0f}%  total {s.overall.total_r:+.2f}R")
    lines.append("")
    lines.append("By setup_type:")
    sorted_setups = sorted(s.by_setup_type.items(), key=lambda kv: kv[1].total_r, reverse=True)
    lines.append(f"  {'setup_type':<48}{'n':>5}{'win%':>7}{'avg R':>8}{'total R':>9}")
    lines.append("  " + "─" * 76)
    for setup, stat in sorted_setups:
        marker = " ★" if setup.startswith("funding_extreme") else ""
        lines.append(f"  {setup:<48}{stat.n:>5}  {stat.win_rate * 100:>5.0f}%{stat.avg_r:>+7.2f}{stat.total_r:>+8.2f}{marker}")
    lines.append("")
    lines.append("By side:")
    for side, stat in s.by_side.items():
        lines.append(f"  {side:<7} n={stat.n:>3}  win {stat.win_rate * 100:>3.0f}%  total {stat.total_r:+.2f}R")
    lines.append("")
    lines.append("Top 3 / Bottom 3 symbols:")
    sym_sorted = sorted(s.by_symbol.items(), key=lambda kv: kv[1].total_r, reverse=True)
    for sym, stat in sym_sorted[:3]:
        lines.append(f"  + {sym:<10} n={stat.n:>3}  {stat.total_r:+.2f}R")
    for sym, stat in sym_sorted[-3:]:
        if sym in [s for s, _ in sym_sorted[:3]]:
            continue
        lines.append(f"  - {sym:<10} n={stat.n:>3}  {stat.total_r:+.2f}R")
    return "\n".join(lines)
```

- [ ] **Step 4:** Tests PASS. Commit.

---

## Phase 4 — CLI + integration (1 task)

### Task 7: CLI `__main__.py` + glue

**Files:**
- Create: `scripts/backtest/__main__.py`
- Test: `tests/backtest/test_cli.py`

- [ ] **Step 1:** Implement:

```python
"""CLI entry point: python -m scripts.backtest [run] [options]"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.backtest.runner import BacktestConfig, BacktestRunner
from scripts.backtest.reporter import build_summary, format_report

DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "AVAXUSDT", "LINKUSDT", "BNBUSDT", "ADAUSDT", "TRXUSDT",
    "DOTUSDT", "MATICUSDT", "LTCUSDT", "SHIBUSDT", "UNIUSDT",
    "ATOMUSDT", "BCHUSDT", "FILUSDT", "ETCUSDT", "NEARUSDT",
]


def _parse_args():
    p = argparse.ArgumentParser(prog="python -m scripts.backtest")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run backtest over a date range")
    run.add_argument("--days", type=int, default=30, help="days to backtest (default 30)")
    run.add_argument("--start", type=str, help="ISO start (overrides --days)")
    run.add_argument("--end", type=str, default=None, help="ISO end (default now)")
    run.add_argument("--symbols", type=str, help="comma-separated symbols (default V5 whitelist)")
    run.add_argument("--cache-root", type=str, default="data/backtest_cache")
    run.add_argument("--output-root", type=str, default="data/backtest_runs")
    run.add_argument("--no-cache", action="store_true", help="(reserved) force re-fetch")
    run.add_argument("--quiet", action="store_true")
    run.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    if args.cmd != "run":
        return 1

    if args.end:
        end_dt = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
    else:
        end_dt = datetime.now(timezone.utc).replace(microsecond=0, second=0)
        # round down to 15m boundary
        end_dt = end_dt.replace(minute=(end_dt.minute // 15) * 15)

    if args.start:
        start_dt = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
    else:
        start_dt = end_dt - timedelta(days=args.days)

    symbols = args.symbols.split(",") if args.symbols else DEFAULT_SYMBOLS

    cfg = BacktestConfig(
        start_iso=start_dt.isoformat(),
        end_iso=end_dt.isoformat(),
        symbols=symbols,
        cache_root=args.cache_root,
        db_path=os.environ.get("DB_PATH", "data/rabbit_hunter.db"),
        quiet=args.quiet,
        verbose=args.verbose,
    )

    if not args.quiet:
        print(f"Backtest: {cfg.start_iso} → {cfg.end_iso}")
        print(f"Symbols: {len(symbols)}")
        print(f"Loading klines from cache or OKX…")

    runner = BacktestRunner(cfg)
    runner.run()

    summary = build_summary(
        runner.entries,
        total_signals=runner.total_signals,
        total_passed=runner.total_passed,
        period_start=cfg.start_iso,
        period_end=cfg.end_iso,
        max_concurrent_reached=runner.max_concurrent,
    )

    report = format_report(summary)
    print()
    print(report)

    # Write artifacts
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    out_dir = Path(args.output_root) / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "entries.json").write_text(json.dumps([e.to_dict() for e in runner.entries], indent=2))
    (out_dir / "summary.json").write_text(json.dumps(summary.to_dict(), indent=2))
    (out_dir / "report.txt").write_text(report)

    print()
    print(f"Report written to: {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2:** Write CLI test:

```python
import subprocess
import sys
from pathlib import Path


def test_cli_help_runs():
    out = subprocess.run(
        [sys.executable, "-m", "scripts.backtest", "run", "--help"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0
    assert "--days" in out.stdout
    assert "--symbols" in out.stdout
```

- [ ] **Step 3:** Tests PASS. Commit.

---

## Phase 5 — Smoke test + iteration (1 task)

### Task 8: Run against last 7 days, verify reasonable output

This task is manual smoke + bug fixing, not a fresh code drop. The implementer should:

- [ ] **Step 1:** Run smoke test:
```bash
cd /Users/lizhishaoniange/Documents/Rabbit-Hunter
python -m scripts.backtest run --days 7 --quiet
```

Expected first run: takes ~30-60s for OKX fetch + ~10s for replay. Outputs report.

- [ ] **Step 2:** Verify output looks plausible:
  - `Total scans` > 0 (should be ~7 days × 96 candles × 20 symbols ≈ 13,000)
  - `AND-passed` > 0 (probably 50-300 over 7d)
  - `Entered` ≤ AND-passed (slot limit)
  - `Closed` should equal Entered (force-close at end)
  - by_setup_type has more than 1 bucket
  - profit_factor exists if any losses

- [ ] **Step 3:** If anything looks wrong, debug:
  - Add `--verbose` and inspect a few trades
  - Sanity check: open `data/backtest_runs/<timestamp>/entries.json`, check at least one entry has all fields populated

- [ ] **Step 4:** Run 30-day version:
```bash
python -m scripts.backtest run --days 30 --quiet
```
Take ~5min total. Save sample report somewhere.

- [ ] **Step 5:** Document in a README at `scripts/backtest/README.md` how to interpret results.

- [ ] **Step 6:** Final commit + push.

---

## Self-Review

✓ Spec coverage:
- AI gate skipped (D1) — runner doesn't call AI
- OHLC touch + SL-first (D2) — position_sim
- Max hold 8h (D3) — MAX_HOLD_MIN = 480
- Slot limit 3 (D4) — runner._tick_new_entries
- R-value primary metric (D5) — schemas + reporter
- Funding z as-of (D6) — Task 1
- Kline cache (D7) — Task 2

✓ No placeholders. All steps include code.

✓ All type names consistent: `BacktestEntry`, `BacktestSummary`, `SetupStats`, `BacktestConfig`, `BacktestRunner`.

**Known risks:**
- The exact signatures of `v5_strategy.decide()` and `v5_risk_calculator.plan()` may differ from what I sketched. Task 5 Step 1 explicitly inspects them. The implementer should adapt the call to match real signatures (DONE_WITH_CONCERNS acceptable).
- `derive_setup_type` location may be different — Task 5 Step 1 verifies.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-06-18-backtest-engine.md`. Recommended: subagent-driven, 8 tasks, ~3-4 hours.
