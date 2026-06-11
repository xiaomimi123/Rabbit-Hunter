"""V5 AI 输出限幅 — 防止 AI 给出离谱参数。

短线策略下,SL 不能太宽(扛不住扫),TP 不能太远(15min 拿不到),
size 不能超过预算或太小没意义。
"""
from v5_types import AIResult

SL_MULT_MIN, SL_MULT_MAX = 1.0, 3.0
TP_MULT_MIN, TP_MULT_MAX = 1.5, 5.0
SIZE_MULT_MIN, SIZE_MULT_MAX = 0.3, 1.2
CONFIDENCE_MIN, CONFIDENCE_MAX = 0.0, 1.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def clamp_ai_result(raw: AIResult) -> AIResult:
    """把 AI 给的参数夹在合理范围。"""
    return AIResult(
        execute=raw.execute,
        sl_multiplier=_clamp(raw.sl_multiplier, SL_MULT_MIN, SL_MULT_MAX),
        tp_multiplier=_clamp(raw.tp_multiplier, TP_MULT_MIN, TP_MULT_MAX),
        size_multiplier=_clamp(raw.size_multiplier, SIZE_MULT_MIN, SIZE_MULT_MAX),
        confidence=_clamp(raw.confidence, CONFIDENCE_MIN, CONFIDENCE_MAX),
        reasoning=raw.reasoning,
    )


__all__ = ["clamp_ai_result", "SL_MULT_MIN", "SL_MULT_MAX",
           "TP_MULT_MIN", "TP_MULT_MAX", "SIZE_MULT_MIN", "SIZE_MULT_MAX"]
