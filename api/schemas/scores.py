"""V5 信号 + 漏斗 schema。"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class V5SignalItem(BaseModel):
    id: int
    symbol: str
    created_at: str
    delta_15m_pct: Optional[float] = None
    volume_24h_usdt: Optional[float] = None
    rsi_15m: Optional[float] = None
    macd_15m: Optional[float] = None
    macd_signal_15m: Optional[float] = None
    macd_hist_15m: Optional[float] = None
    macd_hist_prev_15m: Optional[float] = None
    rsi_4h: Optional[float] = None
    macd_hist_4h: Optional[float] = None
    atr_15m: Optional[float] = None
    current_price: Optional[float] = None
    should_trade: int = 0
    side: Optional[str] = None
    reasoning: Optional[str] = None
    block_reason: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_sl_multiplier: Optional[float] = None
    ai_tp_multiplier: Optional[float] = None
    ai_size_multiplier: Optional[float] = None
    ai_reasoning: Optional[str] = None
    entry_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    size_usdt: Optional[float] = None
    expected_rr: Optional[float] = None
    executed: int = 0
    position_id: Optional[int] = None


class V5SignalsResponse(BaseModel):
    status: str = "success"
    data: List[V5SignalItem]
    funnel: Dict[str, int]
