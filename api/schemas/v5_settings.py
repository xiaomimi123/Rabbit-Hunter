"""V5 系统设置 schema。"""
from typing import Optional, Literal
from pydantic import BaseModel


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
