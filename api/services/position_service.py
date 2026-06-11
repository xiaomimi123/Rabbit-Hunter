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
    conn = sqlite3.connect(db_path)
    try:
        sql = "SELECT * FROM positions_v5"
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
