"""
持仓路由

端点:
  GET  /api/v43/positions
  POST /api/v43/trade/open
  POST /api/v43/trade/close
"""

import os
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_supabase, get_supabase_optional, check_kill_switch
from api.schemas.positions import (
    TradeOpenRequest,
    TradeCloseRequest,
    TradeResponse,
)
from api.services.position_service import format_positions

router = APIRouter(prefix="/api/v43", tags=["positions"])


@router.get("/positions")
async def get_v43_positions(supabase=Depends(get_supabase)):
    """
    获取 V4.3 持仓列表

    返回所有未平仓的持仓。
    """
    try:
        response = (
            supabase.table("positions_v43")
            .select("*")
            .eq("status", "OPEN")
            .order("created_at", desc=True)
            .execute()
        )

        formatted_positions = format_positions(response.data or [])

        return {
            "status": "success",
            "code": 200,
            "data": {
                "active": formatted_positions,
                "total": len(formatted_positions),
            },
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取持仓列表失败: {str(e)}",
        )


@router.post("/trade/open", response_model=TradeResponse)
async def open_v43_position(
    request: TradeOpenRequest,
    supabase=Depends(get_supabase_optional),
):
    """
    开仓（V4.3）

    根据 V4.3 决策执行开仓操作。
    """
    # 检查 Kill Switch
    if check_kill_switch(supabase):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kill Switch 已开启，禁止交易",
        )

    try:
        from scripts.binance_trader import BinanceTrader  # type: ignore[import-not-found]

        api_key = os.environ.get("BINANCE_API_KEY")
        api_secret = os.environ.get("BINANCE_API_SECRET")
        if not api_key or not api_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="BINANCE_API_KEY / BINANCE_API_SECRET 未配置",
            )

        testnet = os.environ.get("BINANCE_TESTNET", "false").lower() == "true"
        leverage = int(os.environ.get("BINANCE_LEVERAGE", "10"))
        trader = BinanceTrader(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
            leverage=leverage,
        )

        # 获取当前市场价格
        entry_price = request.price
        if entry_price is None:
            binance_symbol = request.symbol.replace("/", "")
            ticker = trader.exchange.fetch_ticker(binance_symbol)
            entry_price = ticker.get("last")
            if not entry_price:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"无法获取 {request.symbol} 当前价格",
                )

        # 执行真实开仓
        trade_result = trader.open_position(
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type or "MARKET",
            price=entry_price if (request.order_type or "MARKET").upper() == "LIMIT" else None,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
        )

        if not trade_result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"交易所拒绝订单: {trade_result.get('error', '未知错误')}",
            )

        order_id = trade_result.get("order_id")
        filled_price = trade_result.get("price") or entry_price

        # 写入 DB（交易成功后才写入）
        if supabase is not None:
            try:
                supabase.table("positions_v43").insert({
                    "symbol": request.symbol,
                    "side": request.side,
                    "entry_price": filled_price,
                    "position_size": request.quantity,
                    "stop_price": request.stop_loss,
                    "take_profit": request.take_profit,
                    "status": "OPEN",
                    "order_id": order_id,
                    "created_at": datetime.now().isoformat(),
                }).execute()
            except Exception as db_err:
                print(f"[CRITICAL] 交易成功但 DB 写入失败: {request.symbol} order={order_id} err={db_err}")

        return TradeResponse(
            success=True,
            order_id=order_id,
            symbol=request.symbol,
            message=f"开仓成功（{request.side} {request.quantity} {request.symbol} @ {filled_price}）",
            timestamp=datetime.now().isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"开仓失败: {str(e)}",
        )


@router.post("/trade/close", response_model=TradeResponse)
async def close_v43_position(
    request: TradeCloseRequest,
    supabase=Depends(get_supabase_optional),
):
    """
    平仓（V4.3）

    根据 V4.3 决策执行平仓操作。
    """
    # 检查 Kill Switch
    if check_kill_switch(supabase):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kill Switch 已开启，禁止交易",
        )

    try:
        from scripts.v43_position_manager import V43PositionManager  # type: ignore[import-not-found]
        from scripts.binance_trader import BinanceTrader  # type: ignore[import-not-found]

        # 初始化交易器（如果配置了币安 API）
        trader = None
        if os.environ.get("BINANCE_API_KEY") and os.environ.get("BINANCE_API_SECRET"):
            trader = BinanceTrader()

        # 初始化持仓管理器
        position_manager = V43PositionManager(
            supabase_client=supabase,
            trader=trader,
        )

        # 获取当前市价（用于计算平仓 PnL）
        exit_price = 0.0
        try:
            if trader:
                binance_symbol = request.symbol.replace("/", "")
                ticker = trader.exchange.fetch_ticker(binance_symbol)
                exit_price = float(ticker.get("last") or 0)
        except Exception:
            pass
        # 若无法获取市价，从数据库持仓记录取 current_price 作为兜底
        if exit_price == 0.0 and supabase:
            try:
                row = (
                    supabase.table("positions_v43")
                    .select("current_price, entry_price")
                    .eq("symbol", request.symbol)
                    .eq("status", "OPEN")
                    .limit(1)
                    .execute()
                )
                if row.data:
                    exit_price = float(
                        row.data[0].get("current_price") or row.data[0].get("entry_price") or 0
                    )
            except Exception:
                pass

        # 执行平仓
        result = position_manager.close_position(
            symbol=request.symbol,
            exit_price=exit_price,
            exit_reason="手动平仓",
            write_queue=None,
        )

        if result:
            return TradeResponse(
                success=True,
                symbol=request.symbol,
                message=f"平仓成功: {request.symbol}",
                timestamp=datetime.now().isoformat(),
            )
        else:
            return TradeResponse(
                success=False,
                symbol=request.symbol,
                message="平仓失败: 未找到持仓或平仓失败",
                error="Position not found or close failed",
                timestamp=datetime.now().isoformat(),
            )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"平仓失败: {str(e)}",
        )
