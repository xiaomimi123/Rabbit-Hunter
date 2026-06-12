"""V5 ChartPage:K 线 + 事件。

URL 用下划线表示 symbol(H_USDT → H/USDT)避免 % encoding 边界。
"""
import os
import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Path

from api.schemas.v5_charts import (
    Kline, KlinesResponse, SymbolEvent, SymbolEventsResponse,
)
from api.services.score_service import ensure_utc_iso


router = APIRouter(prefix="/api/v5", tags=["charts"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def _decode(symbol: str) -> str:
    return symbol.replace("_", "/")


@router.get("/klines/{symbol}", response_model=KlinesResponse)
async def get_klines(
    symbol: str = Path(...),
    interval: Literal["15m", "1h", "4h"] = Query("15m"),
    limit: int = Query(200, ge=10, le=500),
) -> KlinesResponse:
    raw_symbol = _decode(symbol)
    try:
        from scripts.tasks.exchange_endpoints import fetch_klines
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"exchange_endpoints 不可用: {e}")
    try:
        raw = fetch_klines(raw_symbol, interval, limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"K 线拉取失败: {type(e).__name__}: {e}")

    klines = []
    for row in raw:
        try:
            ts, o, h, l, c, v = row[0], row[1], row[2], row[3], row[4], row[5]
            klines.append(Kline(ts=int(ts), open=float(o), high=float(h),
                                low=float(l), close=float(c), volume=float(v)))
        except Exception:
            continue
    return KlinesResponse(symbol=raw_symbol, interval=interval, klines=klines)


@router.get("/events/{symbol}", response_model=SymbolEventsResponse)
async def get_symbol_events(
    symbol: str = Path(...),
    limit: int = Query(50, ge=1, le=500),
) -> SymbolEventsResponse:
    raw_symbol = _decode(symbol)
    db = _db()
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("""
            SELECT id, symbol, side, entry_price, entry_time, exit_price,
                   exit_time, exit_reason, pnl_percent, status,
                   entry_rsi_15m, entry_macd_hist_15m, ai_reason
              FROM paper_trades
             WHERE symbol = ?
             ORDER BY entry_time DESC LIMIT ?
        """, (raw_symbol, limit)).fetchall()
    finally:
        conn.close()

    events: list[SymbolEvent] = []
    for (pid, sym, side, entry_p, entry_t, exit_p, exit_t,
         exit_reason, pnl_pct, status, rsi_15m, macd_hist_15m, ai_reason) in rows:
        events.append(SymbolEvent(
            event_type="entry", side=side, price=float(entry_p or 0.0),
            timestamp=ensure_utc_iso(entry_t) or "",
            position_id=pid,
            reasoning=(ai_reason or "")[:200],
            rsi_15m=float(rsi_15m) if rsi_15m is not None else None,
            macd_hist_15m=float(macd_hist_15m) if macd_hist_15m is not None else None,
        ))
        if status == "CLOSED" and exit_p is not None:
            events.append(SymbolEvent(
                event_type="exit", side=side, price=float(exit_p),
                timestamp=ensure_utc_iso(exit_t) or "",
                position_id=pid,
                exit_reason=exit_reason,
                pnl_pct=float(pnl_pct or 0.0) / 100.0,
            ))
    return SymbolEventsResponse(symbol=raw_symbol, events=events)
