"""Aggregate BacktestEntries → BacktestSummary, render to text.

Profit factor = sum(positive R) / |sum(negative R)|; None if no losses.
Max drawdown computed on cumulative-R curve, in chronological entry order.

M6 升级:同时算 gross(扣前)和 net(扣成本后)两套 PF/MaxDD/avg_R 对照。
"""
from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import asdict
from typing import List, Optional

from scripts.backtest.cost_model import CostConfig, compute_cost_breakdown
from scripts.backtest.schemas import (
    BacktestEntry,
    BacktestSummary,
    SetupStats,
)


def _pf_and_dd(rs: List[float]) -> tuple[Optional[float], float]:
    """共用:返回 (profit_factor, max_drawdown_r)。"""
    wins_sum = sum(r for r in rs if r > 0)
    losses_sum = sum(-r for r in rs if r < 0)
    pf = (wins_sum / losses_sum) if losses_sum > 0 else None
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)
    return pf, max_dd


def _net_view(entry: BacktestEntry) -> Optional[BacktestEntry]:
    """返回 entry 副本,把 realized_r 替换成 net_realized_r。

    若没算过 net(老数据),返回 None。
    """
    if entry.net_realized_r is None:
        return None
    e = copy.copy(entry)
    e.realized_r = entry.net_realized_r
    return e


def apply_costs_to_entries(
    entries: List[BacktestEntry], cfg: CostConfig,
) -> None:
    """就地为每个 entry 填 net_realized_r / fee_cost_r / slippage_cost_r。"""
    for e in entries:
        if e.realized_r is None:
            continue
        br = compute_cost_breakdown(
            gross_r=e.realized_r,
            entry_price=e.entry_price,
            sl_price=e.sl_price,
            cfg=cfg,
        )
        e.net_realized_r = br.net_r
        e.fee_cost_r = br.fee_cost_r
        e.slippage_cost_r = br.slippage_cost_r


def build_summary(
    entries: List[BacktestEntry],
    total_signals: int,
    total_passed: int,
    period_start: str,
    period_end: str,
    max_concurrent_reached: int,
    cost_config: Optional[CostConfig] = None,
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
    pf, max_dd = _pf_and_dd(rs)

    summary = BacktestSummary(
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

    # M6 扣成本对照:若任一 entry 有 net_realized_r,就算 net 视图
    net_closed = [e for e in closed if e.net_realized_r is not None]
    if net_closed:
        net_views = [v for v in (_net_view(e) for e in net_closed) if v is not None]
        net_rs = [v.realized_r for v in net_views]
        net_pf, net_dd = _pf_and_dd(net_rs)
        net_by_setup: dict = defaultdict(list)
        for v in net_views:
            net_by_setup[v.setup_type].append(v)
        summary.overall_net = SetupStats.from_entries(net_views)
        summary.profit_factor_net = net_pf
        summary.max_drawdown_r_net = net_dd
        summary.by_setup_type_net = {
            k: SetupStats.from_entries(v) for k, v in net_by_setup.items()
        }
        if cost_config is not None:
            summary.cost_config = asdict(cost_config)

    return summary


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
