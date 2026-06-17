"""V6 funding rate schema 测试。"""
import os
import sqlite3
import tempfile
import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def test_funding_rates_table_created(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(funding_rates)").fetchall()]
    conn.close()
    for required in (
        "symbol", "instrument_id", "funding_time", "funding_rate",
        "annualized_rate", "source", "fetched_at",
    ):
        assert required in cols, f"missing: {required}"


def test_funding_rates_unique_constraint(db):
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO funding_rates (symbol, instrument_id, funding_time,
            funding_rate, annualized_rate, source)
        VALUES ('BTCUSDT', 'BTC-USDT-SWAP', '2026-06-17T00:00:00+00:00',
                0.0001, 0.1095, 'okx')
    """)
    conn.commit()
    # 同一 (symbol, funding_time, source) 重复 → IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("""
            INSERT INTO funding_rates (symbol, instrument_id, funding_time,
                funding_rate, annualized_rate, source)
            VALUES ('BTCUSDT', 'BTC-USDT-SWAP', '2026-06-17T00:00:00+00:00',
                    0.0002, 0.219, 'okx')
        """)
    conn.close()


def test_funding_zscore_cache_table_created(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(funding_zscore_cache)").fetchall()]
    conn.close()
    for required in (
        "symbol", "computed_at", "current_funding_rate", "mean_30d",
        "std_30d", "zscore_30d", "sample_size_30d",
        "is_extreme", "extreme_direction",
    ):
        assert required in cols, f"missing: {required}"


def test_trade_scores_v5_has_funding_columns(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(trade_scores_v5)").fetchall()]
    conn.close()
    assert "funding_z_score" in cols
    assert "funding_rate_8h" in cols


def test_reflections_has_funding_columns(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(reflections)").fetchall()]
    conn.close()
    assert "funding_z_score_at_entry" in cols
    assert "funding_rate_at_entry" in cols


def test_zscore_cache_pk_replaces(db):
    """同一 symbol 写两次 → 后写覆盖。"""
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO funding_zscore_cache (symbol, current_funding_rate,
            mean_30d, std_30d, zscore_30d, sample_size_30d, is_extreme)
        VALUES ('BTCUSDT', 0.0001, 0.00005, 0.0001, 0.5, 90, 0)
    """)
    conn.execute("""
        INSERT OR REPLACE INTO funding_zscore_cache (symbol, current_funding_rate,
            mean_30d, std_30d, zscore_30d, sample_size_30d, is_extreme)
        VALUES ('BTCUSDT', 0.0005, 0.00005, 0.0001, 4.5, 90, 1)
    """)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM funding_zscore_cache WHERE symbol='BTCUSDT'").fetchone()[0]
    z = conn.execute("SELECT zscore_30d FROM funding_zscore_cache WHERE symbol='BTCUSDT'").fetchone()[0]
    conn.close()
    assert n == 1
    assert z == 4.5
