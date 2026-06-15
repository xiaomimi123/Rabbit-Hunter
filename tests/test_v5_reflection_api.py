"""GET /api/v5/reflections — list endpoint."""
import sqlite3
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    from api.main import app
    return TestClient(app), tmp.name


def _insert_reflection(db_path, *, pid=1, symbol="HUSDT"):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO paper_trades (id, symbol, side, entry_price, entry_time, status,
            stop_loss, take_profit, position_size_usdt, leverage, strategy_id,
            created_at, exit_price, exit_time, exit_reason, pnl_percent)
        VALUES (?, ?, 'SHORT', 0.166, datetime('now', '-30 minutes'), 'CLOSED',
                0.169, 0.162, 15, 10, 'v5_rsi_macd', datetime('now', '-30 minutes'),
                0.162, datetime('now'), 'TP_HIT', 1.8)
    """, (pid, symbol))
    conn.execute("""
        INSERT INTO reflections (paper_trade_id, why_entered, what_was_expected,
            what_actually_happened, correction_idea, failure_mode_key, setup_type,
            outcome_class, realized_r, holding_minutes, confidence_at_entry,
            self_assessed_prediction_accuracy, is_in_predicted_failure_mode,
            ai_provider, ai_model, ai_latency_ms, prompt_version)
        VALUES (?, 'rsi 72 + macd bearish', 'pullback then tp',
                'actually went to tp quickly', 'add 4h filter next time', NULL,
                'rsi_overbought_macd_bearish_short', 'WIN', 1.0, 30, 0.7,
                0.85, 0, 'deepseek', 'deepseek-chat', 4200, 'reflection-prompt-v1')
    """, (pid,))
    conn.commit()
    conn.close()


def test_list_returns_empty_wrapper(client):
    c, _ = client
    r = c.get("/api/v5/reflections?limit=10")
    assert r.status_code == 200
    assert r.json() == {"status": "success", "data": []}


def test_list_returns_recent_reflections_joined_with_paper_trade(client):
    c, db = client
    _insert_reflection(db, pid=1, symbol="HUSDT")
    r = c.get("/api/v5/reflections?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert len(body["data"]) == 1
    item = body["data"][0]
    assert item["paper_trade_id"] == 1
    assert item["symbol"] == "HUSDT"
    assert item["side"] == "SHORT"
    assert item["outcome_class"] == "WIN"
    assert "rsi 72" in item["why_entered"]


def test_list_respects_limit(client):
    c, db = client
    for i in range(5):
        _insert_reflection(db, pid=i + 1, symbol=f"X{i}USDT")
    r = c.get("/api/v5/reflections?limit=3")
    assert r.status_code == 200
    assert len(r.json()["data"]) == 3


def test_failure_taxonomy_returns_8_seeds(client):
    c, _ = client
    r = c.get("/api/v5/failure-taxonomy")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert len(body["data"]) == 8
    keys = {m["key"] for m in body["data"]}
    assert "chase_after_3pct_move" in keys
    for m in body["data"]:
        assert m["seeded"] is True
        assert m["sample_count"] == 0    # 还没 reflection 链上


def test_failure_taxonomy_counts_reflections(client):
    c, db = client
    _insert_reflection(db, pid=1)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE reflections SET failure_mode_key='chase_after_3pct_move' WHERE paper_trade_id=1")
    conn.commit()
    conn.close()
    r = c.get("/api/v5/failure-taxonomy")
    by_key = {m["key"]: m for m in r.json()["data"]}
    assert by_key["chase_after_3pct_move"]["sample_count"] == 1


def test_setup_performance_returns_empty(client):
    c, _ = client
    r = c.get("/api/v5/setup-performance?days=7")
    assert r.status_code == 200
    assert r.json() == {"status": "success", "data": []}


def test_sizing_recommendations_pending_only(client):
    c, db = client
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO position_sizing_recommendations
            (setup_type, current_size_multiplier, recommended_size_multiplier,
             confidence_score, rationale, status)
        VALUES ('rsi_overbought_macd_bearish_short', 1.0, 0.6, 0.78,
                'test', 'pending'),
               ('other', 1.0, 0.8, 0.5, 'test2', 'approved')
    """)
    conn.commit()
    conn.close()
    r = c.get("/api/v5/sizing-recommendations")
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["setup_type"] == "rsi_overbought_macd_bearish_short"


def test_decide_sizing_approve(client):
    c, db = client
    conn = sqlite3.connect(db)
    cur = conn.execute("""
        INSERT INTO position_sizing_recommendations
            (setup_type, current_size_multiplier, recommended_size_multiplier,
             confidence_score, rationale)
        VALUES ('X', 1.0, 0.7, 0.8, 'x')
    """)
    rec_id = cur.lastrowid
    conn.commit()
    conn.close()
    r = c.patch(f"/api/v5/sizing-recommendations/{rec_id}",
                json={"decision": "approve"})
    assert r.status_code == 200
    conn = sqlite3.connect(db)
    status = conn.execute(
        "SELECT status FROM position_sizing_recommendations WHERE id=?", (rec_id,)
    ).fetchone()[0]
    conn.close()
    assert status == "approved"


def test_calibration_returns_inserted_buckets(client):
    c, db = client
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO ai_confidence_calibration
            (ai_model, confidence_bucket, predicted_win_rate, actual_win_rate,
             sample_count, calibration_multiplier)
        VALUES ('deepseek-chat', 0.7, 0.7, 0.5, 15, 0.714)
    """)
    conn.commit()
    conn.close()
    r = c.get("/api/v5/confidence-calibration")
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["confidence_bucket"] == 0.7
    assert body["data"][0]["actual_win_rate"] == 0.5
