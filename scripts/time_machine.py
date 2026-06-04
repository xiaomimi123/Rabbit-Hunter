"""
V4.2 Time Machine (历史回放脚本)

功能：
- 模拟历史行情，回放交易决策
- 使用 V4.1/V4.2 规则进行策略回放
- 计算 WCS (Whale Capture Score) 分数
- 输出性能报告

WCS 公式：
WCS = (Trend_Profit * 1.0) - (Max_Drawdown * 2.0) - (Missed_P3A * 1.5)
"""

from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import json


@dataclass
class SimulationConfig:
    """模拟配置"""
    atr_multiplier_p2: float = 2.5
    atr_multiplier_p3a_early: float = 2.5
    atr_multiplier_p3a_normal: float = 2.0
    atr_multiplier_p3b: float = 1.5
    structure_gap_threshold: float = 0.02  # 2%
    phase_age_max_candles: int = 100
    context_gate_required: bool = True
    golden_wick_bypass_structure: bool = True


@dataclass
class SimulatedTrade:
    """模拟交易记录"""
    symbol: str
    entry_time: datetime
    entry_price: float
    side: str  # "LONG" | "SHORT"
    exit_time: Optional[datetime]
    exit_price: Optional[float]
    stop_loss_price: float
    position_size: float
    pnl: float  # 盈亏百分比
    pnl_usdt: float  # 盈亏 USDT
    market_phase: str
    kill_zone: str
    is_golden_wick: bool
    exit_reason: str  # "TAKE_PROFIT" | "STOP_LOSS" | "TIME_STOP" | "PHASE_CHANGE"


@dataclass
class SimulationResult:
    """模拟结果"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_profit: float
    total_loss: float
    avg_profit: float
    avg_loss: float
    max_profit: float
    max_loss: float
    trend_profit: float  # 主升浪利润
    max_drawdown: float  # 最大回撤
    missed_p3a: int  # 错过的 P3A 机会
    wcs_score: float  # Whale Capture Score


def calculate_wcs(
    trend_profit: float,
    max_drawdown: float,
    missed_p3a: int
) -> float:
    """
    计算 WCS (Whale Capture Score)
    
    WCS = (Trend_Profit * 1.0) - (Max_Drawdown * 2.0) - (Missed_P3A * 1.5)
    
    Args:
        trend_profit: 主升浪利润（累计盈利）
        max_drawdown: 最大回撤（绝对值）
        missed_p3a: 错过的 P3A 机会数量
    
    Returns:
        WCS 分数
    """
    return (trend_profit * 1.0) - (max_drawdown * 2.0) - (missed_p3a * 1.5)


def simulate_trade(
    entry_record: dict,
    future_records: List[dict],
    config: SimulationConfig,
    account_balance: float = 10000.0,
    risk_per_trade: float = 0.015
) -> Optional[SimulatedTrade]:
    """
    模拟单笔交易
    
    Args:
        entry_record: 入场记录（来自 ai_training_data）
        future_records: 未来记录列表（用于计算退出）
        config: 模拟配置
        account_balance: 账户余额
        risk_per_trade: 单笔风险百分比
    
    Returns:
        模拟交易记录，如果无法模拟则返回 None
    """
    # 检查是否有交易信号
    signal = entry_record.get("technical_signal")
    if signal not in ["LONG", "SHORT"]:
        return None
    
    # 检查是否允许交易
    if not entry_record.get("is_trade_allowed", False):
        return None
    
    # 获取入场信息
    entry_price = float(entry_record.get("price", 0))
    if entry_price <= 0:
        return None
    
    entry_time_str = entry_record.get("created_at")
    if not entry_time_str:
        return None
    
    try:
        if isinstance(entry_time_str, str):
            if entry_time_str.endswith("Z"):
                entry_time_str = entry_time_str[:-1] + "+00:00"
            entry_time = datetime.fromisoformat(entry_time_str.replace("Z", "+00:00"))
        else:
            return None
    except Exception:
        return None
    
    # 获取止损价格
    chandelier_stop = entry_record.get("chandelier_stop_price")
    if chandelier_stop is None:
        # 如果没有吊灯止损，使用 ATR 计算
        atr_value = entry_record.get("atr_value")
        atr_multiplier = entry_record.get("atr_multiplier")
        if atr_value and atr_multiplier:
            if signal == "LONG":
                stop_loss_price = entry_price - (atr_value * atr_multiplier)
            else:
                stop_loss_price = entry_price + (atr_value * atr_multiplier)
        else:
            return None
    else:
        stop_loss_price = float(chandelier_stop)
    
    # 计算仓位
    position_size = abs(account_balance * risk_per_trade / abs(entry_price - stop_loss_price))
    
    # 获取市场信息
    market_phase = entry_record.get("market_phase") or "UNKNOWN"
    kill_zone = entry_record.get("kill_zone_signal") or "NONE"
    is_golden_wick = entry_record.get("is_golden_wick", False)
    
    # 模拟退出逻辑（简化：使用未来价格）
    exit_time = None
    exit_price = None
    exit_reason = "TIME_STOP"
    pnl = 0.0
    
    highest_high = entry_price
    lowest_low = entry_price
    
    for future_record in future_records:
        future_price = float(future_record.get("price", 0))
        if future_price <= 0:
            continue
        
        future_time_str = future_record.get("created_at")
        if not future_time_str:
            continue
        
        try:
            if isinstance(future_time_str, str):
                if future_time_str.endswith("Z"):
                    future_time_str = future_time_str[:-1] + "+00:00"
                future_time = datetime.fromisoformat(future_time_str.replace("Z", "+00:00"))
            else:
                continue
        except Exception:
            continue
        
        # 更新最高价/最低价（用于计算回撤）
        if signal == "LONG":
            highest_high = max(highest_high, future_price)
            # 检查止损
            if future_price <= stop_loss_price:
                exit_time = future_time
                exit_price = stop_loss_price
                exit_reason = "STOP_LOSS"
                pnl = (stop_loss_price - entry_price) / entry_price
                break
            # 检查阶段变化（简化：如果阶段变为 P4，退出）
            future_phase = future_record.get("market_phase")
            if future_phase == "P4_DISTRIBUTION":
                exit_time = future_time
                exit_price = future_price
                exit_reason = "PHASE_CHANGE"
                pnl = (future_price - entry_price) / entry_price
                break
        else:  # SHORT
            lowest_low = min(lowest_low, future_price)
            # 检查止损
            if future_price >= stop_loss_price:
                exit_time = future_time
                exit_price = stop_loss_price
                exit_reason = "STOP_LOSS"
                pnl = (entry_price - stop_loss_price) / entry_price
                break
            # 检查阶段变化
            future_phase = future_record.get("market_phase")
            if future_phase == "P4_DISTRIBUTION":
                exit_time = future_time
                exit_price = future_price
                exit_reason = "PHASE_CHANGE"
                pnl = (entry_price - future_price) / entry_price
                break
    
    # 如果没有退出，使用最后一个价格
    if exit_time is None and future_records:
        last_record = future_records[-1]
        last_price = float(last_record.get("price", entry_price))
        last_time_str = last_record.get("created_at")
        if last_time_str:
            try:
                if isinstance(last_time_str, str):
                    if last_time_str.endswith("Z"):
                        last_time_str = last_time_str[:-1] + "+00:00"
                    exit_time = datetime.fromisoformat(last_time_str.replace("Z", "+00:00"))
                    exit_price = last_price
                    if signal == "LONG":
                        pnl = (last_price - entry_price) / entry_price
                    else:
                        pnl = (entry_price - last_price) / entry_price
            except Exception:
                pass
    
    # 计算盈亏 USDT
    pnl_usdt = account_balance * risk_per_trade * pnl if pnl != 0 else 0.0
    
    return SimulatedTrade(
        symbol=entry_record.get("symbol", ""),
        entry_time=entry_time,
        entry_price=entry_price,
        side=signal,
        exit_time=exit_time,
        exit_price=exit_price,
        stop_loss_price=stop_loss_price,
        position_size=position_size,
        pnl=pnl,
        pnl_usdt=pnl_usdt,
        market_phase=market_phase,
        kill_zone=kill_zone,
        is_golden_wick=is_golden_wick,
        exit_reason=exit_reason
    )


def replay_history(
    records: List[dict],
    config: SimulationConfig,
    horizon_hours: int = 24,
    account_balance: float = 10000.0
) -> SimulationResult:
    """
    历史回放
    
    Args:
        records: 历史记录列表（从 ai_training_data 获取，按时间排序）
        config: 模拟配置
        horizon_hours: 持仓时间窗口（小时）
        account_balance: 初始账户余额
    
    Returns:
        模拟结果
    """
    trades: List[SimulatedTrade] = []
    missed_p3a = 0
    
    # 按时间排序
    sorted_records = sorted(records, key=lambda x: x.get("created_at", ""))
    
    i = 0
    while i < len(sorted_records):
        entry_record = sorted_records[i]
        
        # 检查是否是 P3A 机会但未交易
        market_phase = entry_record.get("market_phase")
        is_trade_allowed = entry_record.get("is_trade_allowed", False)
        if market_phase == "P3A_PUMP_START" and not is_trade_allowed:
            missed_p3a += 1
        
        # 尝试模拟交易
        # 获取未来记录（horizon_hours 内）
        horizon_end = None
        entry_time_str = entry_record.get("created_at")
        if entry_time_str:
            try:
                if isinstance(entry_time_str, str):
                    if entry_time_str.endswith("Z"):
                        entry_time_str = entry_time_str[:-1] + "+00:00"
                    entry_time = datetime.fromisoformat(entry_time_str.replace("Z", "+00:00"))
                    horizon_end = entry_time + timedelta(hours=horizon_hours)
            except Exception:
                pass
        
        if horizon_end:
            future_records = [
                r for r in sorted_records[i+1:]
                if r.get("created_at") and (
                    datetime.fromisoformat(
                        r.get("created_at").replace("Z", "+00:00")
                    ) <= horizon_end
                )
            ]
        else:
            future_records = sorted_records[i+1:i+100]  # 默认取后续 100 条
        
        trade = simulate_trade(entry_record, future_records, config, account_balance)
        if trade:
            trades.append(trade)
            # 更新账户余额（简化：不考虑复利）
            account_balance += trade.pnl_usdt
        
        i += 1
    
    # 计算统计指标
    if not trades:
        return SimulationResult(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            total_profit=0.0,
            total_loss=0.0,
            avg_profit=0.0,
            avg_loss=0.0,
            max_profit=0.0,
            max_loss=0.0,
            trend_profit=0.0,
            max_drawdown=0.0,
            missed_p3a=missed_p3a,
            wcs_score=0.0
        )
    
    winning_trades = [t for t in trades if t.pnl > 0]
    losing_trades = [t for t in trades if t.pnl <= 0]
    
    total_profit = sum(t.pnl_usdt for t in winning_trades)
    total_loss = sum(t.pnl_usdt for t in losing_trades)
    
    avg_profit = total_profit / len(winning_trades) if winning_trades else 0.0
    avg_loss = total_loss / len(losing_trades) if losing_trades else 0.0
    
    max_profit = max(t.pnl_usdt for t in trades) if trades else 0.0
    max_loss = min(t.pnl_usdt for t in trades) if trades else 0.0
    
    # 计算最大回撤（简化：使用最大亏损）
    max_drawdown = abs(max_loss)
    
    # 计算主升浪利润（累计盈利）
    trend_profit = total_profit
    
    # 计算 WCS
    wcs_score = calculate_wcs(trend_profit, max_drawdown, missed_p3a)
    
    return SimulationResult(
        total_trades=len(trades),
        winning_trades=len(winning_trades),
        losing_trades=len(losing_trades),
        win_rate=len(winning_trades) / len(trades) if trades else 0.0,
        total_profit=total_profit,
        total_loss=total_loss,
        avg_profit=avg_profit,
        avg_loss=avg_loss,
        max_profit=max_profit,
        max_loss=max_loss,
        trend_profit=trend_profit,
        max_drawdown=max_drawdown,
        missed_p3a=missed_p3a,
        wcs_score=wcs_score
    )


def format_simulation_report(result: SimulationResult) -> str:
    """
    格式化模拟报告
    
    Args:
        result: 模拟结果
    
    Returns:
        格式化的报告字符串
    """
    report = f"""
=== 历史回放模拟报告 ===

📊 交易统计
- 总交易数: {result.total_trades}
- 盈利交易: {result.winning_trades}
- 亏损交易: {result.losing_trades}
- 胜率: {result.win_rate*100:.2f}%

💰 盈亏统计
- 总盈利: {result.total_profit:.2f} USDT
- 总亏损: {result.total_loss:.2f} USDT
- 平均盈利: {result.avg_profit:.2f} USDT
- 平均亏损: {result.avg_loss:.2f} USDT
- 最大盈利: {result.max_profit:.2f} USDT
- 最大亏损: {result.max_loss:.2f} USDT

📈 主升浪捕获
- 主升浪利润: {result.trend_profit:.2f} USDT
- 最大回撤: {result.max_drawdown:.2f} USDT
- 错过 P3A 机会: {result.missed_p3a} 次

🎯 WCS 分数
- WCS = {result.wcs_score:.2f}
  = (Trend_Profit * 1.0) - (Max_Drawdown * 2.0) - (Missed_P3A * 1.5)
  = ({result.trend_profit:.2f} * 1.0) - ({result.max_drawdown:.2f} * 2.0) - ({result.missed_p3a} * 1.5)
"""
    return report


__all__ = [
    "SimulationConfig",
    "SimulatedTrade",
    "SimulationResult",
    "calculate_wcs",
    "simulate_trade",
    "replay_history",
    "format_simulation_report",
]

