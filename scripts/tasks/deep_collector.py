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
# Low-level fetch helpers — v0.5.2 起全部走 exchange_endpoints facade
# 模块按 env EXCHANGE 切换 Binance/OKX 后端，业务代码无感知。
# 这里保留原函数名作为 thin wrappers，外部 import 路径不变。
# ---------------------------------------------------------------------------

try:
    from exchange_endpoints import (  # type: ignore[import-not-found]
        fetch_price_and_funding   as _ee_fetch_price_and_funding,
        fetch_open_interest       as _ee_fetch_oi,
        fetch_ls_ratio            as _ee_fetch_ls_ratio,
        fetch_price_change_1h     as _ee_fetch_price_change_1h,
        fetch_oi_change_1h        as _ee_fetch_oi_change_1h,
        fetch_klines_ohlcv        as _ee_fetch_klines_ohlcv,
        fetch_klines_full         as _ee_fetch_klines_full,
    )
except ImportError:
    from .exchange_endpoints import (  # type: ignore[import-not-found]
        fetch_price_and_funding   as _ee_fetch_price_and_funding,
        fetch_open_interest       as _ee_fetch_oi,
        fetch_ls_ratio            as _ee_fetch_ls_ratio,
        fetch_price_change_1h     as _ee_fetch_price_change_1h,
        fetch_oi_change_1h        as _ee_fetch_oi_change_1h,
        fetch_klines_ohlcv        as _ee_fetch_klines_ohlcv,
        fetch_klines_full         as _ee_fetch_klines_full,
    )


def _fetch_price_and_funding(binance_symbol: str) -> dict:
    """{price, funding_rate} — exchange-agnostic（facade 处理 OKX/Binance）。"""
    return _ee_fetch_price_and_funding(binance_symbol)


def _fetch_oi(binance_symbol: str) -> float | None:
    return _ee_fetch_oi(binance_symbol)


def _fetch_ls_ratio(binance_symbol: str) -> float | None:
    return _ee_fetch_ls_ratio(binance_symbol)


def _fetch_price_change_1h(binance_symbol: str) -> float | None:
    return _ee_fetch_price_change_1h(binance_symbol)


def _fetch_oi_change_1h(binance_symbol: str) -> float | None:
    return _ee_fetch_oi_change_1h(binance_symbol)


def _fetch_klines_ohlcv(binance_symbol: str, interval: str, limit: int) -> list[dict]:
    return _ee_fetch_klines_ohlcv(binance_symbol, interval, limit)


# v45: 公开 wrappers — scorer._build_ai_training_row 引用这两个名字
def fetch_klines_ohlcv(binance_symbol: str, interval: str, limit: int) -> list[dict]:
    return _ee_fetch_klines_ohlcv(binance_symbol, interval, limit)


def fetch_klines_full(
    binance_symbol: str, interval: str, limit: int
) -> tuple[list[float], list[float], list[float]]:
    return _ee_fetch_klines_full(binance_symbol, interval, limit)


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
