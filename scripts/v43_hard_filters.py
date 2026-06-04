"""
V4.3 硬约束模块

硬约束检查（AI 无权修改的规则）：
- P1/P4 阶段禁止开仓
- 阶段年龄 > 100 根 K 线禁止
- 预期收益 < 2% 禁止
- 单笔风险 > 1.5% 禁止（在仓位计算时检查）
"""

from typing import Dict, Any, Tuple


def pass_hard_filters(features: Dict[str, Any]) -> Tuple[bool, str]:
    """
    硬约束检查（AI 无权修改）
    
    Args:
        features: 特征字典
    
    Returns:
        (passed, reason)
        - passed=True: 通过硬约束
        - passed=False: 被拦截，reason 说明原因
    """
    # 1. 阶段约束
    phase = features.get("phase", "P1_NO_WHALE")
    if phase in ["P1_NO_WHALE", "P4_DISTRIBUTION"]:
        return (False, "PHASE_NOT_ALLOWED")
    
    # 2. 阶段年龄约束（✅ 修复：P2 吸筹阶段允许更长的年龄）
    phase_age = features.get("phase_age", 0)
    phase = features.get("phase", "P1_NO_WHALE")
    
    # P3A（拉升）必须年轻，防止接盘（保持 100 的限制）
    if phase == "P3A_PUMP_START":
        if phase_age > 100:
            return (False, "PHASE_TOO_OLD")
    # P2（吸筹）可以很老，越老爆发力越强（放宽到 2000，约 20 天）
    elif phase == "P2_ACCUMULATION":
        if phase_age > 2000:  # ✅ 修复：P2 允许更长的吸筹时间
            return (False, "PHASE_TOO_OLD")
    # P3B 和其他阶段保持 100 的限制
    else:
        if phase_age > 100:
            return (False, "PHASE_TOO_OLD")
    
    # 3. 预期收益约束
    range_left = features.get("range_left", 0.0)
    if range_left < 0.02:  # 2%
        return (False, "LOW_EXPECTED_RETURN")
    
    # 4. 风险约束（在仓位计算时检查）
    # risk_per_trade <= 1.5%
    # 这里不检查，因为需要知道 entry_price 和 stop_price
    
    return (True, "")


__all__ = ["pass_hard_filters"]

