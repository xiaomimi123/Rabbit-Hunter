"""V5ReflectionWorker — poll reflection_queue → run reflection → record outcome.

- 每 30s poll
- AI 失败 → retry_count++ + error 落库,3 次后放弃
- AI 调用走注入的 ai_call (便于测试 + 切换 provider)
"""
import asyncio
import sqlite3
import traceback
from typing import Awaitable, Callable, List, Optional

from scripts.ai.reflection_runner import run_reflection_for_trade


AICall = Callable[[str], Awaitable[str]]

POLL_INTERVAL_S = 30
MAX_RETRIES = 3


class V5ReflectionWorker:
    """async poll-loop worker。"""

    def __init__(self, *, db_path: str, ai_call: AICall,
                 ai_provider: Optional[str] = None,
                 ai_model: Optional[str] = None,
                 taxonomy_keys: Optional[List[str]] = None,
                 poll_interval_s: int = POLL_INTERVAL_S):
        self.db_path = db_path
        self.ai_call = ai_call
        self.ai_provider = ai_provider
        self.ai_model = ai_model
        self.taxonomy_keys = taxonomy_keys or []
        self.poll_interval_s = poll_interval_s

    def _fetch_pending(self, limit: int = 5) -> List[int]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT paper_trade_id FROM reflection_queue "
                "WHERE completed_at IS NULL AND retry_count < ? "
                "ORDER BY id LIMIT ?",
                (MAX_RETRIES, limit),
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    def _mark_started(self, paper_trade_id: int) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE reflection_queue SET started_at = datetime('now') "
                "WHERE paper_trade_id=?", (paper_trade_id,)
            )
            conn.commit()
        finally:
            conn.close()

    def _mark_completed(self, paper_trade_id: int) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE reflection_queue SET completed_at = datetime('now'), "
                "error = NULL WHERE paper_trade_id=?", (paper_trade_id,)
            )
            conn.commit()
        finally:
            conn.close()

    def _mark_failed(self, paper_trade_id: int, error: str) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE reflection_queue SET retry_count = retry_count + 1, "
                "error = ? WHERE paper_trade_id=?",
                (error[:500], paper_trade_id),
            )
            conn.commit()
        finally:
            conn.close()

    async def _tick(self) -> None:
        pending = self._fetch_pending()
        for pid in pending:
            self._mark_started(pid)
            try:
                await run_reflection_for_trade(
                    paper_trade_id=pid, db_path=self.db_path,
                    ai_call=self.ai_call,
                    ai_provider=self.ai_provider, ai_model=self.ai_model,
                    taxonomy_keys=self.taxonomy_keys,
                )
                self._mark_completed(pid)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                self._mark_failed(pid, err)
                print(f"[V5ReflectionWorker] paper_trade {pid} failed: {err}")
                traceback.print_exc()

    async def run(self) -> None:
        from datetime import datetime, timezone
        print(f"[V5ReflectionWorker] 启动,间隔 {self.poll_interval_s}s")
        last_daily_date: Optional[str] = None

        while True:
            try:
                await self._tick()

                # Daily aggregate at 03:00 UTC (once per UTC date)
                now = datetime.now(timezone.utc)
                today_str = now.strftime("%Y-%m-%d")
                if now.hour >= 3 and last_daily_date != today_str:
                    try:
                        from scripts.ai.setup_aggregator import aggregate_daily
                        from datetime import timedelta
                        yday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
                        n = aggregate_daily(db_path=self.db_path, target_date=yday)
                        print(f"[V5ReflectionWorker] daily aggregate {yday}: {n} setup_types")
                        last_daily_date = today_str
                    except Exception as e:
                        print(f"[V5ReflectionWorker] daily aggregate failed: {e}")

            except asyncio.CancelledError:
                print("[V5ReflectionWorker] 取消信号,退出")
                return
            except Exception as e:
                print(f"[V5ReflectionWorker] tick 异常: {type(e).__name__}: {e}")
            await asyncio.sleep(self.poll_interval_s)
