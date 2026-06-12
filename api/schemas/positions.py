"""V5 持仓 schema。"""
from typing import Optional, List
from pydantic import BaseModel


class V5PositionResponse(BaseModel):
    id: int
    symbol: str
    side: str
    status: str
    entry_price: Optional[float] = None
    entry_time: Optional[str] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    size_usdt: Optional[float] = None
    leverage: Optional[int] = None
    position_size_coins: Optional[float] = None
    target_close_at: Optional[str] = None
    extension_count: int = 0
    entry_rsi_15m: Optional[float] = None
    entry_macd_hist_15m: Optional[float] = None
    entry_rsi_4h: Optional[float] = None
    entry_atr_15m: Optional[float] = None
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    exit_reason: Optional[str] = None
    pnl_usdt: Optional[float] = None
    pnl_pct: Optional[float] = None
    holding_minutes: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    strategy_id: Optional[str] = None


class V5PositionsResponse(BaseModel):
    status: str = "success"
    data: List[V5PositionResponse]
