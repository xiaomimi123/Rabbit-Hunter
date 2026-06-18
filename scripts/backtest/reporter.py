"""Aggregate BacktestEntries → BacktestSummary, render to text.

Profit factor = sum(positive R) / |sum(negative R)|; None if no losses.
Max drawdown computed on cumulative-R curve, in chronological entry order.
"""
from __future__ import annotations

from collections import defaultdict
from typing import List

from scripts.backtest.schemas import (
    BacktestEntry,
    BacktestSummary,
    SetupStats,
)


def build_summary(
    entries: List[BacktestEntry],
    total_signals: int,
    total_passed: int,
    period_start: str,
    period_end: str,
    max_concurrent_reached: int,
) -> BacktestSummary:
    closed = [e for e in entries if e.realized_r is not None]

    by_setup: dict = defaultdict(list)
    by_side: dict = defaultdict(list)
    by_symbol: dict = defaultdict(list)
    for e in closed:
        by_setup[e.setup_type].append(e)
        by_side[e.side].append(e)
        by_symbol[e.symbol].append(e)

    rs = [e.realized_r for e in closed]
    wins_sum = sum(r for r in rs if r > 0)
    losses_sum = sum(-r for r in rs if r < 0)
    pf = (wins_sum / losses_sum) if losses_sum > 0 else None

    # Max drawdown on cumulative R curve in chronological entry order.
    # closed list is in entry order because runner appends in order.
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
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
    lines: List[str] = []
    lines.append(f"=== Backtest: {s.period_start} → {s.period_end} ===")
    lines.append(
        f"Total scans: {s.total_signals}   AND-passed: {s.total_passed}   "
        f"Entered: {s.total_entries}   Closed: {s.total_closed}"
    )
    lines.append("")
    lines.append("Aggregate:")
    if s.profit_factor is not None:
        lines.append(
            f"  Profit Factor: {s.profit_factor:.2f}    "
            f"Max DD: {s.max_drawdown_r:+.2f}R   "
            f"Max concurrent: {s.max_concurrent_reached}"
        )
    else:
        lines.append(
            f"  Profit Factor: ∞ (no losses)   "
            f"Max DD: {s.max_drawdown_r:+.2f}R   "
            f"Max concurrent: {s.max_concurrent_reached}"
        )
    if s.overall.n > 0:
        lines.append(
            f"  Overall: n={s.overall.n}  win {s.overall.win_rate * 100:.0f}%  "
            f"total {s.overall.total_r:+.2f}R   avg {s.overall.avg_r:+.2f}R"
        )
    else:
        lines.append("  Overall: no closed trades")

    if s.by_setup_type:
        lines.append("")
        lines.append("By setup_type:")
        sorted_setups = sorted(
            s.by_setup_type.items(), key=lambda kv: kv[1].total_r, reverse=True
        )
        lines.append(
            f"  {'setup_type':<48}{'n':>5}{'win%':>7}{'avg R':>8}{'total R':>9}"
        )
        lines.append("  " + "─" * 76)
        for setup, stat in sorted_setups:
            marker = " ★" if setup.startswith("funding_extreme") else ""
            lines.append(
                f"  {setup:<48}{stat.n:>5}  {stat.win_rate * 100:>5.0f}%"
                f"{stat.avg_r:>+7.2f}{stat.total_r:>+8.2f}{marker}"
            )

    if s.by_side:
        lines.append("")
        lines.append("By side:")
        for side in sorted(s.by_side.keys()):
            stat = s.by_side[side]
            lines.append(
                f"  {side:<7} n={stat.n:>3}  win {stat.win_rate * 100:>3.0f}%  "
                f"total {stat.total_r:+.2f}R"
            )

    if s.by_symbol:
        lines.append("")
        lines.append("Top 3 / Bottom 3 symbols:")
        sym_sorted = sorted(
            s.by_symbol.items(), key=lambda kv: kv[1].total_r, reverse=True
        )
        top3 = sym_sorted[:3]
        bot3 = [item for item in sym_sorted[-3:] if item not in top3]
        for sym, stat in top3:
            lines.append(f"  + {sym:<10} n={stat.n:>3}  {stat.total_r:+.2f}R")
        for sym, stat in bot3:
            lines.append(f"  - {sym:<10} n={stat.n:>3}  {stat.total_r:+.2f}R")
    return "\n".join(lines)
