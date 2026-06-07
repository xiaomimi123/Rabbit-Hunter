"""
V4.3 进场逻辑验证器

功能：
- 4D 评分校验
- 状态判定 (PASS/WAIT/FAIL)
- AI 建议生成
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# 确保 scripts 目录在路径中
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

try:
    from scripts.v43_feature_extractor import extract_features
    from scripts.v43_score_calculator import calculate_scores
    from scripts.v43_hard_filters import pass_hard_filters
    from scripts.v43_decision_policy import decision_policy
    from scripts.v43_weight_manager import get_current_weights
except ImportError as e:
    print(f"[WARNING] V4.3 EntryValidator 导入失败: {e}")
    # 尝试备用导入路径
    try:
        from v43_feature_extractor import extract_features  # type: ignore
        from v43_score_calculator import calculate_scores  # type: ignore
        from v43_hard_filters import pass_hard_filters  # type: ignore
        from v43_decision_policy import decision_policy  # type: ignore
        from v43_weight_manager import get_current_weights  # type: ignore
    except ImportError:
        pass


class EntryValidator:
    """
    进场逻辑验证器
    
    验证交易进场条件，提供详细评分和建议。
    """
    
    def validate_entry(
        self,
        symbol: str,
        leverage: int = 10,
        risk: float = 2.0
    ) -> Dict[str, Any]:
        """
        验证进场条件
        
        Args:
            symbol: 交易对
            leverage: 杠杆倍数
            risk: 风险比例（百分比）
        
        Returns:
            验证结果字典
        """
        try:
            # 1. 获取基础数据（价格、funding_rate 等）
            # 尝试从数据库获取最新数据
            price = 0.0
            funding_rate = None
            long_short_ratio = None
            oi_value = None
            oi_change_1h = None
            price_change_1h = None
            
            try:
                import ccxt
                # 创建临时 exchange 实例获取数据
                exchange = ccxt.binanceusdm({
                    "enableRateLimit": True,
                    "options": {"defaultType": "future"}
                })
                
                # 获取 ticker 数据
                ticker = exchange.fetch_ticker(symbol)
                price = float(ticker.get("last") or ticker.get("close") or 0.0)
                
                # 尝试获取 funding rate（如果可用）
                try:
                    funding_info = exchange.fetch_funding_rate(symbol)
                    funding_rate = float(funding_info.get("fundingRate", 0.0)) if funding_info else None
                except Exception:
                    pass
                
            except Exception as e:
                print(f"[WARNING] EntryValidator: 无法从 API 获取数据: {e}")
                # 如果 API 获取失败，尝试从数据库获取最新记录
                try:
                    from supabase import create_client
                    SUPABASE_URL = os.environ.get("SUPABASE_URL")
                    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
                    if SUPABASE_URL and SUPABASE_KEY:
                        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
                        # 从 trade_scores_v43 获取最新记录
                        response = supabase.table("trade_scores_v43").select(
                            "features, created_at"
                        ).eq("symbol", symbol).order("created_at", desc=True).limit(1).execute()
                        
                        if response.data:
                            record = response.data[0]
                            features_data = record.get("features", {})
                            if isinstance(features_data, str):
                                import json
                                features_data = json.loads(features_data)
                            
                            price = float(features_data.get("price") or features_data.get("current_price") or 0.0)
                            funding_rate = features_data.get("funding")
                            long_short_ratio = features_data.get("ls_ratio")
                            oi_value = features_data.get("oi_value")
                            oi_change_1h = features_data.get("oi_change")
                            price_change_1h = features_data.get("price_change")
                except Exception:
                    pass
            
            # 如果价格仍然为 0，返回错误
            if price == 0.0:
                return {
                    "symbol": symbol,
                    "error": "无法获取价格数据，请检查网络连接或币安 API 配置",
                    "timestamp": datetime.now().isoformat(),
                }
            
            # 2. 提取特征（使用获取到的数据）
            features = extract_features(
                symbol=symbol,
                price=price,
                funding_rate=funding_rate,
                long_short_ratio=long_short_ratio,
                oi_value=oi_value,
                oi_change_1h=oi_change_1h,
                price_change_1h=price_change_1h,
            )
            
            # 3. 计算分数（v0.5.1：calculate_scores 是 aggregate_score + 当前 weights 的 wrapper）
            scores = calculate_scores(features)

            # 4. 硬约束检查（v0.5.1：pass_hard_filters 实际只接受 features 一个参数）
            hard_filter_result = pass_hard_filters(features)

            # 5. 决策策略（v0.5.1：实际签名是 (score_result, market_regime, account_stage, opportunity_density)）
            try:
                from v43_decision_policy import detect_market_regime, get_account_stage  # type: ignore[import-not-found]
            except ImportError:
                from scripts.v43_decision_policy import detect_market_regime, get_account_stage  # type: ignore[import-not-found]
            # 用 features 推 regime；account_stage 默认 GROWTH（验证场景下没有真实余额）
            try:
                market_regime = detect_market_regime(features)
            except Exception:
                market_regime = "NEUTRAL"
            try:
                account_stage = get_account_stage(account_balance=10000.0 * (risk / 2.0))
            except Exception:
                account_stage = "GROWTH"
            decision = decision_policy(
                scores,
                market_regime,
                account_stage,
                opportunity_density=1.0,
            )
            
            # 6. 格式化评分结果
            score_items = [
                {
                    "label": "结构分 (Structure)",
                    "score": int(scores["structure_score"] * 100),
                    "status": "PASS" if scores["structure_score"] >= 0.6 else "WAIT",
                },
                {
                    "label": "波动率分 (Volatility)",
                    "score": int(scores["volatility_score"] * 100),
                    "status": "PASS" if scores["volatility_score"] >= 0.6 else "WAIT",
                },
                {
                    "label": "情绪分 (Sentiment)",
                    "score": int(scores["sentiment_score"] * 100),
                    "status": "PASS" if scores["sentiment_score"] >= 0.5 else "WAIT",
                },
                {
                    "label": "操纵分 (Manipulation)",
                    "score": int(scores["manipulation_score"] * 100),
                    "status": "PASS" if scores["manipulation_score"] >= 0.6 else "WAIT",
                },
            ]
            
            # 7. 生成 AI 建议
            ai_reason = self._generate_ai_reason(scores, features, decision, hard_filter_result)
            
            # 8. 计算推荐止损
            ai_stop_loss = self._calculate_ai_stop_loss(features, scores)
            
            # 9. 计算预估仓位
            estimated_position = self._calculate_estimated_position(features, risk, leverage)
            
            return {
                "symbol": symbol,
                "leverage": leverage,
                "risk": risk,
                "timestamp": datetime.now().isoformat(),
                "scores": score_items,
                "finalScore": round(scores["final_score"] * 100, 1),
                "hardFilterPassed": hard_filter_result[0],
                "hardFilterReason": hard_filter_result[1] if not hard_filter_result[0] else None,
                "shouldTrade": decision.get("should_trade", False),
                "decisionReason": decision.get("reason", ""),
                "aiReason": ai_reason,
                "aiStopLoss": ai_stop_loss,
                "estimatedPosition": estimated_position,
                "positionSizeMultiplier": decision.get("position_size_multiplier", 0.0),
            }
        except Exception as e:
            print(f"[ERROR] EntryValidator.validate_entry 失败: {e}")
            return {
                "symbol": symbol,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    def _generate_ai_reason(
        self,
        scores: Dict[str, Any],
        features: Dict[str, Any],
        decision: Dict[str, Any],
        hard_filter_result: tuple[bool, str]
    ) -> str:
        """生成 AI 建议"""
        reasons = []
        
        # 硬约束检查
        if not hard_filter_result[0]:
            reasons.append(f"硬约束未通过: {hard_filter_result[1]}")
            return " ".join(reasons)
        
        # 分数分析
        if scores["structure_score"] >= 0.8:
            reasons.append("结构空间理想")
        elif scores["structure_score"] < 0.5:
            reasons.append("结构空间不足")
        
        if scores["sentiment_score"] < 0.4:
            reasons.append("社交媒体情绪面尚不稳定")
        
        if scores["volatility_score"] >= 0.7:
            reasons.append("波动率充足，预期收益良好")
        
        # 决策建议
        if decision.get("should_trade", False):
            if decision.get("position_size_multiplier", 0) < 0.8:
                reasons.append("建议采用阶梯式建仓策略")
            reasons.append("建议在首单成交后自动开启 ATR 移动止损")
        else:
            reasons.append(f"暂不建议交易: {decision.get('reason', '评分不足')}")
        
        return "。".join(reasons) if reasons else "AI 分析完成，建议谨慎操作"
    
    def _calculate_ai_stop_loss(self, features: Dict[str, Any], scores: Dict[str, Any]) -> float:
        """计算 AI 推荐止损"""
        price = features.get("price", 0.0)
        atr = features.get("atr", 0.0)
        phase = features.get("phase", "P1_NO_WHALE")
        
        if price == 0 or atr == 0:
            return price * 0.98  # 默认 2% 止损
        
        # 根据阶段调整
        if phase == "P3A_PUMP_START":
            k = 2.5
        elif phase == "P3B_PUMP_LATE":
            k = 2.0
        else:
            k = 1.5
        
        stop_loss = price - (atr * k)
        return round(stop_loss, 2)
    
    def _calculate_estimated_position(
        self,
        features: Dict[str, Any],
        risk: float,
        leverage: int
    ) -> float:
        """计算预估仓位价值"""
        price = features.get("price", 0.0)
        if price == 0:
            return 0.0
        
        # 简化计算：假设账户余额为 10000 USDT
        account_balance = 10000.0
        risk_amount = account_balance * (risk / 100.0)
        
        # 考虑杠杆
        position_value = risk_amount * leverage
        
        return round(position_value, 2)


# 全局单例
_entry_validator: Optional[EntryValidator] = None


def get_entry_validator() -> EntryValidator:
    """获取全局 EntryValidator 实例"""
    global _entry_validator
    if _entry_validator is None:
        _entry_validator = EntryValidator()
    return _entry_validator

