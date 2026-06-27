"""V5 Trader KPI endpoint — 交易员中控 dashboard 用。

返回:
  - 滚动指标 (Profit Factor / Sharpe / MaxDD / Win% / Total R / AvgR / N)
  - 风控宪法 7 条铁律实时状态
  - AI 健康度 (最近 24h 真实推理 vs 兜底比例)

依据 docs/risk-constitution-audit.md 的宪法 7 条铁律。
"""
from __future__ import annotations

import math
import os
import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel


router = APIRouter(prefix="/api/v5", tags=["dashboard"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


# ─────────────────────────────────────────────────────────────
# Pydantic 模型
# ─────────────────────────────────────────────────────────────


class RollingKpi(BaseModel):
    n_trades: int
    win_rate: float
    profit_factor: Optional[float]
    total_r: float
    avg_r: float
    max_dd_r: float
    sharpe: Optional[float]


class Rule2SLAttached(BaseModel):
    """规则 2:今日开仓必挂止损 — 今日开仓数 vs 实挂 SL 数。"""
    today_opens: int
    today_sl_attached: int
    ok: bool


class Rule3DailyDrawdown(BaseModel):
    """规则 3:日内 -3% 锁仓 — 今日累计 R / 限额。"""
    today_pnl_usdt: float
    today_pnl_pct: float
    limit_pct: float
    lockdown_triggered: bool
    distance_pct: float


class Rule5SLRatio(BaseModel):
    """规则 5:今日开仓 SL/ATR ratio 是否落在 [1.5, 2.2]。"""
    today_opens: int
    today_in_range: int
    ok: bool


class ConstitutionStatus(BaseModel):
    """7 条铁律实时状态。每条 .ok 是布尔,辅以详情。"""
    rule_1_risk_cap_ok: bool          # 单笔风险 ≤ 1% (config 实测)
    rule_2_sl_attached: Rule2SLAttached
    rule_3_daily_dd: Rule3DailyDrawdown
    rule_4_leverage_in_range: bool    # 当前 v5_leverage param 是否在 [3,5]
    rule_4_leverage_value: int
    rule_5_sl_atr_ratio: Rule5SLRatio
    rule_6_short_disabled: bool       # ENABLE_SHORT_TRADING is False
    rule_6_today_blocked: int         # 今日被新闸门拦的 SHORT 数
    rule_7_killer_disabled: bool      # 杀手 setup 在禁用名单
    rule_7_today_blocked: int         # 今日被 IRONLAW:SETUP_DISABLED 拦的数


class AIHealth(BaseModel):
    """AI 健康度 (last N hours)。"""
    window_hours: int
    total_ai_calls: int               # ai_reasoning 非空数
    real_responses: int               # 既非 'AI unavailable' 也非 'FAILURE_MODE_MATCH'
    fallback_passthrough: int         # 'AI unavailable%'
    failure_taxonomy_rejects: int     # 'FAILURE_MODE_MATCH%'


class TraderKpi(BaseModel):
    window_days: int
    generated_at: str
    rolling: RollingKpi
    constitution: ConstitutionStatus
    ai_health: AIHealth


# ─────────────────────────────────────────────────────────────
# 计算 helpers
# ─────────────────────────────────────────────────────────────


def _compute_r(pnl: float, position_size_usdt: float, leverage: float,
               entry_price: float, stop_loss: float) -> Optional[float]:
    """1R = SL 触发时的 USDT 损失。R = pnl / risk_usdt。"""
    if not (position_size_usdt and leverage and entry_price and stop_loss):
        return None
    if entry_price <= 0:
        return None
    sl_dist_pct = abs(entry_price - stop_loss) / entry_price
    if sl_dist_pct <= 0:
        return None
    risk_usdt = position_size_usdt * leverage * sl_dist_pct
    if risk_usdt <= 0:
        return None
    return pnl / risk_usdt


def _rolling_kpi_from_paper(db_path: str, window_days: int) -> RollingKpi:
    """从 paper_trades 窗口内的 CLOSED 交易计算滚动 KPI。"""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"""SELECT pnl, position_size_usdt, leverage, entry_price, stop_loss
                FROM paper_trades
                WHERE status='CLOSED' AND exit_time >= datetime('now', '-{window_days} days')
                ORDER BY exit_time""",
        ).fetchall()
    finally:
        conn.close()

    rs: List[float] = []
    for pnl, size, lev, ent, sl in rows:
        r = _compute_r(pnl, size, lev, ent, sl)
        if r is not None:
            rs.append(r)

    if not rs:
        return RollingKpi(
            n_trades=0, win_rate=0.0, profit_factor=None,
            total_r=0.0, avg_r=0.0, max_dd_r=0.0, sharpe=None,
        )

    n = len(rs)
    wins = sum(1 for r in rs if r > 0)
    pos = sum(r for r in rs if r > 0)
    neg = sum(abs(r) for r in rs if r < 0)
    pf = (pos / neg) if neg > 0 else None
    total = sum(rs)
    avg = total / n

    # Max DD on cumulative R curve
    cum, peak, mdd = 0.0, 0.0, 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        if cum - peak < mdd:
            mdd = cum - peak

    # Sharpe = mean / stdev × sqrt(n);n<2 退回 None
    if n >= 2:
        mean = total / n
        var = sum((r - mean) ** 2 for r in rs) / (n - 1)
        std = math.sqrt(var) if var > 0 else 0.0
        sharpe = (mean / std) * math.sqrt(n) if std > 0 else None
    else:
        sharpe = None

    return RollingKpi(
        n_trades=n,
        win_rate=wins / n,
        profit_factor=pf,
        total_r=total,
        avg_r=avg,
        max_dd_r=mdd,
        sharpe=sharpe,
    )


def _today_start_iso() -> str:
    """SQLite-style: today UTC 0 点。"""
    return "datetime('now', 'start of day')"


def _constitution_status(db_path: str) -> ConstitutionStatus:
    """7 条铁律实时快照。"""
    from scripts.config import get_config
    from scripts.risk_constitution import (
        DAILY_DRAWDOWN_LIMIT_PCT,
        MAX_PER_TRADE_RISK_PCT,
        FINAL_SL_ATR_RATIO_MAX,
        FINAL_SL_ATR_RATIO_MIN,
    )
    cfg = get_config(reload=True)

    # 规则 1: config 的 risk_per_trade ≤ 0.01 (tier 0 上限)
    rule_1_ok = cfg.risk_per_trade <= MAX_PER_TRADE_RISK_PCT + 1e-9

    conn = sqlite3.connect(db_path)
    try:
        # 规则 2: 今日开仓 + stop_loss 非空
        today_opens, today_attached = conn.execute(
            f"""SELECT
                  COUNT(*),
                  SUM(CASE WHEN stop_loss IS NOT NULL AND stop_loss > 0 THEN 1 ELSE 0 END)
                FROM paper_trades
                WHERE entry_time >= {_today_start_iso()}""",
        ).fetchone()
        today_opens = int(today_opens or 0)
        today_attached = int(today_attached or 0)
        rule_2 = Rule2SLAttached(
            today_opens=today_opens,
            today_sl_attached=today_attached,
            ok=(today_opens == today_attached),
        )

        # 规则 3: 今日累计 PnL vs 阈值
        today_pnl_usdt = float(conn.execute(
            f"""SELECT COALESCE(SUM(pnl), 0)
                FROM paper_trades
                WHERE status='CLOSED' AND exit_time >= {_today_start_iso()}""",
        ).fetchone()[0] or 0.0)
        initial_balance = float(os.environ.get("PAPER_INITIAL_BALANCE_USDT", "10000") or 10000)
        today_pnl_pct = today_pnl_usdt / initial_balance if initial_balance > 0 else 0.0
        rule_3 = Rule3DailyDrawdown(
            today_pnl_usdt=today_pnl_usdt,
            today_pnl_pct=today_pnl_pct,
            limit_pct=-DAILY_DRAWDOWN_LIMIT_PCT,
            lockdown_triggered=today_pnl_pct <= -DAILY_DRAWDOWN_LIMIT_PCT,
            distance_pct=today_pnl_pct - (-DAILY_DRAWDOWN_LIMIT_PCT),
        )

        # 规则 5: 今日开仓 SL/ATR ratio 落在 [1.5, 2.2]
        rule_5_rows = conn.execute(
            f"""SELECT entry_price, stop_loss, entry_atr_15m
                FROM paper_trades
                WHERE entry_time >= {_today_start_iso()}
                  AND entry_atr_15m IS NOT NULL AND entry_atr_15m > 0""",
        ).fetchall()
        in_range = 0
        for ent, sl, atr in rule_5_rows:
            if not (ent and sl and atr and atr > 0):
                continue
            ratio = abs(ent - sl) / atr
            if FINAL_SL_ATR_RATIO_MIN - 1e-9 <= ratio <= FINAL_SL_ATR_RATIO_MAX + 1e-9:
                in_range += 1
        rule_5 = Rule5SLRatio(
            today_opens=len(rule_5_rows),
            today_in_range=in_range,
            ok=(len(rule_5_rows) == in_range),
        )

        # 规则 6: 今日被 SHORT_DISABLED 拦截数
        rule_6_blocked = int(conn.execute(
            f"""SELECT COUNT(*) FROM trade_scores_v5
                WHERE created_at >= {_today_start_iso()}
                  AND block_reason = 'SHORT_DISABLED'""",
        ).fetchone()[0] or 0)

        # 规则 7: 今日被 IRONLAW:SETUP_DISABLED 拦截数
        rule_7_blocked = int(conn.execute(
            f"""SELECT COUNT(*) FROM trade_scores_v5
                WHERE created_at >= {_today_start_iso()}
                  AND block_reason LIKE 'IRONLAW:SETUP_DISABLED%'""",
        ).fetchone()[0] or 0)

    finally:
        conn.close()

    return ConstitutionStatus(
        rule_1_risk_cap_ok=rule_1_ok,
        rule_2_sl_attached=rule_2,
        rule_3_daily_dd=rule_3,
        rule_4_leverage_in_range=(3 <= cfg.binance_leverage <= 5),
        rule_4_leverage_value=int(cfg.binance_leverage),
        rule_5_sl_atr_ratio=rule_5,
        rule_6_short_disabled=(cfg.enable_short_trading is False),
        rule_6_today_blocked=rule_6_blocked,
        rule_7_killer_disabled=True,    # 由 DEFAULT_DISABLED_SETUPS 静态保证
        rule_7_today_blocked=rule_7_blocked,
    )


def _ai_health(db_path: str, window_hours: int) -> AIHealth:
    """最近 N 小时 AI 调用真实/兜底分布。"""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            f"""SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN ai_reasoning LIKE 'AI unavailable%' THEN 1 ELSE 0 END) AS fallback,
                  SUM(CASE WHEN ai_reasoning LIKE 'FAILURE_MODE_MATCH%' THEN 1 ELSE 0 END) AS taxonomy
                FROM trade_scores_v5
                WHERE created_at >= datetime('now', '-{window_hours} hours')
                  AND ai_reasoning IS NOT NULL""",
        ).fetchone()
    finally:
        conn.close()

    total = int(row[0] or 0)
    fallback = int(row[1] or 0)
    taxonomy = int(row[2] or 0)
    real = total - fallback - taxonomy
    return AIHealth(
        window_hours=window_hours,
        total_ai_calls=total,
        real_responses=max(0, real),
        fallback_passthrough=fallback,
        failure_taxonomy_rejects=taxonomy,
    )


# ─────────────────────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────────────────────


@router.get("/dashboard/trader-kpi", response_model=TraderKpi)
async def get_trader_kpi(
    window_days: int = Query(30, ge=1, le=365),
    ai_window_hours: int = Query(24, ge=1, le=168),
) -> TraderKpi:
    """交易员中控 KPI:滚动 + 宪法 + AI 健康度。"""
    from datetime import datetime, timezone
    db_path = _db()
    return TraderKpi(
        window_days=window_days,
        generated_at=datetime.now(timezone.utc).isoformat(),
        rolling=_rolling_kpi_from_paper(db_path, window_days),
        constitution=_constitution_status(db_path),
        ai_health=_ai_health(db_path, ai_window_hours),
    )
