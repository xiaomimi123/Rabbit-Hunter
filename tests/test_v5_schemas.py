"""V5 Pydantic schemas sanity test。"""
import pytest


def test_strategy_config_response_round_trip():
    from api.schemas.v5_strategy_config import StrategyConfigResponse, ParamSpec
    r = StrategyConfigResponse(params=[
        ParamSpec(key="v5_rsi_overbought", value=70.0, default=70.0, min=60.0, max=80.0, unit="", description="开空 RSI 阈值"),
    ])
    assert r.params[0].value == 70.0
    j = r.model_dump_json()
    r2 = StrategyConfigResponse.model_validate_json(j)
    assert r2.params[0].key == "v5_rsi_overbought"


def test_settings_response_masks_keys():
    from api.schemas.v5_settings import SettingsResponse
    r = SettingsResponse(
        exchange="okx",
        openai_api_key_masked="sk-****abcd",
        openai_assistant_id=None,
        deepseek_api_key_masked="sk-****wxyz",
        deepseek_enabled=True,
        active_ai_provider="deepseek",
        active_chat_model="deepseek-chat",
        system_mode="SHADOW",
        enable_auto_trading=False,
        ai_fail_open=False,
        sl_tp_fail_open=False,
    )
    assert "****" in r.openai_api_key_masked


def test_ai_status_response():
    from api.schemas.v5_ai import AIStatusResponse
    r = AIStatusResponse(
        provider="deepseek",
        chat_model="deepseek-chat",
        healthy=True,
        last_latency_ms=7800,
        decisions_24h=142,
        rag_utilization_24h=0.78,
        rag_cases_in_db=142,
    )
    assert r.rag_utilization_24h == 0.78


def test_ai_decision_item():
    from api.schemas.v5_ai import AIDecisionItem
    d = AIDecisionItem(
        id=1, created_at="2026-06-12T10:00:00+00:00",
        symbol="H/USDT", side="SHORT",
        execute=True, confidence=0.7,
        reasoning="...", top1_distance=0.08, rag_case_count=5,
    )
    assert d.execute is True


def test_kline_response():
    from api.schemas.v5_charts import KlinesResponse, Kline
    r = KlinesResponse(symbol="H/USDT", interval="15m",
                       klines=[Kline(ts=1717200000000, open=0.166, high=0.168, low=0.165, close=0.166, volume=1000.0)])
    assert r.klines[0].close == 0.166


def test_symbol_event():
    from api.schemas.v5_charts import SymbolEvent, SymbolEventsResponse
    ev = SymbolEvent(
        event_type="entry", side="SHORT", price=0.166,
        timestamp="2026-06-12T10:00:00+00:00",
        position_id=1, reasoning="RSI 超买", rsi_15m=72.0, macd_hist_15m=-0.0005,
    )
    r = SymbolEventsResponse(symbol="H/USDT", events=[ev])
    assert r.events[0].event_type == "entry"


def test_manual_order_preview_response():
    from api.schemas.v5_manual_order import (
        ManualOrderPreviewRequest, ManualOrderPreviewResponse,
        ManualOrderDecisionSnapshot, ManualOrderRagCase,
    )
    req = ManualOrderPreviewRequest(symbol="H/USDT", side="SHORT", size_usdt=15.0)
    assert req.size_usdt == 15.0

    r = ManualOrderPreviewResponse(
        symbol="H/USDT", side="SHORT", current_price=0.166,
        indicators={"rsi_15m": 72.0, "macd_hist_15m": -0.0005, "atr_15m": 0.0015,
                    "rsi_4h": 65.0, "macd_hist_4h": 0.003},
        decision=ManualOrderDecisionSnapshot(
            should_trade=True, side="SHORT", reasoning="RSI 超买"),
        risk_plan={"entry_price": 0.166, "sl_price": 0.169, "tp_price": 0.162,
                   "size_usdt": 15.0, "leverage": 10, "expected_rr": 1.67},
        ai_result={"execute": True, "sl_multiplier": 1.8, "tp_multiplier": 2.6,
                   "size_multiplier": 1.0, "confidence": 0.7, "reasoning": "..."},
        rag_cases=[
            ManualOrderRagCase(entry_rsi_15m=73.2, entry_macd_hist_15m=-0.0006,
                               outcome="WIN", pnl_pct=0.004, exit_reason="TP_HIT", distance=0.08),
        ],
    )
    assert len(r.rag_cases) == 1


def test_manual_order_execute_request():
    from api.schemas.v5_manual_order import ManualOrderExecuteRequest
    req = ManualOrderExecuteRequest(
        symbol="H/USDT", side="SHORT", size_usdt=15.0,
        sl_multiplier=1.8, tp_multiplier=2.6, size_multiplier=1.0,
    )
    assert req.sl_multiplier == 1.8
