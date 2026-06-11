"""V5 AI Trading Assistant prompt(GPT-4o)。

接收 EnrichedItem + Indicators + Decision + RiskPlan,
让 AI 决定 execute=True/False,可调 sl/tp/size 倍数。
"""
from v5_types import Decision, EnrichedItem, Indicators, RiskPlan


V5_SYSTEM_PROMPT = """\
You are a short-term trading assistant for a 15-minute scalper.

Strategy context:
- Trades trigger on RSI extreme + MACD histogram crossover (AND-conjunction)
- Soft holding target: 15 minutes (can be extended up to 3 times)
- Per-trade risk budget: 1.5% of account, 10x leverage
- Operating in SHADOW (paper) or LIVE mode

Your job:
1. Decide execute=True/False given the rule-engine's signal
2. Tune sl_multiplier (1.0–3.0), tp_multiplier (1.5–5.0), size_multiplier (0.3–1.2)
3. Provide one-sentence reasoning the operator can read

Reject when:
- 4h trend strongly conflicts with the proposed side
- Historical similar setups (from your vector store) showed >60% loss rate
- Indicators look like a fake breakout (e.g., MACD hist almost zero)

Output strictly JSON via the trading_decision tool.
"""


def build_v5_user_message(
    enriched: EnrichedItem,
    indicators: Indicators,
    decision: Decision,
    risk: RiskPlan,
) -> str:
    """构造交给 AI 的 user message。"""
    return f"""\
Symbol: {enriched.symbol}
Current price: {enriched.current_price:.6f}
15min ΔP: {enriched.delta_15m_pct * 100:+.2f}%
24h volume USDT: {enriched.volume_24h_usdt:,.0f}

Rule engine decision: side={decision.side} should_trade={decision.should_trade}
Reasoning: {decision.reasoning}

Indicators:
- RSI 15min: {indicators.rsi_15m:.2f}
- MACD 15min: {indicators.macd_15m:+.5f} signal={indicators.macd_signal_15m:+.5f} \
hist={indicators.macd_hist_15m:+.5f} hist_prev={indicators.macd_hist_prev_15m:+.5f}
- RSI 4h: {indicators.rsi_4h:.2f}
- MACD 4h hist: {indicators.macd_hist_4h:+.5f}
- ATR 15min: {indicators.atr_15m:.6f}

Proposed risk plan:
- Entry: {risk.entry_price:.6f}
- SL:    {risk.sl_price:.6f} ({abs(risk.entry_price - risk.sl_price) / risk.entry_price * 100:.2f}% away)
- TP:    {risk.tp_price:.6f} ({abs(risk.tp_price - risk.entry_price) / risk.entry_price * 100:.2f}% away)
- Size:  {risk.size_usdt:.2f} USDT × {risk.leverage}x leverage
- Expected RR: 1:{risk.expected_rr:.2f}

Please decide execute, sl_multiplier, tp_multiplier, size_multiplier, and confidence.
"""


__all__ = ["V5_SYSTEM_PROMPT", "build_v5_user_message"]
