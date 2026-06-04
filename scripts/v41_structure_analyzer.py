"""
V4.1 结构空间分析器

功能：
- 计算结构性预期收益空间（Structure_Gap）
- 实现 2% 硬门槛拦截（Pre-Trade Impact Check）
"""

from typing import Optional
import numpy as np


def find_pivot_highs(
    highs: list[float],
    window: int = 5
) -> list[float]:
    """
    查找分形高点（Pivot High）
    
    一个点被认为是 Pivot High，当且仅当：
    - 它是其左右各 window 个点中的最高点
    
    Args:
        highs: 最高价列表（从旧到新）
        window: 窗口大小，默认 5
    
    Returns:
        Pivot High 价格列表（已排序）
    """
    if len(highs) < window * 2 + 1:
        return []
    
    pivot_highs = []
    for i in range(window, len(highs) - window):
        is_pivot = True
        center_high = highs[i]
        
        # 检查左右各 window 个点
        for j in range(i - window, i + window + 1):
            if j != i and highs[j] >= center_high:
                is_pivot = False
                break
        
        if is_pivot:
            pivot_highs.append(center_high)
    
    return sorted(pivot_highs)


def calculate_structure_gap(
    current_price: float,
    highs_1h: Optional[list[float]] = None,
    lows_1h: Optional[list[float]] = None,
    closes_1h: Optional[list[float]] = None,
    use_bollinger: bool = True
) -> tuple[float, str]:
    """
    计算结构性预期收益空间（Structure_Gap）
    
    算法（多头示例）：
    1. 取过去 100 根 1H K 线的高点
    2. 找所有 Pivot High（分形高点）或使用 Bollinger Band Upper
    3. 找到大于当前价格的最接近阻力位
    4. 若不存在（历史新高），则 Next_Resistance = current_price * 1.05
    
    Args:
        current_price: 当前价格
        highs_1h: 1H K 线最高价列表（从旧到新），至少 100 根
        lows_1h: 1H K 线最低价列表（可选，用于 Bollinger）
        closes_1h: 1H K 线收盘价列表（可选，用于 Bollinger）
        use_bollinger: 是否使用 Bollinger Band 作为备选阻力位
    
    Returns:
        (structure_gap, method)
        - structure_gap: 结构空间百分比（例如 0.025 表示 2.5%）
        - method: 计算方法（"PIVOT", "BOLLINGER", "VIRTUAL"）
    """
    if current_price <= 0:
        return 0.0, "INVALID"
    
    # 方法 1: 使用 Pivot Highs
    if highs_1h and len(highs_1h) >= 20:
        # 只取最近 100 根
        recent_highs = highs_1h[-100:] if len(highs_1h) > 100 else highs_1h
        pivot_highs = find_pivot_highs(recent_highs, window=5)
        
        # 找到大于当前价格的最小阻力位
        for pivot in pivot_highs:
            if pivot > current_price:
                gap = (pivot - current_price) / current_price
                return gap, "PIVOT"
    
    # 方法 2: 使用 Bollinger Band Upper
    if use_bollinger and closes_1h and len(closes_1h) >= 20:
        try:
            from technical_indicators import calculate_bollinger_bands
            bb = calculate_bollinger_bands(closes_1h, period=20, std_dev=2.0)
            if bb and bb.get("upper"):
                upper_band = bb["upper"]
                if upper_band > current_price:
                    gap = (upper_band - current_price) / current_price
                    return gap, "BOLLINGER"
        except Exception:  # noqa: BLE001
            pass
    
    # 方法 3: 虚拟阻力位（历史新高或数据不足）
    # 假设上方有 5% 的虚拟空间
    virtual_resistance = current_price * 1.05
    gap = (virtual_resistance - current_price) / current_price
    return gap, "VIRTUAL"


def check_pre_trade_impact(
    structure_gap: float,
    min_gap: float = 0.02
) -> tuple[bool, str]:
    """
    Pre-Trade Impact Check（2% 硬门槛拦截）
    
    规则：
    IF Structure_Gap < 0.02 (2%)
        → BLOCK TRADE
        → Reason: LOW_R_R_POTENTIAL
    
    Args:
        structure_gap: 结构空间百分比（例如 0.025 表示 2.5%）
        min_gap: 最小允许的结构空间，默认 0.02 (2%)
    
    Returns:
        (allowed, reason)
        - allowed: True 表示允许交易，False 表示拦截
        - reason: 拦截原因或 "OK"
    """
    if structure_gap < min_gap:
        return False, "LOW_R_R_POTENTIAL"
    return True, "OK"


__all__ = [
    "find_pivot_highs",
    "calculate_structure_gap",
    "check_pre_trade_impact",
]

