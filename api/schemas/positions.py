"""
持仓相关 Pydantic 模型
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel


class PositionV43Response(BaseModel):
    # 前端期望的字段（驼峰命名）
    symbol: str
    entryPrice: float
    currentPrice: float
    atrStop: float
    takeProfit: Optional[float] = None
    leverage: float = 1.0
    size: float
    pnl: float
    pnlPercent: float
    status: str  # "SAFE" | "DANGER"
    side: str  # "LONG" | "SHORT"
    # 保留原始字段供兼容
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    position_size: Optional[float] = None
    stop_price: Optional[float] = None
    atr_k: Optional[float] = None
    phase: Optional[str] = None
    phase_age: Optional[int] = None
    pnl_percent: Optional[float] = None


class PositionsResponse(BaseModel):
    status: str
    code: int
    data: Dict[str, Any]


class TradeOpenRequest(BaseModel):
    symbol: str
    side: str  # "LONG" or "SHORT"
    quantity: float
    order_type: Optional[str] = "MARKET"
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class TradeCloseRequest(BaseModel):
    symbol: str
    quantity: Optional[float] = None
    order_type: Optional[str] = "MARKET"


class TradeResponse(BaseModel):
    success: bool
    order_id: Optional[str] = None
    symbol: str
    message: str
    error: Optional[str] = None
    timestamp: str
