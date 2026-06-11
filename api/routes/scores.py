"""V5 信号 + 漏斗 API。"""
import os
from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas.scores import V5SignalItem, V5SignalsResponse
from scripts.v5_signal_manager import V5SignalManager

router = APIRouter(prefix="/api/v5", tags=["signals"])


def _signal_manager() -> V5SignalManager:
    db = os.environ.get("DB_PATH", "data/rabbit_hunter.db")
    return V5SignalManager(db_path=db)


@router.get("/signals", response_model=V5SignalsResponse)
async def get_signals(
    limit: int = Query(50, ge=1, le=200),
    only_executed: bool = Query(False),
    only_should_trade: bool = Query(False),
    funnel_hours: int = Query(1, ge=1, le=24),
):
    sm = _signal_manager()
    rows = sm.list_signals(limit=limit,
                           only_executed=only_executed,
                           only_should_trade=only_should_trade)
    funnel = sm.funnel_stats(since_hours=funnel_hours)
    return V5SignalsResponse(data=rows, funnel=funnel)
