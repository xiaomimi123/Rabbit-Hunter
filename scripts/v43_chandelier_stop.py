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
) -> Dict[str, Any]:
    """
    开仓时初始化止损
    
    Args:
        features: 特征字典
        price: 当前价格
        atr: ATR 值
    
    Returns:
        position: 持仓字典
    """
    phase = features.get("phase", "P1_NO_WHALE")
    phase_age = features.get("phase_age", 0)
    
    # 动态 k 值
    k = dynamic_k_by_phase(phase, phase_age)
    
    stop_price = price - k * atr
    
    return {
        "entry_price": price,
        "stop_price": stop_price,
        "k": k,
        "highest_price": price,  # 用于跟踪最高价
        "phase": phase,
        "phase_age": phase_age,
        "atr_shock_detected": False,
        "atr_shock_freeze_until": 0,
        "atr_shock_atr": None,
    }


def update_chandelier_stop(
    position: Dict[str, Any],
    current_high: float,
    atr: float,
    atr_history: Optional[List[float]] = None,
    bars_since_entry: int = 0,
) -> Dict[str, Any]:
    """
    ATR Chandelier  trailing stop
    
    规则：
    1. 止损只上移，不下移
    2. 新止损 = 最高价 - k * ATR
    3. 如果新止损 > 当前止损，更新
    4. ⚠️ ATR Shock Guard：防止异常拉盘/插针导致止损被合法上移
    
    Args:
        position: 持仓字典
        current_high: 当前最高价
        atr: 当前 ATR
        atr_history: ATR 历史（用于检测异常）
        bars_since_entry: 开仓后的 K 线数
    
    Returns:
        position: 更新后的持仓字典
    """
    k = position.get("k", 2.0)
    highest_price = max(position.get("highest_price", position["entry_price"]), current_high)
    position["highest_price"] = highest_price
    
    # ✅ 修复 2：第一步先检查 ATR shock（改变逻辑顺序）
    # 防止异常拉盘/插针 → ATR 突然放大 → 止损被合法上移 → 下一根回调被扫
    if atr_history and len(atr_history) >= 3:
        atr_change_rate = (atr - atr_history[-3]) / atr_history[-3] if atr_history[-3] > 0 else 0
        
        # 如果 ATR 在短时间内大幅增加（> 50%），可能是异常拉盘/插针
        if atr_change_rate > 0.5:
            # 在冻结期间，完全不动止损（直接返回）
            if position.get("atr_shock_freeze_until", 0) > bars_since_entry:
                # 仍在冻结期 → 不更新任何东西，直接返回
                return position
            else:
                # 新的冻结期开始
                position["atr_shock_freeze_until"] = bars_since_entry + 3
                position["atr_shock_detected"] = True
                position["atr_shock_atr"] = atr_history[-3]  # 保存异常前的 ATR
                # ✅ 关键：异常刚检测到时，不更新止损，直接返回
                return position
    
    # ✅ 第二步：如果不在冻结期，才计算新的止损
    # （此时 ATR 变化已经安定下来，不会被异常波动影响）
    effective_atr = position.get("atr_shock_atr", atr) if position.get("atr_shock_detected", False) else atr
    new_stop = highest_price - k * effective_atr
    
    # ⚠️ 关键：止损只上移，不下移
    if new_stop > position.get("stop_price", position["entry_price"]):
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

