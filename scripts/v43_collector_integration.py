"""
V4.3 Collector 集成辅助函数（性能优化版）

提供 V4.3 模块与 collector.py 集成的辅助函数
支持性能优化版本的特征提取和分数计算
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import os
import time

# 性能优化开关（环境变量控制）
V43_PERF_OPTIMIZED = os.environ.get("V43_PERF_OPTIMIZED", "1") in ("1", "true", "True")

# 根据配置选择使用优化版本或标准版本
if V43_PERF_OPTIMIZED:
    try:
        from v43_feature_extractor_optimized import extract_features
        from v43_score_calculator_optimized import aggregate_score
        _using_optimized = True
    except ImportError:
        # 如果优化版本不存在，回退到标准版本
        from v43_feature_extractor import extract_features
        from v43_score_calculator import aggregate_score
        _using_optimized = False
else:
    from v43_feature_extractor import extract_features
    from v43_score_calculator import aggregate_score
    _using_optimized = False

from v43_hard_filters import pass_hard_filters
from v43_decision_policy import decision_policy, detect_market_regime, get_account_stage
from v43_weight_manager import load_weights
from v43_chandelier_stop import initialize_position

# V4.4 策略路由（可选）
V44_ENABLED = os.environ.get("V44_ENABLED", "0") in ("1", "true", "True")
try:
    from v44_strategy_router import route_strategy, StrategyResult
    V44_AVAILABLE = True
except ImportError:
    V44_AVAILABLE = False
    StrategyResult = None  # type: ignore

# 权重缓存（避免重复加载）
_weight_cache: Optional[Dict[str, float]] = None
_weight_cache_time: float = 0.0
_weight_cache_ttl: float = 60.0  # 权重缓存有效期 60 秒


def build_v43_trade_score_row(
    symbol: str,
    features: Dict[str, Any],
    score_result: Dict[str, Any],
    decision_result: Dict[str, Any],
    weights: Dict[str, float],
    ai_decision_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    构建写入 trade_scores_v43 表的行数据
    
    Args:
        symbol: 交易对符号
        features: 特征字典
        score_result: 分数计算结果
        decision_result: 决策策略结果
        weights: 权重字典
        ai_decision_id: AI 决策 ID（可选）
    
    Returns:
        行数据字典
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # V4.4 策略路由字段（如果存在）
    strategy_id = decision_result.get("strategy_id") or features.get("strategy_id")
    side = decision_result.get("side") or features.get("side") or "LONG"
    strategy_score = decision_result.get("strategy_score")
    
    return {
        "created_at": now_iso,
        "symbol": symbol,
        "features": features,
        "structure_score": score_result.get("structure_score"),
        "volatility_score": score_result.get("volatility_score"),
        "sentiment_score": score_result.get("sentiment_score"),
        "manipulation_score": score_result.get("manipulation_score"),
        "final_score": score_result.get("final_score"),
        "weights": weights,
        "weights_version": weights.get("version", "v4.3.0"),
        "ai_decision_id": ai_decision_id,
        "decision_policy": decision_result,
        "opportunity_density_score": None,  # 需要从外部计算
        "executed": decision_result.get("should_trade", False),
        "reason": decision_result.get("reason", ""),
        # V4.4 策略路由字段
        "strategy_id": strategy_id,
        "side": side,
        "strategy_score": strategy_score,
    }


def process_v43_trading_decision(
    symbol: str,
    price: float,
    metrics: Dict[str, Any],
    weights: Optional[Dict[str, float]] = None,
    account_balance: float = 10000.0,
    initial_balance: float = 10000.0,
    supabase_client=None,  # 新增：用于查询持仓
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    处理 V4.3 交易决策流程
    
    Args:
        symbol: 交易对符号
        price: 当前价格
        metrics: 市场指标（包含所有必要数据）
        weights: 权重字典（如果为 None，则从配置文件加载）
        account_balance: 账户余额
        initial_balance: 初始余额
    
    Returns:
        (features, score_result, decision_result)
    """
    # 1. 加载权重（带缓存）
    if weights is None:
        weights = _get_cached_weights()
    
    # 2. 提取特征（带异常处理）
    try:
        features = extract_features(
            symbol=symbol,
            price=price,
            funding_rate=metrics.get("funding_rate"),
            long_short_ratio=metrics.get("ls_ratio"),
            oi_value=metrics.get("oi_value"),
            oi_change_1h=metrics.get("oi_change"),
            price_change_1h=metrics.get("price_change"),
            cvd_data=metrics.get("cvd_data"),
            oi_series=metrics.get("oi_series"),
            prices=metrics.get("prices"),
            highs_1h=metrics.get("highs_1h"),
            closes_1h=metrics.get("closes_1h"),
            phase_4h=metrics.get("phase_4h"),
            phase_1h=metrics.get("phase_1h"),
            phase_age_candles=metrics.get("phase_age_candles"),
            atr_value=metrics.get("atr_value"),
            ohlcv_15m=metrics.get("ohlcv_15m"),
        )
    except Exception as e:
        # 特征提取失败，返回空特征字典
        print(f"[WARNING] V4.3 特征提取失败 ({symbol}): {type(e).__name__}: {e}")
        features = {
            "phase": "P1_NO_WHALE",
            "phase_age": 0,
            "htf_align": 0,
            "atr": 0.0,
            "atr_expand": 0.0,
            "range_left": 0.0,
            "funding": 0.0,
            "ls_ratio": 1.0,
            "oi_change": 0.0,
            "lower_wick": 0.0,
            "liq_cluster": 0.0,
            "volume_spike": 0.0,
        }
    
    # 3. 先计算分数（V4.3 核心价值：可解释性，即使硬约束不通过也要算出分数）
    try:
        score_result = aggregate_score(features, weights)
    except Exception as e:
        # 分数计算失败，返回零分
        return (
            features,
            {"final_score": 0.0, "block_reason": f"SCORE_CALC_ERROR: {type(e).__name__}"},
            {"should_trade": False, "reason": f"分数计算失败: {e}"},
        )
    
    # 4. 检查硬约束（在计算分数之后，只影响 should_trade，不影响分数本身）
    # ✅ 手术一：分数与拦截完全解耦，即使被拦截也保留原始分数
    hard_filter_passed = True
    hard_filter_reason = ""
    block_reasons = []
    
    try:
        hard_filter_passed, hard_filter_reason = pass_hard_filters(features)
        
        # ✅ 增强：收集所有拦截原因（用于前端显示）
        if not hard_filter_passed:
            block_reasons.append(hard_filter_reason)
        
        # 如果分数计算中有 block_reason（例如波动率拦截），也加入列表
        # ✅ 关键：必须在策略路由之前收集，因为 Vulture 策略需要知道 block_reason
        score_block_reason = score_result.get("block_reason", "")
        if score_block_reason and score_block_reason not in block_reasons:
            block_reasons.append(score_block_reason)
    except Exception as e:
        # 硬约束检查失败，保留分数但标记为不允许
        hard_filter_passed = False
        hard_filter_reason = f"HARD_FILTER_ERROR: {type(e).__name__}"
        block_reasons = [hard_filter_reason]
    
    # 5. V4.4 策略路由（如果启用）- 在硬约束检查之后，但即使硬约束不通过也要执行
    # ✅ 关键修复：策略路由需要知道 block_reason，所以必须在硬约束检查之后执行
    # ✅ 但即使硬约束不通过，也要执行策略路由（Vulture 策略就是针对被拦截的情况）
    strategy_result = None
    if V44_ENABLED and V44_AVAILABLE:
        try:
            # 收集所有拦截原因
            all_block_reasons = block_reasons.copy()
            
            # 确保 features 中包含 symbol（策略路由可能需要）
            if "symbol" not in features:
                features["symbol"] = symbol
            
            # 执行策略路由（即使硬约束不通过也要执行）
            block_reason_str = ", ".join(all_block_reasons) if all_block_reasons else ""
            
            # 调试日志（仅在调试模式）
            debug_mode = os.environ.get("V44_DEBUG", "0") in ("1", "true", "True")
            if debug_mode:
                print(f"[V4.4 DEBUG] 调用策略路由: symbol={symbol}, phase={features.get('phase')}, block_reason={block_reason_str}")
            
            strategy_result = route_strategy(
                features=features,
                score_result=score_result,
                block_reason=block_reason_str,
            )
            
            # 调试日志
            if debug_mode:
                print(f"[V4.4 DEBUG] 策略路由返回: strategy_id={strategy_result.id if strategy_result else 'None'}")
            
            # 如果策略路由返回 WAIT，检查是否是观察模式
            if strategy_result and strategy_result.id == "WAIT":
                # 如果 reason 里包含 [WATCHLIST]，记录观察日志
                if "[WATCHLIST]" in strategy_result.reason:
                    print(f"[👁️ WATCH] {symbol:15s} | 进入观察池: {strategy_result.reason}")
                    # 可以在这里做 insert_to_watchlist_db(symbol) 的操作（如果需要）
                # 返回 WAIT，拒绝交易
                return (features, score_result, {
                    "should_trade": False,
                    "strategy_id": "WAIT",
                    "side": "NONE",
                    "reason": strategy_result.reason,
                    "block_reason": "WAIT_STRATEGY",
                    "block_reasons": all_block_reasons + ["WAIT_STRATEGY"],
                })
            
            # 如果策略路由返回非 WAIT，使用策略路由的结果（即使硬约束不通过）
            # V4.5 变更：SNIFFER 已禁用，只有 SNIPER 和 VULTURE 能进入交易流程
            if strategy_result and strategy_result.id != "WAIT":
                # 额外检查：确保不是 SNIFFER（虽然路由已经不会返回 SNIFFER，但双重保险）
                if strategy_result.id == "SNIFFER":
                    # SNIFFER 已禁用，记录观察日志但不交易
                    print(f"[👁️ WATCH] {symbol:15s} | SNIFFER 已禁用（V4.5 降级为观察者）")
                    # 返回 WAIT，拒绝交易
                    decision_result = {
                        "should_trade": False,
                        "strategy_id": "WAIT",
                        "side": "NONE",
                        "reason": "SNIFFER 策略已禁用（V4.5 降级为观察者）",
                        "block_reason": "SNIFFER_DISABLED",
                        "block_reasons": all_block_reasons + ["SNIFFER_DISABLED"],
                    }
                    return (features, score_result, decision_result)
                # 检查持仓限制（最大同时持仓数）
                try:
                    from v44_position_checker import check_position_limit, get_open_positions_by_strategy
                    position_limit_passed, position_limit_msg = check_position_limit(
                        supabase_client=supabase_client,
                        strategy_id=strategy_result.id
                    )
                    
                    # 调试信息：显示当前持仓情况
                    if debug_mode:
                        positions_by_strategy, total_count = get_open_positions_by_strategy(supabase_client)
                        current_strategy_positions = positions_by_strategy.get(strategy_result.id, 0)
                        print(f"[V4.4 DEBUG] 持仓检查: {strategy_result.id} 当前持仓={current_strategy_positions}, 全局持仓={total_count}, 结果={position_limit_msg}")
                    
                    if not position_limit_passed:
                        # 超过持仓限制，阻止交易
                        print(f"[V4.4] {symbol:15s} | Strategy: {strategy_result.id:8s} | BLOCKED: {position_limit_msg}")
                        decision_result = {
                            "should_trade": False,
                            "strategy_id": strategy_result.id,
                            "side": strategy_result.side,
                            "reason": f"持仓限制: {position_limit_msg}",
                            "strategy_score": strategy_result.score,
                            "block_reason": f"持仓限制: {position_limit_msg}",
                            "block_reasons": all_block_reasons + [f"持仓限制: {position_limit_msg}"],
                        }
                        return (features, score_result, decision_result)
                except ImportError as e:
                    # 如果导入失败，跳过持仓限制检查（向后兼容）
                    if debug_mode:
                        print(f"[V4.4 DEBUG] 持仓检查模块导入失败: {e}")
                    position_limit_passed = True
                except Exception as e:
                    # 如果查询失败，允许交易（向后兼容）
                    print(f"[WARNING] 持仓检查失败: {e}")
                    position_limit_passed = True
                
                # 使用策略路由的结果
                # 注意：策略路由日志已在 collector.py 中打印，这里不再重复打印
                # print(f"[V4.4] {symbol:15s} | Strategy: {strategy_result.id:8s} | Score: {strategy_result.score:5.1f} | Side: {strategy_result.side:5s} | {strategy_result.reason}")
                
                # 构建决策结果
                decision_result = {
                    "should_trade": True,  # 策略路由认为可以交易（即使硬约束不通过）
                    "strategy_id": strategy_result.id,
                    "side": strategy_result.side,
                    "confidence": strategy_result.confidence,
                    "position_size_multiplier": strategy_result.risk_profile.get("position_size", 1.0),
                    "stop_loss_atr_multiplier": strategy_result.risk_profile.get("stop_loss_atr_multiplier", 2.0),
                    "entry_type": "market" if strategy_result.side == "LONG" else "market_short",
                    "reason": strategy_result.reason,
                    "strategy_score": strategy_result.score,
                    "block_reason": ", ".join(all_block_reasons) if all_block_reasons else "",  # 保留拦截原因（用于日志）
                    "block_reasons": all_block_reasons,  # 所有拦截原因列表
                }
                
                # 更新 features，添加策略信息
                features["strategy_id"] = strategy_result.id
                features["side"] = strategy_result.side
                
                return (features, score_result, decision_result)
        except Exception as e:
            print(f"[WARNING] V4.4 策略路由失败 ({symbol}): {type(e).__name__}: {e}")
            # 策略路由失败，继续使用原有逻辑
    
    # 6. 如果分数计算中有 block_reason（例如预期收益 < 2%），且策略路由未触发，返回拦截结果
    # ✅ 注意：这个检查必须在策略路由之后，因为 Vulture 策略需要知道 block_reason
    if score_result.get("block_reason") and (not strategy_result or strategy_result.id == "WAIT"):
        # 如果 block_reason 不在 block_reasons 中，添加它
        score_block_reason = score_result.get("block_reason")
        if score_block_reason not in block_reasons:
            block_reasons.append(score_block_reason)
        
        return (
            features,
            score_result,  # 保留计算出的分数（可能不是 0.0）
            {
                "should_trade": False,
                "position_size_multiplier": 0.0,
                "entry_type": "skip",
                "reason": f"分数计算拦截: {score_block_reason}",
                "block_reason": score_block_reason,
                "block_reasons": block_reasons,  # 所有拦截原因列表
            },
        )
    
    # 7. 如果硬约束不通过且策略路由未触发，返回拦截结果
    if not hard_filter_passed and (not strategy_result or strategy_result.id == "WAIT"):
        # ✅ 正确实现：返回计算出的分数，但标记为不允许交易
        return (
            features,
            score_result,  # 保留计算出的分数（不是 0.0）
            {
                "should_trade": False,
                "position_size_multiplier": 0.0,
                "entry_type": "skip",
                "reason": f"硬约束拦截: {hard_filter_reason}",
                "block_reason": hard_filter_reason,  # 主要拦截原因
                "block_reasons": block_reasons,  # 所有拦截原因列表（用于前端显示）
            },
        )
    
    # 8. 决策策略层（带异常处理）- V4.3 原有逻辑
    try:
        market_regime = detect_market_regime(features)
        account_stage = get_account_stage(account_balance, initial_balance)
        opportunity_density = 0.5  # 默认值，需要从外部计算
        
        decision_result = decision_policy(
            score_result=score_result,
            market_regime=market_regime,
            account_stage=account_stage,
            opportunity_density=opportunity_density,
        )
    except Exception as e:
        # 决策策略失败，默认不交易
        decision_result = {
            "should_trade": False,
            "position_size_multiplier": 0.0,
            "entry_type": "skip",
            "reason": f"决策策略失败: {type(e).__name__}: {e}",
        }
    
    return (features, score_result, decision_result)


def _get_cached_weights() -> Dict[str, float]:
    """获取权重（带缓存）"""
    global _weight_cache, _weight_cache_time
    
    current_time = time.time()
    
    # 检查缓存是否有效
    if _weight_cache is None or (current_time - _weight_cache_time) > _weight_cache_ttl:
        _weight_cache = load_weights()
        _weight_cache_time = current_time
    
    return _weight_cache


def clear_weight_cache():
    """清空权重缓存（用于测试或手动清理）"""
    global _weight_cache, _weight_cache_time
    _weight_cache = None
    _weight_cache_time = 0.0


__all__ = [
    "build_v43_trade_score_row",
    "process_v43_trading_decision",
    "clear_weight_cache",
]

