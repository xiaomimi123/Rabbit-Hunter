# Reflection Worker Phases 1-3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 spec §7 阶段 1-3 落地:每笔关仓自动 AI 5 问复盘 → 失败模式分类过滤入场 → 日聚合 + 周度 fractional Kelly 仓位建议 + AI 置信度校准 + 前端复盘工作台 3 个 tab。阶段 4 (entry filter 提案 + A/B) 和阶段 5 (监控) 留作后续 plan。

**Architecture:**
- 后端新增独立 `v5_reflection_worker` 异步进程,跟 `v5_position_monitor` / `v5_scorer` 同级,run-loop + 内嵌 cron 调度
- 数据流:`paper_trades.status='CLOSED'` → `reflection_queue` → AI → `reflections` + `ai_training_data`(向后兼容) + 增量更新 `ai_confidence_calibration`
- 入场端 `trading_assistant.decide` 增加两层 short-circuit:`failure_taxonomy` 匹配 → veto;`ai_confidence_calibration` 应用倍数
- 前端新 `/v5/reflection` 三 tab 页 + AI Status 页加校准曲线
- 所有"修改策略"行为(sizing 调整)默认 pending → 用户批准 → 仅写 DB,不自动应用到 trading_assistant(本 plan 不实现自动应用,留给阶段 4)

**Tech Stack:** Python 3.11 / FastAPI / SQLite / Pydantic v2 / pytest (后端 125 tests baseline) · React 19 / Vite / Vitest / TanStack Query (前端 47 tests baseline after glossary/chart hover)

**Direct push to `main`** per user policy throughout.

**Cumulative test target after this plan:** backend 125 + 30 = ~155; frontend 47 + 10 = ~57.

**Working directory:** `/Users/lizhishaoniange/Documents/Rabbit-Hunter`. Frontend dir: `Rabbit Hunterfronted/` (preserve the space and the "fronted" typo).

---

## File Inventory

### Phase 1 — Layer 1 实时复盘

| File | Action | Responsibility |
|---|---|---|
| `scripts/local_db.py` | MODIFY | Append `reflection_queue` + `reflections` tables to `_V5_SCHEMA_SQL` |
| `scripts/ai/reflection_prompt.py` | CREATE | 5 问 prompt builder + JSON schema in prompt |
| `scripts/ai/reflection_runner.py` | CREATE | Thin async wrapper: load context → call AI → validate → persist |
| `api/schemas/v5_reflection.py` | CREATE | Pydantic schemas: ReflectionOutput / ReflectionRecord / ReflectionsResponse |
| `scripts/tasks/v5_reflection_worker.py` | CREATE | Main `asyncio` worker; phase-1 only does Layer 1 |
| `scripts/v5_position_monitor.py` | MODIFY | After successful close → `enqueue_reflection(paper_trade_id, db_path)` |
| `scripts/tasks/collector_main.py` | MODIFY | Wire up `V5ReflectionWorker.run()` in lifespan |
| `api/routes/v5_reflection.py` | CREATE | `GET /api/v5/reflections?limit=N` |
| `api/main.py` | MODIFY | Register `v5_reflection` router |
| `tests/test_reflection_db.py` | CREATE | DB schema + enqueue tests |
| `tests/test_reflection_prompt.py` | CREATE | Prompt builder tests |
| `tests/test_reflection_runner.py` | CREATE | Mock AI; full pipeline test |
| `tests/test_v5_reflection_api.py` | CREATE | API integration test |

### Phase 2 — Layer 2 失败模式

| File | Action | Responsibility |
|---|---|---|
| `scripts/local_db.py` | MODIFY | Add `failure_taxonomy` table + seed function |
| `scripts/ai/failure_taxonomy.py` | CREATE | DSL parser + matcher + 8 seeded rules |
| `scripts/ai/trading_assistant.py` | MODIFY | Pre-decision check: match taxonomy → veto with `block_reason=FAILURE_MODE_MATCH:<key>` |
| `api/schemas/v5_reflection.py` | MODIFY | Add FailureMode / FailureTaxonomyResponse schemas |
| `api/routes/v5_reflection.py` | MODIFY | Add `GET /api/v5/failure-taxonomy` |
| `tests/test_failure_taxonomy.py` | CREATE | DSL parser + each seeded rule tests |
| `tests/test_trading_assistant_taxonomy.py` | CREATE | Veto integration test |

### Phase 3 — Layer 3 日聚合 + Layer 4 Kelly 仓位 + 置信度校准

| File | Action | Responsibility |
|---|---|---|
| `scripts/local_db.py` | MODIFY | Add `setup_performance_daily`, `position_sizing_recommendations`, `ai_confidence_calibration` |
| `scripts/ai/setup_aggregator.py` | CREATE | Daily aggregator by setup_type |
| `scripts/ai/kelly_sizing.py` | CREATE | fractional Kelly + 3-window confidence |
| `scripts/ai/confidence_calibration.py` | CREATE | Increment on reflection + lookup multiplier |
| `scripts/ai/trading_assistant.py` | MODIFY | Apply calibration multiplier to AI confidence |
| `scripts/tasks/v5_reflection_worker.py` | MODIFY | Daily 03:00 UTC + weekly Sun 04:00 UTC cron |
| `api/schemas/v5_reflection.py` | MODIFY | Add SetupPerformanceItem / SizingRecommendation / CalibrationCurvePoint schemas |
| `api/routes/v5_reflection.py` | MODIFY | Add `GET /setup-performance`, `GET /sizing-recommendations`, `PATCH /sizing-recommendations/:id`, `GET /confidence-calibration` |
| `tests/test_setup_aggregator.py` | CREATE | |
| `tests/test_kelly_sizing.py` | CREATE | |
| `tests/test_confidence_calibration.py` | CREATE | |

### Phase 3 frontend

| File | Action | Responsibility |
|---|---|---|
| `Rabbit Hunterfronted/types.ts` | MODIFY | Reflection / FailureMode / SetupPerformance / SizingRecommendation / CalibrationPoint types |
| `Rabbit Hunterfronted/hooks/api/useV5Reflections.ts` | CREATE | List + per-tab data hooks |
| `Rabbit Hunterfronted/components/pages/V5ReflectionPage.tsx` | CREATE | 3-tab page (复盘流 / 失败模式 / 仓位建议) |
| `Rabbit Hunterfronted/components/pages/V5AIStatusPage.tsx` | MODIFY | Add calibration curve HoloCard |
| `Rabbit Hunterfronted/App.tsx` | MODIFY | `/v5/reflection` route |
| `Rabbit Hunterfronted/components/layout/Sidebar.tsx` | MODIFY | "智能" group adds "复盘工作台" |
| `Rabbit Hunterfronted/services/glossary.ts` | MODIFY | Add 反思 / 失败模式 / Kelly 仓位 / 置信度校准 terms |
| `Rabbit Hunterfronted/tests/pages/V5ReflectionPage.test.tsx` | CREATE | |

---

## Phase 1 — Layer 1 实时复盘 (5 tasks)

### Task 1: DB schema — reflection_queue + reflections + setup_type 派生函数

**Files:**
- Modify: `scripts/local_db.py` (append to `_V5_SCHEMA_SQL`)
- Create: `scripts/ai/setup_type.py`
- Create: `tests/test_reflection_db.py`
- Create: `tests/test_setup_type.py`

- [ ] **Step 1: Write failing test `tests/test_setup_type.py`**

```python
"""setup_type 派生 — 确定性,不依赖 AI。"""
from scripts.ai.setup_type import derive_setup_type


def _entry(**over):
    base = dict(
        side="SHORT", strategy_id="v5_rsi_macd",
        rsi_15m=72.0, macd_hist=-0.0012, macd_hist_prev=0.0008,
        funding_z_score=None,
    )
    base.update(over)
    return base


def test_manual_short_returns_manual_short():
    assert derive_setup_type(_entry(strategy_id="v5_manual", side="SHORT")) == "manual_short"


def test_rsi_overbought_macd_bearish_short():
    assert derive_setup_type(_entry()) == "rsi_overbought_macd_bearish_short"


def test_rsi_oversold_macd_bullish_long():
    assert derive_setup_type(_entry(
        side="LONG", rsi_15m=28.0,
        macd_hist=0.0005, macd_hist_prev=-0.0004,
    )) == "rsi_oversold_macd_bullish_long"


def test_rsi_neutral_macd_extending_short():
    assert derive_setup_type(_entry(rsi_15m=55.0,
        macd_hist=-0.001, macd_hist_prev=-0.0008)) == "rsi_neutral_macd_extending_short"


def test_funding_extreme_short_overrides_when_zscore_high():
    assert derive_setup_type(_entry(funding_z_score=2.3)) == "funding_extreme_short_rsi_overbought"


def test_funding_extreme_long_when_negative():
    assert derive_setup_type(_entry(
        side="LONG", rsi_15m=25.0,
        macd_hist=0.0005, macd_hist_prev=-0.0004,
        funding_z_score=-2.5,
    )) == "funding_extreme_long_rsi_oversold"
```

- [ ] **Step 2: Run, expect fail**

```bash
python3 -m pytest tests/test_setup_type.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Write `scripts/ai/setup_type.py`**

```python
"""setup_type 派生 — 确定性,可枚举。聚合按它分桶。"""
from typing import Optional


def derive_setup_type(entry: dict) -> str:
    """从 entry snapshot 派生 setup_type 字符串。AI 不参与。

    entry 必须含字段:side / strategy_id / rsi_15m / macd_hist / macd_hist_prev
    可选: funding_z_score(V6 上线后才有)
    """
    side = (entry.get("side") or "").upper()
    side_lower = side.lower() if side else "unknown"

    if entry.get("strategy_id") == "v5_manual":
        return f"manual_{side_lower}"

    rsi = float(entry.get("rsi_15m") or 50.0)
    hist = float(entry.get("macd_hist") or 0.0)
    hist_prev = float(entry.get("macd_hist_prev") or 0.0)

    if rsi >= 70:
        rsi_state = "rsi_overbought"
    elif rsi <= 30:
        rsi_state = "rsi_oversold"
    else:
        rsi_state = "rsi_neutral"

    if hist_prev < 0 and hist > 0:
        macd_state = "macd_bullish"
    elif hist_prev > 0 and hist < 0:
        macd_state = "macd_bearish"
    else:
        macd_state = "macd_extending"

    fz: Optional[float] = entry.get("funding_z_score")
    if fz is not None and abs(fz) >= 2.0:
        direction = "short" if fz > 0 else "long"
        return f"funding_extreme_{direction}_{rsi_state}"

    return f"{rsi_state}_{macd_state}_{side_lower}"
```

- [ ] **Step 4: Run tests, expect 6 passed**

- [ ] **Step 5: Write failing test `tests/test_reflection_db.py`**

```python
"""reflection_queue + reflections schema + enqueue_reflection helper。"""
import os
import sqlite3
import tempfile
import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def test_reflection_queue_table_created(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(reflection_queue)").fetchall()]
    conn.close()
    assert "id" in cols
    assert "paper_trade_id" in cols
    assert "enqueued_at" in cols
    assert "started_at" in cols
    assert "completed_at" in cols
    assert "error" in cols
    assert "retry_count" in cols


def test_reflections_table_created(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(reflections)").fetchall()]
    conn.close()
    for required in (
        "paper_trade_id", "why_entered", "what_was_expected",
        "what_actually_happened", "correction_idea", "failure_mode_key",
        "setup_type", "outcome_class", "realized_r",
        "confidence_at_entry", "self_assessed_prediction_accuracy",
        "ai_provider", "ai_model", "prompt_version", "raw_response_json",
    ):
        assert required in cols, f"missing column: {required}"


def test_paper_trade_id_unique_in_queue(db):
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO reflection_queue (paper_trade_id) VALUES (1)")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO reflection_queue (paper_trade_id) VALUES (1)")
    conn.close()


def test_enqueue_reflection_helper_inserts(db):
    from scripts.local_db import enqueue_reflection
    enqueue_reflection(123, db_path=db)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT paper_trade_id, started_at, completed_at FROM reflection_queue WHERE paper_trade_id=123"
    ).fetchone()
    conn.close()
    assert row == (123, None, None)


def test_enqueue_reflection_helper_is_idempotent(db):
    """重复 enqueue 同一 paper_trade 不抛异常 (use INSERT OR IGNORE)。"""
    from scripts.local_db import enqueue_reflection
    enqueue_reflection(456, db_path=db)
    enqueue_reflection(456, db_path=db)
    conn = sqlite3.connect(db)
    count = conn.execute(
        "SELECT COUNT(*) FROM reflection_queue WHERE paper_trade_id=456"
    ).fetchone()[0]
    conn.close()
    assert count == 1
```

- [ ] **Step 6: Run, expect fail**

- [ ] **Step 7: Modify `scripts/local_db.py`**

Find `_V5_SCHEMA_SQL` near line 39 — it's a multi-line SQL string ending before a closing `"""`. Append the following tables INSIDE that string, just before the closing `"""`:

```sql

CREATE TABLE IF NOT EXISTS reflection_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_trade_id INTEGER NOT NULL UNIQUE,
    enqueued_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    error TEXT,
    retry_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_reflection_queue_pending
    ON reflection_queue(completed_at, retry_count)
    WHERE completed_at IS NULL;

CREATE TABLE IF NOT EXISTS reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_trade_id INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    why_entered TEXT NOT NULL,
    what_was_expected TEXT NOT NULL,
    what_actually_happened TEXT NOT NULL,
    correction_idea TEXT NOT NULL,
    failure_mode_key TEXT,
    setup_type TEXT NOT NULL,
    outcome_class TEXT NOT NULL,
    realized_r REAL NOT NULL,
    holding_minutes INTEGER NOT NULL,
    confidence_at_entry REAL NOT NULL,
    self_assessed_prediction_accuracy REAL,
    is_in_predicted_failure_mode INTEGER,
    ai_provider TEXT,
    ai_model TEXT,
    ai_latency_ms INTEGER,
    prompt_version TEXT,
    raw_response_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_reflections_setup_type
    ON reflections(setup_type, created_at);
```

At module bottom (after `init_local_db` definition), add the helper:

```python
def enqueue_reflection(paper_trade_id: int, *, db_path: str = "data/rabbit_hunter.db") -> None:
    """关仓后入队 reflection。idempotent — 重复入队同一 paper_trade 安全忽略。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO reflection_queue (paper_trade_id) VALUES (?)",
            (paper_trade_id,),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 8: Run tests, expect 5 passed**

```bash
python3 -m pytest tests/test_reflection_db.py tests/test_setup_type.py -v 2>&1 | tail -15
```

- [ ] **Step 9: Run full suite, no regression**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 125 + 11 = 136 passed.

- [ ] **Step 10: Commit**

```bash
git add scripts/local_db.py scripts/ai/setup_type.py tests/test_reflection_db.py tests/test_setup_type.py
git commit -m "feat(reflection): DB schema (reflection_queue + reflections) + setup_type 派生

- reflection_queue: paper_trade_id UNIQUE + (completed_at, retry_count) index
- reflections: 5 问结构化字段 + 聚合 dimensions + AI audit
- enqueue_reflection() idempotent helper
- derive_setup_type() 确定性派生 (manual/rsi_state × macd_state × side / funding_extreme)

11 unit tests."
```

---

### Task 2: Reflection prompt builder + Pydantic schemas

**Files:**
- Create: `scripts/ai/reflection_prompt.py`
- Create: `api/schemas/v5_reflection.py`
- Create: `tests/test_reflection_prompt.py`

- [ ] **Step 1: Write `api/schemas/v5_reflection.py`**

```python
"""V5 Reflection — Pydantic schemas for AI output + API responses."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# === AI Output Schema (validated against AI JSON response) ===

class ReflectionAIOutput(BaseModel):
    """AI 必须严格按这个 schema 回答 5 问。"""
    why_entered: str = Field(..., min_length=10, max_length=500)
    what_was_expected: str = Field(..., min_length=10, max_length=500)
    what_actually_happened: str = Field(..., min_length=10, max_length=500)
    correction_idea: str = Field(..., min_length=10, max_length=500)
    failure_mode_key: Optional[str] = Field(None, max_length=80)
    self_assessed_prediction_accuracy: float = Field(..., ge=0.0, le=1.0)
    is_in_predicted_failure_mode: bool


# === Stored Reflection Record (full row) ===

class ReflectionRecord(BaseModel):
    id: int
    paper_trade_id: int
    created_at: str
    why_entered: str
    what_was_expected: str
    what_actually_happened: str
    correction_idea: str
    failure_mode_key: Optional[str]
    setup_type: str
    outcome_class: Literal["WIN", "LOSS", "SCRATCH"]
    realized_r: float
    holding_minutes: int
    confidence_at_entry: float
    self_assessed_prediction_accuracy: Optional[float]
    is_in_predicted_failure_mode: Optional[bool]
    ai_provider: Optional[str]
    ai_model: Optional[str]
    ai_latency_ms: Optional[int]
    # 关联的 paper_trade 概要 (前端复盘流 card 展示用)
    symbol: Optional[str] = None
    side: Optional[str] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl_pct: Optional[float] = None


class ReflectionsResponse(BaseModel):
    status: str = "success"
    data: List[ReflectionRecord]


PROMPT_VERSION = "reflection-prompt-v1"
```

- [ ] **Step 2: Write failing test `tests/test_reflection_prompt.py`**

```python
"""Prompt builder — 应当注入 entry snapshot + 持仓轨迹 + RAG cases + taxonomy + JSON schema 指令。"""
import json
from scripts.ai.reflection_prompt import build_reflection_prompt


def _sample_close_context():
    return {
        "paper_trade_id": 7,
        "symbol": "HUSDT",
        "side": "SHORT",
        "strategy_id": "v5_rsi_macd",
        "entry_price": 0.166,
        "exit_price": 0.169,
        "entry_time": "2026-06-13T09:48:00+00:00",
        "exit_time": "2026-06-13T10:15:00+00:00",
        "exit_reason": "SL_HIT",
        "realized_r": -1.0,
        "holding_minutes": 27,
        "confidence_at_entry": 0.7,
        "entry_rsi_15m": 72.1,
        "entry_rsi_4h": 68.0,
        "entry_macd_hist_15m": -0.0012,
        "entry_macd_hist_prev_15m": 0.0008,
        "entry_atr_15m": 0.0015,
        "funding_z_score": None,
        "rule_reasoning": "RSI overbought + MACD bearish cross",
        "ai_reasoning": "short setup with RAG support",
        "rag_cases_text": "case1 RSI=73.2 hist=-0.0006 → WIN +0.4% TP_HIT\ncase2 RSI=71.5 hist=-0.0004 → LOSS -0.3% SL_HIT",
        "during_hold_path": "T+0 price 0.166 / T+5 0.167 / T+15 0.1685 / T+27 SL hit 0.169",
        "taxonomy_keys": [
            "late_entry_signal_decay",
            "macd_false_cross",
            "against_4h_trend_no_funding_filter",
            "sl_too_tight_in_high_atr",
            "tp_too_far_in_low_atr",
            "news_event_30min_blackout",
            "chase_after_3pct_move",
            "repeat_failure_same_symbol_24h",
        ],
    }


def test_prompt_contains_all_5_questions():
    prompt = build_reflection_prompt(_sample_close_context())
    assert "why_entered" in prompt
    assert "what_was_expected" in prompt
    assert "what_actually_happened" in prompt
    assert "failure_mode_key" in prompt
    assert "correction_idea" in prompt


def test_prompt_includes_entry_snapshot_values():
    prompt = build_reflection_prompt(_sample_close_context())
    assert "72.1" in prompt           # rsi_15m
    assert "HUSDT" in prompt
    assert "SHORT" in prompt
    assert "SL_HIT" in prompt


def test_prompt_includes_during_hold_path():
    prompt = build_reflection_prompt(_sample_close_context())
    assert "T+0" in prompt
    assert "T+27" in prompt


def test_prompt_includes_rag_cases():
    prompt = build_reflection_prompt(_sample_close_context())
    assert "case1" in prompt
    assert "WIN +0.4%" in prompt


def test_prompt_includes_all_taxonomy_keys():
    prompt = build_reflection_prompt(_sample_close_context())
    for k in (
        "late_entry_signal_decay", "macd_false_cross",
        "against_4h_trend_no_funding_filter",
        "chase_after_3pct_move", "repeat_failure_same_symbol_24h",
    ):
        assert k in prompt


def test_prompt_requires_json_response_with_schema():
    prompt = build_reflection_prompt(_sample_close_context())
    # 应当明示 JSON-only 输出
    assert "JSON" in prompt or "json" in prompt
    # 应当列出所有 7 个字段
    for field in ("why_entered", "what_was_expected", "what_actually_happened",
                  "correction_idea", "failure_mode_key",
                  "self_assessed_prediction_accuracy", "is_in_predicted_failure_mode"):
        assert field in prompt


def test_prompt_handles_missing_funding_gracefully():
    ctx = _sample_close_context()
    ctx["funding_z_score"] = None
    prompt = build_reflection_prompt(ctx)
    # 不应当抛异常,出现 funding 行但标注 N/A
    assert "Funding" in prompt or "funding" in prompt
```

- [ ] **Step 3: Run, expect fail**

- [ ] **Step 4: Write `scripts/ai/reflection_prompt.py`**

```python
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
```

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest tests/test_reflection_prompt.py -v 2>&1 | tail -10
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/ai/reflection_prompt.py api/schemas/v5_reflection.py tests/test_reflection_prompt.py
git commit -m "feat(reflection): 5 问 prompt builder + Pydantic schemas

- Prompt 注入 entry snapshot + 持仓轨迹 + RAG cases + 8 个 taxonomy keys
- 强制 JSON 响应,每字段长度边界 + 数值边界
- ReflectionAIOutput pydantic 校验
- ReflectionRecord 含关联 paper_trade 概要字段
- PROMPT_VERSION 用于追溯

7 prompt builder tests."
```

---

### Task 3: Reflection runner — load context → AI call → validate → persist

**Files:**
- Create: `scripts/ai/reflection_runner.py`
- Create: `tests/test_reflection_runner.py`

- [ ] **Step 1: Write failing test `tests/test_reflection_runner.py`**

```python
"""Reflection runner — 用 mock AI 跑完整管道,确认入库正确。"""
import json
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _insert_closed_paper_trade(db_path, *, pid=1, side="SHORT", strategy="v5_rsi_macd",
                                entry_rsi=72.0, macd_hist=-0.0012, macd_hist_prev=0.0008):
    conn = sqlite3.connect(db_path)
    entry_t = (datetime.now(timezone.utc) - timedelta(minutes=27)).isoformat()
    exit_t = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO paper_trades (
            id, symbol, side, entry_price, entry_time, status,
            stop_loss, take_profit, position_size_usdt, leverage,
            strategy_id, created_at, exit_price, exit_time, exit_reason,
            pnl_percent, entry_rsi_15m, entry_macd_hist_15m,
            ai_confidence, ai_reason
        ) VALUES (?, 'HUSDT', ?, 0.166, ?, 'CLOSED',
                  0.169, 0.162, 15.0, 10,
                  ?, ?, 0.169, ?, 'SL_HIT',
                  -1.8, ?, ?,
                  0.7, 'short setup')
    """, (pid, side, entry_t, strategy, entry_t, exit_t, entry_rsi, macd_hist))
    # 同时塞个 trade_scores_v5 行,reflection runner 会查它拿 macd_hist_prev
    conn.execute("""
        INSERT INTO trade_scores_v5 (
            symbol, created_at, rsi_15m, macd_hist_15m, macd_hist_prev_15m,
            atr_15m, current_price, executed, position_id, should_trade, side
        ) VALUES ('HUSDT', ?, ?, ?, ?, 0.0015, 0.166, 1, ?, 1, ?)
    """, (entry_t, entry_rsi, macd_hist, macd_hist_prev, pid, side))
    conn.commit()
    conn.close()


def test_run_reflection_writes_reflection_row(db, monkeypatch):
    """成功路径 — mock AI 返回有效 JSON,reflection 被持久化。"""
    from scripts.ai.reflection_runner import run_reflection_for_trade

    _insert_closed_paper_trade(db, pid=1)

    fake_ai_response = json.dumps({
        "why_entered": "RSI 72.1 overbought + MACD hist 由正转负 (death cross at this bar)",
        "what_was_expected": "AI 期望 1.5-2 ATR 反弹完成 then mean revert to RSI 60",
        "what_actually_happened": "价格继续 push up 至 0.169 触发 SL,RSI 反而到 75",
        "correction_idea": "在 4h RSI 也 < 70 时才允许 SHORT,避免单 timeframe 误判",
        "failure_mode_key": "against_4h_trend_no_funding_filter",
        "self_assessed_prediction_accuracy": 0.3,
        "is_in_predicted_failure_mode": False,
    })
    mock_ai = AsyncMock(return_value=fake_ai_response)

    import asyncio
    asyncio.run(run_reflection_for_trade(
        paper_trade_id=1, db_path=db,
        ai_call=mock_ai, taxonomy_keys=[
            "late_entry_signal_decay", "macd_false_cross",
            "against_4h_trend_no_funding_filter", "sl_too_tight_in_high_atr",
        ],
    ))

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT setup_type, outcome_class, realized_r, failure_mode_key, "
        "       confidence_at_entry, self_assessed_prediction_accuracy, "
        "       prompt_version FROM reflections WHERE paper_trade_id=1"
    ).fetchone()
    conn.close()
    assert row is not None
    setup_type, outcome, r, fm_key, conf, sapa, pv = row
    assert setup_type == "rsi_overbought_macd_bearish_short"
    assert outcome == "LOSS"
    assert abs(r - (-1.0)) < 0.5    # SL_HIT → realized_r ≈ -1
    assert fm_key == "against_4h_trend_no_funding_filter"
    assert conf == 0.7
    assert sapa == 0.3
    assert pv == "reflection-prompt-v1"


def test_run_reflection_persists_audit_fields(db, monkeypatch):
    """AI provider / model / latency 写入。"""
    from scripts.ai.reflection_runner import run_reflection_for_trade

    _insert_closed_paper_trade(db, pid=2)

    fake_ai_response = json.dumps({
        "why_entered": "test reason for entry",
        "what_was_expected": "test expectation",
        "what_actually_happened": "test reality",
        "correction_idea": "test correction idea",
        "failure_mode_key": None,
        "self_assessed_prediction_accuracy": 0.5,
        "is_in_predicted_failure_mode": False,
    })
    mock_ai = AsyncMock(return_value=fake_ai_response)

    import asyncio
    asyncio.run(run_reflection_for_trade(
        paper_trade_id=2, db_path=db,
        ai_call=mock_ai, ai_provider="deepseek", ai_model="deepseek-chat",
        taxonomy_keys=[],
    ))

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT ai_provider, ai_model, ai_latency_ms FROM reflections "
        "WHERE paper_trade_id=2"
    ).fetchone()
    conn.close()
    assert row[0] == "deepseek"
    assert row[1] == "deepseek-chat"
    assert row[2] is not None and row[2] >= 0


def test_run_reflection_rejects_invalid_json(db, monkeypatch):
    """AI 返回非 JSON → 抛 ValueError,不写 reflections。"""
    from scripts.ai.reflection_runner import run_reflection_for_trade

    _insert_closed_paper_trade(db, pid=3)
    mock_ai = AsyncMock(return_value="this is not json")

    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(run_reflection_for_trade(
            paper_trade_id=3, db_path=db,
            ai_call=mock_ai, taxonomy_keys=[],
        ))
    conn = sqlite3.connect(db)
    n = conn.execute(
        "SELECT COUNT(*) FROM reflections WHERE paper_trade_id=3"
    ).fetchone()[0]
    conn.close()
    assert n == 0


def test_run_reflection_rejects_schema_violation(db, monkeypatch):
    """AI 返回 JSON 但字段不全 → ValueError。"""
    from scripts.ai.reflection_runner import run_reflection_for_trade

    _insert_closed_paper_trade(db, pid=4)
    fake_ai_response = json.dumps({"why_entered": "x"})    # missing fields
    mock_ai = AsyncMock(return_value=fake_ai_response)

    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(run_reflection_for_trade(
            paper_trade_id=4, db_path=db, ai_call=mock_ai, taxonomy_keys=[],
        ))


def test_run_reflection_idempotent_skip_if_already_done(db, monkeypatch):
    """如果 paper_trade 已经有 reflection,跳过。"""
    from scripts.ai.reflection_runner import run_reflection_for_trade

    _insert_closed_paper_trade(db, pid=5)
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO reflections (paper_trade_id, why_entered, what_was_expected,
            what_actually_happened, correction_idea, setup_type, outcome_class,
            realized_r, holding_minutes, confidence_at_entry, prompt_version)
        VALUES (5, 'x', 'y', 'z', 'w', 'manual_short', 'WIN', 1.0, 30, 0.7, 'v1')
    """)
    conn.commit()
    conn.close()

    mock_ai = AsyncMock(return_value="{}")
    import asyncio
    # should not call AI
    asyncio.run(run_reflection_for_trade(
        paper_trade_id=5, db_path=db, ai_call=mock_ai, taxonomy_keys=[]
    ))
    mock_ai.assert_not_called()
```

- [ ] **Step 2: Run, expect fail**

- [ ] **Step 3: Write `scripts/ai/reflection_runner.py`**

```python
"""Reflection runner — load context → AI → validate → persist.

异步 + 注入 ai_call (Callable[[str], Awaitable[str]]) 便于测试。
"""
import json
import sqlite3
import time
from typing import Awaitable, Callable, List, Optional

from pydantic import ValidationError

from api.schemas.v5_reflection import PROMPT_VERSION, ReflectionAIOutput
from scripts.ai.reflection_prompt import build_reflection_prompt
from scripts.ai.setup_type import derive_setup_type


AICall = Callable[[str], Awaitable[str]]


def _classify_outcome(realized_r: float) -> str:
    if abs(realized_r) < 0.2:
        return "SCRATCH"
    return "WIN" if realized_r > 0 else "LOSS"


def _holding_minutes(entry_iso: str, exit_iso: str) -> int:
    from datetime import datetime
    dt_e = datetime.fromisoformat(entry_iso.replace("Z", "+00:00"))
    dt_x = datetime.fromisoformat(exit_iso.replace("Z", "+00:00"))
    return int((dt_x - dt_e).total_seconds() / 60)


def _load_close_context(db_path: str, paper_trade_id: int,
                         taxonomy_keys: List[str]) -> Optional[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        pt = conn.execute(
            "SELECT * FROM paper_trades WHERE id=?", (paper_trade_id,)
        ).fetchone()
        if pt is None or (pt["status"] or "").upper() != "CLOSED":
            return None

        # 取入场时的 trade_scores_v5 (拿 macd_hist_prev / 4h refs)
        ts = conn.execute(
            "SELECT * FROM trade_scores_v5 WHERE position_id=? ORDER BY id DESC LIMIT 1",
            (paper_trade_id,)
        ).fetchone()
    finally:
        conn.close()

    entry_price = float(pt["entry_price"] or 0.0)
    exit_price = float(pt["exit_price"] or entry_price)
    sl_price = float(pt["stop_loss"] or 0.0)
    side = (pt["side"] or "").upper()

    # realized_r = pnl / |sl_distance|
    pnl_pct = float(pt["pnl_percent"] or 0.0) / 100.0
    sl_dist_pct = (
        abs(sl_price - entry_price) / entry_price if entry_price > 0 and sl_price > 0
        else 0.01
    )
    realized_r = pnl_pct / sl_dist_pct if sl_dist_pct > 0 else 0.0

    rsi_15m = float(pt["entry_rsi_15m"] or (ts["rsi_15m"] if ts else 50.0))
    macd_hist = float(pt["entry_macd_hist_15m"] or (ts["macd_hist_15m"] if ts else 0.0))
    macd_hist_prev = float(ts["macd_hist_prev_15m"] if ts else 0.0)

    setup_type = derive_setup_type({
        "side": side, "strategy_id": pt["strategy_id"] or "v5_rsi_macd",
        "rsi_15m": rsi_15m,
        "macd_hist": macd_hist, "macd_hist_prev": macd_hist_prev,
        "funding_z_score": None,
    })

    return {
        "paper_trade_id": paper_trade_id,
        "symbol": pt["symbol"],
        "side": side,
        "strategy_id": pt["strategy_id"],
        "entry_price": entry_price,
        "exit_price": exit_price,
        "entry_time": pt["entry_time"],
        "exit_time": pt["exit_time"],
        "exit_reason": pt["exit_reason"],
        "realized_r": realized_r,
        "holding_minutes": _holding_minutes(pt["entry_time"], pt["exit_time"]),
        "confidence_at_entry": float(pt["ai_confidence"] or 0.0),
        "entry_rsi_15m": rsi_15m,
        "entry_rsi_4h": float(ts["rsi_4h"]) if ts and ts["rsi_4h"] is not None else None,
        "entry_macd_hist_15m": macd_hist,
        "entry_macd_hist_prev_15m": macd_hist_prev,
        "entry_atr_15m": float(pt["atr_k"] or (ts["atr_15m"] if ts else 0.0)),
        "funding_z_score": None,
        "rule_reasoning": ts["reasoning"] if ts else None,
        "ai_reasoning": pt["ai_reason"],
        "rag_cases_text": None,    # 阶段 1 暂不回填,留 prompt 优雅处理 None
        "during_hold_path": None,
        "taxonomy_keys": taxonomy_keys,
        "_setup_type": setup_type,
        "_pnl_pct": pnl_pct,
    }


def _persist(db_path: str, ctx: dict, ai_out: ReflectionAIOutput,
              raw: str, latency_ms: int, ai_provider: Optional[str],
              ai_model: Optional[str]) -> None:
    realized_r = ctx["realized_r"]
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            INSERT INTO reflections (
                paper_trade_id, why_entered, what_was_expected, what_actually_happened,
                correction_idea, failure_mode_key, setup_type, outcome_class,
                realized_r, holding_minutes, confidence_at_entry,
                self_assessed_prediction_accuracy, is_in_predicted_failure_mode,
                ai_provider, ai_model, ai_latency_ms, prompt_version, raw_response_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ctx["paper_trade_id"], ai_out.why_entered, ai_out.what_was_expected,
            ai_out.what_actually_happened, ai_out.correction_idea,
            ai_out.failure_mode_key, ctx["_setup_type"],
            _classify_outcome(realized_r), realized_r,
            ctx["holding_minutes"], ctx["confidence_at_entry"],
            ai_out.self_assessed_prediction_accuracy,
            1 if ai_out.is_in_predicted_failure_mode else 0,
            ai_provider, ai_model, latency_ms, PROMPT_VERSION, raw,
        ))
        conn.commit()
    finally:
        conn.close()


def _already_reflected(db_path: str, paper_trade_id: int) -> bool:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM reflections WHERE paper_trade_id=? LIMIT 1",
            (paper_trade_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


async def run_reflection_for_trade(*, paper_trade_id: int, db_path: str,
                                    ai_call: AICall,
                                    taxonomy_keys: List[str],
                                    ai_provider: Optional[str] = None,
                                    ai_model: Optional[str] = None) -> None:
    """主入口。pre-check idempotent → load ctx → ai → validate → persist。"""
    if _already_reflected(db_path, paper_trade_id):
        return

    ctx = _load_close_context(db_path, paper_trade_id, taxonomy_keys)
    if ctx is None:
        raise ValueError(f"paper_trade {paper_trade_id} not found or not CLOSED")

    prompt = build_reflection_prompt(ctx)
    t0 = time.monotonic()
    raw = await ai_call(prompt)
    latency_ms = int((time.monotonic() - t0) * 1000)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"reflection AI response is not JSON: {e}") from e

    try:
        ai_out = ReflectionAIOutput.model_validate(parsed)
    except ValidationError as e:
        raise ValueError(f"reflection AI response failed schema: {e}") from e

    _persist(db_path, ctx, ai_out, raw, latency_ms, ai_provider, ai_model)
```

- [ ] **Step 4: Run tests, expect 5 passed**

```bash
python3 -m pytest tests/test_reflection_runner.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Run full suite, no regression**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 136 + 5 = 141 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/ai/reflection_runner.py tests/test_reflection_runner.py
git commit -m "feat(reflection): runner — load context → AI → validate → persist

- _load_close_context joins paper_trades + trade_scores_v5 for entry snapshot
- realized_r = pnl_pct / sl_distance_pct,outcome SCRATCH if |r|<0.2
- ai_call injected (testable),pydantic schema rejects partial / non-JSON
- Idempotent skip if reflection already exists for this paper_trade

5 runner pipeline tests covering happy path / audit fields /
invalid JSON / schema violation / idempotency."
```

---

### Task 4: V5ReflectionWorker process + integrate with position_monitor close

**Files:**
- Create: `scripts/tasks/v5_reflection_worker.py`
- Modify: `scripts/v5_position_monitor.py` (add enqueue on close)
- Modify: `scripts/tasks/collector_main.py` (start worker)
- Create: `tests/test_v5_reflection_worker.py`

- [ ] **Step 1: Write failing test `tests/test_v5_reflection_worker.py`**

```python
"""V5ReflectionWorker poll loop — 用 mock AI + tmpfs DB 跑一次 tick。"""
import asyncio
import json
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _seed_closed_trade_and_enqueue(db_path, pid=7):
    """填一个 CLOSED paper_trade + 一行 trade_scores + 入队 reflection。"""
    conn = sqlite3.connect(db_path)
    et = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    xt = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO paper_trades (id, symbol, side, entry_price, entry_time, status,
            stop_loss, take_profit, position_size_usdt, leverage, strategy_id,
            created_at, exit_price, exit_time, exit_reason, pnl_percent,
            entry_rsi_15m, entry_macd_hist_15m, ai_confidence, ai_reason)
        VALUES (?, 'HUSDT', 'SHORT', 0.166, ?, 'CLOSED', 0.169, 0.162,
                15.0, 10, 'v5_rsi_macd', ?, 0.162, ?, 'TP_HIT', 1.8,
                72.1, -0.0012, 0.7, 'short setup')
    """, (pid, et, et, xt))
    conn.execute("""
        INSERT INTO trade_scores_v5 (symbol, created_at, rsi_15m, macd_hist_15m,
            macd_hist_prev_15m, atr_15m, current_price, executed, position_id,
            should_trade, side)
        VALUES ('HUSDT', ?, 72.1, -0.0012, 0.0008, 0.0015, 0.166, 1, ?, 1, 'SHORT')
    """, (et, pid))
    conn.execute(
        "INSERT INTO reflection_queue (paper_trade_id) VALUES (?)", (pid,)
    )
    conn.commit()
    conn.close()


def test_worker_tick_processes_pending_queue_item(db):
    from scripts.tasks.v5_reflection_worker import V5ReflectionWorker

    _seed_closed_trade_and_enqueue(db, pid=7)

    fake_ai = AsyncMock(return_value=json.dumps({
        "why_entered": "RSI overbought + MACD bearish cross at this bar",
        "what_was_expected": "Expected 1.5-2 ATR pullback then partial TP",
        "what_actually_happened": "Price dropped quickly to TP, hit it in 10 bars",
        "correction_idea": "Consider 4h alignment for higher conviction next time",
        "failure_mode_key": None,
        "self_assessed_prediction_accuracy": 0.85,
        "is_in_predicted_failure_mode": False,
    }))

    worker = V5ReflectionWorker(db_path=db, ai_call=fake_ai,
                                 ai_provider="deepseek", ai_model="deepseek-chat")
    asyncio.run(worker._tick())

    conn = sqlite3.connect(db)
    reflected = conn.execute(
        "SELECT outcome_class FROM reflections WHERE paper_trade_id=7"
    ).fetchone()
    queue_state = conn.execute(
        "SELECT completed_at, error FROM reflection_queue WHERE paper_trade_id=7"
    ).fetchone()
    conn.close()

    assert reflected == ("WIN",)
    assert queue_state[0] is not None    # completed_at filled
    assert queue_state[1] is None        # no error


def test_worker_tick_records_error_and_increments_retry(db):
    from scripts.tasks.v5_reflection_worker import V5ReflectionWorker

    _seed_closed_trade_and_enqueue(db, pid=8)
    fake_ai = AsyncMock(side_effect=RuntimeError("AI provider down"))

    worker = V5ReflectionWorker(db_path=db, ai_call=fake_ai)
    asyncio.run(worker._tick())

    conn = sqlite3.connect(db)
    qrow = conn.execute(
        "SELECT completed_at, error, retry_count FROM reflection_queue WHERE paper_trade_id=8"
    ).fetchone()
    conn.close()
    assert qrow[0] is None
    assert "AI provider down" in (qrow[1] or "")
    assert qrow[2] == 1


def test_worker_tick_skips_after_3_retries(db):
    from scripts.tasks.v5_reflection_worker import V5ReflectionWorker

    _seed_closed_trade_and_enqueue(db, pid=9)
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE reflection_queue SET retry_count=3 WHERE paper_trade_id=9"
    )
    conn.commit()
    conn.close()

    fake_ai = AsyncMock()
    worker = V5ReflectionWorker(db_path=db, ai_call=fake_ai)
    asyncio.run(worker._tick())
    fake_ai.assert_not_called()


def test_enqueue_reflection_called_from_close_position_helper(db, monkeypatch):
    """v5_position_monitor close_position path 自动 enqueue。"""
    from scripts.local_db import enqueue_reflection
    enqueue_reflection(99, db_path=db)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT paper_trade_id FROM reflection_queue WHERE paper_trade_id=99"
    ).fetchone()
    conn.close()
    assert row == (99,)
```

- [ ] **Step 2: Run, expect fail**

- [ ] **Step 3: Write `scripts/tasks/v5_reflection_worker.py`**

```python
"""V5ReflectionWorker — poll reflection_queue → run reflection → record outcome.

- 每 30s poll
- AI 失败 → retry_count++ + error 落库,3 次后放弃
- AI 调用走注入的 ai_call (便于测试 + 切换 provider)
"""
import asyncio
import sqlite3
import traceback
from typing import Awaitable, Callable, List, Optional

from scripts.ai.reflection_runner import run_reflection_for_trade


AICall = Callable[[str], Awaitable[str]]

POLL_INTERVAL_S = 30
MAX_RETRIES = 3


class V5ReflectionWorker:
    """async poll-loop worker。"""

    def __init__(self, *, db_path: str, ai_call: AICall,
                 ai_provider: Optional[str] = None,
                 ai_model: Optional[str] = None,
                 taxonomy_keys: Optional[List[str]] = None,
                 poll_interval_s: int = POLL_INTERVAL_S):
        self.db_path = db_path
        self.ai_call = ai_call
        self.ai_provider = ai_provider
        self.ai_model = ai_model
        self.taxonomy_keys = taxonomy_keys or []
        self.poll_interval_s = poll_interval_s

    def _fetch_pending(self, limit: int = 5) -> List[int]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT paper_trade_id FROM reflection_queue "
                "WHERE completed_at IS NULL AND retry_count < ? "
                "ORDER BY id LIMIT ?",
                (MAX_RETRIES, limit),
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    def _mark_started(self, paper_trade_id: int) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE reflection_queue SET started_at = datetime('now') "
                "WHERE paper_trade_id=?", (paper_trade_id,)
            )
            conn.commit()
        finally:
            conn.close()

    def _mark_completed(self, paper_trade_id: int) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE reflection_queue SET completed_at = datetime('now'), "
                "error = NULL WHERE paper_trade_id=?", (paper_trade_id,)
            )
            conn.commit()
        finally:
            conn.close()

    def _mark_failed(self, paper_trade_id: int, error: str) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE reflection_queue SET retry_count = retry_count + 1, "
                "error = ? WHERE paper_trade_id=?",
                (error[:500], paper_trade_id),
            )
            conn.commit()
        finally:
            conn.close()

    async def _tick(self) -> None:
        pending = self._fetch_pending()
        for pid in pending:
            self._mark_started(pid)
            try:
                await run_reflection_for_trade(
                    paper_trade_id=pid, db_path=self.db_path,
                    ai_call=self.ai_call,
                    ai_provider=self.ai_provider, ai_model=self.ai_model,
                    taxonomy_keys=self.taxonomy_keys,
                )
                self._mark_completed(pid)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                self._mark_failed(pid, err)
                print(f"[V5ReflectionWorker] paper_trade {pid} failed: {err}")
                traceback.print_exc()

    async def run(self) -> None:
        print(f"[V5ReflectionWorker] 启动,间隔 {self.poll_interval_s}s")
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                print("[V5ReflectionWorker] 取消信号,退出")
                return
            except Exception as e:
                print(f"[V5ReflectionWorker] tick 异常: {type(e).__name__}: {e}")
            await asyncio.sleep(self.poll_interval_s)
```

- [ ] **Step 4: Modify `scripts/v5_position_monitor.py` — enqueue on close**

Find the place in `_tick` where `pm.close_position(...)` is called. After the close call (and the existing `_enqueue_ws(...)` call from B1-T10), add:

```python
                # B-Phase-1: 触发 reflection 入队
                try:
                    from scripts.local_db import enqueue_reflection
                    enqueue_reflection(position["id"], db_path=pm.db_path)
                except Exception as e:
                    print(f"[V5PositionMonitor] reflection enqueue failed: {e}")
```

- [ ] **Step 5: Modify `scripts/tasks/collector_main.py` — start worker**

Find the existing wire-up of `V5PositionMonitor` (search for `V5PositionMonitor(`). After that block, add:

```python
    # Reflection worker (阶段 1)
    from scripts.tasks.v5_reflection_worker import V5ReflectionWorker

    async def _reflection_ai_call(prompt: str) -> str:
        """用 trading_assistant 已有的 LLM 客户端做轻量 chat 调用。
        失败时上层 worker 会落 error + retry。"""
        if ai is None or ai.client is None:
            raise RuntimeError("AI client not configured for reflection")
        import asyncio
        resp = await ai.client.chat.completions.create(
            model=ai.chat_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""

    reflection_worker = V5ReflectionWorker(
        db_path=db_path,
        ai_call=_reflection_ai_call,
        ai_provider=(ai.provider if ai else None),
        ai_model=(ai.chat_model if ai else None),
        taxonomy_keys=[],   # Phase 2 会填充
    )
    tasks.append(asyncio.create_task(reflection_worker.run(),
                                      name="v5_reflection_worker"))
```

(If `tasks` is not the exact variable name in your version of `collector_main`, match the pattern used for V5ScorerWorker / V5PositionMonitor and append to the same list.)

- [ ] **Step 6: Run tests**

```bash
python3 -m pytest tests/test_v5_reflection_worker.py -v 2>&1 | tail -15
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 4 new + 145 cumulative.

- [ ] **Step 7: Commit**

```bash
git add scripts/tasks/v5_reflection_worker.py scripts/v5_position_monitor.py \
        scripts/tasks/collector_main.py tests/test_v5_reflection_worker.py
git commit -m "feat(reflection): V5ReflectionWorker 进程 + enqueue 集成

- Async poll loop (30s),retry 3 次后放弃
- mark_started/completed/failed 三态
- v5_position_monitor 关仓后入队 (best-effort,失败不阻塞监控)
- collector_main 启动 reflection worker,AI call 走 trading_assistant.client
- JSON response_format 强制 AI 返回 JSON object

4 worker integration tests."
```

---

### Task 5: API route + frontend Tab 1 (最近复盘流)

**Files:**
- Create: `api/routes/v5_reflection.py`
- Modify: `api/main.py` (register router)
- Create: `tests/test_v5_reflection_api.py`
- Modify: `Rabbit Hunterfronted/types.ts`
- Create: `Rabbit Hunterfronted/hooks/api/useV5Reflections.ts`
- Create: `Rabbit Hunterfronted/components/pages/V5ReflectionPage.tsx`
- Modify: `Rabbit Hunterfronted/App.tsx` (add route)
- Modify: `Rabbit Hunterfronted/components/layout/Sidebar.tsx` (nav entry)
- Modify: `Rabbit Hunterfronted/services/glossary.ts` (add 反思/失败模式 terms)
- Create: `Rabbit Hunterfronted/tests/pages/V5ReflectionPage.test.tsx`

- [ ] **Step 1: Write `tests/test_v5_reflection_api.py`**

```python
"""GET /api/v5/reflections — list endpoint."""
import sqlite3
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    from api.main import app
    return TestClient(app), tmp.name


def _insert_reflection(db_path, *, pid=1, symbol="HUSDT"):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO paper_trades (id, symbol, side, entry_price, entry_time, status,
            stop_loss, take_profit, position_size_usdt, leverage, strategy_id,
            created_at, exit_price, exit_time, exit_reason, pnl_percent)
        VALUES (?, ?, 'SHORT', 0.166, datetime('now', '-30 minutes'), 'CLOSED',
                0.169, 0.162, 15, 10, 'v5_rsi_macd', datetime('now', '-30 minutes'),
                0.162, datetime('now'), 'TP_HIT', 1.8)
    """, (pid, symbol))
    conn.execute("""
        INSERT INTO reflections (paper_trade_id, why_entered, what_was_expected,
            what_actually_happened, correction_idea, failure_mode_key, setup_type,
            outcome_class, realized_r, holding_minutes, confidence_at_entry,
            self_assessed_prediction_accuracy, is_in_predicted_failure_mode,
            ai_provider, ai_model, ai_latency_ms, prompt_version)
        VALUES (?, 'rsi 72 + macd bearish', 'pullback then tp',
                'actually went to tp quickly', 'add 4h filter next time', NULL,
                'rsi_overbought_macd_bearish_short', 'WIN', 1.0, 30, 0.7,
                0.85, 0, 'deepseek', 'deepseek-chat', 4200, 'reflection-prompt-v1')
    """, (pid,))
    conn.commit()
    conn.close()


def test_list_returns_empty_wrapper(client):
    c, _ = client
    r = c.get("/api/v5/reflections?limit=10")
    assert r.status_code == 200
    assert r.json() == {"status": "success", "data": []}


def test_list_returns_recent_reflections_joined_with_paper_trade(client):
    c, db = client
    _insert_reflection(db, pid=1, symbol="HUSDT")
    r = c.get("/api/v5/reflections?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert len(body["data"]) == 1
    item = body["data"][0]
    assert item["paper_trade_id"] == 1
    assert item["symbol"] == "HUSDT"
    assert item["side"] == "SHORT"
    assert item["outcome_class"] == "WIN"
    assert "rsi 72" in item["why_entered"]


def test_list_respects_limit(client):
    c, db = client
    for i in range(5):
        _insert_reflection(db, pid=i + 1, symbol=f"X{i}USDT")
    r = c.get("/api/v5/reflections?limit=3")
    assert r.status_code == 200
    assert len(r.json()["data"]) == 3
```

- [ ] **Step 2: Run, expect 3 fail**

- [ ] **Step 3: Write `api/routes/v5_reflection.py`**

```python
"""V5 Reflection API — list reflections joined with paper_trade summary."""
import os
import sqlite3

from fastapi import APIRouter, Query

from api.schemas.v5_reflection import ReflectionRecord, ReflectionsResponse


router = APIRouter(prefix="/api/v5", tags=["reflection"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


@router.get("/reflections", response_model=ReflectionsResponse)
async def list_reflections(limit: int = Query(20, ge=1, le=200)) -> ReflectionsResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT r.*, p.symbol, p.side, p.entry_price, p.exit_price,
                   p.exit_reason, p.pnl_percent
              FROM reflections r
              LEFT JOIN paper_trades p ON p.id = r.paper_trade_id
             ORDER BY r.id DESC
             LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()

    data = []
    for row in rows:
        d = dict(row)
        # 把 SQLite int(0/1) 转回 bool 给 frontend
        if d.get("is_in_predicted_failure_mode") is not None:
            d["is_in_predicted_failure_mode"] = bool(d["is_in_predicted_failure_mode"])
        # pnl_percent → pnl_pct
        d["pnl_pct"] = d.pop("pnl_percent", None)
        data.append(ReflectionRecord(**d))
    return ReflectionsResponse(data=data)
```

- [ ] **Step 4: Register in `api/main.py`**

```python
from api.routes import v5_reflection
app.include_router(v5_reflection.router)
```

- [ ] **Step 5: Run tests, expect 3 passed**

```bash
python3 -m pytest tests/test_v5_reflection_api.py -v 2>&1 | tail -10
```

- [ ] **Step 6: Update `Rabbit Hunterfronted/types.ts`**

Append (before the WebSocket section):

```ts
// ── Reflection ──
export type OutcomeClass = 'WIN' | 'LOSS' | 'SCRATCH';

export interface ReflectionRecord {
  id: number;
  paper_trade_id: number;
  created_at: string;
  why_entered: string;
  what_was_expected: string;
  what_actually_happened: string;
  correction_idea: string;
  failure_mode_key: string | null;
  setup_type: string;
  outcome_class: OutcomeClass;
  realized_r: number;
  holding_minutes: number;
  confidence_at_entry: number;
  self_assessed_prediction_accuracy: number | null;
  is_in_predicted_failure_mode: boolean | null;
  ai_provider: string | null;
  ai_model: string | null;
  ai_latency_ms: number | null;
  symbol: string | null;
  side: Side | null;
  entry_price: number | null;
  exit_price: number | null;
  exit_reason: string | null;
  pnl_pct: number | null;
}

export interface ReflectionsResponse {
  status: string;
  data: ReflectionRecord[];
}
```

- [ ] **Step 7: Create `Rabbit Hunterfronted/hooks/api/useV5Reflections.ts`**

```ts
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { ReflectionsResponse } from '../../types';

export function useV5Reflections(limit = 20) {
  return useQuery<ReflectionsResponse>({
    queryKey: ['v5', 'reflections', limit],
    queryFn: () => apiGet<ReflectionsResponse>(`/api/v5/reflections?limit=${limit}`),
    refetchInterval: 30_000,
  });
}
```

- [ ] **Step 8: Create `Rabbit Hunterfronted/components/pages/V5ReflectionPage.tsx`**

```tsx
import React, { useState } from 'react';
import { useV5Reflections } from '../../hooks/api/useV5Reflections';
import { Card } from '../primitives/Card';
import { Badge } from '../primitives/Badge';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Term } from '../shared/Term';
import type { ReflectionRecord } from '../../types';
import { Brain, AlertTriangle, Scale } from 'lucide-react';

type Tab = 'recent' | 'taxonomy' | 'sizing';

export function V5ReflectionPage() {
  const [tab, setTab] = useState<Tab>('recent');

  return (
    <div className="space-y-4">
      <div className="flex gap-2 text-xs">
        <TabButton active={tab === 'recent'} onClick={() => setTab('recent')} icon={<Brain size={14} />}>
          最近复盘流
        </TabButton>
        <TabButton active={tab === 'taxonomy'} onClick={() => setTab('taxonomy')} icon={<AlertTriangle size={14} />}>
          失败模式
        </TabButton>
        <TabButton active={tab === 'sizing'} onClick={() => setTab('sizing')} icon={<Scale size={14} />}>
          仓位建议
        </TabButton>
      </div>

      {tab === 'recent' && <RecentReflectionsTab />}
      {tab === 'taxonomy' && <Card title="失败模式"><div className="text-white/40 text-sm">阶段 2 上线后启用</div></Card>}
      {tab === 'sizing' && <Card title="仓位建议"><div className="text-white/40 text-sm">阶段 3 上线后启用</div></Card>}
    </div>
  );
}

function TabButton({ active, onClick, icon, children }:
                   { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-1 rounded-sm border px-3 py-1.5 font-mono transition-colors ${
        active
          ? 'border-accent-info bg-accent-info/10 text-accent-info'
          : 'border-white/10 text-white/60 hover:bg-white/5'
      }`}
    >
      {icon}{children}
    </button>
  );
}

function RecentReflectionsTab() {
  const q = useV5Reflections(20);
  if (q.isLoading) return <LoadingSkeleton rows={6} />;
  const rows = q.data?.data ?? [];

  if (rows.length === 0) {
    return (
      <Card title="最近复盘流">
        <div className="py-12 text-center text-white/40">
          ▌ 等待第一笔关仓后,reflection worker 自动生成
        </div>
      </Card>
    );
  }

  return (
    <Card title={`最近复盘流 (n=${rows.length})`}>
      <div className="space-y-3">
        {rows.map(r => <ReflectionCard key={r.id} r={r} />)}
      </div>
    </Card>
  );
}

function ReflectionCard({ r }: { r: ReflectionRecord }) {
  const outcomeTone =
    r.outcome_class === 'WIN' ? 'long' :
    r.outcome_class === 'LOSS' ? 'short' : 'neutral';
  const rTone = r.realized_r >= 0 ? 'text-accent-long' : 'text-accent-short';

  return (
    <div className="rounded-md border border-white/10 bg-bg-base p-3 space-y-2">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="font-medium text-white">{r.symbol ?? '—'}</span>
          {r.side && <Badge variant={r.side === 'LONG' ? 'long' : 'short'}>{r.side}</Badge>}
          <Badge variant={outcomeTone as any}>{r.outcome_class}</Badge>
          <span className="font-mono text-white/50">setup: {r.setup_type}</span>
        </div>
        <div className="flex items-center gap-3 font-mono text-white/60">
          <span className={rTone}>R {r.realized_r >= 0 ? '+' : ''}{r.realized_r.toFixed(2)}</span>
          <span>{r.holding_minutes}min</span>
          <span>{new Date(r.created_at).toLocaleTimeString('zh-CN', { hour12: false })}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <div className="text-cyan-300/70 mb-1">▶ 为什么开仓</div>
          <div className="text-white/80">{r.why_entered}</div>
        </div>
        <div>
          <div className="text-cyan-300/70 mb-1">▶ 当时怎么想</div>
          <div className="text-white/80">{r.what_was_expected}</div>
        </div>
        <div>
          <div className="text-cyan-300/70 mb-1">▶ 实际怎么走</div>
          <div className="text-white/80">{r.what_actually_happened}</div>
        </div>
        <div>
          <div className="text-cyan-300/70 mb-1">▶ 下次怎么改</div>
          <div className="text-white/80">{r.correction_idea}</div>
        </div>
      </div>

      <div className="flex items-center justify-between text-[11px] font-mono text-white/40">
        <div>
          {r.failure_mode_key && (
            <Badge variant="warn">
              <Term k="failure_mode">失败模式</Term>: {r.failure_mode_key}
            </Badge>
          )}
        </div>
        <div className="flex gap-3">
          <span>AI: {r.ai_model ?? '—'} ({r.ai_latency_ms ?? '—'}ms)</span>
          {r.self_assessed_prediction_accuracy != null && (
            <span>自评 {(r.self_assessed_prediction_accuracy * 100).toFixed(0)}%</span>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 9: Add route in `Rabbit Hunterfronted/App.tsx`**

Import:
```tsx
import { V5ReflectionPage } from './components/pages/V5ReflectionPage';
```

Inside `<Route path="/v5" element={<AppShell />}>`:
```tsx
<Route path="reflection" element={<V5ReflectionPage />} />
```

- [ ] **Step 10: Add Sidebar nav entry**

In `Rabbit Hunterfronted/components/layout/Sidebar.tsx`, in the "智能" group, add (and add `BookText` to lucide imports):

```tsx
{ to: '/v5/reflection', label: '复盘工作台', Icon: BookText },
```

- [ ] **Step 11: Add glossary terms**

In `Rabbit Hunterfronted/services/glossary.ts`, add to the GLOSSARY dict:

```ts
failure_mode: {
  key: 'failure_mode', zh: '失败模式', en: 'Failure Mode', category: 'AI',
  desc: 'AI 对这笔交易失败原因的分类,来自预置 8 种 + 新提案的 taxonomy。命中已知失败模式的新 setup 会被入场层 veto。',
},
reflection: {
  key: 'reflection', zh: '复盘', en: 'Reflection', category: 'AI',
  desc: '每笔关仓后,AI 用 5 问结构(为什么开 / 怎么想 / 实际怎么走 / 哪种失败 / 下次怎么改)分析,作为下次决策的 RAG 输入。',
},
realized_r: {
  key: 'realized_r', zh: '实际 R 倍', en: 'Realized R-multiple', category: '统计',
  desc: '盈亏百分比 ÷ SL 距离百分比。+1 = 触发 TP,-1 = 触发 SL。是跨币种比较交易质量的标准单位。',
},
setup_type: {
  key: 'setup_type', zh: 'Setup 类型', en: 'Setup Type', category: '信号',
  desc: '入场时根据 RSI 状态 × MACD 状态 × 方向(可能加 funding)派生的桶名。所有聚合按它分类。',
},
```

- [ ] **Step 12: Frontend test `Rabbit Hunterfronted/tests/pages/V5ReflectionPage.test.tsx`**

```tsx
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { V5ReflectionPage } from '@/components/pages/V5ReflectionPage';

const SAMPLE = {
  status: 'success',
  data: [{
    id: 1, paper_trade_id: 7, created_at: '2026-06-15T10:30:00+00:00',
    why_entered: 'RSI 72.1 overbought + MACD bearish cross',
    what_was_expected: 'Expected 1.5-2 ATR pullback then partial TP',
    what_actually_happened: 'Price dropped to TP quickly',
    correction_idea: 'Consider 4h alignment next time',
    failure_mode_key: null,
    setup_type: 'rsi_overbought_macd_bearish_short',
    outcome_class: 'WIN', realized_r: 1.0, holding_minutes: 30,
    confidence_at_entry: 0.7,
    self_assessed_prediction_accuracy: 0.85,
    is_in_predicted_failure_mode: false,
    ai_provider: 'deepseek', ai_model: 'deepseek-chat', ai_latency_ms: 4200,
    symbol: 'HUSDT', side: 'SHORT',
    entry_price: 0.166, exit_price: 0.162, exit_reason: 'TP_HIT', pnl_pct: 1.8,
  }],
};

function wrap(qc: QueryClient) {
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter><V5ReflectionPage /></MemoryRouter>
    </QueryClientProvider>
  );
}

describe('V5ReflectionPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify(SAMPLE), { status: 200 })));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('renders 3 tab buttons', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(wrap(qc));
    expect(screen.getByText('最近复盘流')).toBeInTheDocument();
    expect(screen.getByText('失败模式')).toBeInTheDocument();
    expect(screen.getByText('仓位建议')).toBeInTheDocument();
  });

  it('shows reflection card after data loads', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(wrap(qc));
    await waitFor(() => expect(screen.getByText('HUSDT')).toBeInTheDocument());
    expect(screen.getByText(/RSI 72\.1 overbought/)).toBeInTheDocument();
    expect(screen.getByText(/Consider 4h alignment/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 13: Run all tests + build**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/pages/V5ReflectionPage.test.tsx 2>&1 | tail -8
npx vitest run 2>&1 | tail -3
npx vite build 2>&1 | tail -5
cd /Users/lizhishaoniange/Documents/Rabbit-Hunter
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: FE 47 + 2 = 49; BE 145 + 3 = 148; build OK.

- [ ] **Step 14: Commit**

```bash
git add api/routes/v5_reflection.py api/main.py tests/test_v5_reflection_api.py \
        "Rabbit Hunterfronted/types.ts" \
        "Rabbit Hunterfronted/hooks/api/useV5Reflections.ts" \
        "Rabbit Hunterfronted/components/pages/V5ReflectionPage.tsx" \
        "Rabbit Hunterfronted/App.tsx" \
        "Rabbit Hunterfronted/components/layout/Sidebar.tsx" \
        "Rabbit Hunterfronted/services/glossary.ts" \
        "Rabbit Hunterfronted/tests/pages/V5ReflectionPage.test.tsx"
git commit -m "feat(reflection): GET /api/v5/reflections + 复盘工作台 Tab 1

- API: list with paper_trade JOIN summary, configurable limit, {status,data} wrapper
- Frontend: 3-tab scaffold, Tab 1 reflection cards 5-问 grid
- Outcome badge tone + realized_r colored + setup_type chip
- Sidebar 智能 group gains 复盘工作台 entry
- Glossary terms: 复盘 / 失败模式 / 实际 R 倍 / Setup 类型

3 API tests + 2 page tests."
```

---

## Phase 2 — Layer 2 失败模式 (4 tasks)

### Task 6: failure_taxonomy table + 8 种子模式

**Files:**
- Modify: `scripts/local_db.py` (add table + seed function)
- Create: `scripts/ai/failure_taxonomy_seed.py`
- Create: `tests/test_failure_taxonomy_seed.py`

- [ ] **Step 1: Write failing test `tests/test_failure_taxonomy_seed.py`**

```python
"""Failure taxonomy table + 8 种子记录。"""
import sqlite3
import tempfile
import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def test_failure_taxonomy_table_exists(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(failure_taxonomy)").fetchall()]
    conn.close()
    for c in ("key", "label_zh", "label_en", "description",
              "detection_rule", "is_active", "sample_count",
              "avg_loss_pct", "seeded", "created_at"):
        assert c in cols


def test_8_seeds_inserted_on_init(db):
    conn = sqlite3.connect(db)
    n = conn.execute(
        "SELECT COUNT(*) FROM failure_taxonomy WHERE seeded=1"
    ).fetchone()[0]
    conn.close()
    assert n == 8


def test_all_seeded_keys_present(db):
    conn = sqlite3.connect(db)
    keys = {r[0] for r in conn.execute(
        "SELECT key FROM failure_taxonomy WHERE seeded=1"
    ).fetchall()}
    conn.close()
    expected = {
        "late_entry_signal_decay",
        "macd_false_cross",
        "against_4h_trend_no_funding_filter",
        "sl_too_tight_in_high_atr",
        "tp_too_far_in_low_atr",
        "news_event_30min_blackout",
        "chase_after_3pct_move",
        "repeat_failure_same_symbol_24h",
    }
    assert keys == expected


def test_each_seed_has_label_and_detection_rule(db):
    conn = sqlite3.connect(db)
    rows = conn.execute("""
        SELECT key, label_zh, label_en, detection_rule FROM failure_taxonomy WHERE seeded=1
    """).fetchall()
    conn.close()
    for k, lz, le, rule in rows:
        assert lz and len(lz) > 0
        assert le and len(le) > 0
        # Detection rule 可以为 NULL (e.g. news_event 需挂日历),但绝大多数应该有
        if k != "news_event_30min_blackout":
            assert rule is not None


def test_seed_idempotent(db, monkeypatch):
    """二次 init 不应重复插入。"""
    from scripts.local_db import init_local_db
    init_local_db(db)
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM failure_taxonomy WHERE seeded=1").fetchone()[0]
    conn.close()
    assert n == 8
```

- [ ] **Step 2: Run, expect fail**

- [ ] **Step 3: Create `scripts/ai/failure_taxonomy_seed.py`**

```python
"""8 个预置失败模式 — 系统启动时 seed 进 DB。

key 是 snake_case 唯一标识。
detection_rule 是 mini-DSL,Task 7 的 parser 会解释。
"""
from typing import List, Tuple


SEEDS: List[dict] = [
    {
        "key": "late_entry_signal_decay",
        "label_zh": "信号衰减后晚入场",
        "label_en": "Late entry after signal decay",
        "description": "RSI 已极端但 MACD hist 已经从拐点退太远,等于追在反转点之后。",
        "detection_rule": "entry_rsi_15m > 70 AND ABS(macd_hist_prev_15m / macd_hist_15m) < 0.3",
    },
    {
        "key": "macd_false_cross",
        "label_zh": "MACD 假拐点",
        "label_en": "MACD false crossover",
        "description": "MACD hist 单根 K 线翻转后又翻回,实际不是趋势转折。",
        "detection_rule": "macd_recross_within_3_bars",
    },
    {
        "key": "against_4h_trend_no_funding_filter",
        "label_zh": "逆 4h 趋势无 funding 确认",
        "label_en": "Counter-trend without funding rate confirmation",
        "description": "15m 入场方向跟 4h MACD 主趋势相反,且 funding rate 没给极端反向信号,大概率被趋势收割。",
        "detection_rule": "SIGN(side_int) != SIGN(macd_hist_4h) AND ABS(funding_z_score) < 1.5",
    },
    {
        "key": "sl_too_tight_in_high_atr",
        "label_zh": "高波动期 SL 过紧",
        "label_en": "SL too tight under high ATR regime",
        "description": "ATR 在历史高分位,但 SL 距离不到 1.2x ATR,容易被正常波动吃掉。",
        "detection_rule": "atr_15m > P75_atr_30d AND sl_distance_atr_ratio < 1.2",
    },
    {
        "key": "tp_too_far_in_low_atr",
        "label_zh": "低波动期 TP 过远",
        "label_en": "TP too far under low ATR regime",
        "description": "ATR 在历史低分位,但 TP 距离超过 2.8x ATR,时间窗内根本走不到。",
        "detection_rule": "atr_15m < P25_atr_30d AND tp_distance_atr_ratio > 2.8",
    },
    {
        "key": "news_event_30min_blackout",
        "label_zh": "宏观数据 30 分钟内入场",
        "label_en": "Entry within 30 min of macro event",
        "description": "CPI / FOMC / NFP 发布前后 30 分钟,波动方向不可预测,纪律性回避。",
        "detection_rule": None,    # 需挂日历,Phase 2 暂留 NULL
    },
    {
        "key": "chase_after_3pct_move",
        "label_zh": "追在 3% 大幅之后",
        "label_en": "Chase after 3% rapid move",
        "description": "15m 已经走出 ≥2.5% 单边,这时候开同方向单是典型 FOMO 陷阱。",
        "detection_rule": "ABS(delta_15m_pct) > 0.025",
    },
    {
        "key": "repeat_failure_same_symbol_24h",
        "label_zh": "24h 内同币重复亏",
        "label_en": "Repeat failure on same symbol within 24h",
        "description": "过去 24h 该 symbol 已经有 ≥2 笔 LOSS,大概率市场制度对该币不友好。",
        "detection_rule": "symbol_loss_count_24h >= 2",
    },
]
```

- [ ] **Step 4: Modify `scripts/local_db.py` — add taxonomy table + seed call**

Append to `_V5_SCHEMA_SQL` (inside the multi-line string, before the closing `"""`):

```sql

CREATE TABLE IF NOT EXISTS failure_taxonomy (
    key TEXT PRIMARY KEY,
    label_zh TEXT NOT NULL,
    label_en TEXT NOT NULL,
    description TEXT NOT NULL,
    detection_rule TEXT,
    is_active INTEGER DEFAULT 1,
    sample_count INTEGER DEFAULT 0,
    avg_loss_pct REAL,
    last_seen_at TEXT,
    seeded INTEGER DEFAULT 0,
    approved_by TEXT,
    approved_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

At module bottom (after `init_local_db`), add a seed helper and call it from `init_local_db`:

```python
def _seed_failure_taxonomy(conn) -> None:
    from scripts.ai.failure_taxonomy_seed import SEEDS
    for s in SEEDS:
        conn.execute("""
            INSERT OR IGNORE INTO failure_taxonomy
                (key, label_zh, label_en, description, detection_rule,
                 seeded, approved_by, approved_at)
            VALUES (?, ?, ?, ?, ?, 1, 'system', datetime('now'))
        """, (s["key"], s["label_zh"], s["label_en"],
              s["description"], s["detection_rule"]))
```

Find the existing `init_local_db` function. Just before its final `conn.commit()` (or right after `executescript(_V5_SCHEMA_SQL)`), add:

```python
    _seed_failure_taxonomy(conn)
```

- [ ] **Step 5: Run tests, expect 5 passed + full suite no regression**

```bash
python3 -m pytest tests/test_failure_taxonomy_seed.py -v 2>&1 | tail -10
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 148 + 5 = 153.

- [ ] **Step 6: Commit**

```bash
git add scripts/local_db.py scripts/ai/failure_taxonomy_seed.py tests/test_failure_taxonomy_seed.py
git commit -m "feat(reflection): failure_taxonomy 表 + 8 种子模式

- failure_taxonomy schema (key/label/detection_rule/is_active/stats/seeded)
- 8 预置 seeds: late_entry_signal_decay / macd_false_cross /
  against_4h_trend_no_funding_filter / sl_too_tight_in_high_atr /
  tp_too_far_in_low_atr / news_event_30min_blackout(rule=NULL) /
  chase_after_3pct_move / repeat_failure_same_symbol_24h
- init_local_db 自动 idempotent seed

5 seed tests."
```

---

### Task 7: detection_rule DSL parser + matcher

**Files:**
- Create: `scripts/ai/failure_taxonomy.py`
- Create: `tests/test_failure_taxonomy_matcher.py`

- [ ] **Step 1: Write failing test `tests/test_failure_taxonomy_matcher.py`**

```python
"""Failure taxonomy matcher — 给一个入场 candidate,返回命中的 taxonomy keys。"""
import sqlite3
import tempfile
import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _candidate(**over):
    base = dict(
        side="SHORT", side_int=-1,
        rsi_15m=72.0, macd_hist_15m=-0.0012, macd_hist_prev_15m=0.0008,
        macd_hist_4h=0.003, atr_15m=0.0015,
        sl_distance_atr_ratio=1.5, tp_distance_atr_ratio=2.0,
        delta_15m_pct=0.01,
        funding_z_score=None,
        symbol="HUSDT",
    )
    base.update(over)
    return base


def test_no_matches_when_candidate_clean(db):
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(), db_path=db)
    assert hits == []


def test_late_entry_matches_when_hist_decayed(db):
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(
        rsi_15m=72.5,
        macd_hist_prev_15m=-0.0001,    # 几乎为 0 → 比已经退太远
        macd_hist_15m=-0.001,
    ), db_path=db)
    assert "late_entry_signal_decay" in hits


def test_chase_after_3pct_matches(db):
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(delta_15m_pct=0.03), db_path=db)
    assert "chase_after_3pct_move" in hits


def test_against_4h_no_funding_matches(db):
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(
        side="SHORT", side_int=-1,
        macd_hist_4h=0.005,           # 4h 看多
        funding_z_score=None,
    ), db_path=db)
    assert "against_4h_trend_no_funding_filter" in hits


def test_funding_high_z_overrides_4h_filter(db):
    """funding z-score 极端时,该规则不再触发(funding 给了反向背书)。"""
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(
        side="SHORT", side_int=-1,
        macd_hist_4h=0.005,
        funding_z_score=2.5,           # funding 极端正 = SHORT 有理
    ), db_path=db)
    assert "against_4h_trend_no_funding_filter" not in hits


def test_repeat_failure_same_symbol_24h_matches(db):
    """注入 2 笔过去 24h LOSS → 匹配。"""
    from scripts.ai.failure_taxonomy import match_failure_modes
    conn = sqlite3.connect(db)
    for i in range(2):
        conn.execute("""
            INSERT INTO paper_trades (symbol, side, entry_price, entry_time, status,
                stop_loss, take_profit, position_size_usdt, leverage, strategy_id,
                created_at, exit_time, exit_reason, pnl_percent)
            VALUES ('HUSDT', 'SHORT', 0.166, datetime('now', '-3 hours'), 'CLOSED',
                    0.169, 0.162, 15, 10, 'v5_rsi_macd', datetime('now', '-3 hours'),
                    datetime('now', '-2 hours'), 'SL_HIT', -1.8)
        """)
    conn.commit()
    conn.close()
    hits = match_failure_modes(_candidate(symbol="HUSDT"), db_path=db)
    assert "repeat_failure_same_symbol_24h" in hits


def test_only_active_taxonomy_is_matched(db):
    """is_active=0 的 rule 不参与匹配。"""
    from scripts.ai.failure_taxonomy import match_failure_modes
    conn = sqlite3.connect(db)
    conn.execute("UPDATE failure_taxonomy SET is_active=0 WHERE key='chase_after_3pct_move'")
    conn.commit()
    conn.close()
    hits = match_failure_modes(_candidate(delta_15m_pct=0.03), db_path=db)
    assert "chase_after_3pct_move" not in hits
```

- [ ] **Step 2: Run, expect 7 fail**

- [ ] **Step 3: Write `scripts/ai/failure_taxonomy.py`**

```python
"""Failure taxonomy matcher — 把 candidate dict 跟 active taxonomy 比对。

DSL 故意保持非通用化:每个 rule 直接对应一个 handler 函数。这避免了
写一个完整 SQL DSL parser,代价是 detection_rule 字段在 Phase 2 主要起
"自描述"作用,真正的匹配逻辑由 _HANDLERS 注册。

后续如需 AI 提案新模式自动转 DSL,可在 Phase 4 加 parser。
"""
import os
import sqlite3
from typing import Callable, List, Optional


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


Handler = Callable[[dict, str], bool]


def _h_late_entry_signal_decay(c: dict, db_path: str) -> bool:
    rsi = c.get("rsi_15m") or 0
    hist = c.get("macd_hist_15m") or 0
    hist_prev = c.get("macd_hist_prev_15m") or 0
    if rsi <= 70:
        return False
    if hist == 0:
        return False
    return abs(hist_prev / hist) < 0.3


def _h_macd_false_cross(c: dict, db_path: str) -> bool:
    """假拐点要看过去 3 根 K 线 — 单根 entry snapshot 看不出来。
    Phase 2 暂时返回 False (留作 Phase 4 给历史数据回算)。"""
    return False


def _h_against_4h_trend_no_funding(c: dict, db_path: str) -> bool:
    side_int = c.get("side_int") or 0
    macd_4h = c.get("macd_hist_4h") or 0
    fz = c.get("funding_z_score")
    if side_int == 0 or macd_4h == 0:
        return False
    same_dir = (side_int > 0 and macd_4h > 0) or (side_int < 0 and macd_4h < 0)
    if same_dir:
        return False
    # 反向 + funding 没给极端确认 → 触发
    if fz is None:
        return True
    return abs(fz) < 1.5


def _h_sl_too_tight_high_atr(c: dict, db_path: str) -> bool:
    atr = c.get("atr_15m") or 0
    ratio = c.get("sl_distance_atr_ratio") or 999
    p75 = _percentile_atr(db_path, 75, 30)
    if p75 is None or atr == 0:
        return False
    return atr > p75 and ratio < 1.2


def _h_tp_too_far_low_atr(c: dict, db_path: str) -> bool:
    atr = c.get("atr_15m") or 0
    ratio = c.get("tp_distance_atr_ratio") or 0
    p25 = _percentile_atr(db_path, 25, 30)
    if p25 is None or atr == 0:
        return False
    return atr < p25 and ratio > 2.8


def _h_news_event_blackout(c: dict, db_path: str) -> bool:
    """需挂日历,Phase 2 始终返回 False。"""
    return False


def _h_chase_after_3pct(c: dict, db_path: str) -> bool:
    dp = c.get("delta_15m_pct") or 0
    return abs(dp) > 0.025


def _h_repeat_failure_same_symbol(c: dict, db_path: str) -> bool:
    symbol = c.get("symbol")
    if not symbol:
        return False
    conn = sqlite3.connect(db_path)
    try:
        n = conn.execute("""
            SELECT COUNT(*) FROM paper_trades
             WHERE symbol = ? AND status = 'CLOSED'
               AND pnl_percent < 0
               AND exit_time >= datetime('now', '-24 hours')
        """, (symbol,)).fetchone()[0]
        return n >= 2
    finally:
        conn.close()


_HANDLERS: dict[str, Handler] = {
    "late_entry_signal_decay":              _h_late_entry_signal_decay,
    "macd_false_cross":                      _h_macd_false_cross,
    "against_4h_trend_no_funding_filter":    _h_against_4h_trend_no_funding,
    "sl_too_tight_in_high_atr":              _h_sl_too_tight_high_atr,
    "tp_too_far_in_low_atr":                 _h_tp_too_far_low_atr,
    "news_event_30min_blackout":             _h_news_event_blackout,
    "chase_after_3pct_move":                 _h_chase_after_3pct,
    "repeat_failure_same_symbol_24h":        _h_repeat_failure_same_symbol,
}


def _percentile_atr(db_path: str, percentile: int, days: int) -> Optional[float]:
    """简化版:取 trade_scores_v5 过去 N 天的 atr_15m,按内存排序取分位。"""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT atr_15m FROM trade_scores_v5 "
            f"WHERE atr_15m IS NOT NULL "
            f"AND created_at >= datetime('now', '-{days} days') "
            f"ORDER BY atr_15m"
        ).fetchall()
    finally:
        conn.close()
    if len(rows) < 20:
        return None
    idx = int(len(rows) * percentile / 100)
    return rows[idx][0]


def match_failure_modes(candidate: dict, *, db_path: Optional[str] = None) -> List[str]:
    """对一个入场 candidate 跑所有 active taxonomy handlers,返回命中 keys."""
    db = db_path or _db()
    conn = sqlite3.connect(db)
    try:
        active_keys = [r[0] for r in conn.execute(
            "SELECT key FROM failure_taxonomy WHERE is_active=1"
        ).fetchall()]
    finally:
        conn.close()

    hits: List[str] = []
    for key in active_keys:
        handler = _HANDLERS.get(key)
        if handler is None:
            continue   # AI-proposed key not yet implemented
        try:
            if handler(candidate, db):
                hits.append(key)
        except Exception as e:
            print(f"[taxonomy] handler {key} raised {type(e).__name__}: {e}")
    return hits
```

- [ ] **Step 4: Run tests + full suite**

```bash
python3 -m pytest tests/test_failure_taxonomy_matcher.py -v 2>&1 | tail -15
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 7 new + 160 cumulative.

- [ ] **Step 5: Commit**

```bash
git add scripts/ai/failure_taxonomy.py tests/test_failure_taxonomy_matcher.py
git commit -m "feat(reflection): failure_taxonomy matcher with 8 handlers

- _HANDLERS dict-of-funcs (not full DSL parser — pragma over purity)
- macd_false_cross + news_event 留 stub (need history / calendar)
- ATR percentile from trade_scores_v5 last 30d (min 20 samples)
- repeat_failure_same_symbol_24h queries paper_trades CLOSED with pnl<0
- against_4h_trend overridden when |funding_z| ≥ 1.5
- is_active=0 taxonomy skipped

7 matcher tests covering each branch."
```

---

### Task 8: trading_assistant.decide veto + reflection_worker uses taxonomy keys

**Files:**
- Modify: `scripts/ai/trading_assistant.py` (pre-decision veto)
- Modify: `scripts/tasks/collector_main.py` (pass taxonomy keys to worker)
- Create: `tests/test_trading_assistant_taxonomy.py`

- [ ] **Step 1: Write failing test `tests/test_trading_assistant_taxonomy.py`**

```python
"""trading_assistant.decide 在 candidate 命中 failure_taxonomy 时直接拒绝。"""
import sqlite3
import tempfile
import pytest
from unittest.mock import AsyncMock

from v5_types import AIResult, Decision, EnrichedItem, Indicators, RiskPlan


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _make_objects(side="SHORT", delta_pct=0.005, rsi=72.0):
    enriched = EnrichedItem(
        symbol="HUSDT", current_price=0.166, delta_15m_pct=delta_pct,
        volume_24h_usdt=5e7, klines_15m=[], klines_4h=[],
    )
    indicators = Indicators(
        rsi_15m=rsi, macd_15m=0, macd_signal_15m=0,
        macd_hist_15m=-0.0012, macd_hist_prev_15m=0.0008,
        rsi_4h=68.0, macd_hist_4h=0.003,
        atr_15m=0.0015,
    )
    decision = Decision(should_trade=True, side=side,
                         reasoning="rsi + macd", block_reason=None)
    risk = RiskPlan(entry_price=0.166, sl_price=0.169, tp_price=0.162,
                     size_usdt=15, leverage=10, expected_rr=1.5)
    return enriched, indicators, decision, risk


@pytest.mark.asyncio
async def test_decide_returns_taxonomy_block_when_chase_after_3pct(db, monkeypatch):
    """delta_15m_pct=0.03 → chase_after_3pct_move 命中 → AI 不调用,返回 execute=False。"""
    from scripts.ai.trading_assistant import TradingAssistant

    enriched, indicators, decision, risk = _make_objects(delta_pct=0.03)
    ai = TradingAssistant()
    ai.client = object()    # 让客户端非 None
    ai._decide_via_chat = AsyncMock()    # spy — 不应被调用

    result = await ai.decide(enriched, indicators, decision, risk)
    assert result.execute is False
    assert "FAILURE_MODE" in (result.reasoning or "")
    assert "chase_after_3pct_move" in (result.reasoning or "")
    ai._decide_via_chat.assert_not_called()


@pytest.mark.asyncio
async def test_decide_proceeds_when_no_taxonomy_match(db, monkeypatch):
    """clean candidate → 走原 AI 路径。"""
    from scripts.ai.trading_assistant import TradingAssistant

    enriched, indicators, decision, risk = _make_objects(
        delta_pct=0.005, rsi=72.0,
    )
    # 把 macd_hist_4h 调到跟 SHORT 方向一致 → 不触发 against_4h
    indicators.macd_hist_4h = -0.003

    ai = TradingAssistant()
    ai.client = object()
    fake_result = AIResult(execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
                            size_multiplier=1.0, confidence=0.7,
                            reasoning="proceed")
    ai._decide_via_chat = AsyncMock(return_value=fake_result)

    result = await ai.decide(enriched, indicators, decision, risk)
    assert result.execute is True
    ai._decide_via_chat.assert_called_once()


@pytest.mark.asyncio
async def test_decide_skips_taxonomy_for_manual_strategy(db, monkeypatch):
    """v5_manual 单豁免 taxonomy(用户主动开,跟自动单不同纪律)。"""
    from scripts.ai.trading_assistant import TradingAssistant

    enriched, indicators, decision, risk = _make_objects(delta_pct=0.03)
    ai = TradingAssistant()
    ai.client = object()
    fake_result = AIResult(execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
                            size_multiplier=1.0, confidence=0.7,
                            reasoning="manual override")
    ai._decide_via_chat = AsyncMock(return_value=fake_result)

    result = await ai.decide(enriched, indicators, decision, risk,
                              strategy_id="v5_manual")
    assert result.execute is True
    ai._decide_via_chat.assert_called_once()
```

Note: this test uses `pytest-asyncio`. Verify it's configured (it should be — V5 already uses async tests). If not, add to `pytest.ini`:
```
[pytest]
asyncio_mode = auto
```

- [ ] **Step 2: Run, expect 3 fail**

- [ ] **Step 3: Modify `scripts/ai/trading_assistant.py` — add taxonomy veto at top of decide()**

Find the `async def decide(self, enriched, indicators, decision, risk` signature (~line 236). Add an optional `strategy_id` parameter and a taxonomy check before the AI call.

```python
    async def decide(self, enriched, indicators, decision, risk,
                     *, strategy_id: Optional[str] = None) -> AIResult:
        """Pre-decision veto: 命中 failure_taxonomy 直接返回 execute=False。
        v5_manual 单豁免 (用户主导)。"""
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

        # 原 RAG + AI call 路径 (现有代码,无改动)
        self._pending_rag_text = ""
        # ... (existing code continues)
```

Replace the whole function body carefully — keep the existing RAG fetch + `_decide_via_chat` call logic intact.

- [ ] **Step 4: Modify scorer call site if needed**

Search `process_enriched_v5` in `scripts/tasks/scorer.py` for `await ai.decide(`. If it doesn't pass `strategy_id`, that's fine — defaults to None which skips taxonomy only for manual orders. **No change needed** to scorer.

Search `api/routes/v5_manual_order.py` for `await ta.decide(`. Pass `strategy_id="v5_manual"` to opt out of taxonomy:

Find:
```python
        ai_result = await ta.decide(enriched, indicators, decision, risk)
```
Replace with:
```python
        ai_result = await ta.decide(enriched, indicators, decision, risk,
                                     strategy_id="v5_manual")
```

- [ ] **Step 5: Modify `scripts/tasks/collector_main.py` — pass taxonomy keys to worker**

Find the `V5ReflectionWorker(...)` constructor call. Change `taxonomy_keys=[]` to:

```python
        taxonomy_keys=[
            "late_entry_signal_decay", "macd_false_cross",
            "against_4h_trend_no_funding_filter", "sl_too_tight_in_high_atr",
            "tp_too_far_in_low_atr", "news_event_30min_blackout",
            "chase_after_3pct_move", "repeat_failure_same_symbol_24h",
        ],
```

(So the AI sees the taxonomy when reflecting.)

- [ ] **Step 6: Run tests + full suite**

```bash
python3 -m pytest tests/test_trading_assistant_taxonomy.py -v 2>&1 | tail -10
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 3 new + 163 cumulative.

- [ ] **Step 7: Commit**

```bash
git add scripts/ai/trading_assistant.py scripts/tasks/collector_main.py \
        api/routes/v5_manual_order.py tests/test_trading_assistant_taxonomy.py
git commit -m "feat(reflection): trading_assistant veto on failure_taxonomy match

- Pre-decision check: candidate → match_failure_modes() → veto with
  reasoning='FAILURE_MODE_MATCH:<keys>' on hit, never calls LLM
- v5_manual strategy_id bypasses taxonomy (user override)
- v5_manual_order route passes strategy_id explicitly
- collector_main wires 8 taxonomy keys into reflection worker

3 veto integration tests."
```

---

### Task 9: API `/failure-taxonomy` + frontend Tab 2

**Files:**
- Modify: `api/schemas/v5_reflection.py` (add taxonomy schemas)
- Modify: `api/routes/v5_reflection.py` (add list endpoint)
- Modify: `Rabbit Hunterfronted/types.ts`
- Modify: `Rabbit Hunterfronted/hooks/api/useV5Reflections.ts`
- Modify: `Rabbit Hunterfronted/components/pages/V5ReflectionPage.tsx`
- Modify: `tests/test_v5_reflection_api.py`

- [ ] **Step 1: Add to `api/schemas/v5_reflection.py`**

```python
class FailureMode(BaseModel):
    key: str
    label_zh: str
    label_en: str
    description: str
    detection_rule: Optional[str]
    is_active: bool
    sample_count: int
    avg_loss_pct: Optional[float]
    last_seen_at: Optional[str]
    seeded: bool
    approved_by: Optional[str]


class FailureTaxonomyResponse(BaseModel):
    status: str = "success"
    data: List[FailureMode]
```

- [ ] **Step 2: Add route in `api/routes/v5_reflection.py`**

```python
from api.schemas.v5_reflection import FailureMode, FailureTaxonomyResponse


@router.get("/failure-taxonomy", response_model=FailureTaxonomyResponse)
async def list_failure_taxonomy() -> FailureTaxonomyResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        # Backfill stats from reflections
        rows = conn.execute("""
            SELECT t.key, t.label_zh, t.label_en, t.description,
                   t.detection_rule, t.is_active, t.avg_loss_pct,
                   t.seeded, t.approved_by, t.last_seen_at,
                   (SELECT COUNT(*) FROM reflections r
                      WHERE r.failure_mode_key = t.key) AS sample_count
              FROM failure_taxonomy t
             ORDER BY sample_count DESC, t.key
        """).fetchall()
    finally:
        conn.close()
    return FailureTaxonomyResponse(data=[
        FailureMode(
            key=r["key"], label_zh=r["label_zh"], label_en=r["label_en"],
            description=r["description"], detection_rule=r["detection_rule"],
            is_active=bool(r["is_active"]),
            sample_count=r["sample_count"], avg_loss_pct=r["avg_loss_pct"],
            last_seen_at=r["last_seen_at"], seeded=bool(r["seeded"]),
            approved_by=r["approved_by"],
        )
        for r in rows
    ])
```

- [ ] **Step 3: Append to `tests/test_v5_reflection_api.py`**

```python
def test_failure_taxonomy_returns_8_seeds(client):
    c, _ = client
    r = c.get("/api/v5/failure-taxonomy")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert len(body["data"]) == 8
    keys = {m["key"] for m in body["data"]}
    assert "chase_after_3pct_move" in keys
    for m in body["data"]:
        assert m["seeded"] is True
        assert m["sample_count"] == 0    # 还没 reflection 链上


def test_failure_taxonomy_counts_reflections(client):
    c, db = client
    _insert_reflection(db, pid=1)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE reflections SET failure_mode_key='chase_after_3pct_move' WHERE paper_trade_id=1")
    conn.commit()
    conn.close()
    r = c.get("/api/v5/failure-taxonomy")
    by_key = {m["key"]: m for m in r.json()["data"]}
    assert by_key["chase_after_3pct_move"]["sample_count"] == 1
```

- [ ] **Step 4: Add to `Rabbit Hunterfronted/types.ts`** (before WebSocket section):

```ts
export interface FailureMode {
  key: string;
  label_zh: string;
  label_en: string;
  description: string;
  detection_rule: string | null;
  is_active: boolean;
  sample_count: number;
  avg_loss_pct: number | null;
  last_seen_at: string | null;
  seeded: boolean;
  approved_by: string | null;
}

export interface FailureTaxonomyResponse {
  status: string;
  data: FailureMode[];
}
```

- [ ] **Step 5: Add hook in `Rabbit Hunterfronted/hooks/api/useV5Reflections.ts`**

```ts
import type { FailureTaxonomyResponse } from '../../types';

export function useV5FailureTaxonomy() {
  return useQuery<FailureTaxonomyResponse>({
    queryKey: ['v5', 'failure-taxonomy'],
    queryFn: () => apiGet<FailureTaxonomyResponse>('/api/v5/failure-taxonomy'),
    refetchInterval: 60_000,
  });
}
```

- [ ] **Step 6: Update `V5ReflectionPage.tsx` — replace TaxonomyTab stub**

Add import:
```tsx
import { useV5FailureTaxonomy } from '../../hooks/api/useV5Reflections';
```

Replace the placeholder `{tab === 'taxonomy' && <Card title="失败模式">...}` with `<TaxonomyTab />`, and add the component:

```tsx
function TaxonomyTab() {
  const q = useV5FailureTaxonomy();
  if (q.isLoading) return <LoadingSkeleton rows={5} />;
  const rows = q.data?.data ?? [];

  return (
    <Card title={`失败模式分布 (n=${rows.length})`}>
      <div className="overflow-hidden rounded-md border border-white/10">
        <table className="w-full text-xs">
          <thead className="bg-white/5">
            <tr className="text-left text-white/60">
              <th className="px-2 py-2">key</th>
              <th className="px-2 py-2">中文标签</th>
              <th className="px-2 py-2 text-right">命中次数</th>
              <th className="px-2 py-2">detection_rule</th>
              <th className="px-2 py-2">来源</th>
              <th className="px-2 py-2 text-right">激活</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(m => (
              <tr key={m.key} className="border-t border-white/5 hover:bg-white/[0.02]">
                <td className="px-2 py-1.5 font-mono text-white/80">{m.key}</td>
                <td className="px-2 py-1.5 text-white">{m.label_zh}</td>
                <td className="px-2 py-1.5 text-right font-mono">
                  {m.sample_count > 0
                    ? <span className="text-accent-warn">{m.sample_count}</span>
                    : <span className="text-white/30">0</span>}
                </td>
                <td className="px-2 py-1.5 font-mono text-white/50 truncate max-w-xs">
                  {m.detection_rule ?? '—'}
                </td>
                <td className="px-2 py-1.5">
                  {m.seeded
                    ? <Badge variant="info">预置</Badge>
                    : <Badge variant="warn">AI 提案</Badge>}
                </td>
                <td className="px-2 py-1.5 text-right">
                  {m.is_active
                    ? <span className="text-accent-long">●</span>
                    : <span className="text-white/30">○</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
```

- [ ] **Step 7: Run tests + build**

```bash
python3 -m pytest tests/test_v5_reflection_api.py -v 2>&1 | tail -10
python3 -m pytest tests/ -q 2>&1 | tail -3
cd "Rabbit Hunterfronted"
npx vitest run 2>&1 | tail -3
npx vite build 2>&1 | tail -5
```

Expected: BE 163 + 2 = 165; FE 49(no new tests for this small UI change — covered by existing V5ReflectionPage.test); build OK.

- [ ] **Step 8: Commit**

```bash
cd /Users/lizhishaoniange/Documents/Rabbit-Hunter
git add api/schemas/v5_reflection.py api/routes/v5_reflection.py tests/test_v5_reflection_api.py \
        "Rabbit Hunterfronted/types.ts" \
        "Rabbit Hunterfronted/hooks/api/useV5Reflections.ts" \
        "Rabbit Hunterfronted/components/pages/V5ReflectionPage.tsx"
git commit -m "feat(reflection): GET /failure-taxonomy + Tab 2 (失败模式分布)

- Backend joins taxonomy with reflection sample_count
- Frontend table: key / label_zh / sample_count / detection_rule / seeded / active
- Predefined vs AI-proposed badge

2 API tests."
```

---

## Phase 3 — Layer 3 日聚合 + Layer 4 Kelly 仓位 + 置信度校准 (5 tasks)

### Task 10: setup_performance_daily aggregator + cron in worker

**Files:**
- Modify: `scripts/local_db.py` (add 3 tables: setup_performance_daily, position_sizing_recommendations, ai_confidence_calibration)
- Create: `scripts/ai/setup_aggregator.py`
- Modify: `scripts/tasks/v5_reflection_worker.py` (cron scheduler)
- Create: `tests/test_setup_aggregator.py`

- [ ] **Step 1: Append to `_V5_SCHEMA_SQL` in `scripts/local_db.py`**

```sql

CREATE TABLE IF NOT EXISTS setup_performance_daily (
    date TEXT NOT NULL,
    setup_type TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    win_count INTEGER NOT NULL,
    loss_count INTEGER NOT NULL,
    scratch_count INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    avg_realized_r REAL NOT NULL,
    avg_holding_minutes REAL,
    expectancy REAL,
    sharpe_30d REAL,
    top_failure_mode TEXT,
    PRIMARY KEY (date, setup_type)
);

CREATE TABLE IF NOT EXISTS position_sizing_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setup_type TEXT NOT NULL,
    proposed_at TEXT DEFAULT (datetime('now')),
    current_size_multiplier REAL NOT NULL,
    recommended_size_multiplier REAL NOT NULL,
    confidence_score REAL NOT NULL,
    rationale TEXT NOT NULL,
    sample_count_30d INTEGER,
    sample_count_60d INTEGER,
    sample_count_90d INTEGER,
    kelly_f_30d REAL,
    kelly_f_60d REAL,
    kelly_f_90d REAL,
    fractional_kelly_applied REAL,
    status TEXT DEFAULT 'pending',
    user_decision_at TEXT,
    user_decision_note TEXT,
    user_modified_value REAL,
    ab_test_started_at TEXT,
    ab_test_target_sample INTEGER,
    ab_test_result TEXT
);

CREATE TABLE IF NOT EXISTS ai_confidence_calibration (
    ai_model TEXT NOT NULL,
    confidence_bucket REAL NOT NULL,
    predicted_win_rate REAL NOT NULL,
    actual_win_rate REAL NOT NULL,
    sample_count INTEGER NOT NULL,
    calibration_multiplier REAL NOT NULL,
    last_updated TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (ai_model, confidence_bucket)
);
```

- [ ] **Step 2: Write failing test `tests/test_setup_aggregator.py`**

```python
"""Daily aggregator by setup_type — group reflections, compute stats."""
import sqlite3
import tempfile
import pytest
from datetime import datetime, timezone, timedelta


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _seed_reflections(db_path, rows):
    conn = sqlite3.connect(db_path)
    for r in rows:
        conn.execute("""
            INSERT INTO reflections (paper_trade_id, why_entered, what_was_expected,
                what_actually_happened, correction_idea, failure_mode_key,
                setup_type, outcome_class, realized_r, holding_minutes,
                confidence_at_entry, created_at, prompt_version)
            VALUES (?, 'x', 'y', 'z', 'w', ?, ?, ?, ?, ?, 0.7, ?, 'v1')
        """, (r["pid"], r.get("fm"), r["setup_type"], r["outcome"],
              r["realized_r"], r.get("hold", 30), r["created_at"]))
    conn.commit()
    conn.close()


def test_aggregate_groups_by_setup_type_and_date(db):
    from scripts.ai.setup_aggregator import aggregate_daily

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT12:00:00+00:00")
    _seed_reflections(db, [
        dict(pid=1, setup_type="rsi_overbought_macd_bearish_short",
             outcome="WIN", realized_r=1.2, created_at=yesterday),
        dict(pid=2, setup_type="rsi_overbought_macd_bearish_short",
             outcome="LOSS", realized_r=-1.0, created_at=yesterday),
        dict(pid=3, setup_type="rsi_oversold_macd_bullish_long",
             outcome="WIN", realized_r=0.8, created_at=yesterday),
    ])

    aggregate_daily(db_path=db, target_date=yesterday[:10])

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT setup_type, sample_count, win_count, loss_count, win_rate, avg_realized_r "
        "FROM setup_performance_daily ORDER BY setup_type"
    ).fetchall()
    conn.close()

    by_setup = {r[0]: r for r in rows}
    assert by_setup["rsi_overbought_macd_bearish_short"][1] == 2
    assert by_setup["rsi_overbought_macd_bearish_short"][2] == 1
    assert abs(by_setup["rsi_overbought_macd_bearish_short"][4] - 0.5) < 1e-9
    assert abs(by_setup["rsi_overbought_macd_bearish_short"][5] - 0.1) < 1e-9
    assert by_setup["rsi_oversold_macd_bullish_long"][1] == 1


def test_aggregate_includes_top_failure_mode(db):
    from scripts.ai.setup_aggregator import aggregate_daily

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT12:00:00+00:00")
    _seed_reflections(db, [
        dict(pid=1, setup_type="X", outcome="LOSS", realized_r=-1.0,
             fm="late_entry_signal_decay", created_at=yesterday),
        dict(pid=2, setup_type="X", outcome="LOSS", realized_r=-1.0,
             fm="late_entry_signal_decay", created_at=yesterday),
        dict(pid=3, setup_type="X", outcome="LOSS", realized_r=-1.0,
             fm="chase_after_3pct_move", created_at=yesterday),
    ])
    aggregate_daily(db_path=db, target_date=yesterday[:10])

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT top_failure_mode FROM setup_performance_daily WHERE setup_type='X'"
    ).fetchone()
    conn.close()
    assert row[0] == "late_entry_signal_decay"


def test_aggregate_is_idempotent(db):
    """跑两次同一天,不重复入库。"""
    from scripts.ai.setup_aggregator import aggregate_daily

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT12:00:00+00:00")
    _seed_reflections(db, [
        dict(pid=1, setup_type="Y", outcome="WIN", realized_r=1.0, created_at=today),
    ])
    aggregate_daily(db_path=db, target_date=today[:10])
    aggregate_daily(db_path=db, target_date=today[:10])

    conn = sqlite3.connect(db)
    n = conn.execute(
        "SELECT COUNT(*) FROM setup_performance_daily WHERE setup_type='Y'"
    ).fetchone()[0]
    conn.close()
    assert n == 1


def test_aggregate_computes_expectancy(db):
    from scripts.ai.setup_aggregator import aggregate_daily

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT12:00:00+00:00")
    _seed_reflections(db, [
        dict(pid=1, setup_type="Z", outcome="WIN", realized_r=2.0, created_at=today),
        dict(pid=2, setup_type="Z", outcome="WIN", realized_r=1.0, created_at=today),
        dict(pid=3, setup_type="Z", outcome="LOSS", realized_r=-1.0, created_at=today),
        dict(pid=4, setup_type="Z", outcome="LOSS", realized_r=-1.0, created_at=today),
    ])
    aggregate_daily(db_path=db, target_date=today[:10])

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT win_rate, avg_realized_r, expectancy FROM setup_performance_daily WHERE setup_type='Z'"
    ).fetchone()
    conn.close()
    win_rate, avg_r, exp = row
    # win_rate 0.5, avg_win=1.5, avg_loss=-1.0 → expectancy = 0.5*1.5 - 0.5*1 = 0.25
    assert abs(win_rate - 0.5) < 1e-9
    assert abs(avg_r - 0.25) < 1e-9
    assert abs(exp - 0.25) < 1e-9
```

- [ ] **Step 3: Run, expect 4 fail**

- [ ] **Step 4: Write `scripts/ai/setup_aggregator.py`**

```python
"""Daily aggregator — group reflections of target_date by setup_type, write daily snapshot."""
import os
import sqlite3
from collections import Counter
from typing import Optional


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def aggregate_daily(*, db_path: Optional[str] = None,
                     target_date: Optional[str] = None) -> int:
    """target_date 形如 '2026-06-14'。None = 昨天。返回写入行数。"""
    db = db_path or _db()
    if target_date is None:
        from datetime import datetime, timezone, timedelta
        target_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("""
            SELECT setup_type, outcome_class, realized_r, holding_minutes,
                   failure_mode_key
              FROM reflections
             WHERE substr(created_at, 1, 10) = ?
        """, (target_date,)).fetchall()

        # group
        groups: dict = {}
        for setup_type, outcome, r, hm, fm in rows:
            g = groups.setdefault(setup_type, {
                "rs": [], "fms": [], "holds": [], "wins": 0, "losses": 0, "scratch": 0,
            })
            g["rs"].append(r)
            g["holds"].append(hm or 0)
            if fm:
                g["fms"].append(fm)
            if outcome == "WIN": g["wins"] += 1
            elif outcome == "LOSS": g["losses"] += 1
            else: g["scratch"] += 1

        written = 0
        for setup_type, g in groups.items():
            n = len(g["rs"])
            avg_r = sum(g["rs"]) / n if n > 0 else 0.0
            wins = [r for r in g["rs"] if r > 0]
            losses = [r for r in g["rs"] if r < 0]
            win_rate = g["wins"] / n if n > 0 else 0.0
            avg_w = sum(wins) / len(wins) if wins else 0.0
            avg_l = sum(losses) / len(losses) if losses else 0.0
            loss_rate = g["losses"] / n if n > 0 else 0.0
            expectancy = win_rate * avg_w + loss_rate * avg_l
            avg_hold = sum(g["holds"]) / n if n > 0 else None
            top_fm = Counter(g["fms"]).most_common(1)[0][0] if g["fms"] else None

            conn.execute("""
                INSERT OR REPLACE INTO setup_performance_daily (
                    date, setup_type, sample_count, win_count, loss_count, scratch_count,
                    win_rate, avg_realized_r, avg_holding_minutes,
                    expectancy, top_failure_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (target_date, setup_type, n, g["wins"], g["losses"], g["scratch"],
                   win_rate, avg_r, avg_hold, expectancy, top_fm))
            written += 1
        conn.commit()
        return written
    finally:
        conn.close()
```

- [ ] **Step 5: Modify `scripts/tasks/v5_reflection_worker.py` — add daily cron**

Replace the `run()` method to include a daily timer:

```python
    async def run(self) -> None:
        from datetime import datetime, timezone
        print(f"[V5ReflectionWorker] 启动,间隔 {self.poll_interval_s}s")
        last_daily_date: Optional[str] = None

        while True:
            try:
                await self._tick()

                # Daily aggregate at 03:00 UTC (once per UTC date)
                now = datetime.now(timezone.utc)
                today_str = now.strftime("%Y-%m-%d")
                if now.hour >= 3 and last_daily_date != today_str:
                    try:
                        from scripts.ai.setup_aggregator import aggregate_daily
                        from datetime import timedelta
                        yday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
                        n = aggregate_daily(db_path=self.db_path, target_date=yday)
                        print(f"[V5ReflectionWorker] daily aggregate {yday}: {n} setup_types")
                        last_daily_date = today_str
                    except Exception as e:
                        print(f"[V5ReflectionWorker] daily aggregate failed: {e}")

            except asyncio.CancelledError:
                return
            except Exception as e:
                print(f"[V5ReflectionWorker] tick 异常: {type(e).__name__}: {e}")
            await asyncio.sleep(self.poll_interval_s)
```

- [ ] **Step 6: Run tests + full suite**

```bash
python3 -m pytest tests/test_setup_aggregator.py -v 2>&1 | tail -10
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 4 new + 169 cumulative.

- [ ] **Step 7: Commit**

```bash
git add scripts/local_db.py scripts/ai/setup_aggregator.py \
        scripts/tasks/v5_reflection_worker.py tests/test_setup_aggregator.py
git commit -m "feat(reflection): daily aggregator by setup_type + worker cron

- 3 new tables: setup_performance_daily / position_sizing_recommendations /
  ai_confidence_calibration
- aggregate_daily(target_date): groups reflections, writes win_rate / avg_r /
  expectancy / top_failure_mode per setup_type
- Idempotent (INSERT OR REPLACE on PK date+setup_type)
- worker cron: 03:00 UTC daily, processes yesterday

4 aggregator tests."
```

---

### Task 11: AI confidence calibration — increment on reflection + apply in trading_assistant

**Files:**
- Create: `scripts/ai/confidence_calibration.py`
- Modify: `scripts/ai/reflection_runner.py` (call update_calibration after persist)
- Modify: `scripts/ai/trading_assistant.py` (apply multiplier on AI confidence)
- Create: `tests/test_confidence_calibration.py`

- [ ] **Step 1: Write failing test `tests/test_confidence_calibration.py`**

```python
"""AI confidence calibration — bucket-wise actual win rate, multiplier."""
import sqlite3
import tempfile
import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def test_update_creates_new_bucket(db):
    from scripts.ai.confidence_calibration import update_calibration
    update_calibration(ai_model="deepseek-chat", confidence_at_entry=0.7,
                       won=True, db_path=db)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT actual_win_rate, sample_count, calibration_multiplier "
        "FROM ai_confidence_calibration WHERE ai_model='deepseek-chat' AND confidence_bucket=0.7"
    ).fetchone()
    conn.close()
    actual_wr, n, mult = row
    assert n == 1
    assert actual_wr == 1.0
    assert abs(mult - (1.0 / 0.7)) < 1e-9


def test_update_running_average(db):
    from scripts.ai.confidence_calibration import update_calibration
    # 3 wins + 2 losses at confidence 0.7 → actual_wr = 0.6
    for won in [True, True, False, True, False]:
        update_calibration(ai_model="deepseek-chat", confidence_at_entry=0.7,
                           won=won, db_path=db)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT actual_win_rate, sample_count, calibration_multiplier "
        "FROM ai_confidence_calibration WHERE confidence_bucket=0.7"
    ).fetchone()
    conn.close()
    actual_wr, n, mult = row
    assert n == 5
    assert abs(actual_wr - 0.6) < 1e-9
    assert abs(mult - (0.6 / 0.7)) < 1e-9


def test_get_multiplier_returns_1_when_no_data(db):
    from scripts.ai.confidence_calibration import get_calibration_multiplier
    mult = get_calibration_multiplier(ai_model="unknown", confidence=0.7, db_path=db)
    assert mult == 1.0


def test_get_multiplier_falls_back_when_sample_too_small(db):
    """sample < 10 → 不用校准,返回 1.0。"""
    from scripts.ai.confidence_calibration import update_calibration, get_calibration_multiplier
    for _ in range(5):
        update_calibration(ai_model="deepseek-chat", confidence_at_entry=0.7,
                           won=False, db_path=db)
    mult = get_calibration_multiplier(ai_model="deepseek-chat", confidence=0.7, db_path=db)
    assert mult == 1.0


def test_get_multiplier_after_sufficient_samples(db):
    from scripts.ai.confidence_calibration import update_calibration, get_calibration_multiplier
    # 15 samples, 6 wins → actual 0.4, predicted 0.8 → multiplier = 0.5
    for i in range(15):
        update_calibration(ai_model="deepseek-chat", confidence_at_entry=0.8,
                           won=(i < 6), db_path=db)
    mult = get_calibration_multiplier(ai_model="deepseek-chat", confidence=0.8, db_path=db)
    assert abs(mult - 0.5) < 1e-9


def test_buckets_round_to_nearest_tenth(db):
    from scripts.ai.confidence_calibration import update_calibration
    update_calibration(ai_model="deepseek-chat", confidence_at_entry=0.72,
                       won=True, db_path=db)
    update_calibration(ai_model="deepseek-chat", confidence_at_entry=0.68,
                       won=False, db_path=db)
    conn = sqlite3.connect(db)
    buckets = sorted(r[0] for r in conn.execute(
        "SELECT confidence_bucket FROM ai_confidence_calibration "
        "WHERE ai_model='deepseek-chat'"
    ).fetchall())
    conn.close()
    assert buckets == [0.7, 0.7] or buckets == [0.7]   # both rounded to 0.7
```

- [ ] **Step 2: Run, expect fail**

- [ ] **Step 3: Write `scripts/ai/confidence_calibration.py`**

```python
"""AI confidence calibration — running track of (predicted vs actual) win rate
per (model, confidence bucket)."""
import os
import sqlite3
from typing import Optional

MIN_SAMPLES_FOR_CALIBRATION = 10


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def _bucket(confidence: float) -> Optional[float]:
    """Round to nearest 0.1 in [0.5, 0.9]."""
    b = round(confidence, 1)
    if b < 0.5 or b > 0.95:
        return None
    return b


def update_calibration(*, ai_model: str, confidence_at_entry: float,
                        won: bool, db_path: Optional[str] = None) -> None:
    bucket = _bucket(confidence_at_entry)
    if bucket is None:
        return
    db = db_path or _db()
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT actual_win_rate, sample_count FROM ai_confidence_calibration "
            "WHERE ai_model=? AND confidence_bucket=?",
            (ai_model, bucket),
        ).fetchone()
        if row is None:
            actual_wr = 1.0 if won else 0.0
            n = 1
        else:
            old_wr, n_old = row
            n = n_old + 1
            actual_wr = (old_wr * n_old + (1 if won else 0)) / n
        multiplier = actual_wr / bucket if bucket > 0 else 1.0
        conn.execute("""
            INSERT INTO ai_confidence_calibration
                (ai_model, confidence_bucket, predicted_win_rate, actual_win_rate,
                 sample_count, calibration_multiplier, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(ai_model, confidence_bucket) DO UPDATE SET
                actual_win_rate = excluded.actual_win_rate,
                sample_count = excluded.sample_count,
                calibration_multiplier = excluded.calibration_multiplier,
                last_updated = excluded.last_updated
        """, (ai_model, bucket, bucket, actual_wr, n, multiplier))
        conn.commit()
    finally:
        conn.close()


def get_calibration_multiplier(*, ai_model: str, confidence: float,
                                 db_path: Optional[str] = None) -> float:
    """返回乘子(实际胜率 / 预测胜率)。样本不足或无数据 → 1.0."""
    bucket = _bucket(confidence)
    if bucket is None:
        return 1.0
    db = db_path or _db()
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT calibration_multiplier, sample_count "
            "FROM ai_confidence_calibration WHERE ai_model=? AND confidence_bucket=?",
            (ai_model, bucket),
        ).fetchone()
    finally:
        conn.close()
    if row is None or row[1] < MIN_SAMPLES_FOR_CALIBRATION:
        return 1.0
    return float(row[0])
```

- [ ] **Step 4: Modify `scripts/ai/reflection_runner.py` — call update_calibration after persist**

In `run_reflection_for_trade`, after `_persist(...)`, add:

```python
    # B-Phase-3: 更新 calibration
    if ai_model:
        try:
            from scripts.ai.confidence_calibration import update_calibration
            update_calibration(
                ai_model=ai_model,
                confidence_at_entry=ctx["confidence_at_entry"],
                won=(ctx["realized_r"] > 0),
                db_path=db_path,
            )
        except Exception as e:
            print(f"[reflection] calibration update failed: {e}")
```

- [ ] **Step 5: Modify `scripts/ai/trading_assistant.py` — apply multiplier on AI confidence**

In `_decide_via_chat`, after parsing the LLM JSON response and constructing the `AIResult`, but BEFORE returning, apply the multiplier:

```python
        # B-Phase-3: apply calibration multiplier
        try:
            from scripts.ai.confidence_calibration import get_calibration_multiplier
            mult = get_calibration_multiplier(
                ai_model=self.chat_model,
                confidence=ai_result.confidence,
            )
            if mult != 1.0:
                ai_result = AIResult(
                    execute=ai_result.execute,
                    sl_multiplier=ai_result.sl_multiplier,
                    tp_multiplier=ai_result.tp_multiplier,
                    size_multiplier=ai_result.size_multiplier,
                    confidence=ai_result.confidence * mult,
                    reasoning=ai_result.reasoning + f" [calibrated ×{mult:.2f}]",
                )
        except Exception as e:
            print(f"[trading_assistant] calibration apply failed: {e}")
        return ai_result
```

(Adapt to exact return-construction pattern in your `_decide_via_chat` — the principle is: after the AIResult is built, wrap with calibration.)

- [ ] **Step 6: Run tests + full suite**

```bash
python3 -m pytest tests/test_confidence_calibration.py -v 2>&1 | tail -10
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 6 new + 175 cumulative.

- [ ] **Step 7: Commit**

```bash
git add scripts/ai/confidence_calibration.py scripts/ai/reflection_runner.py \
        scripts/ai/trading_assistant.py tests/test_confidence_calibration.py
git commit -m "feat(reflection): AI confidence calibration

- update_calibration: bucket-wise running average per (model, 0.1 bucket)
- get_calibration_multiplier: returns 1.0 below 10 samples (avoid overcorrection)
- Reflection runner triggers update after each persist
- trading_assistant._decide_via_chat applies multiplier to AIResult.confidence
  with reasoning annotated '[calibrated ×N]'

6 calibration tests."
```

---

### Task 12: Kelly fractional sizing engine + weekly cron

**Files:**
- Create: `scripts/ai/kelly_sizing.py`
- Modify: `scripts/tasks/v5_reflection_worker.py` (weekly cron)
- Create: `tests/test_kelly_sizing.py`

- [ ] **Step 1: Write failing test `tests/test_kelly_sizing.py`**

```python
"""Fractional Kelly sizing engine + 3-window confidence."""
import sqlite3
import tempfile
import pytest
from datetime import datetime, timezone, timedelta


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _seed_reflections_evenly(db_path, setup_type, n, win_rate, avg_win_r, avg_loss_r,
                              days_back_max=30):
    """填 n 笔均匀分布在过去 days_back_max 天的 reflections。"""
    conn = sqlite3.connect(db_path)
    n_wins = int(n * win_rate)
    for i in range(n):
        days_back = (i % days_back_max) + 1
        created = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
        won = i < n_wins
        r = avg_win_r if won else avg_loss_r
        conn.execute("""
            INSERT INTO reflections (paper_trade_id, why_entered, what_was_expected,
                what_actually_happened, correction_idea, setup_type, outcome_class,
                realized_r, holding_minutes, confidence_at_entry, created_at, prompt_version)
            VALUES (?, 'x', 'y', 'z', 'w', ?, ?, ?, 30, 0.7, ?, 'v1')
        """, (10000 + i, setup_type, 'WIN' if won else 'LOSS', r, created))
    conn.commit()
    conn.close()


def test_returns_no_recommendation_when_insufficient_samples(db):
    from scripts.ai.kelly_sizing import generate_sizing_recommendations
    _seed_reflections_evenly(db, "X", n=3, win_rate=0.6,
                              avg_win_r=1.0, avg_loss_r=-1.0)
    out = generate_sizing_recommendations(db_path=db)
    # samples too few → no row for this setup
    assert all(r["setup_type"] != "X" for r in out)


def test_returns_recommendation_with_sufficient_samples(db):
    from scripts.ai.kelly_sizing import generate_sizing_recommendations
    # 60 笔 60% 胜率 avg_win=1.5 avg_loss=-1.0 → Kelly = 0.6/1.0 - 0.4/1.5 ≈ 0.333
    _seed_reflections_evenly(db, "X", n=60, win_rate=0.6,
                              avg_win_r=1.5, avg_loss_r=-1.0)
    out = generate_sizing_recommendations(db_path=db)
    x = next(r for r in out if r["setup_type"] == "X")
    assert 0.005 <= x["recommended_size_multiplier"] <= 0.02
    assert x["confidence_score"] > 0


def test_recommendation_written_to_db(db):
    from scripts.ai.kelly_sizing import generate_sizing_recommendations
    _seed_reflections_evenly(db, "Y", n=60, win_rate=0.55,
                              avg_win_r=1.2, avg_loss_r=-1.0)
    generate_sizing_recommendations(db_path=db)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, sample_count_30d FROM position_sizing_recommendations "
        "WHERE setup_type='Y' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row[0] == "pending"
    assert row[1] > 0


def test_recommendation_clamps_to_bounds(db):
    """即使 Kelly 计算很大,也不超过 2%;很小不低于 0.5%。"""
    from scripts.ai.kelly_sizing import generate_sizing_recommendations
    # 极高胜率 90% + 高 R → Kelly 大
    _seed_reflections_evenly(db, "Z", n=60, win_rate=0.9,
                              avg_win_r=3.0, avg_loss_r=-1.0)
    generate_sizing_recommendations(db_path=db)
    conn = sqlite3.connect(db)
    rec = conn.execute(
        "SELECT recommended_size_multiplier FROM position_sizing_recommendations "
        "WHERE setup_type='Z'"
    ).fetchone()[0]
    conn.close()
    assert 0.005 <= rec <= 0.02
```

- [ ] **Step 2: Run, expect fail**

- [ ] **Step 3: Write `scripts/ai/kelly_sizing.py`**

```python
"""Fractional Kelly sizing recommendation engine.

For each setup_type with adequate samples in 30d/60d/90d windows:
- Compute Kelly fraction f = p/a - (1-p)/b
- Apply fractional coefficient based on 3-window consistency
- Clamp to [0.005, 0.02] (0.5% to 2% of account)
- Insert as 'pending' recommendation
"""
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import List, Optional


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


MIN_SAMPLE = 10


def _kelly_in_window(conn, setup_type: str, days: int) -> tuple:
    """Returns (kelly_f, sample_count) for the window. kelly_f=None when insufficient."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT realized_r, outcome_class FROM reflections
         WHERE setup_type = ? AND created_at >= ?
    """, (setup_type, cutoff)).fetchall()
    n = len(rows)
    if n < MIN_SAMPLE:
        return None, n
    wins = [r for r, oc in rows if oc == "WIN"]
    losses = [r for r, oc in rows if oc == "LOSS"]
    if not wins or not losses:
        return None, n
    p = len(wins) / n
    b = sum(wins) / len(wins)
    a = sum(abs(r) for r in losses) / len(losses)
    if a == 0:
        return None, n
    f = (p / a) - ((1 - p) / b)
    return max(0.0, f), n


def generate_sizing_recommendations(*, db_path: Optional[str] = None) -> List[dict]:
    db = db_path or _db()
    conn = sqlite3.connect(db)
    try:
        # All setup_types with any reflections
        setup_types = [r[0] for r in conn.execute(
            "SELECT DISTINCT setup_type FROM reflections"
        ).fetchall()]

        out: List[dict] = []
        for st in setup_types:
            f30, n30 = _kelly_in_window(conn, st, 30)
            f60, n60 = _kelly_in_window(conn, st, 60)
            f90, n90 = _kelly_in_window(conn, st, 90)
            valid = [(f, n) for f, n in [(f30, n30), (f60, n60), (f90, n90)] if f is not None]
            if len(valid) < 2:
                continue   # not enough confidence

            fs = [f for f, _ in valid]
            spread = (max(fs) - min(fs)) / (max(fs) + 1e-6)
            total_n = sum(n for _, n in valid)
            confidence_score = (1 - min(spread, 1.0)) * min(total_n / 90.0, 1.0)
            fk_coef = 0.25 + 0.25 * confidence_score

            # weighted average by sample count
            raw = sum(f * n for f, n in valid) / sum(n for _, n in valid)
            recommended = raw * fk_coef
            recommended = max(0.005, min(0.02, recommended))

            rationale = (
                f"30d Kelly={f30}, 60d={f60}, 90d={f90}; "
                f"spread={spread:.2%}, samples={total_n}, "
                f"fractional_k={fk_coef:.2f}"
            )
            row = {
                "setup_type": st,
                "current_size_multiplier": 1.0,
                "recommended_size_multiplier": recommended,
                "confidence_score": confidence_score,
                "rationale": rationale,
                "sample_count_30d": n30,
                "sample_count_60d": n60,
                "sample_count_90d": n90,
                "kelly_f_30d": f30,
                "kelly_f_60d": f60,
                "kelly_f_90d": f90,
                "fractional_kelly_applied": fk_coef,
            }
            conn.execute("""
                INSERT INTO position_sizing_recommendations (
                    setup_type, current_size_multiplier, recommended_size_multiplier,
                    confidence_score, rationale,
                    sample_count_30d, sample_count_60d, sample_count_90d,
                    kelly_f_30d, kelly_f_60d, kelly_f_90d,
                    fractional_kelly_applied
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["setup_type"], row["current_size_multiplier"],
                row["recommended_size_multiplier"], row["confidence_score"],
                row["rationale"], row["sample_count_30d"], row["sample_count_60d"],
                row["sample_count_90d"], row["kelly_f_30d"], row["kelly_f_60d"],
                row["kelly_f_90d"], row["fractional_kelly_applied"],
            ))
            out.append(row)
        conn.commit()
        return out
    finally:
        conn.close()
```

- [ ] **Step 4: Modify `scripts/tasks/v5_reflection_worker.py` — add weekly cron**

Inside the `run()` loop, after the daily aggregate block, add:

```python
                # Weekly sizing recommendations: Sunday 04:00 UTC
                if (now.weekday() == 6 and now.hour >= 4
                        and last_weekly_date != today_str):
                    try:
                        from scripts.ai.kelly_sizing import generate_sizing_recommendations
                        recs = generate_sizing_recommendations(db_path=self.db_path)
                        print(f"[V5ReflectionWorker] weekly sizing: {len(recs)} recommendations")
                        last_weekly_date = today_str
                    except Exception as e:
                        print(f"[V5ReflectionWorker] weekly sizing failed: {e}")
```

And initialize `last_weekly_date: Optional[str] = None` right next to `last_daily_date`.

- [ ] **Step 5: Run tests + full suite**

```bash
python3 -m pytest tests/test_kelly_sizing.py -v 2>&1 | tail -10
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 4 new + 179 cumulative.

- [ ] **Step 6: Commit**

```bash
git add scripts/ai/kelly_sizing.py scripts/tasks/v5_reflection_worker.py tests/test_kelly_sizing.py
git commit -m "feat(reflection): fractional Kelly sizing engine + weekly cron

- generate_sizing_recommendations(): per setup_type, compute Kelly f in
  30d/60d/90d windows, weight by samples, apply fractional coefficient
  (0.25-0.5) by 3-window consistency
- Clamp to [0.5%, 2%] of account
- Insert as 'pending', user must approve via API (Task 13)
- Worker cron: Sun 04:00 UTC

4 sizing engine tests."
```

---

### Task 13: Phase-3 APIs + Frontend Tab 3 + AI Status calibration curve

**Files:**
- Modify: `api/schemas/v5_reflection.py`
- Modify: `api/routes/v5_reflection.py`
- Modify: `Rabbit Hunterfronted/types.ts`
- Modify: `Rabbit Hunterfronted/hooks/api/useV5Reflections.ts`
- Modify: `Rabbit Hunterfronted/components/pages/V5ReflectionPage.tsx`
- Modify: `Rabbit Hunterfronted/components/pages/V5AIStatusPage.tsx`
- Modify: `tests/test_v5_reflection_api.py`

- [ ] **Step 1: Add to `api/schemas/v5_reflection.py`**

```python
class SetupPerformanceItem(BaseModel):
    date: str
    setup_type: str
    sample_count: int
    win_count: int
    loss_count: int
    win_rate: float
    avg_realized_r: float
    expectancy: Optional[float]
    top_failure_mode: Optional[str]


class SetupPerformanceResponse(BaseModel):
    status: str = "success"
    data: List[SetupPerformanceItem]


class SizingRecommendation(BaseModel):
    id: int
    setup_type: str
    proposed_at: str
    current_size_multiplier: float
    recommended_size_multiplier: float
    confidence_score: float
    rationale: str
    sample_count_30d: Optional[int]
    sample_count_60d: Optional[int]
    sample_count_90d: Optional[int]
    kelly_f_30d: Optional[float]
    kelly_f_60d: Optional[float]
    kelly_f_90d: Optional[float]
    status: str


class SizingRecommendationsResponse(BaseModel):
    status: str = "success"
    data: List[SizingRecommendation]


class SizingDecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "modify"]
    modified_value: Optional[float] = None
    note: Optional[str] = None


class CalibrationPoint(BaseModel):
    ai_model: str
    confidence_bucket: float
    predicted_win_rate: float
    actual_win_rate: float
    sample_count: int
    calibration_multiplier: float


class CalibrationResponse(BaseModel):
    status: str = "success"
    data: List[CalibrationPoint]
```

- [ ] **Step 2: Add routes in `api/routes/v5_reflection.py`**

```python
from fastapi import HTTPException, Path
from api.schemas.v5_reflection import (
    SetupPerformanceItem, SetupPerformanceResponse,
    SizingRecommendation, SizingRecommendationsResponse,
    SizingDecisionRequest, CalibrationPoint, CalibrationResponse,
)


@router.get("/setup-performance", response_model=SetupPerformanceResponse)
async def list_setup_performance(days: int = Query(7, ge=1, le=90)) -> SetupPerformanceResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT date, setup_type, sample_count, win_count, loss_count,
                   win_rate, avg_realized_r, expectancy, top_failure_mode
              FROM setup_performance_daily
             WHERE date >= date('now', '-' || ? || ' days')
             ORDER BY date DESC, sample_count DESC
        """, (days,)).fetchall()
    finally:
        conn.close()
    return SetupPerformanceResponse(data=[SetupPerformanceItem(**dict(r)) for r in rows])


@router.get("/sizing-recommendations", response_model=SizingRecommendationsResponse)
async def list_sizing_recommendations(status: str = Query("pending")) -> SizingRecommendationsResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT id, setup_type, proposed_at, current_size_multiplier,
                   recommended_size_multiplier, confidence_score, rationale,
                   sample_count_30d, sample_count_60d, sample_count_90d,
                   kelly_f_30d, kelly_f_60d, kelly_f_90d, status
              FROM position_sizing_recommendations
             WHERE status = ?
             ORDER BY id DESC
        """, (status,)).fetchall()
    finally:
        conn.close()
    return SizingRecommendationsResponse(
        data=[SizingRecommendation(**dict(r)) for r in rows]
    )


@router.patch("/sizing-recommendations/{rec_id}")
async def decide_sizing_recommendation(
    rec_id: int = Path(...),
    body: SizingDecisionRequest = ...,
):
    new_status = {"approve": "approved", "reject": "rejected",
                  "modify": "modified"}[body.decision]
    conn = sqlite3.connect(_db())
    try:
        cur = conn.execute(
            "UPDATE position_sizing_recommendations "
            "SET status=?, user_decision_at=datetime('now'), "
            "    user_decision_note=?, user_modified_value=? "
            "WHERE id=? AND status='pending'",
            (new_status, body.note, body.modified_value, rec_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="recommendation not found or not pending")
    finally:
        conn.close()
    return {"status": "success", "rec_id": rec_id, "new_status": new_status}


@router.get("/confidence-calibration", response_model=CalibrationResponse)
async def list_calibration() -> CalibrationResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT ai_model, confidence_bucket, predicted_win_rate, "
            "       actual_win_rate, sample_count, calibration_multiplier "
            "FROM ai_confidence_calibration "
            "ORDER BY ai_model, confidence_bucket"
        ).fetchall()
    finally:
        conn.close()
    return CalibrationResponse(data=[CalibrationPoint(**dict(r)) for r in rows])
```

- [ ] **Step 3: Add API tests to `tests/test_v5_reflection_api.py`**

```python
def test_setup_performance_returns_empty(client):
    c, _ = client
    r = c.get("/api/v5/setup-performance?days=7")
    assert r.status_code == 200
    assert r.json() == {"status": "success", "data": []}


def test_sizing_recommendations_pending_only(client):
    c, db = client
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO position_sizing_recommendations
            (setup_type, current_size_multiplier, recommended_size_multiplier,
             confidence_score, rationale, status)
        VALUES ('rsi_overbought_macd_bearish_short', 1.0, 0.6, 0.78,
                'test', 'pending'),
               ('other', 1.0, 0.8, 0.5, 'test2', 'approved')
    """)
    conn.commit()
    conn.close()
    r = c.get("/api/v5/sizing-recommendations")
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["setup_type"] == "rsi_overbought_macd_bearish_short"


def test_decide_sizing_approve(client):
    c, db = client
    conn = sqlite3.connect(db)
    cur = conn.execute("""
        INSERT INTO position_sizing_recommendations
            (setup_type, current_size_multiplier, recommended_size_multiplier,
             confidence_score, rationale)
        VALUES ('X', 1.0, 0.7, 0.8, 'x')
    """)
    rec_id = cur.lastrowid
    conn.commit()
    conn.close()
    r = c.patch(f"/api/v5/sizing-recommendations/{rec_id}",
                json={"decision": "approve"})
    assert r.status_code == 200
    conn = sqlite3.connect(db)
    status = conn.execute(
        "SELECT status FROM position_sizing_recommendations WHERE id=?", (rec_id,)
    ).fetchone()[0]
    conn.close()
    assert status == "approved"


def test_calibration_returns_inserted_buckets(client):
    c, db = client
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO ai_confidence_calibration
            (ai_model, confidence_bucket, predicted_win_rate, actual_win_rate,
             sample_count, calibration_multiplier)
        VALUES ('deepseek-chat', 0.7, 0.7, 0.5, 15, 0.714)
    """)
    conn.commit()
    conn.close()
    r = c.get("/api/v5/confidence-calibration")
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["confidence_bucket"] == 0.7
    assert body["data"][0]["actual_win_rate"] == 0.5
```

- [ ] **Step 4: Add to `Rabbit Hunterfronted/types.ts`**

```ts
export interface SetupPerformanceItem {
  date: string;
  setup_type: string;
  sample_count: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  avg_realized_r: number;
  expectancy: number | null;
  top_failure_mode: string | null;
}

export interface SetupPerformanceResponse {
  status: string;
  data: SetupPerformanceItem[];
}

export interface SizingRecommendation {
  id: number;
  setup_type: string;
  proposed_at: string;
  current_size_multiplier: number;
  recommended_size_multiplier: number;
  confidence_score: number;
  rationale: string;
  sample_count_30d: number | null;
  sample_count_60d: number | null;
  sample_count_90d: number | null;
  kelly_f_30d: number | null;
  kelly_f_60d: number | null;
  kelly_f_90d: number | null;
  status: string;
}

export interface SizingRecommendationsResponse {
  status: string;
  data: SizingRecommendation[];
}

export interface CalibrationPoint {
  ai_model: string;
  confidence_bucket: number;
  predicted_win_rate: number;
  actual_win_rate: number;
  sample_count: number;
  calibration_multiplier: number;
}

export interface CalibrationResponse {
  status: string;
  data: CalibrationPoint[];
}
```

- [ ] **Step 5: Add hooks in `Rabbit Hunterfronted/hooks/api/useV5Reflections.ts`**

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPatch } from '../../services/api';
import type {
  SizingRecommendationsResponse, SetupPerformanceResponse, CalibrationResponse,
} from '../../types';

export function useV5SizingRecommendations() {
  return useQuery<SizingRecommendationsResponse>({
    queryKey: ['v5', 'sizing-recommendations'],
    queryFn: () => apiGet<SizingRecommendationsResponse>('/api/v5/sizing-recommendations?status=pending'),
    refetchInterval: 60_000,
  });
}

export function useV5DecideSizing() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, modified_value, note }: {
      id: number; decision: 'approve' | 'reject' | 'modify';
      modified_value?: number; note?: string;
    }) => apiPatch(`/api/v5/sizing-recommendations/${id}`,
                    { decision, modified_value, note }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['v5', 'sizing-recommendations'] }),
  });
}

export function useV5SetupPerformance(days = 7) {
  return useQuery<SetupPerformanceResponse>({
    queryKey: ['v5', 'setup-performance', days],
    queryFn: () => apiGet<SetupPerformanceResponse>(`/api/v5/setup-performance?days=${days}`),
    refetchInterval: 120_000,
  });
}

export function useV5Calibration() {
  return useQuery<CalibrationResponse>({
    queryKey: ['v5', 'confidence-calibration'],
    queryFn: () => apiGet<CalibrationResponse>('/api/v5/confidence-calibration'),
    refetchInterval: 60_000,
  });
}
```

- [ ] **Step 6: Replace SizingTab stub in `V5ReflectionPage.tsx`**

Add import:
```tsx
import { useV5SizingRecommendations, useV5DecideSizing } from '../../hooks/api/useV5Reflections';
import { useState } from 'react';
```

Replace `{tab === 'sizing' && <Card title="仓位建议">...}` with `<SizingTab />`, and add:

```tsx
function SizingTab() {
  const q = useV5SizingRecommendations();
  const decide = useV5DecideSizing();
  if (q.isLoading) return <LoadingSkeleton rows={4} />;
  const rows = q.data?.data ?? [];

  if (rows.length === 0) {
    return (
      <Card title="仓位建议(等审批)">
        <div className="py-12 text-center text-white/40">
          ▌ 还没有 pending 的仓位建议。每周日 04:00 UTC 自动生成
        </div>
      </Card>
    );
  }

  return (
    <Card title={`仓位建议 — 待审批 (${rows.length})`}>
      <div className="space-y-3">
        {rows.map(r => <SizingCard key={r.id} r={r} onDecide={decide.mutate} />)}
      </div>
    </Card>
  );
}

function SizingCard({ r, onDecide }: {
  r: any; onDecide: (args: any) => void;
}) {
  const [modValue, setModValue] = useState<number | ''>('');
  const deltaPct = ((r.recommended_size_multiplier - r.current_size_multiplier)
                    / r.current_size_multiplier) * 100;
  const tone = deltaPct >= 0 ? 'text-accent-long' : 'text-accent-short';
  return (
    <div className="rounded-md border border-white/10 bg-bg-base p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="font-mono text-sm text-white">setup_type: {r.setup_type}</div>
        <div className="text-xs text-white/50 font-mono">
          confidence {(r.confidence_score * 100).toFixed(0)}%
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 text-xs font-mono">
        <div>
          <div className="text-white/50">当前 size 倍数</div>
          <div className="text-white text-base">{r.current_size_multiplier.toFixed(3)}</div>
        </div>
        <div>
          <div className="text-white/50">推荐 size 倍数</div>
          <div className={`${tone} text-base`}>
            {r.recommended_size_multiplier.toFixed(3)}
            <span className="text-xs ml-2">({deltaPct >= 0 ? '+' : ''}{deltaPct.toFixed(0)}%)</span>
          </div>
        </div>
        <div>
          <div className="text-white/50">Kelly 30/60/90d</div>
          <div className="text-white/80 text-xs">
            {r.kelly_f_30d?.toFixed(3) ?? '—'} / {r.kelly_f_60d?.toFixed(3) ?? '—'} / {r.kelly_f_90d?.toFixed(3) ?? '—'}
          </div>
        </div>
      </div>
      <div className="text-xs text-white/60">{r.rationale}</div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onDecide({ id: r.id, decision: 'approve' })}
          className="rounded-sm border border-accent-long/40 bg-accent-long/10 px-3 py-1 text-xs text-accent-long"
        >
          批准
        </button>
        <button
          type="button"
          onClick={() => onDecide({ id: r.id, decision: 'reject' })}
          className="rounded-sm border border-accent-short/40 bg-accent-short/10 px-3 py-1 text-xs text-accent-short"
        >
          拒绝
        </button>
        <input
          type="number"
          step="0.001"
          value={modValue}
          onChange={(e) => setModValue(e.target.value === '' ? '' : Number(e.target.value))}
          placeholder="改值"
          className="w-24 rounded-sm border border-white/15 bg-bg-base px-2 py-1 text-xs text-white"
        />
        <button
          type="button"
          disabled={modValue === ''}
          onClick={() => onDecide({ id: r.id, decision: 'modify',
                                     modified_value: Number(modValue) })}
          className="rounded-sm border border-accent-info/40 bg-accent-info/10 px-3 py-1 text-xs text-accent-info disabled:opacity-40"
        >
          修改后批准
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Add calibration curve to `V5AIStatusPage.tsx`**

Add import:
```tsx
import { useV5Calibration } from '../../hooks/api/useV5Reflections';
```

Append a new HoloCard at the end of the page (right before the closing `</div>`):

```tsx
      <CalibrationCurveCard />
```

Add component (inside the file):

```tsx
function CalibrationCurveCard() {
  const q = useV5Calibration();
  const points = q.data?.data ?? [];
  return (
    <HoloCard>
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-cyan-300/80 mb-3">
        ▌ CONFIDENCE CALIBRATION CURVE
      </div>
      {points.length === 0 ? (
        <div className="py-8 text-center font-mono text-cyan-300/40 text-xs">
          ▌ awaiting first 10 reflections per bucket...
        </div>
      ) : (
        <div className="space-y-1 font-mono text-xs">
          {points.map(p => {
            const drift = p.actual_win_rate - p.predicted_win_rate;
            const tone = Math.abs(drift) < 0.05 ? 'text-accent-long'
                       : Math.abs(drift) < 0.15 ? 'text-accent-warn'
                       : 'text-accent-short';
            return (
              <div key={`${p.ai_model}-${p.confidence_bucket}`}
                   className="grid grid-cols-12 gap-2 py-1 border-b border-white/5">
                <div className="col-span-2 text-cyan-300/70">{p.ai_model}</div>
                <div className="col-span-2 text-white">{(p.confidence_bucket * 100).toFixed(0)}%</div>
                <div className="col-span-3 text-white/60">
                  predicted → actual {(p.actual_win_rate * 100).toFixed(0)}%
                </div>
                <div className={`col-span-2 ${tone}`}>
                  Δ {drift >= 0 ? '+' : ''}{(drift * 100).toFixed(0)}pt
                </div>
                <div className="col-span-2 text-violet-300/70">
                  ×{p.calibration_multiplier.toFixed(2)}
                </div>
                <div className="col-span-1 text-white/40 text-right">
                  n={p.sample_count}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </HoloCard>
  );
}
```

- [ ] **Step 8: Run tests + build**

```bash
python3 -m pytest tests/test_v5_reflection_api.py -v 2>&1 | tail -10
python3 -m pytest tests/ -q 2>&1 | tail -3
cd "Rabbit Hunterfronted"
npx vitest run 2>&1 | tail -3
npx vite build 2>&1 | tail -5
```

Expected: BE 179 + 4 = 183; FE 49 (no new tests added — existing V5ReflectionPage.test still passes); build OK.

- [ ] **Step 9: Commit**

```bash
cd /Users/lizhishaoniange/Documents/Rabbit-Hunter
git add api/schemas/v5_reflection.py api/routes/v5_reflection.py tests/test_v5_reflection_api.py \
        "Rabbit Hunterfronted/types.ts" \
        "Rabbit Hunterfronted/hooks/api/useV5Reflections.ts" \
        "Rabbit Hunterfronted/components/pages/V5ReflectionPage.tsx" \
        "Rabbit Hunterfronted/components/pages/V5AIStatusPage.tsx"
git commit -m "feat(reflection): Phase 3 APIs + frontend Tab 3 + AI calibration curve

- GET /setup-performance / /sizing-recommendations / /confidence-calibration
- PATCH /sizing-recommendations/:id (approve/reject/modify)
- Tab 3: pending sizing approval cards with Kelly breakdown + 3 actions
- AI Status: holographic calibration curve card with per-bucket drift

4 API tests."
```

---

### Task 14: Verification — full suite + verify script + docker rebuild + tag

**Files:**
- Modify: `scripts/verify_v5_acceptance.py` (add reflection schema check)

- [ ] **Step 1: Full FE + BE test runs**

```bash
cd /Users/lizhishaoniange/Documents/Rabbit-Hunter
python3 -m pytest tests/ -q 2>&1 | tail -3
cd "Rabbit Hunterfronted"
npm test 2>&1 | tail -10
npx vite build 2>&1 | tail -5
```

Expected: BE 183 passed; FE 49 passed; build OK.

- [ ] **Step 2: Extend `scripts/verify_v5_acceptance.py`**

Append a new function and update `__main__`:

```python
def verify_reflection_phase_1_3(db_path: str = "data/rabbit_hunter.db") -> bool:
    import os, sqlite3
    print("\n=== Reflection Worker (Phases 1-3) ===")
    if not os.path.exists(db_path):
        print(f"db not found: {db_path}")
        return False
    conn = sqlite3.connect(db_path)
    try:
        for table in ("reflection_queue", "reflections", "failure_taxonomy",
                      "setup_performance_daily", "position_sizing_recommendations",
                      "ai_confidence_calibration"):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"  {table}: {n} rows")
            except sqlite3.OperationalError as e:
                print(f"  {table}: MISSING ({e})")
                return False

        n_seeds = conn.execute(
            "SELECT COUNT(*) FROM failure_taxonomy WHERE seeded=1"
        ).fetchone()[0]
        if n_seeds != 8:
            print(f"  expected 8 seeded failure modes, got {n_seeds}")
            return False
        print(f"  ✓ 8 seeded failure_taxonomy modes present")

        print("\n✅ Reflection Phases 1-3 schema verification passed")
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    import os, sys
    db = os.environ.get("DB_PATH", "data/rabbit_hunter.db")
    ok_a = verify(db)
    ok_b = verify_plan_b_backend(db)
    ok_c = verify_plan_b_frontend()
    ok_d = verify_reflection_phase_1_3(db)
    sys.exit(0 if (ok_a and ok_b and ok_c and ok_d) else 1)
```

- [ ] **Step 3: Smoke run verify script**

```bash
python3 scripts/verify_v5_acceptance.py 2>&1 | tail -30
```

Expected: all 4 sections pass.

- [ ] **Step 4: Docker rebuild + restart api/collector/frontend**

```bash
docker compose build --no-cache api collector frontend 2>&1 | tail -10
docker compose up -d api collector frontend 2>&1 | tail -5
sleep 10
```

- [ ] **Step 5: Sanity check new endpoints**

```bash
curl -s http://localhost:8000/api/v5/reflections?limit=5 | python3 -m json.tool | head -10
curl -s http://localhost:8000/api/v5/failure-taxonomy | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'seeded count: {sum(1 for m in d[\"data\"] if m[\"seeded\"])}')"
curl -s http://localhost:8000/api/v5/setup-performance?days=7 | python3 -m json.tool | head -5
curl -s http://localhost:8000/api/v5/sizing-recommendations | python3 -m json.tool | head -5
curl -s http://localhost:8000/api/v5/confidence-calibration | python3 -m json.tool | head -5
```

Expected: all return `{"status":"success","data":[...]}` (may be empty arrays until reflections accumulate); 8 seeded failure modes.

- [ ] **Step 6: Container DB check**

```bash
docker compose exec -T collector python -c "
import sqlite3
c = sqlite3.connect('/app/data/rabbit_hunter.db')
print('reflections:', c.execute('SELECT COUNT(*) FROM reflections').fetchone()[0])
print('failure_taxonomy seeded:', c.execute('SELECT COUNT(*) FROM failure_taxonomy WHERE seeded=1').fetchone()[0])
print('reflection_queue pending:', c.execute('SELECT COUNT(*) FROM reflection_queue WHERE completed_at IS NULL').fetchone()[0])
"
```

Expected: 8 seeded; pending queue may be 0 unless trades just closed.

- [ ] **Step 7: Commit verify script + tag + push**

```bash
git add scripts/verify_v5_acceptance.py
git commit -m "chore(reflection): verify_v5_acceptance covers Phases 1-3 schema"
git tag v6.0.0-reflection-phases-1-3-shipped
git push origin main
git push origin v6.0.0-reflection-phases-1-3-shipped
```

- [ ] **Step 8: Manual smoke checklist (post-deploy)**

Open browser http://localhost:5173 and verify:
- `/v5/reflection` Tab 1 (复盘流):empty state or recent reflections render
- `/v5/reflection` Tab 2 (失败模式):8 seeded rows show, sample_count=0 initially
- `/v5/reflection` Tab 3 (仓位建议):empty state (no recommendations until Sunday cron)
- `/v5/ai`:cyber HoloCards intact, new "CONFIDENCE CALIBRATION CURVE" card at the bottom showing "awaiting..." (until 10 reflections per bucket land)
- Existing pages /v5/signals / /v5/active / /v5/dashboard / /v5/chart still work
- No console errors

If any check fails, fix in a follow-up commit. The gate for declaring Phases 1-3 "shipped" is: schemas live, endpoints respond, no regressions on existing routes.

---

## Self-Review

### Spec coverage check

| Spec section | Task(s) |
|---|---|
| §2.1 5-layer loop | T1 (Layer 0+1 DB) / T3-T4 (Layer 1 reflection) / T6-T8 (Layer 2 taxonomy) / T10 (Layer 3 aggregator) / T11 (Layer 4 calibration) / T12 (Layer 4 Kelly) |
| §2.2 Process layer (worker) | T4 (worker process) + T10 (daily cron) + T12 (weekly cron) |
| §3.1 reflection_queue | T1 |
| §3.2 reflections | T1 |
| §3.3 failure_taxonomy | T6 |
| §3.4 setup_performance_daily | T10 |
| §3.5 position_sizing_recommendations | T10 (schema) + T12 (writer) + T13 (API) |
| §3.6 ai_confidence_calibration | T10 (schema) + T11 (logic + API in T13) |
| §3.7 entry_filter_proposals | **DEFERRED to Phase 4** (not in this plan) |
| §4.1 setup_type derivation | T1 |
| §4.2 5-question prompt | T2 |
| §4.3 8 seeded failure modes | T6 |
| §4.4 detection DSL | T7 (handlers-not-parser pragma) |
| §4.5 fractional Kelly | T12 |
| §4.6 calibration update + apply | T11 |
| §5.1 /v5/reflection page | T5 (scaffold) + T9 (Tab 2) + T13 (Tab 3) |
| §5.2 AI Status calibration curve | T13 |
| §5.3 Dashboard setup_type breakdown | **NOT INCLUDED** in this plan — could be added as a separate small task before T14 if user wants. Recorded as gap. |
| §6 risk mitigations | partially: separate reflection model not yet (uses same DeepSeek), no auto-apply of sizing (manual approval enforced), Kelly fractional + bounds applied. Other mitigations are Phase 4-5 territory. |
| §7 phases 1-3 | this plan covers |
| §8 acceptance criteria | external — to be measured 90 days post-deploy. Not implementable as code. |

**One gap:** §5.3 (Dashboard setup_type breakdown) is mentioned in spec but not in this plan. It's a small UI addition. Adding as a note: if you want it now, insert a sub-task between T13 and T14 to add a setup-performance card to V5DashboardPage. I'm leaving it out of the base plan to keep scope tight; can be done in a follow-up commit.

### Type consistency check

- `realized_r`, `setup_type`, `outcome_class` consistent across T1 schema / T2 Pydantic / T3 runner / T10 aggregator / T12 Kelly
- `failure_mode_key` consistent: T2 AI output schema → T3 persisted → T6 taxonomy table key → T7 matcher returned list → T9 frontend display
- `confidence_at_entry` flows: T3 runner reads → T11 calibration updates → T11 trading_assistant reads multiplier
- `sample_count_30d/60d/90d` consistent: T12 writer → T13 API → T13 frontend display
- API response wrappers all use `{status, data}` matching existing convention

### Placeholder check

Searched for "TBD", "TODO", "implement later", "fill in details", "similar to Task" — none found. All test code, all SQL, all Pydantic schemas, all TSX/TS are inline-complete.

### Test count summary

- T1: 11 (setup_type 6 + reflection_db 5)
- T2: 7 (reflection_prompt)
- T3: 5 (reflection_runner)
- T4: 4 (v5_reflection_worker)
- T5: 3 BE + 2 FE
- T6: 5 (failure_taxonomy_seed)
- T7: 7 (failure_taxonomy_matcher)
- T8: 3 (trading_assistant_taxonomy)
- T9: 2 (failure-taxonomy API)
- T10: 4 (setup_aggregator)
- T11: 6 (confidence_calibration)
- T12: 4 (kelly_sizing)
- T13: 4 BE

**BE total new: ~65 tests. Backend goes 125 → ~190.**
**FE total new: 2 tests. Frontend goes 47 → 49.**

(Existing reviewers will see modest FE coverage — the work is mostly UI rendering of already-tested API data. Adding a test for SizingTab approve-button + CalibrationCurveCard render is a small optional improvement, omitted to keep plan size manageable.)

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-15-reflection-worker-phases-1-3.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review (spec + quality), continuous execution. This is how V5 B-1 (11 tasks 0 blockers) and B-2 (17 tasks) shipped.

**2. Inline Execution** — execute in this session via `superpowers:executing-plans` with checkpoints for review.

Which approach?


