"""
DEPRECATED - backward-compatibility shim.

All functions have been moved to scripts/core/risk_calculator.py.
This file only re-exports them so existing imports continue to work.
"""

from scripts.core.risk_calculator import (  # noqa: F401
    calculate_atr,
    calculate_position_size,
    check_funding_trap,
    get_atr_multiplier,
    calculate_chandelier_stop,
)

__all__ = [
    "calculate_atr",
    "calculate_position_size",
    "check_funding_trap",
    "get_atr_multiplier",
    "calculate_chandelier_stop",
]
