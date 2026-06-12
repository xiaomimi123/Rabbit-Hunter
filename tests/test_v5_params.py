"""V5Params 热读层测试。"""
import sqlite3
import tempfile
import time
import pytest


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def test_env_takes_priority(monkeypatch):
    """env 设了就锁死,即使 DB 有不同值。"""
    from scripts.v5_params import get_param
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "65")
    db = _fresh_db()
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('v5_rsi_overbought', '60')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", db)
    v = get_param("v5_rsi_overbought", default=70.0, cast=float)
    assert v == 65.0   # env > DB


def test_db_takes_over_when_env_unset(monkeypatch):
    monkeypatch.delenv("V5_RSI_OVERBOUGHT", raising=False)
    db = _fresh_db()
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('v5_rsi_overbought', '68')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", db)
    from scripts.v5_params import _CACHE, get_param
    _CACHE.clear()
    v = get_param("v5_rsi_overbought", default=70.0, cast=float)
    assert v == 68.0


def test_default_when_neither_set(monkeypatch):
    from scripts.v5_params import _CACHE, get_param
    monkeypatch.delenv("V5_RSI_OVERBOUGHT", raising=False)
    db = _fresh_db()
    monkeypatch.setenv("DB_PATH", db)
    _CACHE.clear()
    v = get_param("v5_rsi_overbought", default=70.0, cast=float)
    assert v == 70.0


def test_cache_avoids_db_hit(monkeypatch):
    """同一 key 5s 内只读一次 DB。"""
    from scripts.v5_params import _CACHE, get_param
    monkeypatch.delenv("V5_RSI_OVERBOUGHT", raising=False)
    db = _fresh_db()
    monkeypatch.setenv("DB_PATH", db)
    _CACHE.clear()

    v1 = get_param("v5_rsi_overbought", default=70.0, cast=float)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('v5_rsi_overbought', '99')"
    )
    conn.commit()
    conn.close()
    v2 = get_param("v5_rsi_overbought", default=70.0, cast=float)
    assert v2 == v1


def test_invalidate_force_refresh(monkeypatch):
    """invalidate_cache 后再读会拿到新值。"""
    from scripts.v5_params import _CACHE, get_param, invalidate_cache
    monkeypatch.delenv("V5_RSI_OVERBOUGHT", raising=False)
    db = _fresh_db()
    monkeypatch.setenv("DB_PATH", db)
    _CACHE.clear()

    _ = get_param("v5_rsi_overbought", default=70.0, cast=float)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('v5_rsi_overbought', '55')"
    )
    conn.commit()
    conn.close()

    invalidate_cache()
    v = get_param("v5_rsi_overbought", default=70.0, cast=float)
    assert v == 55.0


def test_invalid_value_falls_back_to_default(monkeypatch):
    """DB 里存了不能解析的字符串 → fallback default。"""
    from scripts.v5_params import _CACHE, get_param
    monkeypatch.delenv("V5_RSI_OVERBOUGHT", raising=False)
    db = _fresh_db()
    monkeypatch.setenv("DB_PATH", db)
    _CACHE.clear()
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('v5_rsi_overbought', 'not-a-number')"
    )
    conn.commit()
    conn.close()
    v = get_param("v5_rsi_overbought", default=70.0, cast=float)
    assert v == 70.0
