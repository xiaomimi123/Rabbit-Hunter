"""OKX 公开 funding rate API 客户端 — 纯 HTTP,无 key,无副作用。

Endpoints used:
  GET /api/v5/public/funding-rate-history?instId=...&limit=...
  GET /api/v5/public/funding-rate?instId=...

Response shape (success):
  {"code":"0", "data":[{...}], "msg":""}

Response shape (error):
  {"code":"50001", "data":[], "msg":"..."}
"""
import json
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from scripts.http_retry import with_retries          # type: ignore[import-not-found]
except ImportError:
    from http_retry import with_retries                   # type: ignore[import-not-found]


OKX_BASE = "https://www.okx.com/api/v5/public"


def symbol_to_okx_instid(symbol: str) -> str:
    """'BTCUSDT' → 'BTC-USDT-SWAP'. Idempotent if already OKX-formatted."""
    if "-SWAP" in symbol:
        return symbol
    if not symbol.endswith("USDT"):
        raise ValueError(f"unsupported symbol format: {symbol}")
    base = symbol[: -len("USDT")]
    return f"{base}-USDT-SWAP"


def okx_instid_to_symbol(instid: str) -> str:
    """'BTC-USDT-SWAP' → 'BTCUSDT'. Idempotent if already V5-formatted."""
    if "-SWAP" not in instid:
        return instid
    parts = instid.split("-")
    return f"{parts[0]}{parts[1]}"


def parse_funding_response(raw: dict) -> List[dict]:
    """OKX response → list of dicts ready for DB insert.

    Each output row:
      {
        "symbol": "BTCUSDT",
        "instrument_id": "BTC-USDT-SWAP",
        "funding_time": "2026-06-17T08:00:00+00:00",
        "funding_rate": float,
        "annualized_rate": float,
        "settled_rate": float | None,
      }
    """
    if str(raw.get("code")) != "0":
        raise ValueError(
            f"OKX error code={raw.get('code')} msg={raw.get('msg', '')!r}"
        )

    out: List[dict] = []
    for row in raw.get("data", []):
        instid = row["instId"]
        rate = float(row["fundingRate"])
        ts_ms = int(row["fundingTime"])
        ft = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
        settled_raw = row.get("realizedRate") or row.get("settFundingRate")
        settled = float(settled_raw) if settled_raw not in (None, "") else None
        out.append({
            "symbol": okx_instid_to_symbol(instid),
            "instrument_id": instid,
            "funding_time": ft,
            "funding_rate": rate,
            "annualized_rate": rate * 365 * 3,    # 3 periods per day
            "settled_rate": settled,
        })
    return out


def _do_get(url: str, timeout_s: float) -> dict:
    """One HTTP GET — JSON-decoded result. Retried by caller via with_retries."""
    req = Request(url, headers={"User-Agent": "rabbit-hunter-v6/1.0"})
    with urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def fetch_funding_history(symbol: str, *, limit: int = 100,
                           timeout_s: float = 10.0) -> List[dict]:
    """拉一个 symbol 的最近 N 个 funding 历史。带 5 次指数退避重试。"""
    instid = symbol_to_okx_instid(symbol)
    params = urlencode({"instId": instid, "limit": str(limit)})
    url = f"{OKX_BASE}/funding-rate-history?{params}"
    raw = with_retries(lambda: _do_get(url, timeout_s),
                       description=f"funding history {symbol}")
    return parse_funding_response(raw)


def fetch_current_funding(symbol: str, *, timeout_s: float = 10.0) -> Optional[dict]:
    """拉一个 symbol 的当前(未结算)funding rate。带重试。返回单条 dict 或 None。"""
    instid = symbol_to_okx_instid(symbol)
    params = urlencode({"instId": instid})
    url = f"{OKX_BASE}/funding-rate?{params}"
    raw = with_retries(lambda: _do_get(url, timeout_s),
                       description=f"funding current {symbol}")
    rows = parse_funding_response(raw)
    return rows[0] if rows else None
