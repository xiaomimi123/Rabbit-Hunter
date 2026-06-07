"""
Exchange trader 工厂 — 按 env EXCHANGE 路由到 BinanceTrader 或 OkxTrader。

调用方不再 `BinanceTrader(...)` 直接 new，而是 `get_trader(...)`，
让"信号源 + 执行器"配对总是 active exchange 一家。

用法：
    from exchange_factory import get_trader
    trader = get_trader()                          # 用 env EXCHANGE 决定
    trader = get_trader(exchange='binance')        # 显式 override
    trader = get_trader(api_key='x', api_secret='y')  # 透传凭据

v0.5.2：默认 EXCHANGE=okx，与 scanner / deep_collector 信号源对齐。
"""

import os
from typing import Any, Optional


def get_active_exchange() -> str:
    """返回当前 active exchange 名（'binance' 或 'okx'）。"""
    return (os.environ.get("EXCHANGE", "okx") or "okx").lower().strip()


def get_trader(
    *,
    exchange: Optional[str] = None,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    passphrase: Optional[str] = None,
    testnet: Optional[bool] = None,
    leverage: Optional[int] = None,
) -> Any:
    """工厂：返回 active exchange 对应的 trader。

    Args:
        exchange: 'binance' / 'okx'；None 时读 env EXCHANGE。
        api_key / api_secret: 显式凭据；None 时 trader 自己从 env 取。
        passphrase: OKX 专属（Binance 忽略）。
        testnet: 测试网开关；None 时 trader 自己从 env 取。
        leverage: 杠杆；None 时 trader 自己从 env 取。

    Returns:
        trader 实例。trader 暴露的方法（open_position / close_position / set_stop_loss /
        set_take_profit / fetch_balance / _get_positions）在两个 exchange 上等价。
    """
    name = (exchange or get_active_exchange()).lower()

    if name == "okx":
        try:
            from okx_trader import OkxTrader  # type: ignore[import-not-found]
        except ImportError:
            from scripts.okx_trader import OkxTrader  # type: ignore[import-not-found]
        kwargs = {}
        if api_key is not None:    kwargs["api_key"]    = api_key
        if api_secret is not None: kwargs["api_secret"] = api_secret
        if passphrase is not None: kwargs["passphrase"] = passphrase
        if testnet is not None:    kwargs["testnet"]    = testnet
        if leverage is not None:   kwargs["leverage"]   = leverage
        return OkxTrader(**kwargs)

    if name == "binance":
        try:
            from binance_trader import BinanceTrader  # type: ignore[import-not-found]
        except ImportError:
            from scripts.binance_trader import BinanceTrader  # type: ignore[import-not-found]
        kwargs = {}
        if api_key is not None:    kwargs["api_key"]    = api_key
        if api_secret is not None: kwargs["api_secret"] = api_secret
        if testnet is not None:    kwargs["testnet"]    = testnet
        if leverage is not None:   kwargs["leverage"]   = leverage
        return BinanceTrader(**kwargs)

    raise ValueError(f"未知 EXCHANGE={name!r}；支持: 'binance', 'okx'")


__all__ = ["get_trader", "get_active_exchange"]
