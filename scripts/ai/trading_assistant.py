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
        # Provider 解析优先级:
        #   1. DeepSeek(DEEPSEEK_ENABLED=true + DEEPSEEK_API_KEY 有值)
        #      → AsyncOpenAI(base_url="https://api.deepseek.com/v1"),走 chat
        #        completions(DeepSeek 不支持 Assistants API/Vector Store)
        #   2. OpenAI(OPENAI_API_KEY 有值,通过 SettingsPage 或 env)
        #      → 走 Assistants API + Vector Store(完整学习闭环)
        #   3. 否则 client=None,scorer fail-closed
        self.provider: Optional[str] = None
        self.client = None
        self.assistant_id: Optional[str] = None
        self.vector_store_id: Optional[str] = None
        self.chat_model: str = "gpt-4o"
        self._ready = False

        if self._try_init_deepseek():
            return
        self._try_init_openai()

    def _try_init_deepseek(self) -> bool:
        """检测 DeepSeek 配置 → 初始化兼容 client。返回 True 表示走 DeepSeek。"""
        enabled = os.getenv("DEEPSEEK_ENABLED", "false").lower() in ("1", "true")
        key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not (enabled and key):
            return False
        try:
            import openai as _openai
            self.client = _openai.AsyncOpenAI(
                api_key=key,
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            )
            self.provider = "deepseek"
            self.chat_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            self._ready = True  # DeepSeek 不用 Assistants,初始化即就绪
            print(f"[AI] TradingAssistant 用 DeepSeek({self.chat_model})provider")
            return True
        except ImportError:
            return False

    def _try_init_openai(self) -> None:
        api_key = self._resolve_openai_key()
        if not api_key:
            return
        try:
            import openai as _openai
            self.client = _openai.AsyncOpenAI(api_key=api_key)
            self.provider = "openai"
            self.assistant_id = os.getenv("OPENAI_ASSISTANT_ID")
            self.vector_store_id = os.getenv("OPENAI_VECTOR_STORE_ID")
            self.chat_model = os.getenv("OPENAI_TRADING_MODEL", "gpt-4o")
        except ImportError:
            self.client = None

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
        """Load existing assistant or create a new one.

        DeepSeek 等非 OpenAI provider 不用 Assistants API/Vector Store,
        _ready 已在 __init__ 里设;此处直接 no-op。
        """
        if not self.client:
            return
        if self.provider != "openai":
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
        *,
        strategy_id: Optional[str] = None,
    ) -> "AIResult":
        """Pre-decision veto: 命中 failure_taxonomy 直接返回 execute=False。
        v5_manual 单豁免 (用户主导)。
        V5 二次审查 — 根据 provider 走 Assistants(OpenAI+assistant_id)
        或 chat completions(DeepSeek / OpenAI 无 assistant_id)。
        """
        from v5_types import AIResult

        if strategy_id != "v5_manual":
            from scripts.ai.failure_taxonomy import match_failure_modes

            side_int = 1 if decision.side == "LONG" else -1
            sl_dist = abs((risk.sl_price or 0) - (risk.entry_price or 0))
            tp_dist = abs((risk.tp_price or 0) - (risk.entry_price or 0))
            atr = indicators.atr_15m or 0.0
            candidate = {
                "symbol": enriched.symbol,
                "side": decision.side,
                "side_int": side_int,
                "rsi_15m": indicators.rsi_15m,
                "macd_hist_15m": indicators.macd_hist_15m,
                "macd_hist_prev_15m": indicators.macd_hist_prev_15m,
                "macd_hist_4h": indicators.macd_hist_4h,
                "atr_15m": atr,
                "sl_distance_atr_ratio": (sl_dist / atr) if atr > 0 else 0,
                "tp_distance_atr_ratio": (tp_dist / atr) if atr > 0 else 0,
                "delta_15m_pct": enriched.delta_15m_pct,
                "funding_z_score": None,    # V6 上线后填
            }
            try:
                hits = match_failure_modes(candidate)
            except Exception as e:
                print(f"[trading_assistant] taxonomy match error: {e}")
                hits = []
            if hits:
                return AIResult(
                    execute=False,
                    sl_multiplier=1.0, tp_multiplier=1.0,
                    size_multiplier=0.0, confidence=0.0,
                    reasoning=f"FAILURE_MODE_MATCH: {','.join(hits)}",
                )

        # ── 原 RAG + AI call 路径继续 (existing code) ──
        from scripts.ai.prompt import V5_SYSTEM_PROMPT, build_v5_user_message
        from scripts.ai.guardrails import clamp_ai_result

        if not self.client:
            return AIResult(execute=False, sl_multiplier=1.0, tp_multiplier=1.0,
                            size_multiplier=0.0, confidence=0.0,
                            reasoning="AI 未初始化")

        user_msg = build_v5_user_message(enriched, indicators, decision, risk)
        timeout_s = float(os.getenv("AI_DECISION_TIMEOUT", "20"))

        # RAG 注入(仅 chat completions 路径用)
        self._pending_rag_text = ""
        if not (self.provider == "openai" and self.assistant_id):
            try:
                from scripts.ai.local_rag import find_similar_cases, format_cases_for_prompt
                cases = find_similar_cases(
                    indicators, side=decision.side or "SHORT", top_k=5,
                    source_delta_15m_pct=enriched.delta_15m_pct,
                )
                self._pending_rag_text = format_cases_for_prompt(cases)
            except Exception as e:
                print(f"[AI] RAG 检索失败,跳过: {type(e).__name__}: {e}")

        try:
            if self.provider == "openai" and self.assistant_id:
                raw_json = await asyncio.wait_for(
                    self._decide_via_assistant(user_msg, timeout_s=timeout_s),
                    timeout=timeout_s + 2.0,
                )
            else:
                raw_json = await asyncio.wait_for(
                    self._decide_via_chat(V5_SYSTEM_PROMPT, user_msg),
                    timeout=timeout_s,
                )
            if isinstance(raw_json, AIResult):
                return clamp_ai_result(raw_json)
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
                            reasoning=f"AI 调用超时(>{timeout_s:.0f}s),fail-closed")
        except Exception as e:
            return AIResult(execute=False, sl_multiplier=1.0, tp_multiplier=1.0,
                            size_multiplier=0.0, confidence=0.0,
                            reasoning=f"AI 调用异常 {type(e).__name__}: {e}")

    # ------------------------------------------------------------------
    # Provider-specific decision paths
    # ------------------------------------------------------------------

    async def _decide_via_assistant(self, user_msg: str, timeout_s: float = 20) -> dict:
        """OpenAI Assistants 路径 — 有 Vector Store 学习闭环。"""
        thread = await self._create_thread()
        await self._add_message(thread.id, user_msg)
        run = await self._run_with_timeout(thread.id, self.assistant_id, timeout_s=timeout_s)
        return await self._extract_tool_output(thread.id, run)

    async def _decide_via_chat(self, system_prompt: str, user_msg: str) -> dict:
        """Chat completions 路径,带 RAG-lite 注入。"""
        json_constraint = (
            "\n\nReturn ONLY a JSON object with exactly these keys: "
            'execute (boolean), sl_multiplier (number 1.0-3.0), '
            'tp_multiplier (number 1.5-5.0), size_multiplier (number 0.3-1.2), '
            'confidence (number 0.0-1.0), reasoning (string ≤ 200 chars). '
            "No markdown, no surrounding text."
        )

        rag_text = getattr(self, "_pending_rag_text", "") or ""
        if rag_text:
            system_full = system_prompt + "\n\n" + rag_text + json_constraint
        else:
            system_full = system_prompt + json_constraint

        resp = await self.client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {"role": "system", "content": system_full},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=300,
        )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)

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
        """轻量 chat completion — 不用 Assistant thread,快得多。给续仓决策用。

        模型用 self.chat_model:OpenAI 用户实际是 gpt-4o(可用 OPENAI_QUICK_MODEL
        覆盖到 gpt-4o-mini 省钱),DeepSeek 用户用 deepseek-chat。
        """
        if not self.client:
            return "CLOSE"
        # OpenAI 用户想用更便宜的 quick 模型可以覆盖
        model = os.getenv("OPENAI_QUICK_MODEL", self.chat_model) if self.provider == "openai" else self.chat_model
        resp = await self.client.chat.completions.create(
            model=model,
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
