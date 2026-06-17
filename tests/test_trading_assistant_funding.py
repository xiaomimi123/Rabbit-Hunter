"""trading_assistant 在 _decide_via_chat 的 prompt 注入 funding context."""
import sqlite3
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock

from v5_types import AIResult, Decision, EnrichedItem, Indicators, RiskPlan


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _objects():
    enriched = EnrichedItem(
        symbol="BTCUSDT", current_price=0.166, delta_15m_pct=0.005,
        volume_24h_usdt=5e7, klines_15m=[], klines_4h=[],
    )
    indicators = Indicators(
        rsi_15m=72.0, macd_15m=0, macd_signal_15m=0,
        macd_hist_15m=-0.0012, macd_hist_prev_15m=0.0008,
        rsi_4h=68.0, macd_hist_4h=-0.003,
        atr_15m=0.0015,
    )
    decision = Decision(should_trade=True, side="SHORT",
                        reasoning="rsi+macd", block_reason=None)
    risk = RiskPlan(entry_price=0.166, sl_price=0.169, tp_price=0.162,
                    size_usdt=15, leverage=10, expected_rr=1.5)
    return enriched, indicators, decision, risk


@pytest.mark.asyncio
async def test_decide_chat_prompt_includes_funding_when_cache_present(db, monkeypatch):
    """funding cache 有 BTCUSDT → AI prompt 含 funding section."""
    from scripts.ai.trading_assistant import TradingAssistant

    # 注入 funding cache
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO funding_zscore_cache (symbol, current_funding_rate,
            zscore_30d, sample_size_30d, is_extreme, extreme_direction)
        VALUES ('BTCUSDT', 0.0008, 2.5, 30, 1, 'long_crowded')
    """)
    conn.commit()
    conn.close()

    enriched, indicators, decision, risk = _objects()
    ai = TradingAssistant()
    ai.client = object()

    captured_prompts = {}

    async def fake_chat_with_capture(system_prompt, user_msg):
        captured_prompts["system"] = system_prompt
        captured_prompts["user"] = user_msg
        return AIResult(execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
                        size_multiplier=1.0, confidence=0.7, reasoning="ok")

    monkeypatch.setattr(ai, "_decide_via_chat", fake_chat_with_capture)

    await ai.decide(enriched, indicators, decision, risk)

    user_msg = captured_prompts.get("user", "")
    assert "FUNDING" in user_msg.upper() or "funding" in user_msg
    assert "2.5" in user_msg     # z-score 数字应出现
    assert "long_crowded" in user_msg or "long crowding" in user_msg.lower()


@pytest.mark.asyncio
async def test_decide_chat_prompt_omits_funding_when_no_cache(db, monkeypatch):
    """cache 空时 prompt 不应含具体 funding 数字(或 explicitly say N/A)."""
    from scripts.ai.trading_assistant import TradingAssistant

    enriched, indicators, decision, risk = _objects()
    ai = TradingAssistant()
    ai.client = object()

    captured = {}

    async def fake_chat(system_prompt, user_msg):
        captured["user"] = user_msg
        return AIResult(execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
                        size_multiplier=1.0, confidence=0.7, reasoning="ok")

    monkeypatch.setattr(ai, "_decide_via_chat", fake_chat)

    await ai.decide(enriched, indicators, decision, risk)

    user_msg = captured.get("user", "")
    # 应该 either 不出现 FUNDING block 或者明确 N/A
    if "FUNDING" in user_msg.upper():
        assert "N/A" in user_msg or "no data" in user_msg.lower()
