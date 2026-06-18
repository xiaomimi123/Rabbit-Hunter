"""CLI entry point: python -m scripts.backtest run [options]"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root + scripts/ are on sys.path (matches existing
# collector_main.py convention so scripts/* modules can use their
# 'from v5_types import …' bare imports).
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_SCRIPTS = Path(__file__).parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from scripts.backtest.reporter import build_summary, format_report
from scripts.backtest.runner import BacktestConfig, BacktestRunner
from scripts.v5_symbol_whitelist import V5_TOP20_WHITELIST


def _round_down_15m(dt: datetime) -> datetime:
    return dt.replace(microsecond=0, second=0,
                      minute=(dt.minute // 15) * 15)


def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="python -m scripts.backtest",
        description="Replay V5.1 + V6 strategy rules over historical data.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run a backtest over a date range")
    run.add_argument("--days", type=int, default=30,
                     help="days to backtest (default 30)")
    run.add_argument("--start", type=str,
                     help="ISO start datetime (overrides --days)")
    run.add_argument("--end", type=str, default=None,
                     help="ISO end datetime (default = now rounded down to 15m)")
    run.add_argument("--symbols", type=str,
                     help="comma-separated symbols (default = V5 top-20 whitelist)")
    run.add_argument("--cache-root", type=str, default="data/backtest_cache")
    run.add_argument("--output-root", type=str, default="data/backtest_runs")
    run.add_argument("--no-cache", action="store_true",
                     help="(reserved) force re-fetch")
    run.add_argument("--quiet", action="store_true",
                     help="suppress progress lines")
    run.add_argument("--verbose", action="store_true",
                     help="print every entry as it opens/closes")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    if args.cmd != "run":
        return 1

    if args.end:
        end_dt = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
    else:
        end_dt = _round_down_15m(datetime.now(timezone.utc))

    if args.start:
        start_dt = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
    else:
        start_dt = end_dt - timedelta(days=args.days)

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = sorted(V5_TOP20_WHITELIST)

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
        print(f"Backtest range : {cfg.start_iso} → {cfg.end_iso}")
        print(f"Symbols        : {len(symbols)} ({', '.join(symbols[:5])}…)")
        print(f"DB path        : {cfg.db_path}")
        print(f"Cache root     : {cfg.cache_root}")
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

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    out_dir = Path(args.output_root) / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "entries.json").write_text(
        json.dumps([e.to_dict() for e in runner.entries], indent=2))
    (out_dir / "summary.json").write_text(
        json.dumps(summary.to_dict(), indent=2))
    (out_dir / "report.txt").write_text(report)

    print()
    print(f"Report written to: {out_dir}/")
    print(f"  ├─ entries.json     ({len(runner.entries)} trade records)")
    print(f"  ├─ summary.json")
    print(f"  └─ report.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
