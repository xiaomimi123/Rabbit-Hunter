"""V5 Reflection API — list reflections joined with paper_trade summary."""
import os
import sqlite3

from fastapi import APIRouter, HTTPException, Path, Query

from api.schemas.v5_reflection import (
    ReflectionRecord, ReflectionsResponse,
    FailureMode, FailureTaxonomyResponse,
    SetupPerformanceItem, SetupPerformanceResponse,
    SizingRecommendation, SizingRecommendationsResponse,
    SizingDecisionRequest, CalibrationPoint, CalibrationResponse,
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


@router.get("/setup-performance", response_model=SetupPerformanceResponse)
async def list_setup_performance(days: int = Query(7, ge=1, le=90)) -> SetupPerformanceResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT date, setup_type, sample_count, win_count, loss_count,
                   win_rate, avg_realized_r, expectancy, top_failure_mode
              FROM setup_performance_daily
             WHERE date >= date('now', '-' || ? || ' days')
             ORDER BY date DESC, sample_count DESC
        """, (days,)).fetchall()
    finally:
        conn.close()
    return SetupPerformanceResponse(data=[SetupPerformanceItem(**dict(r)) for r in rows])


@router.get("/sizing-recommendations", response_model=SizingRecommendationsResponse)
async def list_sizing_recommendations(status: str = Query("pending")) -> SizingRecommendationsResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT id, setup_type, proposed_at, current_size_multiplier,
                   recommended_size_multiplier, confidence_score, rationale,
                   sample_count_30d, sample_count_60d, sample_count_90d,
                   kelly_f_30d, kelly_f_60d, kelly_f_90d, status
              FROM position_sizing_recommendations
             WHERE status = ?
             ORDER BY id DESC
        """, (status,)).fetchall()
    finally:
        conn.close()
    return SizingRecommendationsResponse(
        data=[SizingRecommendation(**dict(r)) for r in rows]
    )


@router.patch("/sizing-recommendations/{rec_id}")
async def decide_sizing_recommendation(
    rec_id: int = Path(...),
    body: SizingDecisionRequest = ...,
):
    new_status = {"approve": "approved", "reject": "rejected",
                  "modify": "modified"}[body.decision]
    conn = sqlite3.connect(_db())
    try:
        cur = conn.execute(
            "UPDATE position_sizing_recommendations "
            "SET status=?, user_decision_at=datetime('now'), "
            "    user_decision_note=?, user_modified_value=? "
            "WHERE id=? AND status='pending'",
            (new_status, body.note, body.modified_value, rec_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="recommendation not found or not pending")
    finally:
        conn.close()
    return {"status": "success", "rec_id": rec_id, "new_status": new_status}


@router.get("/confidence-calibration", response_model=CalibrationResponse)
async def list_calibration() -> CalibrationResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT ai_model, confidence_bucket, predicted_win_rate, "
            "       actual_win_rate, sample_count, calibration_multiplier "
            "FROM ai_confidence_calibration "
            "ORDER BY ai_model, confidence_bucket"
        ).fetchall()
    finally:
        conn.close()
    return CalibrationResponse(data=[CalibrationPoint(**dict(r)) for r in rows])
