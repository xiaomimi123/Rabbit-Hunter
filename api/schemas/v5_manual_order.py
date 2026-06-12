"""V5 手动模拟开单 schema。"""
from typing import List, Optional, Literal
from pydantic import BaseModel


class ManualOrderPreviewRequest(BaseModel):
    symbol: str
    side: Optional[Literal["LONG", "SHORT"]] = None
    size_usdt: float = 15.0


class ManualOrderDecisionSnapshot(BaseModel):
    should_trade: bool
    side: Optional[Literal["LONG", "SHORT"]]
    reasoning: str
    block_reason: Optional[str] = None


class ManualOrderRagCase(BaseModel):
    entry_rsi_15m: float
    entry_macd_hist_15m: float
    outcome: Literal["WIN", "LOSS", "FLAT"]
    pnl_pct: float
    exit_reason: str
    distance: float


class ManualOrderPreviewResponse(BaseModel):
    symbol: str
    side: Literal["LONG", "SHORT"]
    current_price: float
    indicators: dict
    decision: ManualOrderDecisionSnapshot
    risk_plan: dict
    ai_result: dict
    rag_cases: List[ManualOrderRagCase]
    rag_summary: Optional[str] = None


class ManualOrderExecuteRequest(BaseModel):
    symbol: str
    side: Literal["LONG", "SHORT"]
    size_usdt: float = 15.0
    sl_multiplier: float = 1.0
    tp_multiplier: float = 1.0
    size_multiplier: float = 1.0


class ManualOrderExecuteResponse(BaseModel):
    position_id: int
    symbol: str
    side: Literal["LONG", "SHORT"]
    entry_price: float
    sl_price: float
    tp_price: float
    size_usdt: float
    strategy_id: str
