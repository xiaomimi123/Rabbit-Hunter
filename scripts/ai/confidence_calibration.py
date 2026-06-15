"""AI confidence calibration — running track of (predicted vs actual) win rate
per (model, confidence bucket)."""
import os
import sqlite3
from typing import Optional

MIN_SAMPLES_FOR_CALIBRATION = 10


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def _bucket(confidence: float) -> Optional[float]:
    """Round to nearest 0.1 in [0.5, 0.9]."""
    b = round(confidence, 1)
    if b < 0.5 or b > 0.95:
        return None
    return b


def update_calibration(*, ai_model: str, confidence_at_entry: float,
                        won: bool, db_path: Optional[str] = None) -> None:
    bucket = _bucket(confidence_at_entry)
    if bucket is None:
        return
    db = db_path or _db()
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT actual_win_rate, sample_count FROM ai_confidence_calibration "
            "WHERE ai_model=? AND confidence_bucket=?",
            (ai_model, bucket),
        ).fetchone()
        if row is None:
            actual_wr = 1.0 if won else 0.0
            n = 1
        else:
            old_wr, n_old = row
            n = n_old + 1
            actual_wr = (old_wr * n_old + (1 if won else 0)) / n
        multiplier = actual_wr / bucket if bucket > 0 else 1.0
        conn.execute("""
            INSERT INTO ai_confidence_calibration
                (ai_model, confidence_bucket, predicted_win_rate, actual_win_rate,
                 sample_count, calibration_multiplier, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(ai_model, confidence_bucket) DO UPDATE SET
                actual_win_rate = excluded.actual_win_rate,
                sample_count = excluded.sample_count,
                calibration_multiplier = excluded.calibration_multiplier,
                last_updated = excluded.last_updated
        """, (ai_model, bucket, bucket, actual_wr, n, multiplier))
        conn.commit()
    finally:
        conn.close()


def get_calibration_multiplier(*, ai_model: str, confidence: float,
                                 db_path: Optional[str] = None) -> float:
    """返回乘子(实际胜率 / 预测胜率)。样本不足或无数据 → 1.0."""
    bucket = _bucket(confidence)
    if bucket is None:
        return 1.0
    db = db_path or _db()
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT calibration_multiplier, sample_count "
            "FROM ai_confidence_calibration WHERE ai_model=? AND confidence_bucket=?",
            (ai_model, bucket),
        ).fetchone()
    finally:
        conn.close()
    if row is None or row[1] < MIN_SAMPLES_FOR_CALIBRATION:
        return 1.0
    return float(row[0])
