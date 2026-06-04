"""
V4.3 决策策略层

将分数转换为交易决策。

为什么重要？
- 同样 0.72 分：在趋势市 = 可大仓，在震荡市 = 小仓/试单
- 防止 AI 默认：分数越高 = 越该梭哈（这在后期非常危险）
"""

from typing import Dict, Any, Literal, Optional


def detect_market_regime(
    features: Dict[str, Any],
    price_history: Optional[list[float]] = None,
) -> Literal["TRENDING", "RANGING", "UNCERTAIN"]:
    """
    识别市场状态（趋势市/震荡市）
    
    Args:
        features: 特征字典
        price_history: 价格历史（可选，用于更精确的判断）
    
    Returns:
        market_regime: "TRENDING" | "RANGING" | "UNCERTAIN"
    """
    phase = features.get("phase", "P1_NO_WHALE")
    
    # 根据阶段判断
    if phase in ["P3A_PUMP_START", "P3B_PUMP_LATE"]:
        return "TRENDING"
    elif phase == "P2_ACCUMULATION":
        return "RANGING"
    else:
        return "UNCERTAIN"


def get_account_stage(
    balance: float,
    initial_balance: float = 10000.0,
) -> Literal["GROWTH", "CONSERVATIVE"]:
    """
    获取账户阶段
    
    Args:
        balance: 当前余额
        initial_balance: 初始余额
    
    Returns:
        account_stage: "GROWTH" | "CONSERVATIVE"
    """
    # 简化：如果余额 > 初始余额 * 1.2，认为是成长期
    if balance > initial_balance * 1.2:
        return "GROWTH"
    else:
        return "CONSERVATIVE"


def clamp(value: float, min_val: float, max_val: float) -> float:
    """将值限制在范围内"""
    return max(min_val, min(max_val, value))


def decision_policy(
    score_result: Dict[str, Any],
    market_regime: str,
    account_stage: str,
    opportunity_density: float,
) -> Dict[str, Any]:
    """
    决策策略层：将分数转换为交易决策
    
    为什么重要？
    - 同样 0.72 分：
      * 在趋势市 = 可大仓
      * 在震荡市 = 小仓 / 试单
    - 同样的 score，不同账户阶段含义不同
    
    修复 3：ODS 只影响仓位，不影响是否交易！
    
    Args:
        score_result: 分数结果（来自 aggregate_score）
        market_regime: 市场状态（"TRENDING" | "RANGING" | "UNCERTAIN"）
        account_stage: 账户阶段（"GROWTH" | "CONSERVATIVE"）
        opportunity_density: 机会密度分数 (0-1)
    
    Returns:
        {
            "should_trade": bool,
            "position_size_multiplier": float,  # 仓位倍数（0.0-1.0）
            "entry_type": str,                  # "full" / "test" / "skip"
            "reason": str,
        }
    """
    final_score = score_result.get("final_score", 0.0)
    
    # ✅ 修复 3.1：更灵活的 threshold（根据市场状态）
    # 而不是固定的 0.65
    if market_regime == "TRENDING":
        threshold = 0.60  # 趋势市：降低门槛，容易赚钱
    elif market_regime == "RANGING":
        threshold = 0.70  # 震荡市：提高门槛，保护资金
    else:
        threshold = 0.65  # 不确定：中等门槛
    
    # 基础检查：是否交易（只基于 score 和 threshold）
    # ✅ 关键改变：这里不再考虑 ODS
    if final_score < threshold:
        return {
            "should_trade": False,
            "position_size_multiplier": 0.0,
            "entry_type": "skip",
            "reason": f"SCORE={final_score:.2f} < THRESHOLD={threshold:.2f}",
        }
    
    # ✅ 修复 3.2：ODS 只影响仓位，不影响是否交易
    # 基础仓位根据市场状态
    position_multiplier = {
        "TRENDING": 1.0,      # 趋势市：可以大仓
        "RANGING": 0.5,       # 震荡市：小仓试单
        "UNCERTAIN": 0.3,     # 不确定：保守试单
    }.get(market_regime, 0.5)
    
    # 根据账户阶段调整
    if account_stage == "GROWTH":
        # 成长期：可以激进
        pass
    elif account_stage == "CONSERVATIVE":
        # 保守期：降低仓位
        position_multiplier *= 0.7
    
    # ✅ 修复 3.3：ODS 作为最后的仓位微调（不影响是否交易）
    # 机会稀少时：可以承受风险，仓位保持或略增
    # 机会密集时：分散风险，仓位略减
    ods_factor = 1.0
    if opportunity_density < 0.3:
        ods_factor = 1.1  # 机会稀少，可以激进（+10%）
    elif opportunity_density > 0.8:
        ods_factor = 0.8  # 机会密集，分散（-20%）
    else:
        ods_factor = 1.0  # 机会适中，保持
    
    final_position_multiplier = clamp(position_multiplier * ods_factor, 0.0, 1.0)
    
    # 确定入场类型
    entry_type = "full" if final_position_multiplier >= 0.8 else "test"
    
    return {
        "should_trade": True,
        "position_size_multiplier": final_position_multiplier,
        "entry_type": entry_type,
        "reason": f"SCORE={final_score:.2f} >= {threshold:.2f}, REGIME={market_regime}, ODS={opportunity_density:.2f}",
    }


__all__ = [
    "detect_market_regime",
    "get_account_stage",
    "decision_policy",
]

