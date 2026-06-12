"""V5 ChartPage K 线 + 事件 schema。"""
from typing import List, Optional, Literal
from pydantic import BaseModel


class Kline(BaseModel):
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class KlinesResponse(BaseModel):
    symbol: str
    interval: Literal["15m", "1h", "4h"]
    klines: List[Kline]


class SymbolEvent(BaseModel):
    event_type: Literal["entry", "exit", "extension"]
    side: Optional[Literal["LONG", "SHORT"]] = None
    price: float
    timestamp: str
    position_id: Optional[int] = None
    reasoning: Optional[str] = None
    rsi_15m: Optional[float] = None
    macd_hist_15m: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl_pct: Optional[float] = None


class SymbolEventsResponse(BaseModel):
    symbol: str
    events: List[SymbolEvent]
