"""Hard guardrails applied to AI decisions regardless of what the AI proposes.

These rules are always enforced and cannot be overridden by the AI.
"""
from dataclasses import dataclass, field

# Absolute limits
SL_MIN = 1.2
SL_MAX = 3.0
TP_MIN = 2.0
TP_MAX = 6.0
SIZE_MIN = 0.3
SIZE_MAX = 1.2
MIN_RR_RATIO = 1.5  # TP distance must be at least 1.5x SL distance


@dataclass
class GuardrailResult:
    sl_multiplier: float
    tp_multiplier: float
    size_multiplier: float
    adjustments: list = field(default_factory=list)


def apply_guardrails(
    sl_mult: float,
    tp_mult: float,
    size_mult: float,
) -> GuardrailResult:
    """Clamp AI-proposed parameters to safe ranges and enforce min R:R ratio."""
    adjustments = []

    # Clamp SL
    sl = max(SL_MIN, min(SL_MAX, float(sl_mult)))
    if round(sl, 3) != round(float(sl_mult), 3):
        adjustments.append(f"SL clamped {sl_mult:.2f}→{sl:.2f}")

    # Clamp TP
    tp = max(TP_MIN, min(TP_MAX, float(tp_mult)))
    if round(tp, 3) != round(float(tp_mult), 3):
        adjustments.append(f"TP clamped {tp_mult:.2f}→{tp:.2f}")

    # Enforce minimum R:R ratio
    if tp < sl * MIN_RR_RATIO:
        tp_adjusted = round(sl * MIN_RR_RATIO, 2)
        adjustments.append(f"TP adjusted for min R:R ({MIN_RR_RATIO}x) → {tp_adjusted:.2f}")
        tp = tp_adjusted

    # Clamp size
    size = max(SIZE_MIN, min(SIZE_MAX, float(size_mult)))
    if round(size, 3) != round(float(size_mult), 3):
        adjustments.append(f"size clamped {size_mult:.2f}→{size:.2f}")

    return GuardrailResult(
        sl_multiplier=sl,
        tp_multiplier=tp,
        size_multiplier=size,
        adjustments=adjustments,
    )
