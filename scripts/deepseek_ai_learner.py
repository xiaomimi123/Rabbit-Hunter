"""
DeepSeek AI 学习器（Rabbit Hunter V4.2）

功能：
- 在裁决时访问历史数据，让 AI 具备学习能力
- 分析历史交易结果，改进决策
- 自动从历史数据中提取模式
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional
from datetime import datetime, timedelta, timezone

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None


class DeepSeekLearner:
    """DeepSeek AI 学习器：从历史数据中学习"""
    
    def __init__(self, supabase: Optional[Client] = None):
        """
        初始化学习器
        
        Args:
            supabase: Supabase 客户端（可选，如果不提供则从环境变量创建）
        """
        if supabase is None and SUPABASE_AVAILABLE:
            supabase_url = os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_KEY")
            if supabase_url and supabase_key:
                self.supabase = create_client(supabase_url, supabase_key)
            else:
                self.supabase = None
        else:
            self.supabase = supabase
        
        self._cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
        self._cache_ttl = 300  # 5 分钟缓存
    
    def get_historical_context(
        self,
        symbol: str,
        market_phase: Optional[str] = None,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        获取历史上下文数据，用于 AI 学习
        
        Args:
            symbol: 交易对符号
            market_phase: 当前市场阶段（可选）
            days: 查询最近 N 天的数据
        
        Returns:
            历史上下文字典
        """
        if not self.supabase:
            return {}
        
        # 检查缓存
        cache_key = f"{symbol}_{market_phase}_{days}"
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if (datetime.now().timestamp() - cached_time) < self._cache_ttl:
                return cached_data
        
        try:
            # 查询最近 N 天的数据
            start_time = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            
            # 1. 查询该币种的历史决策
            response = (
                self.supabase.table("ai_training_data")
                .select("ai_score, ai_allowed, market_phase, kill_zone_signal, exit_clarity_score, created_at")
                .eq("symbol", symbol)
                .gte("created_at", start_time)
                .not_.is_("ai_score", "null")
                .order("created_at", desc=False)
                .limit(100)
                .execute()
            )
            
            historical_decisions = response.data or []
            
            # 2. 查询该币种的模拟交易结果（如果有）
            paper_response = (
                self.supabase.table("paper_trades")
                .select("symbol, ret, pnl_usdt, status, created_at")
                .eq("symbol", symbol)
                .gte("created_at", start_time)
                .order("created_at", desc=False)
                .limit(50)
                .execute()
            )
            
            paper_trades = paper_response.data or []
            
            # 3. 计算统计指标
            context = self._calculate_statistics(
                historical_decisions,
                paper_trades,
                market_phase
            )
            
            # 更新缓存
            self._cache[cache_key] = (datetime.now().timestamp(), context)
            
            return context
            
        except Exception as e:
            # 如果查询失败，返回空字典
            return {}
    
    def _calculate_statistics(
        self,
        historical_decisions: list,
        paper_trades: list,
        current_phase: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        计算历史统计指标
        
        Args:
            historical_decisions: 历史决策列表
            paper_trades: 模拟交易列表
            current_phase: 当前市场阶段
        
        Returns:
            统计指标字典
        """
        stats = {
            "historical_decisions_count": len(historical_decisions),
            "paper_trades_count": len(paper_trades),
            "avg_ai_score": 0.0,
            "allowed_rate": 0.0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "phase_specific_stats": {},
        }
        
        if not historical_decisions:
            return stats
        
        # 计算平均 AI 分数
        scores = [float(d.get("ai_score", 0)) for d in historical_decisions if d.get("ai_score")]
        if scores:
            stats["avg_ai_score"] = sum(scores) / len(scores)
        
        # 计算允许率
        allowed_count = sum(1 for d in historical_decisions if d.get("ai_allowed"))
        stats["allowed_rate"] = allowed_count / len(historical_decisions) if historical_decisions else 0.0
        
        # 计算交易胜率和平均收益
        if paper_trades:
            returns = [float(t.get("ret", 0)) for t in paper_trades if t.get("ret")]
            wins = [r for r in returns if r > 0]
            stats["win_rate"] = len(wins) / len(returns) if returns else 0.0
            stats["avg_return"] = sum(returns) / len(returns) if returns else 0.0
        
        # 按市场阶段统计（如果当前阶段已知）
        if current_phase:
            phase_decisions = [d for d in historical_decisions if d.get("market_phase") == current_phase]
            if phase_decisions:
                phase_scores = [float(d.get("ai_score", 0)) for d in phase_decisions if d.get("ai_score")]
                phase_allowed = sum(1 for d in phase_decisions if d.get("ai_allowed"))
                
                stats["phase_specific_stats"] = {
                    "count": len(phase_decisions),
                    "avg_score": sum(phase_scores) / len(phase_scores) if phase_scores else 0.0,
                    "allowed_rate": phase_allowed / len(phase_decisions) if phase_decisions else 0.0,
                }
        
        return stats
    
    def enrich_features_with_history(
        self,
        features: Dict[str, Any],
        days: int = 7
    ) -> Dict[str, Any]:
        """
        用历史数据丰富特征，用于 AI 决策
        
        Args:
            features: 当前特征字典
            days: 查询最近 N 天的历史数据
        
        Returns:
            增强后的特征字典
        """
        symbol = features.get("symbol")
        market_phase = features.get("market_phase")
        
        if not symbol:
            return features
        
        # 获取历史上下文
        historical_context = self.get_historical_context(symbol, market_phase, days)
        
        # 将历史数据添加到特征中
        enriched_features = dict(features)
        enriched_features["historical_context"] = historical_context
        
        # 添加简化的历史指标（用于 AI 提示词）
        if historical_context:
            enriched_features["historical_avg_score"] = historical_context.get("avg_ai_score", 0.0)
            enriched_features["historical_allowed_rate"] = historical_context.get("allowed_rate", 0.0)
            enriched_features["historical_win_rate"] = historical_context.get("win_rate", 0.0)
            enriched_features["historical_avg_return"] = historical_context.get("avg_return", 0.0)
            
            # 如果当前阶段有历史数据，添加阶段特定统计
            phase_stats = historical_context.get("phase_specific_stats", {})
            if phase_stats:
                enriched_features["phase_historical_avg_score"] = phase_stats.get("avg_score", 0.0)
                enriched_features["phase_historical_allowed_rate"] = phase_stats.get("allowed_rate", 0.0)
        
        return enriched_features


__all__ = ["DeepSeekLearner"]

