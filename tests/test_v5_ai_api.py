"""V5 AI status + decisions API 测试。"""
import sqlite3
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_db(monkeypatch):
    from scripts.local_db import init_local_db
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    init_local_db(tmp.name)
    from api.main import app
    return TestClient(app), tmp.name


def test_ai_status_empty(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/ai/status")
    assert r.status_code == 200
    data = r.json()
    assert "provider" in data
    assert data["decisions_24h"] == 0
    assert data["rag_utilization_24h"] == 0.0
    assert data["rag_cases_in_db"] == 0


def test_ai_status_with_data(app_with_db, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    client, db = app_with_db
    conn = sqlite3.connect(db)
    for i in range(3):
        reasoning = "Historical similar cases" if i < 2 else "no rag"
        conn.execute(
            "INSERT INTO trade_scores_v5 (symbol, created_at, should_trade, "
            "ai_reasoning, executed) "
            "VALUES (?, datetime('now', '-1 hour'), 1, ?, 1)",
            (f"S{i}", reasoning),
        )
    for i in range(12):
        conn.execute(
            "INSERT INTO ai_training_data (symbol, side, entry_rsi_15m, "
            "entry_macd_hist_15m, entry_rsi_4h, outcome, pnl_pct, created_at) "
            "VALUES (?, 'SHORT', 72.0, -0.0005, 65.0, 'WIN', 0.004, datetime('now'))",
            (f"H{i}",),
        )
    conn.commit()
    conn.close()
    r = client.get("/api/v5/ai/status")
    data = r.json()
    assert data["decisions_24h"] == 3
    assert abs(data["rag_utilization_24h"] - 2/3) < 0.01
    assert data["rag_cases_in_db"] == 12


def test_decisions_returns_recent(app_with_db):
    client, db = app_with_db
    conn = sqlite3.connect(db)
    for i in range(5):
        conn.execute("""
            INSERT INTO trade_scores_v5 (
                symbol, created_at, side, ai_confidence, ai_reasoning,
                should_trade, executed
            ) VALUES (?, datetime('now', '-1 hour'), 'SHORT', ?, ?, 1, 1)
        """, (f"S{i}", 0.6 + i * 0.05, f"reason {i}"))
    conn.commit()
    conn.close()
    r = client.get("/api/v5/ai/decisions?limit=3")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decisions"]) == 3
    for d in data["decisions"]:
        assert d["symbol"].startswith("S")


def test_decisions_filters_no_ai_reasoning(app_with_db):
    client, db = app_with_db
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO trade_scores_v5 (symbol, created_at, should_trade) "
        "VALUES ('X', datetime('now'), 0)")
    conn.commit()
    conn.close()
    r = client.get("/api/v5/ai/decisions")
    assert r.json()["decisions"] == []
