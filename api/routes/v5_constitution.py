"""M3 宪法 + M8 setup_performance 暴露给前端。

文档 §5 + §10:让前端能看到铁律层数值 + 自动剪枝结果。
"""
import os
import sqlite3
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(prefix="/api/v5", tags=["constitution"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


class ConstitutionSnapshot(BaseModel):
    """M3 风控宪法静态值。"""
    max_per_trade_risk_pct: float
    daily_drawdown_limit_pct: float
    min_rr: float
    min_liq_to_sl_distance_ratio: float
    final_sl_atr_ratio_min: float
    final_sl_atr_ratio_max: float
    evolution_ai_sl_mult_min: float
    evolution_ai_sl_mult_max: float
    evolution_size_mult_min: float
    evolution_size_mult_max: float
    min_sample_size_for_decision: int
    default_disabled_setups: List[str]


class IronlawLiveState(BaseModel):
    """今日运行时风险状态。"""
    today_realized_pnl: float
    daily_dd_remaining_usdt: float
    daily_dd_triggered: bool
    open_positions: int
    max_concurrent: int


class SetupPerfRow(BaseModel):
    setup_type: str
    sample_count: int
    win_count: int
    loss_count: int
    scratch_count: int
    avg_realized_r: Optional[float]
    total_realized_r: Optional[float]
    status: str
    disabled_reason: Optional[str]
    updated_at: str


class SetupPerfResponse(BaseModel):
    rows: List[SetupPerfRow]


@router.get("/constitution", response_model=ConstitutionSnapshot)
async def get_constitution() -> ConstitutionSnapshot:
    """M3 静态宪法值。"""
    from scripts.risk_constitution import (
        MAX_PER_TRADE_RISK_PCT, DAILY_DRAWDOWN_LIMIT_PCT, MIN_RR,
        MIN_LIQ_TO_SL_DISTANCE_RATIO,
        FINAL_SL_ATR_RATIO_MIN, FINAL_SL_ATR_RATIO_MAX,
        EVOLUTION_AI_SL_MULT_MIN, EVOLUTION_AI_SL_MULT_MAX,
        EVOLUTION_SIZE_MULT_MIN, EVOLUTION_SIZE_MULT_MAX,
        MIN_SAMPLE_SIZE_FOR_DECISION, DEFAULT_DISABLED_SETUPS,
    )
    return ConstitutionSnapshot(
        max_per_trade_risk_pct=MAX_PER_TRADE_RISK_PCT,
        daily_drawdown_limit_pct=DAILY_DRAWDOWN_LIMIT_PCT,
        min_rr=MIN_RR,
        min_liq_to_sl_distance_ratio=MIN_LIQ_TO_SL_DISTANCE_RATIO,
        final_sl_atr_ratio_min=FINAL_SL_ATR_RATIO_MIN,
        final_sl_atr_ratio_max=FINAL_SL_ATR_RATIO_MAX,
        evolution_ai_sl_mult_min=EVOLUTION_AI_SL_MULT_MIN,
        evolution_ai_sl_mult_max=EVOLUTION_AI_SL_MULT_MAX,
        evolution_size_mult_min=EVOLUTION_SIZE_MULT_MIN,
        evolution_size_mult_max=EVOLUTION_SIZE_MULT_MAX,
        min_sample_size_for_decision=MIN_SAMPLE_SIZE_FOR_DECISION,
        default_disabled_setups=sorted(DEFAULT_DISABLED_SETUPS),
    )


@router.get("/ironlaw-state", response_model=IronlawLiveState)
async def get_ironlaw_state() -> IronlawLiveState:
    """今日的运行时风控状态:已实现 PnL + 剩余日 DD 预算 + 活仓占用。"""
    from scripts.risk_gates import get_today_realized_pnl
    from scripts.risk_constitution import DAILY_DRAWDOWN_LIMIT_PCT

    db_path = _db()
    today_pnl = get_today_realized_pnl(db_path)

    # 假定本金 (env > default 10000)
    equity = float(os.environ.get("PAPER_INITIAL_BALANCE_USDT", "10000") or 10000)
    dd_limit = equity * DAILY_DRAWDOWN_LIMIT_PCT
    dd_remaining = max(0.0, dd_limit + today_pnl)
    dd_triggered = -today_pnl >= dd_limit - 1e-9

    conn = sqlite3.connect(db_path)
    try:
        n_open = conn.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'"
        ).fetchone()[0] or 0
    finally:
        conn.close()

    return IronlawLiveState(
        today_realized_pnl=today_pnl,
        daily_dd_remaining_usdt=dd_remaining,
        daily_dd_triggered=dd_triggered,
        open_positions=int(n_open),
        max_concurrent=3,
    )


@router.get("/setup-performance", response_model=SetupPerfResponse)
async def get_setup_performance() -> SetupPerfResponse:
    """M8 实时 setup_performance 聚合,按 sample_count 降序。"""
    from scripts.setup_performance import ensure_table

    db_path = _db()
    ensure_table(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT setup_type, sample_count, win_count, loss_count,
                   scratch_count, avg_realized_r, total_realized_r,
                   status, disabled_reason, updated_at
              FROM setup_performance
             ORDER BY sample_count DESC
        """).fetchall()
    finally:
        conn.close()

    return SetupPerfResponse(rows=[SetupPerfRow(**dict(r)) for r in rows])
