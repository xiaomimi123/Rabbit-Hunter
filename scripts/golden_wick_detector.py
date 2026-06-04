"""
V4.2 Golden Wick (定海神针) 检测器

功能：
- 检测下影线长度 > K 线全长 60% 的形态
- 检测跌破支撑位后 15m 内快速收回 (Liquidity Sweep)
- 这是 V4.2 的最高优先级信号，可跳过部分过滤条件
"""

from typing import Optional, Tuple
from datetime import datetime, timezone, timedelta


def calculate_wick_ratio(
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float
) -> float:
    """
    计算下影线占比
    
    下影线长度 = min(open, close) - low
    K 线全长 = high - low
    下影线占比 = 下影线长度 / K 线全长
    
    Args:
        open_price: 开盘价
        high_price: 最高价
        low_price: 最低价
        close_price: 收盘价
    
    Returns:
        下影线占比（0.0 - 1.0），例如 0.65 表示 65%
    """
    if high_price == low_price:
        return 0.0
    
    body_bottom = min(open_price, close_price)
    lower_wick = body_bottom - low_price
    total_range = high_price - low_price
    
    if total_range == 0:
        return 0.0
    
    return lower_wick / total_range


def find_support_level(
    ohlcv: list[dict],
    lookback: int = 20
) -> Optional[float]:
    """
    查找支撑位
    
    使用最近 N 根 K 线的最低点作为支撑位
    
    Args:
        ohlcv: OHLCV 数据列表（从旧到新）
        lookback: 回看周期，默认 20 根
    
    Returns:
        支撑位价格，如果数据不足返回 None
    """
    if not ohlcv or len(ohlcv) < lookback:
        return None
    
    # 取最近 N 根 K 线
    recent = ohlcv[-lookback:]
    lows = [k.get("low", 0) for k in recent if k.get("low")]
    
    if not lows:
        return None
    
    # 支撑位 = 最近 N 根 K 线的最低点
    support = min(lows)
    return float(support)


def check_liquidity_sweep(
    ohlcv: list[dict],
    support_level: float,
    sweep_window: int = 2
) -> Tuple[bool, Optional[int]]:
    """
    检测流动性扫盘（Liquidity Sweep）
    
    条件：
    1. 某根 K 线的最低价 < 支撑位（跌破支撑）
    2. 在随后的 N 根 K 线内（默认 2 根，即 15-30 分钟），收盘价 > 支撑位（快速收回）
    
    Args:
        ohlcv: OHLCV 数据列表（从旧到新）
        support_level: 支撑位价格
        sweep_window: 扫盘窗口（K 线根数），默认 2 根（30 分钟）
    
    Returns:
        (is_sweep, sweep_index)
        - is_sweep: 是否发生流动性扫盘
        - sweep_index: 发生扫盘的 K 线索引（从旧到新），None 表示未发生
    """
    if not ohlcv or support_level <= 0:
        return False, None
    
    # 从后往前查找（最近的数据）
    for i in range(len(ohlcv) - 1, -1, -1):
        k = ohlcv[i]
        low = k.get("low")
        close = k.get("close")
        
        if low is None or close is None:
            continue
        
        # 检查是否跌破支撑位
        if float(low) < support_level:
            # 检查后续 K 线是否快速收回
            for j in range(i + 1, min(i + 1 + sweep_window, len(ohlcv))):
                next_k = ohlcv[j]
                next_close = next_k.get("close")
                
                if next_close and float(next_close) > support_level:
                    # 快速收回，确认是流动性扫盘
                    return True, i
            
            # 如果跌破后没有快速收回，继续往前查找
    
    return False, None


def detect_golden_wick(
    ohlcv_15m: list[dict],
    *,
    min_wick_ratio: float = 0.6,
    lookback_period: int = 20,
    sweep_window: int = 2
) -> Tuple[bool, dict]:
    """
    检测定海神针形态（Golden Wick）
    
    条件（必须同时满足）：
    1. 下影线长度 > K 线全长 60%
    2. 跌破支撑位后 15m 内（1-2 根 K 线）快速收回 (Liquidity Sweep)
    
    Args:
        ohlcv_15m: 15m K 线 OHLCV 数据列表（从旧到新），至少需要 20 根
        min_wick_ratio: 最小下影线占比，默认 0.6 (60%)
        lookback_period: 支撑位回看周期，默认 20 根（5 小时）
        sweep_window: 扫盘窗口（K 线根数），默认 2 根（30 分钟）
    
    Returns:
        (is_golden_wick, details)
        - is_golden_wick: 是否是定海神针形态
        - details: 详细信息字典
            {
                "wick_ratio": float,          # 下影线占比
                "support_level": float,       # 支撑位价格
                "sweep_detected": bool,       # 是否发生扫盘
                "sweep_index": int | None,    # 扫盘 K 线索引
                "reason": str                 # 原因说明
            }
    """
    if not ohlcv_15m or len(ohlcv_15m) < lookback_period:
        return False, {
            "wick_ratio": 0.0,
            "support_level": None,
            "sweep_detected": False,
            "sweep_index": None,
            "reason": "数据不足（需要至少 20 根 15m K 线）"
        }
    
    # 获取最新一根 K 线
    latest = ohlcv_15m[-1]
    open_price = float(latest.get("open", 0))
    high_price = float(latest.get("high", 0))
    low_price = float(latest.get("low", 0))
    close_price = float(latest.get("close", 0))
    
    if open_price == 0 or high_price == 0 or low_price == 0 or close_price == 0:
        return False, {
            "wick_ratio": 0.0,
            "support_level": None,
            "sweep_detected": False,
            "sweep_index": None,
            "reason": "K 线数据无效"
        }
    
    # 1. 计算下影线占比
    wick_ratio = calculate_wick_ratio(open_price, high_price, low_price, close_price)
    
    # 2. 查找支撑位
    support_level = find_support_level(ohlcv_15m, lookback=lookback_period)
    
    # 3. 检测流动性扫盘
    sweep_detected, sweep_index = False, None
    if support_level:
        sweep_detected, sweep_index = check_liquidity_sweep(
            ohlcv_15m,
            support_level,
            sweep_window=sweep_window
        )
    
    # 4. 判断是否是 Golden Wick
    is_golden_wick = False
    reason = ""
    
    if wick_ratio < min_wick_ratio:
        reason = f"下影线占比不足（{wick_ratio*100:.1f}% < {min_wick_ratio*100:.0f}%）"
    elif not support_level:
        reason = "无法确定支撑位"
    elif not sweep_detected:
        reason = "未检测到流动性扫盘（跌破支撑后未快速收回）"
    else:
        # 所有条件满足
        is_golden_wick = True
        reason = f"定海神针确认（下影线{wick_ratio*100:.1f}%，扫盘后快速收回）"
    
    return is_golden_wick, {
        "wick_ratio": wick_ratio,
        "support_level": support_level,
        "sweep_detected": sweep_detected,
        "sweep_index": sweep_index,
        "reason": reason
    }


__all__ = [
    "calculate_wick_ratio",
    "find_support_level",
    "check_liquidity_sweep",
    "detect_golden_wick",
]

