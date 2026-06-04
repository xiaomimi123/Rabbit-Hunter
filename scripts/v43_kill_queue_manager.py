"""
V4.3 实时猎杀队列管理器

功能：
- 实时计算所有币种的 AI 评分
- 排序并缓存 Top N
- 支持过滤和排序
- 提供增量更新
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timedelta
import asyncio
import os
import sys

# 添加项目根目录到路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

try:
    from supabase import create_client, Client
    from v43_feature_extractor import extract_features
    from v43_score_calculator import calculate_scores, aggregate_score
    from v43_decision_policy import decision_policy
    from v43_weight_manager import get_current_weights
except ImportError as e:
    print(f"[WARNING] V4.3 KillQueueManager 导入失败: {e}")


class KillQueueManager:
    """
    实时猎杀队列管理器
    
    负责：
    1. 从 trade_scores_v43 表读取最新评分
    2. 排序和过滤
    3. 缓存结果
    4. 提供增量更新
    """
    
    def __init__(self, supabase_client: Optional[Client] = None):
        """
        初始化管理器
        
        Args:
            supabase_client: Supabase 客户端（如果为 None，会尝试从环境变量创建）
        """
        self.supabase = supabase_client
        if not self.supabase:
            self._init_supabase()
        
        self.cache: List[Dict[str, Any]] = []
        self.last_update: Optional[datetime] = None
        self.cache_ttl = 5  # 缓存有效期（秒）
        self.subscribers: List[Callable] = []
    
    def _init_supabase(self):
        """初始化 Supabase 客户端"""
        try:
            SUPABASE_URL = os.environ.get("SUPABASE_URL")
            SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
            
            if SUPABASE_URL and SUPABASE_KEY:
                self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
                print("[INFO] KillQueueManager: Supabase 客户端初始化成功")
            else:
                print("[WARNING] KillQueueManager: Supabase 配置缺失")
        except Exception as e:
            print(f"[ERROR] KillQueueManager: Supabase 初始化失败: {e}")
    
    def get_kill_queue(
        self,
        limit: int = 20,
        min_score: float = 60.0,
        phase_filter: Optional[List[str]] = None,
        sort_by: str = "score",
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        获取猎杀队列
        
        Args:
            limit: 最多返回币种数
            min_score: 最低 AI 评分（0-100）
            phase_filter: 阶段过滤列表（如 ['P3A', 'P3B']）
            sort_by: 排序方式（'score' 或 'age'）
            offset: 分页偏移
        
        Returns:
            包含 data, pagination, metadata 的字典
        """
        if not self.supabase:
            return {
                "data": [],
                "pagination": {"total": 0, "limit": limit, "offset": offset, "pages": 0},
                "metadata": {"updatedAt": datetime.now().isoformat(), "dataFreshness": "N/A", "systemHealth": 0.0}
            }
        
        try:
            # 转换 min_score 为 0-1 范围
            min_score_normalized = min_score / 100.0
            
            # 构建查询
            query = self.supabase.table("trade_scores_v43").select("*")
            query = query.gte("final_score", min_score_normalized)
            
            # 排序
            if sort_by == "score":
                query = query.order("final_score", desc=True)
            elif sort_by == "age":
                query = query.order("created_at", desc=False)  # 年龄越小越靠前
            
            # 获取数据
            response = (
                query
                .range(offset, offset + limit - 1)
                .limit(limit)
                .execute()
            )
            
            # 获取总数（用于分页信息）
            count_query = self.supabase.table("trade_scores_v43").select("id", count="exact")
            count_query = count_query.gte("final_score", min_score_normalized)
            count_response = count_query.execute()
            total = count_response.count if hasattr(count_response, 'count') else len(response.data or [])
            
            # 格式化数据
            items = []
            for record in response.data or []:
                item = self._format_kill_queue_item(record)
                
                # 阶段过滤（后置过滤）
                if phase_filter and item.get("phase") not in phase_filter:
                    continue
                
                items.append(item)
            
            # 如果进行了阶段过滤，重新计算 total
            if phase_filter:
                total = len(items)
            
            return {
                "data": items,
                "pagination": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "pages": (total + limit - 1) // limit if limit > 0 else 0,
                },
                "metadata": {
                    "updatedAt": datetime.now().isoformat(),
                    "dataFreshness": "1s",
                    "systemHealth": 0.98,
                }
            }
        except Exception as e:
            print(f"[ERROR] KillQueueManager.get_kill_queue 失败: {e}")
            return {
                "data": [],
                "pagination": {"total": 0, "limit": limit, "offset": offset, "pages": 0},
                "metadata": {"updatedAt": datetime.now().isoformat(), "dataFreshness": "ERROR", "systemHealth": 0.0}
            }
    
    def _format_kill_queue_item(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化单个队列项
        
        Args:
            record: 数据库记录
        
        Returns:
            格式化后的字典
        """
        # 计算阶段年龄
        created_at = record.get("created_at")
        if isinstance(created_at, str):
            try:
                created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                age_seconds = (datetime.now(created_dt.tzinfo) - created_dt).total_seconds()
                age_minutes = int(age_seconds / 60)
                phase_age = f"{int(age_seconds // 3600):02d}:{int((age_seconds % 3600) // 60):02d}:{int(age_seconds % 60):02d}"
            except:
                age_minutes = 0
                phase_age = "00:00:00"
        else:
            age_minutes = 0
            phase_age = "00:00:00"
        
        # 提取权重
        weights = record.get("weights", {})
        if isinstance(weights, str):
            import json
            try:
                weights = json.loads(weights)
            except:
                weights = {}
        
        # 提取 features（JSONB 字段）
        features = record.get("features", {})
        if isinstance(features, str):
            import json
            try:
                features = json.loads(features)
            except:
                features = {}
        
        # 提取 decision_policy（JSONB 字段）
        decision_policy = record.get("decision_policy", {})
        if isinstance(decision_policy, str):
            import json
            try:
                decision_policy = json.loads(decision_policy)
            except:
                decision_policy = {}
        
        # 提取阶段（优先从 features 中提取，因为这是原始数据）
        phase = features.get("phase") or record.get("phase") or record.get("market_phase", "UNKNOWN")
        
        # 提取阶段年龄（从 features 中提取 phase_age_candles，转换为分钟）
        phase_age_candles = features.get("phase_age_candles") or features.get("phase_age")
        if phase_age_candles is not None:
            # 假设是 15m K线，1 根 K线 = 15 分钟
            phase_age_minutes_from_features = int(phase_age_candles) * 15
            if phase_age_minutes_from_features > 0:
                age_minutes = phase_age_minutes_from_features
        
        # 计算 AI 评分（0-100）
        final_score = record.get("final_score", 0.0)
        ai_score = float(final_score) * 100.0
        
        # 提取四维评分（原始值，0-1 范围）
        structure_score = record.get("structure_score")
        volatility_score = record.get("volatility_score")
        sentiment_score = record.get("sentiment_score")
        manipulation_score = record.get("manipulation_score")
        
        # 提取 V4.4 策略信息
        strategy_id = record.get("strategy_id")
        side = record.get("side", "LONG")
        strategy_score = record.get("strategy_score")
        
        # 提取决策信息
        should_trade = decision_policy.get("should_trade", False)
        position_size_multiplier = decision_policy.get("position_size_multiplier", 0.0)
        block_reason = decision_policy.get("block_reason") or decision_policy.get("reason", "")
        
        # 提取价格（优先从 features 中提取）
        price_value = features.get("current_price") or features.get("price") or record.get("price", 0.0)
        
        return {
            "symbol": record.get("symbol", "UNKNOWN"),
            "price": float(price_value) if price_value else 0.0,
            "change24h": float(record.get("change_24h", 0.0)),
            "changePercent": float(record.get("change_24h", 0.0)),
            "aiScore": round(ai_score, 1),
            "final_score": float(final_score),  # 原始 final_score (0-1)
            "phase": phase,
            "phaseAge": phase_age,
            "ageInMinutes": age_minutes,
            "reason": record.get("reason") or decision_policy.get("reason", "AI 评分达标"),
            "confidence": float(final_score),
            "weights": {
                "structure": float(weights.get("structure", 0.25)),
                "sentiment": float(weights.get("sentiment", 0.25)),
                "volatility": float(weights.get("volatility", 0.25)),
                "manipulation": float(weights.get("manipulation", 0.25)),
            },
            # V4.3 Kill Board 必需字段
            "structure_score": float(structure_score) if structure_score is not None else None,
            "volatility_score": float(volatility_score) if volatility_score is not None else None,
            "sentiment_score": float(sentiment_score) if sentiment_score is not None else None,
            "manipulation_score": float(manipulation_score) if manipulation_score is not None else None,
            "should_trade": should_trade,
            "position_size_multiplier": float(position_size_multiplier) if position_size_multiplier else 0.0,
            "block_reason": block_reason,
            "decision_policy": decision_policy,
            "features": features,
            # V4.4 策略信息
            "strategy_id": strategy_id,
            "strategyId": strategy_id,  # 前端期望的驼峰命名
            "side": side,
            "strategy_score": float(strategy_score) if strategy_score is not None else None,
            # 保留额外字段供未来使用
            "technicalSignals": record.get("technical_signals", []),
            "riskLevel": self._calculate_risk_level(final_score, phase),
            "expectedMove": float(record.get("expected_move", 0.0)),
            "expectedMovePercent": float(record.get("expected_move_percent", 0.0)),
            "volume24h": float(record.get("volume_24h", 0.0)),
            "liquidity": self._calculate_liquidity(record.get("volume_24h", 0.0)),
            "timestamp": created_at or datetime.now().isoformat(),
            "lastUpdated": record.get("updated_at", created_at) or datetime.now().isoformat(),
        }
    
    def _calculate_risk_level(self, score: float, phase: str) -> str:
        """计算风险等级"""
        if score >= 0.8:
            return "low"
        elif score >= 0.6:
            return "medium"
        else:
            return "high"
    
    def _calculate_liquidity(self, volume_24h: float) -> str:
        """计算流动性等级"""
        if volume_24h >= 100_000_000:
            return "high"
        elif volume_24h >= 10_000_000:
            return "medium"
        else:
            return "low"
    
    def subscribe_to_updates(self, callback: Callable[[List[Dict[str, Any]]], None]):
        """
        订阅实时更新
        
        Args:
            callback: 回调函数，接收更新后的队列数据
        """
        self.subscribers.append(callback)
    
    def notify_subscribers(self, data: List[Dict[str, Any]]):
        """通知所有订阅者"""
        for callback in self.subscribers:
            try:
                callback(data)
            except Exception as e:
                print(f"[ERROR] KillQueueManager 通知订阅者失败: {e}")


# 全局单例
_kill_queue_manager: Optional[KillQueueManager] = None


def get_kill_queue_manager() -> KillQueueManager:
    """获取全局 KillQueueManager 实例"""
    global _kill_queue_manager
    if _kill_queue_manager is None:
        _kill_queue_manager = KillQueueManager()
    return _kill_queue_manager

