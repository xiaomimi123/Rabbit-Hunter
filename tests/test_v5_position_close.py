"""Batch 12 Finding 12: v5_position_close 支持 LIVE 分支。"""
import sqlite3
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _init_schema(db_path):
    """建 paper_trades + positions_v5 最小 schema。"""
    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, side TEXT, status TEXT, entry_price REAL,
            entry_time TEXT, exit_price REAL, exit_time TEXT, exit_reason TEXT,
            pnl REAL, pnl_percent REAL, holding_hours REAL,
            current_price REAL, stop_loss REAL, take_profit REAL,
            position_size_usdt REAL, leverage INTEGER,
            strategy_id TEXT, created_at TEXT, updated_at TEXT,
            source_score_id INTEGER
        );
        CREATE TABLE positions_v5 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, side TEXT, status TEXT, entry_price REAL,
            entry_time TEXT, sl_price REAL, tp_price REAL,
            sl_attached INTEGER, tp_attached INTEGER, error_context TEXT,
            size_usdt REAL, leverage INTEGER, position_size_coins REAL,
            target_close_at TEXT, extension_count INTEGER,
            created_at TEXT, updated_at TEXT,
            exit_price REAL, exit_time TEXT, exit_reason TEXT,
            pnl_usdt REAL, pnl_pct REAL, holding_minutes REAL
        );
    ''')
    conn.commit()
    conn.close()


def test_close_paper_position_still_works(monkeypatch, tmp_path):
    """paper_trades 命中 → mode=paper, status=CLOSED(F12 不 regress paper 路径)。"""
    db_path = tmp_path / "test.db"
    _init_schema(str(db_path))
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO paper_trades (id, symbol, side, status, entry_price, entry_time) "
        "VALUES (1, 'BTC/USDT', 'LONG', 'OPEN', 50000, datetime('now'))"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", str(db_path))

    from api.main import app
    client = TestClient(app)
    r = client.post("/api/v5/positions/1/close",
                    json={"exit_price": 51000, "exit_reason": "MANUAL_USER"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "paper"
    assert body["position_id"] == 1


def test_close_live_position_uses_broker(monkeypatch, tmp_path):
    """positions_v5 命中 → 调 get_trader + V5PositionManager, mode=live。"""
    db_path = tmp_path / "test.db"
    _init_schema(str(db_path))
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO positions_v5 (id, symbol, side, status, entry_price, entry_time, "
        "size_usdt, leverage, position_size_coins) "
        "VALUES (100, 'BTC/USDT', 'LONG', 'OPEN', 50000, '2026-07-04T00:00:00+00:00', 15, 10, 0.0003)"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", str(db_path))

    mock_trader = MagicMock()
    mock_trader.close_position = MagicMock(return_value={"success": True})

    with patch("scripts.exchange_factory.get_trader", return_value=mock_trader):
        from api.main import app
        client = TestClient(app)
        r = client.post("/api/v5/positions/100/close",
                        json={"exit_price": 51000, "exit_reason": "MANUAL_USER"})

    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "live"
    assert body["position_id"] == 100
    mock_trader.close_position.assert_called_once_with("BTC/USDT")


def test_close_position_not_found_returns_404(monkeypatch, tmp_path):
    """paper + live 都无 → 404。"""
    db_path = tmp_path / "test.db"
    _init_schema(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))

    from api.main import app
    client = TestClient(app)
    r = client.post("/api/v5/positions/999/close",
                    json={"exit_price": 51000, "exit_reason": "MANUAL_USER"})
    assert r.status_code == 404
