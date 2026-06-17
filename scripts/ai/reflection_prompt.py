"""5 问 reflection prompt — 喂给 AI 后强制 JSON 响应。

Prompt 设计原则:
1. 给出完整证据(entry snapshot + 持仓轨迹 + RAG cases AI 当时引用)
2. 强制选 taxonomy 或提新(允许 'NEW:<key>' 前缀)
3. 要求 actionable 答案
4. 跟踪 self-assessment (用于 confidence calibration)
"""
from api.schemas.v5_reflection import PROMPT_VERSION


def build_reflection_prompt(ctx: dict) -> str:
    """ctx fields: see tests/test_reflection_prompt.py::_sample_close_context()"""
    funding_str = (
        f"{ctx.get('funding_z_score'):.2f}"
        if ctx.get("funding_z_score") is not None
        else "N/A (V6 funding feed not active for this trade)"
    )

    fz = ctx.get("funding_z_score")
    fr = ctx.get("funding_rate_at_entry")
    if fz is not None and fr is not None:
        annualized = fr * 365 * 3 * 100
        funding_block = (
            f"\n[ENTRY FUNDING SNAPSHOT]\n"
            f"8h funding rate: {fr*100:+.4f}% (annualized {annualized:+.1f}%)\n"
            f"30d z-score: {fz:+.2f}\n"
        )
    else:
        funding_block = "\n[ENTRY FUNDING SNAPSHOT]\nN/A (no funding data available)\n"

    taxonomy_lines = "\n".join(f"  - {k}" for k in ctx.get("taxonomy_keys", []))

    return f"""You are reviewing a CLOSED trade made by an automated quant bot.
Your task: answer 5 structured questions in JSON. Do NOT confabulate generic
trading advice. Anchor every answer to specific evidence from the snapshot.

[TRADE OVERVIEW]
Paper Trade ID: {ctx['paper_trade_id']}
Symbol: {ctx['symbol']}
Side: {ctx['side']}
Strategy: {ctx.get('strategy_id', 'unknown')}
Entry: {ctx['entry_price']} @ {ctx['entry_time']}
Exit: {ctx['exit_price']} @ {ctx['exit_time']} ({ctx['exit_reason']})
Realized R: {ctx['realized_r']:+.2f}
Holding: {ctx['holding_minutes']} minutes

[ENTRY SNAPSHOT]
RSI 15m: {ctx['entry_rsi_15m']}
RSI 4h:  {ctx.get('entry_rsi_4h', 'N/A')}
MACD hist 15m: {ctx['entry_macd_hist_15m']} (prev: {ctx['entry_macd_hist_prev_15m']})
ATR 15m: {ctx['entry_atr_15m']}
Funding rate z-score: {funding_str}

Rule engine reasoning: {ctx.get('rule_reasoning', 'N/A')}
AI confidence at entry: {ctx['confidence_at_entry']:.2f}
AI reasoning at entry: {ctx.get('ai_reasoning', 'N/A')}
{funding_block}
[RAG CASES AI SAW AT ENTRY]
{ctx.get('rag_cases_text') or '(none — cold start)'}

[DURING-HOLD MARKET PATH]
{ctx.get('during_hold_path') or '(not recorded)'}

[FAILURE TAXONOMY KEYS]
{taxonomy_lines or '  (no taxonomy seeded yet)'}

[YOUR TASK]
Return a single JSON object with exactly these 7 fields. No prose outside JSON.

{{
  "why_entered": "<causal: what specific combination triggered entry. Cite indicators by name + value>",
  "what_was_expected": "<reconstruct from SL/TP/confidence: what was AI's predicted path>",
  "what_actually_happened": "<realized: how price actually moved vs expectation, citing the during-hold path>",
  "failure_mode_key": "<one of the taxonomy keys above, OR 'NEW:<your_proposed_snake_case_key>' if none fits, OR null if WIN>",
  "correction_idea": "<actionable: what rule, if added at entry-time, would have prevented or improved this trade. Be specific enough to translate to SQL/DSL>",
  "self_assessed_prediction_accuracy": <float 0-1: how close was AI's predicted path to reality>,
  "is_in_predicted_failure_mode": <bool: was the failure mode something AI could have predicted at entry given the snapshot>
}}

Constraints:
- Each text field: 10-500 chars.
- Anchor to evidence; do NOT invent indicators not shown above.
- If realized_r > 0.5: this was a WIN — failure_mode_key should be null; correction_idea may still suggest improvements.
- Prompt version: {PROMPT_VERSION}
"""
