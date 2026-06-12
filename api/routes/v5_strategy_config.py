"""/api/v5/strategy-config — GET/PATCH/preview。

GET     返回 13 个 V5 旋钮当前值 + default + range + unit + description
PATCH   写 system_settings + invalidate v5_params cache
POST /preview  基于过去 N 天 trade_scores_v5 估算 新阈值下入场频率 + 胜率
"""
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, status

from api.schemas.v5_strategy_config import (
    ParamSpec, StrategyConfigResponse,
    StrategyConfigPatchRequest, StrategyConfigPreviewResponse,
)
from scripts.v5_params import (
    get_param, invalidate_cache, DEFAULTS, PARAM_META,
)


router = APIRouter(prefix="/api/v5", tags=["strategy-config"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def _cast_for(key: str):
    """返回该 key 该用的 Python cast。"""
    default = DEFAULTS.get(key)
    if isinstance(default, bool):
        return lambda v: str(v).lower() in ("1", "true", "yes")
    if isinstance(default, int):
        return int
    return float


@router.get("/strategy-config", response_model=StrategyConfigResponse)
async def get_strategy_config() -> StrategyConfigResponse:
    params = []
    for key, default in DEFAULTS.items():
        meta = PARAM_META.get(key, (0, 0, "", ""))
        cur = get_param(key, default, _cast_for(key))
        params.append(ParamSpec(
            key=key,
            value=float(cur),
            default=float(default),
            min=float(meta[0]),
            max=float(meta[1]),
            unit=meta[2],
            description=meta[3],
        ))
    return StrategyConfigResponse(params=params)


@router.patch("/strategy-config", response_model=StrategyConfigResponse)
async def patch_strategy_config(req: StrategyConfigPatchRequest) -> StrategyConfigResponse:
    db = _db()
    # 校验
    for key, val in req.updates.items():
        if key not in DEFAULTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown param key: {key}",
            )
        lo, hi, _, _ = PARAM_META.get(key, (None, None, "", ""))
        if lo is not None and not (float(lo) <= float(val) <= float(hi)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{key}={val} out of range [{lo}, {hi}]",
            )

    # 写 DB(INSERT 新行,旧行保留审计)
    conn = sqlite3.connect(db)
    try:
        for key, val in req.updates.items():
            # 整数型参数存为整数字符串，浮点型存为浮点字符串
            cast = _cast_for(key)
            typed = cast(val)
            # 整形 default 的参数或值为整数的浮点数，省略小数点
            if isinstance(typed, float) and typed == int(typed):
                stored = str(int(typed))
            else:
                stored = str(typed)
            conn.execute(
                "INSERT INTO system_settings (key, value, created_at) "
                "VALUES (?, ?, datetime('now'))",
                (key, stored),
            )
        conn.commit()
    finally:
        conn.close()

    invalidate_cache()
    return await get_strategy_config()


@router.post("/strategy-config/preview", response_model=StrategyConfigPreviewResponse)
async def preview_strategy_config(req: dict) -> StrategyConfigPreviewResponse:
    """快速估算:候选阈值下,过去 7 天 trade_scores_v5 的入场频率 + 胜率。"""
    candidate = req.get("candidate_params", {})
    db = _db()
    sample_days = 7
    conn = sqlite3.connect(db)
    try:
        overbought = float(candidate.get("v5_rsi_overbought", DEFAULTS["v5_rsi_overbought"]))
        oversold = float(candidate.get("v5_rsi_oversold", DEFAULTS["v5_rsi_oversold"]))

        would_trade = conn.execute(
            "SELECT COUNT(*) FROM trade_scores_v5 "
            "WHERE created_at >= datetime('now', '-7 day') "
            "  AND ((side='SHORT' AND rsi_15m > ?) "
            "    OR (side='LONG'  AND rsi_15m < ?))",
            (overbought, oversold),
        ).fetchone()[0] or 0

        days_have_data = conn.execute(
            "SELECT MIN(7, CAST((julianday('now') - julianday(MIN(created_at))) AS INTEGER)) "
            "FROM trade_scores_v5"
        ).fetchone()[0] or 0
        sample_days = int(days_have_data) if days_have_data else 0

        hourly = (would_trade / max(sample_days, 1)) / 24.0

        wins = conn.execute(
            "SELECT COUNT(*) FROM ai_training_data "
            "WHERE outcome='WIN' "
            "  AND ((side='SHORT' AND entry_rsi_15m > ?) "
            "    OR (side='LONG'  AND entry_rsi_15m < ?))",
            (overbought, oversold),
        ).fetchone()[0] or 0
        totals = conn.execute(
            "SELECT COUNT(*) FROM ai_training_data "
            "WHERE outcome IN ('WIN','LOSS','FLAT') "
            "  AND ((side='SHORT' AND entry_rsi_15m > ?) "
            "    OR (side='LONG'  AND entry_rsi_15m < ?))",
            (overbought, oversold),
        ).fetchone()[0] or 0
        win_rate = (wins / totals) if totals else 0.0
    finally:
        conn.close()

    return StrategyConfigPreviewResponse(
        candidate_params=candidate,
        estimated_hourly_entries=round(hourly, 2),
        estimated_win_rate=round(win_rate, 3),
        sample_days=sample_days,
    )
