"""/api/v5/ai/status + /decisions"""
import os
import sqlite3
from fastapi import APIRouter

from api.schemas.v5_ai import (
    AIStatusResponse, AIDecisionItem, AIDecisionsResponse,
)
from scripts.ai.local_rag import rag_utilization_24h
from api.services.score_service import ensure_utc_iso


router = APIRouter(prefix="/api/v5", tags=["ai"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def _resolve_active_provider() -> tuple:
    """跟 v5_settings 同款逻辑。"""
    db = _db()
    try:
        conn = sqlite3.connect(db)
        try:
            row = conn.execute(
                "SELECT key, value FROM system_settings "
                "WHERE key IN ('deepseek_enabled', 'deepseek_api_key', "
                "             'openai_api_key') ORDER BY rowid DESC"
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        row = []
    state = {k: v for k, v in row}
    deepseek_enabled = (state.get("deepseek_enabled") or
                        os.environ.get("DEEPSEEK_ENABLED", "false")).lower() in ("1", "true")
    deepseek_key = state.get("deepseek_api_key") or os.environ.get("DEEPSEEK_API_KEY", "")
    openai_key = state.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")

    if deepseek_enabled and deepseek_key:
        return "deepseek", os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    if openai_key:
        return "openai", os.environ.get("OPENAI_TRADING_MODEL", "gpt-4o")
    return None, None


@router.get("/ai/status", response_model=AIStatusResponse)
async def get_ai_status() -> AIStatusResponse:
    db = _db()
    provider, chat_model = _resolve_active_provider()
    conn = sqlite3.connect(db)
    try:
        decisions_24h = conn.execute(
            "SELECT COUNT(*) FROM trade_scores_v5 "
            "WHERE should_trade=1 AND ai_reasoning IS NOT NULL "
            "  AND created_at >= datetime('now', '-24 hour')"
        ).fetchone()[0] or 0

        rag_in_db = conn.execute(
            "SELECT COUNT(*) FROM ai_training_data WHERE outcome IS NOT NULL"
        ).fetchone()[0] or 0
    finally:
        conn.close()

    util = rag_utilization_24h(db_path=db)

    return AIStatusResponse(
        provider=provider,
        chat_model=chat_model,
        healthy=(provider is not None),
        last_latency_ms=None,
        decisions_24h=int(decisions_24h),
        rag_utilization_24h=round(util, 3),
        rag_cases_in_db=int(rag_in_db),
    )


@router.get("/ai/decisions", response_model=AIDecisionsResponse)
async def get_ai_decisions(limit: int = 20) -> AIDecisionsResponse:
    db = _db()
    limit = max(1, min(200, limit))
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT id, created_at, symbol, side, should_trade, ai_confidence, "
            "       ai_reasoning "
            "  FROM trade_scores_v5 "
            " WHERE ai_reasoning IS NOT NULL "
            " ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()

    decisions = []
    for rid, created_at, symbol, side, should_trade, conf, reasoning in rows:
        top1 = None
        rag_count = 0
        if reasoning and "case1" in reasoning:
            import re
            m = re.search(r"distance=([0-9.]+)", reasoning)
            if m:
                try:
                    top1 = float(m.group(1))
                except ValueError:
                    pass
            rag_count = len(re.findall(r"case\d+:", reasoning))
        decisions.append(AIDecisionItem(
            id=rid,
            created_at=ensure_utc_iso(created_at) or created_at,
            symbol=symbol or "",
            side=side or "SHORT",
            execute=bool(should_trade),
            confidence=float(conf or 0.0),
            reasoning=(reasoning or "")[:200],
            top1_distance=top1,
            rag_case_count=rag_count,
        ))
    return AIDecisionsResponse(decisions=decisions)
