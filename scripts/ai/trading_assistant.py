"""OpenAI Assistants API trading decision engine.

Flow per signal:
  1. Build structured message with current market data
  2. Create a new Thread (stateless per signal)
  3. Run the Assistant — it retrieves similar trades from Vector Store automatically
  4. Parse the function call: execute_trade() or skip_trade()
  5. Apply guardrails to clamp parameters
  6. Return AIDecision to caller

The Vector Store provides the "memory" — historical trades uploaded periodically
by memory_uploader.py act as few-shot examples the Assistant can retrieve.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import openai

from .guardrails import GuardrailRejection, apply_guardrails
from .prompt import SYSTEM_PROMPT


def _fail_open() -> bool:
    """Whether to fall back to execute=True when the AI layer is unavailable.

    Defaults to False (fail-closed): if the second-opinion AI cannot answer,
    we skip the trade rather than rubber-stamp it. Set AI_FAIL_OPEN=true to
    restore the legacy "approve on failure" behavior.
    """
    return os.getenv("AI_FAIL_OPEN", "false").lower() in ("1", "true")

# ---------------------------------------------------------------------------
# Function tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_trade",
            "description": "Execute this trade signal with the specified risk parameters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tp_multiplier": {
                        "type": "number",
                        "description": "Take profit ATR multiplier (2.0 – 6.0). TP = entry ± tp_multiplier × ATR",
                    },
                    "sl_multiplier": {
                        "type": "number",
                        "description": "Stop loss ATR multiplier (1.2 – 3.0). SL = entry ∓ sl_multiplier × ATR",
                    },
                    "size_multiplier": {
                        "type": "number",
                        "description": "Position size multiplier (0.5 – 1.2). Scales the base risk-per-trade.",
                    },
                    "confidence": {
                        "type": "integer",
                        "description": "Confidence level 0-100.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief reasoning for the decision (1-2 sentences).",
                    },
                },
                "required": ["tp_multiplier", "sl_multiplier", "size_multiplier", "confidence", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skip_trade",
            "description": "Skip this trade signal — do not execute.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Reason for skipping (1-2 sentences).",
                    }
                },
                "required": ["reason"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class AIDecision:
    execute: bool
    sl_multiplier: float = 2.0
    tp_multiplier: float = 3.0
    size_multiplier: float = 1.0
    confidence: int = 50
    reasoning: str = ""
    guardrail_adjustments: list = field(default_factory=list)

    def log_line(self, symbol: str) -> str:
        action = "EXECUTE" if self.execute else "SKIP"
        parts = [f"[AI] {symbol} → {action} | conf={self.confidence}"]
        if self.execute:
            parts.append(f"SL={self.sl_multiplier:.1f}x TP={self.tp_multiplier:.1f}x size={self.size_multiplier:.1f}x")
        if self.guardrail_adjustments:
            parts.append(f"guardrails: {', '.join(self.guardrail_adjustments)}")
        parts.append(f"| {self.reasoning}")
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# TradingAssistant
# ---------------------------------------------------------------------------


class TradingAssistant:
    """Wraps OpenAI Assistants API for per-signal trade decisions."""

    def __init__(self) -> None:
        # v0.5.6: SettingsPage 存 ai_config 的 openai key 优先；env 兜底
        api_key = self._resolve_openai_key()
        if not api_key:
            raise ValueError("OPENAI key not set (try SettingsPage AI provider=openai 或 OPENAI_API_KEY env)")

        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.assistant_id: Optional[str] = os.getenv("OPENAI_ASSISTANT_ID")
        self.vector_store_id: Optional[str] = os.getenv("OPENAI_VECTOR_STORE_ID")
        self._ready = False

    @staticmethod
    def _resolve_openai_key() -> Optional[str]:
        try:
            try:
                from ai_config_manager import resolve_active_ai  # type: ignore[import-not-found]
            except ImportError:
                from scripts.ai_config_manager import resolve_active_ai  # type: ignore[import-not-found]
            cfg = resolve_active_ai(expected_provider="openai")
            if cfg.get("enabled") and cfg.get("api_key"):
                return cfg["api_key"]
        except Exception:
            pass
        return os.getenv("OPENAI_API_KEY")

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Load existing assistant or create a new one."""
        if self.assistant_id:
            self._ready = True
            print(f"[AI] TradingAssistant loaded | assistant={self.assistant_id} | vs={self.vector_store_id}")
            return
        await self._create_assistant()

    async def _create_assistant(self) -> None:
        """One-time creation of Assistant + Vector Store. IDs are printed for .env."""
        print("[AI] Creating new Assistant and Vector Store...")

        # Create vector store
        vs = await self.client.beta.vector_stores.create(name="RabbitHunter_TradeMemory")
        self.vector_store_id = vs.id

        # Build tools list: file_search + our function tools
        tools = [{"type": "file_search"}, *TOOLS]

        assistant = await self.client.beta.assistants.create(
            name="RabbitHunter_TradingAI",
            instructions=SYSTEM_PROMPT,
            model=os.getenv("OPENAI_TRADING_MODEL", "gpt-4o"),
            tools=tools,
            tool_resources={"file_search": {"vector_store_ids": [self.vector_store_id]}},
        )
        self.assistant_id = assistant.id
        self._ready = True

        print("=" * 60)
        print("[AI] Assistant created successfully. Add to your .env:")
        print(f"  OPENAI_ASSISTANT_ID={self.assistant_id}")
        print(f"  OPENAI_VECTOR_STORE_ID={self.vector_store_id}")
        print("=" * 60)

    # ------------------------------------------------------------------
    # Main decision method
    # ------------------------------------------------------------------

    async def decide(
        self,
        symbol: str,
        side: str,
        price: float,
        features: dict,
        score_result: dict,
        decision_result: dict,
    ) -> AIDecision:
        """Make a trade/skip decision for one signal.

        Falls back to execute-with-defaults if AI is unavailable or times out.
        """
        if not self._ready or not self.assistant_id:
            fail_open = _fail_open()
            return AIDecision(
                execute=fail_open,
                confidence=40 if fail_open else 0,
                reasoning=(
                    "AI not initialized; AI_FAIL_OPEN=true → executing with rule defaults"
                    if fail_open
                    else "AI not initialized; AI_FAIL_OPEN=false → skipping trade"
                ),
            )

        try:
            message = self._build_message(symbol, side, price, features, score_result, decision_result)

            thread = await self.client.beta.threads.create(
                messages=[{"role": "user", "content": message}]
            )

            run = await self.client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=self.assistant_id,
            )

            timeout = float(os.getenv("OPENAI_DECISION_TIMEOUT", "20"))
            result = await self._wait_for_decision(thread.id, run.id, timeout=timeout)

            # Fire-and-forget thread cleanup
            asyncio.create_task(self._delete_thread(thread.id))

            print(result.log_line(symbol))
            return result

        except Exception as exc:
            fail_open = _fail_open()
            print(f"[AI] ERROR deciding {symbol}: {exc} | fail_open={fail_open}")
            return AIDecision(
                execute=fail_open,
                confidence=40 if fail_open else 0,
                reasoning=(
                    f"AI error ({type(exc).__name__}); AI_FAIL_OPEN=true → executing"
                    if fail_open
                    else f"AI error ({type(exc).__name__}); AI_FAIL_OPEN=false → skipping trade"
                ),
            )

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    async def _wait_for_decision(
        self, thread_id: str, run_id: str, timeout: float = 20.0
    ) -> AIDecision:
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            run = await self.client.beta.threads.runs.retrieve(
                thread_id=thread_id, run_id=run_id
            )

            if run.status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                for tc in tool_calls:
                    args = json.loads(tc.function.arguments)
                    # Submit dummy output so run completes cleanly
                    await self.client.beta.threads.runs.submit_tool_outputs(
                        thread_id=thread_id,
                        run_id=run_id,
                        tool_outputs=[{"tool_call_id": tc.id, "output": "acknowledged"}],
                    )

                    if tc.function.name == "execute_trade":
                        try:
                            g = apply_guardrails(
                                sl_mult=args.get("sl_multiplier", 2.0),
                                tp_mult=args.get("tp_multiplier", 3.0),
                                size_mult=args.get("size_multiplier", 1.0),
                            )
                        except GuardrailRejection as exc:
                            print(f"[AI] guardrails rejected execute_trade args: {exc}")
                            return AIDecision(
                                execute=False,
                                confidence=0,
                                reasoning=f"Guardrails rejected AI output: {exc}",
                            )
                        return AIDecision(
                            execute=True,
                            sl_multiplier=g.sl_multiplier,
                            tp_multiplier=g.tp_multiplier,
                            size_multiplier=g.size_multiplier,
                            confidence=int(args.get("confidence", 70)),
                            reasoning=args.get("reasoning", ""),
                            guardrail_adjustments=g.adjustments,
                        )

                    elif tc.function.name == "skip_trade":
                        return AIDecision(
                            execute=False,
                            confidence=0,
                            reasoning=args.get("reason", "AI skipped"),
                        )

                    else:
                        # Unknown tool name — treat as malformed AI output, fail-closed.
                        print(f"[AI] unknown tool call '{tc.function.name}', skipping trade")
                        return AIDecision(
                            execute=False,
                            confidence=0,
                            reasoning=f"AI emitted unknown tool '{tc.function.name}'",
                        )

            elif run.status in ("completed", "failed", "cancelled", "expired"):
                reason = f"Run ended with status={run.status}"
                fail_open = _fail_open() and run.status == "completed"
                # failed/cancelled/expired: always fail-closed (the AI didn't actually decide).
                # completed without tool call: honor AI_FAIL_OPEN.
                if run.status != "completed":
                    print(f"[AI] WARNING: {reason} → skipping trade")
                else:
                    print(f"[AI] {reason} without tool call | fail_open={fail_open}")
                return AIDecision(
                    execute=fail_open,
                    confidence=40 if fail_open else 0,
                    reasoning=(
                        f"{reason}; AI_FAIL_OPEN=true → executing with rule defaults"
                        if fail_open
                        else f"{reason}; skipping trade (fail-closed)"
                    ),
                )

            await asyncio.sleep(0.5)

        # Timeout
        fail_open = _fail_open()
        print(f"[AI] TIMEOUT after {timeout}s | fail_open={fail_open}")
        return AIDecision(
            execute=fail_open,
            confidence=35 if fail_open else 0,
            reasoning=(
                "AI timeout; AI_FAIL_OPEN=true → executing with rule defaults"
                if fail_open
                else "AI timeout; AI_FAIL_OPEN=false → skipping trade"
            ),
        )

    # ------------------------------------------------------------------
    # Message builder
    # ------------------------------------------------------------------

    def _build_message(
        self,
        symbol: str,
        side: str,
        price: float,
        features: dict,
        score_result: dict,
        decision_result: dict,
    ) -> str:
        strategy_id = decision_result.get("strategy_id", "UNKNOWN")
        atr = features.get("atr") or features.get("atr_1h") or 0.0
        funding = features.get("funding_rate", 0.0)
        oi_change = features.get("oi_change_1h", features.get("oi_change", 0.0))
        price_change = features.get("price_change_1h", features.get("price_change", 0.0))
        ls_ratio = features.get("long_short_ratio", features.get("ls_ratio", 0.0))

        structure = score_result.get("structure_score", 0.0) * 100
        volatility = score_result.get("volatility_score", 0.0) * 100
        sentiment = score_result.get("sentiment_score", 0.0) * 100
        manipulation = score_result.get("manipulation_score", 0.0) * 100
        final_score = score_result.get("final_score", 0.0) * 100

        return f"""## Signal: {symbol} | {side} | {strategy_id}

**Price**: {price:.6g}  |  **ATR**: {atr:.6g}

### Dimension Scores (0-100)
| Metric | Score |
|--------|-------|
| Structure | {structure:.1f} |
| Volatility | {volatility:.1f} |
| Sentiment | {sentiment:.1f} |
| Manipulation | {manipulation:.1f} |
| **Final** | **{final_score:.1f}** |

### Market Context
| Field | Value |
|-------|-------|
| OI Change 1h | {oi_change:+.2f}% |
| Price Change 1h | {price_change:+.2f}% |
| Funding Rate | {float(funding)*100:+.4f}% |
| Long/Short Ratio | {float(ls_ratio):.2f} |
| Market Phase | {features.get('phase', features.get('market_phase', 'UNKNOWN'))} |
| Kill Zone | {features.get('kill_zone_signal', 'NONE')} |

### Rule Engine
- Strategy: {strategy_id}
- Rule reason: {decision_result.get('reason', decision_result.get('block_reason', 'N/A'))}

Search your memory for similar historical trades on {symbol} or similar market conditions, then call execute_trade() or skip_trade()."""

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def _delete_thread(self, thread_id: str) -> None:
        try:
            await self.client.beta.threads.delete(thread_id=thread_id)
        except Exception:
            pass
