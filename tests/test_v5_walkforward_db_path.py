"""Batch 8 Finding 6: walkforward 路由 DB 定位统一到 DB_PATH env var。"""
import os


def test_db_path_reads_db_path_env(monkeypatch):
    """_db_path() 应读 DB_PATH env,与其他 API 路由一致(Finding 6)。"""
    monkeypatch.setenv("DB_PATH", "data/custom_test.db")
    monkeypatch.delenv("LOCAL_DB_PATH", raising=False)

    from api.routes import v5_walkforward
    assert v5_walkforward._db_path() == "data/custom_test.db"


def test_db_path_ignores_local_db_path_env(monkeypatch):
    """老 LOCAL_DB_PATH env 不再生效,防回归(Finding 6)。"""
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.setenv("LOCAL_DB_PATH", "data/should_be_ignored.db")

    from api.routes import v5_walkforward
    # 无 DB_PATH → fallback 到 default,不能读 LOCAL_DB_PATH
    assert v5_walkforward._db_path() == "data/rabbit_hunter.db"


def test_db_path_default_when_unset(monkeypatch):
    """两个 env 都不设时,返回 default(Finding 6)。"""
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("LOCAL_DB_PATH", raising=False)

    from api.routes import v5_walkforward
    assert v5_walkforward._db_path() == "data/rabbit_hunter.db"
