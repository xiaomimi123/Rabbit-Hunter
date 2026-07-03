"""Unit tests for scripts.settings_db.read_sl_tp_fail_open."""
import sqlite3

import pytest

from scripts.settings_db import read_sl_tp_fail_open


def _make_db_with_setting(tmp_path, key: str, value: str) -> str:
    db = str(tmp_path / "settings.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE system_settings (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES (?, ?)", (key, value),
    )
    conn.commit()
    conn.close()
    return db


def _make_db_with_empty_settings(tmp_path) -> str:
    db = str(tmp_path / "settings.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE system_settings (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.commit()
    conn.close()
    return db


def test_reads_true_from_db(tmp_path, monkeypatch):
    monkeypatch.delenv("SL_TP_FAIL_OPEN", raising=False)
    db = _make_db_with_setting(tmp_path, "sl_tp_fail_open", "true")
    assert read_sl_tp_fail_open(db) is True


def test_reads_false_from_db(tmp_path, monkeypatch):
    # DB 值 = false;env 即使是 true 也不应生效（DB 优先）
    monkeypatch.setenv("SL_TP_FAIL_OPEN", "true")
    db = _make_db_with_setting(tmp_path, "sl_tp_fail_open", "false")
    assert read_sl_tp_fail_open(db) is False


def test_falls_back_to_env_when_db_missing_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SL_TP_FAIL_OPEN", "1")
    db = _make_db_with_empty_settings(tmp_path)
    assert read_sl_tp_fail_open(db) is True


def test_falls_back_to_env_when_db_unopenable(tmp_path, monkeypatch):
    monkeypatch.setenv("SL_TP_FAIL_OPEN", "yes")
    non_existent = str(tmp_path / "does_not_exist.db")
    # sqlite 会创建空的但没有 system_settings 表 → _read_setting 内部错误 → 返 None → 用 env
    assert read_sl_tp_fail_open(non_existent) is True


def test_returns_false_when_both_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("SL_TP_FAIL_OPEN", raising=False)
    db = _make_db_with_empty_settings(tmp_path)
    assert read_sl_tp_fail_open(db) is False


def test_db_priority_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SL_TP_FAIL_OPEN", "true")
    db = _make_db_with_setting(tmp_path, "sl_tp_fail_open", "false")
    assert read_sl_tp_fail_open(db) is False
