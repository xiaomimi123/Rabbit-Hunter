"""
Shared utility functions used by multiple task modules.

Covers:
  - Binance / ccxt symbol format conversions
  - Supabase client initialisation
  - ccxt exchange initialisation
"""

from __future__ import annotations

import os

import requests
from supabase import create_client, Client


# ---------------------------------------------------------------------------
# Symbol format conversions
# ---------------------------------------------------------------------------

def symbol_to_binance_symbol(symbol: str) -> str:
    """
    Convert ccxt format to Binance futures format.
    Example: TRB/USDT -> TRBUSDT
    """
    return symbol.replace("/", "")


def binance_symbol_to_ccxt_symbol(binance_symbol: str) -> str:
    """
    Convert Binance futures format to ccxt format.
    Example: TRBUSDT -> TRB/USDT
    """
    if binance_symbol.endswith("USDT"):
        base = binance_symbol[:-4]
        return f"{base}/USDT"
    return binance_symbol


def normalize_binance_symbol(s: str) -> str:
    """
    Normalise any symbol representation to Binance uppercase format.
    Example: TRB/USDT -> TRBUSDT,  trbusdt -> TRBUSDT
    """
    return s.replace("/", "").upper()


# ---------------------------------------------------------------------------
# Supabase initialisation
# ---------------------------------------------------------------------------

def init_supabase() -> Client | None:
    """
    Initialise a Supabase client from environment variables.

    Performs a lightweight health-check and connection test before returning
    the client.  Returns None (with a warning) if the URL/key are missing,
    invalid, or unreachable.
    """
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        print("[WARNING] 未配置 SUPABASE_URL / SUPABASE_KEY，将只打印数据，不写入数据库。")
        return None

    # URL reachability check
    try:
        health_url = supabase_url.rstrip("/") + "/auth/v1/health"
        r = requests.get(health_url, timeout=10)
        if r.status_code not in (200, 401, 403):
            print(f"[ERROR] Supabase URL 可能不正确：GET {health_url} -> {r.status_code}")
            print("[WARNING] 将只打印数据，不写入数据库。")
            return None
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] Supabase URL 健康检查失败：{e}")
        print("[WARNING] 将只打印数据，不写入数据库。")
        return None

    # Key-type hints
    if supabase_key.startswith("sbp_"):
        print(
            "[ERROR] 检测到 SUPABASE_KEY 以 sbp_ 开头（Personal Access Token），"
            "supabase-py 无法用它读写数据表。"
        )
        print("[INFO] 请使用 service_role key（eyJ... 开头的 JWT）")
        return None
    if supabase_key.startswith("sb_secret_"):
        print("[INFO] 检测到新版本 Secret key (sb_secret_ 开头)")
        print("[WARNING] 新版本 key 可能不被当前 supabase-py 支持")
    elif supabase_key.startswith("eyJ"):
        print("[INFO] 检测到旧版本 service_role key (JWT 格式)")

    try:
        client: Client = create_client(supabase_url, supabase_key)
        # Verify core table is accessible
        client.table("ai_training_data").select("id").limit(1).execute()
        # Optional table – ignore if absent
        try:
            client.table("system_settings").select("key").limit(1).execute()
        except Exception as e2:  # noqa: BLE001
            if "PGRST205" in str(e2) or "Could not find the table" in str(e2):
                print("[WARNING] system_settings 表不存在（不影响主流程）")
            else:
                raise e2
        print("[INFO] Supabase 连接成功！")
        return client
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        print(f"[ERROR] Supabase 连接失败: {e}")
        if "404" in msg or "JSON could not be generated" in msg:
            print("[INFO] 建议：尝试使用 Legacy service_role key（eyJ... 开头的 JWT）")
        elif "401" in msg or "403" in msg or "permission" in msg.lower():
            print("[INFO] 建议：检查 API key 是否为 service_role 类型")
        print("[WARNING] 将只打印数据，不写入数据库。")
        return None


# ---------------------------------------------------------------------------
# ccxt exchange initialisation
# ---------------------------------------------------------------------------

def init_exchange():
    """
    Initialise a ccxt binanceusdm instance if API credentials are configured.

    Returns None when credentials are absent; public-API paths are used in
    that case.
    """
    try:
        import ccxt  # local import – keeps ccxt optional for pure-util usage
    except ImportError:
        return None

    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")

    if not api_key or not api_secret:
        return None

    config: dict = {
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
        "apiKey": api_key,
        "secret": api_secret,
    }
    return ccxt.binanceusdm(config)
