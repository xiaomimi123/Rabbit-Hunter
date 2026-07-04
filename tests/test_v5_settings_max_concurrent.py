"""Batch 18 Finding 18: SettingsPage 同时活仓上限 后端 API 契约测试。"""
import sqlite3
from fastapi.testclient import TestClient


def _init(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE system_settings (
            key TEXT PRIMARY KEY, value TEXT,
            created_at TEXT, updated_at TEXT
        );
    ''')
    conn.commit()
    conn.close()


def test_get_settings_default_v5_max_concurrent(monkeypatch, tmp_path):
    """system_settings 无 v5_max_concurrent → get_settings 返 default 3。"""
    db_path = tmp_path / "t.db"
    _init(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))
    from api.main import app
    client = TestClient(app)
    r = client.get("/api/v5/settings")
    assert r.status_code == 200
    assert r.json()["v5_max_concurrent"] == 3


def test_patch_v5_max_concurrent_writes_system_settings(monkeypatch, tmp_path):
    """PATCH v5_max_concurrent=5 → system_settings 有该 key,GET 返 5。"""
    db_path = tmp_path / "t.db"
    _init(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))
    from api.main import app
    client = TestClient(app)
    r = client.patch("/api/v5/settings", json={"v5_max_concurrent": 5})
    assert r.status_code == 200
    assert r.json()["v5_max_concurrent"] == 5

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT value FROM system_settings WHERE key='v5_max_concurrent'").fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "5"


def test_patch_v5_max_concurrent_rejects_out_of_range(monkeypatch, tmp_path):
    """PATCH v5_max_concurrent=100 → HTTP 422,未写入。"""
    db_path = tmp_path / "t.db"
    _init(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))
    from api.main import app
    client = TestClient(app)
    r = client.patch("/api/v5/settings", json={"v5_max_concurrent": 100})
    assert r.status_code == 422

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT value FROM system_settings WHERE key='v5_max_concurrent'").fetchone()
    conn.close()
    assert row is None
