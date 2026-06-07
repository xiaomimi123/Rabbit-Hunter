"""
通用交易所配置管理器（v0.5.3）

复用 binance_config_manager 的 Fernet 加密基础设施，但 exchange-agnostic：
按 exchange 名分 key 命名空间存储到 system_settings 表：

  exchange_okx_api_key
  exchange_okx_api_secret      (加密)
  exchange_okx_api_passphrase  (加密)
  exchange_okx_testnet
  exchange_okx_leverage
  exchange_binance_api_key
  ... (同上)

外加：
  active_exchange = 'okx' | 'binance'

读取顺序：DB → env → 不可用。
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

# 复用 binance_config_manager 的加密辅助（避免重复实现 Fernet KDF）
try:
    from binance_config_manager import BinanceConfigManager as _CryptoHelper  # type: ignore[import-not-found]
except ImportError:
    from scripts.binance_config_manager import BinanceConfigManager as _CryptoHelper  # type: ignore[import-not-found]


SUPPORTED_EXCHANGES = ("okx", "binance")
SENSITIVE_FIELDS = ("api_secret", "api_passphrase")  # 这两个字段加密存


class ExchangeConfigManager:
    """通用 exchange 配置 CRUD — 与单 exchange 的 BinanceConfigManager 同语义但 multi-exchange。"""

    def __init__(self, supabase_client=None):
        self.supabase = supabase_client
        # 借用 BinanceConfigManager 的加密器（同一把 key file）
        self._crypto = _CryptoHelper(supabase_client=supabase_client)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=5)

    # ── 私有：DB key ↔ field 映射 ──────────────────────────────────────

    @staticmethod
    def _db_key(exchange: str, field: str) -> str:
        return f"exchange_{exchange}_{field}"

    def _encrypt(self, value: str) -> str:
        return self._crypto.encrypt_secret(value)

    def _decrypt(self, value: str) -> str:
        return self._crypto.decrypt_secret(value)

    # ── 公开：get / save / delete config ─────────────────────────────

    def get_config(
        self,
        exchange: str,
        force_refresh: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """读取某 exchange 的完整配置。DB 没有则尝试 env，最终都没有返回 None。"""
        exchange = exchange.lower()
        if exchange not in SUPPORTED_EXCHANGES:
            return None

        # 缓存
        if not force_refresh and exchange in self._cache:
            ts = self._cache_time.get(exchange)
            if ts and datetime.now() - ts < self._cache_ttl:
                return self._cache[exchange]

        from_db = self._get_from_db(exchange) if self.supabase else None
        if from_db:
            self._cache[exchange] = from_db
            self._cache_time[exchange] = datetime.now()
            return from_db

        # DB 没有 → 兜底用 env
        from_env = self._get_from_env(exchange)
        return from_env  # 不进缓存（env 变化时方便看到）

    def _get_from_db(self, exchange: str) -> Optional[Dict[str, Any]]:
        """从 system_settings 拉一个 exchange 的全部 fields。任何关键字段缺失返回 None。"""
        try:
            cfg: Dict[str, Any] = {}
            fields = ["api_key", "api_secret", "api_passphrase", "testnet", "leverage"]
            for f in fields:
                r = (
                    self.supabase.table("system_settings")
                    .select("value")
                    .eq("key", self._db_key(exchange, f))
                    .execute()
                )
                if r.data:
                    v = r.data[0].get("value", "")
                    if f in SENSITIVE_FIELDS and v:
                        v = self._decrypt(v)
                    cfg[f] = v
            if not cfg.get("api_key"):
                return None
            # 类型转换
            cfg["testnet"] = (cfg.get("testnet") or "false").lower() in ("1", "true")
            try:
                cfg["leverage"] = int(cfg.get("leverage") or 10)
            except (TypeError, ValueError):
                cfg["leverage"] = 10
            cfg["exchange"] = exchange
            cfg["source"] = "db"
            return cfg
        except Exception as e:
            print(f"[ExchangeConfigManager] _get_from_db({exchange}) 失败: {e}")
            return None

    def _get_from_env(self, exchange: str) -> Optional[Dict[str, Any]]:
        """env 兜底 — 即使是 OKX 也用 OKX_* 前缀，Binance 用 BINANCE_*。"""
        prefix = exchange.upper()
        key = os.environ.get(f"{prefix}_API_KEY", "").strip()
        secret = os.environ.get(f"{prefix}_API_SECRET", "").strip()
        passphrase = os.environ.get(f"{prefix}_API_PASSPHRASE", "").strip()
        if not key:
            return None
        testnet_env = os.environ.get(f"{prefix}_TESTNET", "false").lower() in ("1", "true")
        leverage_env = int(os.environ.get(f"{prefix}_LEVERAGE", "10"))
        return {
            "exchange":      exchange,
            "api_key":       key,
            "api_secret":    secret,
            "api_passphrase":passphrase,  # binance 是空字符串，OKX 必填
            "testnet":       testnet_env,
            "leverage":      leverage_env,
            "source":        "env",
        }

    def save_config(
        self,
        exchange: str,
        *,
        api_key: str,
        api_secret: str,
        api_passphrase: str = "",
        testnet: bool = False,
        leverage: int = 10,
    ) -> Dict[str, Any]:
        """写入 DB。敏感字段（secret/passphrase）走 Fernet 加密。"""
        exchange = exchange.lower()
        if exchange not in SUPPORTED_EXCHANGES:
            return {"success": False, "error": f"不支持的 exchange: {exchange}"}
        if not self.supabase:
            return {"success": False, "error": "DB 未配置"}

        try:
            payload = {
                "api_key":        api_key.strip(),
                "api_secret":     self._encrypt(api_secret.strip()),
                "api_passphrase": self._encrypt(api_passphrase.strip()) if api_passphrase else "",
                "testnet":        "true" if testnet else "false",
                "leverage":       str(int(leverage)),
            }
            for field, value in payload.items():
                self.supabase.table("system_settings").upsert(
                    {"key": self._db_key(exchange, field), "value": value},
                    on_conflict="key",
                ).execute()
            # 清缓存
            self._cache.pop(exchange, None)
            self._cache_time.pop(exchange, None)
            return {"success": True, "exchange": exchange, "configured": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_config(self, exchange: str) -> Dict[str, Any]:
        exchange = exchange.lower()
        if not self.supabase:
            return {"success": False, "error": "DB 未配置"}
        try:
            for field in ("api_key", "api_secret", "api_passphrase", "testnet", "leverage"):
                self.supabase.table("system_settings").delete().eq(
                    "key", self._db_key(exchange, field)
                ).execute()
            self._cache.pop(exchange, None)
            self._cache_time.pop(exchange, None)
            return {"success": True, "exchange": exchange}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── active exchange 切换 ─────────────────────────────────────────

    def get_active_exchange(self) -> str:
        """active_exchange 在 system_settings 里；没有时回退 env EXCHANGE，再没有时 'okx'。"""
        if self.supabase:
            try:
                r = (
                    self.supabase.table("system_settings")
                    .select("value")
                    .eq("key", "active_exchange")
                    .execute()
                )
                if r.data:
                    v = (r.data[0].get("value") or "").strip().lower()
                    if v in SUPPORTED_EXCHANGES:
                        return v
            except Exception:
                pass
        return (os.environ.get("EXCHANGE", "okx") or "okx").lower().strip()

    def set_active_exchange(self, exchange: str) -> Dict[str, Any]:
        exchange = exchange.lower()
        if exchange not in SUPPORTED_EXCHANGES:
            return {"success": False, "error": f"不支持: {exchange}"}
        if not self.supabase:
            return {"success": False, "error": "DB 未配置"}
        try:
            self.supabase.table("system_settings").upsert(
                {"key": "active_exchange", "value": exchange},
                on_conflict="key",
            ).execute()
            return {"success": True, "active_exchange": exchange}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── status 概览（返回 masked 形式给前端展示）─────────────────────

    def get_status(self) -> Dict[str, Any]:
        """前端 SettingsPage 一次读全：所有 exchange 是否已配置 + active。"""
        result: Dict[str, Any] = {
            "active": self.get_active_exchange(),
            "exchanges": {},
        }
        for ex in SUPPORTED_EXCHANGES:
            cfg = self.get_config(ex, force_refresh=True)
            if cfg:
                key = cfg.get("api_key", "")
                masked = (key[:4] + "…" + key[-4:]) if len(key) > 10 else "configured"
                result["exchanges"][ex] = {
                    "configured":   True,
                    "api_key_masked": masked,
                    "testnet":      cfg.get("testnet", False),
                    "leverage":     cfg.get("leverage", 10),
                    "source":       cfg.get("source", "unknown"),
                    "has_passphrase": bool(cfg.get("api_passphrase")),  # OKX 用
                }
            else:
                result["exchanges"][ex] = {"configured": False}
        return result


# 单例
_manager: Optional[ExchangeConfigManager] = None


def get_exchange_config_manager(supabase_client=None) -> ExchangeConfigManager:
    global _manager
    if _manager is None:
        _manager = ExchangeConfigManager(supabase_client=supabase_client)
    elif supabase_client is not None and _manager.supabase is None:
        _manager.supabase = supabase_client
        _manager._crypto.supabase = supabase_client
    return _manager


__all__ = ["ExchangeConfigManager", "get_exchange_config_manager", "SUPPORTED_EXCHANGES"]
