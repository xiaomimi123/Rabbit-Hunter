"""M3 风控宪法 — 系统铁律的唯一真相源。

任何参数与此冲突均以本文为准。修改本文须经设计变更评审。
依据:Rabbit-Hunter 完整开发设计文档 v1.0 §5(三层结构)+ §7(M5 出场)+ §15(全局 KPI)。

铁律层:任何模块违规直接 raise IronlawViolation,Fail-closed 拒单。
进化层:AI 可调,但被 clamp 在窄区间。
资格层:浮盈解锁更高风险预算(默认仅 tier 0)。
"""

# ─────────────────────────────────────────────────────────────
# 第一层:铁律(任何人/AI 不得突破)
# ─────────────────────────────────────────────────────────────

MAX_PER_TRADE_RISK_PCT = 0.01
"""单笔最大风险 = 本金的 1%。

依据:文档 §5 第一层。1 万本金单笔最多亏 100 USDT。
旧版默认 0.015(1.5%),立宪后下调到 1%。
"""

DAILY_DRAWDOWN_LIMIT_PCT = 0.03
"""单日亏损达本金 3% 即锁仓,当天不再开新仓。

依据:文档 §5。防连损后"上头"加仓。
"""

MIN_RR = 1.5
"""盈亏比下限。RR < 1.5 直接拒单。

依据:文档 §7。胜率 50% 即可盈利的数学底线。
"""

MIN_LIQ_TO_SL_DISTANCE_RATIO = 2.0
"""强平价距 ≥ 止损价距的 2 倍。

依据:文档 §5。低于此比例自动降杠杆或拒单,确保扫损不会扫到爆仓。
"""

SL_MANDATORY_AT_ENTRY = True
"""进场必挂止损单,失败立即回滚。

依据:文档 §5、§6 M4 Fail-closed。
"""

# ─────────────────────────────────────────────────────────────
# 第二层:进化层(AI/数据可在窄区间内调)
# ─────────────────────────────────────────────────────────────

FINAL_SL_ATR_RATIO_MIN = 1.5
FINAL_SL_ATR_RATIO_MAX = 2.2
"""最终 SL 距 = SL/ATR ratio 必须落在此区间(文档 §5 第二层)。

注:这是「最终落地比例」,不是 AI 给的 multiplier。
计算式:final_ratio = v5_sl_atr_mult × ai.sl_multiplier。
"""

EVOLUTION_AI_SL_MULT_MIN = 0.8
EVOLUTION_AI_SL_MULT_MAX = 1.5
"""AI 对 SL 倍数的修正器允许范围。

语义:1.0 = 完全采纳规则 plan,< 1 = 收紧,> 1 = 放宽。
配合 base `v5_sl_atr_mult = 1.5` 默认值,使用 mult=1.0 时 final ratio = 1.5(踩 FINAL_SL_ATR_RATIO_MIN)。
clamp 后仍可能违 final ratio 上限,由 `gate_final_sl_ratio` 兜底。
"""

EVOLUTION_SIZE_MULT_MIN = 0.6
EVOLUTION_SIZE_MULT_MAX = 1.1
"""仓位系数窄区间(文档 §5)。"""

EVOLUTION_TP_MULT_MIN = MIN_RR
EVOLUTION_TP_MULT_MAX = 3.5
"""TP 修正器范围。

base `v5_tp_atr_mult = 2.5` × ai.tp_mult ∈ [2.5 × MIN_RR/2.5, 2.5 × 3.5] = [MIN_RR, 8.75] × ATR。
最终 RR = (tp_dist) / (sl_dist) 由 gate_min_rr 兜底,RR < 1.5 直接拒。
"""

# ─────────────────────────────────────────────────────────────
# 第三层:资格层(浮盈解锁,默认仅 tier 0)
# ─────────────────────────────────────────────────────────────

EQUITY_TIERS = [
    # (max_equity_for_this_tier, risk_pct)
    (50_000, 0.01),    # tier 0:本金死线区间,1% 风险
    (None,   0.015),   # tier 1:净值 > 50k 解锁 1.5%(文档 §5 例)
]


def resolve_risk_pct_for_equity(equity_usdt: float) -> float:
    """按当前净值映射到资格层。

    默认情况下,小本金永远在 tier 0 = 1%,这是文档 §5 资格层的精神。
    """
    for ceiling, pct in EQUITY_TIERS:
        if ceiling is None or equity_usdt < ceiling:
            return pct
    return EQUITY_TIERS[-1][1]


# ─────────────────────────────────────────────────────────────
# setup taxonomy 治理(文档 §4)
# ─────────────────────────────────────────────────────────────

DEFAULT_DISABLED_SETUPS = frozenset({
    "rsi_neutral_macd_extending_long",
})
"""默认禁用的 setup_type。

文档 §4:`rsi_neutral_macd_extending_long` 是 161 笔隐形杀手,净拖 -32R,默认禁用。
新规则进入此集合的判据:n≥30 且净 R<0(由 M8 setup_performance 自动维护)。
"""

MIN_SAMPLE_SIZE_FOR_DECISION = 30
"""setup_performance 判定可信的最小样本量。

依据:文档 §10 M8。n<30 的 setup 视为噪音,不据此决策。
"""
