"""
交易分数业务逻辑服务

包含 kill queue 去重、格式化等辅助逻辑。
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional


def parse_jsonb(value: Any, default: Any = None) -> Any:
    """将可能的字符串 JSONB 字段解析为 Python 对象。"""
    if default is None:
        default = {}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    if value is None:
        return default
    return value


def format_trade_score(record: Dict[str, Any]) -> Dict[str, Any]:
    """将数据库原始记录格式化为 TradeScoreV43Response 字典。"""
    weights = parse_jsonb(record.get("weights", {}))
    decision_policy = parse_jsonb(record.get("decision_policy", {}))

    return {
        "id": record.get("id"),
        "created_at": record.get("created_at"),
        "symbol": record.get("symbol"),
        "structure_score": float(record.get("structure_score")) if record.get("structure_score") is not None else None,
        "volatility_score": float(record.get("volatility_score")) if record.get("volatility_score") is not None else None,
        "sentiment_score": float(record.get("sentiment_score")) if record.get("sentiment_score") is not None else None,
        "manipulation_score": float(record.get("manipulation_score")) if record.get("manipulation_score") is not None else None,
        "final_score": float(record.get("final_score")) if record.get("final_score") is not None else None,
        "weights": weights,
        "weights_version": record.get("weights_version"),
        "decision_policy": decision_policy,
        "executed": record.get("executed", False),
        "reason": record.get("reason"),
    }


def map_phase(phase_raw: Optional[str]) -> str:
    """将原始阶段名称标准化为枚举格式。"""
    if not phase_raw:
        return "UNKNOWN"
    phase_upper = str(phase_raw).upper()
    if "P1" in phase_upper and ("NO_WHALE" in phase_upper or "WHALE" not in phase_upper):
        return "P1_NO_WHALE"
    if "P2" in phase_upper and "ACCUMULATION" in phase_upper:
        return "P2_ACCUMULATION"
    if "P3A" in phase_upper or "PUMP_START" in phase_upper:
        return "P3A_PUMP_START"
    if "P3B" in phase_upper or "PUMP_LATE" in phase_upper:
        return "P3B_PUMP_LATE"
    if "P4" in phase_upper or "DISTRIBUTION" in phase_upper:
        return "P4_DISTRIBUTION"
    return phase_raw  # 保留原始值（可能已是标准格式）


def extract_technical_signals(reason_text: str) -> List[str]:
    """从 reason 字段文本中提取技术信号标签。"""
    signals = []
    reason_lower = (reason_text or "").lower()
    if "golden" in reason_lower or "wick" in reason_lower:
        signals.append("golden_wick")
    if "atr" in reason_lower or "breakout" in reason_lower:
        signals.append("atr_breakout")
    if "order" in reason_lower or "block" in reason_lower:
        signals.append("order_block_break")
    if "funding" in reason_lower or "divergence" in reason_lower:
        signals.append("funding_divergence")
    return signals


def format_phase_age(phase_age_candles: Optional[Any], candle_minutes: int = 15) -> tuple:
    """
    将 K 线数转换为分钟数和格式化字符串。

    :return: (phase_age_minutes, phase_age_str)
    """
    if phase_age_candles is None:
        return None, None
    phase_age_minutes = int(phase_age_candles) * candle_minutes
    if phase_age_minutes < 0:
        phase_age_minutes = abs(phase_age_minutes)
    hours = phase_age_minutes // 60
    minutes = phase_age_minutes % 60
    phase_age_str = f"{hours:02d}:{minutes:02d}:00"
    return phase_age_minutes, phase_age_str


def format_kill_queue_item(
    record: Dict[str, Any],
    price_value: Optional[float] = None,
    change_24h: float = 0.0,
) -> Dict[str, Any]:
    """将数据库记录格式化为 kill queue 条目。"""
    weights = parse_jsonb(record.get("weights", {}))
    decision_policy = parse_jsonb(record.get("decision_policy", {}))
    features = parse_jsonb(record.get("features", {}))

    record_phase = features.get("phase") or decision_policy.get("phase") or record.get("phase")
    phase_age_candles = features.get("phase_age")

    phase_age_minutes, phase_age_str = format_phase_age(phase_age_candles)
    if phase_age_minutes is None:
        # fallback from decision_policy
        phase_age_minutes = decision_policy.get("phase_age") or record.get("phase_age")
        if phase_age_minutes is not None:
            _, phase_age_str = format_phase_age(phase_age_minutes, candle_minutes=1)

    final_score = record.get("final_score", 0.0)
    ai_score = float(final_score) * 100.0 if final_score else 0.0

    reason_text = record.get("reason", "")
    technical_signals = extract_technical_signals(reason_text)

    risk_level = "medium"
    if ai_score >= 80:
        risk_level = "low"
    elif ai_score < 65:
        risk_level = "high"

    volatility_score = record.get("volatility_score", 0.0)
    expected_move_percent = float(volatility_score) * 5.0 if volatility_score else 0.0

    phase_mapped = map_phase(record_phase)

    structure_score = record.get("structure_score")
    sent_score = record.get("sentiment_score")
    manip_score = record.get("manipulation_score")

    should_trade = decision_policy.get("should_trade", False)
    position_size_multiplier = decision_policy.get("position_size_multiplier", 0.0)
    block_reason = decision_policy.get("block_reason") or decision_policy.get("reason", "")

    # If price not fetched from market_snapshot, try features
    if (price_value is None or price_value == 0.0) and features:
        try:
            current_price = features.get("current_price") or features.get("price")
            if current_price:
                price_value = float(current_price)
        except Exception:
            pass

    return {
        "symbol": record.get("symbol", ""),
        "price": price_value or 0.0,
        "change24h": change_24h,
        "changePercent": change_24h,
        "aiScore": ai_score,
        "final_score": final_score,
        "phase": phase_mapped,
        "age": phase_age_str or "00:00:00",
        "reason": reason_text or "AI 检测到交易机会",
        "weights": {
            "structure": float(weights.get("structure", 0.35)) * 100 if isinstance(weights.get("structure"), (int, float)) else 35,
            "sentiment": float(weights.get("sentiment", 0.25)) * 100 if isinstance(weights.get("sentiment"), (int, float)) else 25,
            "volatility": float(weights.get("volatility", 0.25)) * 100 if isinstance(weights.get("volatility"), (int, float)) else 25,
            "manipulation": float(weights.get("manipulation", 0.15)) * 100 if isinstance(weights.get("manipulation"), (int, float)) else 15,
        },
        "structure_score": float(structure_score) if structure_score is not None else None,
        "volatility_score": float(volatility_score) if volatility_score else None,
        "sentiment_score": float(sent_score) if sent_score is not None else None,
        "manipulation_score": float(manip_score) if manip_score is not None else None,
        "should_trade": should_trade,
        "position_size_multiplier": float(position_size_multiplier) if position_size_multiplier else 0.0,
        "block_reason": block_reason,
        "decision_policy": decision_policy,
        "features": features,
        "phaseAge": phase_age_str,
        "ageInMinutes": phase_age_minutes,
        "phaseAgeCandles": phase_age_candles,
        "confidence": float(final_score) if final_score else None,
        "technicalSignals": technical_signals,
        "riskLevel": risk_level,
        "expectedMove": None,
        "expectedMovePercent": expected_move_percent,
        "volume24h": None,
        "liquidity": "high",
        "timestamp": record.get("created_at", datetime.now().isoformat()),
        "lastUpdated": record.get("updated_at") or record.get("created_at", datetime.now().isoformat()),
    }
