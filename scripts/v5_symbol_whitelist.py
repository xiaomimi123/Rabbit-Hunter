"""高流动性 USDT 永续白名单 — 跳过 RWA / meme / pump,只在流动性好的主流加密币上评分。

V5 默认开启。可通过 v5_use_symbol_whitelist=false 关闭(SHADOW 实验用)。
白名单可通过 v5_symbol_whitelist 参数覆盖(逗号分隔,大小写不敏感)。
"""
from typing import Set


# 25 个高流动性 USDT 永续(主流加密币)
# 历史:
#   2026-06    : MATICUSDT 移除 — Polygon 已改名 POL,OKX 上 MATIC-USDT-SWAP 不存在
#   2026-06-26 : +6 加密主流(WLD/PEPE/AAVE/HYPE/ZEC/IP),OKX SWAP 当前 24h 成交额 >= 1 亿
#                原 19 个里 14 个(BNB/ADA/AVAX/DOT/LINK/UNI/LTC/TRX/BCH/NEAR/ATOM/APT/FIL/ARB)
#                当前已跌破 1 亿,保留以待回暖;MarketScanner 的 MIN_VOLUME_24H_USDT 会自动按需过滤
# 不收:RWA / 美股代币化(SOXL/SKHYNIX/SNDK/SPCX/MU/XAU/XAG)、meme/pump(BEAT/HUSDT/SLX/LAB 等)
V5_TOP20_WHITELIST: Set[str] = {
    # 原 19(V4 时代基线,保留作为未来回暖候选)
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "UNIUSDT", "LTCUSDT", "TRXUSDT", "BCHUSDT",
    "NEARUSDT", "ATOMUSDT", "APTUSDT", "FILUSDT", "ARBUSDT",
    # 2026-06-26 加 6 个当前 OKX SWAP 100M+ 主流加密币
    "WLDUSDT", "PEPEUSDT", "AAVEUSDT", "HYPEUSDT", "ZECUSDT", "IPUSDT",
}


def normalize_symbol(symbol: str) -> str:
    """统一大小写 + 去掉 '/' 或 ':' 分隔符。"""
    if not symbol:
        return ""
    return symbol.replace("/", "").replace(":", "").upper().strip()


def parse_whitelist_param(raw: str) -> Set[str]:
    """v5_symbol_whitelist 参数 → 集合。空 / None → 默认 top20。

    格式: 逗号分隔,大小写不敏感
      e.g. "BTCUSDT,ETHUSDT,SOL/USDT"
    """
    if not raw or not raw.strip():
        return set(V5_TOP20_WHITELIST)
    return {normalize_symbol(s) for s in raw.split(",") if s.strip()}


def is_symbol_allowed(symbol: str, whitelist: Set[str]) -> bool:
    """检查 symbol 是否在白名单。统一归一化后比较。"""
    return normalize_symbol(symbol) in whitelist
