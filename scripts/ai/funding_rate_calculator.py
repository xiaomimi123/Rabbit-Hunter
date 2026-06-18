"""z-score 计算 + cache 读写。无副作用 except cache 写。

设计:
- 计算窗口 30 天滚动 (从最近一次往回找 30d 内所有 funding)
- 最小样本 20(< 7 天数据就 None)
- 排除当前点算 mean/std (防止当前极端值污染基线)
- |z| ≥ 2.0 = extreme
- extreme_direction: long_crowded (z 正,多头付钱) / short_crowded (z 负)
"""
import os
import sqlite3
import statistics
from typing import List, Optional


MIN_SAMPLE_FOR_ZSCORE = 20
EXTREME_THRESHOLD = 2.0


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def compute_zscore_30d(symbol: str, *, db_path: Optional[str] = None) -> Optional[dict]:
    """返回 dict 含 zscore_30d 等;None 表示样本不足。

    最新一笔作为 current_funding_rate;倒数第 2 到 30d 内的作为基线。
    """
    db = db_path or _db()
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("""
            SELECT funding_rate FROM funding_rates
             WHERE symbol = ? AND source = 'okx'
               AND funding_time >= datetime('now', '-30 days')
             ORDER BY funding_time DESC
        """, (symbol,)).fetchall()
    finally:
        conn.close()

    rates = [r[0] for r in rows]
    if len(rates) < MIN_SAMPLE_FOR_ZSCORE:
        return None

    current = rates[0]
    historical = rates[1:]
    mean = statistics.mean(historical)
    std = statistics.stdev(historical) if len(historical) >= 2 else 0.0

    if std == 0:
        zscore = 0.0
    else:
        zscore = (current - mean) / std

    is_extreme = abs(zscore) >= EXTREME_THRESHOLD
    extreme_direction = (
        "long_crowded" if zscore >= EXTREME_THRESHOLD
        else "short_crowded" if zscore <= -EXTREME_THRESHOLD
        else None
    )

    return {
        "current_funding_rate": current,
        "mean_30d": mean,
        "std_30d": std,
        "zscore_30d": zscore,
        "sample_size_30d": len(rates),
        "is_extreme": is_extreme,
        "extreme_direction": extreme_direction,
    }


def compute_zscore_as_of(symbol: str, as_of_iso: str, *,
                          db_path: Optional[str] = None) -> Optional[dict]:
    """Backtest replay variant: compute z-score using only funding events
    strictly BEFORE `as_of_iso`. Window: 30 days prior to as_of, exclusive
    of as_of itself.

    'current_funding_rate' = the most recent rate strictly before as_of
    (treated as the 'now' point for that historical moment).

    Returns dict with same shape as compute_zscore_30d, or None if < MIN_SAMPLE.
    """
    db = db_path or _db()
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("""
            SELECT funding_rate FROM funding_rates
             WHERE symbol = ? AND source = 'okx'
               AND funding_time < ?
               AND funding_time >= datetime(?, '-30 days')
             ORDER BY funding_time DESC
        """, (symbol, as_of_iso, as_of_iso)).fetchall()
    finally:
        conn.close()

    rates = [r[0] for r in rows]
    if len(rates) < MIN_SAMPLE_FOR_ZSCORE:
        return None

    current = rates[0]
    historical = rates[1:]
    mean = statistics.mean(historical)
    std = statistics.stdev(historical) if len(historical) >= 2 else 0.0

    if std == 0:
        zscore = 0.0
    else:
        zscore = (current - mean) / std

    is_extreme = abs(zscore) >= EXTREME_THRESHOLD
    extreme_direction = (
        "long_crowded" if zscore >= EXTREME_THRESHOLD
        else "short_crowded" if zscore <= -EXTREME_THRESHOLD
        else None
    )

    return {
        "current_funding_rate": current,
        "mean_30d": mean,
        "std_30d": std,
        "zscore_30d": zscore,
        "sample_size_30d": len(rates),
        "is_extreme": is_extreme,
        "extreme_direction": extreme_direction,
    }


def refresh_zscore_cache(symbols: List[str], *,
                          db_path: Optional[str] = None) -> int:
    """对每个 symbol 算 z-score 并写 cache。返回写入条数(跳过 None)。"""
    db = db_path or _db()
    written = 0
    conn = sqlite3.connect(db)
    try:
        for sym in symbols:
            out = compute_zscore_30d(sym, db_path=db)
            if out is None:
                continue
            conn.execute("""
                INSERT OR REPLACE INTO funding_zscore_cache (
                    symbol, computed_at, current_funding_rate,
                    mean_30d, std_30d, zscore_30d, sample_size_30d,
                    is_extreme, extreme_direction
                ) VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?)
            """, (
                sym, out["current_funding_rate"],
                out["mean_30d"], out["std_30d"], out["zscore_30d"],
                out["sample_size_30d"],
                1 if out["is_extreme"] else 0,
                out["extreme_direction"],
            ))
            written += 1
        conn.commit()
    finally:
        conn.close()
    return written


def get_cached_zscore(symbol: str, *,
                       db_path: Optional[str] = None) -> Optional[dict]:
    """O(1) 读 cache。None 表示该 symbol 还没计算过。"""
    db = db_path or _db()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM funding_zscore_cache WHERE symbol=?", (symbol,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    d = dict(row)
    d["is_extreme"] = bool(d.get("is_extreme"))
    return d
