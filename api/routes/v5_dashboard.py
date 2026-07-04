"""V5 dashboard 后端聚合 — Finding 20 (Batch 20).

从 5 张表(trade_scores_v5 / paper_trades / positions_v5 OPEN+CLOSED 各 2)
在 SQL 层做 24h 窗口过滤 + 统计,让前端只拉 <1KB 摘要即可,
不再在浏览器做 2500 行 signals + 500 行 CLOSED 的 reduce。
"""
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from api.schemas.v5_dashboard import (
    DashboardSummaryResponse, DashboardClosedTrade, DashboardErrors,
)


router = APIRouter(prefix="/api/v5", tags=["dashboard"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def _safe_signals(conn, cutoff_expr: str) -> Dict[str, Any]:
    """returns dict with keys: signals_24h, passed_and, executed, block_counts."""
    total = conn.execute(
        f"SELECT COUNT(*) FROM trade_scores_v5 WHERE created_at >= {cutoff_expr}"
    ).fetchone()[0] or 0
    passed = conn.execute(
        f"SELECT COUNT(*) FROM trade_scores_v5 WHERE created_at >= {cutoff_expr} AND should_trade=1"
    ).fetchone()[0] or 0
    executed = conn.execute(
        f"SELECT COUNT(*) FROM trade_scores_v5 WHERE created_at >= {cutoff_expr} AND executed=1"
    ).fetchone()[0] or 0
    rows = conn.execute(
        f"SELECT COALESCE(block_reason, CASE WHEN executed=1 THEN 'EXECUTED' "
        f"                                    WHEN should_trade=1 THEN 'NONE' "
        f"                                    ELSE 'OTHER' END) AS k, COUNT(*) "
        f"FROM trade_scores_v5 WHERE created_at >= {cutoff_expr} GROUP BY k"
    ).fetchall()
    block_counts = {r[0]: r[1] for r in rows}
    return {
        "signals_24h": total,
        "passed_and": passed,
        "executed": executed,
        "block_counts": block_counts,
    }


def _safe_closed(conn, cutoff_expr: str, table: str, source: str) -> List[DashboardClosedTrade]:
    """返回 CLOSED + within 24h + pnl_usdt NOT NULL 的行。"""
    rows = conn.execute(
        f"SELECT id, symbol, side, status, entry_time, exit_time, pnl_usdt, pnl_pct "
        f"FROM {table} WHERE status='CLOSED' AND pnl_usdt IS NOT NULL "
        f"AND exit_time >= {cutoff_expr}"
    ).fetchall()
    return [
        DashboardClosedTrade(
            id=r[0], symbol=r[1], side=r[2], status=r[3],
            entry_time=r[4], exit_time=r[5],
            pnl_usdt=r[6], pnl_pct=r[7], source=source,
        )
        for r in rows
    ]


def _safe_active_count(conn, table: str) -> int:
    return conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE status='OPEN'"
    ).fetchone()[0] or 0


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    hours: int = Query(24, ge=1, le=720),
) -> DashboardSummaryResponse:
    """返回 last `hours` 窗口的 dashboard 聚合(默认 24h)。"""
    cutoff_expr = f"datetime('now', '-{hours} hours')"
    conn = sqlite3.connect(_db())

    errors: Dict[str, Optional[str]] = {}
    signals = {"signals_24h": 0, "passed_and": 0, "executed": 0, "block_counts": {}}
    closed_paper: List[DashboardClosedTrade] = []
    closed_live: List[DashboardClosedTrade] = []
    n_active_paper = 0
    n_active_live = 0

    try:
        signals = _safe_signals(conn, cutoff_expr)
    except Exception as e:
        errors["signals"] = f"{type(e).__name__}: {e}"

    try:
        closed_paper = _safe_closed(conn, cutoff_expr, "paper_trades", "paper")
    except Exception as e:
        errors["paper_history"] = f"{type(e).__name__}: {e}"

    try:
        closed_live = _safe_closed(conn, cutoff_expr, "positions_v5", "live")
    except Exception as e:
        errors["live_history"] = f"{type(e).__name__}: {e}"

    try:
        n_active_paper = _safe_active_count(conn, "paper_trades")
    except Exception as e:
        errors["paper_active"] = f"{type(e).__name__}: {e}"

    try:
        n_active_live = _safe_active_count(conn, "positions_v5")
    except Exception as e:
        errors["live_active"] = f"{type(e).__name__}: {e}"

    conn.close()

    closed_24h = [*closed_paper, *closed_live]
    wins = sum(1 for c in closed_24h if (c.pnl_pct or 0) > 0)
    win_rate = (wins / len(closed_24h)) if closed_24h else 0.0
    pnl_sum = sum((c.pnl_usdt or 0) for c in closed_24h)
    pnl_pct_sum = sum((c.pnl_pct or 0) for c in closed_24h)

    avg_hold = 0.0
    if closed_24h:
        total_mins = 0.0
        n = 0
        for c in closed_24h:
            if not c.entry_time or not c.exit_time:
                continue
            try:
                et = datetime.fromisoformat(c.entry_time.replace("Z", "+00:00"))
                xt = datetime.fromisoformat(c.exit_time.replace("Z", "+00:00"))
                total_mins += (xt - et).total_seconds() / 60.0
                n += 1
            except Exception:
                pass
        if n > 0:
            avg_hold = total_mins / n

    errors_obj = DashboardErrors(**errors) if any(errors.values()) else None

    return DashboardSummaryResponse(
        signals_24h=signals["signals_24h"],
        signals_passed_and=signals["passed_and"],
        signals_executed=signals["executed"],
        signals_block_counts=signals["block_counts"],
        win_rate_24h=win_rate,
        pnl_total_usdt=pnl_sum,
        pnl_total_pct=pnl_pct_sum,
        avg_holding_minutes=avg_hold,
        active_count=n_active_paper + n_active_live,
        closed_24h=closed_24h,
        errors=errors_obj,
    )
