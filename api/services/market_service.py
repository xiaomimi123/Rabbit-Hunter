"""
市场数据业务逻辑服务

包含价格查询、ATR 辅助等功能。
"""

import os
from typing import Optional, Dict, Any, Tuple
from urllib.parse import unquote


def normalize_symbol(symbol: str) -> str:
    """
    将前端传入的 symbol（可能含 URL 编码或斜杠）标准化为币安合约格式（如 BTCUSDT）。
    """
    decoded = unquote(symbol)
    return decoded.replace("/", "")


def get_testnet_config() -> bool:
    """从环境变量读取是否使用测试网。"""
    return os.environ.get("BINANCE_TESTNET", "false").lower() in ("true", "1")


def build_ccxt_config(testnet: bool, api_key: Optional[str] = None, api_secret: Optional[str] = None) -> Dict[str, Any]:
    """构建 CCXT binanceusdm 配置字典。"""
    config: Dict[str, Any] = {
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
            "adjustForTimeDifference": True,
        },
    }
    if api_key:
        config["apiKey"] = api_key
    if api_secret:
        config["secret"] = api_secret
    if testnet:
        config["urls"] = {
            "api": {
                "public": "https://testnet.binancefuture.com",
                "private": "https://testnet.binancefuture.com",
            }
        }
    return config


def snap_to_valid_depth_limit(limit: int) -> int:
    """
    将任意深度 limit 映射到 Binance 支持的有效值（5, 10, 20, 50, 100, 500, 1000）。
    """
    valid_limits = [5, 10, 20, 50, 100, 500, 1000]
    return min(valid_limits, key=lambda x: abs(x - limit))


def fetch_market_price_and_change(supabase, symbol: str) -> Tuple[Optional[float], float]:
    """
    从 market_snapshot 表查询最新价格和 24h 涨跌幅。

    :return: (price, change_24h) — 若查询失败则返回 (None, 0.0)
    """
    try:
        response = (
            supabase.table("market_snapshot")
            .select("price, price_change_24h")
            .eq("symbol", symbol)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if response.data and len(response.data) > 0:
            row = response.data[0]
            price = float(row.get("price", 0)) if row.get("price") else None
            change = float(row.get("price_change_24h", 0)) if row.get("price_change_24h") else 0.0
            return price, change
    except Exception:
        pass
    return None, 0.0
