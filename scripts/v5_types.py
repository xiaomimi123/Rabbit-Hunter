"""V5 共享数据类型 — 跨模块传值用。

所有数据类都是 frozen=True、无方法(避免逻辑漏到这里);
方法都放对应模块(indicator_engine / strategy / risk_calculator)。
"""
from dataclasses import dataclass
from typing import Literal, Optional

Side = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class EnrichedItem:
    """DeepCollector 输出,Scorer 输入。"""
    symbol: str                            # OKX symbol,e.g. "H/USDT"
    current_price: float
    delta_15m_pct: float                   # 最新 15min K 线涨跌(小数,例如 0.0342)
    volume_24h_usdt: float                 # Scanner 已算过的 24h USDT 成交额
    klines_15m: list                       # [(ts, o, h, l, c, v), ...] 长度 ≥ 26
    klines_4h: list                        # [(ts, o, h, l, c, v), ...] 长度 ≥ 26


@dataclass(frozen=True)
class Indicators:
    """IndicatorEngine 输出。"""
    rsi_15m: float
    macd_15m: float
    macd_signal_15m: float
    macd_hist_15m: float
    macd_hist_prev_15m: float
    rsi_4h: float
    macd_hist_4h: float
    atr_15m: float


@dataclass(frozen=True)
class Decision:
    """V5Strategy 输出。"""
    should_trade: bool
    side: Optional[Side]                   # 不开单时 None
    reasoning: str                         # 给人/AI 看的解释
    block_reason: Optional[str]            # 不开单时填,例如 NOT_RSI_AND_MACD


@dataclass(frozen=True)
class RiskPlan:
    """RiskCalculator 输出。"""
    entry_price: float
    sl_price: float
    tp_price: float
    size_usdt: float
    leverage: int
    expected_rr: float                     # (TP-Entry)/(Entry-SL),正数


@dataclass(frozen=True)
class AIResult:
    """TradingAssistant.decide() 输出。"""
    execute: bool
    sl_multiplier: float                   # 1.0 表示用规则给的 SL,>1 放宽,<1 收紧
    tp_multiplier: float
    size_multiplier: float                 # 0~1.2 范围
    confidence: float                      # 0~1
    reasoning: str
    # error_kind: 让 scorer 显式区分 AI 失败类型,不靠 reasoning 字符串前缀匹配。
    #   "ok"          — execute 决策正常 (无论 True/False)
    #   "infra"       — AI 调用超时/异常/未初始化等基建错误 (SHADOW 可 pass-through)
    #   "rule"        — failure_taxonomy 命中等规则拒 (任何模式都拒)
    #   "fail_closed" — LIVE + ai_fail_open=false 的安全兜底
    error_kind: str = "ok"
