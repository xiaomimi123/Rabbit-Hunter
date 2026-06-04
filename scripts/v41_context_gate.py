"""
V4.1 多周期 Context Gate 与 Phase Age

功能：
- 多周期 Context Gate（4H/1H 宏观趋势检查）
- Phase Age 计算（阶段年龄，防止接盘）
"""

from typing import Optional, Tuple
from datetime import datetime, timezone, timedelta
from whale_detector import (
    detect_phase,
    PHASE_P1,
    PHASE_P2,
    PHASE_P3A,
    PHASE_P3B,
    PHASE_P4,
)


def get_phase_for_timeframe(
    price_change_1h: Optional[float],
    oi_change_1h: Optional[float],
    cvd_intent: str,
    cvd_1h: Optional[float] = None,
    whale_cvd_1h: Optional[float] = None,
) -> str:
    """
    获取指定时间周期的 P 阶段
    
    复用现有的 detect_phase 逻辑，但可以传入不同周期的数据。
    
    Args:
        price_change_1h: 1H 价格变化百分比（注意：虽然参数名是 1h，但可以传入其他周期）
        oi_change_1h: 1H OI 变化百分比
        cvd_intent: CVD 意图（来自 CVDAnalyzer）
        cvd_1h: 1H CVD 值
        whale_cvd_1h: 1H Whale CVD 值
    
    Returns:
        P 阶段字符串（P1_NO_WHALE, P2_ACCUMULATION, P3A_PUMP_START, P3B_PUMP_LATE, P4_DISTRIBUTION）
    """
    return detect_phase(
        price_change_1h=price_change_1h,
        oi_change_1h=oi_change_1h,
        cvd_intent=cvd_intent,
        cvd_1h=cvd_1h,
        whale_cvd_1h=whale_cvd_1h,
    )


def check_context_gate(
    phase_4h: Optional[str] = None,
    phase_1h: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    多周期 Context Gate 检查
    
    规则：
    - 只有当大周期（4H/1H）也在蓄势或拉升时，才允许 15m 短线参与
    - 大周期在 P1 / P4 视为不利环境
    
    Args:
        phase_4h: 4H 周期的 P 阶段
        phase_1h: 1H 周期的 P 阶段
    
    Returns:
        (allowed, reason)
        - allowed: True 表示允许交易，False 表示拦截
        - reason: 拦截原因或 "OK"
    """
    # 如果数据不足，默认允许（保守策略）
    if phase_4h is None and phase_1h is None:
        return True, "OK_NO_DATA"
    
    # 检查 4H 周期
    if phase_4h in (PHASE_P1, PHASE_P4):
        return False, "MACRO_TREND_INVALID_4H"
    
    # 检查 1H 周期
    if phase_1h in (PHASE_P1, PHASE_P4):
        return False, "MACRO_TREND_INVALID_1H"
    
    return True, "OK"


def calculate_phase_age(
    phase_start_time: Optional[datetime],
    current_time: Optional[datetime] = None,
    candle_interval_minutes: int = 15
) -> Tuple[Optional[int], Optional[float]]:
    """
    计算 Phase Age（阶段年龄）
    
    定义：某个 P 阶段已经持续了多久（以 15m K 线根数计）。
    
    Args:
        phase_start_time: 阶段开始时间（例如：从 P2 → P3A 的那根 K 线时间）
        current_time: 当前时间，默认使用当前 UTC 时间
        candle_interval_minutes: K 线间隔（分钟），默认 15
    
    Returns:
        (duration_candles, phase_age_percent)
        - duration_candles: 持续了多少根 K 线（None 表示无法计算）
        - phase_age_percent: Phase Age 百分比（0-100，None 表示无法计算）
    """
    if phase_start_time is None:
        return None, None
    
    if current_time is None:
        current_time = datetime.now(timezone.utc)
    
    # 确保 phase_start_time 是 timezone-aware
    if phase_start_time.tzinfo is None:
        phase_start_time = phase_start_time.replace(tzinfo=timezone.utc)
    
    # 计算时间差（秒）
    time_diff = (current_time - phase_start_time).total_seconds()
    
    # 转换为 K 线根数
    duration_candles = int(time_diff / (candle_interval_minutes * 60))
    
    # 归一化为 Phase Age 百分比
    # 假设典型拉升周期为 48-96 根 15m K 线（12-24 小时）
    typical_cycle_candles = 72  # 取中位数
    phase_age_percent = min(100.0, (duration_candles / typical_cycle_candles) * 100.0)
    
    return duration_candles, phase_age_percent


def check_phase_age_block(
    duration_candles: Optional[int],
    current_price: float,
    recent_high: Optional[float] = None,
    max_candles: int = 100
) -> Tuple[bool, str]:
    """
    检查 Phase Age 是否触发拦截规则
    
    规则：
    IF Duration_Candles > 100 (≈ 25 小时持续拉升)
       AND 当前价格未创新高
        → BLOCK NEW ENTRY
        → Reason: PHASE_TOO_OLD
    
    Args:
        duration_candles: 阶段持续了多少根 K 线
        current_price: 当前价格
        recent_high: 最近的高价（用于判断是否创新高）
        max_candles: 最大允许的 K 线数，默认 100
    
    Returns:
        (allowed, reason)
        - allowed: True 表示允许交易，False 表示拦截
        - reason: 拦截原因或 "OK"
    """
    if duration_candles is None:
        return True, "OK_NO_DATA"
    
    # 如果持续时间超过阈值
    if duration_candles > max_candles:
        # 检查是否创新高
        if recent_high is not None and current_price < recent_high:
            # 价格未创新高，拦截
            return False, "PHASE_TOO_OLD"
        # 如果创新高了，允许继续（可能是第二波）
        return True, "OK_NEW_HIGH"
    
    return True, "OK"


__all__ = [
    "get_phase_for_timeframe",
    "check_context_gate",
    "calculate_phase_age",
    "check_phase_age_block",
]

