"""OKX historical kline fetcher with JSON disk cache.

Pulls 15m / 4h klines from OKX `/api/v5/market/history-candles`, paginated
in 300-bar chunks. Caches per (symbol, interval, from_iso, to_iso) so that
repeat backtest runs over the same window hit local disk, not the API.

Reuses `symbol_to_okx_instid` from funding_okx_client to stay consistent
with V6 collector conventions.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.funding_okx_client import symbol_to_okx_instid


OKX_HOST = "https://www.okx.com"
DEFAULT_CACHE_ROOT = "data/backtest_cache"
PAGE_SIZE = 300                            # OKX max per page


def _interval_to_okx_bar(interval: str) -> str:
    """'15m' → '15m', '1h' → '1H', '4h' → '4H' (OKX convention)."""
    mapping = {"15m": "15m", "1h": "1H", "4h": "4H"}
    if interval not in mapping:
        raise ValueError(f"unsupported interval: {interval}")
    return mapping[interval]


def _iso_to_safe(iso: str) -> str:
    """'2026-05-19T00:00:00+00:00' → '20260519T000000Z' (filename-safe)."""
    s = iso.replace("-", "").replace(":", "").replace("+00:00", "Z")
    if not s.endswith("Z"):
        s += "Z"
    return s


def cache_path_for(root: str, symbol: str, interval: str,
                    from_iso: str, to_iso: str) -> Path:
    """Deterministic cache file path for a given range."""
    Path(root).mkdir(parents=True, exist_ok=True)
    fname = f"{symbol}_{interval}_{_iso_to_safe(from_iso)}_{_iso_to_safe(to_iso)}.json"
    return Path(root) / fname


def load_cached_klines(root: str, symbol: str, interval: str,
                       from_iso: str, to_iso: str) -> Optional[List[List[float]]]:
    p = cache_path_for(root, symbol, interval, from_iso, to_iso)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        return data.get("klines", [])
    except (json.JSONDecodeError, OSError):
        return None


def save_klines_to_cache(root: str, symbol: str, interval: str,
                          from_iso: str, to_iso: str,
                          klines: List[List[float]]) -> None:
    p = cache_path_for(root, symbol, interval, from_iso, to_iso)
    payload = {
        "symbol": symbol,
        "interval": interval,
        "from": from_iso,
        "to": to_iso,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "klines": klines,
    }
    p.write_text(json.dumps(payload))


def _fetch_okx_history(symbol: str, interval: str,
                        from_ms: int, to_ms: int) -> List[List[float]]:
    """Fetch klines from OKX `history-candles` paginated. Returns ascending by ts.

    The OKX history endpoint returns DESCENDING. Paginate via `after=<oldest ts>`
    to walk backwards from `to_ms` until <= `from_ms`.
    """
    inst_id = symbol_to_okx_instid(symbol)
    bar = _interval_to_okx_bar(interval)
    all_bars: List[List[float]] = []
    cursor = to_ms
    while cursor > from_ms:
        params = {"instId": inst_id, "bar": bar, "after": str(cursor), "limit": str(PAGE_SIZE)}
        url = f"{OKX_HOST}/api/v5/market/history-candles?{urlencode(params)}"
        req = Request(url, headers={"User-Agent": "rabbit-hunter-backtest/0.1"})
        with urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read())
        if payload.get("code") != "0":
            raise RuntimeError(f"OKX error: {payload}")
        rows = payload.get("data", [])
        if not rows:
            break
        # OKX row shape: [ts_ms, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        for r in rows:
            ts = int(r[0])
            if ts < from_ms:
                continue
            all_bars.append([ts, float(r[1]), float(r[2]),
                             float(r[3]), float(r[4]), float(r[5])])
        # Walk further back: cursor = the oldest ts in this page
        oldest = int(rows[-1][0])
        if oldest <= from_ms or oldest >= cursor:
            break
        cursor = oldest
    # Dedup + sort ascending (paginated overlaps possible at boundaries)
    seen = set()
    deduped = []
    for bar_row in all_bars:
        if bar_row[0] in seen:
            continue
        seen.add(bar_row[0])
        deduped.append(bar_row)
    deduped.sort(key=lambda x: x[0])
    return deduped


def fetch_klines_with_cache(cache_root: str, symbol: str, interval: str,
                             from_iso: str, to_iso: str) -> List[List[float]]:
    """Returns klines for [from_iso, to_iso]. Cache hit returns from disk;
    miss triggers OKX fetch + cache write."""
    cached = load_cached_klines(cache_root, symbol, interval, from_iso, to_iso)
    if cached is not None:
        return cached
    from_dt = datetime.fromisoformat(from_iso.replace("Z", "+00:00"))
    to_dt = datetime.fromisoformat(to_iso.replace("Z", "+00:00"))
    from_ms = int(from_dt.timestamp() * 1000)
    to_ms = int(to_dt.timestamp() * 1000)
    klines = _fetch_okx_history(symbol, interval, from_ms, to_ms)
    save_klines_to_cache(cache_root, symbol, interval, from_iso, to_iso, klines)
    return klines
