"""
DatabaseWriter — 本地 SQLite 写入队列消费者。

与原 Supabase 版本保持相同的队列接口（op/table/row/on_conflict），
内部改为写入本地 SQLite 文件（通过 scripts.local_db.LocalDB）。

Queue item format:
    {
        "op":          "insert" | "upsert",
        "table":       str,
        "row":         dict,
        "on_conflict": Optional[str]   # upsert 时使用
    }
"""

from __future__ import annotations

import asyncio
import traceback


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def safe_enqueue(queue: asyncio.Queue, item: dict, symbol: str = "", table: str = "") -> None:
    """
    非阻塞入队：队列满时打印 CRITICAL 警告并丢弃，而不是静默丢失数据。
    """
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        print(
            f"[CRITICAL] 写入队列已满，丢弃数据 "
            f"symbol={symbol} table={table}"
            f"（当前队列大小: {queue.qsize()}）"
        )


# ---------------------------------------------------------------------------
# Worker coroutine
# ---------------------------------------------------------------------------

async def _sqlite_write_worker(queue: asyncio.Queue) -> None:
    """
    后台写入 worker：从 queue 消费写任务并写入本地 SQLite。
    持续运行，单个写入失败不会中断管道。
    """
    from scripts.local_db import get_local_db  # 延迟导入，避免循环依赖

    db = get_local_db()

    while True:
        try:
            item = await queue.get()
            op = item.get("op")
            table = item.get("table")
            row = item.get("row")
            on_conflict = item.get("on_conflict")

            try:
                if op == "insert":
                    await asyncio.to_thread(
                        lambda: db.table(table).insert(row).execute()
                    )
                elif op == "upsert":
                    await asyncio.to_thread(
                        lambda: db.table(table).upsert(row, on_conflict=on_conflict).execute()
                    )
                else:
                    print(f"[WARNING] 未知写入任务类型: {op}")
            except Exception as e:  # noqa: BLE001
                print(f"[WARNING] SQLite 写入失败 ({table}): {str(e)[:200]}")
                traceback.print_exc()

        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] 写库 worker 异常: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            try:
                queue.task_done()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Class interface
# ---------------------------------------------------------------------------

class DatabaseWriter:
    """
    封装一个或多个 _sqlite_write_worker，共享同一个写入队列。

    用法与原 Supabase 版本完全相同：
        writer = DatabaseWriter(queue_maxsize=500, num_workers=2)
        writer.start()
        safe_enqueue(writer.queue, {"op": "upsert", "table": "foo", "row": {...}})
    """

    def __init__(
        self,
        supabase=None,          # 保留参数名以兼容旧调用，已不使用
        queue_maxsize: int = 500,
        num_workers: int = 2,
    ) -> None:
        self.num_workers = num_workers
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        self._tasks: list[asyncio.Task] = []

    def start(self) -> None:
        """在运行中的事件循环内启动 worker 任务。"""
        for i in range(self.num_workers):
            task = asyncio.create_task(
                _sqlite_write_worker(self.queue),
                name=f"db-writer-{i}",
            )
            self._tasks.append(task)
        print(f"[INFO] DatabaseWriter 已启动（{self.num_workers} workers，队列容量 {self.queue.maxsize}）")

    async def stop(self) -> None:
        """等待队列清空后取消所有 worker。"""
        try:
            await asyncio.wait_for(self.queue.join(), timeout=30.0)
        except asyncio.TimeoutError:
            print("[WARNING] DatabaseWriter 停止超时：仍有未完成的写入任务")
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
