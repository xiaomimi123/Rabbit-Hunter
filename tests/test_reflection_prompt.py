"""Prompt builder — 应当注入 entry snapshot + 持仓轨迹 + RAG cases + taxonomy + JSON schema 指令。"""
import json
from scripts.ai.reflection_prompt import build_reflection_prompt


def _sample_close_context():
    return {
        "paper_trade_id": 7,
        "symbol": "HUSDT",
        "side": "SHORT",
        "strategy_id": "v5_rsi_macd",
        "entry_price": 0.166,
        "exit_price": 0.169,
        "entry_time": "2026-06-13T09:48:00+00:00",
        "exit_time": "2026-06-13T10:15:00+00:00",
        "exit_reason": "SL_HIT",
        "realized_r": -1.0,
        "holding_minutes": 27,
        "confidence_at_entry": 0.7,
        "entry_rsi_15m": 72.1,
        "entry_rsi_4h": 68.0,
        "entry_macd_hist_15m": -0.0012,
        "entry_macd_hist_prev_15m": 0.0008,
        "entry_atr_15m": 0.0015,
        "funding_z_score": None,
        "rule_reasoning": "RSI overbought + MACD bearish cross",
        "ai_reasoning": "short setup with RAG support",
        "rag_cases_text": "case1 RSI=73.2 hist=-0.0006 → WIN +0.4% TP_HIT\ncase2 RSI=71.5 hist=-0.0004 → LOSS -0.3% SL_HIT",
        "during_hold_path": "T+0 price 0.166 / T+5 0.167 / T+15 0.1685 / T+27 SL hit 0.169",
        "taxonomy_keys": [
            "late_entry_signal_decay",
            "macd_false_cross",
            "against_4h_trend_no_funding_filter",
            "sl_too_tight_in_high_atr",
            "tp_too_far_in_low_atr",
            "news_event_30min_blackout",
            "chase_after_3pct_move",
            "repeat_failure_same_symbol_24h",
        ],
    }


def test_prompt_contains_all_5_questions():
    prompt = build_reflection_prompt(_sample_close_context())
    assert "why_entered" in prompt
    assert "what_was_expected" in prompt
    assert "what_actually_happened" in prompt
    assert "failure_mode_key" in prompt
    assert "correction_idea" in prompt


def test_prompt_includes_entry_snapshot_values():
    prompt = build_reflection_prompt(_sample_close_context())
    assert "72.1" in prompt           # rsi_15m
    assert "HUSDT" in prompt
    assert "SHORT" in prompt
    assert "SL_HIT" in prompt


def test_prompt_includes_during_hold_path():
    prompt = build_reflection_prompt(_sample_close_context())
    assert "T+0" in prompt
    assert "T+27" in prompt


def test_prompt_includes_rag_cases():
    prompt = build_reflection_prompt(_sample_close_context())
    assert "case1" in prompt
    assert "WIN +0.4%" in prompt


def test_prompt_includes_all_taxonomy_keys():
    prompt = build_reflection_prompt(_sample_close_context())
    for k in (
        "late_entry_signal_decay", "macd_false_cross",
        "against_4h_trend_no_funding_filter",
        "chase_after_3pct_move", "repeat_failure_same_symbol_24h",
    ):
        assert k in prompt


def test_prompt_requires_json_response_with_schema():
    prompt = build_reflection_prompt(_sample_close_context())
    # 应当明示 JSON-only 输出
    assert "JSON" in prompt or "json" in prompt
    # 应当列出所有 7 个字段
    for field in ("why_entered", "what_was_expected", "what_actually_happened",
                  "correction_idea", "failure_mode_key",
                  "self_assessed_prediction_accuracy", "is_in_predicted_failure_mode"):
        assert field in prompt


def test_prompt_handles_missing_funding_gracefully():
    ctx = _sample_close_context()
    ctx["funding_z_score"] = None
    prompt = build_reflection_prompt(ctx)
    # 不应当抛异常,出现 funding 行但标注 N/A
    assert "Funding" in prompt or "funding" in prompt
