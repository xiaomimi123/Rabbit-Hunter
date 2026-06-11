"""TradingAssistant V5 适配测试 — 不调真实 OpenAI,只测 prompt 构造 + 输入输出契约。"""
import pytest
from v5_types import AIResult, Decision, EnrichedItem, Indicators, RiskPlan


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


def test_build_v5_prompt_includes_all_indicators():
    from scripts.ai.prompt import build_v5_user_message
    msg = build_v5_user_message(_enriched(), _indicators(), _decision(), _risk())
    assert "RSI 15min" in msg
    assert "72.0" in msg or "72.00" in msg
    assert "MACD" in msg
    assert "SHORT" in msg
    assert "RSI 4h" in msg
    assert "ΔP" in msg or "delta" in msg.lower()


def test_build_v5_prompt_no_v43_artifacts():
    from scripts.ai.prompt import build_v5_user_message
    msg = build_v5_user_message(_enriched(), _indicators(), _decision(), _risk())
    forbidden = ["P3B", "P3A", "SNIPER", "VULTURE", "structure_score",
                 "manipulation_score", "PUMP_LATE"]
    for word in forbidden:
        assert word not in msg, f"V5 prompt 残留 V4.3 词:{word}"


def test_ai_result_dataclass_round_trip():
    r = AIResult(execute=False, sl_multiplier=1.0, tp_multiplier=1.0,
                 size_multiplier=0.0, confidence=0.3, reasoning="历史相似案例 LOSS 67%")
    assert r.execute is False
    assert r.size_multiplier == 0.0


def test_guardrails_clamps_sl_multiplier():
    from scripts.ai.guardrails import clamp_ai_result
    raw = AIResult(execute=True, sl_multiplier=0.5, tp_multiplier=5.0,
                   size_multiplier=2.0, confidence=0.8, reasoning="test")
    clamped = clamp_ai_result(raw)
    assert 1.0 <= clamped.sl_multiplier <= 3.0
    assert 1.5 <= clamped.tp_multiplier <= 5.0
    assert 0.3 <= clamped.size_multiplier <= 1.2
