"""V6 funding rate API."""
import os
import sqlite3

from fastapi import APIRouter, Path, Query

from api.schemas.v5_funding import (
    FundingHistoryItem, FundingHistoryResponse,
    FundingStatusResponse, FundingZScoreItem,
)


router = APIRouter(prefix="/api/v5/funding", tags=["funding"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


@router.get("/status", response_model=FundingStatusResponse)
async def list_funding_status() -> FundingStatusResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT symbol, computed_at, current_funding_rate, mean_30d,
                   std_30d, zscore_30d, sample_size_30d, is_extreme,
                   extreme_direction
              FROM funding_zscore_cache
             ORDER BY ABS(zscore_30d) DESC, symbol
        """).fetchall()
    finally:
        conn.close()
    return FundingStatusResponse(data=[
        FundingZScoreItem(
            symbol=r["symbol"], computed_at=r["computed_at"],
            current_funding_rate=r["current_funding_rate"],
            annualized_rate_pct=r["current_funding_rate"] * 365 * 3 * 100,
            mean_30d=r["mean_30d"], std_30d=r["std_30d"],
            zscore_30d=r["zscore_30d"],
            sample_size_30d=r["sample_size_30d"] or 0,
            is_extreme=bool(r["is_extreme"]),
            extreme_direction=r["extreme_direction"],
        )
        for r in rows
    ])


@router.get("/history/{symbol}", response_model=FundingHistoryResponse)
async def get_funding_history(
    symbol: str = Path(...),
    limit: int = Query(50, ge=1, le=500),
) -> FundingHistoryResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT funding_time, funding_rate, annualized_rate, source
              FROM funding_rates
             WHERE symbol = ?
             ORDER BY funding_time DESC
             LIMIT ?
        """, (symbol, limit)).fetchall()
    finally:
        conn.close()
    return FundingHistoryResponse(
        symbol=symbol,
        data=[
            FundingHistoryItem(
                funding_time=r["funding_time"],
                funding_rate=r["funding_rate"],
                annualized_rate=r["annualized_rate"],
                source=r["source"],
            ) for r in rows
        ],
    )
