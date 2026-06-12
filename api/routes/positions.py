"""V5 持仓 API。"""
import os
from fastapi import APIRouter, Query

from api.schemas.positions import V5PositionResponse, V5PositionsResponse
from api.services.position_service import fetch_v5_positions, fetch_v5_paper_positions

router = APIRouter(prefix="/api/v5", tags=["positions"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


@router.get("/positions", response_model=V5PositionsResponse)
async def get_live_positions(status: str = Query("OPEN")):
    rows = fetch_v5_positions(_db(), status=status, limit=100)
    return V5PositionsResponse(data=rows)


@router.get("/paper-positions", response_model=V5PositionsResponse)
async def get_paper_positions(status: str = Query("OPEN")):
    """SHADOW 模式的纸面仓位 — 来自 paper_trades。"""
    rows = fetch_v5_paper_positions(_db(), status=status, limit=100)
    mapped = []
    for r in rows:
        mapped.append({
            "id": r["id"],
            "symbol": r["symbol"],
            "side": r["side"],
            "status": r["status"],
            "entry_price": r.get("entry_price"),
            "entry_time": r.get("entry_time"),
            "sl_price": r.get("stop_loss"),
            "tp_price": r.get("take_profit"),
            "size_usdt": r.get("position_size_usdt"),
            "leverage": r.get("leverage"),
            "target_close_at": r.get("target_close_at"),
            "extension_count": r.get("extension_count") or 0,
            "entry_rsi_15m": r.get("entry_rsi_15m"),
            "entry_macd_hist_15m": r.get("entry_macd_hist_15m"),
            "entry_rsi_4h": r.get("entry_rsi_4h"),
            "entry_atr_15m": r.get("entry_atr_15m"),
            "exit_price": r.get("exit_price"),
            "exit_time": r.get("exit_time"),
            "exit_reason": r.get("exit_reason"),
            "pnl_usdt": r.get("pnl"),
            "pnl_pct": r.get("pnl_percent"),
            "holding_minutes": (r.get("holding_hours") or 0) * 60,
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "strategy_id": r.get("strategy_id"),
        })
    return V5PositionsResponse(data=mapped)
