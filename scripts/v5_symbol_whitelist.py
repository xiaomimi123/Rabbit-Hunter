"""高流动性 USDT 永续白名单 — 跳过 RWA / meme / pump,只在流动性好的主流加密币上评分。

V5 默认开启。可通过 v5_use_symbol_whitelist=false 关闭(SHADOW 实验用)。
白名单可通过 v5_symbol_whitelist 参数覆盖(逗号分隔,大小写不敏感)。
"""
from typing import Set


# 22 个高流动性 USDT 永续(主流加密币)
# 规矩(立于 2026-06-26):
#   任何新加 symbol / setup 必须先过 30d backtest + 6m walk-forward(扣成本),
#   net PF >= 1 且 KPI doc §15.2 PASS 才能进白名单。
#
# 历史:
#   2026-06    : MATICUSDT 移除 — Polygon 已改名 POL,OKX 上 MATIC-USDT-SWAP 不存在
#   2026-06-26 : +6 加密主流(WLD/PEPE/AAVE/HYPE/ZEC/IP),OKX SWAP 当时 24h 成交额 >= 1 亿
#   2026-06-26 : 移除 AAVE / ADA / IP — 30d backtest 都是负 net R(AAVE -2.17R 17 笔,
#                ADA -2.33R 13 笔,IP -0.76R 29 笔 win 34%),无 edge,违反立规矩
# 不收:RWA / 美股代币化(SOXL/SKHYNIX/SNDK/SPCX/MU/XAU/XAG)、meme/pump(BEAT/HUSDT/SLX/LAB 等)
V5_TOP20_WHITELIST: Set[str] = {
    # 原 19 - 移除 ADA(亏 R,2026-06-26) = 18
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT",            "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "UNIUSDT", "LTCUSDT", "TRXUSDT", "BCHUSDT",
    "NEARUSDT", "ATOMUSDT", "APTUSDT", "FILUSDT", "ARBUSDT",
    # 2026-06-26 加 6 个 - 移除 AAVE / IP(亏 R) = 4
    "WLDUSDT", "PEPEUSDT",             "HYPEUSDT", "ZECUSDT",
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
