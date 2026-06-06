"""Hard guardrails applied to AI decisions regardless of what the AI proposes.

These rules are always enforced and cannot be overridden by the AI.
"""
import math
from dataclasses import dataclass, field

# Absolute limits
SL_MIN = 1.2
SL_MAX = 3.0
TP_MIN = 2.0
TP_MAX = 6.0
SIZE_MIN = 0.3
SIZE_MAX = 1.2
MIN_RR_RATIO = 1.5  # TP distance must be at least 1.5x SL distance


class GuardrailRejection(ValueError):
    """Raised when AI output is unusable (NaN, inf, wrong type, etc.) — caller must skip the trade."""


@dataclass
class GuardrailResult:
    sl_multiplier: float
    tp_multiplier: float
    size_multiplier: float
    adjustments: list = field(default_factory=list)


def _coerce_finite(name: str, raw):
    # AI may return string/list/dict/None/NaN/inf; reject anything we can't safely clamp.
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise GuardrailRejection(f"{name}={raw!r} is not numeric ({exc})")
    if math.isnan(value) or math.isinf(value):
        raise GuardrailRejection(f"{name}={raw!r} is NaN/inf")
    return value


def apply_guardrails(
    sl_mult: float,
    tp_mult: float,
    size_mult: float,
) -> GuardrailResult:
    """Clamp AI-proposed parameters to safe ranges and enforce min R:R ratio.

    Raises GuardrailRejection if any input is non-numeric, NaN, or inf —
    the caller must treat this as skip_trade, not a clamp.
    """
    adjustments = []

    sl_in = _coerce_finite("sl_multiplier", sl_mult)
    tp_in = _coerce_finite("tp_multiplier", tp_mult)
    size_in = _coerce_finite("size_multiplier", size_mult)

    # Clamp SL
    sl = max(SL_MIN, min(SL_MAX, sl_in))
    if round(sl, 3) != round(sl_in, 3):
        adjustments.append(f"SL clamped {sl_in:.2f}→{sl:.2f}")

    # Clamp TP
    tp = max(TP_MIN, min(TP_MAX, tp_in))
    if round(tp, 3) != round(tp_in, 3):
        adjustments.append(f"TP clamped {tp_in:.2f}→{tp:.2f}")

    # Enforce minimum R:R ratio
    if tp < sl * MIN_RR_RATIO:
        tp_adjusted = round(sl * MIN_RR_RATIO, 2)
        adjustments.append(f"TP adjusted for min R:R ({MIN_RR_RATIO}x) → {tp_adjusted:.2f}")
        tp = tp_adjusted

    # Clamp size
    size = max(SIZE_MIN, min(SIZE_MAX, size_in))
    if round(size, 3) != round(size_in, 3):
        adjustments.append(f"size clamped {size_in:.2f}→{size:.2f}")

    return GuardrailResult(
        sl_multiplier=sl,
        tp_multiplier=tp,
        size_multiplier=size,
        adjustments=adjustments,
    )
