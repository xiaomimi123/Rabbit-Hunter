"""M3 铁律层硬断言测试。

每个 gate 都需要:
1. 合法输入下沉默通过
2. 违规输入下 raise IronlawViolation,且 kind 正确
"""
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest

from scripts.risk_constitution import (
    DAILY_DRAWDOWN_LIMIT_PCT,
    DEFAULT_DISABLED_SETUPS,
    EVOLUTION_AI_SL_MULT_MAX,
    EVOLUTION_AI_SL_MULT_MIN,
    EVOLUTION_SIZE_MULT_MAX,
    EVOLUTION_SIZE_MULT_MIN,
    EVOLUTION_TP_MULT_MAX,
    EVOLUTION_TP_MULT_MIN,
    FINAL_SL_ATR_RATIO_MAX,
    FINAL_SL_ATR_RATIO_MIN,
    MAX_PER_TRADE_RISK_PCT,
    MIN_LIQ_TO_SL_DISTANCE_RATIO,
    MIN_RR,
)
from scripts.risk_gates import (
    IronlawViolation,
    clamp_evolution_size_mult,
    clamp_evolution_sl_mult,
    clamp_evolution_tp_mult,
    gate_daily_drawdown,
    gate_final_sl_ratio,
    gate_liquidation_distance,
    gate_min_rr,
    gate_per_trade_risk,
    gate_setup_enabled,
    gate_sl_attached,
    get_today_realized_pnl,
)


# ─── constitution sanity ─────────────────────────────────────────


def test_constitution_values_match_doc():
    """直接对齐文档 §5 数值。"""
    assert MAX_PER_TRADE_RISK_PCT == 0.01
    assert DAILY_DRAWDOWN_LIMIT_PCT == 0.03
    assert MIN_RR == 1.5
    assert MIN_LIQ_TO_SL_DISTANCE_RATIO == 2.0
    # 文档 §5 第二层:SL ratio 落在 [1.5, 2.2]
    assert FINAL_SL_ATR_RATIO_MIN == 1.5
    assert FINAL_SL_ATR_RATIO_MAX == 2.2


def test_default_disabled_setups_contains_killer():
    """文档 §4:rsi_neutral_macd_extending_long 是 161 笔杀手,默认禁。"""
    assert "rsi_neutral_macd_extending_long" in DEFAULT_DISABLED_SETUPS


# ─── gate_per_trade_risk ─────────────────────────────────────────


def test_per_trade_risk_passes_at_cap():
    """1 万本金 + 100 USDT 计划亏损 = 正好 1%,通过。"""
    gate_per_trade_risk(equity_usdt=10_000, planned_loss_usdt=100)


def test_per_trade_risk_passes_below_cap():
    gate_per_trade_risk(equity_usdt=10_000, planned_loss_usdt=50)


def test_per_trade_risk_violates_above_cap():
    """计划亏损 150 USDT(=1.5%)— 旧默认值,新铁律拒。"""
    with pytest.raises(IronlawViolation) as exc:
        gate_per_trade_risk(equity_usdt=10_000, planned_loss_usdt=150)
    assert exc.value.kind == "PER_TRADE_RISK_EXCEEDED"


def test_per_trade_risk_violates_bad_equity():
    with pytest.raises(IronlawViolation) as exc:
        gate_per_trade_risk(equity_usdt=0, planned_loss_usdt=10)
    assert exc.value.kind == "BAD_EQUITY"


# ─── gate_daily_drawdown ─────────────────────────────────────────


def test_daily_dd_passes_when_no_loss():
    gate_daily_drawdown(equity_usdt=10_000, today_realized_pnl=+50)


def test_daily_dd_passes_at_minor_loss():
    """-2% 今日,还没到 3%。"""
    gate_daily_drawdown(equity_usdt=10_000, today_realized_pnl=-200)


def test_daily_dd_violates_at_3pct():
    """-3% 触发熔断。"""
    with pytest.raises(IronlawViolation) as exc:
        gate_daily_drawdown(equity_usdt=10_000, today_realized_pnl=-300)
    assert exc.value.kind == "DAILY_DRAWDOWN_HIT"


def test_daily_dd_violates_below_3pct():
    with pytest.raises(IronlawViolation) as exc:
        gate_daily_drawdown(equity_usdt=10_000, today_realized_pnl=-500)
    assert exc.value.kind == "DAILY_DRAWDOWN_HIT"


# ─── gate_min_rr ─────────────────────────────────────────


def test_min_rr_passes_at_15():
    """RR = 1.5 正好满足。"""
    gate_min_rr(sl_distance=1.0, tp_distance=1.5)


def test_min_rr_passes_at_higher():
    gate_min_rr(sl_distance=1.0, tp_distance=2.5)


def test_min_rr_violates_below_15():
    """RR = 1.0 拒。"""
    with pytest.raises(IronlawViolation) as exc:
        gate_min_rr(sl_distance=1.0, tp_distance=1.0)
    assert exc.value.kind == "MIN_RR_VIOLATION"


# ─── gate_liquidation_distance ─────────────────────────────────────────


def test_liq_distance_passes_with_low_leverage():
    """10x 杠杆,entry=100,sl=98(2% 距)→ liq ≈ 90(10% 距)→ 10/2 = 5x 远,通过。"""
    gate_liquidation_distance(entry=100, sl_price=98, leverage=10, side="LONG")


def test_liq_distance_violates_with_high_leverage():
    """50x 杠杆,entry=100,sl=98(2% 距)→ liq ≈ 98(2% 距)→ 1x = 不够 2x,拒。"""
    with pytest.raises(IronlawViolation) as exc:
        gate_liquidation_distance(entry=100, sl_price=98, leverage=50, side="LONG")
    assert exc.value.kind == "LIQ_TOO_CLOSE"


def test_liq_distance_short_side():
    """SHORT entry=100, sl=102 (2% 距), 10x → liq ≈ 110(10% 距),通过。"""
    gate_liquidation_distance(entry=100, sl_price=102, leverage=10, side="SHORT")


# ─── gate_sl_attached ─────────────────────────────────────────


def test_sl_attached_passes_with_valid_price():
    gate_sl_attached(sl_price=98.5)


def test_sl_attached_violates_when_none():
    with pytest.raises(IronlawViolation) as exc:
        gate_sl_attached(sl_price=None)
    assert exc.value.kind == "SL_NOT_ATTACHED"


def test_sl_attached_violates_when_zero():
    with pytest.raises(IronlawViolation) as exc:
        gate_sl_attached(sl_price=0)
    assert exc.value.kind == "SL_NOT_ATTACHED"


# ─── gate_setup_enabled ─────────────────────────────────────────


def test_setup_enabled_passes_for_known_winner():
    gate_setup_enabled(setup_type="rsi_oversold_macd_extending_long")


def test_setup_enabled_violates_for_killer():
    with pytest.raises(IronlawViolation) as exc:
        gate_setup_enabled(setup_type="rsi_neutral_macd_extending_long")
    assert exc.value.kind == "SETUP_DISABLED"


# ─── evolution clamps ─────────────────────────────────────────


def test_clamp_sl_mult_within_window():
    assert clamp_evolution_sl_mult(1.0) == 1.0


def test_clamp_sl_mult_below_floor():
    assert clamp_evolution_sl_mult(0.5) == EVOLUTION_AI_SL_MULT_MIN


def test_clamp_sl_mult_above_ceiling():
    assert clamp_evolution_sl_mult(3.0) == EVOLUTION_AI_SL_MULT_MAX


def test_clamp_tp_mult_floor():
    """TP 修正器下限 = MIN_RR = 1.5。"""
    assert clamp_evolution_tp_mult(1.0) == EVOLUTION_TP_MULT_MIN
    assert EVOLUTION_TP_MULT_MIN == MIN_RR


def test_clamp_size_mult_window():
    assert clamp_evolution_size_mult(0.3) == EVOLUTION_SIZE_MULT_MIN
    assert clamp_evolution_size_mult(0.8) == 0.8
    assert clamp_evolution_size_mult(2.0) == EVOLUTION_SIZE_MULT_MAX


# ─── gate_final_sl_ratio ─────────────────────────────────────────


def test_final_sl_ratio_passes_at_floor():
    """SL = 1.5 × ATR 正好踩 FINAL_SL_ATR_RATIO_MIN。"""
    gate_final_sl_ratio(sl_distance=1.5, atr=1.0)


def test_final_sl_ratio_passes_at_ceiling():
    gate_final_sl_ratio(sl_distance=2.2, atr=1.0)


def test_final_sl_ratio_violates_too_tight():
    """SL < 1.5 × ATR 会被噪音扫损。"""
    with pytest.raises(IronlawViolation) as exc:
        gate_final_sl_ratio(sl_distance=1.0, atr=1.0)
    assert exc.value.kind == "SL_ATR_RATIO_OUT_OF_RANGE"


def test_final_sl_ratio_violates_too_wide():
    """SL > 2.2 × ATR 风险预算被吃掉。"""
    with pytest.raises(IronlawViolation) as exc:
        gate_final_sl_ratio(sl_distance=3.0, atr=1.0)
    assert exc.value.kind == "SL_ATR_RATIO_OUT_OF_RANGE"


# ─── get_today_realized_pnl ─────────────────────────────────────────


def test_today_realized_pnl_sums_only_today():
    """只统计今天已关仓的 pnl;过期的 / open 的不算。"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE paper_trades (
                id INTEGER PRIMARY KEY, status TEXT, exit_time TEXT, pnl REAL
            )
        """)
        today = datetime.now(timezone.utc).date().isoformat()
        rows = [
            ("CLOSED", f"{today}T01:00:00+00:00", -50.0),
            ("CLOSED", f"{today}T03:00:00+00:00", +30.0),
            ("CLOSED", "2026-01-01T00:00:00+00:00", -999.0),  # 不是今天
            ("OPEN", None, None),                              # 未关仓
        ]
        for status, et, pnl in rows:
            conn.execute(
                "INSERT INTO paper_trades(status, exit_time, pnl) VALUES (?, ?, ?)",
                (status, et, pnl),
            )
        conn.commit()
        conn.close()

        # -50 + 30 = -20
        assert get_today_realized_pnl(db_path) == -20.0
    finally:
        os.unlink(db_path)
