"""
Paper Trades 报表（Rabbit Hunter 4.0 / MVP）

作用：
- 从 Supabase 的 public.paper_trades 拉取数据，生成快速收益概览。
- 输出总体、按 market_phase、按 kill_zone_signal 的分层指标。

指标：
- 总笔数、胜率、平均收益、胜场均值、败场均值、最大/最小收益
- 分层：market_phase、kill_zone_signal

用法：
  py -3 scripts\report_paper_trades.py

环境：
  .env 需要 SUPABASE_URL / SUPABASE_KEY
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List

from dotenv import load_dotenv
from supabase import Client, create_client


@dataclass(frozen=True)
class ReportConfig:
    days: int = 30
    limit: int = 20000  # 防止过大；可通过环境变量调大


def init_supabase() -> Client:
    from pathlib import Path

    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(dotenv_path=base_dir / ".env")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("缺少 SUPABASE_URL / SUPABASE_KEY")
    return create_client(url, key)


def fetch_trades(supabase: Client, cfg: ReportConfig) -> List[Dict[str, Any]]:
    from datetime import datetime, timedelta, timezone

    start_time = (datetime.now(timezone.utc) - timedelta(days=cfg.days)).isoformat()
    resp = (
        supabase.table("paper_trades")
        .select(
            "symbol, created_at, side, ret, pnl_usdt, status, "
            "market_phase, kill_zone_signal, ai_allowed, ai_score, p3a_match_score"
        )
        .gte("created_at", start_time)
        .order("created_at", desc=False)
        .limit(cfg.limit)
        .execute()
    )
    return list(resp.data or [])


def summarize(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not trades:
        return {}
    vals = [float(t.get("ret") or 0.0) for t in trades]
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v <= 0]
    win_rate = len(wins) / len(vals) if vals else 0.0
    avg = sum(vals) / len(vals) if vals else 0.0
    max_ret = max(vals)
    min_ret = min(vals)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    return {
        "count": len(vals),
        "win_rate": win_rate,
        "avg": avg,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max": max_ret,
        "min": min_ret,
    }


def print_block(title: str, summary: Dict[str, Any]) -> None:
    if not summary:
        print(f"{title}: (no data)")
        return
    print(
        f"{title}: "
        f"count={summary['count']}, "
        f"win_rate={summary['win_rate']*100:.2f}%, "
        f"avg={summary['avg']*100:.3f}%, "
        f"avg_win={summary['avg_win']*100:.3f}%, "
        f"avg_loss={summary['avg_loss']*100:.3f}%, "
        f"max={summary['max']*100:.3f}%, "
        f"min={summary['min']*100:.3f}%"
    )


def main() -> None:
    cfg = ReportConfig(
        days=int(os.environ.get("PAPER_REPORT_DAYS", "30")),
        limit=int(os.environ.get("PAPER_REPORT_LIMIT", "20000")),
    )
    supabase = init_supabase()
    trades = fetch_trades(supabase, cfg)
    print(f"[REPORT] trades fetched: {len(trades)} (days={cfg.days}, limit={cfg.limit})")

    # 总体
    print_block("ALL", summarize(trades))

    # 分 market_phase
    by_phase = defaultdict(list)
    for t in trades:
        phase = t.get("market_phase") or "UNKNOWN"
        by_phase[phase].append(t)
    for phase, items in by_phase.items():
        print_block(f"PHASE={phase}", summarize(items))

    # 分 kill_zone
    by_kz = defaultdict(list)
    for t in trades:
        kz = (t.get("kill_zone_signal") or "NONE").upper()
        by_kz[kz].append(t)
    for kz, items in by_kz.items():
        print_block(f"KZ={kz}", summarize(items))

    # 分 AI 放行
    by_ai = defaultdict(list)
    for t in trades:
        ai = "AI_ALLOWED" if t.get("ai_allowed") else "AI_DENY"
        by_ai[ai].append(t)
    for ai, items in by_ai.items():
        print_block(f"{ai}", summarize(items))


if __name__ == "__main__":
    main()


