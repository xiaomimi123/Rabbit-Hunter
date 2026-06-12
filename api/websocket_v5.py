"""/ws/v5 endpoint。

握手:可选 ?token=<Bearer>(留给 §安全 后续启用)
心跳:服务器每 30s 发 {type:"ping"};没收到 60s pong → 主动 close
"""
import asyncio
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.services.v5_broadcast import get_broadcaster


router = APIRouter()


HEARTBEAT_INTERVAL_S = 30
SILENCE_TIMEOUT_S = 60


@router.websocket("/ws/v5")
async def ws_v5(ws: WebSocket) -> None:
    await ws.accept()
    broadcaster = get_broadcaster()
    broadcaster.register(ws)
    last_seen = time.monotonic()
    try:
        async def _heartbeat():
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL_S)
                try:
                    await ws.send_json({"type": "ping", "ts": time.time()})
                except Exception:
                    return

        hb = asyncio.create_task(_heartbeat())

        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=SILENCE_TIMEOUT_S)
                last_seen = time.monotonic()
            except asyncio.TimeoutError:
                if time.monotonic() - last_seen > SILENCE_TIMEOUT_S:
                    break
            except WebSocketDisconnect:
                break

        hb.cancel()
    finally:
        broadcaster.unregister(ws)
        try:
            await ws.close()
        except Exception:
            pass
