"""
MarketScanner - Fast 1-second market scan for top movers.

Responsibility:
  Layer-1 (coarse filter) of the three-layer funnel:
  - Every ~1 second, fetch the full 24 h ticker snapshot from Binance Futures
    public API.
  - Run detect_movers() to score and rank abnormal symbols.
  - Push the resulting top-movers list to *movers_queue* for the
    DeepCollector to consume.

The scanner owns no persistent state beyond the current top-movers list; all
heavy work (OI, LS ratio, CVD) is delegated downstream.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from supabase import Client

# Default thresholds – overridden by TradingConfig when the class is used via
# collector_main.py.
_DEFAULT_MIN_VOLUME_24H: float = 10_000_000   # 10 M USDT
_DEFAULT_PRICE_CHANGE_THRESHOLD: float = 5.0  # abs(24h %) to flag a mover
_DEFAULT_VOLUME_SPIKE_MIN_MULT: float = 5.0   # quoteVolume > MIN_VOL * this
_DEFAULT_TOP_MOVERS_COUNT: int = 10
_DEFAULT_SCAN_INTERVAL: float = 1.0

# Symbols always excluded from mover detection
_EXCLUDED_SYMBOLS: frozenset[str] = frozenset({"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"})


# ---------------------------------------------------------------------------
# Pure functions (importable without instantiating the class)
# ---------------------------------------------------------------------------

def scan_all_markets_via_public_api() -> dict[str, dict]:
    """
    Layer-1 (coarse scan): fetch all 24 h tickers from Binance Futures in one
    HTTP call.

    Returns a dict {binance_symbol: ticker_dict} limited to USDT-margined
    perpetuals.

    Raises an exception on network failure (caller should handle gracefully).
    """
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        all_tickers = response.json()
    except Exception as e:  # noqa: BLE001
        raise Exception(f"全市场扫描失败: {e}") from e

    result: dict[str, dict] = {}
    for ticker in all_tickers:
        symbol = ticker.get("symbol", "")
        if symbol.endswith("USDT"):
            result[symbol] = ticker
    return result


def detect_movers(
    tickers: dict[str, dict],
    supabase: "Client | None" = None,
    *,
    min_volume_24h: float = _DEFAULT_MIN_VOLUME_24H,
    price_change_threshold: float = _DEFAULT_PRICE_CHANGE_THRESHOLD,
    volume_spike_min_mult: float = _DEFAULT_VOLUME_SPIKE_MIN_MULT,
    top_movers_count: int = _DEFAULT_TOP_MOVERS_COUNT,
    skip_24h_drop_pct: float | None = None,
) -> list[tuple[str, float, str]]:
    """
    Layer-1 filter: score and rank abnormal symbols from a ticker snapshot.

    Scoring logic:
      - Exclude BTC / ETH / BNB / SOL (majors).
      - Exclude symbols with 24 h quoteVolume < *min_volume_24h*.
      - Optionally exclude symbols with 24 h change <= *skip_24h_drop_pct*.
      - Flag as mover if abs(24h %) >= *price_change_threshold* OR
        quoteVolume > min_volume_24h * *volume_spike_min_mult*.
      - Score = abs(24h %) + (volume / 1_000_000) * 0.1.

    Returns [(symbol, score, reason), ...] sorted by score descending,
    truncated to *top_movers_count*.
    """
    movers: list[tuple[str, float, str]] = []

    for symbol, ticker in tickers.items():
        if symbol in _EXCLUDED_SYMBOLS:
            continue

        volume_24h = float(ticker.get("quoteVolume", 0))
        if volume_24h < min_volume_24h:
            continue

        price_change_24h = float(ticker.get("priceChangePercent", 0))
        volume_raw = float(ticker.get("volume", 0))

        if skip_24h_drop_pct is not None and price_change_24h <= skip_24h_drop_pct:
            continue

        score = abs(price_change_24h) + (volume_raw / 1_000_000) * 0.1

        if abs(price_change_24h) >= price_change_threshold:
            reason = f"24h涨跌{price_change_24h:+.2f}%"
            movers.append((symbol, score, reason))
        elif volume_24h > min_volume_24h * volume_spike_min_mult:
            reason = f"放量{volume_24h / 1_000_000:.1f}M"
            movers.append((symbol, score, reason))

    movers.sort(key=lambda x: x[1], reverse=True)
    return movers[:top_movers_count]


# ---------------------------------------------------------------------------
# Class
# ---------------------------------------------------------------------------

class MarketScanner:
    """
    Async task: continuously scans Binance Futures every *scan_interval*
    seconds and pushes the top-movers list to *movers_queue*.

    Each queue item is the full list:
        List[Tuple[binance_symbol: str, score: float, reason: str]]

    Constructor args:
        movers_queue    – asyncio.Queue to push results into.
        scan_interval   – seconds between scans (default 1.0).
        min_volume_24h  – minimum 24 h quoteVolume in USDT (default 10 M).
        top_movers_count – how many symbols to keep per scan (default 10).
        skip_24h_drop_pct – optional: skip symbols with 24 h change below
                            this threshold (e.g. -20.0 to skip crash coins).
        supabase        – optional Supabase client (currently unused in scan
                          logic but kept for future enrichment).
    """

    def __init__(
        self,
        movers_queue: asyncio.Queue,
        *,
        scan_interval: float = _DEFAULT_SCAN_INTERVAL,
        min_volume_24h: float = _DEFAULT_MIN_VOLUME_24H,
        top_movers_count: int = _DEFAULT_TOP_MOVERS_COUNT,
        skip_24h_drop_pct: float | None = None,
        supabase: "Client | None" = None,
    ) -> None:
        self.movers_queue = movers_queue
        self.scan_interval = scan_interval
        self.min_volume_24h = min_volume_24h
        self.top_movers_count = top_movers_count
        self.skip_24h_drop_pct = skip_24h_drop_pct
        self.supabase = supabase

        # Exposed so other components can read the latest result without
        # waiting for a queue item.
        self.current_movers: list[tuple[str, float, str]] = []

    async def run(self) -> None:
        """
        Main coroutine.  Run with asyncio.create_task() or include in an
        asyncio.gather() call.  Exits only on KeyboardInterrupt or if the
        calling task is cancelled.
        """
        print(
            f"[MarketScanner] 启动，扫描间隔 {self.scan_interval}s，"
            f"最低成交量 {self.min_volume_24h / 1_000_000:.0f}M USDT，"
            f"Top {self.top_movers_count}"
        )

        while True:
            loop_start = time.time()
            try:
                tickers = await asyncio.to_thread(scan_all_markets_via_public_api)
                movers = await asyncio.to_thread(
                    lambda: detect_movers(
                        tickers,
                        self.supabase,
                        min_volume_24h=self.min_volume_24h,
                        top_movers_count=self.top_movers_count,
                        skip_24h_drop_pct=self.skip_24h_drop_pct,
                    )
                )
                self.current_movers = movers

                if movers:
                    top5 = ", ".join(m[0] for m in movers[:5])
                    print(
                        f"[MarketScanner] 发现 {len(movers)} 个异动币种"
                        f"（Top 5: {top5}）"
                    )
                else:
                    print("[MarketScanner] 本轮未发现异动币种")

                # Put latest snapshot; drop old one if queue is full to avoid
                # blocking the scan loop.
                try:
                    # Replace stale item when full (best-effort, non-blocking).
                    if self.movers_queue.full():
                        try:
                            self.movers_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    self.movers_queue.put_nowait(movers)
                except asyncio.QueueFull:
                    pass  # Deep collector hasn't consumed yet – skip this tick

            except asyncio.CancelledError:
                print("[MarketScanner] 收到取消信号，退出扫描循环")
                return
            except Exception as e:  # noqa: BLE001
                print(f"[MarketScanner] 扫描出错：{type(e).__name__}: {e}")
                # Brief back-off on error to avoid spinning on persistent failures
                await asyncio.sleep(5)
                continue

            elapsed = time.time() - loop_start
            await asyncio.sleep(max(0.0, self.scan_interval - elapsed))
