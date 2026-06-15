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
