"""
Paper Monitor (v0.5.4) — 异步任务，跟踪所有 OPEN paper_trades 行的当前价
触发 SL/TP 时自动结算。

工作流：
  每 PAPER_MONITOR_INTERVAL_SECONDS 秒：
    1. 拉所有 status='OPEN' 的 paper_trades
    2. 对每个 symbol 调 exchange_endpoints.fetch_price_and_funding 取实时价
    3. 喂给 PaperPositionManager.update_current_price()
       → 不触发：只更新 current_price
       → 触发 SL/TP/超时：写 exit_price, pnl, status=CLOSED
    4. 控制台打 1 行汇总
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

# 与其它 tasks 同样的导入风格（容器内 PYTHONPATH 已含 /app/scripts）
try:
    from paper_position_manager import PaperPositionManager  # type: ignore[import-not-found]
    from tasks.exchange_endpoints import fetch_price_and_funding  # type: ignore[import-not-found]
except ImportError:
    from scripts.paper_position_manager import PaperPositionManager  # type: ignore[import-not-found]
    from scripts.tasks.exchange_endpoints import fetch_price_and_funding  # type: ignore[import-not-found]


class PaperMonitor:
    """异步轮询 — 每 N 秒跟踪所有 OPEN paper_trades 当前价 + SL/TP 触发结算。"""

    def __init__(self, supabase, interval_seconds: int = 30):
        self.supabase = supabase
        self.interval = max(5, int(interval_seconds))
        self._stop = False
        self.pm = PaperPositionManager(supabase_client=supabase)

    async def run(self):
        print(f"[PaperMonitor] 启动，轮询间隔 {self.interval}s")
        # 启动延迟一点，让其它任务先就位
        await asyncio.sleep(5)

        while not self._stop:
            try:
                await self._tick()
            except Exception as e:
                print(f"[PaperMonitor] 轮询出错: {e}")
            await asyncio.sleep(self.interval)

    async def _tick(self):
        positions = self.pm.load_open_positions()
        if not positions:
            return

        # 并发拉所有 symbol 的当前价（exchange_endpoints 在 facade 层就做了重试 + Session）
        tasks = []
        symbols = list(positions.keys())
        for sym in symbols:
            tasks.append(asyncio.to_thread(self._fetch_price_safe, sym))
        prices = await asyncio.gather(*tasks, return_exceptions=True)

        triggered = 0
        for sym, pr in zip(symbols, prices):
            if isinstance(pr, Exception) or pr is None:
                continue
            try:
                result = self.pm.update_current_price(sym, float(pr))
                if result and result.get("status") == "CLOSED":
                    triggered += 1
            except Exception as e:
                print(f"[PaperMonitor] {sym} update 失败: {e}")

        if triggered > 0:
            print(f"[PaperMonitor] 本轮 {triggered} 个虚拟仓位被触发结算")

    @staticmethod
    def _fetch_price_safe(symbol_ccxt: str) -> Optional[float]:
        """从 exchange_endpoints 拿当前价。symbol 是 ccxt 风格 (BTC/USDT)；
        exchange_endpoints 期望 binance flat (BTCUSDT)，做一下转换。"""
        binance_flat = symbol_ccxt.replace("/", "")
        try:
            d = fetch_price_and_funding(binance_flat)
            return float(d.get("price") or 0) or None
        except Exception:
            return None

    def stop(self):
        self._stop = True


__all__ = ["PaperMonitor"]
