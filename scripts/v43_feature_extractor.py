"""
V4.3 特征提取模块

提取所有交易特征，统一管理所有指标。
不删除任何旧指标，只集中管理。

特征分类：
- Structure: phase, phase_age, htf_align
- Volatility: atr, atr_expand, range_left
- Sentiment: funding, ls_ratio, oi_change
- Manipulation: lower_wick, liq_cluster, volume_spike
"""

from __future__ import annotations
from typing import Optional, Dict, Any

# 导入现有模块
try:
    from whale_detector import (
        detect_phase,
        PHASE_P1,
        PHASE_P2,
        PHASE_P3A,
        PHASE_P3B,
        PHASE_P4,
        is_oi_second_spike_confirmed,
    )
    from v41_structure_analyzer import calculate_structure_gap
    from v41_context_gate import check_context_gate
    from technical_indicators import get_all_indicators
except ImportError as e:
    print(f"[WARNING] V4.3 特征提取模块导入失败: {e}")
    # 创建占位常量和函数
    PHASE_P1 = "P1_NO_WHALE"
    PHASE_P2 = "P2_ACCUMULATION"
    PHASE_P3A = "P3A_PUMP_START"
    PHASE_P3B = "P3B_PUMP_LATE"
    PHASE_P4 = "P4_DISTRIBUTION"
    
    def detect_phase(*args, **kwargs):
        return PHASE_P1
    def is_oi_second_spike_confirmed(*args, **kwargs):
        return False
    def calculate_structure_gap(*args, **kwargs):
        return 0.05, "VIRTUAL"
    def check_context_gate(*args, **kwargs):
        return True, "OK"
    def get_all_indicators(*args, **kwargs):
        return {}


def extract_features(
    symbol: str,
    price: float,
    funding_rate: Optional[float],
    long_short_ratio: Optional[float],
    oi_value: Optional[float],
    oi_change_1h: Optional[float],
    price_change_1h: Optional[float],
    cvd_data: Optional[Dict[str, Any]] = None,
    oi_series: Optional[list] = None,
    prices: Optional[list[float]] = None,
    highs_1h: Optional[list[float]] = None,
    closes_1h: Optional[list[float]] = None,
    phase_4h: Optional[str] = None,
    phase_1h: Optional[str] = None,
    phase_age_candles: Optional[int] = None,
    atr_value: Optional[float] = None,
    ohlcv_15m: Optional[list[dict]] = None,
) -> Dict[str, Any]:
    """
    提取所有交易特征（不删除任何旧指标，只集中管理）
    
    Args:
        symbol: 交易对符号
        price: 当前价格
        funding_rate: 资金费率
        long_short_ratio: 多空比
        oi_value: 持仓量
        oi_change_1h: OI 1小时变化（百分比）
        price_change_1h: 价格 1小时变化（百分比）
        cvd_data: CVD 数据（包含 cvd_15m, cvd_1h 等）
        oi_series: OI 序列（用于 P3a 验证）
        prices: 历史价格列表
        highs_1h: 1H K 线最高价列表
        closes_1h: 1H K 线收盘价列表
        phase_4h: 4H 周期阶段
        phase_1h: 1H 周期阶段
        phase_age_candles: 阶段年龄（K 线根数）
        atr_value: ATR 值
        ohlcv_15m: 15m K 线数据
    
    Returns:
        features: 特征字典
    """
    features: Dict[str, Any] = {}
    
    # ========== 基础数据（前端需要） ==========
    # 保存价格和 ATR，供前端显示使用
    features["current_price"] = price
    features["price"] = price  # 兼容字段
    features["atr"] = atr_value if atr_value is not None else 0.0
    
    # ========== Structure 特征 ==========
    
    # 1. Phase（市场阶段）
    phase = PHASE_P1  # 默认值
    if price_change_1h is not None:
        try:
            # 性能优化：复用 CVDAnalyzer 实例（如果可用）
            # 注意：为了保持兼容性，这里仍然创建新实例
            # 如需性能优化，请使用 v43_feature_extractor_optimized.py
            from cvd_analyzer import CVDAnalyzer
            analyzer = CVDAnalyzer(None)
            cvd_intent = "NEUTRAL"
            cvd_1h = None
            
            if cvd_data:
                cvd_1h = float(cvd_data.get("cvd_1h", 0.0) or 0.0)
                try:
                    cvd_intent = analyzer.analyze_cvd_intent(
                        float(price_change_1h) / 100.0, 
                        cvd_data
                    )
                except Exception:
                    cvd_intent = "NEUTRAL"
            
            phase = detect_phase(
                price_change_1h=price_change_1h,
                oi_change_1h=oi_change_1h,
                cvd_intent=cvd_intent,
                cvd_1h=cvd_1h,
                whale_cvd_1h=float((cvd_data or {}).get("whale_cvd_1h", 0.0) or 0.0),
            )
            
            # P3a 验证：必须伴随 OI 二次放量
            if oi_series is not None:
                oi_second_spike_ok = is_oi_second_spike_confirmed(oi_series)
                if phase == PHASE_P3A and not oi_second_spike_ok:
                    phase = PHASE_P2
        except Exception as e:
            print(f"[WARNING] Phase 检测失败: {e}")
            phase = PHASE_P1
    
    features["phase"] = phase
    
    # 2. Phase Age（阶段年龄）
    features["phase_age"] = phase_age_candles if phase_age_candles is not None else 0
    
    # 3. HTF Align（多周期同向）
    # 如果 4H 和 1H 阶段都是 P2/P3A/P3B，且方向一致，则为 1，否则为 0
    htf_align = 0
    if phase_4h and phase_1h:
        # 判断是否同向（都是做多阶段）
        bullish_phases = [PHASE_P2, PHASE_P3A, PHASE_P3B]
        if phase_4h in bullish_phases and phase_1h in bullish_phases:
            htf_align = 1
    features["htf_align"] = htf_align
    
    # ========== Volatility 特征 ==========
    
    # 1. ATR
    features["atr"] = atr_value if atr_value is not None else 0.0
    
    # 2. ATR Expand（ATR 是否扩张）
    # 计算 ATR 变化率（需要历史 ATR 数据）
    atr_expand = 0.0
    if atr_value is not None and prices and len(prices) >= 20:
        try:
            # 使用技术指标计算 ATR
            indicators = get_all_indicators(prices)
            if "atr" in indicators:
                current_atr = indicators["atr"]
                # 简化：如果当前 ATR > 价格 * 0.02，认为扩张
                atr_expand = min(1.0, (current_atr / price) / 0.02) if current_atr else 0.0
        except Exception:
            atr_expand = 0.0
    features["atr_expand"] = atr_expand
    
    # 3. Range Left（上方空间 %）
    # ✅ 修复：如果上方没有阻力位（新高币），给一个基于 ATR 的合理默认值
    range_left = 0.0
    if highs_1h is not None or closes_1h is not None:
        try:
            structure_gap, method = calculate_structure_gap(
                current_price=price,
                highs_1h=highs_1h,
                closes_1h=closes_1h,
                use_bollinger=True
            )
            range_left = max(0.0, structure_gap)
        except Exception:
            range_left = 0.0

    # ✅ ATR-based fallback —— 无论 K 线数据是否拿到、structure_gap 算
    # 出来是不是 0,只要 range_left 仍是 0 且 ATR 有效,就用 5×ATR/price
    # 兜底到 30%~50% 区间。之前 K 线两端都 None 时这道兜底没触发,
    # range_left 死定为 0,导致 LOW_EXPECTED_RETURN 拦截整张 P3 信号面板。
    if range_left == 0.0 and atr_value is not None and atr_value > 0 and price > 0:
        atr_based_range = (atr_value * 5.0) / price
        range_left = max(0.30, min(0.50, atr_based_range))
    features["range_left"] = range_left
    
    # ========== Sentiment 特征 ==========
    
    # 1. Funding Rate（资金费率）
    features["funding"] = funding_rate if funding_rate is not None else 0.0
    
    # 2. Long Short Ratio（多空比）
    features["ls_ratio"] = long_short_ratio if long_short_ratio is not None else 1.0
    
    # 3. OI Change（OI 变化）
    features["oi_change"] = oi_change_1h if oi_change_1h is not None else 0.0
    
    # ========== Manipulation 特征 ==========
    
    # 1. Lower Wick Ratio（下影线比例）
    lower_wick_ratio = 0.0
    if ohlcv_15m and len(ohlcv_15m) > 0:
        try:
            # 使用最新的 K 线
            latest = ohlcv_15m[-1]
            open_price = float(latest.get("open", price))
            high_price = float(latest.get("high", price))
            low_price = float(latest.get("low", price))
            close_price = float(latest.get("close", price))
            
            # 计算下影线比例
            body = abs(close_price - open_price)
            lower_wick = min(open_price, close_price) - low_price
            total_range = high_price - low_price
            
            if total_range > 0:
                lower_wick_ratio = lower_wick / total_range
        except Exception:
            lower_wick_ratio = 0.0
    features["lower_wick"] = lower_wick_ratio
    
    # 2. Liquidation Cluster（爆仓密度）
    # 简化：使用 OI 变化和价格变化的组合来近似
    liq_cluster = 0.0
    if oi_change_1h is not None and price_change_1h is not None:
        # OI 大幅下降 + 价格快速变化 = 可能爆仓
        if oi_change_1h < -5.0 and abs(price_change_1h) > 3.0:
            liq_cluster = min(1.0, abs(oi_change_1h) / 10.0)
    features["liq_cluster"] = liq_cluster
    
    # 3. Volume Spike（成交量异常）
    volume_zscore = 0.0
    if ohlcv_15m and len(ohlcv_15m) >= 20:
        try:
            # 计算最近 20 根 K 线的成交量
            volumes = [float(k.get("volume", 0)) for k in ohlcv_15m[-20:]]
            if volumes:
                mean_vol = sum(volumes) / len(volumes)
                std_vol = (sum((v - mean_vol) ** 2 for v in volumes) / len(volumes)) ** 0.5
                if std_vol > 0:
                    latest_vol = volumes[-1]
                    volume_zscore = min(1.0, (latest_vol - mean_vol) / (std_vol * 2))
        except Exception:
            volume_zscore = 0.0
    features["volume_spike"] = volume_zscore
    
    return features


__all__ = ["extract_features"]

