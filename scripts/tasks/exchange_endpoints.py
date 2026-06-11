"""统一市场数据 facade — Binance / OKX 双 backend，按 EXCHANGE env 切换。

v0.5.2 设计动机：
  v0.5.1 之前 scanner / deep_collector 直接 requests.get('fapi.binance.com/…')，
  把"用哪家交易所"硬编码到业务代码里。现在抽到本模块：
    - 所有调用方继续用 Binance flat 格式 ('BTCUSDT') 作为 canonical symbol
    - 本模块负责 symbol / interval / 字段映射，让 OKX 后端对调用方透明
    - 切换只需 EXCHANGE=binance | EXCHANGE=okx 一个环境变量

公开函数（调用方只用这 6 个）：
  fetch_all_tickers()                          → dict {binance_symbol: ticker_dict}
  fetch_price_and_funding(binance_symbol)      → {'price': float, 'funding_rate': float}
  fetch_open_interest(binance_symbol)          → float | None
  fetch_ls_ratio(binance_symbol)               → float | None
  fetch_oi_change_1h(binance_symbol)           → float | None
  fetch_klines_ohlcv(binance_symbol, interval, limit)
                                                → list[dict] (oldest→newest)
  fetch_klines_full(binance_symbol, interval, limit)
                                                → (highs, lows, closes) 三列表
  fetch_price_change_1h(binance_symbol)        → float | None  (基于 klines)

注意：
  - OKX 市场数据是公开的，不需要 API key（带 key 仅提升 rate-limit）
  - OKX 永续合约符号映射：BTCUSDT ↔ BTC-USDT-SWAP
  - OKX 大小写时段：1h → 1H、4h → 4H、1d → 1D
  - OKX K 线返回**最新在前**，本模块统一反转成 oldest→newest（对齐 Binance 习惯）
"""

from __future__ import annotations

import os
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# 全局 Session — Docker Desktop on macOS 经常对 fapi.binance.com / www.okx.com 出
# 间歇 SSL EOF / Read timeout。共享 Session + Retry 让单次失败自动重试 3 次，
# 不污染上层业务逻辑。
def _build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3, backoff_factor=0.5,
        status_forcelist=(429, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


_SESSION = _build_session()


# ── 全局开关 ─────────────────────────────────────────────────────────
# 读 EXCHANGE env，默认 okx（v0.5.2 起信号源默认走 OKX；要切回 Binance 设 EXCHANGE=binance）
def _active_exchange() -> str:
    return os.environ.get("EXCHANGE", "okx").lower().strip()


OKX_BASE = "https://www.okx.com"
BINANCE_BASE = "https://fapi.binance.com"
_HTTP_TIMEOUT = 15


# ─────────────────────────────────────────────────────────────────────
# Symbol / interval 互转
# ─────────────────────────────────────────────────────────────────────


def binance_symbol_to_okx_inst(binance_symbol: str) -> str:
    """BTCUSDT → BTC-USDT-SWAP（OKX 永续合约 instId）。
    特殊：以 1000 前缀的 meme（如 1000PEPEUSDT）OKX 不一定有对应 SWAP，
    上层会拿到 404 → 跳过该 symbol。"""
    if binance_symbol.endswith("USDT"):
        return f"{binance_symbol[:-4]}-USDT-SWAP"
    return binance_symbol


def okx_inst_to_binance_symbol(inst_id: str) -> str:
    """BTC-USDT-SWAP → BTCUSDT。"""
    parts = inst_id.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}{parts[1]}"
    return inst_id


def binance_symbol_to_base_ccy(binance_symbol: str) -> str:
    """BTCUSDT → BTC（OKX rubik 端点要求 ccy 而非 instId）。"""
    if binance_symbol.endswith("USDT"):
        return binance_symbol[:-4]
    return binance_symbol


_OKX_INTERVAL_MAP = {
    "1m":  "1m",  "3m":  "3m",  "5m":  "5m",  "15m": "15m", "30m": "30m",
    "1h":  "1H",  "2h":  "2H",  "4h":  "4H",  "6h":  "6H",  "12h": "12H",
    "1d":  "1D",  "1w":  "1W",
}


def to_okx_interval(binance_interval: str) -> str:
    return _OKX_INTERVAL_MAP.get(binance_interval, binance_interval.upper())


# ─────────────────────────────────────────────────────────────────────
# 1. 全市场 tickers — 出口 dict {binance_symbol: ticker_shaped_dict}
# ─────────────────────────────────────────────────────────────────────


def fetch_all_tickers() -> dict:
    """统一 24h tickers — 返回 dict {binance_symbol: {priceChangePercent, quoteVolume, volume, lastPrice, _exchange}}"""
    if _active_exchange() == "okx":
        return _okx_all_tickers()
    return _binance_all_tickers()


def _okx_all_tickers() -> dict:
    resp = _SESSION.get(
        f"{OKX_BASE}/api/v5/market/tickers",
        params={"instType": "SWAP"},
        timeout=_HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != "0":
        raise Exception(f"OKX tickers code={payload.get('code')} msg={payload.get('msg')}")
    data = payload.get("data", []) or []

    result: dict = {}
    for t in data:
        inst_id = t.get("instId", "")
        # 只接 USDT 永续（OKX 还有 USDC/USD/各种本币结算合约）
        if not inst_id.endswith("-USDT-SWAP"):
            continue
        binance_sym = okx_inst_to_binance_symbol(inst_id)
        try:
            last = float(t.get("last", 0) or 0)
            open24 = float(t.get("open24h", 0) or 0)
            pct = ((last - open24) / open24 * 100.0) if open24 > 0 else 0.0
            # 注意 OKX SWAP 字段语义（和 spot 不同）：
            #   vol24h       = 合约张数（与 base ccy 数量有 contract-face 比例）
            #   volCcy24h    = 基础币数量（BTC 数量）
            #   volCcyQuote24h = USDT 数量，但 SWAP 经常为 None
            # 所以 USDT 成交额需要自己算：base_ccy × last
            base_ccy_vol  = float(t.get("volCcy24h", 0) or 0)
            contract_vol  = float(t.get("vol24h", 0) or 0)
            # 优先用 volCcyQuote24h（如果给了），否则反推
            quote_vol_raw = t.get("volCcyQuote24h")
            if quote_vol_raw is not None and quote_vol_raw != "":
                quote_vol = float(quote_vol_raw)
            else:
                quote_vol = base_ccy_vol * last
        except (TypeError, ValueError):
            continue
        result[binance_sym] = {
            "symbol":              binance_sym,
            "lastPrice":           last,
            "priceChangePercent":  pct,
            "quoteVolume":         quote_vol,       # USDT 24h 成交额
            "volume":              base_ccy_vol,    # 基础币数量（对齐 Binance "volume" 语义）
            "_inst_id":            inst_id,
            "_exchange":           "okx",
            "_contract_vol":       contract_vol,    # 张数，留给后续可能用
        }
    return result


def _binance_all_tickers() -> dict:
    resp = _SESSION.get(f"{BINANCE_BASE}/fapi/v1/ticker/24hr", timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    all_tickers = resp.json()
    result: dict = {}
    for t in all_tickers:
        sym = t.get("symbol", "")
        if sym.endswith("USDT"):
            t["_exchange"] = "binance"
            result[sym] = t
    return result


# ─────────────────────────────────────────────────────────────────────
# 2. price + funding rate
# ─────────────────────────────────────────────────────────────────────


def fetch_price_and_funding(binance_symbol: str) -> dict:
    """{ 'price': float, 'funding_rate': float } — 失败抛异常（与原 Binance 行为一致）。"""
    if _active_exchange() == "okx":
        return _okx_price_and_funding(binance_symbol)
    return _binance_price_and_funding(binance_symbol)


def _okx_price_and_funding(binance_symbol: str) -> dict:
    inst_id = binance_symbol_to_okx_inst(binance_symbol)

    r1 = _SESSION.get(
        f"{OKX_BASE}/api/v5/market/ticker",
        params={"instId": inst_id},
        timeout=10,
    )
    r1.raise_for_status()
    p = r1.json()
    if p.get("code") != "0" or not p.get("data"):
        raise Exception(f"OKX ticker {inst_id}: {p.get('msg')}")
    last = float(p["data"][0].get("last", 0) or 0)

    r2 = _SESSION.get(
        f"{OKX_BASE}/api/v5/public/funding-rate",
        params={"instId": inst_id},
        timeout=10,
    )
    r2.raise_for_status()
    f = r2.json()
    funding_rate = 0.0
    if f.get("code") == "0" and f.get("data"):
        funding_rate = float(f["data"][0].get("fundingRate", 0) or 0)

    return {"price": last, "funding_rate": funding_rate}


def _binance_price_and_funding(binance_symbol: str) -> dict:
    t = _SESSION.get(
        f"{BINANCE_BASE}/fapi/v1/ticker/24hr",
        params={"symbol": binance_symbol},
        timeout=10,
    )
    t.raise_for_status()
    tj = t.json()
    price = float(tj["lastPrice"])

    f = _SESSION.get(
        f"{BINANCE_BASE}/fapi/v1/premiumIndex",
        params={"symbol": binance_symbol},
        timeout=10,
    )
    f.raise_for_status()
    fj = f.json()
    funding_rate = float(fj.get("lastFundingRate", 0.0))

    return {"price": price, "funding_rate": funding_rate}


# ─────────────────────────────────────────────────────────────────────
# 3. open interest
# ─────────────────────────────────────────────────────────────────────


def fetch_open_interest(binance_symbol: str) -> Optional[float]:
    """OI in base currency。失败/无此 symbol 返回 None。"""
    if _active_exchange() == "okx":
        return _okx_open_interest(binance_symbol)
    return _binance_open_interest(binance_symbol)


def _okx_open_interest(binance_symbol: str) -> Optional[float]:
    inst_id = binance_symbol_to_okx_inst(binance_symbol)
    try:
        r = _SESSION.get(
            f"{OKX_BASE}/api/v5/public/open-interest",
            params={"instId": inst_id},
            timeout=10,
        )
        r.raise_for_status()
        p = r.json()
        if p.get("code") != "0" or not p.get("data"):
            return None
        # OKX 'oiCcy' = OI in base currency（对齐 Binance openInterest 字段语义）
        return float(p["data"][0].get("oiCcy", 0) or 0)
    except Exception:
        return None


def _binance_open_interest(binance_symbol: str) -> Optional[float]:
    try:
        r = _SESSION.get(
            f"{BINANCE_BASE}/fapi/v1/openInterest",
            params={"symbol": binance_symbol},
            timeout=10,
        )
        if r.status_code == 400:
            return None
        r.raise_for_status()
        return float(r.json().get("openInterest", 0))
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
# 4. long/short account ratio
# ─────────────────────────────────────────────────────────────────────


def fetch_ls_ratio(binance_symbol: str) -> Optional[float]:
    if _active_exchange() == "okx":
        return _okx_ls_ratio(binance_symbol)
    return _binance_ls_ratio(binance_symbol)


def _okx_ls_ratio(binance_symbol: str) -> Optional[float]:
    base = binance_symbol_to_base_ccy(binance_symbol)
    try:
        r = _SESSION.get(
            f"{OKX_BASE}/api/v5/rubik/stat/contracts/long-short-account-ratio",
            params={"ccy": base, "period": "5m"},
            timeout=10,
        )
        r.raise_for_status()
        p = r.json()
        if p.get("code") != "0" or not p.get("data"):
            return None
        # data: [[ts, ratio], ...] 最新在前
        return float(p["data"][0][1])
    except Exception:
        return None


def _binance_ls_ratio(binance_symbol: str) -> Optional[float]:
    try:
        r = _SESSION.get(
            f"{BINANCE_BASE}/futures/data/globalLongShortAccountRatio",
            params={"symbol": binance_symbol, "period": "5m", "limit": 1},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            return float(data[0].get("longShortRatio", 1.0))
        return None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
# 5. K-line / OHLCV — 由本模块负责将 OKX 最新在前的返回顺序反转
# ─────────────────────────────────────────────────────────────────────


def fetch_klines_ohlcv(binance_symbol: str, interval: str, limit: int) -> list:
    """返回 [{'open','high','low','close','volume'}, ...]，oldest→newest。失败返回 []。"""
    if _active_exchange() == "okx":
        return _okx_klines(binance_symbol, interval, limit)
    return _binance_klines(binance_symbol, interval, limit)


def _okx_klines(binance_symbol: str, interval: str, limit: int) -> list:
    inst_id = binance_symbol_to_okx_inst(binance_symbol)
    okx_bar = to_okx_interval(interval)
    try:
        r = _SESSION.get(
            f"{OKX_BASE}/api/v5/market/candles",
            params={"instId": inst_id, "bar": okx_bar, "limit": min(int(limit), 300)},
            timeout=10,
        )
        r.raise_for_status()
        p = r.json()
        if p.get("code") != "0":
            return []
        bars = []
        # OKX 最新在前 → reversed 后变成 oldest→newest，对齐 Binance 习惯
        for k in reversed(p.get("data", []) or []):
            try:
                bars.append({
                    "open":   float(k[1]),
                    "high":   float(k[2]),
                    "low":    float(k[3]),
                    "close":  float(k[4]),
                    "volume": float(k[5]),
                })
            except (TypeError, ValueError, IndexError):
                continue
        return bars
    except Exception:
        return []


def _binance_klines(binance_symbol: str, interval: str, limit: int) -> list:
    try:
        r = _SESSION.get(
            f"{BINANCE_BASE}/fapi/v1/klines",
            params={"symbol": binance_symbol, "interval": interval, "limit": limit},
            timeout=10,
        )
        r.raise_for_status()
        return [
            {"open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
             "close": float(k[4]), "volume": float(k[5])}
            for k in r.json()
        ]
    except Exception:
        return []


def fetch_klines_full(binance_symbol: str, interval: str, limit: int):
    """便利 wrapper：返回 (highs, lows, closes) 三个并列列表。"""
    bars = fetch_klines_ohlcv(binance_symbol, interval, limit)
    highs  = [b["high"]  for b in bars]
    lows   = [b["low"]   for b in bars]
    closes = [b["close"] for b in bars]
    return highs, lows, closes


# ─────────────────────────────────────────────────────────────────────
# 6. 1h price change（统一基于 klines 实现，不需要单独的 exchange-specific）
# ─────────────────────────────────────────────────────────────────────


def fetch_price_change_1h(binance_symbol: str) -> Optional[float]:
    """{% change} of the last finalized 1h bar vs the prior one。失败返回 None。"""
    bars = fetch_klines_ohlcv(binance_symbol, "1h", 2)
    if len(bars) < 2:
        return None
    prev_close = bars[-2]["close"]
    last_close = bars[-1]["close"]
    if prev_close == 0:
        return None
    return (last_close - prev_close) / prev_close * 100.0


def fetch_klines(symbol: str, interval: str = "15m", limit: int = 50) -> list:
    """统一拉 K 线 — 返回 OHLCV tuple 列表。

    interval: '15m' / '1h' / '4h' / ...
    limit:    要的根数,默认 50。
    返回 [(ts_ms, open, high, low, close, volume), ...]，oldest→newest。
    失败返回 []。
    """
    if _active_exchange() == "okx":
        return _okx_klines_tuples(symbol, interval, limit)
    return _binance_klines_tuples(symbol, interval, limit)


def _okx_klines_tuples(binance_symbol: str, interval: str, limit: int) -> list:
    inst_id = binance_symbol_to_okx_inst(binance_symbol)
    okx_bar = to_okx_interval(interval)
    try:
        r = _SESSION.get(
            f"{OKX_BASE}/api/v5/market/candles",
            params={"instId": inst_id, "bar": okx_bar, "limit": min(int(limit), 300)},
            timeout=_HTTP_TIMEOUT,
        )
        r.raise_for_status()
        p = r.json()
        if p.get("code") != "0":
            return []
        bars = []
        # OKX 最新在前 → reversed 后变成 oldest→newest
        for k in reversed(p.get("data", []) or []):
            try:
                bars.append((
                    int(k[0]),    # ts_ms
                    float(k[1]),  # open
                    float(k[2]),  # high
                    float(k[3]),  # low
                    float(k[4]),  # close
                    float(k[5]),  # volume
                ))
            except (TypeError, ValueError, IndexError):
                continue
        return bars
    except Exception:
        return []


def _binance_klines_tuples(binance_symbol: str, interval: str, limit: int) -> list:
    try:
        r = _SESSION.get(
            f"{BINANCE_BASE}/fapi/v1/klines",
            params={"symbol": binance_symbol, "interval": interval, "limit": limit},
            timeout=_HTTP_TIMEOUT,
        )
        r.raise_for_status()
        return [
            (int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]))
            for k in r.json()
        ]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────
# 7. 1h OI change
# ─────────────────────────────────────────────────────────────────────


def fetch_oi_change_1h(binance_symbol: str) -> Optional[float]:
    if _active_exchange() == "okx":
        return _okx_oi_change_1h(binance_symbol)
    return _binance_oi_change_1h(binance_symbol)


def _okx_oi_change_1h(binance_symbol: str) -> Optional[float]:
    base = binance_symbol_to_base_ccy(binance_symbol)
    try:
        r = _SESSION.get(
            f"{OKX_BASE}/api/v5/rubik/stat/contracts/open-interest-volume",
            params={"ccy": base, "period": "1H"},
            timeout=10,
        )
        r.raise_for_status()
        p = r.json()
        if p.get("code") != "0":
            return None
        data = p.get("data", []) or []
        if len(data) < 2:
            return None
        # data: [[ts, oi, vol], ...] 最新在前
        last_oi = float(data[0][1])
        prev_oi = float(data[1][1])
        if prev_oi == 0:
            return None
        return (last_oi - prev_oi) / prev_oi * 100.0
    except Exception:
        return None


def _binance_oi_change_1h(binance_symbol: str) -> Optional[float]:
    try:
        r = _SESSION.get(
            f"{BINANCE_BASE}/futures/data/openInterestHist",
            params={"symbol": binance_symbol, "period": "1h", "limit": 2},
            timeout=10,
        )
        if r.status_code == 400:
            return None
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list) or len(data) < 2:
            return None
        def _oi(x):
            return float(x.get("sumOpenInterest") or x.get("openInterest") or 0)
        prev, last = _oi(data[-2]), _oi(data[-1])
        if prev == 0:
            return None
        return (last - prev) / prev * 100.0
    except Exception:
        return None


__all__ = [
    "fetch_all_tickers",
    "fetch_price_and_funding",
    "fetch_open_interest",
    "fetch_ls_ratio",
    "fetch_oi_change_1h",
    "fetch_klines_ohlcv",
    "fetch_klines_full",
    "fetch_price_change_1h",
    "fetch_klines",
    "binance_symbol_to_okx_inst",
    "okx_inst_to_binance_symbol",
    "binance_symbol_to_base_ccy",
    "to_okx_interval",
]
