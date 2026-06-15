"""Daily aggregator by setup_type — group reflections, compute stats."""
import sqlite3
import tempfile
import pytest
from datetime import datetime, timezone, timedelta


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _seed_reflections(db_path, rows):
    conn = sqlite3.connect(db_path)
    for r in rows:
        conn.execute("""
            INSERT INTO reflections (paper_trade_id, why_entered, what_was_expected,
                what_actually_happened, correction_idea, failure_mode_key,
                setup_type, outcome_class, realized_r, holding_minutes,
                confidence_at_entry, created_at, prompt_version)
            VALUES (?, 'x', 'y', 'z', 'w', ?, ?, ?, ?, ?, 0.7, ?, 'v1')
        """, (r["pid"], r.get("fm"), r["setup_type"], r["outcome"],
              r["realized_r"], r.get("hold", 30), r["created_at"]))
    conn.commit()
    conn.close()


def test_aggregate_groups_by_setup_type_and_date(db):
    from scripts.ai.setup_aggregator import aggregate_daily

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT12:00:00+00:00")
    _seed_reflections(db, [
        dict(pid=1, setup_type="rsi_overbought_macd_bearish_short",
             outcome="WIN", realized_r=1.2, created_at=yesterday),
        dict(pid=2, setup_type="rsi_overbought_macd_bearish_short",
             outcome="LOSS", realized_r=-1.0, created_at=yesterday),
        dict(pid=3, setup_type="rsi_oversold_macd_bullish_long",
             outcome="WIN", realized_r=0.8, created_at=yesterday),
    ])

    aggregate_daily(db_path=db, target_date=yesterday[:10])

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT setup_type, sample_count, win_count, loss_count, win_rate, avg_realized_r "
        "FROM setup_performance_daily ORDER BY setup_type"
    ).fetchall()
    conn.close()

    by_setup = {r[0]: r for r in rows}
    assert by_setup["rsi_overbought_macd_bearish_short"][1] == 2
    assert by_setup["rsi_overbought_macd_bearish_short"][2] == 1
    assert abs(by_setup["rsi_overbought_macd_bearish_short"][4] - 0.5) < 1e-9
    assert abs(by_setup["rsi_overbought_macd_bearish_short"][5] - 0.1) < 1e-9
    assert by_setup["rsi_oversold_macd_bullish_long"][1] == 1


def test_aggregate_includes_top_failure_mode(db):
    from scripts.ai.setup_aggregator import aggregate_daily

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT12:00:00+00:00")
    _seed_reflections(db, [
        dict(pid=1, setup_type="X", outcome="LOSS", realized_r=-1.0,
             fm="late_entry_signal_decay", created_at=yesterday),
        dict(pid=2, setup_type="X", outcome="LOSS", realized_r=-1.0,
             fm="late_entry_signal_decay", created_at=yesterday),
        dict(pid=3, setup_type="X", outcome="LOSS", realized_r=-1.0,
             fm="chase_after_3pct_move", created_at=yesterday),
    ])
    aggregate_daily(db_path=db, target_date=yesterday[:10])

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT top_failure_mode FROM setup_performance_daily WHERE setup_type='X'"
    ).fetchone()
    conn.close()
    assert row[0] == "late_entry_signal_decay"


def test_aggregate_is_idempotent(db):
    """跑两次同一天,不重复入库。"""
    from scripts.ai.setup_aggregator import aggregate_daily

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT12:00:00+00:00")
    _seed_reflections(db, [
        dict(pid=1, setup_type="Y", outcome="WIN", realized_r=1.0, created_at=today),
    ])
    aggregate_daily(db_path=db, target_date=today[:10])
    aggregate_daily(db_path=db, target_date=today[:10])

    conn = sqlite3.connect(db)
    n = conn.execute(
        "SELECT COUNT(*) FROM setup_performance_daily WHERE setup_type='Y'"
    ).fetchone()[0]
    conn.close()
    assert n == 1


def test_aggregate_computes_expectancy(db):
    from scripts.ai.setup_aggregator import aggregate_daily

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT12:00:00+00:00")
    _seed_reflections(db, [
        dict(pid=1, setup_type="Z", outcome="WIN", realized_r=2.0, created_at=today),
        dict(pid=2, setup_type="Z", outcome="WIN", realized_r=1.0, created_at=today),
        dict(pid=3, setup_type="Z", outcome="LOSS", realized_r=-1.0, created_at=today),
        dict(pid=4, setup_type="Z", outcome="LOSS", realized_r=-1.0, created_at=today),
    ])
    aggregate_daily(db_path=db, target_date=today[:10])

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT win_rate, avg_realized_r, expectancy FROM setup_performance_daily WHERE setup_type='Z'"
    ).fetchone()
    conn.close()
    win_rate, avg_r, exp = row
    # win_rate 0.5, avg_win=1.5, avg_loss=-1.0 → expectancy = 0.5*1.5 - 0.5*1 = 0.25
    assert abs(win_rate - 0.5) < 1e-9
    assert abs(avg_r - 0.25) < 1e-9
    assert abs(exp - 0.25) < 1e-9
