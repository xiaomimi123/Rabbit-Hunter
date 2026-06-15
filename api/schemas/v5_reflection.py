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


PROMPT_VERSION = "reflection-prompt-v1"
