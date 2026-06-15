"""Fractional Kelly sizing recommendation engine.

For each setup_type with adequate samples in 30d/60d/90d windows:
- Compute Kelly fraction f = p/a - (1-p)/b
- Apply fractional coefficient based on 3-window consistency
- Clamp to [0.005, 0.02] (0.5% to 2% of account)
- Insert as 'pending' recommendation
"""
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import List, Optional


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


MIN_SAMPLE = 10


def _kelly_in_window(conn, setup_type: str, days: int) -> tuple:
    """Returns (kelly_f, sample_count) for the window. kelly_f=None when insufficient."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT realized_r, outcome_class FROM reflections
         WHERE setup_type = ? AND created_at >= ?
    """, (setup_type, cutoff)).fetchall()
    n = len(rows)
    if n < MIN_SAMPLE:
        return None, n
    wins = [r for r, oc in rows if oc == "WIN"]
    losses = [r for r, oc in rows if oc == "LOSS"]
    if not wins or not losses:
        return None, n
    p = len(wins) / n
    b = sum(wins) / len(wins)
    a = sum(abs(r) for r in losses) / len(losses)
    if a == 0:
        return None, n
    f = (p / a) - ((1 - p) / b)
    return max(0.0, f), n


def generate_sizing_recommendations(*, db_path: Optional[str] = None) -> List[dict]:
    db = db_path or _db()
    conn = sqlite3.connect(db)
    try:
        # All setup_types with any reflections
        setup_types = [r[0] for r in conn.execute(
            "SELECT DISTINCT setup_type FROM reflections"
        ).fetchall()]

        out: List[dict] = []
        for st in setup_types:
            f30, n30 = _kelly_in_window(conn, st, 30)
            f60, n60 = _kelly_in_window(conn, st, 60)
            f90, n90 = _kelly_in_window(conn, st, 90)
            valid = [(f, n) for f, n in [(f30, n30), (f60, n60), (f90, n90)] if f is not None]
            if len(valid) < 2:
                continue   # not enough confidence

            fs = [f for f, _ in valid]
            spread = (max(fs) - min(fs)) / (max(fs) + 1e-6)
            total_n = sum(n for _, n in valid)
            confidence_score = (1 - min(spread, 1.0)) * min(total_n / 90.0, 1.0)
            fk_coef = 0.25 + 0.25 * confidence_score

            # weighted average by sample count
            raw = sum(f * n for f, n in valid) / sum(n for _, n in valid)
            recommended = raw * fk_coef
            recommended = max(0.005, min(0.02, recommended))

            rationale = (
                f"30d Kelly={f30}, 60d={f60}, 90d={f90}; "
                f"spread={spread:.2%}, samples={total_n}, "
                f"fractional_k={fk_coef:.2f}"
            )
            row = {
                "setup_type": st,
                "current_size_multiplier": 1.0,
                "recommended_size_multiplier": recommended,
                "confidence_score": confidence_score,
                "rationale": rationale,
                "sample_count_30d": n30,
                "sample_count_60d": n60,
                "sample_count_90d": n90,
                "kelly_f_30d": f30,
                "kelly_f_60d": f60,
                "kelly_f_90d": f90,
                "fractional_kelly_applied": fk_coef,
            }
            conn.execute("""
                INSERT INTO position_sizing_recommendations (
                    setup_type, current_size_multiplier, recommended_size_multiplier,
                    confidence_score, rationale,
                    sample_count_30d, sample_count_60d, sample_count_90d,
                    kelly_f_30d, kelly_f_60d, kelly_f_90d,
                    fractional_kelly_applied
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["setup_type"], row["current_size_multiplier"],
                row["recommended_size_multiplier"], row["confidence_score"],
                row["rationale"], row["sample_count_30d"], row["sample_count_60d"],
                row["sample_count_90d"], row["kelly_f_30d"], row["kelly_f_60d"],
                row["kelly_f_90d"], row["fractional_kelly_applied"],
            ))
            out.append(row)
        conn.commit()
        return out
    finally:
        conn.close()
