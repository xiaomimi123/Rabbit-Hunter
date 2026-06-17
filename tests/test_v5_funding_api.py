"""GET /api/v5/funding/status + /history/{symbol} 测试."""
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


def test_status_returns_empty_when_no_data(client):
    c, _ = client
    r = c.get("/api/v5/funding/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["data"] == []


def test_status_returns_cached_zscores(client):
    c, db = client
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO funding_zscore_cache (symbol, current_funding_rate,
            mean_30d, std_30d, zscore_30d, sample_size_30d, is_extreme,
            extreme_direction)
        VALUES ('BTCUSDT', 0.0005, 0.0001, 0.0001, 2.5, 90, 1, 'long_crowded'),
               ('ETHUSDT', -0.0002, 0.00005, 0.0001, -1.5, 80, 0, NULL)
    """)
    conn.commit()
    conn.close()
    r = c.get("/api/v5/funding/status")
    body = r.json()
    assert len(body["data"]) == 2
    by_sym = {item["symbol"]: item for item in body["data"]}
    assert by_sym["BTCUSDT"]["zscore_30d"] == 2.5
    assert by_sym["BTCUSDT"]["is_extreme"] is True
    assert by_sym["BTCUSDT"]["extreme_direction"] == "long_crowded"
    assert by_sym["ETHUSDT"]["is_extreme"] is False


def test_history_returns_funding_rates(client):
    c, db = client
    conn = sqlite3.connect(db)
    for i in range(5):
        conn.execute("""
            INSERT INTO funding_rates (symbol, instrument_id, funding_time,
                funding_rate, annualized_rate, source)
            VALUES ('BTCUSDT', 'BTC-USDT-SWAP', ?, ?, ?, 'okx')
        """, (f"2026-06-17T0{i}:00:00+00:00", 0.0001 * (i + 1),
              0.0001 * (i + 1) * 365 * 3))
    conn.commit()
    conn.close()
    r = c.get("/api/v5/funding/history/BTCUSDT?limit=10")
    body = r.json()
    assert body["status"] == "success"
    assert body["symbol"] == "BTCUSDT"
    assert len(body["data"]) == 5


def test_history_unknown_symbol_returns_empty(client):
    c, _ = client
    r = c.get("/api/v5/funding/history/UNKNOWN")
    body = r.json()
    assert body["data"] == []
