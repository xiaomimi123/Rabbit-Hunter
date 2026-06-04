"""
权重相关 Pydantic 模型
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class V43WeightsResponse(BaseModel):
    weights: Dict[str, float]
    weights_version: str
    constraints: Dict[str, List[float]]
    applied: bool
    created_at: Optional[str]


class V43WeightHistoryResponse(BaseModel):
    id: int
    created_at: str
    updated_at: Optional[str] = None  # 添加更新时间字段
    weights: Dict[str, float]
    weights_version: str
    performance_metrics: Dict[str, Any]
    opportunity_density_score: Optional[float]
    ai_reason: Optional[str]
    applied: bool
