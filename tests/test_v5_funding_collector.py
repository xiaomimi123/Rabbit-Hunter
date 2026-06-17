"""V5FundingCollector 进程测试 — mock OKX HTTP + DB 验证."""
import asyncio
import sqlite3
import tempfile
from unittest.mock import patch

import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def test_fetch_tick_writes_to_funding_rates(db):
    """mock fetch_funding_history → tick 写入 funding_rates."""
    from scripts.tasks.v5_funding_collector import V5FundingCollector

    fake_history = [
        {"symbol": "BTCUSDT", "instrument_id": "BTC-USDT-SWAP",
         "funding_time": "2026-06-17T08:00:00+00:00",
         "funding_rate": 0.0001, "annualized_rate": 0.1095, "settled_rate": 0.0001},
        {"symbol": "BTCUSDT", "instrument_id": "BTC-USDT-SWAP",
         "funding_time": "2026-06-17T00:00:00+00:00",
         "funding_rate": 0.00008, "annualized_rate": 0.0876, "settled_rate": 0.00008},
    ]

    with patch("scripts.tasks.v5_funding_collector.fetch_funding_history",
                return_value=fake_history):
        worker = V5FundingCollector(db_path=db, symbols=["BTCUSDT"])
        asyncio.run(worker._fetch_tick())

    conn = sqlite3.connect(db)
    n = conn.execute(
        "SELECT COUNT(*) FROM funding_rates WHERE symbol='BTCUSDT'"
    ).fetchone()[0]
    conn.close()
    assert n == 2


def test_fetch_tick_idempotent_on_duplicate(db):
    from scripts.tasks.v5_funding_collector import V5FundingCollector
    fake = [{"symbol": "BTCUSDT", "instrument_id": "BTC-USDT-SWAP",
              "funding_time": "2026-06-17T08:00:00+00:00",
              "funding_rate": 0.0001, "annualized_rate": 0.1095, "settled_rate": None}]

    with patch("scripts.tasks.v5_funding_collector.fetch_funding_history",
                return_value=fake):
        worker = V5FundingCollector(db_path=db, symbols=["BTCUSDT"])
        asyncio.run(worker._fetch_tick())
        asyncio.run(worker._fetch_tick())   # 第二次跑

    conn = sqlite3.connect(db)
    n = conn.execute(
        "SELECT COUNT(*) FROM funding_rates WHERE symbol='BTCUSDT'"
    ).fetchone()[0]
    conn.close()
    assert n == 1


def test_fetch_tick_swallows_api_error(db):
    """单个 symbol 出错不阻塞其他 symbol."""
    from scripts.tasks.v5_funding_collector import V5FundingCollector

    call_count = {"n": 0}

    def fake_fetch(symbol, **kwargs):
        call_count["n"] += 1
        if symbol == "BTCUSDT":
            raise ValueError("OKX error 50001")
        return [{"symbol": symbol, "instrument_id": f"{symbol[:-4]}-USDT-SWAP",
                  "funding_time": "2026-06-17T08:00:00+00:00",
                  "funding_rate": 0.0001, "annualized_rate": 0.1095,
                  "settled_rate": None}]

    with patch("scripts.tasks.v5_funding_collector.fetch_funding_history",
                side_effect=fake_fetch):
        worker = V5FundingCollector(db_path=db, symbols=["BTCUSDT", "ETHUSDT"])
        asyncio.run(worker._fetch_tick())

    assert call_count["n"] == 2
    conn = sqlite3.connect(db)
    btc = conn.execute("SELECT COUNT(*) FROM funding_rates WHERE symbol='BTCUSDT'").fetchone()[0]
    eth = conn.execute("SELECT COUNT(*) FROM funding_rates WHERE symbol='ETHUSDT'").fetchone()[0]
    conn.close()
    assert btc == 0
    assert eth == 1


def test_zscore_tick_refreshes_cache(db):
    """注入 30 条 BTC funding,跑 _zscore_tick → cache 有数据."""
    from scripts.tasks.v5_funding_collector import V5FundingCollector
    from datetime import datetime, timezone, timedelta

    conn = sqlite3.connect(db)
    base = datetime.now(timezone.utc)
    for i in range(30):
        ft = (base - timedelta(hours=8 * i)).isoformat()
        conn.execute("""
            INSERT INTO funding_rates (symbol, instrument_id, funding_time,
                funding_rate, annualized_rate, source)
            VALUES ('BTCUSDT', 'BTC-USDT-SWAP', ?, 0.0001, 0.1095, 'okx')
        """, (ft,))
    conn.commit()
    conn.close()

    worker = V5FundingCollector(db_path=db, symbols=["BTCUSDT"])
    asyncio.run(worker._zscore_tick())

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT zscore_30d, sample_size_30d FROM funding_zscore_cache WHERE symbol='BTCUSDT'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[1] == 30


def test_backfill_uses_larger_limit(db):
    """backfill 一次拉 100,跟普通 tick 拉 5 区分."""
    from scripts.tasks.v5_funding_collector import V5FundingCollector

    captured_limits = []

    def fake_fetch(symbol, **kwargs):
        captured_limits.append(kwargs.get("limit"))
        return []

    with patch("scripts.tasks.v5_funding_collector.fetch_funding_history",
                side_effect=fake_fetch):
        worker = V5FundingCollector(db_path=db, symbols=["BTCUSDT"])
        asyncio.run(worker.backfill_history(limit=100))

    assert captured_limits == [100]
