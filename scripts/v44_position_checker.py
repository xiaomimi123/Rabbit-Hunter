"""
V4.4 持仓检查器

查询当前持仓数，用于检查是否超过最大持仓限制
"""

from typing import Dict, Optional, Tuple
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from v44_strategy_config import check_max_open_positions, GLOBAL_MAX_POSITIONS


def get_open_positions_by_strategy(supabase_client) -> Tuple[Dict[str, int], int]:
    """
    从数据库查询当前持仓数（按策略分组）
    
    Args:
        supabase_client: Supabase 客户端
        
    Returns:
        (positions_by_strategy, total_count): 
        - positions_by_strategy: {strategy_id: count}
        - total_count: 全局总持仓数
    """
    if not supabase_client:
        return {}, 0
    
    try:
        # 查询所有 OPEN 状态的持仓
        response = supabase_client.table("positions_v43").select(
            "strategy_id"
        ).eq("status", "OPEN").execute()
        
        positions_by_strategy: Dict[str, int] = {}
        total_count = 0
        
        for record in response.data or []:
            strategy_id = record.get("strategy_id")
            if strategy_id:
                positions_by_strategy[strategy_id] = positions_by_strategy.get(strategy_id, 0) + 1
                total_count += 1
        
        return positions_by_strategy, total_count
        
    except Exception as e:
        print(f"[WARNING] 查询持仓失败: {e}")
        return {}, 0


def check_position_limit(
    supabase_client,
    strategy_id: str
) -> Tuple[bool, str]:
    """
    检查策略是否超过最大持仓限制
    
    Args:
        supabase_client: Supabase 客户端
        strategy_id: 策略ID
        
    Returns:
        (allowed, message): (是否允许交易, 消息)
    """
    if not supabase_client:
        # 如果没有 supabase 客户端，允许交易（向后兼容）
        return True, "无持仓数据，允许交易"
    
    # 查询当前持仓
    positions_by_strategy, total_count = get_open_positions_by_strategy(supabase_client)
    
    # 获取当前策略的持仓数
    current_strategy_positions = positions_by_strategy.get(strategy_id, 0)
    
    # 检查限制
    return check_max_open_positions(
        strategy_id=strategy_id,
        current_open_positions=current_strategy_positions,
        global_current_positions=total_count
    )


__all__ = [
    "get_open_positions_by_strategy",
    "check_position_limit",
]

