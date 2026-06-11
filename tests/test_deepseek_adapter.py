"""TradingAssistant DeepSeek 适配测试 — 不调真实 API,只测 provider 解析 + 分流。

测试环境通常没装 openai 包,所以在 fixture 里把它注入到 sys.modules 作为
一个 MagicMock。trading_assistant 内部用 try/except 包裹的 import openai
会拿到我们注入的 MagicMock,我们可以直接观察它被怎么调用。
"""
import json
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from v5_types import AIResult, Decision, EnrichedItem, Indicators, RiskPlan


@pytest.fixture
def fake_openai(monkeypatch):
    """注入 fake openai 模块,返回其 AsyncOpenAI 工厂(MagicMock)。"""
    fake_module = MagicMock()
    fake_module.AsyncOpenAI = MagicMock()
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    monkeypatch.delitem(sys.modules, "scripts.ai.trading_assistant", raising=False)
    return fake_module.AsyncOpenAI


# ---------- helpers ----------

def _enriched():
    return EnrichedItem(symbol="H/USDT", current_price=0.166, delta_15m_pct=0.034,
                        volume_24h_usdt=50_000_000, klines_15m=[], klines_4h=[])


def _indicators():
    return Indicators(rsi_15m=72.0, macd_15m=0.001, macd_signal_15m=0.0005,
                      macd_hist_15m=-0.0005, macd_hist_prev_15m=0.0008,
                      rsi_4h=65.0, macd_hist_4h=0.003, atr_15m=0.0015)


def _decision():
    return Decision(should_trade=True, side="SHORT",
                    reasoning="RSI 超买 + MACD 死叉拐点", block_reason=None)


def _risk():
    return RiskPlan(entry_price=0.166, sl_price=0.169, tp_price=0.162,
                    size_usdt=15.0, leverage=10, expected_rr=1.67)


# ---------- Provider 解析 ----------

def test_provider_deepseek_when_enabled_and_key_set(monkeypatch, fake_openai):
    monkeypatch.setenv("DEEPSEEK_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-xxx")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from scripts.ai.trading_assistant import TradingAssistant
    ta = TradingAssistant()
    assert ta.provider == "deepseek"
    assert ta.chat_model == "deepseek-chat"
    assert ta._ready is True
    assert ta.assistant_id is None
    call = fake_openai.call_args
    assert "base_url" in call.kwargs
    assert "deepseek.com" in call.kwargs["base_url"]


def test_provider_openai_when_deepseek_disabled(monkeypatch, fake_openai):
    monkeypatch.setenv("DEEPSEEK_ENABLED", "false")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-xxx")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-yyy")
    monkeypatch.delenv("OPENAI_ASSISTANT_ID", raising=False)

    from scripts.ai.trading_assistant import TradingAssistant
    ta = TradingAssistant()
    assert ta.provider == "openai"
    call = fake_openai.call_args
    assert "base_url" not in call.kwargs or call.kwargs.get("base_url") is None


def test_provider_none_when_no_keys(monkeypatch, fake_openai):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_ENABLED", "false")

    from scripts.ai.trading_assistant import TradingAssistant
    ta = TradingAssistant()
    assert ta.provider is None
    assert ta.client is None


def test_deepseek_priority_over_openai(monkeypatch, fake_openai):
    """DEEPSEEK_ENABLED=true 时,即使 OPENAI_API_KEY 有,也优先 DeepSeek。"""
    monkeypatch.setenv("DEEPSEEK_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-xxx")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-yyy")

    from scripts.ai.trading_assistant import TradingAssistant
    ta = TradingAssistant()
    assert ta.provider == "deepseek"


# ---------- initialize() ----------

@pytest.mark.asyncio
async def test_initialize_skips_assistant_creation_in_deepseek_mode(monkeypatch, fake_openai):
    monkeypatch.setenv("DEEPSEEK_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-xxx")
    from scripts.ai.trading_assistant import TradingAssistant
    ta = TradingAssistant()
    ta._create_assistant = AsyncMock(side_effect=AssertionError("不应被调用"))
    await ta.initialize()


# ---------- decide() 分流 ----------

@pytest.mark.asyncio
async def test_decide_uses_chat_completions_in_deepseek_mode(monkeypatch, fake_openai):
    monkeypatch.setenv("DEEPSEEK_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")

    # 让 fake_openai() 返回的实例上 .chat.completions.create 返回 JSON 字符串
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "execute": True, "sl_multiplier": 1.5, "tp_multiplier": 2.5,
        "size_multiplier": 1.0, "confidence": 0.7,
        "reasoning": "RSI/MACD 信号清晰",
    })))]
    mock_client_inst = MagicMock()
    mock_client_inst.chat.completions.create = AsyncMock(return_value=mock_resp)
    fake_openai.return_value = mock_client_inst

    from scripts.ai.trading_assistant import TradingAssistant
    ta = TradingAssistant()
    result = await ta.decide(_enriched(), _indicators(), _decision(), _risk())

    assert isinstance(result, AIResult)
    assert result.execute is True
    assert 1.0 <= result.sl_multiplier <= 3.0
    assert mock_client_inst.chat.completions.create.called
    call_kwargs = mock_client_inst.chat.completions.create.call_args.kwargs
    assert call_kwargs.get("response_format") == {"type": "json_object"}
    assert call_kwargs.get("model") == "deepseek-chat"


@pytest.mark.asyncio
async def test_decide_uses_assistant_when_openai_with_assistant_id(monkeypatch, fake_openai):
    monkeypatch.delenv("DEEPSEEK_ENABLED", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-y")
    monkeypatch.setenv("OPENAI_ASSISTANT_ID", "asst_xxx")

    from scripts.ai.trading_assistant import TradingAssistant
    ta = TradingAssistant()
    ta._decide_via_assistant = AsyncMock(return_value={
        "execute": False, "sl_multiplier": 1.0, "tp_multiplier": 1.0,
        "size_multiplier": 0.0, "confidence": 0.3, "reasoning": "skip",
    })
    ta._decide_via_chat = AsyncMock(side_effect=AssertionError("不应走 chat 路径"))
    result = await ta.decide(_enriched(), _indicators(), _decision(), _risk())
    assert result.execute is False
    ta._decide_via_assistant.assert_awaited_once()


@pytest.mark.asyncio
async def test_decide_uses_chat_when_openai_without_assistant_id(monkeypatch, fake_openai):
    """OpenAI mode 但用户没创建 Assistant → 自动 fallback chat completions。"""
    monkeypatch.delenv("DEEPSEEK_ENABLED", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-y")
    monkeypatch.delenv("OPENAI_ASSISTANT_ID", raising=False)

    from scripts.ai.trading_assistant import TradingAssistant
    ta = TradingAssistant()
    ta._decide_via_chat = AsyncMock(return_value={
        "execute": True, "sl_multiplier": 1.2, "tp_multiplier": 2.5,
        "size_multiplier": 0.8, "confidence": 0.6, "reasoning": "ok",
    })
    ta._decide_via_assistant = AsyncMock(side_effect=AssertionError("无 assistant_id 时不应走 assistant"))
    result = await ta.decide(_enriched(), _indicators(), _decision(), _risk())
    assert result.execute is True
    ta._decide_via_chat.assert_awaited_once()


# ---------- preflight ----------

def test_preflight_accepts_deepseek_without_openai():
    from scripts.tasks.collector_main import preflight_check
    issues = preflight_check(
        enable_auto_trading=False,
        binance_api_key="", okx_api_key="",
        openai_key="", ai_enabled=True,
        deepseek_key="sk-xxx", deepseek_enabled=True,
    )
    assert issues == []


def test_preflight_fails_when_neither_provider_set():
    from scripts.tasks.collector_main import preflight_check
    issues = preflight_check(
        enable_auto_trading=False,
        binance_api_key="", okx_api_key="",
        openai_key="", ai_enabled=True,
        deepseek_key="", deepseek_enabled=False,
    )
    assert any("DEEPSEEK" in i and "OPENAI" in i for i in issues)


def test_preflight_ok_when_ai_disabled():
    """AI 完全关时(纯规则引擎),不需要任何 provider。"""
    from scripts.tasks.collector_main import preflight_check
    issues = preflight_check(
        enable_auto_trading=False,
        binance_api_key="", okx_api_key="",
        openai_key="", ai_enabled=False,
        deepseek_key="", deepseek_enabled=False,
    )
    assert issues == []
