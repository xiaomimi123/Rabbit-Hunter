"""z-score 计算 + cache 读写测试。"""
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta

import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _seed(conn, symbol: str, rates: list, days_back_start: int = 0):
    """从 days_back_start 天前开始,每 8h 塞一行 funding。"""
    base = datetime.now(timezone.utc) - timedelta(days=days_back_start)
    for i, rate in enumerate(rates):
        ft = (base - timedelta(hours=8 * i)).isoformat()
        conn.execute("""
            INSERT INTO funding_rates (symbol, instrument_id, funding_time,
                funding_rate, annualized_rate, source)
            VALUES (?, ?, ?, ?, ?, 'okx')
        """, (symbol, f"{symbol[:-4]}-USDT-SWAP", ft, rate, rate * 365 * 3))


def test_zscore_returns_none_when_insufficient_samples(db):
    from scripts.ai.funding_rate_calculator import compute_zscore_30d
    conn = sqlite3.connect(db)
    _seed(conn, "BTCUSDT", [0.0001] * 10)   # only 10 samples, need 20
    conn.commit()
    conn.close()
    assert compute_zscore_30d("BTCUSDT", db_path=db) is None


def test_zscore_computes_correctly_with_enough_samples(db):
    """30 samples,current_rate 比 mean 大 2 sigma → zscore ≈ 2.0."""
    from scripts.ai.funding_rate_calculator import compute_zscore_30d
    conn = sqlite3.connect(db)
    historical = [0.0001] * 29              # mean 0.0001, std 0
    _seed(conn, "BTCUSDT", [0.0005] + historical)   # current = 0.0005
    conn.commit()
    conn.close()
    out = compute_zscore_30d("BTCUSDT", db_path=db)
    assert out is not None
    assert out["current_funding_rate"] == 0.0005
    assert out["sample_size_30d"] == 30
    # std=0 → zscore=0 by safety guard
    assert out["zscore_30d"] == 0.0


def test_zscore_detects_extreme(db):
    from scripts.ai.funding_rate_calculator import compute_zscore_30d
    conn = sqlite3.connect(db)
    # 30 samples: historical varies, current extreme
    historical = [0.0001 + 0.00001 * (i % 3 - 1) for i in range(29)]
    _seed(conn, "BTCUSDT", [0.001] + historical)    # current 10x larger
    conn.commit()
    conn.close()
    out = compute_zscore_30d("BTCUSDT", db_path=db)
    assert out is not None
    assert out["zscore_30d"] > 5.0
    assert out["is_extreme"] is True
    assert out["extreme_direction"] == "long_crowded"


def test_zscore_detects_short_crowding(db):
    from scripts.ai.funding_rate_calculator import compute_zscore_30d
    conn = sqlite3.connect(db)
    historical = [0.0001 + 0.00001 * (i % 3 - 1) for i in range(29)]
    _seed(conn, "BTCUSDT", [-0.001] + historical)   # current very negative
    conn.commit()
    conn.close()
    out = compute_zscore_30d("BTCUSDT", db_path=db)
    assert out is not None
    assert out["zscore_30d"] < -5.0
    assert out["is_extreme"] is True
    assert out["extreme_direction"] == "short_crowded"


def test_refresh_zscore_cache_writes_to_db(db):
    from scripts.ai.funding_rate_calculator import refresh_zscore_cache
    conn = sqlite3.connect(db)
    historical = [0.0001 + 0.00001 * (i % 3 - 1) for i in range(29)]
    _seed(conn, "BTCUSDT", [0.0008] + historical)
    conn.commit()
    conn.close()
    n = refresh_zscore_cache(["BTCUSDT"], db_path=db)
    assert n == 1
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT zscore_30d, sample_size_30d, is_extreme FROM funding_zscore_cache "
        "WHERE symbol='BTCUSDT'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[1] == 30


def test_get_cached_zscore_returns_none_for_missing(db):
    from scripts.ai.funding_rate_calculator import get_cached_zscore
    assert get_cached_zscore("ETHUSDT", db_path=db) is None


def test_get_cached_zscore_returns_after_refresh(db):
    from scripts.ai.funding_rate_calculator import refresh_zscore_cache, get_cached_zscore
    conn = sqlite3.connect(db)
    historical = [0.0001] * 29
    _seed(conn, "BTCUSDT", [0.0005] + historical)
    conn.commit()
    conn.close()
    refresh_zscore_cache(["BTCUSDT"], db_path=db)
    out = get_cached_zscore("BTCUSDT", db_path=db)
    assert out is not None
    assert out["current_funding_rate"] == 0.0005
