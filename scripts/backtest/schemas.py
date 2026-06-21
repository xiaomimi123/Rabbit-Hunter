"""Schemas for backtest entries + aggregate summary.

All pure dataclasses. SetupStats.from_entries() encapsulates the
win-rate / median / total-R math so the reporter stays declarative.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Dict, List, Literal, Optional


@dataclass
class BacktestEntry:
    symbol: str
    side: Literal["LONG", "SHORT"]
    setup_type: str
    entry_time: str                  # ISO 8601 with timezone
    entry_price: float
    sl_price: float
    tp_price: float
    exit_time: Optional[str]
    exit_price: Optional[float]
    exit_reason: Optional[Literal["SL_HIT", "TP_HIT", "HORIZON_TIMEOUT"]]
    realized_r: Optional[float]      # gross R (扣前)
    holding_minutes: Optional[int]
    funding_z_at_entry: Optional[float]
    rsi_15m_at_entry: float
    macd_hist_15m_at_entry: float
    # M6 扣成本(可空 — 旧报告兼容)
    net_realized_r: Optional[float] = None
    fee_cost_r: Optional[float] = None
    slippage_cost_r: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SetupStats:
    n: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_r: float = 0.0
    avg_r: float = 0.0
    median_r: float = 0.0
    best_r: float = 0.0
    worst_r: float = 0.0

    @classmethod
    def from_entries(cls, entries: List[BacktestEntry]) -> "SetupStats":
        closed = [e for e in entries if e.realized_r is not None]
        if not closed:
            return cls()
        rs = sorted(e.realized_r for e in closed)
        wins = sum(1 for r in rs if r > 0)
        losses = sum(1 for r in rs if r < 0)
        n = len(rs)
        total = sum(rs)
        avg = total / n
        if n % 2 == 1:
            median = rs[n // 2]
        else:
            median = (rs[n // 2 - 1] + rs[n // 2]) / 2
        return cls(
            n=n, wins=wins, losses=losses,
            win_rate=wins / n if n else 0.0,
            total_r=total,
            avg_r=avg,
            median_r=median,
            best_r=rs[-1],
            worst_r=rs[0],
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BacktestSummary:
    period_start: str
    period_end: str
    total_signals: int
    total_passed: int
    total_entries: int
    total_closed: int
    by_setup_type: Dict[str, SetupStats] = field(default_factory=dict)
    by_side: Dict[str, SetupStats] = field(default_factory=dict)
    by_symbol: Dict[str, SetupStats] = field(default_factory=dict)
    overall: SetupStats = field(default_factory=SetupStats)
    max_concurrent_reached: int = 0
    profit_factor: Optional[float] = None
    max_drawdown_r: float = 0.0
    # M6 扣成本后(net)对照
    overall_net: Optional[SetupStats] = None
    profit_factor_net: Optional[float] = None
    max_drawdown_r_net: Optional[float] = None
    by_setup_type_net: Dict[str, SetupStats] = field(default_factory=dict)
    cost_config: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_signals": self.total_signals,
            "total_passed": self.total_passed,
            "total_entries": self.total_entries,
            "total_closed": self.total_closed,
            "by_setup_type": {k: v.to_dict() for k, v in self.by_setup_type.items()},
            "by_side": {k: v.to_dict() for k, v in self.by_side.items()},
            "by_symbol": {k: v.to_dict() for k, v in self.by_symbol.items()},
            "overall": self.overall.to_dict(),
            "max_concurrent_reached": self.max_concurrent_reached,
            "profit_factor": self.profit_factor,
            "max_drawdown_r": self.max_drawdown_r,
            "overall_net": self.overall_net.to_dict() if self.overall_net else None,
            "profit_factor_net": self.profit_factor_net,
            "max_drawdown_r_net": self.max_drawdown_r_net,
            "by_setup_type_net": {k: v.to_dict() for k, v in self.by_setup_type_net.items()},
            "cost_config": self.cost_config,
        }
