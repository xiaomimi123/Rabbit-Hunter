"""V5 WebSocket broadcast 测试。

注册 client → broadcast → 期望客户端收到 JSON。
WS 心跳 + 重连交给前端集成测试,这里只测后端契约。
"""
import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_broadcaster_send_to_all():
    """注册 mock client → broadcast → mock 收到。"""
    from api.services.v5_broadcast import V5Broadcaster
    b = V5Broadcaster()

    sent = []

    class MockWS:
        async def send_json(self, data):
            sent.append(data)

    ws = MockWS()
    b.register(ws)
    asyncio.run(b.broadcast({
        "type": "position_opened",
        "symbol": "H/USDT", "side": "SHORT", "entry": 0.166,
        "sl": 0.169, "tp": 0.162, "size_usdt": 15.0,
        "position_id": 1, "strategy_id": "v5_rsi_macd", "mode": "SHADOW",
    }))
    assert len(sent) == 1
    assert sent[0]["type"] == "position_opened"


def test_broadcaster_drops_failing_client():
    """send_json raises → 自动 unregister。"""
    from api.services.v5_broadcast import V5Broadcaster
    b = V5Broadcaster()

    class FailWS:
        async def send_json(self, data):
            raise RuntimeError("disconnected")

    ws = FailWS()
    b.register(ws)
    assert len(b._clients) == 1
    asyncio.run(b.broadcast({"type": "ping"}))
    assert len(b._clients) == 0


def test_broadcaster_multiple_clients():
    from api.services.v5_broadcast import V5Broadcaster
    b = V5Broadcaster()

    sent_a, sent_b = [], []

    class MockWS:
        def __init__(self, sink):
            self.sink = sink
        async def send_json(self, data):
            self.sink.append(data)

    b.register(MockWS(sent_a))
    b.register(MockWS(sent_b))
    asyncio.run(b.broadcast({"type": "ai_health", "healthy": True}))
    assert sent_a == sent_b == [{"type": "ai_health", "healthy": True}]
