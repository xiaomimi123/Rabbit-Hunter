"""V5 strategy-config GET/PATCH API 测试。"""
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
    from scripts.v5_params import _CACHE
    _CACHE.clear()
    from api.main import app
    return TestClient(app), tmp.name


def test_get_returns_defaults_when_db_empty(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/strategy-config")
    assert r.status_code == 200
    data = r.json()
    assert "params" in data
    keys = {p["key"] for p in data["params"]}
    assert "v5_rsi_overbought" in keys
    assert "v5_sl_atr_mult" in keys
    for p in data["params"]:
        assert "default" in p and "min" in p and "max" in p


def test_get_returns_db_value_when_set(app_with_db):
    client, db = app_with_db
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO system_settings (key, value) VALUES ('v5_rsi_overbought', '65')")
    conn.commit()
    conn.close()
    r = client.get("/api/v5/strategy-config")
    data = r.json()
    rsi_p = next(p for p in data["params"] if p["key"] == "v5_rsi_overbought")
    assert rsi_p["value"] == 65.0


def test_patch_writes_db_and_invalidates_cache(app_with_db):
    client, db = app_with_db
    client.get("/api/v5/strategy-config")
    r = client.patch("/api/v5/strategy-config", json={
        "updates": {"v5_rsi_overbought": 68, "v5_max_concurrent": 5}
    })
    assert r.status_code == 200
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT value FROM system_settings WHERE key='v5_rsi_overbought' "
        "ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row[0] == "68"
    r2 = client.get("/api/v5/strategy-config")
    data = r2.json()
    rsi_p = next(p for p in data["params"] if p["key"] == "v5_rsi_overbought")
    assert rsi_p["value"] == 68.0


def test_patch_rejects_unknown_key(app_with_db):
    client, _ = app_with_db
    r = client.patch("/api/v5/strategy-config", json={
        "updates": {"unknown_key": 99}
    })
    assert r.status_code == 400
    assert "unknown" in r.text.lower()


def test_patch_rejects_out_of_range(app_with_db):
    client, _ = app_with_db
    r = client.patch("/api/v5/strategy-config", json={
        "updates": {"v5_rsi_overbought": 90}
    })
    assert r.status_code == 400


def test_preview_returns_estimates(app_with_db):
    """无论 ai_training_data 数据多少,/preview 都返回结构化结果。"""
    client, _ = app_with_db
    r = client.post(
        "/api/v5/strategy-config/preview",
        json={"candidate_params": {"v5_rsi_overbought": 65}},
    )
    assert r.status_code == 200
    data = r.json()
    assert "estimated_hourly_entries" in data
    assert "estimated_win_rate" in data
    assert "sample_days" in data
