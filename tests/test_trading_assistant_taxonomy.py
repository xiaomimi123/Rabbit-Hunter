"""trading_assistant.decide 在 candidate 命中 failure_taxonomy 时直接拒绝。"""
import sqlite3
import tempfile
import pytest
from unittest.mock import AsyncMock

from v5_types import AIResult, Decision, EnrichedItem, Indicators, RiskPlan


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _make_objects(side="SHORT", delta_pct=0.005, rsi=72.0,
                   macd_hist_4h=-0.003):
    enriched = EnrichedItem(
        symbol="HUSDT", current_price=0.166, delta_15m_pct=delta_pct,
        volume_24h_usdt=5e7, klines_15m=[], klines_4h=[],
    )
    indicators = Indicators(
        rsi_15m=rsi, macd_15m=0, macd_signal_15m=0,
        macd_hist_15m=-0.0012, macd_hist_prev_15m=0.0008,
        rsi_4h=68.0, macd_hist_4h=macd_hist_4h,
        atr_15m=0.0015,
    )
    decision = Decision(should_trade=True, side=side,
                         reasoning="rsi + macd", block_reason=None)
    risk = RiskPlan(entry_price=0.166, sl_price=0.169, tp_price=0.162,
                     size_usdt=15, leverage=10, expected_rr=1.5)
    return enriched, indicators, decision, risk


@pytest.mark.asyncio
async def test_decide_returns_taxonomy_block_when_chase_after_3pct(db, monkeypatch):
    """delta_15m_pct=0.03 → chase_after_3pct_move 命中 → AI 不调用,返回 execute=False。"""
    from scripts.ai.trading_assistant import TradingAssistant

    enriched, indicators, decision, risk = _make_objects(delta_pct=0.03)
    ai = TradingAssistant()
    ai.client = object()    # 让客户端非 None
    ai._decide_via_chat = AsyncMock()    # spy — 不应被调用

    result = await ai.decide(enriched, indicators, decision, risk)
    assert result.execute is False
    assert "FAILURE_MODE" in (result.reasoning or "")
    assert "chase_after_3pct_move" in (result.reasoning or "")
    ai._decide_via_chat.assert_not_called()


@pytest.mark.asyncio
async def test_decide_proceeds_when_no_taxonomy_match(db, monkeypatch):
    """clean candidate → 走原 AI 路径。"""
    from scripts.ai.trading_assistant import TradingAssistant

    # SHORT + macd_hist_4h 同方向(负数)→ no 4h-against trigger
    # delta_15m_pct 小 → no chase trigger
    enriched, indicators, decision, risk = _make_objects(
        delta_pct=0.005, rsi=72.0, macd_hist_4h=-0.003,
    )

    ai = TradingAssistant()
    ai.client = object()
    fake_result = AIResult(execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
                            size_multiplier=1.0, confidence=0.7,
                            reasoning="proceed")
    ai._decide_via_chat = AsyncMock(return_value=fake_result)

    result = await ai.decide(enriched, indicators, decision, risk)
    assert result.execute is True
    ai._decide_via_chat.assert_called_once()


@pytest.mark.asyncio
async def test_decide_skips_taxonomy_for_manual_strategy(db, monkeypatch):
    """v5_manual 单豁免 taxonomy(用户主动开,跟自动单不同纪律)。"""
    from scripts.ai.trading_assistant import TradingAssistant

    enriched, indicators, decision, risk = _make_objects(delta_pct=0.03)
    ai = TradingAssistant()
    ai.client = object()
    fake_result = AIResult(execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
                            size_multiplier=1.0, confidence=0.7,
                            reasoning="manual override")
    ai._decide_via_chat = AsyncMock(return_value=fake_result)

    result = await ai.decide(enriched, indicators, decision, risk,
                              strategy_id="v5_manual")
    assert result.execute is True
    ai._decide_via_chat.assert_called_once()
