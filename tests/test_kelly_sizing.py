"""Fractional Kelly sizing engine + 3-window confidence."""
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


def _seed_reflections_evenly(db_path, setup_type, n, win_rate, avg_win_r, avg_loss_r,
                              days_back_max=30):
    """填 n 笔均匀分布在过去 days_back_max 天的 reflections。"""
    conn = sqlite3.connect(db_path)
    n_wins = int(n * win_rate)
    for i in range(n):
        days_back = (i % days_back_max) + 1
        created = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
        won = i < n_wins
        r = avg_win_r if won else avg_loss_r
        conn.execute("""
            INSERT INTO reflections (paper_trade_id, why_entered, what_was_expected,
                what_actually_happened, correction_idea, setup_type, outcome_class,
                realized_r, holding_minutes, confidence_at_entry, created_at, prompt_version)
            VALUES (?, 'x', 'y', 'z', 'w', ?, ?, ?, 30, 0.7, ?, 'v1')
        """, (10000 + i, setup_type, 'WIN' if won else 'LOSS', r, created))
    conn.commit()
    conn.close()


def test_returns_no_recommendation_when_insufficient_samples(db):
    from scripts.ai.kelly_sizing import generate_sizing_recommendations
    _seed_reflections_evenly(db, "X", n=3, win_rate=0.6,
                              avg_win_r=1.0, avg_loss_r=-1.0)
    out = generate_sizing_recommendations(db_path=db)
    # samples too few → no row for this setup
    assert all(r["setup_type"] != "X" for r in out)


def test_returns_recommendation_with_sufficient_samples(db):
    from scripts.ai.kelly_sizing import generate_sizing_recommendations
    # 60 笔 60% 胜率 avg_win=1.5 avg_loss=-1.0 → Kelly = 0.6/1.0 - 0.4/1.5 ≈ 0.333
    _seed_reflections_evenly(db, "X", n=60, win_rate=0.6,
                              avg_win_r=1.5, avg_loss_r=-1.0)
    out = generate_sizing_recommendations(db_path=db)
    x = next(r for r in out if r["setup_type"] == "X")
    assert 0.005 <= x["recommended_size_multiplier"] <= 0.02
    assert x["confidence_score"] > 0


def test_recommendation_written_to_db(db):
    from scripts.ai.kelly_sizing import generate_sizing_recommendations
    _seed_reflections_evenly(db, "Y", n=60, win_rate=0.55,
                              avg_win_r=1.2, avg_loss_r=-1.0)
    generate_sizing_recommendations(db_path=db)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, sample_count_30d FROM position_sizing_recommendations "
        "WHERE setup_type='Y' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row[0] == "pending"
    assert row[1] > 0


def test_recommendation_clamps_to_bounds(db):
    """即使 Kelly 计算很大,也不超过 2%;很小不低于 0.5%。"""
    from scripts.ai.kelly_sizing import generate_sizing_recommendations
    # 极高胜率 90% + 高 R → Kelly 大
    _seed_reflections_evenly(db, "Z", n=60, win_rate=0.9,
                              avg_win_r=3.0, avg_loss_r=-1.0)
    generate_sizing_recommendations(db_path=db)
    conn = sqlite3.connect(db)
    rec = conn.execute(
        "SELECT recommended_size_multiplier FROM position_sizing_recommendations "
        "WHERE setup_type='Z'"
    ).fetchone()[0]
    conn.close()
    assert 0.005 <= rec <= 0.02
