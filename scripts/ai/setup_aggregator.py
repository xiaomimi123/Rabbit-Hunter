"""Daily aggregator — group reflections of target_date by setup_type, write daily snapshot."""
import os
import sqlite3
from collections import Counter
from typing import Optional


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def aggregate_daily(*, db_path: Optional[str] = None,
                     target_date: Optional[str] = None) -> int:
    """target_date 形如 '2026-06-14'。None = 昨天。返回写入行数。"""
    db = db_path or _db()
    if target_date is None:
        from datetime import datetime, timezone, timedelta
        target_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("""
            SELECT setup_type, outcome_class, realized_r, holding_minutes,
                   failure_mode_key
              FROM reflections
             WHERE substr(created_at, 1, 10) = ?
        """, (target_date,)).fetchall()

        # group
        groups: dict = {}
        for setup_type, outcome, r, hm, fm in rows:
            g = groups.setdefault(setup_type, {
                "rs": [], "fms": [], "holds": [], "wins": 0, "losses": 0, "scratch": 0,
            })
            g["rs"].append(r)
            g["holds"].append(hm or 0)
            if fm:
                g["fms"].append(fm)
            if outcome == "WIN": g["wins"] += 1
            elif outcome == "LOSS": g["losses"] += 1
            else: g["scratch"] += 1

        written = 0
        for setup_type, g in groups.items():
            n = len(g["rs"])
            avg_r = sum(g["rs"]) / n if n > 0 else 0.0
            wins = [r for r in g["rs"] if r > 0]
            losses = [r for r in g["rs"] if r < 0]
            win_rate = g["wins"] / n if n > 0 else 0.0
            avg_w = sum(wins) / len(wins) if wins else 0.0
            avg_l = sum(losses) / len(losses) if losses else 0.0
            loss_rate = g["losses"] / n if n > 0 else 0.0
            expectancy = win_rate * avg_w + loss_rate * avg_l
            avg_hold = sum(g["holds"]) / n if n > 0 else None
            top_fm = Counter(g["fms"]).most_common(1)[0][0] if g["fms"] else None

            conn.execute("""
                INSERT OR REPLACE INTO setup_performance_daily (
                    date, setup_type, sample_count, win_count, loss_count, scratch_count,
                    win_rate, avg_realized_r, avg_holding_minutes,
                    expectancy, top_failure_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (target_date, setup_type, n, g["wins"], g["losses"], g["scratch"],
                   win_rate, avg_r, avg_hold, expectancy, top_fm))
            written += 1
        conn.commit()
        return written
    finally:
        conn.close()
