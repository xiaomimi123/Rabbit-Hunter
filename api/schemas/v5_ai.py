"""V5 AI 状态 + 最近决策 schema。"""
from typing import List, Optional, Literal
from pydantic import BaseModel


class AIStatusResponse(BaseModel):
    provider: Optional[Literal["openai", "deepseek"]]
    chat_model: Optional[str]
    healthy: bool
    last_latency_ms: Optional[int] = None
    decisions_24h: int
    rag_utilization_24h: float
    rag_cases_in_db: int


class AIDecisionItem(BaseModel):
    id: int
    created_at: str
    symbol: str
    side: Literal["LONG", "SHORT"]
    execute: bool
    confidence: float
    reasoning: str
    top1_distance: Optional[float] = None
    rag_case_count: int = 0


class AIDecisionsResponse(BaseModel):
    decisions: List[AIDecisionItem]
