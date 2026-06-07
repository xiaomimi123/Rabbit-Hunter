"""
V4.3 分数计算模块

计算四维度分数：
- Structure Score（结构分数）
- Volatility Score（波动率分数，含硬门槛）
- Sentiment Score（情绪分数，含负奖励）
- Manipulation Score（操控分数）

聚合所有分数，计算最终交易分数。
"""

from typing import Dict, Any, Tuple, Optional


def clamp(value: float, min_val: float, max_val: float) -> float:
    """将值限制在范围内"""
    return max(min_val, min(max_val, value))


def calculate_structure_score(features: Dict[str, Any]) -> float:
    """
    计算结构分数
    
    Args:
        features: 特征字典
    
    Returns:
        structure_score: 结构分数 (0-1)
    """
    phase_score_map = {
        "P1_NO_WHALE": 0.0,
        "P2_ACCUMULATION": 0.6,
        "P3A_PUMP_START": 1.0,
        "P3B_PUMP_LATE": 0.8,
        "P4_DISTRIBUTION": 0.2,
    }
    
    phase = features.get("phase", "P1_NO_WHALE")
    phase_score = phase_score_map.get(phase, 0.0)
    
    # Phase Age 分数：阶段越新（age 越小）得分越高
    phase_age = features.get("phase_age", 0)
    age_score = clamp(1.0 - phase_age / 100.0, 0.0, 1.0)
    
    # HTF Align 分数：多周期同向
    htf_align = features.get("htf_align", 0)
    align_score = float(htf_align)  # 0 or 1
    
    # 平均三个分数
    structure_score = (phase_score + age_score + align_score) / 3.0
    
    return clamp(structure_score, 0.0, 1.0)


def calculate_volatility_score(features: Dict[str, Any]) -> Tuple[float, str]:
    """
    计算波动率和空间分数
    
    ⚠️ 硬门槛：预期收益 < 2% 直接拦截（修复版：基于 ATR 乘数）
    
    Args:
        features: 特征字典
    
    Returns:
        (score, block_reason)
        - 如果被硬约束拦截，返回 (0.0, "BLOCK_REASON")
        - 否则返回 (score, "")
    """
    rr_expect = features.get("range_left", 0.0)  # 预期收益空间（小数，例如 0.02 = 2%）
    price = features.get("price", 1.0)
    atr = features.get("atr", 0.0)
    phase = features.get("phase", "P1_NO_WHALE")
    
    # ✅ 修复 1：使用 ATR 乘数计算预期移动（而不是单点 range_left）
    # P3A 早期可以期待 2.5 倍 ATR 的移动；初始 range_left 可能只有 1.2%
    expected_atr_multiple = {
        "P3A_PUMP_START": 2.5,
        "P3B_PUMP_LATE": 2.0,
        "P2_ACCUMULATION": 1.5,
    }.get(phase, 1.5)
    
    # 计算预期移动（基于 ATR）
    expected_move = atr * expected_atr_multiple if atr > 0 else 0.0
    expected_move_pct = expected_move / price if price > 0 else 0.0
    
    # ⚠️ 修复后的硬门槛：基于 ATR 的预期收益 < 2% 直接拦截
    # 这样可以在启动前不被杀
    if expected_move_pct < 0.02:
        return (0.0, f"LOW_EXPECTED_RETURN_ATR ({expected_move_pct*100:.2f}% < 2%)")
    
    # ATR Expand 分数
    atr_expand = features.get("atr_expand", 0.0)
    atr_expand_score = clamp(atr_expand, 0.0, 1.0)
    
    # ✅ 修复：使用 expected_move_pct 而不是 rr_expect 作为范围评分
    # Range 分数：归一化到 0-1（假设最大为 5%）
    range_score = clamp(expected_move_pct / 0.05, 0.0, 1.0)
    
    # 平均两个分数
    volatility_score = (atr_expand_score + range_score) / 2.0
    
    return (clamp(volatility_score, 0.0, 1.0), "")


def calculate_sentiment_score(features: Dict[str, Any]) -> float:
    """
    计算市场情绪分数（v45：funding 符号修复 — 反向计算）

    v45 修复：旧代码 funding_penalty = clamp(-funding*10, -1, 0) 然后 `- funding_penalty`，
    实际上让正费率（多头过热，理应看空）反而**抬高**了情绪分。修复为对称 signed 信号：
      - funding > 0（多头付费给空头，过热）→ 看空 → 拉低 sentiment
      - funding < 0（空头付费给多头，空头拥挤）→ 看多 → 抬高 sentiment

    Args:
        features: 特征字典（funding 单位：decimal，如 0.0001 = 0.01%）

    Returns:
        sentiment_score: 情绪分数 (0-1)
    """
    # ── funding 信号（signed，方向感知）──────────────────────
    funding = features.get("funding", 0.0)
    # 经验：±0.1%（0.001）映射到 ±1
    funding_signal = clamp(-float(funding) * 10.0, -1.0, 1.0)

    # ── 多空比 ──────────────────────────────────────────────
    ls_ratio = features.get("ls_ratio", 1.0)
    if 1.0 <= ls_ratio <= 2.0:
        ls_score = 1.0
    elif ls_ratio > 2.5:
        ls_score = 0.3  # 过度拥挤，降低分数
    else:
        ls_score = clamp((ls_ratio - 0.5) / 1.5, 0.0, 1.0)

    # ── OI 变化 ─────────────────────────────────────────────
    oi_change = features.get("oi_change", 0.0)
    oi_score = clamp(oi_change / 10.0, 0.0, 1.0)  # 假设最大 OI 变化为 10%

    # ── 综合 ────────────────────────────────────────────────
    # ls/oi 在 [0,1]，funding_signal 在 [-1,1]
    # 取均值后 clamp 回 [0,1]
    sentiment_score = (ls_score + oi_score + funding_signal) / 3.0
    return clamp(sentiment_score, 0.0, 1.0)


def calculate_manipulation_score(features: Dict[str, Any]) -> float:
    """
    计算主力操控信号分数（"扎针直觉"的量化）
    
    Args:
        features: 特征字典
    
    Returns:
        manipulation_score: 操控分数 (0-1)
    """
    wick_score = features.get("lower_wick", 0.0)  # 下影线比例
    liq_score = features.get("liq_cluster", 0.0)  # 爆仓密度
    volume_score = features.get("volume_spike", 0.0)  # 成交量异常
    
    manipulation_score = (wick_score + liq_score + volume_score) / 3.0
    
    return clamp(manipulation_score, 0.0, 1.0)


def aggregate_score(features: Dict[str, Any], weights: Dict[str, float]) -> Dict[str, Any]:
    """
    聚合所有分数，计算最终交易分数
    
    Args:
        features: 特征字典
        weights: 权重字典，包含 structure, volatility, sentiment, manipulation
    
    Returns:
        {
            "final_score": float,        # 最终聚合分数
            "structure_score": float,     # 结构分数（原始值）
            "volatility_score": float,   # 波动率分数（原始值）
            "sentiment_score": float,    # 情绪分数（原始值）
            "manipulation_score": float, # 操控分数（原始值）
            "weights_version": str,      # 权重版本号
            "block_reason": str,         # 如果被拦截，说明原因
        }
    """
    # 计算各维度分数（保留原始值）
    structure_score = calculate_structure_score(features)
    
    # ✅ 修复：即使波动率分数被拦截，也要计算其他维度分数（保持可解释性）
    volatility_score, volatility_block_reason = calculate_volatility_score(features)
    
    sentiment_score = calculate_sentiment_score(features)
    manipulation_score = calculate_manipulation_score(features)
    
    # 加权聚合（即使波动率被拦截，也使用 0.0 参与计算，而不是直接返回 0.0）
    # 这样可以看到"这个币结构分 20，但波动率被拦截，所以总分是 5"
    final_score = (
        structure_score * weights.get("structure", 0.35) +
        volatility_score * weights.get("volatility", 0.25) +  # 如果被拦截，这里是 0.0
        sentiment_score * weights.get("sentiment", 0.25) +
        manipulation_score * weights.get("manipulation", 0.15)
    )
    
    # 如果有拦截原因，记录在 block_reason 中，但不影响分数计算
    block_reason = volatility_block_reason if volatility_block_reason else ""
    
    return {
        "final_score": clamp(final_score, 0.0, 1.0),
        "structure_score": structure_score,
        "volatility_score": volatility_score,  # 可能是 0.0（如果被拦截）
        "sentiment_score": sentiment_score,
        "manipulation_score": manipulation_score,
        "weights_version": weights.get("version", "v4.3.0"),
        "block_reason": block_reason,  # 记录拦截原因，但不影响分数
    }


# v0.5.1 兼容 wrapper：旧代码（v43_kill_queue_manager / v43_anatomy_analyzer /
# v43_entry_validator）import 的是 `calculate_scores(features)`，而本模块实际
# 只导出 `aggregate_score(features, weights)`。整个 review 期间这些 import
# 全部 ImportError，对应 API 路由形同虚设。在此提供一个 thin wrapper：
#   - 自动从 v43_weight_manager 加载当前 weights（DB > config > 默认）
#   - 再调用 aggregate_score 拼出完整 score_result dict
# 旧调用方完全无需改动。
def calculate_scores(features: Dict[str, Any]) -> Dict[str, Any]:
    """Compat shim — equivalent to `aggregate_score(features, load_weights())`.

    Provided so that 4+ pre-existing callers (KillQueueManager / AnatomyAnalyzer
    / EntryValidator …) stop ImportError-ing. Prefer aggregate_score directly
    in new code.
    """
    try:
        # 优先用 scripts/ 裸名（已通过 PYTHONPATH 在容器里就绪）
        from v43_weight_manager import load_weights  # type: ignore[import-not-found]
    except ImportError:
        from scripts.v43_weight_manager import load_weights  # type: ignore[import-not-found]
    return aggregate_score(features, load_weights())


__all__ = [
    "calculate_structure_score",
    "calculate_volatility_score",
    "calculate_sentiment_score",
    "calculate_manipulation_score",
    "aggregate_score",
    "calculate_scores",
]

