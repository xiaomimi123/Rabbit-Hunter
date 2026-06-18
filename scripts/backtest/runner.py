"""Backtest runner — orchestrates kline load, signal generation, exit sim.

Stitches together the existing V5 pipeline pieces (indicator engine, strategy,
risk calculator, setup_type derivation) against historical klines fetched via
`kline_fetcher.fetch_klines_with_cache`. Open positions are tracked in-memory
and resolved each step via `position_sim.simulate_exit`. AI gate is intentionally
skipped per spec D1 — this measures rule alpha only.

Public surface:
    BacktestConfig(start_iso, end_iso, symbols, cache_root, db_path, ...)
    BacktestRunner(cfg).run()
        → populates .entries, .total_signals, .total_passed, .max_concurrent
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional

from scripts.backtest.kline_fetcher import fetch_klines_with_cache
from scripts.backtest.position_sim import simulate_exit
from scripts.backtest.schemas import BacktestEntry
from scripts.ai.funding_rate_calculator import compute_zscore_as_of
from scripts.ai.setup_type import derive_setup_type
from scripts import v5_indicator_engine
from scripts import v5_strategy
from scripts import v5_risk_calculator
from scripts.v5_types import EnrichedItem

log = logging.getLogger(__name__)

INTERVAL_15M_MS = 15 * 60 * 1000
MAX_CONCURRENT = 3
MAX_HOLD_MINUTES = 480       # 8 hours = 32 × 15m candles
MIN_BARS_FOR_INDICATORS = 30
MAX_LOOKBACK_BARS = 200

# Risk plan defaults — size_usdt is not used for R-value math but plan() requires it.
DEFAULT_BALANCE_USDT = 1000.0
DEFAULT_RISK_PCT = 0.015
DEFAULT_LEVERAGE = 10


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
    """Working-set wrapper around a BacktestEntry while it's still open."""
    entry: BacktestEntry
    entry_ts_ms: int


class BacktestRunner:
    """Drives the historical replay loop. Single `.run()` call mutates state."""

    def __init__(self, cfg: BacktestConfig):
        self.cfg = cfg
        # Public, post-run state:
        self.entries: List[BacktestEntry] = []        # ALL entries (open or closed)
        self.total_signals = 0                         # decisions made
        self.total_passed = 0                          # should_trade=True (pre-slot)
        self.max_concurrent = 0
        # Internal:
        self.open: List[_OpenPosition] = []
        self._kl15: Dict[str, List[List[float]]] = {}
        self._kl4h: Dict[str, List[List[float]]] = {}

    # ── data loading ────────────────────────────────────────────────────────

    def load(self) -> None:
        """Fetch 15m + 4h klines for every symbol in the config."""
        for sym in self.cfg.symbols:
            self._kl15[sym] = fetch_klines_with_cache(
                self.cfg.cache_root, sym, "15m",
                self.cfg.start_iso, self.cfg.end_iso,
            )
            self._kl4h[sym] = fetch_klines_with_cache(
                self.cfg.cache_root, sym, "4h",
                self.cfg.start_iso, self.cfg.end_iso,
            )
            if not self.cfg.quiet:
                log.info(
                    "loaded %s: 15m=%d 4h=%d",
                    sym, len(self._kl15[sym]), len(self._kl4h[sym]),
                )

    # ── timestamp iteration ─────────────────────────────────────────────────

    def _iter_timestamps(self) -> Iterator[int]:
        """Yield every 15m-aligned timestamp in [start, end), strictly increasing."""
        start = self._iso_to_ms(self.cfg.start_iso)
        end = self._iso_to_ms(self.cfg.end_iso)
        # Align UP to the first 15m boundary at or after start.
        if start % INTERVAL_15M_MS == 0:
            t = start
        else:
            t = (start // INTERVAL_15M_MS + 1) * INTERVAL_15M_MS
        while t < end:
            yield t
            t += INTERVAL_15M_MS

    # ── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _iso_to_ms(iso: str) -> int:
        return int(
            datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000
        )

    @staticmethod
    def _ts_to_iso(t_ms: int) -> str:
        return datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).isoformat()

    @staticmethod
    def _klines_up_to(klines: List[List[float]], t_ms: int,
                      max_bars: int = MAX_LOOKBACK_BARS) -> List[List[float]]:
        """Return up to `max_bars` klines with ts < t_ms (latest window)."""
        sliced = [k for k in klines if int(k[0]) < t_ms]
        return sliced[-max_bars:]

    # ── main loop ───────────────────────────────────────────────────────────

    def run(self) -> None:
        """Replay loop. Loads if needed, walks timestamps, force-closes at end."""
        if not self._kl15 and self.cfg.symbols:
            self.load()
        for t in self._iter_timestamps():
            # 1. Resolve any open positions whose SL/TP may have been hit by now.
            self._tick_open_exits(t)
            # 2. Look for new entries if we still have slots.
            self._tick_new_entries(t)
        # 3. Anything still open at end of period → HORIZON_TIMEOUT at last close.
        self._force_close_remaining()

    # ── per-tick: exit checks ───────────────────────────────────────────────

    def _tick_open_exits(self, t: int) -> None:
        still_open: List[_OpenPosition] = []
        for op in self.open:
            entry = op.entry
            # All 15m klines that closed strictly AFTER entry and at-or-before t.
            klines_after = [
                k for k in self._kl15.get(entry.symbol, [])
                if op.entry_ts_ms < int(k[0]) <= t
            ]
            exit_ts, exit_p, reason, r = simulate_exit(
                entry_ts=op.entry_ts_ms,
                entry_price=entry.entry_price,
                sl_price=entry.sl_price,
                tp_price=entry.tp_price,
                side=entry.side,
                klines_after=klines_after,
                max_hold_minutes=MAX_HOLD_MINUTES,
                interval_min=15,
            )
            if reason is not None:
                entry.exit_time = self._ts_to_iso(int(exit_ts)) if exit_ts else None
                entry.exit_price = exit_p
                entry.exit_reason = reason
                entry.realized_r = r
                if exit_ts:
                    entry.holding_minutes = int((exit_ts - op.entry_ts_ms) / 60_000)
                if self.cfg.verbose:
                    print(
                        f"  CLOSE {entry.symbol} {reason} "
                        f"R={r:+.2f}" if r is not None else
                        f"  CLOSE {entry.symbol} {reason}"
                    )
            else:
                still_open.append(op)
        self.open = still_open

    # ── per-tick: new entries ───────────────────────────────────────────────

    def _tick_new_entries(self, t: int) -> None:
        available_slots = MAX_CONCURRENT - len(self.open)
        if available_slots <= 0:
            return
        t_iso = self._ts_to_iso(t)

        candidates = []        # (sym, decision, risk, indicators, funding_z_val)
        for sym in sorted(self.cfg.symbols):       # deterministic order
            kl15 = self._klines_up_to(self._kl15.get(sym, []), t)
            kl4h = self._klines_up_to(self._kl4h.get(sym, []), t)
            if len(kl15) < MIN_BARS_FOR_INDICATORS or len(kl4h) < MIN_BARS_FOR_INDICATORS:
                continue

            try:
                indicators = v5_indicator_engine.calculate_indicators(kl15, kl4h)
            except ValueError:
                # Insufficient klines for one of RSI/MACD/ATR — skip silently.
                continue

            current_price = float(kl15[-1][4])
            if len(kl15) >= 2 and kl15[-2][4]:
                delta_15m_pct = (current_price - float(kl15[-2][4])) / float(kl15[-2][4])
            else:
                delta_15m_pct = 0.0

            enriched = EnrichedItem(
                symbol=sym,
                current_price=current_price,
                delta_15m_pct=delta_15m_pct,
                volume_24h_usdt=0.0,        # not consulted by strategy
                klines_15m=kl15,
                klines_4h=kl4h,
            )

            decision = v5_strategy.decide(enriched, indicators)
            self.total_signals += 1
            if not decision.should_trade:
                continue
            self.total_passed += 1

            # Funding z-score AS-OF this historical moment (drives setup_type).
            funding_z_val: Optional[float] = None
            try:
                fz = compute_zscore_as_of(sym, t_iso, db_path=self.cfg.db_path)
                if fz:
                    funding_z_val = fz.get("zscore_30d")
            except Exception as e:
                if self.cfg.verbose:
                    log.debug("funding_z_as_of failed for %s @ %s: %s", sym, t_iso, e)

            try:
                risk = v5_risk_calculator.plan(
                    side=decision.side,
                    entry=current_price,
                    atr=indicators.atr_15m,
                    balance=DEFAULT_BALANCE_USDT,
                    risk_pct=DEFAULT_RISK_PCT,
                    leverage=DEFAULT_LEVERAGE,
                )
            except ValueError:
                # atr=0 or entry=0 — skip this signal.
                continue

            candidates.append((sym, decision, risk, indicators, funding_z_val))

        # Honor slot limit: deterministic, alphabetical (already sorted above).
        for sym, decision, risk, indicators, funding_z_val in candidates[:available_slots]:
            setup_type = derive_setup_type({
                "side": decision.side,
                "strategy_id": "v5_rsi_macd",
                "rsi_15m": indicators.rsi_15m,
                "macd_hist": indicators.macd_hist_15m,
                "macd_hist_prev": indicators.macd_hist_prev_15m,
                "funding_z_score": funding_z_val,
            })
            entry = BacktestEntry(
                symbol=sym,
                side=decision.side,
                setup_type=setup_type,
                entry_time=t_iso,
                entry_price=risk.entry_price,
                sl_price=risk.sl_price,
                tp_price=risk.tp_price,
                exit_time=None,
                exit_price=None,
                exit_reason=None,
                realized_r=None,
                holding_minutes=None,
                funding_z_at_entry=funding_z_val,
                rsi_15m_at_entry=indicators.rsi_15m,
                macd_hist_15m_at_entry=indicators.macd_hist_15m,
            )
            self.entries.append(entry)
            self.open.append(_OpenPosition(entry=entry, entry_ts_ms=t))
            self.max_concurrent = max(self.max_concurrent, len(self.open))
            if self.cfg.verbose:
                print(
                    f"  OPEN {sym} {decision.side} @ {risk.entry_price:.6f} "
                    f"sl={risk.sl_price:.6f} tp={risk.tp_price:.6f} setup={setup_type}"
                )

    # ── end-of-window cleanup ───────────────────────────────────────────────

    def _force_close_remaining(self) -> None:
        """Mark any still-open positions as HORIZON_TIMEOUT at last available close."""
        for op in self.open:
            entry = op.entry
            kl = self._kl15.get(entry.symbol) or []
            # last bar at-or-after entry; fall back to last bar overall
            tail = [k for k in kl if int(k[0]) > op.entry_ts_ms]
            last = tail[-1] if tail else (kl[-1] if kl else None)
            if last is None:
                continue
            exit_p = float(last[4])
            risk_dist = abs(entry.entry_price - entry.sl_price)
            if risk_dist == 0:
                r = 0.0
            elif entry.side == "LONG":
                r = (exit_p - entry.entry_price) / risk_dist
            else:
                r = (entry.entry_price - exit_p) / risk_dist
            last_ts = int(last[0])
            entry.exit_time = self._ts_to_iso(last_ts)
            entry.exit_price = exit_p
            entry.exit_reason = "HORIZON_TIMEOUT"
            entry.realized_r = r
            entry.holding_minutes = int((last_ts - op.entry_ts_ms) / 60_000)
        self.open = []
