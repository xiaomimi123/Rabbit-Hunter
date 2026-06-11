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
import os
import time
from typing import TYPE_CHECKING, Any

try:
    import requests  # noqa: F401  — kept for V4.3 compat; not used directly here
except ImportError:
    pass  # test env without requests; pure helpers still importable

if TYPE_CHECKING:
    from supabase import Client

try:
    from .utils import symbol_to_binance_symbol, binance_symbol_to_ccxt_symbol
except Exception:
    # test env: requests not installed
    def symbol_to_binance_symbol(s):  # type: ignore[misc]
        return s

    def binance_symbol_to_ccxt_symbol(s):  # type: ignore[misc]
        return s

_DEFAULT_DEEP_SCAN_INTERVAL: float = 60.0
_DEFAULT_MAX_CONCURRENCY: int = 10


# ---------------------------------------------------------------------------
# Low-level fetch helpers — v0.5.2 起全部走 exchange_endpoints facade
# 模块按 env EXCHANGE 切换 Binance/OKX 后端，业务代码无感知。
# 这里保留原函数名作为 thin wrappers，外部 import 路径不变。
# ---------------------------------------------------------------------------

_ee_fetch_price_and_funding = None
_ee_fetch_oi = None
_ee_fetch_ls_ratio = None
_ee_fetch_price_change_1h = None
_ee_fetch_oi_change_1h = None
_ee_fetch_klines_ohlcv = None
_ee_fetch_klines_full = None
_ee_fetch_klines = None

try:
    try:
        from exchange_endpoints import (  # type: ignore[import-not-found]
            fetch_price_and_funding   as _ee_fetch_price_and_funding,
            fetch_open_interest       as _ee_fetch_oi,
            fetch_ls_ratio            as _ee_fetch_ls_ratio,
            fetch_price_change_1h     as _ee_fetch_price_change_1h,
            fetch_oi_change_1h        as _ee_fetch_oi_change_1h,
            fetch_klines_ohlcv        as _ee_fetch_klines_ohlcv,
            fetch_klines_full         as _ee_fetch_klines_full,
            fetch_klines              as _ee_fetch_klines,
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
            fetch_klines              as _ee_fetch_klines,
        )
except Exception:
    # test env: requests not installed — pure helpers below still importable
    pass


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
# V5 过滤 helpers(纯函数,导出给单元测试)
# ---------------------------------------------------------------------------

def compute_delta_15m_pct(klines_15m: list) -> float:
    """最新 15min K 线的 (close - open) / open。

    klines_15m: [(ts_ms, open, high, low, close, volume), ...]
    """
    if not klines_15m:
        return 0.0
    last = klines_15m[-1]
    open_, close = last[1], last[4]
    if open_ <= 0:
        return 0.0
    return (close - open_) / open_


def passes_delta_filter(klines_15m: list, threshold: float = 0.03) -> bool:
    """|ΔP| 必须严格 > threshold。"""
    delta = compute_delta_15m_pct(klines_15m)
    return abs(delta) > threshold


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

    async def _enrich_symbol(self, symbol: str, ticker: dict) -> bool:
        """V5 enrich path: pull 15m+4h klines, filter by |ΔP|>threshold, push EnrichedItem.

        Returns True 表示已成功推入 enriched_queue;False 表示因任何原因 drop
        (K 线拉取失败 / |ΔP| 不达标 / EnrichedItem 构造失败 / 队列满)。
        run() 用返回值做精确统计,避免 enriched_queue.qsize() 受消费者速度影响。
        """
        threshold = float(os.environ.get("V5_DELTA_15M_THRESHOLD", "0.03"))
        try:
            klines_15m = await asyncio.to_thread(_ee_fetch_klines, symbol, "15m", 50)
            klines_4h = await asyncio.to_thread(_ee_fetch_klines, symbol, "4h", 50)
        except Exception as e:
            print(f"[DeepCollector] {symbol} K 线拉取失败: {type(e).__name__}: {e}")
            return False

        if not passes_delta_filter(klines_15m, threshold):
            return False

        delta = compute_delta_15m_pct(klines_15m)
        current_price = float(ticker.get("lastPrice") or (klines_15m[-1][4] if klines_15m else 0.0))

        try:
            try:
                from v5_types import EnrichedItem  # type: ignore[import-not-found]
            except ImportError:
                from scripts.v5_types import EnrichedItem  # type: ignore[import-not-found]
        except Exception as e:
            print(f"[DeepCollector] v5_types import 失败: {e}")
            return False

        item = EnrichedItem(
            symbol=symbol,
            current_price=current_price,
            delta_15m_pct=delta,
            volume_24h_usdt=float(ticker.get("quoteVolume") or 0.0),
            klines_15m=klines_15m,
            klines_4h=klines_4h,
        )

        try:
            self.enriched_queue.put_nowait(item)
            print(f"[DeepCollector] {symbol} ΔP15m={delta*100:+.2f}% → 入 enriched")
            return True
        except asyncio.QueueFull:
            print(f"[DeepCollector] {symbol} enriched_queue 满,drop")
            return False

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

                    # V5 path:_enrich_symbol 拉 15m+4h K 线,过滤 |ΔP|>3%,
                    # 构造 EnrichedItem 推入 enriched_queue。这条路径推的是
                    # EnrichedItem 对象(不是 V4.3 dict),V5Scorer 直接消费。
                    # _enrich_symbol 返回 True/False 表示是否推入队列。
                    tasks = [self._enrich_symbol(sym, {}) for sym in symbols]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    enriched_count = sum(1 for r in results if r is True)

                    print(f"[DeepCollector] 深度采集完成：{enriched_count}/{len(symbols)} 个进入 enriched_queue")

            except asyncio.CancelledError:
                print("[DeepCollector] 收到取消信号，退出")
                return
            except Exception as e:  # noqa: BLE001
                print(f"[DeepCollector] 主循环异常: {type(e).__name__}: {e}")

            await asyncio.sleep(1.0)
