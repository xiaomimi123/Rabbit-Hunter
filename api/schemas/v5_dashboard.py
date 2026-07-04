"""V5 Dashboard summary schema。"""
from typing import Dict, List, Optional
from pydantic import BaseModel


class DashboardClosedTrade(BaseModel):
    id: int
    symbol: str
    side: Optional[str] = None
    status: str
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    pnl_usdt: Optional[float] = None
    pnl_pct: Optional[float] = None
    source: str  # "paper" | "live"


class DashboardErrors(BaseModel):
    signals: Optional[str] = None
    paper_history: Optional[str] = None
    live_history: Optional[str] = None
    paper_active: Optional[str] = None
    live_active: Optional[str] = None


class DashboardSummaryResponse(BaseModel):
    signals_24h: int
    signals_passed_and: int
    signals_executed: int
    signals_block_counts: Dict[str, int]
    win_rate_24h: float
    pnl_total_usdt: float
    pnl_total_pct: float
    avg_holding_minutes: float
    active_count: int
    closed_24h: List[DashboardClosedTrade]
    errors: Optional[DashboardErrors] = None
