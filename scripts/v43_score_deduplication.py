"""
V4.3 分数去重模块

优化问题：trade_scores_v43 表写入频率过高

当前情况：
- Top 5 异动币
- 每分钟循环
- 长期跑会导致表暴涨、查询慢、Supabase 成本上升

解决方案：
1. 分数变化 < ε（阈值）→ 不写
2. 或每 symbol 每 X 分钟写一次（降频）

实现：
- 内存缓存最后一次写入的 (symbol, final_score, timestamp)
- 新分数与旧分数对比
- 若变化 < ε 且距离上次写入 < X 分钟，则跳过
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import time

# 去重配置
SCORE_DEDUP_ENABLED = True  # 启用去重
SCORE_CHANGE_EPSILON = 0.02  # 分数变化阈值（2%）
SCORE_WRITE_INTERVAL_SECONDS = 300  # 最少写入间隔（5 分钟）

# 内存缓存：记录每个 symbol 的最后一次写入
# 格式：{"BTC/USDT": {"final_score": 0.75, "timestamp": 1234567890}}
_score_cache: Dict[str, Dict[str, Any]] = {}


def should_write_score(
    symbol: str,
    final_score: float,
    force: bool = False,
) -> Tuple[bool, str]:
    """
    判断是否应该写入 trade_scores_v43
    
    Args:
        symbol: 交易对符号
        final_score: 最终分数 (0-1)
        force: 强制写入（用于 should_trade=True 的情况）
    
    Returns:
        (should_write, reason)
        - (True, "reason") → 应该写入
        - (False, "reason") → 应该跳过
    """
    if not SCORE_DEDUP_ENABLED:
        return (True, "DEDUP_DISABLED")
    
    # 强制写入（重要交易信号）
    if force:
        _update_score_cache(symbol, final_score)
        return (True, "FORCE_WRITE")
    
    # 获取缓存
    cache_entry = _score_cache.get(symbol)
    current_time = time.time()
    
    # 第一次写入该 symbol
    if cache_entry is None:
        _update_score_cache(symbol, final_score)
        return (True, "FIRST_WRITE")
    
    last_score = cache_entry.get("final_score", 0.0)
    last_write_time = cache_entry.get("timestamp", 0)
    
    # 计算分数变化
    score_change = abs(final_score - last_score)
    time_since_last_write = current_time - last_write_time
    
    # 规则 1: 分数变化显著（> ε）→ 写入
    if score_change > SCORE_CHANGE_EPSILON:
        _update_score_cache(symbol, final_score)
        return (True, f"SCORE_CHANGED ({score_change:.3f} > {SCORE_CHANGE_EPSILON})")
    
    # 规则 2: 时间足够久（> X 分钟）→ 写入（定期检查）
    if time_since_last_write > SCORE_WRITE_INTERVAL_SECONDS:
        _update_score_cache(symbol, final_score)
        return (True, f"PERIODIC_WRITE ({time_since_last_write:.0f}s > {SCORE_WRITE_INTERVAL_SECONDS}s)")
    
    # 都不满足 → 跳过
    return (False, f"DEDUP (change={score_change:.3f}, interval={time_since_last_write:.0f}s)")


def _update_score_cache(symbol: str, final_score: float) -> None:
    """更新缓存"""
    _score_cache[symbol] = {
        "final_score": final_score,
        "timestamp": time.time(),
    }


def get_dedup_stats() -> Dict[str, Any]:
    """
    获取去重统计信息
    
    Returns:
        {
            "cached_symbols": int,
            "cache": dict,
        }
    """
    return {
        "cached_symbols": len(_score_cache),
        "cache": _score_cache.copy(),
    }


def clear_cache() -> None:
    """清空缓存（用于测试或重启）"""
    global _score_cache
    _score_cache.clear()


__all__ = [
    "should_write_score",
    "get_dedup_stats",
    "clear_cache",
]

