"""V5 WebSocket broadcaster — 全局单例。

register/unregister/broadcast,失败 client 自动 unregister。
Scorer 和 PositionMonitor 在关键事件时 await broadcaster.broadcast(...)。
"""
from __future__ import annotations

import asyncio
from typing import Any, List, Optional, Protocol


class WSLike(Protocol):
    async def send_json(self, data: Any) -> None: ...


class V5Broadcaster:
    def __init__(self) -> None:
        self._clients: List[WSLike] = []
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        """Lazily create the lock inside a running event loop (Python 3.9 compat)."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def register(self, ws: WSLike) -> None:
        self._clients.append(ws)

    def unregister(self, ws: WSLike) -> None:
        try:
            self._clients.remove(ws)
        except ValueError:
            pass

    async def broadcast(self, payload: dict) -> None:
        if not self._clients:
            return
        lock = self._get_lock()
        async with lock:
            clients = list(self._clients)
        failed: List[WSLike] = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                failed.append(ws)
        if failed:
            async with lock:
                for ws in failed:
                    try:
                        self._clients.remove(ws)
                    except ValueError:
                        pass

    @property
    def client_count(self) -> int:
        return len(self._clients)


_broadcaster: Optional[V5Broadcaster] = None


def get_broadcaster() -> V5Broadcaster:
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = V5Broadcaster()
    return _broadcaster
