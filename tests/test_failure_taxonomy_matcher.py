"""Failure taxonomy matcher — 给一个入场 candidate,返回命中的 taxonomy keys。"""
import sqlite3
import tempfile
import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _candidate(**over):
    base = dict(
        side="SHORT", side_int=-1,
        rsi_15m=72.0, macd_hist_15m=-0.0012, macd_hist_prev_15m=0.0008,
        macd_hist_4h=0.003, atr_15m=0.0015,
        sl_distance_atr_ratio=1.5, tp_distance_atr_ratio=2.0,
        delta_15m_pct=0.01,
        funding_z_score=None,
        symbol="HUSDT",
    )
    base.update(over)
    return base


def test_no_matches_when_candidate_clean(db):
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(), db_path=db)
    assert hits == []


def test_late_entry_matches_when_hist_decayed(db):
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(
        rsi_15m=72.5,
        macd_hist_prev_15m=-0.0001,    # 几乎为 0 → 比已经退太远
        macd_hist_15m=-0.001,
    ), db_path=db)
    assert "late_entry_signal_decay" in hits


def test_chase_after_3pct_matches(db):
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(delta_15m_pct=0.03), db_path=db)
    assert "chase_after_3pct_move" in hits


def test_against_4h_no_funding_matches(db):
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(
        side="SHORT", side_int=-1,
        macd_hist_4h=0.005,           # 4h 看多
        funding_z_score=None,
    ), db_path=db)
    assert "against_4h_trend_no_funding_filter" in hits


def test_funding_high_z_overrides_4h_filter(db):
    """funding z-score 极端时,该规则不再触发(funding 给了反向背书)。"""
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(
        side="SHORT", side_int=-1,
        macd_hist_4h=0.005,
        funding_z_score=2.5,           # funding 极端正 = SHORT 有理
    ), db_path=db)
    assert "against_4h_trend_no_funding_filter" not in hits


def test_repeat_failure_same_symbol_24h_matches(db):
    """注入 2 笔过去 24h LOSS → 匹配。"""
    from scripts.ai.failure_taxonomy import match_failure_modes
    conn = sqlite3.connect(db)
    for i in range(2):
        conn.execute("""
            INSERT INTO paper_trades (symbol, side, entry_price, entry_time, status,
                stop_loss, take_profit, position_size_usdt, leverage, strategy_id,
                created_at, exit_time, exit_reason, pnl_percent)
            VALUES ('HUSDT', 'SHORT', 0.166, datetime('now', '-3 hours'), 'CLOSED',
                    0.169, 0.162, 15, 10, 'v5_rsi_macd', datetime('now', '-3 hours'),
                    datetime('now', '-2 hours'), 'SL_HIT', -1.8)
        """)
    conn.commit()
    conn.close()
    hits = match_failure_modes(_candidate(symbol="HUSDT"), db_path=db)
    assert "repeat_failure_same_symbol_24h" in hits


def test_only_active_taxonomy_is_matched(db):
    """is_active=0 的 rule 不参与匹配。"""
    from scripts.ai.failure_taxonomy import match_failure_modes
    conn = sqlite3.connect(db)
    conn.execute("UPDATE failure_taxonomy SET is_active=0 WHERE key='chase_after_3pct_move'")
    conn.commit()
    conn.close()
    hits = match_failure_modes(_candidate(delta_15m_pct=0.03), db_path=db)
    assert "chase_after_3pct_move" not in hits


def test_funding_extreme_overrides_4h_filter_when_supports(db):
    """SHORT + 4h 上行(逆) + funding z=+2.5(多头拥挤背书 SHORT) → 不触发 against_4h."""
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(
        side="SHORT", side_int=-1,
        macd_hist_4h=0.005,           # 4h 看多
        funding_z_score=2.5,           # funding 背书 SHORT
    ), db_path=db)
    assert "against_4h_trend_no_funding_filter" not in hits


def test_funding_extreme_against_direction_still_triggers(db):
    """SHORT + 4h 上行 + funding z=-2.5(空头拥挤,反向 → LONG 才合理)
    funding 不背书 SHORT → against_4h 触发."""
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(
        side="SHORT", side_int=-1,
        macd_hist_4h=0.005,
        funding_z_score=-2.5,
    ), db_path=db)
    assert "against_4h_trend_no_funding_filter" in hits


def test_funding_moderate_does_not_override(db):
    """funding |z| < 1.5 (中性) → 不算背书,against_4h 仍触发."""
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(
        side="SHORT", side_int=-1,
        macd_hist_4h=0.005,
        funding_z_score=1.0,
    ), db_path=db)
    assert "against_4h_trend_no_funding_filter" in hits
