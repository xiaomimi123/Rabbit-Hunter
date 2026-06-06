"""
DeepCollector - Layer-2 deep metric collection for top movers.

Responsibility:
  Consumes a *movers_queue* (list of top-mover tuples from MarketScanner)
  and, every *deep_scan_interval* seconds, performs deep collection for each
  symbol in the list:

    1. Level-1 structure analysis (whale_detector.analyze_structure_level_1)
       — symbols flagged P4_CRASHING are dropped.
    2. Fast metrics: price + funding rate (public API).
    3. Slow metrics: OI + long/short ratio (public API, 60-second cadence).
    4. 1-hour price change and 1-hour OI change.

  Enriched metric dicts are pushed to *enriched_queue* for StrategyScorer to
  consume.

Queue protocols:
  movers_queue   <- List[Tuple[binance_symbol: str, score: float, reason: str]]
  enriched_queue -> Dict with at least:
      symbol, price, funding_rate, oi_value, ls_ratio,
      price_change, oi_change, _ts, (optionally) level1_phase, level1_reason
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:
    from supabase import Client

from .utils import symbol_to_binance_symbol, binance_symbol_to_ccxt_symbol

_DEFAULT_DEEP_SCAN_INTERVAL: float = 60.0
_DEFAULT_MAX_CONCURRENCY: int = 10


# ---------------------------------------------------------------------------
# Low-level fetch helpers (stateless pure functions)
# ---------------------------------------------------------------------------

def _fetch_price_and_funding(binance_symbol: str) -> dict:
    """Fetch last price and funding rate via Binance public REST API."""
    base = "https://fapi.binance.com"
    ticker = requests.get(
        f"{base}/fapi/v1/ticker/24hr", params={"symbol": binance_symbol}, timeout=10
    )
    ticker.raise_for_status()
    t = ticker.json()
    price = float(t["lastPrice"])

    funding = requests.get(
        f"{base}/fapi/v1/premiumIndex", params={"symbol": binance_symbol}, timeout=10
    )
    funding.raise_for_status()
    f = funding.json()
    funding_rate = float(f.get("lastFundingRate", 0.0))

    return {"price": price, "funding_rate": funding_rate}


def _fetch_oi(binance_symbol: str) -> float | None:
    """Fetch open interest via Binance public REST API."""
    resp = requests.get(
        "https://fapi.binance.com/fapi/v1/openInterest",
        params={"symbol": binance_symbol},
        timeout=10,
    )
    if resp.status_code == 400:
        return None
    resp.raise_for_status()
    data = resp.json()
    try:
        return float(data["openInterest"])
    except Exception:  # noqa: BLE001
        return None


def _fetch_ls_ratio(binance_symbol: str) -> float | None:
    """Fetch global long/short account ratio via Binance public REST API."""
    try:
        resp = requests.get(
            "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
            params={"symbol": binance_symbol, "period": "5m", "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            return float(data[0].get("longShortRatio", 1.0))
        if isinstance(data, dict):
            return float(data.get("longShortRatio", 1.0))
        return None
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None  # symbol doesn't support this endpoint
        return None
    except Exception:  # noqa: BLE001
        return None


def _fetch_price_change_1h(binance_symbol: str) -> float | None:
    """Compute 1-hour price change % from Binance kline API."""
    try:
        resp = requests.get(
            "https://fapi.binance.com/fapi/v1/klines",
            params={"symbol": binance_symbol, "interval": "1h", "limit": 2},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or len(data) < 2:
            return None
        prev_close = float(data[-2][4])
        last_close = float(data[-1][4])
        if prev_close == 0:
            return None
        return (last_close - prev_close) / prev_close * 100.0
    except Exception:  # noqa: BLE001
        return None


def _fetch_oi_change_1h(binance_symbol: str) -> float | None:
    """Compute 1-hour OI change % via Binance openInterestHist API."""
    try:
        resp = requests.get(
            "https://fapi.binance.com/futures/data/openInterestHist",
            params={"symbol": binance_symbol, "period": "1h", "limit": 2},
            timeout=10,
        )
        if resp.status_code == 400:
            return None
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or len(data) < 2:
            return None

        def _oi(x: dict) -> float:
            return float(x.get("sumOpenInterest") or x.get("openInterest") or 0)

        prev, last = _oi(data[-2]), _oi(data[-1])
        if prev == 0:
            return None
        return (last - prev) / prev * 100.0
    except Exception:  # noqa: BLE001
        return None


def _fetch_klines_ohlcv(binance_symbol: str, interval: str, limit: int) -> list[dict]:
    """Fetch OHLCV klines (oldest→newest)."""
    try:
        resp = requests.get(
            "https://fapi.binance.com/fapi/v1/klines",
            params={"symbol": binance_symbol, "interval": interval, "limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        return [
            {
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            }
            for k in resp.json()
        ]
    except Exception:  # noqa: BLE001
        return []


# v45: 公开 API — scorer._build_ai_training_row 通过这两个名字引用
# 之前 scorer 的 ImportError 让每次 ai_training_data 写入静默失败
def fetch_klines_ohlcv(binance_symbol: str, interval: str, limit: int) -> list[dict]:
    """公开包装：返回 OHLCV dict 列表（oldest→newest）。"""
    return _fetch_klines_ohlcv(binance_symbol, interval, limit)


def fetch_klines_full(
    binance_symbol: str, interval: str, limit: int
) -> tuple[list[float], list[float], list[float]]:
    """公开包装：返回 (highs, lows, closes) 三个并列列表（oldest→newest）。
    用于 scorer._build_ai_training_row 给 v41_risk_manager 喂数据。"""
    bars = _fetch_klines_ohlcv(binance_symbol, interval, limit)
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]
    return highs, lows, closes


# ---------------------------------------------------------------------------
# Single-symbol deep collection
# ---------------------------------------------------------------------------

async def _collect_one(
    binance_symbol: str,
    sem: asyncio.Semaphore,
) -> tuple[str, dict] | None:
    """
    Deep-collect a single symbol.  Returns (binance_symbol, metrics) or None
    if the symbol was filtered by Level-1 analysis.
    """
    async with sem:
        # --- Level-1 structure analysis ---
        level1_result: dict | None = None
        try:
            from whale_detector import analyze_structure_level_1  # type: ignore

            ohlcv_1h = await asyncio.to_thread(_fetch_klines_ohlcv, binance_symbol, "1h", 10)
            ohlcv_4h = await asyncio.to_thread(_fetch_klines_ohlcv, binance_symbol, "4h", 10)
            if ohlcv_1h and ohlcv_4h:
                phase, reason = analyze_structure_level_1(ohlcv_1h, ohlcv_4h)
                if phase == "P4_CRASHING":
                    print(f"[DeepCollector] {binance_symbol} 被 Level-1 过滤：{reason}")
                    return None
                level1_result = {"phase": phase, "reason": reason}
        except ImportError:
            pass
        except Exception as e:  # noqa: BLE001
            print(f"[DeepCollector] {binance_symbol} Level-1 分析失败: {e}")

        # --- Fast metrics ---
        try:
            fast = await asyncio.to_thread(_fetch_price_and_funding, binance_symbol)
        except Exception as e:  # noqa: BLE001
            print(f"[DeepCollector] {binance_symbol} 快指标获取失败: {e}")
            return None

        price = float(fast["price"])
        funding_rate = float(fast["funding_rate"])

        # --- Slow metrics (OI + LS) ---
        oi_value: float | None = await asyncio.to_thread(_fetch_oi, binance_symbol)
        ls_ratio: float | None = await asyncio.to_thread(_fetch_ls_ratio, binance_symbol)

        # --- 1-hour change rates ---
        price_change: float | None = await asyncio.to_thread(
            _fetch_price_change_1h, binance_symbol
        )
        oi_change: float | None = None
        if oi_value is not None:
            oi_change = await asyncio.to_thread(_fetch_oi_change_1h, binance_symbol)

        metrics: dict[str, Any] = {
            "symbol": binance_symbol,
            "ccxt_symbol": binance_symbol_to_ccxt_symbol(binance_symbol),
            "price": price,
            "funding_rate": funding_rate,
            "oi_value": oi_value,
            "ls_ratio": ls_ratio,
            "price_change": price_change,
            "oi_change": oi_change,
            "_ts": time.time(),
        }
        if level1_result:
            metrics["level1_phase"] = level1_result["phase"]
            metrics["level1_reason"] = level1_result["reason"]

        return binance_symbol, metrics


# ---------------------------------------------------------------------------
# Class
# ---------------------------------------------------------------------------

class DeepCollector:
    """
    Async task: reads top-mover lists from *movers_queue*, deep-collects each
    symbol every *deep_scan_interval* seconds, and pushes enriched metric
    dicts to *enriched_queue*.

    Constructor args:
        movers_queue      – asyncio.Queue supplying mover lists from MarketScanner.
        enriched_queue    – asyncio.Queue to push enriched metric dicts.
        deep_scan_interval – seconds between deep-scan cycles (default 60).
        max_concurrency   – max simultaneous HTTP requests per cycle (default 10).
    """

    def __init__(
        self,
        movers_queue: asyncio.Queue,
        enriched_queue: asyncio.Queue,
        *,
        deep_scan_interval: float = _DEFAULT_DEEP_SCAN_INTERVAL,
        max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        self.movers_queue = movers_queue
        self.enriched_queue = enriched_queue
        self.deep_scan_interval = deep_scan_interval
        self._sem = asyncio.Semaphore(max_concurrency)

        # Most-recent mover list (updated whenever a new one arrives)
        self._current_movers: list[tuple[str, float, str]] = []

    async def run(self) -> None:
        """
        Main coroutine.  Run with asyncio.create_task() or asyncio.gather().
        """
        print(
            f"[DeepCollector] 启动，深度采集间隔 {self.deep_scan_interval}s，"
            f"最大并发 {self._sem._value}"
        )

        last_deep_ts = 0.0

        while True:
            try:
                # Non-blockingly drain movers_queue to get the latest snapshot
                while True:
                    try:
                        movers = self.movers_queue.get_nowait()
                        self._current_movers = movers
                    except asyncio.QueueEmpty:
                        break

                now = time.time()
                if now - last_deep_ts >= self.deep_scan_interval and self._current_movers:
                    last_deep_ts = now
                    symbols = [m[0] for m in self._current_movers]
                    print(f"[DeepCollector] 开始深度采集：{symbols}")

                    tasks = [_collect_one(sym, self._sem) for sym in symbols]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    enriched_count = 0
                    for result in results:
                        if isinstance(result, Exception):
                            print(f"[DeepCollector] 深度采集异常: {result}")
                            continue
                        if result is None:
                            continue
                        _sym, metrics = result
                        try:
                            self.enriched_queue.put_nowait(metrics)
                            enriched_count += 1
                        except asyncio.QueueFull:
                            print(
                                f"[CRITICAL] enriched_queue 已满，丢弃 {_sym} 的深度数据"
                                f"（队列大小: {self.enriched_queue.qsize()}）"
                            )

                    print(f"[DeepCollector] 深度采集完成：{enriched_count}/{len(symbols)} 个")

            except asyncio.CancelledError:
                print("[DeepCollector] 收到取消信号，退出")
                return
            except Exception as e:  # noqa: BLE001
                print(f"[DeepCollector] 主循环异常: {type(e).__name__}: {e}")

            await asyncio.sleep(1.0)
