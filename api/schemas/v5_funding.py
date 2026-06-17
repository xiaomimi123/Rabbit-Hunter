"""V6 funding rate API schemas."""
from typing import List, Optional

from pydantic import BaseModel


class FundingZScoreItem(BaseModel):
    symbol: str
    computed_at: str
    current_funding_rate: float
    annualized_rate_pct: float
    mean_30d: Optional[float]
    std_30d: Optional[float]
    zscore_30d: Optional[float]
    sample_size_30d: int
    is_extreme: bool
    extreme_direction: Optional[str]


class FundingStatusResponse(BaseModel):
    status: str = "success"
    data: List[FundingZScoreItem]


class FundingHistoryItem(BaseModel):
    funding_time: str
    funding_rate: float
    annualized_rate: float
    source: str


class FundingHistoryResponse(BaseModel):
    status: str = "success"
    symbol: str
    data: List[FundingHistoryItem]
