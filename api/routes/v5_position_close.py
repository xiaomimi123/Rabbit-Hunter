"""POST /api/v5/positions/{position_id}/close。

平 paper_trades(SHADOW)或 positions_v5(LIVE)。MVP 只支持 paper_trades —
LIVE 走 V5PositionManager.close_position 需要 broker 实例,前端 LIVE 单的
手动平仓后续单独做。
"""
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel


router = APIRouter(prefix="/api/v5", tags=["positions"])


class CloseRequest(BaseModel):
    exit_price: float
    exit_reason: str = "MANUAL_USER"


class CloseResponse(BaseModel):
    position_id: int
    status: str
    exit_price: float
    exit_reason: str


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


@router.post("/positions/{position_id}/close", response_model=CloseResponse)
async def close_position(
    position_id: int = Path(...),
    body: CloseRequest = ...,
) -> CloseResponse:
    db = _db()
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT status FROM paper_trades WHERE id=?", (position_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail=f"position {position_id} not found")
    if (row[0] or "").upper() == "CLOSED":
        raise HTTPException(status_code=409, detail=f"position {position_id} already CLOSED")

    from scripts.paper_position_manager import PaperPositionManager
    pm = PaperPositionManager(db_path=db)
    pm.close_position(position_id, exit_price=body.exit_price, exit_reason=body.exit_reason)

    # Reflection 入队(跟 v5_position_monitor 的 close 路径对齐)
    try:
        from scripts.local_db import enqueue_reflection
        enqueue_reflection(position_id, db_path=db)
    except Exception as e:
        print(f"[v5_position_close] reflection enqueue failed: {e}")

    return CloseResponse(
        position_id=position_id,
        status="CLOSED",
        exit_price=body.exit_price,
        exit_reason=body.exit_reason,
    )
