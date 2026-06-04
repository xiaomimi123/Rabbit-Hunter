"""
Whale Detector (Rabbit Hunter 4.0)

目标：
- 根据价格/持仓量/OI/CVD 意图推断 P 阶段（P1-P4）
- 根据白皮书三大猎杀场景输出 Kill Zone 信号：
  - SQUEEZE（逼空）
  - ACCUMULATION（底部吸筹）
  - SHAKEOUT（假摔洗盘）

注意：
- 这里返回的是“状态/场景”，不直接等同于“立即交易”。
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple, Union


PHASE_P1 = "P1_NO_WHALE"
PHASE_P2 = "P2_ACCUMULATION"
PHASE_P3A = "P3A_PUMP_START"
PHASE_P3B = "P3B_PUMP_LATE"
PHASE_P4 = "P4_DISTRIBUTION"

KZ_NONE = "NONE"
KZ_SQUEEZE = "SQUEEZE"
KZ_ACCUMULATION = "ACCUMULATION"
KZ_SHAKEOUT = "SHAKEOUT"
KZ_TOMBSTONE = "TOMBSTONE"  # V4.2 新增：墓碑线（空头信号）
KZ_WHALE_EXIT_PUMP = "WHALE_EXIT_PUMP"  # V4.2 新增：庄家出逃（空头信号）


def detect_phase(
    *,
    price_change_1h: Optional[float],
    oi_change_1h: Optional[float],
    cvd_intent: str,
    cvd_1h: Optional[float] = None,
    whale_cvd_1h: Optional[float] = None,
) -> str:
    """
    P 阶段判定（工程化近似实现）

    输入约定：
    - price_change_1h / oi_change_1h 为“百分比”（例如 2.5 表示 +2.5%）
    - cvd_intent 来自 CVDAnalyzer.analyze_cvd_intent
    """
    p = float(price_change_1h) if price_change_1h is not None else 0.0
    oi = float(oi_change_1h) if oi_change_1h is not None else 0.0
    cvd1h = float(cvd_1h) if cvd_1h is not None else 0.0
    w1h = float(whale_cvd_1h) if whale_cvd_1h is not None else 0.0

    # P4：派发/出货（V4.2 重新定义：必须满足背离）
    # 条件：Price Up + OI Down + CVD Down（庄家跑了）
    # 价格还在高位（或试图创新高）+ OI 显著下降 + CVD 断崖式下跌
    price_up = p > 0.0  # 价格还在高位或试图创新高
    oi_down = oi < -2.0  # OI 显著下降（Whale Closing Longs）
    cvd_down = (cvd_intent == "DISTRIBUTION") or (cvd1h < 0 and cvd1h < -abs(w1h) * 0.5)  # CVD 断崖式下跌
    
    if price_up and oi_down and cvd_down:
        return PHASE_P4

    # P3b：拉盘后期（分歧加剧，OI 开始回落/资金开始撤）
    if p > 1.0 and (oi < -1.0 or cvd_intent == "DISTRIBUTION"):
        return PHASE_P3B

    # P3a：拉盘前期（燃料充足）：价格上行 + OI 增加 + CVD 认可
    if p > 1.0 and oi > 2.0 and cvd_intent in ("PUMP_CONFIRMED", "ACCUMULATION") and (cvd1h > 0 or w1h > 0):
        return PHASE_P3A

    # P2：吸筹：价格横盘 + CVD/whaleCVD 显著偏买
    if abs(p) < 0.5 and cvd_intent == "ACCUMULATION":
        return PHASE_P2

    return PHASE_P1


def is_oi_second_spike_confirmed(
    oi_series: Optional[Sequence[Union[float, Tuple[float, float]]]],
    *,
    min_points: int = 5,
    dip_ratio: float = 0.01,
    second_spike_ratio: float = 0.015,
) -> bool:
    """
    OI 二次放量验证（工程化近似）

    输入：
    - oi_series: [oi, oi, ...] 或 [(ts, oi), ...]

    判定模式（简化）：
    - 先出现一段明显上升（第一波）
    - 中间有一次回撤（dip）
    - 再出现第二波上升并突破第一波高点（second spike）
    """
    if not oi_series:
        return False

    values: list[float] = []
    for x in oi_series:
        if isinstance(x, tuple) and len(x) >= 2:
            values.append(float(x[1]))
        else:
            values.append(float(x))

    # 去除无效
    values = [v for v in values if v > 0]
    if len(values) < min_points:
        return False

    # 只看最近窗口
    window = values[-min_points:]
    first_high = max(window[:-2])
    last = window[-1]

    # 必须有回撤：从 first_high 到某个点回撤 dip_ratio
    dipped = any(v <= first_high * (1 - dip_ratio) for v in window)
    if not dipped:
        return False

    # 二次放量：末尾突破 first_high，并且相对 first_high 增幅达到 second_spike_ratio
    if last >= first_high * (1 + second_spike_ratio):
        return True

    return False


def check_kill_zones(
    *,
    funding_rate: float,
    oi_change_1h: Optional[float],
    price_breakout: bool,
    cvd_intent: str,
    phase: Optional[str] = None,
    flash_crash: bool = False,
    oi_stable: bool = False,
) -> str:
    """
    三大猎杀场景识别（返回单一最强信号）
    """
    oi = float(oi_change_1h) if oi_change_1h is not None else 0.0

    # 1) 逼空暴利：Funding 极负 + OI 增 + 有效突破
    if funding_rate < -0.0005 and oi > 0 and price_breakout:
        return KZ_SQUEEZE

    # 2) 底部吸筹：价格横盘 + CVD 显示吸筹（通常对应 P2）
    if cvd_intent == "ACCUMULATION" and (phase in (None, PHASE_P2, PHASE_P3A)):
        return KZ_ACCUMULATION

    # 3) 假摔洗盘：闪崩但 OI 不显著下降（且只在 P2 后期 / P3a 生效）
    if flash_crash and oi_stable and phase in (PHASE_P2, PHASE_P3A):
        return KZ_SHAKEOUT

    return KZ_NONE


def compute_exit_clarity_score(
    *,
    phase: str,
    kill_zone: str,
    funding_rate: float,
    oi_change_1h: Optional[float],
    price_change_1h: Optional[float],
    cvd_intent: str,
    oi_second_spike_confirmed: bool = False,
) -> int:
    """
    退出条件清晰度评分（0-100）

    核心思想（白皮书 4.0）：
    - 退出条件必须比入场更清晰；越接近“可量化触发条件”，分越高。
    """
    p = float(price_change_1h) if price_change_1h is not None else 0.0
    oi = float(oi_change_1h) if oi_change_1h is not None else 0.0

    # 基础分：阶段越靠近 P3a，越可能具备“快进快出”的明确退出条件
    base_map = {
        PHASE_P1: 0,
        PHASE_P2: 45,
        PHASE_P3A: 70,
        PHASE_P3B: 30,
        PHASE_P4: 10,
    }
    score = int(base_map.get(phase, 0))

    # Kill Zone 加成：逼空/洗盘通常更有明确退出触发
    if kill_zone == KZ_SQUEEZE:
        score += 15
    elif kill_zone == KZ_SHAKEOUT:
        score += 10
    elif kill_zone == KZ_ACCUMULATION:
        score += 5

    # Funding 条件越“极端”越可作为退出触发（逼空：费率回正就是跑点）
    if kill_zone == KZ_SQUEEZE and funding_rate < -0.0005:
        score += 10

    # OI 趋势：P3a 需要燃料（OI 正增长）；若下降说明退出更模糊/更危险
    if phase == PHASE_P3A:
        if oi > 2.0:
            score += 8
        elif oi < 0:
            score -= 12

    # 强制验证：P3a 必须伴随 OI 二次放量
    if phase == PHASE_P3A and not oi_second_spike_confirmed:
        score -= 18
    if phase == PHASE_P3A and oi_second_spike_confirmed:
        score += 6

    # 价格趋势：突破越明显，退出目标/止损点越容易定义
    if p > 2.0:
        score += 5
    elif p < -1.0:
        score -= 8

    # CVD 对齐：派发信号会显著降低“安全退出优势”
    if cvd_intent == "PUMP_CONFIRMED" and phase == PHASE_P3A:
        score += 5
    if cvd_intent == "DISTRIBUTION":
        score -= 15

    return max(0, min(100, int(score)))


def analyze_structure_level_1(
    ohlcv_1h: list[dict] | None,
    ohlcv_4h: list[dict] | None,
    *,
    min_1h_bars: int = 2,
    min_4h_bars: int = 6,
) -> tuple[str, str]:
    """
    Level 1 结构层分析：判断大跌后的尸体是否"复活"
    
    输入：
    - ohlcv_1h: [{"open": float, "high": float, "low": float, "close": float, "volume": float}, ...]
    - ohlcv_4h: 同上，4H 周期
    
    返回: (phase, reason)
    - phase: "P4_CRASHING" | "P2_POTENTIAL" | "P3A_START" | "UNKNOWN"
    - reason: 人类可读的原因
    
    核心逻辑（V4.2 分层漏斗）：
    - A. 排除逻辑：正在崩盘 (Falling Knife) -> P4_CRASHING
    - B. 观察逻辑：潜在 P2 (尸体凉透，开始吸筹) -> P2_POTENTIAL
    - C. 进场逻辑：P3A 启动 (诈尸) -> P3A_START
    """
    if not ohlcv_1h or len(ohlcv_1h) < min_1h_bars:
        return "UNKNOWN", "1H 数据不足"
    if not ohlcv_4h or len(ohlcv_4h) < min_4h_bars:
        return "UNKNOWN", "4H 数据不足"
    
    # 获取最近的数据
    last_1h = ohlcv_1h[-1]
    last_4h = ohlcv_4h[-1]
    
    # 计算 1h 内的振幅 (High - Low) / Open
    open_1h = float(last_1h.get("open", 0))
    high_1h = float(last_1h.get("high", 0))
    low_1h = float(last_1h.get("low", 0))
    close_1h = float(last_1h.get("close", 0))
    vol_1h = float(last_1h.get("volume", 0))
    
    if open_1h == 0:
        return "UNKNOWN", "1H 开盘价为 0"
    
    volatility_1h = (high_1h - low_1h) / open_1h
    
    # 计算 4H 成交量变化 (当前4h量 vs 过去24h平均量)
    volumes_4h = [float(b.get("volume", 0)) for b in ohlcv_4h]
    if len(volumes_4h) >= 6:
        avg_vol_24h = sum(volumes_4h[-6:]) / 6  # 过去 6 根 4H = 24 小时
        vol_4h = float(last_4h.get("volume", 0))
        vol_ratio = vol_4h / avg_vol_24h if avg_vol_24h > 0 else 1.0
    else:
        vol_ratio = 1.0
    
    # 计算 4H 实体大小（判断是否十字星）
    open_4h = float(last_4h.get("open", 0))
    close_4h = float(last_4h.get("close", 0))
    if open_4h == 0:
        return "UNKNOWN", "4H 开盘价为 0"
    
    body_ratio_4h = abs(close_4h - open_4h) / open_4h
    
    # 计算 1H 涨跌幅
    price_change_1h_pct = ((close_1h - open_1h) / open_1h) * 100
    
    # --- 判定逻辑 ---
    
    # A. 排除逻辑：正在崩盘 (Falling Knife)
    # 1h 跌幅巨大（>5%），且量还在放大（vol_ratio > 2.0）
    if price_change_1h_pct < -5.0 and vol_ratio > 2.0:
        return "P4_CRASHING", f"正在砸盘（1H跌{price_change_1h_pct:.1f}%，量能{vol_ratio:.1f}x），接飞刀必死"
    
    # B. 观察逻辑：潜在 P2 (尸体凉透，开始吸筹)
    # 4h 跌不动了（十字星，body < 1%） + 1h 波动率极低（<1.5%） + 量缩（vol_ratio < 1.5）
    if body_ratio_4h < 0.01 and volatility_1h < 0.015 and vol_ratio < 1.5:
        return "P2_POTENTIAL", f"波动率收缩（4H实体{body_ratio_4h*100:.2f}%，1H振幅{volatility_1h*100:.2f}%），进入观察池"
    
    # C. 进场逻辑：P3A 启动 (诈尸)
    # 之前是 P2 (低波) + 突然一根大阳线突破（1H涨幅>3%） + 量能配合（vol_ratio > 1.2）
    if volatility_1h > 0.03 and price_change_1h_pct > 3.0 and vol_ratio > 1.2:
        return "P3A_START", f"放量启动（1H涨{price_change_1h_pct:.1f}%，振幅{volatility_1h*100:.2f}%，量能{vol_ratio:.1f}x），准备猎杀"
    
    return "UNKNOWN", "结构不清晰"


def detect_bull_trap(
    ohlcv_15m: list[dict],
    oi_change_15m: Optional[float] = None,
    *,
    min_wick_ratio: float = 0.6,
    min_oi_drop: float = -0.05,
) -> Tuple[bool, Optional[str], dict]:
    """
    识别 P4 阶段的诱多墓碑线（做空信号）
    
    V4.2 空头增补规范：
    - 形态：极长的上影线（上影线长度 > 60%）
    - 位置：发生在 P3B 末端或 P4 阶段
    - 行为：价格快速冲高（诱多），然后迅速回落，收盘价低于开盘价（实体翻绿）
    - 确认：伴随着 OI 的锐减（庄家借着拉高平了大量多单）
    
    Args:
        ohlcv_15m: 15m K 线数据列表（从旧到新），至少需要 1 根
        oi_change_15m: 15m OI 变化百分比（例如 -5.0 表示 -5%），用于确认庄家出逃
        min_wick_ratio: 最小上影线占比，默认 0.6 (60%)
        min_oi_drop: 最小 OI 下降百分比，默认 -0.05 (-5%)
    
    Returns:
        (is_tombstone, signal_type, details)
        - is_tombstone: 是否检测到墓碑线
        - signal_type: "WHALE_EXIT_PUMP" 或 None
        - details: 详细信息字典
    """
    if not ohlcv_15m or len(ohlcv_15m) < 1:
        return False, None, {"reason": "数据不足"}
    
    # 获取最新一根 K 线
    current = ohlcv_15m[-1]
    open_price = float(current.get("open", 0))
    high_price = float(current.get("high", 0))
    low_price = float(current.get("low", 0))
    close_price = float(current.get("close", 0))
    
    if open_price == 0 or high_price == 0 or low_price == 0 or close_price == 0:
        return False, None, {"reason": "K 线数据无效"}
    
    # 1. 检查墓碑形态
    # 上影线长度 = high - max(open, close)
    body_top = max(open_price, close_price)
    upper_wick = high_price - body_top
    total_range = high_price - low_price
    
    if total_range == 0:
        return False, None, {"reason": "K 线范围无效"}
    
    wick_ratio = upper_wick / total_range
    
    # 2. 检查实体是否翻绿（收盘价 < 开盘价）
    is_bearish_body = close_price < open_price
    
    # 3. 检查 OI 下降（庄家出逃证据）
    oi_drop_confirmed = False
    if oi_change_15m is not None:
        oi_drop_confirmed = float(oi_change_15m) < min_oi_drop
    
    # 综合判断
    is_tombstone = False
    signal_type = None
    reason = ""
    
    if wick_ratio < min_wick_ratio:
        reason = f"上影线占比不足（{wick_ratio*100:.1f}% < {min_wick_ratio*100:.0f}%）"
    elif not is_bearish_body:
        reason = "实体未翻绿（收盘价未低于开盘价）"
    elif not oi_drop_confirmed:
        reason = f"OI 下降不足（{oi_change_15m*100:.1f}% >= {min_oi_drop*100:.0f}%）"
    else:
        # 所有条件满足
        is_tombstone = True
        signal_type = KZ_WHALE_EXIT_PUMP
        reason = f"墓碑线确认（上影线{wick_ratio*100:.1f}%，OI下降{oi_change_15m*100:.1f}%，庄家出逃）"
    
    return is_tombstone, signal_type, {
        "wick_ratio": wick_ratio,
        "is_bearish_body": is_bearish_body,
        "oi_change_15m": oi_change_15m,
        "oi_drop_confirmed": oi_drop_confirmed,
        "reason": reason
    }


__all__ = [
    "detect_phase",
    "check_kill_zones",
    "is_oi_second_spike_confirmed",
    "compute_exit_clarity_score",
    "analyze_structure_level_1",
    "detect_bull_trap",
    "PHASE_P1",
    "PHASE_P2",
    "PHASE_P3A",
    "PHASE_P3B",
    "PHASE_P4",
    "KZ_NONE",
    "KZ_SQUEEZE",
    "KZ_ACCUMULATION",
    "KZ_SHAKEOUT",
    "KZ_TOMBSTONE",
    "KZ_WHALE_EXIT_PUMP",
]


