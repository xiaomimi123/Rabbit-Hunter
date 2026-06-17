"""Top-20 USDT 永续白名单 — 跳过热门小币 / meme,只在流动性好的主流币上评分。

V5 默认开启。可通过 v5_use_symbol_whitelist=false 关闭(SHADOW 实验用)。
白名单可通过 v5_symbol_whitelist 参数覆盖(逗号分隔,大小写不敏感)。
"""
from typing import Set


# 20 个最高流动性 USDT 永续(主流 + 一线 alt)
V5_TOP20_WHITELIST: Set[str] = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "UNIUSDT", "LTCUSDT", "TRXUSDT", "BCHUSDT",
    "NEARUSDT", "ATOMUSDT", "APTUSDT", "FILUSDT", "ARBUSDT",
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
