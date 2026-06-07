"""
AI 大模型配置管理器（v0.5.3）

用 system_settings 表保存：
  ai_provider      = 'openai' | 'deepseek' | 'anthropic' | 'disabled'
  ai_api_key       (加密)
  ai_model         自由文本（如 gpt-4o, deepseek-chat, claude-sonnet-4-5）
  ai_enabled       'true' | 'false'

复用 BinanceConfigManager 的 Fernet 加密。
DB 没有时 fallback 到 env（OPENAI_API_KEY / DEEPSEEK_API_KEY / ANTHROPIC_API_KEY 对应）。

trading_assistant.py / deepseek_ai.py 在初始化时调 get_ai_config()，DB > env。
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

try:
    from binance_config_manager import BinanceConfigManager as _CryptoHelper  # type: ignore[import-not-found]
except ImportError:
    from scripts.binance_config_manager import BinanceConfigManager as _CryptoHelper  # type: ignore[import-not-found]


SUPPORTED_PROVIDERS = ("openai", "deepseek", "anthropic", "disabled")

# 每个 provider 的默认 env 变量名（DB 缺省时 fallback）
_PROVIDER_ENV_KEY = {
    "openai":    "OPENAI_API_KEY",
    "deepseek":  "DEEPSEEK_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

# 每个 provider 的默认 model（仅当 DB 和 env OPENAI_TRADING_MODEL 都没设时用）
_PROVIDER_DEFAULT_MODEL = {
    "openai":    "gpt-4o",
    "deepseek":  "deepseek-chat",
    "anthropic": "claude-sonnet-4-5",
    "disabled":  "",
}


class AIConfigManager:
    """AI provider/model/key 的 DB CRUD + env fallback。"""

    def __init__(self, supabase_client=None):
        self.supabase = supabase_client
        self._crypto = _CryptoHelper(supabase_client=supabase_client)
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)

    # ── 内部 ─────────────────────────────────────────────────────────

    def _encrypt(self, v: str) -> str:
        return self._crypto.encrypt_secret(v)

    def _decrypt(self, v: str) -> str:
        return self._crypto.decrypt_secret(v)

    def _get_from_db(self) -> Optional[Dict[str, Any]]:
        try:
            row_map = {}
            for f in ("ai_provider", "ai_api_key", "ai_model", "ai_enabled"):
                r = (
                    self.supabase.table("system_settings")
                    .select("value")
                    .eq("key", f)
                    .execute()
                )
                if r.data:
                    row_map[f] = r.data[0].get("value", "")
            if not row_map.get("ai_provider"):
                return None
            provider = row_map["ai_provider"].strip().lower()
            api_key = row_map.get("ai_api_key", "")
            if api_key:
                api_key = self._decrypt(api_key)
            return {
                "provider": provider,
                "api_key":  api_key,
                "model":    row_map.get("ai_model") or _PROVIDER_DEFAULT_MODEL.get(provider, ""),
                "enabled":  (row_map.get("ai_enabled") or "false").lower() in ("1", "true"),
                "source":   "db",
            }
        except Exception as e:
            print(f"[AIConfigManager] _get_from_db 失败: {e}")
            return None

    def _get_from_env(self) -> Dict[str, Any]:
        """fallback：env 里 OPENAI_API_KEY 优先（与 v0.5.0 之前行为一致）。"""
        # 优先级：openai > deepseek > anthropic
        for provider in ("openai", "deepseek", "anthropic"):
            env_key = _PROVIDER_ENV_KEY[provider]
            api_key = os.environ.get(env_key, "").strip()
            if api_key:
                return {
                    "provider": provider,
                    "api_key":  api_key,
                    "model":    (
                        os.environ.get("OPENAI_TRADING_MODEL") if provider == "openai"
                        else os.environ.get("DEEPSEEK_MODEL") if provider == "deepseek"
                        else os.environ.get("ANTHROPIC_MODEL")
                    ) or _PROVIDER_DEFAULT_MODEL[provider],
                    "enabled":  True,
                    "source":   "env",
                }
        return {
            "provider": "disabled",
            "api_key":  "",
            "model":    "",
            "enabled":  False,
            "source":   "default",
        }

    # ── 公开 API ────────────────────────────────────────────────────

    def get_config(self, force_refresh: bool = False) -> Dict[str, Any]:
        if not force_refresh and self._cache and self._cache_time:
            if datetime.now() - self._cache_time < self._cache_ttl:
                return self._cache

        result = None
        if self.supabase:
            result = self._get_from_db()
        if result is None:
            result = self._get_from_env()
            # env 兜底不缓存
            return result

        self._cache = result
        self._cache_time = datetime.now()
        return result

    def save_config(
        self,
        provider: str,
        api_key: str,
        model: str = "",
        enabled: bool = True,
    ) -> Dict[str, Any]:
        provider = provider.lower()
        if provider not in SUPPORTED_PROVIDERS:
            return {"success": False, "error": f"不支持的 provider: {provider}"}
        if not self.supabase:
            return {"success": False, "error": "DB 未配置"}
        try:
            payload = {
                "ai_provider": provider,
                "ai_api_key":  self._encrypt(api_key.strip()) if api_key else "",
                "ai_model":    model.strip() or _PROVIDER_DEFAULT_MODEL.get(provider, ""),
                "ai_enabled":  "true" if enabled else "false",
            }
            for k, v in payload.items():
                self.supabase.table("system_settings").upsert(
                    {"key": k, "value": v}, on_conflict="key",
                ).execute()
            self._cache = None
            return {"success": True, "provider": provider, "model": payload["ai_model"]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_config(self) -> Dict[str, Any]:
        if not self.supabase:
            return {"success": False, "error": "DB 未配置"}
        try:
            for f in ("ai_provider", "ai_api_key", "ai_model", "ai_enabled"):
                self.supabase.table("system_settings").delete().eq("key", f).execute()
            self._cache = None
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_status(self) -> Dict[str, Any]:
        cfg = self.get_config(force_refresh=True)
        key = cfg.get("api_key") or ""
        masked = (key[:4] + "…" + key[-4:]) if len(key) > 10 else ("configured" if key else "")
        return {
            "provider":         cfg.get("provider"),
            "model":            cfg.get("model"),
            "enabled":          cfg.get("enabled", False),
            "api_key_masked":   masked,
            "source":           cfg.get("source"),
            "available_providers": list(SUPPORTED_PROVIDERS),
        }


_manager: Optional[AIConfigManager] = None


def get_ai_config_manager(supabase_client=None) -> AIConfigManager:
    global _manager
    if _manager is None:
        _manager = AIConfigManager(supabase_client=supabase_client)
    elif supabase_client is not None and _manager.supabase is None:
        _manager.supabase = supabase_client
        _manager._crypto.supabase = supabase_client
    return _manager


__all__ = ["AIConfigManager", "get_ai_config_manager", "SUPPORTED_PROVIDERS"]
