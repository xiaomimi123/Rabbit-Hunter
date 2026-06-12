"""V5 position close API 测试。"""
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


def _open_paper_trade(db, symbol="H/USDT"):
    conn = sqlite3.connect(db)
    cur = conn.execute("""
        INSERT INTO paper_trades (
            symbol, side, entry_price, entry_time, status,
            stop_loss, take_profit, position_size_usdt, leverage,
            strategy_id, created_at
        ) VALUES (?, 'SHORT', 0.166, datetime('now'), 'OPEN',
                  0.169, 0.162, 15.0, 10,
                  'v5_rsi_macd', datetime('now'))
    """, (symbol,))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def test_close_open_paper_trade(app_with_db):
    client, db = app_with_db
    pid = _open_paper_trade(db)
    r = client.post(f"/api/v5/positions/{pid}/close", json={
        "exit_price": 0.165, "exit_reason": "MANUAL_USER"
    })
    assert r.status_code == 200, r.text
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, exit_price, exit_reason FROM paper_trades WHERE id=?",
        (pid,)).fetchone()
    conn.close()
    assert row == ("CLOSED", 0.165, "MANUAL_USER")


def test_close_unknown_returns_404(app_with_db):
    client, _ = app_with_db
    r = client.post("/api/v5/positions/99999/close", json={
        "exit_price": 0.165, "exit_reason": "MANUAL_USER"
    })
    assert r.status_code == 404


def test_close_already_closed_returns_409(app_with_db):
    client, db = app_with_db
    pid = _open_paper_trade(db)
    client.post(f"/api/v5/positions/{pid}/close", json={
        "exit_price": 0.165, "exit_reason": "MANUAL_USER"})
    r = client.post(f"/api/v5/positions/{pid}/close", json={
        "exit_price": 0.164, "exit_reason": "MANUAL_USER"})
    assert r.status_code == 409
