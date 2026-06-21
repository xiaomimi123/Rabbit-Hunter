"""M6 Walk-Forward orchestrator — 防过拟合核心。

依据:Rabbit-Hunter 完整开发设计文档 v1.0 §8。

逻辑:
1. 数据按时间切滚动窗口:[train_start, train_end) 后接 [oos_start, oos_end)。
2. 训练段只是观察 — 当前策略无自动调参,训练段=已知样本;
   若后续接入 grid-search,在此处叉入。
3. 样本外段(OOS)用 *与训练段相同* 的参数跑 BacktestRunner,记录所有 entries。
4. 拼接所有 OOS 段 entries → 纯样本外的资金曲线。
5. 扣成本(cost_model)→ 得到 gross / net 两套 KPI。
6. 判定:OOS avg R > 0、PF > 1 → edge 较可能真;垮 → 过拟合。

CLI:
    python -m scripts.walkforward \
        --start 2026-01-01 --end 2026-06-01 \
        --train-days 60 --oos-days 14 --step-days 14 \
        --symbols BTC/USDT,ETH/USDT \
        --out reports/wf_btc_eth.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from scripts.backtest.cost_model import (
    COST_REALISTIC,
    CostConfig,
)
from scripts.backtest.reporter import (
    apply_costs_to_entries,
    build_summary,
)
from scripts.backtest.runner import BacktestConfig, BacktestRunner
from scripts.backtest.schemas import BacktestEntry

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────


@dataclass
class WalkForwardConfig:
    start_iso: str                       # overall window start (UTC ISO)
    end_iso: str                         # overall window end
    symbols: List[str]
    train_days: int = 60
    oos_days: int = 14
    step_days: int = 14
    cache_root: str = "data/backtest_cache"
    db_path: str = "data/rabbit_hunter.db"
    cost_config: CostConfig = field(default_factory=lambda: COST_REALISTIC)
    setup_filter: Optional[str] = None   # 只统计特定 setup_type 的 entries
    quiet: bool = True


# ─────────────────────────────────────────────────────────────
# Window splitter
# ─────────────────────────────────────────────────────────────


@dataclass
class WindowSpec:
    train_start: str
    train_end: str
    oos_start: str
    oos_end: str

    def to_dict(self) -> dict:
        return asdict(self)


def _parse(iso: str) -> datetime:
    s = iso.rstrip("Z")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # accept date-only
        dt = datetime.strptime(s, "%Y-%m-%d")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def generate_windows(
    *, start_iso: str, end_iso: str,
    train_days: int, oos_days: int, step_days: int,
) -> List[WindowSpec]:
    """生成滚动窗口序列。

    第 N 个窗口:
      train_start_N = start + N*step
      train_end_N   = train_start_N + train_days
      oos_start_N   = train_end_N
      oos_end_N     = oos_start_N + oos_days

    当 oos_end_N > end 时停止生成。
    """
    start = _parse(start_iso)
    end = _parse(end_iso)
    out: List[WindowSpec] = []
    step = timedelta(days=step_days)
    train_dur = timedelta(days=train_days)
    oos_dur = timedelta(days=oos_days)

    n = 0
    while True:
        train_start = start + n * step
        train_end = train_start + train_dur
        oos_start = train_end
        oos_end = oos_start + oos_dur
        if oos_end > end:
            break
        out.append(WindowSpec(
            train_start=train_start.isoformat(),
            train_end=train_end.isoformat(),
            oos_start=oos_start.isoformat(),
            oos_end=oos_end.isoformat(),
        ))
        n += 1
        if n > 5000:  # 安全闸门:别陷入无穷
            raise RuntimeError("generate_windows: too many windows")
    return out


# ─────────────────────────────────────────────────────────────
# OOS run + concatenation
# ─────────────────────────────────────────────────────────────


def run_window_oos(
    *, window: WindowSpec, cfg: WalkForwardConfig,
) -> List[BacktestEntry]:
    """跑一个窗口的 OOS 段,返回 entries。"""
    bt_cfg = BacktestConfig(
        start_iso=window.oos_start,
        end_iso=window.oos_end,
        symbols=cfg.symbols,
        cache_root=cfg.cache_root,
        db_path=cfg.db_path,
        quiet=cfg.quiet,
    )
    runner = BacktestRunner(bt_cfg)
    runner.run()
    entries = runner.entries
    if cfg.setup_filter is not None:
        entries = [e for e in entries if e.setup_type == cfg.setup_filter]
    return entries


# ─────────────────────────────────────────────────────────────
# Top-level orchestrator
# ─────────────────────────────────────────────────────────────


@dataclass
class WalkForwardReport:
    config: dict
    windows: List[dict]
    oos_combined_entries: List[dict]
    oos_summary: dict           # gross 视图(扣成本前)
    oos_summary_net: dict       # net 视图(扣成本后)
    pass_doc_kpi: dict          # 文档 §15 KPI #2、#3 判定

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def run_walkforward(cfg: WalkForwardConfig) -> WalkForwardReport:
    """主入口:跑全部窗口 + 拼接 OOS + 算 gross/net + 判定。"""
    windows = generate_windows(
        start_iso=cfg.start_iso, end_iso=cfg.end_iso,
        train_days=cfg.train_days, oos_days=cfg.oos_days,
        step_days=cfg.step_days,
    )

    all_oos: List[BacktestEntry] = []
    window_dicts: List[dict] = []
    for i, w in enumerate(windows):
        entries = run_window_oos(window=w, cfg=cfg)
        window_dicts.append({
            **w.to_dict(),
            "n_entries": len(entries),
            "n_closed": sum(1 for e in entries if e.realized_r is not None),
        })
        all_oos.extend(entries)
        if not cfg.quiet:
            print(f"[WF] window {i+1}/{len(windows)} OOS: {len(entries)} entries")

    # 扣成本
    apply_costs_to_entries(all_oos, cfg.cost_config)

    # 构造 OOS 综合 summary
    summary = build_summary(
        entries=all_oos,
        total_signals=0,    # WF 不关注 signal 数,只关心 entries
        total_passed=0,
        period_start=windows[0].oos_start if windows else cfg.start_iso,
        period_end=windows[-1].oos_end if windows else cfg.end_iso,
        max_concurrent_reached=0,
        cost_config=cfg.cost_config,
    )

    # 文档 §15 KPI 判定
    gross_avg_r = summary.overall.avg_r if summary.overall.n > 0 else 0.0
    gross_pf = summary.profit_factor   # None 表示无亏损单
    net_avg_r = summary.overall_net.avg_r if summary.overall_net and summary.overall_net.n > 0 else 0.0
    net_pf = summary.profit_factor_net

    # net_pf None = 没有 net 亏损单(全赢)→ 视为 ∞ > 1 → pass
    # net_pf > 1.0 也 pass
    net_pf_passes = (net_pf is None and summary.overall_net is not None
                     and summary.overall_net.n > 0) or (
        net_pf is not None and net_pf > 1.0)
    kpi = {
        "n_oos_trades": summary.overall.n,
        "gross_avg_r": gross_avg_r,
        "gross_profit_factor": gross_pf,
        "net_avg_r": net_avg_r,
        "net_profit_factor": net_pf,
        # 文档 §15 #2:OOS net avg_R > 0 且 net PF > 1(或无亏损)
        "kpi_passes_doc_15_2": (net_avg_r > 0) and net_pf_passes,
    }

    return WalkForwardReport(
        config=asdict(cfg),
        windows=window_dicts,
        oos_combined_entries=[e.to_dict() for e in all_oos],
        oos_summary=_summary_to_kpi_dict(summary, view="gross"),
        oos_summary_net=_summary_to_kpi_dict(summary, view="net"),
        pass_doc_kpi=kpi,
    )


def _summary_to_kpi_dict(s, view: str) -> dict:
    """提取 KPI 子集供 JSON 报告用。"""
    if view == "gross":
        overall = s.overall
        return {
            "n": overall.n,
            "win_rate": overall.win_rate,
            "avg_r": overall.avg_r,
            "total_r": overall.total_r,
            "median_r": overall.median_r,
            "best_r": overall.best_r,
            "worst_r": overall.worst_r,
            "profit_factor": s.profit_factor,
            "max_drawdown_r": s.max_drawdown_r,
        }
    if not s.overall_net or s.overall_net.n == 0:
        return {}
    return {
        "n": s.overall_net.n,
        "win_rate": s.overall_net.win_rate,
        "avg_r": s.overall_net.avg_r,
        "total_r": s.overall_net.total_r,
        "median_r": s.overall_net.median_r,
        "best_r": s.overall_net.best_r,
        "worst_r": s.overall_net.worst_r,
        "profit_factor": s.profit_factor_net,
        "max_drawdown_r": s.max_drawdown_r_net,
    }


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────


def _main():
    p = argparse.ArgumentParser(description="M6 Walk-Forward 标准报告")
    p.add_argument("--start", required=True, help="ISO start (e.g. 2026-01-01)")
    p.add_argument("--end", required=True, help="ISO end (e.g. 2026-06-01)")
    p.add_argument("--symbols", required=True, help="CSV: BTC/USDT,ETH/USDT")
    p.add_argument("--train-days", type=int, default=60)
    p.add_argument("--oos-days", type=int, default=14)
    p.add_argument("--step-days", type=int, default=14)
    p.add_argument("--cache-root", default="data/backtest_cache")
    p.add_argument("--db-path", default="data/rabbit_hunter.db")
    p.add_argument("--setup-filter", default=None, help="只统计指定 setup_type")
    p.add_argument("--cost-preset", choices=["optimistic", "realistic", "pessimistic"],
                   default="realistic")
    p.add_argument("--out", required=True, help="输出 JSON 路径")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    from scripts.backtest.cost_model import (
        COST_OPTIMISTIC, COST_PESSIMISTIC, COST_REALISTIC,
    )
    cost = {
        "optimistic": COST_OPTIMISTIC,
        "realistic": COST_REALISTIC,
        "pessimistic": COST_PESSIMISTIC,
    }[args.cost_preset]

    cfg = WalkForwardConfig(
        start_iso=args.start, end_iso=args.end,
        symbols=[s.strip() for s in args.symbols.split(",") if s.strip()],
        train_days=args.train_days, oos_days=args.oos_days, step_days=args.step_days,
        cache_root=args.cache_root, db_path=args.db_path,
        cost_config=cost,
        setup_filter=args.setup_filter,
        quiet=not args.verbose,
    )
    print(f"[WF] start={args.start} end={args.end} train_days={args.train_days} "
          f"oos_days={args.oos_days} step_days={args.step_days}")
    report = run_walkforward(cfg)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        f.write(report.to_json())
    print(f"[WF] report → {args.out}")

    k = report.pass_doc_kpi
    gpf = f"{k['gross_profit_factor']:.2f}" if k['gross_profit_factor'] is not None else "∞"
    npf = f"{k['net_profit_factor']:.2f}" if k['net_profit_factor'] is not None else "∞"
    print(f"[WF] OOS n={k['n_oos_trades']} "
          f"gross avg_R={k['gross_avg_r']:.3f} PF={gpf} | "
          f"net avg_R={k['net_avg_r']:.3f} PF={npf} "
          f"→ doc §15 KPI #2: {'PASS' if k['kpi_passes_doc_15_2'] else 'FAIL'}")


if __name__ == "__main__":
    _main()
