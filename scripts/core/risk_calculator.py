"""
Risk calculation utilities - canonical implementation.

Consolidated from scripts/v41_risk_manager.py (V4.1).
All new code should import from here; v41_risk_manager.py is a thin
backward-compatibility re-export wrapper.

Functions:
    calculate_atr               – Average True Range (ATR)
    calculate_position_size     – Risk-parity position sizing
    check_funding_trap          – Funding-rate short trap filter
    get_atr_multiplier          – Phase-aware ATR multiplier
    calculate_chandelier_stop   – Chandelier Exit stop price
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


def calculate_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    length: int = 14,
) -> Optional[float]:
    """
    Calculate Average True Range (ATR).

    Args:
        highs, lows, closes: OHLCV lists (oldest → newest).
        length: ATR period (default 14).

    Returns:
        ATR value, or None if data is insufficient or ATR ≤ 0.
    """
    min_len = min(len(highs), len(lows), len(closes))
    if min_len < length + 1:
        return None

    h = np.array(highs[-min_len:])
    l = np.array(lows[-min_len:])
    c = np.array(closes[-min_len:])

    tr_list = [
        max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        for i in range(1, len(h))
    ]
    if len(tr_list) < length:
        return None

    atr = float(np.mean(tr_list[-length:]))
    return atr if atr > 0 else None


def calculate_position_size(
    account_balance: float,
    entry_price: float,
    stop_loss_price: float,
    risk_per_trade: float = 0.015,
    is_short: bool = False,
) -> float:
    """
    Risk-parity position sizing.

    Core idea: fix account-level risk (e.g. 1.5 %); the wider the stop
    distance, the smaller the position.

    Short positions use half the risk ratio to account for unlimited
    upside risk and slippage.

    Args:
        account_balance:  Total account balance in quote currency.
        entry_price:      Trade entry price.
        stop_loss_price:  Stop-loss price.
        risk_per_trade:   Fraction of balance to risk (default 0.015 = 1.5 %).
        is_short:         If True, effective risk is halved.

    Returns:
        Position size in base currency units; 0.0 if inputs are invalid.
    """
    if account_balance <= 0 or entry_price <= 0:
        return 0.0

    effective_risk = risk_per_trade * (0.5 if is_short else 1.0)
    distance = abs(entry_price - stop_loss_price)
    if distance <= 0:
        return 0.0

    return (account_balance * effective_risk) / distance


def check_funding_trap(
    funding_rate: float,
    is_short: bool = False,
) -> Tuple[bool, str]:
    """
    Funding-rate short-trap filter (V4.2).

    Rule: block short entries when funding_rate < -0.01 % (negative rate
    indicates crowded shorts; risk of short squeeze).

    Returns:
        (is_allowed, reason_string)
    """
    if not is_short:
        return True, "非空头交易，无需检查费率陷阱"
    if funding_rate < -0.0001:
        return False, f"费率陷阱：当前费率 {funding_rate*100:.3f}% < -0.01%，禁止做空（防逼空）"
    return True, "费率检查通过"


def get_atr_multiplier(
    phase: str,
    phase_age_percent: Optional[float] = None,
    is_short: bool = False,
) -> Optional[float]:
    """
    Phase-aware ATR multiplier for Chandelier Exit sizing.

    Long mapping (V4.1):
        P3A, age < 30 % → 2.5  (early breakout, wide stop)
        P3A, 30-70 %    → 2.0  (trend following)
        P3A, > 70 %     → 1.8  (approaching P3B)
        P3B             → 1.5  (late stage, tight stop)
        others          → None (no entry allowed)

    Short (V4.2): P4 only → 1.5

    Returns:
        ATR multiplier k, or None if entry is not allowed for this phase.
    """
    from whale_detector import PHASE_P3A, PHASE_P3B, PHASE_P4  # type: ignore

    if is_short:
        return 1.5 if phase == PHASE_P4 else None

    if phase == PHASE_P3A:
        if phase_age_percent is None:
            return 2.0
        if phase_age_percent < 30:
            return 2.5
        if phase_age_percent <= 70:
            return 2.0
        return 1.8
    if phase == PHASE_P3B:
        return 1.5
    return None


def calculate_chandelier_stop(
    entry_price: float,
    atr_value: float,
    atr_multiplier: float,
    highest_high_since_entry: Optional[float] = None,
    current_stop: Optional[float] = None,
    is_long: bool = True,
) -> float:
    """
    Chandelier Exit stop price.

    Long:  stop = max(Highest_High - k*ATR, current_stop)  [ratchet up only]
    Short: stop = min(Lowest_Low  + k*ATR, current_stop)   [ratchet down only]

    Falls back to ±2 % fixed stop when ATR is invalid.
    """
    if atr_value <= 0 or atr_multiplier <= 0:
        return entry_price * (0.98 if is_long else 1.02)

    if is_long:
        ref = highest_high_since_entry if (highest_high_since_entry and highest_high_since_entry > entry_price) else entry_price
        new_stop = ref - atr_multiplier * atr_value
        return max(new_stop, current_stop) if current_stop is not None else new_stop
    else:
        ref = highest_high_since_entry if highest_high_since_entry is not None else entry_price
        new_stop = ref + atr_multiplier * atr_value
        return min(new_stop, current_stop) if current_stop is not None else new_stop


__all__ = [
    "calculate_atr",
    "calculate_position_size",
    "check_funding_trap",
    "get_atr_multiplier",
    "calculate_chandelier_stop",
]
