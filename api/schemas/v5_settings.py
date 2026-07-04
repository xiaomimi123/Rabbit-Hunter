"""V5 系统设置 schema。"""
from typing import Optional, Literal
from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    exchange: Literal["okx", "binance"]

    openai_api_key_masked: str = ""
    openai_assistant_id: Optional[str] = None
    openai_vector_store_id: Optional[str] = None

    deepseek_api_key_masked: str = ""
    deepseek_enabled: bool = False

    active_ai_provider: Optional[Literal["openai", "deepseek"]] = None
    active_chat_model: Optional[str] = None

    system_mode: Literal["SHADOW", "LIVE"]
    enable_auto_trading: bool

    ai_fail_open: bool
    sl_tp_fail_open: bool
    v5_max_concurrent: int = 3


class SettingsPatchRequest(BaseModel):
    """全部字段可选。Key 字段 '' 视为清空,不提交则保留原值。"""
    exchange: Optional[Literal["okx", "binance"]] = None
    openai_api_key: Optional[str] = None
    openai_assistant_id: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    deepseek_enabled: Optional[bool] = None
    system_mode: Optional[Literal["SHADOW", "LIVE"]] = None
    enable_auto_trading: Optional[bool] = None
    ai_fail_open: Optional[bool] = None
    sl_tp_fail_open: Optional[bool] = None
    v5_max_concurrent: Optional[int] = Field(default=None, ge=1, le=10)


class TestAIRequest(BaseModel):
    """测试 AI 连接。可选传入候选 key — 传了就用候选,不传就用 DB 里现有的。"""
    provider: Optional[Literal["openai", "deepseek"]] = None
    deepseek_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None


class TestAIResponse(BaseModel):
    ok: bool
    provider: Optional[Literal["openai", "deepseek"]] = None
    model: Optional[str] = None
    latency_ms: Optional[int] = None
    response_text: Optional[str] = None       # AI 实际返回的内容(测试时一般是 "ok")
    error_type: Optional[Literal[
        "insufficient_balance", "auth_failed", "rate_limit",
        "network", "no_key_configured", "unknown",
    ]] = None
    message: str                              # 给用户看的中文描述
