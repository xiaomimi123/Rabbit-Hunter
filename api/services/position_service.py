"""V5 持仓格式化。"""
import sqlite3
from typing import List


def _utc_iso(ts):
    if not isinstance(ts, str) or not ts:
        return ts
    if ts.endswith("Z") or "+" in ts[10:] or "-" in ts[10:]:
        return ts
    return ts + "+00:00"


def fetch_v5_positions(db_path: str, *, status: str = None, limit: int = 100) -> List[dict]:
    """
    status=OPEN 时同时返回 OPEN_DEGRADED (HIGH-1+2 后的新状态:主仓还在,SL/TP 缺一个),
    因为它们都"还在跑",前端 PortfolioPage 应一并看到并按 sl_attached/tp_attached 飘红。
    ERROR_RECONCILE_NEEDED 不算"还在跑"的活仓,单独 ?status=ERROR_RECONCILE_NEEDED 查。
    """
    conn = sqlite3.connect(db_path)
    try:
        sql = "SELECT * FROM positions_v5"
        params: list = []
        if status:
            s = status.upper()
            if s == "OPEN":
                sql += " WHERE status IN ('OPEN', 'OPEN_DEGRADED')"
            else:
                sql += " WHERE status=?"
                params.append(s)
        sql += " ORDER BY entry_time DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        for r in rows:
            for f in ("entry_time", "exit_time", "target_close_at", "created_at", "updated_at"):
                r[f] = _utc_iso(r.get(f))
        return rows
    finally:
        conn.close()


def fetch_v5_paper_positions(db_path: str, *, status: str = None, limit: int = 100) -> List[dict]:
    """SHADOW 模式下,持仓来自 paper_trades。"""
    conn = sqlite3.connect(db_path)
    try:
        sql = "SELECT * FROM paper_trades"
        params = []
        if status:
            sql += " WHERE status=?"
            params.append(status.upper())
        sql += " ORDER BY entry_time DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        for r in rows:
            for f in ("entry_time", "exit_time", "target_close_at", "created_at", "updated_at"):
                r[f] = _utc_iso(r.get(f))
        return rows
    finally:
        conn.close()
