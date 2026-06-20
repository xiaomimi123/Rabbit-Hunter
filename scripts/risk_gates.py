"""M3 铁律层硬断言。

所有 gate_* 函数在违规时 raise IronlawViolation。
调用方应捕获该异常并写 block_reason 拒单,不应吞掉。

依据:Rabbit-Hunter 完整开发设计文档 v1.0 §5(M3)、§7(M5)、§15(全局 KPI)。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from scripts.risk_constitution import (
    MAX_PER_TRADE_RISK_PCT,
    DAILY_DRAWDOWN_LIMIT_PCT,
    MIN_RR,
    MIN_LIQ_TO_SL_DISTANCE_RATIO,
    EVOLUTION_AI_SL_MULT_MIN,
    EVOLUTION_AI_SL_MULT_MAX,
    EVOLUTION_SIZE_MULT_MIN,
    EVOLUTION_SIZE_MULT_MAX,
    EVOLUTION_TP_MULT_MIN,
    EVOLUTION_TP_MULT_MAX,
    FINAL_SL_ATR_RATIO_MIN,
    FINAL_SL_ATR_RATIO_MAX,
    DEFAULT_DISABLED_SETUPS,
)


class IronlawViolation(Exception):
    """铁律层硬异常。捕获后须写 block_reason 拒单。

    异常 message 形如 `KIND: human-readable-detail` —— KIND 用于 block_reason 落库。
    """

    def __init__(self, kind: str, detail: str):
        self.kind = kind
        self.detail = detail
        super().__init__(f"{kind}: {detail}")


# ─────────────────────────────────────────────────────────────
# 单笔风险 / 强平距 / SL 必挂 / RR 下限
# ─────────────────────────────────────────────────────────────


def gate_per_trade_risk(
    *,
    equity_usdt: float,
    planned_loss_usdt: float,
    cap_pct: Optional[float] = None,
) -> None:
    """单笔最大风险 ≤ cap_pct × 本金。

    cap_pct 留 None 时按资格层 (tier-aware) 解析:小本金 tier 0 = 1%,大本金 tier 1 = 1.5%。
    调用方若已用资格层算了 risk_pct,应原样传入,确保 plan() 和 gate 同一刻度。
    """
    from scripts.risk_constitution import resolve_risk_pct_for_equity

    if equity_usdt <= 0:
        raise IronlawViolation("BAD_EQUITY", f"equity must be > 0, got {equity_usdt}")
    if cap_pct is None:
        cap_pct = resolve_risk_pct_for_equity(equity_usdt)
    cap = equity_usdt * cap_pct
    if planned_loss_usdt > cap + 1e-9:
        raise IronlawViolation(
            "PER_TRADE_RISK_EXCEEDED",
            f"planned loss {planned_loss_usdt:.2f} > cap {cap:.2f} "
            f"(= {cap_pct*100:.2f}% of {equity_usdt:.2f})",
        )


def gate_daily_drawdown(*, equity_usdt: float, today_realized_pnl: float) -> None:
    """单日已实现亏损 ≥ DAILY_DRAWDOWN_LIMIT_PCT × 本金 → 拒新单。

    today_realized_pnl 为今日 sum(pnl),正值=盈利,负值=亏损。
    """
    if equity_usdt <= 0:
        raise IronlawViolation("BAD_EQUITY", f"equity must be > 0, got {equity_usdt}")
    loss = -today_realized_pnl
    limit = equity_usdt * DAILY_DRAWDOWN_LIMIT_PCT
    if loss >= limit - 1e-9:
        raise IronlawViolation(
            "DAILY_DRAWDOWN_HIT",
            f"today realized {today_realized_pnl:.2f} ≤ -{limit:.2f} "
            f"(-{DAILY_DRAWDOWN_LIMIT_PCT*100:.1f}% of {equity_usdt:.2f}); "
            f"new entries locked for today",
        )


def gate_min_rr(*, sl_distance: float, tp_distance: float) -> None:
    """tp_distance / sl_distance ≥ MIN_RR。"""
    if sl_distance <= 0:
        raise IronlawViolation("BAD_SL", f"sl_distance must be > 0, got {sl_distance}")
    if tp_distance <= 0:
        raise IronlawViolation("BAD_TP", f"tp_distance must be > 0, got {tp_distance}")
    rr = tp_distance / sl_distance
    if rr < MIN_RR - 1e-9:
        raise IronlawViolation(
            "MIN_RR_VIOLATION",
            f"rr={rr:.2f} < {MIN_RR}",
        )


def gate_liquidation_distance(
    *, entry: float, sl_price: float, leverage: int, side: str,
) -> None:
    """强平价距 ≥ MIN_LIQ_TO_SL_DISTANCE_RATIO × 止损价距。

    简化公式(忽略 maintenance margin):
      LONG  → liq ≈ entry × (1 - 1/leverage)
      SHORT → liq ≈ entry × (1 + 1/leverage)
    """
    if leverage <= 0:
        raise IronlawViolation("BAD_LEVERAGE", f"leverage must be > 0, got {leverage}")
    if entry <= 0:
        raise IronlawViolation("BAD_ENTRY", f"entry must be > 0, got {entry}")

    sl_dist = abs(entry - sl_price)
    if sl_dist == 0:
        raise IronlawViolation("BAD_SL", "sl_price equals entry")

    side_u = side.upper()
    if side_u == "LONG":
        liq = entry * (1.0 - 1.0 / leverage)
    elif side_u == "SHORT":
        liq = entry * (1.0 + 1.0 / leverage)
    else:
        raise IronlawViolation("BAD_SIDE", f"unknown side {side}")
    liq_dist = abs(entry - liq)

    if liq_dist < MIN_LIQ_TO_SL_DISTANCE_RATIO * sl_dist:
        raise IronlawViolation(
            "LIQ_TOO_CLOSE",
            f"liq_dist={liq_dist:.6g} < {MIN_LIQ_TO_SL_DISTANCE_RATIO}× "
            f"sl_dist={sl_dist:.6g} (leverage={leverage} too high for this ATR; "
            f"reduce leverage or widen SL within evolution bounds)",
        )


def gate_sl_attached(*, sl_price: Optional[float]) -> None:
    """进场必挂止损(SL_MANDATORY_AT_ENTRY)。"""
    if sl_price is None or sl_price <= 0:
        raise IronlawViolation(
            "SL_NOT_ATTACHED",
            "stop loss is required at entry; rollback if attach fails",
        )


def gate_setup_enabled(*, setup_type: str, db_path: Optional[str] = None) -> None:
    """禁用 setup → 拒。

    检查两个来源:
    1. DEFAULT_DISABLED_SETUPS(宪法静态清单,含文档 §4 161 笔杀手)
    2. setup_performance 表中 status='disabled' 的(M8 自动剪枝产物)
    """
    if db_path is None:
        if setup_type in DEFAULT_DISABLED_SETUPS:
            raise IronlawViolation(
                "SETUP_DISABLED",
                f"setup_type {setup_type!r} in DEFAULT_DISABLED_SETUPS",
            )
        return

    # 有 db_path 时,使用 M8 维护的运行时清单
    from scripts.setup_performance import get_disabled_setups
    disabled = get_disabled_setups(db_path)
    if setup_type in disabled:
        raise IronlawViolation(
            "SETUP_DISABLED",
            f"setup_type {setup_type!r} is disabled (default or auto-pruned)",
        )


# ─────────────────────────────────────────────────────────────
# 进化层 clamp
# ─────────────────────────────────────────────────────────────


def clamp_evolution_sl_mult(v: float) -> float:
    """clamp AI 的 sl 修正器到 [0.8, 1.5]。base × clamp 仍可能违 final ratio,由 gate 兜底。"""
    return max(EVOLUTION_AI_SL_MULT_MIN, min(EVOLUTION_AI_SL_MULT_MAX, v))


def clamp_evolution_tp_mult(v: float) -> float:
    return max(EVOLUTION_TP_MULT_MIN, min(EVOLUTION_TP_MULT_MAX, v))


def clamp_evolution_size_mult(v: float) -> float:
    return max(EVOLUTION_SIZE_MULT_MIN, min(EVOLUTION_SIZE_MULT_MAX, v))


def gate_final_sl_ratio(*, sl_distance: float, atr: float) -> None:
    """最终 SL/ATR ratio 必须落在 [FINAL_SL_ATR_RATIO_MIN, FINAL_SL_ATR_RATIO_MAX]。

    文档 §5 第二层 — 最关键的"窄区间"实际约束。
    """
    if atr <= 0:
        raise IronlawViolation("BAD_ATR", f"atr must be > 0, got {atr}")
    ratio = sl_distance / atr
    if ratio < FINAL_SL_ATR_RATIO_MIN - 1e-9 or ratio > FINAL_SL_ATR_RATIO_MAX + 1e-9:
        raise IronlawViolation(
            "SL_ATR_RATIO_OUT_OF_RANGE",
            f"final SL/ATR={ratio:.2f} not in "
            f"[{FINAL_SL_ATR_RATIO_MIN}, {FINAL_SL_ATR_RATIO_MAX}]",
        )


# ─────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────


def get_today_realized_pnl(db_path: str) -> float:
    """SUM(pnl) from paper_trades closed today (UTC)。

    用于 gate_daily_drawdown 的输入。
    """
    today = datetime.now(timezone.utc).date().isoformat()
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM paper_trades "
            "WHERE status='CLOSED' AND DATE(exit_time)=?",
            (today,),
        ).fetchone()
        return float(row[0] or 0.0)
    finally:
        conn.close()


__all__ = [
    "IronlawViolation",
    "gate_per_trade_risk",
    "gate_daily_drawdown",
    "gate_min_rr",
    "gate_liquidation_distance",
    "gate_sl_attached",
    "gate_setup_enabled",
    "gate_final_sl_ratio",
    "clamp_evolution_sl_mult",
    "clamp_evolution_tp_mult",
    "clamp_evolution_size_mult",
    "get_today_realized_pnl",
]
