"""
交易分数路由

端点:
  GET /api/v43/trade-scores
  GET /api/v43/kill-queue
  GET /api/v43/trade-score/{symbol:path}   ← 必须放最后，避免与上面冲突
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import get_supabase, get_supabase_optional
from api.schemas.scores import TradeScoreV43Response, KillQueueResponse
from api.services.score_service import format_trade_score, format_kill_queue_item
from api.services.market_service import fetch_market_price_and_change

router = APIRouter(prefix="/api/v43", tags=["scores"])


@router.get("/trade-scores", response_model=List[TradeScoreV43Response])
async def get_v43_trade_scores(
    limit: int = Query(50, description="返回的记录数，最多 200", ge=1, le=200),
    symbol: Optional[str] = Query(None, description="筛选币种"),
    executed: Optional[bool] = Query(None, description="筛选是否执行"),
    supabase=Depends(get_supabase),
):
    """
    获取 V4.3 交易分数记录

    返回交易分数列表，支持筛选和分页。
    """
    try:
        query = supabase.table("trade_scores_v43").select("*")

        if symbol:
            query = query.eq("symbol", symbol)

        if executed is not None:
            query = query.eq("executed", executed)

        response = (
            query
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        return [format_trade_score(r) for r in (response.data or [])]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取交易分数失败: {str(e)}",
        )


@router.get("/kill-queue", response_model=KillQueueResponse)
async def get_kill_queue(
    limit: int = Query(20, description="最多返回币种数", ge=1, le=100),
    minScore: float = Query(60.0, description="最低 AI 评分", ge=0.0, le=100.0),
    phase: Optional[str] = Query(None, description="阶段过滤（逗号分隔，如：P3A,P3B）"),
    sortBy: str = Query("score", description="排序方式", regex="^(score|age)$"),
    offset: int = Query(0, description="分页偏移", ge=0),
    supabase=Depends(get_supabase_optional),
):
    """
    获取猎杀队列（按 AI 评分排序的币种列表）

    返回满足条件的交易机会，按评分或阶段年龄排序。
    """
    try:
        # 优先使用 KillQueueManager
        from scripts.v43_kill_queue_manager import get_kill_queue_manager  # type: ignore[import-not-found]

        manager = get_kill_queue_manager()
        manager.supabase = supabase

        phase_list = None
        if phase:
            phase_list = [p.strip().upper() for p in phase.split(",")]

        result = manager.get_kill_queue(
            limit=limit,
            min_score=minScore,
            phase_filter=phase_list,
            sort_by=sortBy,
            offset=offset,
        )

        return KillQueueResponse(
            status="success",
            code=200,
            data=result["data"],
            pagination=result["pagination"],
            metadata=result["metadata"],
        )
    except ImportError:
        # 降级：直接查询数据库
        return await _get_kill_queue_fallback(
            supabase=supabase,
            limit=limit,
            minScore=minScore,
            phase=phase,
            sortBy=sortBy,
            offset=offset,
        )


async def _get_kill_queue_fallback(
    supabase,
    limit: int,
    minScore: float,
    phase: Optional[str],
    sortBy: str,
    offset: int,
) -> KillQueueResponse:
    """KillQueueManager 不可用时的降级实现：直接查询 trade_scores_v43。"""
    if supabase is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase 未配置",
        )

    try:
        min_score_normalized = minScore / 100.0
        query = supabase.table("trade_scores_v43").select("*").gte("final_score", min_score_normalized)

        phase_list = []
        if phase:
            phase_list = [p.strip().upper() for p in phase.split(",")]

        if sortBy == "score":
            query = query.order("final_score", desc=True)
        else:
            query = query.order("created_at", desc=True)

        response = query.range(offset, offset + limit - 1).limit(limit).execute()

        count_response = (
            supabase.table("trade_scores_v43")
            .select("id", count="exact")
            .gte("final_score", min_score_normalized)
            .execute()
        )
        total = (
            count_response.count
            if hasattr(count_response, "count") and count_response.count is not None
            else len(response.data or [])
        )

        items = []
        for record in response.data or []:
            symbol = record.get("symbol", "")
            price_value, change_24h = fetch_market_price_and_change(supabase, symbol)
            items.append(format_kill_queue_item(record, price_value, change_24h))

        if phase_list:
            items = [item for item in items if item.get("phase") in phase_list]
            total = len(items)

        return KillQueueResponse(
            status="success",
            code=200,
            data=items,
            pagination={
                "total": total,
                "limit": limit,
                "offset": offset,
                "pages": (total + limit - 1) // limit if limit > 0 else 0,
            },
            metadata={
                "updatedAt": datetime.now().isoformat(),
                "dataFreshness": "1s",
                "systemHealth": 0.98,
            },
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取猎杀队列失败: {str(e)}",
        )


# NOTE: {symbol:path} route MUST be registered last in this router
@router.get("/trade-score/{symbol:path}", response_model=TradeScoreV43Response)
async def get_v43_trade_score_for_symbol(
    symbol: str,
    supabase=Depends(get_supabase),
):
    """
    获取指定币种的最新 V4.3 交易分数

    返回该币种最近一次的交易分数记录。
    """
    try:
        response = (
            supabase.table("trade_scores_v43")
            .select("*")
            .eq("symbol", symbol)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到 {symbol} 的交易分数记录",
            )

        return format_trade_score(response.data[0])
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取交易分数失败: {str(e)}",
        )
