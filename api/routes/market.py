"""
市场数据路由

端点:
  GET  /api/v43/anatomy/{symbol:path}/chart-data
  POST /api/v43/anatomy/{symbol:path}/ai-explain
  GET  /api/v43/anatomy/{symbol:path}
  GET  /api/v43/market-depth/{symbol:path}
"""

import os
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from api.dependencies import get_supabase_optional
from api.schemas.common import ApiResponse
from api.services.market_service import snap_to_valid_depth_limit, get_testnet_config, build_ccxt_config

router = APIRouter(prefix="/api/v43", tags=["market"])


# ============================================
# Pydantic 模型（市场路由专用）
# ============================================


class AnatomyAIExplainRequest(BaseModel):
    symbol: str
    score: float
    reason: str
    atr: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reward_risk_ratio: Optional[float] = None
    phase: Optional[str] = None


class AnatomyResponse(BaseModel):
    status: str
    code: int
    data: dict


# ============================================
# 注意：更具体的路由必须放在更通用的 {symbol:path} 路由之前
# ============================================


@router.get("/anatomy/{symbol:path}/chart-data")
async def get_chart_data(
    symbol: str,
    timeframe: str = Query("15m", description="时间周期"),
    limit: int = Query(100, description="K 线数量", ge=1, le=1000),
):
    """
    获取图表数据（TradingView 格式）

    FastAPI 会自动解码 URL 编码的路径参数，所以 symbol 参数已经是解码后的值。
    """
    try:
        symbol = unquote(symbol)
        print(f"[INFO] /api/v43/anatomy/{symbol}/chart-data: 接收到的 symbol 参数: {symbol}")

        from scripts.v43_anatomy_analyzer import get_anatomy_analyzer  # type: ignore[import-not-found]

        analyzer = get_anatomy_analyzer()
        result = analyzer.get_chart_data(symbol, timeframe, limit)

        if not result:
            print(f"[WARNING] /api/v43/anatomy/{symbol}/chart-data: 未获取到 K 线数据")
            return []

        print(f"[INFO] /api/v43/anatomy/{symbol}/chart-data: 返回 {len(result)} 根 K 线")
        return result
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取图表数据失败: {str(e)}",
        )


@router.post("/anatomy/{symbol:path}/ai-explain")
async def explain_anatomy(symbol: str, payload: AnatomyAIExplainRequest):
    """使用 DeepSeek 生成深度解剖台的 AI 文本解释。"""
    try:
        decoded_symbol = unquote(symbol)
        from scripts.v43_deepseek_constrained import DeepSeekConstrained  # type: ignore[import-not-found]

        ds = DeepSeekConstrained()
        if not ds.is_ready():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="DeepSeek API 未配置",
            )

        context = {
            "atr": payload.atr,
            "stop_loss": payload.stop_loss,
            "take_profit": payload.take_profit,
            "reward_risk_ratio": payload.reward_risk_ratio,
            "phase": payload.phase,
        }

        text = ds.generate_anatomy_explanation(
            decoded_symbol,
            float(payload.score),
            payload.reason,
            context=context,
        )
        if not text:
            text = f"AI: 对 {decoded_symbol} 评分 {payload.score:.1f}，当前更偏向观望或轻仓试探。"

        return {"status": "success", "code": 200, "data": {"text": text}}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成 AI 解释失败: {str(e)}",
        )


# NOTE: 通用 {symbol:path} 路由必须放在所有 /anatomy/{symbol:path}/* 子路由之后
@router.get("/anatomy/{symbol:path}", response_model=AnatomyResponse)
async def get_anatomy(
    symbol: str,
    timeframe: str = Query("15m", description="时间周期"),
    supabase=Depends(get_supabase_optional),
):
    """
    获取币种深度分析

    返回结构性缺口、蜡烛图形态、权重分布、止损/盈利比推荐。
    """
    try:
        symbol = unquote(symbol)
        print(f"[INFO] /api/v43/anatomy/{symbol}: 接收到的 symbol 参数: {symbol}")

        from scripts.v43_anatomy_analyzer import get_anatomy_analyzer  # type: ignore[import-not-found]

        analyzer = get_anatomy_analyzer()
        analyzer.supabase = supabase

        result = analyzer.analyze_symbol(symbol, timeframe)

        return AnatomyResponse(status="success", code=200, data=result)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"分析币种失败: {str(e)}",
        )


# NOTE: market-depth/{symbol:path} is also path-parameterized, put after anatomy routes
@router.get("/market-depth/{symbol:path}")
async def get_market_depth(
    symbol: str,
    limit: int = Query(20, description="盘口深度条数（每边）", ge=1, le=100),
):
    """
    获取币安市场深度（Order Book）

    - 使用 CCXT 公共接口获取 order book
    - 不依赖私有 API Key
    - 前端期望返回格式: { bids: [[price, amount], ...], asks: [[price, amount], ...] }
    - Binance API 只支持 limit: 5, 10, 20, 50, 100, 500, 1000
    """
    try:
        decoded_symbol = unquote(symbol)

        import ccxt  # type: ignore[import-not-found]

        binance_limit = snap_to_valid_depth_limit(limit)
        if binance_limit != limit:
            print(f"[INFO] 市场深度 limit={limit} 映射到 Binance 有效值: {binance_limit}")

        testnet = get_testnet_config()
        config = build_ccxt_config(testnet)
        exchange = ccxt.binanceusdm(config)

        binance_symbol = decoded_symbol.replace("/", "")
        order_book = exchange.fetch_order_book(binance_symbol, limit=binance_limit)

        bids = order_book.get("bids", [])[:limit]
        asks = order_book.get("asks", [])[:limit]

        return {
            "bids": bids,
            "asks": asks,
            "symbol": decoded_symbol,
            "binanceSymbol": binance_symbol,
            "limit": limit,
            "binanceLimit": binance_limit,
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取市场深度失败: {str(e)}",
        )
