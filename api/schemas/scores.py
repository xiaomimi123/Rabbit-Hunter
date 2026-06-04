"""
交易分数相关 Pydantic 模型
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class TradeScoreV43Response(BaseModel):
    id: int
    created_at: str
    symbol: str
    structure_score: Optional[float]
    volatility_score: Optional[float]
    sentiment_score: Optional[float]
    manipulation_score: Optional[float]
    final_score: Optional[float]
    weights: Dict[str, Any]
    weights_version: Optional[str]
    decision_policy: Dict[str, Any]
    executed: bool
    reason: Optional[str]


class KillQueueItem(BaseModel):
    symbol: str
    price: Optional[float] = None
    change24h: Optional[float] = None
    changePercent: Optional[float] = None
    aiScore: float
    phase: Optional[str] = None
    phaseAge: Optional[str] = None
    ageInMinutes: Optional[int] = None
    reason: Optional[str] = None
    confidence: Optional[float] = None
    weights: Dict[str, Any] = {}
    technicalSignals: List[str] = []
    riskLevel: Optional[str] = None
    expectedMove: Optional[float] = None
    expectedMovePercent: Optional[float] = None
    volume24h: Optional[float] = None
    liquidity: Optional[str] = None
    timestamp: str
    lastUpdated: str


class KillQueueResponse(BaseModel):
    status: str
    code: int
    data: List[KillQueueItem]
    pagination: Dict[str, Any]
    metadata: Dict[str, Any]
