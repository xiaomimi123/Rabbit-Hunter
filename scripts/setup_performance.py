"""M8 setup_performance — 实时聚合 + 自动剪枝。

依据:Rabbit-Hunter 完整开发设计文档 v1.0 §10。

核心规则:
1. 每个 setup_type 累计 n、avg_realized_r、总 R。
2. n ≥ MIN_SAMPLE_SIZE_FOR_DECISION (30) 才可信。
3. n ≥ 30 且 net_avgR < 0 → 自动 disable(隐形杀手)。
4. n < 30 → status='noisy',不据此决策但允许继续累积样本。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Set

from scripts.risk_constitution import (
    DEFAULT_DISABLED_SETUPS,
    MIN_SAMPLE_SIZE_FOR_DECISION,
)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS setup_performance (
    setup_type        TEXT    PRIMARY KEY,
    sample_count      INTEGER NOT NULL DEFAULT 0,
    win_count         INTEGER NOT NULL DEFAULT 0,
    loss_count        INTEGER NOT NULL DEFAULT 0,
    scratch_count     INTEGER NOT NULL DEFAULT 0,
    avg_realized_r    REAL,
    total_realized_r  REAL,
    status            TEXT    NOT NULL DEFAULT 'noisy',
    disabled_reason   TEXT,
    updated_at        TEXT    NOT NULL
);
"""


def ensure_table(db_path: str) -> None:
    """幂等建表。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def refresh_setup_performance(db_path: str) -> dict[str, dict]:
    """从 reflections 表重算所有 setup_type 的聚合 + 状态。

    返回当前所有 setup_type → 聚合 dict 的快照。
    """
    ensure_table(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("""
            SELECT setup_type, outcome_class, realized_r
            FROM reflections
            WHERE setup_type IS NOT NULL
        """).fetchall()

        # 聚合
        agg: dict[str, dict] = {}
        for setup_type, outcome, r in rows:
            if setup_type not in agg:
                agg[setup_type] = {
                    "sample_count": 0, "win_count": 0,
                    "loss_count": 0, "scratch_count": 0,
                    "total_r": 0.0,
                }
            a = agg[setup_type]
            a["sample_count"] += 1
            if outcome == "WIN":
                a["win_count"] += 1
            elif outcome == "LOSS":
                a["loss_count"] += 1
            else:
                a["scratch_count"] += 1
            a["total_r"] += float(r or 0.0)

        # 决定 status
        result: dict[str, dict] = {}
        for setup_type, a in agg.items():
            n = a["sample_count"]
            avg_r = a["total_r"] / n if n > 0 else 0.0
            if n < MIN_SAMPLE_SIZE_FOR_DECISION:
                status, reason = "noisy", None
            elif avg_r < 0:
                status, reason = "disabled", "NEGATIVE_EXPECTANCY_30PLUS"
            else:
                status, reason = "active", None

            conn.execute("""
                INSERT INTO setup_performance (
                    setup_type, sample_count, win_count, loss_count, scratch_count,
                    avg_realized_r, total_realized_r, status, disabled_reason, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(setup_type) DO UPDATE SET
                    sample_count=excluded.sample_count,
                    win_count=excluded.win_count,
                    loss_count=excluded.loss_count,
                    scratch_count=excluded.scratch_count,
                    avg_realized_r=excluded.avg_realized_r,
                    total_realized_r=excluded.total_realized_r,
                    status=excluded.status,
                    disabled_reason=excluded.disabled_reason,
                    updated_at=excluded.updated_at
            """, (
                setup_type, n, a["win_count"], a["loss_count"], a["scratch_count"],
                avg_r, a["total_r"], status, reason, now_iso,
            ))
            result[setup_type] = {
                "sample_count": n, "win_count": a["win_count"],
                "loss_count": a["loss_count"], "scratch_count": a["scratch_count"],
                "avg_realized_r": avg_r, "total_realized_r": a["total_r"],
                "status": status, "disabled_reason": reason,
            }
        conn.commit()
        return result
    finally:
        conn.close()


def get_disabled_setups(db_path: str | None = None) -> Set[str]:
    """返回当前所有需禁用的 setup_type。

    包含两个来源:
    1. 文档 §4 默认禁用清单(DEFAULT_DISABLED_SETUPS)— 写在宪法里
    2. M8 自动判定 status='disabled' 的 setup(n≥30 且负期望)
    """
    disabled = set(DEFAULT_DISABLED_SETUPS)
    if db_path is None:
        return disabled
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT setup_type FROM setup_performance WHERE status='disabled'"
            ).fetchall()
            disabled.update(r[0] for r in rows)
        finally:
            conn.close()
    except sqlite3.OperationalError:
        # setup_performance 表尚未建,仅返回默认禁用清单
        pass
    return disabled


__all__ = [
    "ensure_table",
    "refresh_setup_performance",
    "get_disabled_setups",
]
