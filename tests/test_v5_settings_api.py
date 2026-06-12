"""V5 settings GET/PATCH API 测试。"""
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
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    init_local_db(tmp.name)
    conn = sqlite3.connect(tmp.name)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('system_state', 'SHADOW')")
    conn.commit()
    conn.close()
    from api.main import app
    return TestClient(app), tmp.name


def test_get_returns_default_structure(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["system_mode"] in ("SHADOW", "LIVE")
    assert "openai_api_key_masked" in data
    assert "deepseek_api_key_masked" in data
    assert data["openai_api_key_masked"] == ""
    assert data["deepseek_api_key_masked"] == ""


def test_get_masks_existing_key(app_with_db):
    client, db = app_with_db
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('openai_api_key', 'sk-abcdefghijklmnop')")
    conn.commit()
    conn.close()
    r = client.get("/api/v5/settings")
    data = r.json()
    assert data["openai_api_key_masked"].startswith("sk-")
    assert "****" in data["openai_api_key_masked"]
    assert data["openai_api_key_masked"].endswith("mnop")
    assert "abcdefghij" not in data["openai_api_key_masked"]


def test_patch_writes_settings(app_with_db):
    client, db = app_with_db
    r = client.patch("/api/v5/settings", json={
        "deepseek_api_key": "sk-deepseekxxx",
        "deepseek_enabled": True,
        "ai_fail_open": False,
    })
    assert r.status_code == 200
    conn = sqlite3.connect(db)
    rows = dict(conn.execute(
        "SELECT key, value FROM system_settings "
        "WHERE key IN ('deepseek_api_key', 'deepseek_enabled', 'ai_fail_open')"
    ).fetchall())
    conn.close()
    assert rows.get("deepseek_api_key") == "sk-deepseekxxx"
    assert rows.get("deepseek_enabled") == "true"


def test_patch_mode_change_to_live(app_with_db):
    client, _ = app_with_db
    r = client.patch("/api/v5/settings", json={"system_mode": "LIVE"})
    assert r.status_code == 200
    r2 = client.get("/api/v5/settings")
    assert r2.json()["system_mode"] == "LIVE"


def test_patch_empty_key_clears(app_with_db):
    """显式提交 "" 清空 key。"""
    client, db = app_with_db
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('openai_api_key', 'sk-old')")
    conn.commit()
    conn.close()
    r = client.patch("/api/v5/settings", json={"openai_api_key": ""})
    assert r.status_code == 200
    r2 = client.get("/api/v5/settings")
    assert r2.json()["openai_api_key_masked"] == ""
