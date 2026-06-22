"""V5 账户余额端点 — Dashboard 显示 OKX 实盘 / 模拟盘资产。

无 API key 配置时返回 not_configured 状态;有 key 时调 OkxTrader.fetch_balance。
"""
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(prefix="/api/v5", tags=["account"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


class AccountBalance(BaseModel):
    status: str               # 'not_configured' | 'ok' | 'error'
    exchange: str
    testnet: bool
    total_usdt: float
    available_usdt: float
    error: Optional[str] = None
    paper_initial_balance_usdt: float
    paper_realized_pnl_usdt: float
    paper_open_count: int


def _paper_stats(db_path: str) -> dict:
    """从 paper_trades 算出 SHADOW 视角的"账户"状态。"""
    conn = sqlite3.connect(db_path)
    try:
        realized = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM paper_trades WHERE status='CLOSED'"
        ).fetchone()[0] or 0
        open_n = conn.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'"
        ).fetchone()[0] or 0
    finally:
        conn.close()
    initial = float(os.environ.get("PAPER_INITIAL_BALANCE_USDT", "10000") or 10000)
    return {
        "paper_initial_balance_usdt": initial,
        "paper_realized_pnl_usdt": float(realized),
        "paper_open_count": int(open_n),
    }


def _okx_keys(db_path: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """从 DB system_settings 读 okx_api_key / okx_api_secret / okx_passphrase。"""
    conn = sqlite3.connect(db_path)
    try:
        def _get(k):
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key=? ORDER BY rowid DESC LIMIT 1",
                (k,),
            ).fetchone()
            return row[0] if row and row[0] else None
        return _get("okx_api_key"), _get("okx_api_secret"), _get("okx_passphrase")
    finally:
        conn.close()


@router.get("/account/balance", response_model=AccountBalance)
async def get_account_balance() -> AccountBalance:
    """读账户余额(OKX)。无 key 时回退到 SHADOW paper 统计视图。"""
    db_path = _db()
    paper = _paper_stats(db_path)
    exchange = (os.environ.get("EXCHANGE", "okx") or "okx").lower()

    api_key, secret, passphrase = _okx_keys(db_path)
    if not (api_key and secret and passphrase):
        return AccountBalance(
            status="not_configured",
            exchange=exchange,
            testnet=False,
            total_usdt=0.0,
            available_usdt=0.0,
            **paper,
        )

    try:
        from scripts.okx_trader import OkxTrader
        testnet_str = os.environ.get("OKX_DEMO", "false").lower()
        testnet = testnet_str in ("1", "true", "yes")
        trader = OkxTrader(
            api_key=api_key, secret=secret, passphrase=passphrase,
            testnet=testnet,
        )
        bal = trader.fetch_balance()
        return AccountBalance(
            status="ok" if not bal.get("error") else "error",
            exchange=exchange,
            testnet=bool(bal.get("testnet", testnet)),
            total_usdt=float(bal.get("balance") or 0),
            available_usdt=float(bal.get("availableBalance") or 0),
            error=bal.get("error"),
            **paper,
        )
    except Exception as e:
        return AccountBalance(
            status="error",
            exchange=exchange,
            testnet=False,
            total_usdt=0.0,
            available_usdt=0.0,
            error=f"{type(e).__name__}: {e}",
            **paper,
        )
