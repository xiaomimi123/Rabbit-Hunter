"""V5 Reflection API — list reflections joined with paper_trade summary."""
import os
import sqlite3

from fastapi import APIRouter, Query

from api.schemas.v5_reflection import (
    ReflectionRecord, ReflectionsResponse,
    FailureMode, FailureTaxonomyResponse,
)


router = APIRouter(prefix="/api/v5", tags=["reflection"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


@router.get("/reflections", response_model=ReflectionsResponse)
async def list_reflections(limit: int = Query(20, ge=1, le=200)) -> ReflectionsResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT r.*, p.symbol, p.side, p.entry_price, p.exit_price,
                   p.exit_reason, p.pnl_percent
              FROM reflections r
              LEFT JOIN paper_trades p ON p.id = r.paper_trade_id
             ORDER BY r.id DESC
             LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()

    data = []
    for row in rows:
        d = dict(row)
        # 把 SQLite int(0/1) 转回 bool 给 frontend
        if d.get("is_in_predicted_failure_mode") is not None:
            d["is_in_predicted_failure_mode"] = bool(d["is_in_predicted_failure_mode"])
        # pnl_percent → pnl_pct
        d["pnl_pct"] = d.pop("pnl_percent", None)
        data.append(ReflectionRecord(**d))
    return ReflectionsResponse(data=data)


@router.get("/failure-taxonomy", response_model=FailureTaxonomyResponse)
async def list_failure_taxonomy() -> FailureTaxonomyResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT t.key, t.label_zh, t.label_en, t.description,
                   t.detection_rule, t.is_active, t.avg_loss_pct,
                   t.seeded, t.approved_by, t.last_seen_at,
                   (SELECT COUNT(*) FROM reflections r
                      WHERE r.failure_mode_key = t.key) AS sample_count
              FROM failure_taxonomy t
             ORDER BY sample_count DESC, t.key
        """).fetchall()
    finally:
        conn.close()
    return FailureTaxonomyResponse(data=[
        FailureMode(
            key=r["key"], label_zh=r["label_zh"], label_en=r["label_en"],
            description=r["description"], detection_rule=r["detection_rule"],
            is_active=bool(r["is_active"]),
            sample_count=r["sample_count"], avg_loss_pct=r["avg_loss_pct"],
            last_seen_at=r["last_seen_at"], seeded=bool(r["seeded"]),
            approved_by=r["approved_by"],
        )
        for r in rows
    ])
