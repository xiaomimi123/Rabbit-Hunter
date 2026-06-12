"""V5 charts API 测试。fetch_klines mock 掉。"""
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


def test_klines_returns_data(app_with_db, monkeypatch):
    import sys
    import types

    fake = [(1717200000000, 0.166, 0.168, 0.165, 0.166, 1000.0)] * 50

    def _fake_fetch(*args, **kwargs):
        return fake

    # Inject a fake module so the lazy import inside the route succeeds
    # even when the real `requests` dep is absent in the test environment.
    fake_mod = types.ModuleType("scripts.tasks.exchange_endpoints")
    fake_mod.fetch_klines = _fake_fetch
    monkeypatch.setitem(sys.modules, "scripts.tasks.exchange_endpoints", fake_mod)

    client, _ = app_with_db
    r = client.get("/api/v5/klines/H_USDT?interval=15m&limit=50")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "H/USDT"
    assert data["interval"] == "15m"
    assert len(data["klines"]) == 50
    assert data["klines"][0]["ts"] == 1717200000000
    assert data["klines"][0]["close"] == 0.166


def test_klines_rejects_invalid_interval(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/klines/H_USDT?interval=2d")
    assert r.status_code == 400 or r.status_code == 422


def test_events_aggregates_from_paper_trades(app_with_db):
    """paper_trades 里的开/平仓事件应该出现在 events。"""
    client, db = app_with_db
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO paper_trades (
            symbol, side, entry_price, entry_time, status,
            stop_loss, take_profit, position_size_usdt, leverage,
            entry_rsi_15m, entry_macd_hist_15m,
            strategy_id, created_at
        ) VALUES ('H/USDT', 'SHORT', 0.166, '2026-06-12T09:48:00+00:00', 'CLOSED',
                  0.169, 0.162, 15.0, 10,
                  72.0, -0.0005,
                  'v5_rsi_macd', '2026-06-12T09:48:00+00:00')
    """)
    conn.execute("""
        UPDATE paper_trades SET exit_price=0.162, exit_time='2026-06-12T09:55:00+00:00',
          exit_reason='TP_HIT', pnl_percent=2.4 WHERE id=last_insert_rowid()
    """)
    conn.commit()
    conn.close()
    r = client.get("/api/v5/events/H_USDT")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "H/USDT"
    types = {e["event_type"] for e in data["events"]}
    assert "entry" in types
    assert "exit" in types


def test_events_empty_for_unknown_symbol(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/events/UNKNOWN_USDT")
    assert r.status_code == 200
    assert r.json()["events"] == []
