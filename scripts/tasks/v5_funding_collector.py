"""V5FundingCollector — 拉 OKX funding + 算 z-score。

- 每 5 min tick → fetch_funding_history(symbol, limit=5) 拉最近 5 个,UNIQUE 入 funding_rates
- 每 1 h cron → refresh_zscore_cache(symbols) 重算所有 cache
- 启动时跑一次 backfill_history(limit=100) 拿 90d 历史
- 单 symbol 失败不阻塞其他 symbol(swallowed + logged)
"""
import asyncio
import sqlite3
import traceback
from typing import List, Optional

from scripts.funding_okx_client import fetch_funding_history
from scripts.ai.funding_rate_calculator import refresh_zscore_cache


FETCH_INTERVAL_S = 300       # 5 min
ZSCORE_INTERVAL_S = 3600     # 1 h


class V5FundingCollector:
    """async poll-loop worker。"""

    def __init__(self, *, db_path: str, symbols: List[str],
                 fetch_interval_s: int = FETCH_INTERVAL_S,
                 zscore_interval_s: int = ZSCORE_INTERVAL_S):
        self.db_path = db_path
        self.symbols = list(symbols)
        self.fetch_interval_s = fetch_interval_s
        self.zscore_interval_s = zscore_interval_s

    def _persist(self, rows: List[dict]) -> int:
        if not rows:
            return 0
        conn = sqlite3.connect(self.db_path)
        try:
            for r in rows:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO funding_rates (
                            symbol, instrument_id, funding_time,
                            funding_rate, annualized_rate, settled_rate, source
                        ) VALUES (?, ?, ?, ?, ?, ?, 'okx')
                    """, (
                        r["symbol"], r["instrument_id"], r["funding_time"],
                        r["funding_rate"], r["annualized_rate"], r.get("settled_rate"),
                    ))
                except Exception as e:
                    print(f"[V5FundingCollector] persist row failed: {e}")
            conn.commit()
        finally:
            conn.close()
        return len(rows)

    async def _fetch_tick(self) -> None:
        """每个 symbol 拉最近 5 个 funding。单个失败不阻塞其他。"""
        for sym in self.symbols:
            try:
                rows = await asyncio.to_thread(fetch_funding_history, sym, limit=5)
                self._persist(rows)
            except Exception as e:
                print(f"[V5FundingCollector] {sym} fetch failed: {type(e).__name__}: {e}")

    async def _zscore_tick(self) -> None:
        try:
            n = await asyncio.to_thread(refresh_zscore_cache, self.symbols,
                                          db_path=self.db_path)
            print(f"[V5FundingCollector] zscore refreshed for {n} symbols")
        except Exception as e:
            print(f"[V5FundingCollector] zscore refresh failed: {e}")
            traceback.print_exc()

    async def backfill_history(self, *, limit: int = 100) -> None:
        """启动时拉 limit 个 funding 历史(≈ 33 天 @ 8h period)。"""
        print(f"[V5FundingCollector] backfill 启动 (limit={limit}/symbol)")
        for sym in self.symbols:
            try:
                rows = await asyncio.to_thread(fetch_funding_history, sym, limit=limit)
                n = self._persist(rows)
                print(f"[V5FundingCollector] backfill {sym}: {n} rows")
            except Exception as e:
                print(f"[V5FundingCollector] backfill {sym} failed: {e}")

    async def run(self) -> None:
        """主循环:tick fetch + cron zscore。"""
        print(f"[V5FundingCollector] 启动,{len(self.symbols)} symbols,"
              f"fetch={self.fetch_interval_s}s zscore={self.zscore_interval_s}s")

        # 启动 backfill 一次
        await self.backfill_history(limit=100)
        await self._zscore_tick()

        last_fetch = 0.0
        last_zscore = 0.0
        import time
        while True:
            try:
                now = time.monotonic()
                if now - last_fetch >= self.fetch_interval_s:
                    await self._fetch_tick()
                    last_fetch = now
                if now - last_zscore >= self.zscore_interval_s:
                    await self._zscore_tick()
                    last_zscore = now
            except asyncio.CancelledError:
                print("[V5FundingCollector] 取消信号,退出")
                return
            except Exception as e:
                print(f"[V5FundingCollector] loop 异常: {type(e).__name__}: {e}")
            await asyncio.sleep(30)
