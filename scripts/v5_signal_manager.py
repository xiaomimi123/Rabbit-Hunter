"""V5 信号管理器 — 替代 v43_kill_queue_manager。

从 trade_scores_v5 读最新一批,按 created_at 倒序。
"""
import sqlite3
from datetime import datetime
from typing import Optional


def _utc_iso(ts):
    """Naive ISO → 补 +00:00。"""
    if not isinstance(ts, str) or not ts:
        return ts
    if ts.endswith("Z") or "+" in ts[10:] or "-" in ts[10:]:
        return ts
    return ts + "+00:00"


class V5SignalManager:
    def __init__(self, db_path: str = "data/rabbit_hunter.db"):
        self.db_path = db_path

    def list_signals(self, *, limit: int = 50, only_executed: bool = False,
                     only_should_trade: bool = False) -> list:
        conn = sqlite3.connect(self.db_path)
        try:
            sql = "SELECT * FROM trade_scores_v5 WHERE 1=1"
            params = []
            if only_executed:
                sql += " AND executed=1"
            if only_should_trade:
                sql += " AND should_trade=1"
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cur = conn.execute(sql, params)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            for r in rows:
                r["created_at"] = _utc_iso(r.get("created_at"))
            return rows
        finally:
            conn.close()

    def funnel_stats(self, since_hours: int = 1) -> dict:
        """返回过去 N 小时的漏斗:总扫到 / should_trade=1 / executed=1。"""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                "SELECT COUNT(*),"
                "       SUM(CASE WHEN should_trade=1 THEN 1 ELSE 0 END),"
                "       SUM(CASE WHEN executed=1 THEN 1 ELSE 0 END)"
                "  FROM trade_scores_v5"
                f" WHERE created_at >= datetime('now', '-{int(since_hours)} hour')"
            )
            total, n_should, n_exec = cur.fetchone()
            return {"total": total or 0,
                    "should_trade": n_should or 0,
                    "executed": n_exec or 0}
        finally:
            conn.close()
