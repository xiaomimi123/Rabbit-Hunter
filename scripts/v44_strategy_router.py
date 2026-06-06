"""
V4.4 策略路由模块

根据市场特征，将交易机会路由到最适合的策略：
- Sniffer (潜伏者): P2 吸筹阶段，提前布局
- Sniper (狙击手): P3A 主升浪，重仓出击
- Vulture (秃鹫): P3B/P4 出货阶段，反手做空
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional, Literal
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# 导入策略配置
try:
    from v44_strategy_config import check_strategy_threshold, get_strategy_threshold
except ImportError:
    # 如果导入失败，使用默认函数
    def check_strategy_threshold(strategy_id: str, score: float) -> tuple[bool, str]:
        """默认实现：所有策略都需要 60 分"""
        min_score = 60.0
        if score >= min_score:
            return True, f"Score {score:.1f} >= {min_score:.1f} (Pass)"
        else:
            return False, f"Score {score:.1f} < {min_score:.1f} (Fail)"
    
    def get_strategy_threshold(strategy_id: str) -> float:
        """默认实现：返回 60 分"""
        return 60.0

# 导入策略路由动态配置
try:
    from v44_strategy_router_config import get_router_config
except ImportError:
    # 如果导入失败，使用默认配置
    def get_router_config():
        return {
            "SNIPER": {"min_structure_score": 60.0, "position_size": 1.0, "stop_loss_atr_multiplier": 2.0},
            "SNIFFER": {"enabled": False, "min_oi_growth": 0.05, "min_volume_spike": 3.0, "min_whale_activity": 0.7},
            "VULTURE": {"min_oi_drop": -0.03, "min_score_boost": 60.0, "position_size": 0.5, "stop_loss_atr_multiplier": 1.5},
        }


@dataclass
class StrategyResult:
    """策略路由结果"""
    id: str  # 'SNIFFER', 'SNIPER', 'VULTURE', 'WAIT'
    score: float  # 策略特定评分 (0-100)
    side: str  # 'LONG', 'SHORT', 'NONE'
    confidence: float  # 置信度 (0-1)
    risk_profile: Dict[str, float]  # 风险配置 {position_size, stop_loss_atr_multiplier}
    reason: str  # 触发原因


def calculate_whale_activity(features: Dict[str, Any]) -> float:
    """
    计算庄家活动强度（0-1）
    
    基于多个指标综合判断：
    - OI 变化（持仓量上升 = 庄家建仓）
    - 成交量异动（爆量 = 庄家行动）
    - 资金费率异常（负费率 = 庄家做多）
    - 多空比变化（LS 上升 = 散户接盘）
    
    Args:
        features: 特征字典
        
    Returns:
        whale_activity: 0-1，越高表示庄家活动越明显
    """
    # 从动态配置加载参数
    config = get_router_config()
    whale_weights = config.get("WHALE_ACTIVITY_WEIGHTS", {
        "oi_score": 0.4,
        "volume_score": 0.3,
        "funding_score": 0.2,
        "ls_score": 0.1,
    })
    whale_thresholds = config.get("WHALE_ACTIVITY_THRESHOLDS", {
        "oi_max": 0.10,
        "volume_max": 3.0,
        "funding_max": 0.001,
        "ls_max": 2.0,
    })
    
    oi_change = features.get("oi_change", 0) or 0
    volume_spike = features.get("volume_spike", 0) or 0
    funding_rate = features.get("funding", 0) or 0
    ls_ratio = features.get("ls_ratio", 1.0) or 1.0
    
    # oi_change 始终是百分比形式（如 5.0 = 5%），统一除以 100 转为小数
    oi_change_decimal = oi_change / 100.0
    
    # 归一化各项指标（使用动态配置的阈值）
    oi_score = min(abs(oi_change_decimal) / whale_thresholds["oi_max"], 1.0) if oi_change_decimal > 0 else 0.0
    volume_score = min(volume_spike / whale_thresholds["volume_max"], 1.0) if volume_spike > 0 else 0.0
    funding_score = min(abs(funding_rate) / whale_thresholds["funding_max"], 1.0) if funding_rate < 0 else 0.0
    ls_score = min((ls_ratio - 1.0) / (whale_thresholds["ls_max"] - 1.0), 1.0) if ls_ratio > 1.0 else 0.0
    
    # 加权平均（使用动态配置的权重）
    whale_activity = (
        oi_score * whale_weights["oi_score"] +
        volume_score * whale_weights["volume_score"] +
        funding_score * whale_weights["funding_score"] +
        ls_score * whale_weights["ls_score"]
    )
    
    return min(whale_activity, 1.0)


def detect_btc_trend() -> Literal["SUPER_BULL", "BULL", "NEUTRAL", "BEAR"]:
    """
    检测 BTC 趋势（简化版）
    
    注意：这是一个简化实现，实际应该从交易所获取 BTC 价格数据
    目前返回 NEUTRAL，后续可以集成真实的 BTC 趋势检测
    
    Returns:
        btc_trend: BTC 趋势状态
    """
    # TODO: 集成真实的 BTC 趋势检测
    # 可以从 Binance API 获取 BTC/USDT 价格，计算趋势
    # 或者从 Supabase 查询 BTC 的历史数据
    
    # 临时实现：从环境变量读取（如果配置了）
    btc_trend_env = os.environ.get("BTC_TREND", "NEUTRAL").upper()
    if btc_trend_env in ["SUPER_BULL", "BULL", "NEUTRAL", "BEAR"]:
        return btc_trend_env
    
    # 默认返回 NEUTRAL（不做限制）
    return "NEUTRAL"


def route_strategy(
    features: Dict[str, Any],
    score_result: Dict[str, Any],
    block_reason: str = "",
) -> StrategyResult:
    """
    策略路由：根据特征判断最适合的策略
    
    Args:
        features: 特征字典
        score_result: 分数计算结果
        block_reason: 拦截原因（如果有）
        
    Returns:
        StrategyResult: 策略结果
    """
    phase = features.get("phase", "P1_NO_WHALE")
    structure_score = score_result.get("structure_score", 0) or 0
    sentiment_score = score_result.get("sentiment_score", 0) or 0
    final_score = score_result.get("final_score", 0) or 0
    
    # 调试日志（仅在调试模式）
    debug_mode = os.environ.get("V44_DEBUG", "0") in ("1", "true", "True")
    if debug_mode:
        symbol = features.get("symbol", "UNKNOWN")
        oi_change = features.get("oi_change", 0) or 0
        print(f"[V4.4 DEBUG] {symbol} | phase={phase} | oi_change={oi_change} | block_reason={block_reason}")
    
    # 转换为百分比（如果 score_result 是 0-1 范围）
    if isinstance(structure_score, float) and structure_score <= 1.0:
        structure_score = structure_score * 100
    if isinstance(sentiment_score, float) and sentiment_score <= 1.0:
        sentiment_score = sentiment_score * 100
    if isinstance(final_score, float) and final_score <= 1.0:
        final_score = final_score * 100
    
    # 从动态配置加载参数
    config = get_router_config()
    sniper_config = config.get("SNIPER", {})
    sniffer_config = config.get("SNIFFER", {})
    vulture_config = config.get("VULTURE", {})
    
    # ============================================
    # 1. 执行层 A (The Sniper - 狙击手，V4.5 独尊)
    # ============================================
    # V4.5 变更：只有 P3A 且结构分高，才允许做多
    if phase == "P3A_PUMP_START":
        min_structure_score = sniper_config.get("min_structure_score", 60.0)
        if structure_score > min_structure_score:
            # 检查策略特定门槛（SNIPER 需要 60 分）
            sniper_threshold = get_strategy_threshold("SNIPER")
            passed, threshold_msg = check_strategy_threshold("SNIPER", structure_score)
            if passed:
                return StrategyResult(
                    id="SNIPER",
                    score=structure_score,
                    side="LONG",
                    confidence=sniper_config.get("min_confidence", 0.8),
                    risk_profile={
                        "position_size": sniper_config.get("position_size", 1.0),
                        "stop_loss_atr_multiplier": sniper_config.get("stop_loss_atr_multiplier", 2.0),
                    },
                    reason=f"P3A 主升浪确认，结构分 {structure_score:.1f}，适合重仓出击"
                )
            else:
                # 分数不够，返回 WAIT
                if debug_mode:
                    print(f"[V4.4 DEBUG] SNIPER 分数不足: {threshold_msg}")
    
    # ============================================
    # 2. 观察层 (The Watcher - 原 Sniffer，V4.5 降级为观察者)
    # ============================================
    # V4.5 变更：SNIFFER 已禁用交易，只保留观察功能
    # 即使发现异动，也只记录，不返回交易策略 ID
    if phase == "P2_ACCUMULATION":
        # 检查是否启用 SNIFFER（从动态配置读取）
        sniffer_enabled = sniffer_config.get("enabled", False)
        
        # 计算庄家活动强度（仅用于观察）
        whale_activity = calculate_whale_activity(features)
        oi_change = features.get("oi_change", 0) or 0
        volume_spike = features.get("volume_spike", 0) or 0
        
        # oi_change 始终是百分比形式（如 5.0 = 5%），统一除以 100 转为小数
        oi_change_decimal = oi_change / 100.0
        
        # 检查是否有异动（使用动态配置的阈值）
        min_oi_growth = sniffer_config.get("min_oi_growth", 0.05)
        min_volume_spike = sniffer_config.get("min_volume_spike", 3.0)
        min_whale_activity = sniffer_config.get("min_whale_activity", 0.7)
        
        has_strong_oi_growth = oi_change_decimal > min_oi_growth
        has_strong_volume = volume_spike > min_volume_spike
        has_whale_activity = whale_activity > min_whale_activity
        
        # 如果发现异动，返回 WAIT 但标记为观察
        if has_strong_oi_growth or has_strong_volume or has_whale_activity:
            # 返回 WAIT，但在 reason 里写清楚，方便我们看到它在"瞪着猎物"
            return StrategyResult(
                id="WAIT",
                score=0,
                side="NONE",
                confidence=0.0,
                risk_profile={},
                reason=f"[WATCHLIST] P2 Accumulation Detected. OI={oi_change:.2%}, Volume={volume_spike:.1f}x, Whale={whale_activity:.2f}. Waiting for Breakout..."
            )
    
    # ============================================
    # 3. 执行层 B (The Vulture - 秃鹫，V4.5 加权)
    # ============================================
    # V4.5 变更：做空是当前的主力，给它足够的空间
    # 门槛从 75 放宽到 70，持仓从 3 提升到 5
    # v45 临时止血：默认禁用 SHORT 入场（chandelier_stop 数学 + funding 符号未修）
    if phase in ["P3B_PUMP_LATE", "P4_DISTRIBUTION"]:
        # SHORT kill switch — 在跑完 OI/structure 计算和 AI 二次决策前提前返回，省 token
        if os.environ.get("ENABLE_SHORT_TRADING", "false").lower() not in ("1", "true"):
            return StrategyResult(
                id="WAIT",
                score=0,
                side="NONE",
                confidence=0.0,
                risk_profile={},
                reason=f"SHORT kill switch active (ENABLE_SHORT_TRADING=false) — phase={phase} 候选忽略"
            )
        # Vulture 触发条件：
        # - 被 LOW_EXPECTED_RETURN 拦截（上方无空间）
        # - OI 下降 > 3%（庄家平多，3% 的出货已经很明显）
        oi_change = features.get("oi_change", 0) or 0
        
        # 检查是否被 LOW_EXPECTED_RETURN 拦截
        has_low_expected = block_reason and "LOW_EXPECTED" in block_reason.upper()
        # oi_change 始终是百分比形式（如 -3.0 = -3%），统一除以 100 转为小数
        oi_change_decimal = oi_change / 100.0
        min_oi_drop = vulture_config.get("min_oi_drop", -0.03)  # 从动态配置读取
        has_oi_drop = oi_change_decimal < min_oi_drop
        
        # 调试日志
        if debug_mode:
            symbol = features.get("symbol", "UNKNOWN")
            print(f"[V4.4 DEBUG] {symbol} | Vulture检查: phase={phase}, has_low_expected={has_low_expected}, oi_change={oi_change} ({oi_change_decimal:.4f}), has_oi_drop={has_oi_drop}")
        
        if has_low_expected and has_oi_drop:
            # 检查 BTC 趋势（牛市不做空）
            btc_trend = detect_btc_trend()
            if btc_trend == "SUPER_BULL":
                return StrategyResult(
                    id="WAIT",
                    score=0,
                    side="NONE",
                    confidence=0.0,
                    risk_profile={},
                    reason="BTC 超级牛市，禁止做空"
                )
            
            # 计算做空信号强度（基于 OI 下降幅度和结构分数）
            # 注意：使用 oi_change_decimal 进行计算
            # 从动态配置读取参数
            vulture_score_config = config.get("VULTURE_SCORE", {})
            oi_contribution_max = vulture_score_config.get("oi_contribution_max", 0.10)
            structure_weight = vulture_score_config.get("structure_weight", 0.5)
            oi_weight = vulture_score_config.get("oi_weight", 0.5)
            
            # OI 下降幅度贡献：下降 3% = 30分，下降 10% = 100分（线性）
            oi_contribution = min(abs(oi_change_decimal) / oi_contribution_max, 1.0) * 100

            # 结构分数贡献（structure_score 已经在 L168-173 被转换到 0-100，
            # 这里不能再乘 100 — v45 修复：之前的 *100 让 VULTURE 分数飙到 ~3000，
            # 等于任何 P3B/P4 候选都能过 70 阈值）
            structure_contribution = structure_score if structure_score > 0 else 0
            
            # 综合分数：OI 贡献和结构分数加权平均（使用动态配置的权重）
            if structure_contribution > 0:
                short_signal_strength = (oi_contribution * oi_weight + structure_contribution * structure_weight) / (oi_weight + structure_weight)
            else:
                # 如果没有结构分数，仅基于 OI 下降
                short_signal_strength = oi_contribution
            
            # 放宽版：确保分数至少能达到配置的阈值（如果接近）
            min_score_boost = vulture_config.get("min_score_boost", 60.0)
            min_score_boost_threshold = vulture_config.get("min_score_boost_threshold", 50.0)
            vulture_score = max(short_signal_strength, min_score_boost) if short_signal_strength > min_score_boost_threshold else short_signal_strength
            
            # 检查策略特定门槛（VULTURE 需要 70 分，V4.5 放宽）
            passed, threshold_msg = check_strategy_threshold("VULTURE", vulture_score)
            if passed:
                # 从动态配置读取置信度和风险配置
                high_oi_drop_threshold = vulture_config.get("high_oi_drop_threshold", 0.10)
                confidence_high = vulture_config.get("confidence_high_oi_drop", 0.7)
                confidence_normal = vulture_config.get("confidence_normal", 0.6)
                
                return StrategyResult(
                    id="VULTURE",
                    score=vulture_score,
                    side="SHORT",
                    confidence=confidence_high if abs(oi_change_decimal) > high_oi_drop_threshold else confidence_normal,
                    risk_profile={
                        "position_size": vulture_config.get("position_size", 0.5),
                        "stop_loss_atr_multiplier": vulture_config.get("stop_loss_atr_multiplier", 1.5),
                    },
                    reason=f"P3B/P4 出货阶段，OI下降 {oi_change_decimal:.2%}，结构分 {structure_score:.1f}，适合反手做空"
                )
            else:
                # 分数不够，返回 WAIT
                if debug_mode:
                    print(f"[V4.4 DEBUG] VULTURE 分数不足: {threshold_msg}")
    
    # ============================================
    # 4. 都不满足，等待
    # ============================================
    return StrategyResult(
        id="WAIT",
        score=0,
        side="NONE",
        confidence=0.0,
        risk_profile={},
        reason=f"阶段 {phase}，无合适策略"
    )


__all__ = [
    "StrategyResult",
    "route_strategy",
    "calculate_whale_activity",
    "detect_btc_trend",
]

