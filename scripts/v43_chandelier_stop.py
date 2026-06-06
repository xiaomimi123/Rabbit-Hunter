"""
V4.3 ATR Chandelier Stop 模块

ATR Chandelier Trailing Stop：
- 止损只上移，不下移
- 跟随最高价动态调整
- 使用 ATR 作为波动率基准
- ⚠️ ATR Shock Guard：防止异常拉盘/插针导致止损被合法上移
"""

from typing import Dict, Any, Optional, List


def dynamic_k_by_phase(phase: str, phase_age: int) -> float:
    """
    根据阶段和年龄动态计算 k 值
    
    阶段	k值	说明
    P3A early	2.5	早期，给更大空间
    P3A mid	2.0	中期，适中
    P3B	1.5	后期，收紧止损
    
    Args:
        phase: 市场阶段
        phase_age: 阶段年龄（K 线根数）
    
    Returns:
        k: ATR 倍数
    """
    if phase == "P3A_PUMP_START":
        if phase_age < 20:
            return 2.5  # P3A early
        else:
            return 2.0  # P3A mid
    elif phase == "P3B_PUMP_LATE":
        return 1.5
    else:
        return 2.0  # 默认


def initialize_position(
    features: Dict[str, Any],
    price: float,
    atr: float,
    side: str = "LONG",
) -> Dict[str, Any]:
    """
    开仓时初始化止损（v45：side-aware，支持 LONG/SHORT 对称数学）

    LONG:  stop = price - k * atr，跟踪 highest_price
    SHORT: stop = price + k * atr，跟踪 lowest_price

    Args:
        features: 特征字典
        price: 当前价格
        atr: ATR 值
        side: "LONG" 或 "SHORT"（默认 LONG 保持向后兼容）

    Returns:
        position: 持仓字典
    """
    phase = features.get("phase", "P1_NO_WHALE")
    phase_age = features.get("phase_age", 0)
    k = dynamic_k_by_phase(phase, phase_age)

    side_u = side.upper()
    if side_u == "LONG":
        stop_price = price - k * atr
    elif side_u == "SHORT":
        stop_price = price + k * atr
    else:
        raise ValueError(f"无效 side: {side}（必须是 LONG 或 SHORT）")

    return {
        "entry_price": price,
        "stop_price": stop_price,
        "k": k,
        "side": side_u,
        # 对称初始化：LONG 跟最高，SHORT 跟最低
        "highest_price": price if side_u == "LONG" else None,
        "lowest_price":  price if side_u == "SHORT" else None,
        "phase": phase,
        "phase_age": phase_age,
        "atr_shock_detected": False,
        "atr_shock_freeze_until": 0,
        "atr_shock_atr": None,
    }


def update_chandelier_stop(
    position: Dict[str, Any],
    current_price: float,
    atr: float,
    atr_history: Optional[List[float]] = None,
    bars_since_entry: int = 0,
) -> Dict[str, Any]:
    """
    ATR Chandelier trailing stop（v45：side-aware）

    LONG:
        - 跟踪 highest_price_since_entry
        - new_stop = highest - k * effective_atr
        - 止损只**上移**（new_stop > current → update）
    SHORT:
        - 跟踪 lowest_price_since_entry
        - new_stop = lowest + k * effective_atr
        - 止损只**下移**（new_stop < current → update）— 价越跌、止损越紧

    ATR Shock Guard：ATR 短期突变 (>50%) 期间冻结 3 根 K 线，避免插针/拉盘
    把止损"合法地"挪到不利位置然后被下一根回调扫掉。方向无关。

    Args:
        position: 持仓字典（需含 side / entry_price / stop_price，建议含 highest_price 或 lowest_price）
        current_price: 当前价（替代旧的 current_high — 现在对 LONG 视为高、对 SHORT 视为低）
        atr: 当前 ATR
        atr_history: ATR 历史（用于检测突变）
        bars_since_entry: 开仓以来的 K 线数

    Returns:
        position: 更新后的持仓字典
    """
    side = (position.get("side") or "LONG").upper()
    k = position.get("k") or position.get("atr_k") or 2.0
    entry = position.get("entry_price", current_price)

    # ── 跟踪 极值（方向感知）─────────────────────────────────
    if side == "LONG":
        highest_price = max(position.get("highest_price") or entry, current_price)
        position["highest_price"] = highest_price
        reference = highest_price
    else:  # SHORT
        existing_low = position.get("lowest_price")
        lowest_price = min(existing_low if existing_low is not None else entry, current_price)
        position["lowest_price"] = lowest_price
        reference = lowest_price

    # ── ATR Shock Guard ──────────────────────────────────────
    if atr_history and len(atr_history) >= 3:
        baseline = atr_history[-3]
        atr_change_rate = (atr - baseline) / baseline if baseline > 0 else 0
        if atr_change_rate > 0.5:
            # ATR 突变期 — 冻结
            if position.get("atr_shock_freeze_until", 0) > bars_since_entry:
                return position
            position["atr_shock_freeze_until"] = bars_since_entry + 3
            position["atr_shock_detected"] = True
            position["atr_shock_atr"] = baseline
            return position

    # ── 计算 new_stop 并按方向单边 ratchet ────────────────────
    effective_atr = position.get("atr_shock_atr", atr) if position.get("atr_shock_detected", False) else atr
    current_stop = position.get("stop_price", entry)

    if side == "LONG":
        new_stop = reference - k * effective_atr
        # 单向：只上移
        if new_stop > current_stop:
            position["stop_price"] = new_stop
    else:  # SHORT
        new_stop = reference + k * effective_atr
        # 单向：只下移（止损越来越紧 → 锁定利润）
        if new_stop < current_stop:
            position["stop_price"] = new_stop

    return position


def should_exit_position(
    position: Dict[str, Any],
    current_price: float,
    current_phase: str,
) -> tuple[bool, str]:
    """
    判断是否应该出场
    
    Args:
        position: 持仓字典
        current_price: 当前价格
        current_phase: 当前市场阶段
    
    Returns:
        (should_exit, reason)
    """
    side = position.get("side", "LONG")
    entry_price = position.get("entry_price", 0)
    
    # ✅ 方式 1: ATR 止损触发
    stop_price = position.get("stop_price", entry_price)
    if side == "LONG":
        if current_price <= stop_price:
            return (True, "ATR_STOP_TRIGGERED")
    else:  # SHORT
        if current_price >= stop_price:
            return (True, "ATR_STOP_TRIGGERED")
    
    # ✅ 方式 2: Phase 从 P3 → P4（派发确认）
    if current_phase == "P4_DISTRIBUTION":
        return (True, "DISTRIBUTION_CONFIRMED")
    
    return (False, "")


"""
P3 吃到底的哲学（写进注释）

If you are shaken out before P3 ends,
you are paying tuition to the market maker.

This system exists to STOP that behavior.

核心思想：
- 市场主力会在 P3 阶段反复洗盘
- 如果你被洗出，就是在给主力"交学费"
- 本系统的存在就是为了阻止这种行为
- 通过 ATR Chandelier Stop，让止损跟随趋势上移
- 只有在趋势真正结束时（P4）才出场
"""


__all__ = [
    "dynamic_k_by_phase",
    "initialize_position",
    "update_chandelier_stop",
    "should_exit_position",
]

