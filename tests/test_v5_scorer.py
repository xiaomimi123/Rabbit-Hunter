"""V5 Scorer process_enriched_v5 分支测试 (F3 balance=None)."""
import asyncio
import sqlite3
import sys
from unittest.mock import MagicMock


def _stub_ccxt():
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = MagicMock()


def _fake_klines(n: int = 50):
    """构造 n 条最小 kline,足够 IndicatorEngine (RSI/MACD 需 ≥ 35)。"""
    return [(i * 900_000, 0.166, 0.167, 0.165, 0.166, 100.0) for i in range(n)]


def _make_enriched():
    """构造最小 EnrichedItem。klines 30 条 flat, decide() 通常返 should_trade=False,
    我们用 monkeypatch decide 让它 True 才能触达 balance gate。"""
    _stub_ccxt()
    from scripts.v5_types import EnrichedItem
    return EnrichedItem(
        symbol="BTC/USDT",
        current_price=30000.0,
        delta_15m_pct=0.03,
        volume_24h_usdt=1_500_000_000.0,
        klines_15m=_fake_klines(),
        klines_4h=_fake_klines(),
    )


def test_process_enriched_none_balance_writes_block(tmp_path, monkeypatch):
    """balance_usdt=None → 写 trade_scores_v5 block_reason=BALANCE_UNAVAILABLE, skip 开仓。"""
    _stub_ccxt()
    from scripts.local_db import init_local_db
    from scripts.tasks import scorer

    db = str(tmp_path / "x.db")
    init_local_db(db)

    enriched = _make_enriched()

    # monkeypatch decide() 让它返 should_trade=True,才能穿过 "not should_trade" 早期 return,
    # 触达紧接其后的 balance-None gate
    from scripts.v5_types import Decision
    monkeypatch.setattr(
        scorer, "decide",
        lambda enr, ind, funding_z=None: Decision(
            should_trade=True, side="LONG",
            reasoning="test-strong-signal", block_reason=None,
        ),
    )

    paper_pm = MagicMock()
    live_pm = MagicMock()
    ai = MagicMock()

    asyncio.run(scorer.process_enriched_v5(
        enriched=enriched, ai=ai, paper_pm=paper_pm, live_pm=live_pm,
        mode="LIVE", db_path=db, balance_usdt=None,
    ))

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT block_reason FROM trade_scores_v5 WHERE symbol=?", ("BTC/USDT",)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "BALANCE_UNAVAILABLE"

    # skip 开仓 → paper_pm / live_pm 未被调
    paper_pm.open_position.assert_not_called()
    live_pm.open_position.assert_not_called()
