"""
AI Judge Model (Rabbit Hunter 4.0)

定位：
- AI 不预测方向，只输出“是否继续参与/是否放行”的概率与建议。
- 这是一个最小可控版本：逻辑回归（Logistic Regression）。

数据：
- 训练数据来自 ai_training_data（特征）+ “未来价格表现”构造的标签。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AIJudgeResult:
    ai_score: float  # 0-1
    ai_allowed: bool
    ai_reason: str
    ai_version: str


DEFAULT_AI_VERSION = "ai_judge_lr_v1"


def _safe_float(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        return float(x)
    except Exception:  # noqa: BLE001
        return 0.0


def _encode_phase(phase: Optional[str]) -> int:
    p = (phase or "").upper()
    return {
        "P1_NO_WHALE": 1,
        "P2_ACCUMULATION": 2,
        "P3A_PUMP_START": 3,
        "P3B_PUMP_LATE": 4,
        "P4_DISTRIBUTION": 5,
    }.get(p, 0)


def _encode_kz(kz: Optional[str]) -> int:
    k = (kz or "").upper()
    return {"NONE": 0, "ACCUMULATION": 1, "SHAKEOUT": 2, "SQUEEZE": 3}.get(k, 0)


def build_feature_vector(row: Dict[str, Any]) -> list[float]:
    """
    将 ai_training_data 一行转换为数值特征向量。
    仅使用项目目前稳定产出的字段。
    """
    return [
        _safe_float(row.get("funding_rate")),
        _safe_float(row.get("long_short_ratio")),
        _safe_float(row.get("oi_change_1h")),
        _safe_float(row.get("price_change_1h")),
        _safe_float(row.get("cvd_15m")),
        _safe_float(row.get("cvd_1h")),
        _safe_float(row.get("cvd_value")),
        float(_encode_phase(row.get("market_phase"))),
        float(_encode_kz(row.get("kill_zone_signal"))),
        _safe_float(row.get("exit_clarity_score")),
        _safe_float(row.get("confidence_level")),
        1.0 if bool(row.get("price_breakout")) else 0.0,
    ]


__all__ = ["AIJudgeResult", "DEFAULT_AI_VERSION", "build_feature_vector"]


