"""OpenAI Assistants API trading decision engine.

Flow per signal (V5):
  1. Build structured message with V5 EnrichedItem/Indicators/Decision/RiskPlan
  2. Create a new Thread (stateless per signal)
  3. Run the Assistant — it retrieves similar trades from Vector Store automatically
  4. Parse the function call output (trading_decision tool)
  5. Apply guardrails to clamp parameters
  6. Return AIResult to caller

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
            "name": "trading_decision",
            "description": "Report the trade decision with risk parameters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "execute": {
                        "type": "boolean",
                        "description": "Whether to execute the trade.",
                    },
                    "sl_multiplier": {
                        "type": "number",
                        "description": "SL multiplier (1.0–3.0). 1.0 = use rule-engine SL as-is.",
                    },
                    "tp_multiplier": {
                        "type": "number",
                        "description": "TP multiplier (1.5–5.0). 1.0 = use rule-engine TP as-is.",
                    },
                    "size_multiplier": {
                        "type": "number",
                        "description": "Position size multiplier (0.3–1.2).",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence level 0.0–1.0.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "One-sentence reasoning.",
                    },
                },
                "required": ["execute", "sl_multiplier", "tp_multiplier",
                             "size_multiplier", "confidence", "reasoning"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Result dataclass (legacy — kept for backward compat with scorer.py)
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
            self.client = None
            self.assistant_id = None
            self.vector_store_id = None
            self._ready = False
            return

        try:
            import openai as _openai
            self.client = _openai.AsyncOpenAI(api_key=api_key)
        except ImportError:
            self.client = None

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
        if not self.client:
            return
        if self.assistant_id:
            self._ready = True
            print(f"[AI] TradingAssistant loaded | assistant={self.assistant_id} | vs={self.vector_store_id}")
            return
        await self._create_assistant()

    async def _create_assistant(self) -> None:
        """One-time creation of Assistant + Vector Store. IDs are printed for .env."""
        if not self.client:
            return
        print("[AI] Creating new Assistant and Vector Store...")

        from scripts.ai.prompt import V5_SYSTEM_PROMPT

        # Create vector store
        vs = await self.client.beta.vector_stores.create(name="RabbitHunter_TradeMemory")
        self.vector_store_id = vs.id

        # Build tools list: file_search + our function tools
        tools = [{"type": "file_search"}, *TOOLS]

        assistant = await self.client.beta.assistants.create(
            name="RabbitHunter_TradingAI",
            instructions=V5_SYSTEM_PROMPT,
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
    # V5 Main decision method
    # ------------------------------------------------------------------

    async def decide(
        self,
        enriched,           # EnrichedItem
        indicators,         # Indicators
        decision,           # Decision
        risk,               # RiskPlan
    ) -> "AIResult":
        """V5 二次审查 — 用 GPT-4o 看完上下文给最终参数。"""
        from v5_types import AIResult
        from scripts.ai.prompt import V5_SYSTEM_PROMPT, build_v5_user_message
        from scripts.ai.guardrails import clamp_ai_result

        if not self.client or not self.assistant_id:
            return AIResult(execute=False, sl_multiplier=1.0, tp_multiplier=1.0,
                            size_multiplier=0.0, confidence=0.0,
                            reasoning="AI 未初始化")

        user_msg = build_v5_user_message(enriched, indicators, decision, risk)
        try:
            thread = await self._create_thread()
            await self._add_message(thread.id, user_msg)
            run = await self._run_with_timeout(thread.id, self.assistant_id, timeout_s=20)
            raw_json = await self._extract_tool_output(thread.id, run)
            result = AIResult(
                execute=bool(raw_json.get("execute", False)),
                sl_multiplier=float(raw_json.get("sl_multiplier", 1.0)),
                tp_multiplier=float(raw_json.get("tp_multiplier", 1.0)),
                size_multiplier=float(raw_json.get("size_multiplier", 1.0)),
                confidence=float(raw_json.get("confidence", 0.5)),
                reasoning=str(raw_json.get("reasoning", "")),
            )
            return clamp_ai_result(result)
        except asyncio.TimeoutError:
            return AIResult(execute=False, sl_multiplier=1.0, tp_multiplier=1.0,
                            size_multiplier=0.0, confidence=0.0,
                            reasoning="AI 调用超时(>20s),fail-closed")
        except Exception as e:
            return AIResult(execute=False, sl_multiplier=1.0, tp_multiplier=1.0,
                            size_multiplier=0.0, confidence=0.0,
                            reasoning=f"AI 调用异常 {type(e).__name__}: {e}")

    # ------------------------------------------------------------------
    # V5 low-level helpers (used by decide above)
    # ------------------------------------------------------------------

    async def _create_thread(self):
        """Create a new empty thread."""
        return await self.client.beta.threads.create()

    async def _add_message(self, thread_id: str, content: str) -> None:
        """Add a user message to a thread."""
        await self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content,
        )

    async def _run_with_timeout(self, thread_id: str, assistant_id: str, timeout_s: float = 20):
        """Start a run and wait for it to reach requires_action or terminal state."""
        run = await self.client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
        )
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            run = await self.client.beta.threads.runs.retrieve(
                thread_id=thread_id, run_id=run.id
            )
            if run.status in ("requires_action", "completed", "failed", "cancelled", "expired"):
                return run
            await asyncio.sleep(0.5)
        raise asyncio.TimeoutError(f"Run did not complete within {timeout_s}s")

    async def _extract_tool_output(self, thread_id: str, run) -> dict:
        """Extract the first tool call arguments from a requires_action run.

        Submits a dummy output so the run completes cleanly, then returns
        the parsed JSON args dict. Returns empty dict if no tool call.
        """
        if run.status != "requires_action":
            return {}
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        if not tool_calls:
            return {}
        tc = tool_calls[0]
        args = json.loads(tc.function.arguments)
        # Submit dummy output so run completes cleanly
        await self.client.beta.threads.runs.submit_tool_outputs(
            thread_id=thread_id,
            run_id=run.id,
            tool_outputs=[{"tool_call_id": tc.id, "output": "acknowledged"}],
        )
        # Fire-and-forget thread cleanup
        asyncio.create_task(self._delete_thread(thread_id))
        return args

    # ------------------------------------------------------------------
    # Lightweight single-turn completion (no Assistant thread)
    # ------------------------------------------------------------------

    async def quick_yes_no(self, system: str, user: str) -> str:
        """轻量 chat completion — 不用 Assistant thread,快得多。给续仓决策用。"""
        if not self.client:
            return "CLOSE"
        resp = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=10,
        )
        return resp.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def _delete_thread(self, thread_id: str) -> None:
        try:
            await self.client.beta.threads.delete(thread_id=thread_id)
        except Exception:
            pass
