"""
V4.4 策略配置模块

定义策略特定的门槛和限制
"""

from typing import Dict, Optional
import os
from datetime import datetime, timezone

# ============================================
# 策略特定门槛 (Strategy-Specific Thresholds)
# ============================================
# 每个策略的最低分数要求
STRATEGY_THRESHOLDS: Dict[str, float] = {
    # "SNIFFER": 已禁用，不再允许交易（V4.5 降级为观察者）
    "SNIPER": 60.0,    # 🟢 保持 60。主升浪必须有高质量
    "VULTURE": 70.0,   # 🔵 从 75 放宽到 70。既然胜率高，就多给点机会
    "WAIT": 0.0,       # 等待策略：不检查门槛
}

# ============================================
# 最大同时持仓数 (Max Open Positions)
# ============================================
# 每个策略最多同时持有的仓位数量
# 作用：限制同一时间的风险暴露，而不是限制赚钱的次数
# 如果前面的单子都止盈了，应该允许继续开新单
MAX_OPEN_POSITIONS: Dict[str, int] = {
    "SNIFFER": 0,   # 🔴 锁死！绝对不允许开单！（V4.5 降级为观察者）
    "SNIPER": 5,    # 🟢 主升浪：最多 5 个，质量优先
    "VULTURE": 5,   # 🔵 秃鹫：提升到 5 个！它是现在的现金牛
    "WAIT": 0,      # 等待策略：不限制
}

# 全局最大持仓（防止资金分散太细）
GLOBAL_MAX_POSITIONS = 8

# ============================================
# 全局默认门槛（向后兼容）
# ============================================
DEFAULT_MIN_SCORE = 60.0


def get_strategy_threshold(strategy_id: str) -> float:
    """
    获取策略的最低分数门槛
    
    Args:
        strategy_id: 策略ID ('SNIFFER', 'SNIPER', 'VULTURE', 'WAIT')
        
    Returns:
        min_score: 最低分数要求
    """
    # SNIFFER 已禁用，返回一个极高的门槛（实际不会触发）
    if strategy_id == "SNIFFER":
        return 999.0  # 永远无法通过
    
    return STRATEGY_THRESHOLDS.get(strategy_id, DEFAULT_MIN_SCORE)


def get_max_open_positions(strategy_id: str) -> int:
    """
    获取策略的最大同时持仓数
    
    Args:
        strategy_id: 策略ID
        
    Returns:
        max_positions: 最多同时持仓数
    """
    return MAX_OPEN_POSITIONS.get(strategy_id, 0)


def check_strategy_threshold(strategy_id: str, score: float) -> tuple[bool, str]:
    """
    检查策略分数是否达到门槛
    
    Args:
        strategy_id: 策略ID
        score: 策略分数
        
    Returns:
        (passed, message): (是否通过, 消息)
    """
    if strategy_id == "WAIT":
        return False, "WAIT 策略不检查门槛"
    
    # SNIFFER 已禁用，永远不允许交易
    if strategy_id == "SNIFFER":
        return False, "SNIFFER 策略已禁用（V4.5 降级为观察者）"
    
    min_score = get_strategy_threshold(strategy_id)
    
    if score >= min_score:
        return True, f"Score {score:.1f} >= {min_score:.1f} (Pass)"
    else:
        return False, f"Score {score:.1f} < {min_score:.1f} (Fail)"


# ============================================
# 每日交易计数器（内存版本）
# ============================================
# 注意：这是内存版本，重启后会重置
# 如果需要持久化，应该使用数据库

_daily_trade_counts: Dict[str, Dict[str, int]] = {}  # {date: {strategy_id: count}}
_last_reset_date: Optional[str] = None


def get_today_date() -> str:
    """获取今天的日期字符串（UTC）"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def reset_daily_counts_if_needed():
    """如果需要，重置每日计数器"""
    global _last_reset_date
    today = get_today_date()
    
    if _last_reset_date != today:
        _daily_trade_counts.clear()
        _last_reset_date = today


def increment_daily_count(strategy_id: str) -> int:
    """
    增加策略的每日交易计数
    
    Args:
        strategy_id: 策略ID
        
    Returns:
        current_count: 当前计数
    """
    reset_daily_counts_if_needed()
    today = get_today_date()
    
    if today not in _daily_trade_counts:
        _daily_trade_counts[today] = {}
    
    if strategy_id not in _daily_trade_counts[today]:
        _daily_trade_counts[today][strategy_id] = 0
    
    _daily_trade_counts[today][strategy_id] += 1
    return _daily_trade_counts[today][strategy_id]


def get_daily_count(strategy_id: str) -> int:
    """
    获取策略的今日交易计数
    
    Args:
        strategy_id: 策略ID
        
    Returns:
        count: 今日交易次数
    """
    reset_daily_counts_if_needed()
    today = get_today_date()
    
    if today not in _daily_trade_counts:
        return 0
    
    return _daily_trade_counts[today].get(strategy_id, 0)


def check_max_open_positions(
    strategy_id: str,
    current_open_positions: int,
    global_current_positions: int = 0
) -> tuple[bool, str]:
    """
    检查策略是否超过最大同时持仓数
    
    Args:
        strategy_id: 策略ID
        current_open_positions: 当前该策略的持仓数
        global_current_positions: 全局当前持仓数（可选）
        
    Returns:
        (allowed, message): (是否允许交易, 消息)
    """
    if strategy_id == "WAIT":
        return False, "WAIT 策略不允许交易"
    
    # SNIFFER 已禁用，永远不允许交易（V4.5）
    if strategy_id == "SNIFFER":
        return False, "SNIFFER 策略已禁用（V4.5 降级为观察者）"
    
    # 检查全局持仓限制
    if global_current_positions > 0 and global_current_positions >= GLOBAL_MAX_POSITIONS:
        return False, f"全局持仓已满 ({global_current_positions}/{GLOBAL_MAX_POSITIONS})"
    
    # 检查策略特定持仓限制
    max_positions = get_max_open_positions(strategy_id)
    if max_positions <= 0:
        return True, "无限制"
    
    if current_open_positions < max_positions:
        return True, f"持仓 {current_open_positions}/{max_positions} (有空位)"
    else:
        return False, f"持仓已满 ({current_open_positions}/{max_positions})"


def get_all_daily_counts() -> Dict[str, int]:
    """
    获取所有策略的今日交易计数
    
    Returns:
        counts: {strategy_id: count}
    """
    reset_daily_counts_if_needed()
    today = get_today_date()
    
    return _daily_trade_counts.get(today, {}).copy()


# ============================================
# 环境变量覆盖（用于测试和调试）
# ============================================
def load_config_from_env():
    """从环境变量加载配置（如果存在）"""
    # SNIFFER 门槛
    sniffer_threshold = os.environ.get("V44_SNIFFER_THRESHOLD")
    if sniffer_threshold:
        try:
            STRATEGY_THRESHOLDS["SNIFFER"] = float(sniffer_threshold)
        except ValueError:
            pass
    
    # SNIPER 门槛
    sniper_threshold = os.environ.get("V44_SNIPER_THRESHOLD")
    if sniper_threshold:
        try:
            STRATEGY_THRESHOLDS["SNIPER"] = float(sniper_threshold)
        except ValueError:
            pass
    
    # VULTURE 门槛
    vulture_threshold = os.environ.get("V44_VULTURE_THRESHOLD")
    if vulture_threshold:
        try:
            STRATEGY_THRESHOLDS["VULTURE"] = float(vulture_threshold)
        except ValueError:
            pass
    
    # VULTURE 最大持仓
    vulture_max = os.environ.get("V44_VULTURE_MAX_POSITIONS")
    if vulture_max:
        try:
            MAX_OPEN_POSITIONS["VULTURE"] = int(vulture_max)
        except ValueError:
            pass
    
    # SNIPER 最大持仓
    sniper_max = os.environ.get("V44_SNIPER_MAX_POSITIONS")
    if sniper_max:
        try:
            MAX_OPEN_POSITIONS["SNIPER"] = int(sniper_max)
        except ValueError:
            pass
    
    # SNIFFER 最大持仓
    sniffer_max = os.environ.get("V44_SNIFFER_MAX_POSITIONS")
    if sniffer_max:
        try:
            MAX_OPEN_POSITIONS["SNIFFER"] = int(sniffer_max)
        except ValueError:
            pass
    
    # 全局最大持仓
    global_max = os.environ.get("V44_GLOBAL_MAX_POSITIONS")
    if global_max:
        try:
            global GLOBAL_MAX_POSITIONS
            GLOBAL_MAX_POSITIONS = int(global_max)
        except ValueError:
            pass


# 初始化时加载环境变量配置
load_config_from_env()

