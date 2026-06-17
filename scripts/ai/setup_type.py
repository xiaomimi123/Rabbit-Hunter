"""setup_type 派生 — 确定性,可枚举。聚合按它分桶。"""
from typing import Optional


def derive_setup_type(entry: dict) -> str:
    """从 entry snapshot 派生 setup_type。AI 不参与。

    优先级:
      1. v5_manual → manual_<side>
      2. |funding_z_score| >= 2.0 → funding_extreme_<dir>_<rsi_state>
      3. RSI×MACD×side → rsi_<state>_macd_<state>_<side>
    """
    side = (entry.get("side") or "").upper()
    side_lower = side.lower() if side else "unknown"

    if entry.get("strategy_id") == "v5_manual":
        return f"manual_{side_lower}"

    rsi = float(entry.get("rsi_15m") or 50.0)
    hist = float(entry.get("macd_hist") or 0.0)
    hist_prev = float(entry.get("macd_hist_prev") or 0.0)

    if rsi >= 70:
        rsi_state = "rsi_overbought"
    elif rsi <= 30:
        rsi_state = "rsi_oversold"
    else:
        rsi_state = "rsi_neutral"

    fz = entry.get("funding_z_score")
    if fz is not None and abs(fz) >= 2.0:
        direction = "short" if fz > 0 else "long"
        return f"funding_extreme_{direction}_{rsi_state}"

    if hist_prev < 0 and hist > 0:
        macd_state = "macd_bullish"
    elif hist_prev > 0 and hist < 0:
        macd_state = "macd_bearish"
    else:
        macd_state = "macd_extending"

    return f"{rsi_state}_{macd_state}_{side_lower}"
