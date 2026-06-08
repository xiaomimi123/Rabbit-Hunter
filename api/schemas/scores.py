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
    # v0.5.x 修复:前端需要的 V4.3 四维原始评分(0-1)和综合分,
    # 之前 Pydantic 模型未声明这些字段导致 FastAPI 静默丢弃 → 前端显示 0.0
    final_score: Optional[float] = None
    structure_score: Optional[float] = None
    volatility_score: Optional[float] = None
    sentiment_score: Optional[float] = None
    manipulation_score: Optional[float] = None
    # V4.4 策略路由
    strategy_id: Optional[str] = None
    strategyId: Optional[str] = None
    side: Optional[str] = None
    strategy_score: Optional[float] = None
    # 决策结果
    should_trade: Optional[bool] = None
    block_reason: Optional[str] = None
    position_size_multiplier: Optional[float] = None
    decision_policy: Optional[Dict[str, Any]] = None
    features: Optional[Dict[str, Any]] = None
    # AI 决策细节
    ai_reasoning: Optional[str] = None
    ai_sl_multiplier: Optional[float] = None
    ai_tp_multiplier: Optional[float] = None
    # 已有字段
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
