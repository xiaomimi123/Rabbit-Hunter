"""
V4.3 机会密度指标模块

计算 Opportunity Density Score (ODS)：
ODS = trades_per_week × average_expectancy × performance_factor

为什么重要？
- AI 调权重时，必须回答："是提高了单笔质量，还是提高了机会密度？"
- 防止 AI 偏向低频高分 → 资金长期闲置
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta


def calculate_opportunity_density_score(
    trades_per_week: float,
    average_expectancy: float,
    recent_performance: Optional[Dict[str, float]] = None,
) -> float:
    """
    计算机会密度分数（Opportunity Density Score）
    
    定义：
    ODS = trades_per_week × average_expectancy × performance_factor
    
    为什么重要？
    - AI 调权重时，必须回答：
      "今天的策略调整，是提高了单笔质量，还是提高了机会密度？"
    - 否则 AI 会自然偏向 低频高分 → 资金长期闲置
    
    Args:
        trades_per_week: 每周交易次数
        average_expectancy: 平均期望收益（每笔交易的期望收益）
        recent_performance: 最近表现指标（可选）
            - win_rate: 胜率 (0-1)
            - profit_factor: 盈亏比
    
    Returns:
        ODS (0-1): 机会密度分数
    """
    if recent_performance is None:
        recent_performance = {}
    
    # 基础 ODS
    base_ods = trades_per_week * average_expectancy
    
    # 性能因子（最近表现越好，ODS 越高）
    win_rate = recent_performance.get("win_rate", 0.5)
    profit_factor = recent_performance.get("profit_factor", 1.0)
    performance_factor = (win_rate * 0.5 + profit_factor * 0.5)
    
    ods = base_ods * performance_factor
    
    # 归一化到 0-1（假设最大 ODS 为 10）
    return min(1.0, max(0.0, ods / 10.0))


def calculate_trades_per_week(
    trades: list[Dict[str, Any]],
    days: int = 7,
) -> float:
    """
    计算每周交易次数
    
    Args:
        trades: 交易列表（每个交易包含 created_at 或 entry_time）
        days: 统计天数（默认 7 天）
    
    Returns:
        trades_per_week: 每周交易次数
    """
    if not trades:
        return 0.0
    
    # 计算时间范围
    now = datetime.now()
    start_date = now - timedelta(days=days)
    
    # 统计时间范围内的交易
    count = 0
    for trade in trades:
        # 尝试从不同字段获取时间
        trade_time = None
        if "created_at" in trade:
            trade_time = trade["created_at"]
        elif "entry_time" in trade:
            trade_time = trade["entry_time"]
        
        if trade_time:
            # 如果是字符串，转换为 datetime
            if isinstance(trade_time, str):
                try:
                    trade_time = datetime.fromisoformat(trade_time.replace("Z", "+00:00"))
                except Exception:
                    continue
            
            # 如果是 datetime，检查是否在时间范围内
            if isinstance(trade_time, datetime):
                if trade_time >= start_date:
                    count += 1
    
    # 转换为每周次数
    trades_per_week = (count / days) * 7.0
    
    return trades_per_week


def calculate_average_expectancy(
    trades: list[Dict[str, Any]],
) -> float:
    """
    计算平均期望收益
    
    Args:
        trades: 交易列表（每个交易包含 pnl 或 ret）
    
    Returns:
        average_expectancy: 平均期望收益
    """
    if not trades:
        return 0.0
    
    total_expectancy = 0.0
    count = 0
    
    for trade in trades:
        # 尝试从不同字段获取收益
        pnl = None
        if "pnl" in trade:
            pnl = trade["pnl"]
        elif "pnl_usdt" in trade:
            pnl = trade["pnl_usdt"]
        elif "ret" in trade:
            pnl = trade["ret"]
        
        if pnl is not None:
            try:
                total_expectancy += float(pnl)
                count += 1
            except (ValueError, TypeError):
                continue
    
    if count == 0:
        return 0.0
    
    return total_expectancy / count


__all__ = [
    "calculate_opportunity_density_score",
    "calculate_trades_per_week",
    "calculate_average_expectancy",
]

