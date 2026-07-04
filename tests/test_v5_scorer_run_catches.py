"""V5Scorer.run 广谱 catch 现在发 ws 事件而非静默 (Finding 10)."""
import asyncio
import sqlite3
import sys
from unittest.mock import MagicMock


def _stub_ccxt():
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = MagicMock()


def test_scorer_run_catches_exception_writes_ws_event(tmp_path, monkeypatch):
    """process_enriched_v5 抛异常 → run() 捕获后写 ws_event_queue scorer_error。"""
    _stub_ccxt()
    from scripts.local_db import init_local_db
    from scripts.tasks import scorer
    from scripts.v5_types import EnrichedItem

    db = str(tmp_path / "x.db")
    init_local_db(db)

    # mock process_enriched_v5 抛异常
    async def raiser(**kwargs):
        raise RuntimeError("db locked")
    monkeypatch.setattr(scorer, "process_enriched_v5", raiser)

    # 构造 EnrichedItem — 50 flat klines 保证 indicator engine 不会先 fail
    enriched = EnrichedItem(
        symbol="BTC/USDT", current_price=30000.0,
        delta_15m_pct=0.03, volume_24h_usdt=1e9,
        klines_15m=[(i, 30000.0, 30001.0, 29999.0, 30000.0, 100.0) for i in range(50)],
        klines_4h=[(i, 30000.0, 30001.0, 29999.0, 30000.0, 100.0) for i in range(50)],
    )

    # 构造 queue + V5Scorer,queue 里塞 1 个 item;必须在 asyncio.run 内创建 queue
    # 避免 Python 3.9 "Future attached to a different loop" 问题
    async def _run_once():
        queue: asyncio.Queue = asyncio.Queue()
        queue.put_nowait(enriched)
        scorer_obj = scorer.V5Scorer(
            enriched_queue=queue,
            ai=MagicMock(),
            paper_pm=MagicMock(),
            live_pm=MagicMock(),
            mode_resolver=lambda: "SHADOW",
            balance_fetcher=lambda: 1000.0,
            db_path=db,
        )
        # 跑 run() 一次迭代;queue 空后 .get() 会阻塞,用 timeout 打断
        try:
            await asyncio.wait_for(scorer_obj.run(), timeout=0.5)
        except asyncio.TimeoutError:
            pass
    asyncio.run(_run_once())

    # 验证 ws_event_queue 有一条 scorer_error
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT payload_json FROM ws_event_queue"
    ).fetchone()
    conn.close()
    assert row is not None
    payload = row[0]
    assert "scorer_error" in payload
    assert "BTC/USDT" in payload
    assert "db locked" in payload
