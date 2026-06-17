"""V5 scoring pipeline 集成测试。Mock OKX 拉 K 线 + AI,验证端到端流。"""
import asyncio
import sqlite3
import tempfile
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from tests.conftest import _build_klines


@pytest.fixture
def fresh_db():
    from scripts.local_db import init_local_db
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    init_local_db(tmp.name)
    return tmp.name


@pytest.mark.asyncio
async def test_strong_signal_writes_trade_scores_v5_and_paper_trade(fresh_db, monkeypatch):
    """构造一个必然触发 SHORT 的输入 → 验证 paper_trades + trade_scores_v5 各写一行。"""
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "60")
    monkeypatch.setenv("DB_PATH", fresh_db)
    monkeypatch.setenv("V5_USE_SYMBOL_WHITELIST", "false")  # 测试用的 TEST/USDT 不在白名单

    rising_then_drop = [100 + i * 2 for i in range(40)] + [180, 178, 176]
    klines_15m = _build_klines(rising_then_drop)
    klines_4h = _build_klines([100 + i * 1.5 for i in range(40)])

    from v5_types import AIResult
    fake_ai = MagicMock()
    fake_ai.decide = AsyncMock(return_value=AIResult(
        execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
        size_multiplier=1.0, confidence=0.7, reasoning="test"
    ))

    monkeypatch.setenv("PAPER_INITIAL_BALANCE_USDT", "1000")

    from scripts.tasks.scorer import process_enriched_v5
    from v5_types import EnrichedItem
    enriched = EnrichedItem(
        symbol="TEST/USDT", current_price=176.0, delta_15m_pct=-0.034,
        volume_24h_usdt=50_000_000, klines_15m=klines_15m, klines_4h=klines_4h,
    )

    from scripts.paper_position_manager import PaperPositionManager
    paper_pm = PaperPositionManager(db_path=fresh_db)

    await process_enriched_v5(
        enriched=enriched, ai=fake_ai, paper_pm=paper_pm, live_pm=None,
        mode="SHADOW", db_path=fresh_db, balance_usdt=1000.0,
    )

    conn = sqlite3.connect(fresh_db)
    scores = conn.execute(
        "SELECT symbol, should_trade, side, executed FROM trade_scores_v5"
    ).fetchall()
    trades = conn.execute(
        "SELECT symbol, side, status FROM paper_trades"
    ).fetchall()
    conn.close()

    assert len(scores) == 1
    assert scores[0][0] == "TEST/USDT"
    assert scores[0][1] == 1
    assert scores[0][2] == "SHORT"
    assert scores[0][3] == 1
    assert len(trades) == 1
    assert trades[0] == ("TEST/USDT", "SHORT", "OPEN")
