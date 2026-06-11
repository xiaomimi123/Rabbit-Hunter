"""V5 API 集成测试 — 用 FastAPI TestClient。"""
import tempfile, sqlite3
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    conn = sqlite3.connect(tmp.name)
    conn.execute("""
        INSERT INTO trade_scores_v5 (symbol, created_at, should_trade, side,
        rsi_15m, macd_hist_15m, executed)
        VALUES ('H/USDT', '2026-06-12T10:00:00', 1, 'SHORT', 72.0, -0.0005, 1)
    """)
    conn.commit()
    conn.close()
    from api.main import app
    return TestClient(app), tmp.name


def test_get_signals_returns_v5_item(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/signals")
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert "funnel" in data
    assert len(data["data"]) == 1
    item = data["data"][0]
    assert item["symbol"] == "H/USDT"
    assert item["rsi_15m"] == 72.0
    assert item["macd_hist_15m"] == -0.0005


def test_get_positions_empty(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/positions")
    assert r.status_code == 200
    assert r.json()["data"] == []
