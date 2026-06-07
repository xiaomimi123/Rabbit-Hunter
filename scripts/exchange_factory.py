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
    """返回当前 active exchange 名（'binance' 或 'okx'）。

    v0.5.3 起：优先读 system_settings（前端 SettingsPage 改的值实时生效），
    DB 没有值时回退 env EXCHANGE，默认 'okx'。
    """
    try:
        try:
            from exchange_config_manager import get_exchange_config_manager  # type: ignore[import-not-found]
            from local_db import get_local_db  # type: ignore[import-not-found]
        except ImportError:
            from scripts.exchange_config_manager import get_exchange_config_manager  # type: ignore[import-not-found]
            from scripts.local_db import get_local_db  # type: ignore[import-not-found]
        mgr = get_exchange_config_manager(get_local_db())
        return mgr.get_active_exchange()
    except Exception:
        # DB 不可用（启动初期 / 测试场景）→ env fallback
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

    # v0.5.3：DB 配置优先 — SettingsPage 改的值无需重启
    # 如果显式传了 kwargs，尊重它；否则 DB → env
    db_cfg = None
    try:
        try:
            from exchange_config_manager import get_exchange_config_manager  # type: ignore[import-not-found]
            from local_db import get_local_db  # type: ignore[import-not-found]
        except ImportError:
            from scripts.exchange_config_manager import get_exchange_config_manager  # type: ignore[import-not-found]
            from scripts.local_db import get_local_db  # type: ignore[import-not-found]
        db_cfg = get_exchange_config_manager(get_local_db()).get_config(name, force_refresh=False)
    except Exception:
        db_cfg = None

    def _coerce_bool(v) -> bool:
        if v is None: return False
        if isinstance(v, bool): return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    def _pick(field: str, override, env_key: str, default=None):
        # 注意：bool/数字 0 都是合法值，不能用 truthy 判断
        if override is not None:
            return override
        if db_cfg and field in db_cfg and db_cfg[field] not in (None, ""):
            return db_cfg[field]
        env_val = os.environ.get(env_key)
        if env_val not in (None, ""):
            return env_val
        return default

    if name == "okx":
        try:
            from okx_trader import OkxTrader  # type: ignore[import-not-found]
        except ImportError:
            from scripts.okx_trader import OkxTrader  # type: ignore[import-not-found]
        return OkxTrader(
            api_key=    _pick("api_key",        api_key,    "OKX_API_KEY")        or "",
            api_secret= _pick("api_secret",     api_secret, "OKX_API_SECRET")     or "",
            passphrase= _pick("api_passphrase", passphrase, "OKX_API_PASSPHRASE") or "",
            testnet=    _coerce_bool(_pick("testnet", testnet, "OKX_TESTNET", False)),
            leverage=   int(_pick("leverage",   leverage,   "OKX_LEVERAGE", 10) or 10),
        )

    if name == "binance":
        try:
            from binance_trader import BinanceTrader  # type: ignore[import-not-found]
        except ImportError:
            from scripts.binance_trader import BinanceTrader  # type: ignore[import-not-found]
        return BinanceTrader(
            api_key=    _pick("api_key",    api_key,    "BINANCE_API_KEY")    or "",
            api_secret= _pick("api_secret", api_secret, "BINANCE_API_SECRET") or "",
            testnet=    _coerce_bool(_pick("testnet", testnet, "BINANCE_TESTNET", False)),
            leverage=   int(_pick("leverage", leverage, "BINANCE_LEVERAGE", 10) or 10),
        )

    raise ValueError(f"未知 EXCHANGE={name!r}；支持: 'binance', 'okx'")


__all__ = ["get_trader", "get_active_exchange"]
