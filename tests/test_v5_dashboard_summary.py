"""Batch 20 Finding 20: /dashboard/summary 后端聚合端点。"""
import sqlite3
from fastapi.testclient import TestClient


def _init(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE trade_scores_v5 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, created_at TEXT, should_trade INTEGER,
            executed INTEGER, block_reason TEXT
        );
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, side TEXT, status TEXT,
            entry_time TEXT, exit_time TEXT,
            pnl_usdt REAL, pnl_pct REAL
        );
        CREATE TABLE positions_v5 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, side TEXT, status TEXT,
            entry_time TEXT, exit_time TEXT,
            pnl_usdt REAL, pnl_pct REAL
        );
    ''')
    conn.commit()
    conn.close()


def test_summary_default_hours_24(monkeypatch, tmp_path):
    """空 DB → 全 0, closed_24h=[], errors 应为 None。"""
    db_path = tmp_path / "t.db"
    _init(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))
    from api.main import app
    client = TestClient(app)
    r = client.get("/api/v5/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["signals_24h"] == 0
    assert body["pnl_total_usdt"] == 0
    assert body["active_count"] == 0
    assert body["closed_24h"] == []
    assert body.get("errors") in (None, {}, )


def test_summary_aggregates_paper_and_live(monkeypatch, tmp_path):
    """seed 2 paper CLOSED (pnl 5, -1) + 2 live CLOSED (pnl 3, 4) + 1 paper OPEN + 2 live OPEN
    → pnl_total_usdt=11, active_count=3, closed_24h=4, win_rate=3/4。"""
    db_path = tmp_path / "t.db"
    _init(str(db_path))
    conn = sqlite3.connect(str(db_path))
    now = "datetime('now')"
    # signals: 3 in 24h (2 should_trade, 1 executed, 1 blocked with reason)
    conn.execute(f"INSERT INTO trade_scores_v5 (symbol, created_at, should_trade, executed, block_reason) VALUES ('A', {now}, 1, 1, NULL)")
    conn.execute(f"INSERT INTO trade_scores_v5 (symbol, created_at, should_trade, executed, block_reason) VALUES ('B', {now}, 1, 0, NULL)")
    conn.execute(f"INSERT INTO trade_scores_v5 (symbol, created_at, should_trade, executed, block_reason) VALUES ('C', {now}, 0, 0, 'SIGNAL_REVERSE')")
    # paper CLOSED
    conn.execute(f"INSERT INTO paper_trades (symbol, side, status, entry_time, exit_time, pnl_usdt, pnl_pct) VALUES ('P1', 'LONG', 'CLOSED', {now}, {now}, 5.0, 0.02)")
    conn.execute(f"INSERT INTO paper_trades (symbol, side, status, entry_time, exit_time, pnl_usdt, pnl_pct) VALUES ('P2', 'SHORT', 'CLOSED', {now}, {now}, -1.0, -0.005)")
    # live CLOSED
    conn.execute(f"INSERT INTO positions_v5 (symbol, side, status, entry_time, exit_time, pnl_usdt, pnl_pct) VALUES ('L1', 'LONG', 'CLOSED', {now}, {now}, 3.0, 0.015)")
    conn.execute(f"INSERT INTO positions_v5 (symbol, side, status, entry_time, exit_time, pnl_usdt, pnl_pct) VALUES ('L2', 'SHORT', 'CLOSED', {now}, {now}, 4.0, 0.02)")
    # paper OPEN
    conn.execute(f"INSERT INTO paper_trades (symbol, side, status, entry_time) VALUES ('PO1', 'LONG', 'OPEN', {now})")
    # live OPEN
    conn.execute(f"INSERT INTO positions_v5 (symbol, side, status, entry_time) VALUES ('LO1', 'LONG', 'OPEN', {now})")
    conn.execute(f"INSERT INTO positions_v5 (symbol, side, status, entry_time) VALUES ('LO2', 'SHORT', 'OPEN', {now})")
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", str(db_path))

    from api.main import app
    client = TestClient(app)
    r = client.get("/api/v5/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["signals_24h"] == 3
    assert body["signals_passed_and"] == 2
    assert body["signals_executed"] == 1
    assert body["signals_block_counts"].get("SIGNAL_REVERSE") == 1
    assert body["pnl_total_usdt"] == 11.0        # 5 + -1 + 3 + 4
    assert body["active_count"] == 3              # paper 1 + live 2
    assert len(body["closed_24h"]) == 4
    assert body["win_rate_24h"] == 0.75           # 3 wins / 4


def test_summary_hours_out_of_range_422(monkeypatch, tmp_path):
    """hours=0 或 hours>720 → 422。"""
    db_path = tmp_path / "t.db"
    _init(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))
    from api.main import app
    client = TestClient(app)
    assert client.get("/api/v5/dashboard/summary?hours=0").status_code == 422
    assert client.get("/api/v5/dashboard/summary?hours=1000").status_code == 422
