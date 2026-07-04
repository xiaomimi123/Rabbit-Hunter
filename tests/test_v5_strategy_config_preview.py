"""Batch 9 Finding 7: preview 端点用 paper_trades 算胜率。"""
import sqlite3
from fastapi.testclient import TestClient


def _seed_db(db_path):
    """建表 + 塞 8 条 paper_trades JOIN trade_scores_v5:
    - 3 SHORT with rsi_15m=75 (符合 overbought=70): pnl 1, 2, -1 → 2 WIN
    - 3 LONG  with rsi_15m=25 (符合 oversold=30):  pnl -1, -2, 1 → 1 WIN
    - 2 out-of-range (rsi=50), 不该出现在结果中
    """
    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE trade_scores_v5 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, created_at TEXT, rsi_15m REAL, side TEXT,
            should_trade INTEGER
        );
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, side TEXT, status TEXT, pnl REAL,
            source_score_id INTEGER
        );
    ''')
    score_rows = [
        (75, 'SHORT'), (75, 'SHORT'), (75, 'SHORT'),
        (25, 'LONG'),  (25, 'LONG'),  (25, 'LONG'),
        (50, 'SHORT'), (50, 'LONG'),
    ]
    for rsi, side in score_rows:
        conn.execute(
            "INSERT INTO trade_scores_v5 (symbol, created_at, rsi_15m, side, should_trade) "
            "VALUES (?, datetime('now'), ?, ?, 1)",
            ('BTC/USDT', rsi, side)
        )
    paper_rows = [
        ('BTC/USDT', 'SHORT', 'CLOSED', 1.0, 1),
        ('BTC/USDT', 'SHORT', 'CLOSED', 2.0, 2),
        ('BTC/USDT', 'SHORT', 'CLOSED', -1.0, 3),
        ('BTC/USDT', 'LONG',  'CLOSED', -1.0, 4),
        ('BTC/USDT', 'LONG',  'CLOSED', -2.0, 5),
        ('BTC/USDT', 'LONG',  'CLOSED', 1.0, 6),
        ('BTC/USDT', 'SHORT', 'CLOSED', 5.0, 7),
        ('BTC/USDT', 'LONG',  'CLOSED', 5.0, 8),
    ]
    for row in paper_rows:
        conn.execute(
            "INSERT INTO paper_trades (symbol, side, status, pnl, source_score_id) "
            "VALUES (?, ?, ?, ?, ?)", row
        )
    conn.commit()
    conn.close()


def test_preview_uses_paper_trades_win_rate(monkeypatch, tmp_path):
    """符合阈值的 6 条 paper_trades → win_rate=3/6=0.5, sample_n=6, data_source=paper_trades。"""
    db_path = tmp_path / "test.db"
    _seed_db(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))
    from api.main import app
    client = TestClient(app)
    r = client.post(
        "/api/v5/strategy-config/preview",
        json={"candidate_params": {"v5_rsi_overbought": 70, "v5_rsi_oversold": 30}}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sample_n"] == 6
    assert body["data_source"] == "paper_trades"
    assert body["estimated_win_rate"] == 0.5


def test_preview_no_data_falls_back_to_zero(monkeypatch, tmp_path):
    """paper_trades 为空 → win_rate=0, sample_n=0, data_source=no_data。"""
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript('''
        CREATE TABLE trade_scores_v5 (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, created_at TEXT, rsi_15m REAL, side TEXT, should_trade INTEGER);
        CREATE TABLE paper_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, side TEXT, status TEXT, pnl REAL, source_score_id INTEGER);
    ''')
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", str(db_path))
    from api.main import app
    client = TestClient(app)
    r = client.post(
        "/api/v5/strategy-config/preview",
        json={"candidate_params": {"v5_rsi_overbought": 70, "v5_rsi_oversold": 30}}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sample_n"] == 0
    assert body["data_source"] == "no_data"
    assert body["estimated_win_rate"] == 0.0


def test_preview_excludes_out_of_range_rsi(monkeypatch, tmp_path):
    """阈值 overbought=80 → 数据里 rsi=75 都不入统计,sample_n=0。"""
    db_path = tmp_path / "test.db"
    _seed_db(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))
    from api.main import app
    client = TestClient(app)
    r = client.post(
        "/api/v5/strategy-config/preview",
        json={"candidate_params": {"v5_rsi_overbought": 80, "v5_rsi_oversold": 20}}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sample_n"] == 0
    assert body["data_source"] == "no_data"
