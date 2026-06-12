"""V5 策略配置 schema。"""
from typing import List, Optional, Union
from pydantic import BaseModel


class ParamSpec(BaseModel):
    """单个参数:当前值 + 默认 + 范围 + 单位 + 说明。"""
    key: str
    value: float
    default: float
    min: float
    max: float
    unit: str = ""
    description: str = ""


class StrategyConfigResponse(BaseModel):
    params: List[ParamSpec]


class StrategyConfigPatchRequest(BaseModel):
    """前端 PATCH 一次只改若干个 key。"""
    updates: dict[str, float]


class StrategyConfigPreviewResponse(BaseModel):
    """回测预览。"""
    candidate_params: dict[str, float]
    estimated_hourly_entries: float
    estimated_win_rate: float
    sample_days: int
