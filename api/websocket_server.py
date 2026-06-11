"""
V4.3 WebSocket 服务器

提供实时数据推送：
- 猎杀队列更新
- 持仓更新
- AI 进化事件
- 系统状态更新
- 图表数据更新
- 交易确认

v45：bearer 鉴权（与 HTTP 路由的 require_auth 平行）
  浏览器 WS 升级不能发自定义 Authorization 头，所以走 query string：
    ws://host:port/ws/v43?token=<API_BEARER_TOKEN>
  未配置 API_BEARER_TOKEN 时不强制（默认本机模式兼容）。
  注意：query string 会进 nginx/uvicorn 的 access log；单机使用风险可控，
  若日后接入反代部署，建议改成 cookie / 短期 ticket。
"""

import os
import secrets
from typing import Dict, List, Set, Optional

from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json
from datetime import datetime

# TODO(v5): rewire kill_queue broadcast to use V5SignalManager
try:
    from scripts.v43_kill_queue_manager import get_kill_queue_manager  # type: ignore[import-not-found]
except ImportError:
    get_kill_queue_manager = None  # type: ignore[assignment]


def _expected_bearer_token() -> Optional[str]:
    """运行时读取，避免锁死值（与 api/dependencies.py 行为一致）"""
    tok = os.environ.get("API_BEARER_TOKEN", "").strip()
    return tok or None


async def _authorize_ws(websocket: WebSocket) -> bool:
    """校验 WS 升级的 bearer token。
    - API_BEARER_TOKEN 未设 → 直接放行（兼容默认本机模式）
    - 已设 → 必须 ?token=<value> 或 ?api_key=<value> 且 constant-time 相等
    失败时返回 False 并 close(code=4401)；调用方应立即 return。
    """
    expected = _expected_bearer_token()
    if expected is None:
        return True
    # query_params: starlette QueryParams（dict-like），支持 .get
    qp = websocket.query_params
    provided = (qp.get("token") or qp.get("api_key") or "").strip()
    if provided and secrets.compare_digest(provided, expected):
        return True
    # 1008 = Policy Violation；自定义 4401 也常用作"WS 鉴权失败"
    await websocket.close(code=4401, reason="Unauthorized")
    print("[WebSocket] 鉴权失败：query 中缺少或不匹配 bearer token")
    return False


class WebSocketManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.subscriptions: Dict[WebSocket, List[str]] = {}  # 每个连接订阅的事件类型
    
    async def connect(self, websocket: WebSocket):
        """接受新的 WebSocket 连接"""
        await websocket.accept()
        self.active_connections.add(websocket)
        self.subscriptions[websocket] = []
        print(f"[WebSocket] 新连接建立，当前连接数: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        self.active_connections.discard(websocket)
        self.subscriptions.pop(websocket, None)
        print(f"[WebSocket] 连接断开，当前连接数: {len(self.active_connections)}")
    
    def subscribe(self, websocket: WebSocket, event_type: str):
        """订阅事件类型"""
        if websocket in self.subscriptions:
            if event_type not in self.subscriptions[websocket]:
                self.subscriptions[websocket].append(event_type)
    
    def unsubscribe(self, websocket: WebSocket, event_type: str):
        """取消订阅"""
        if websocket in self.subscriptions:
            self.subscriptions[websocket].remove(event_type)
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """发送个人消息"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"[WebSocket] 发送消息失败: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, message: dict, event_type: str = None):
        """广播消息给所有订阅了该事件类型的连接"""
        if event_type:
            # 只发送给订阅了该事件类型的连接
            targets = [
                ws for ws in self.active_connections
                if event_type in self.subscriptions.get(ws, [])
            ]
        else:
            # 发送给所有连接
            targets = list(self.active_connections)
        
        disconnected = []
        for connection in targets:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"[WebSocket] 广播消息失败: {e}")
                disconnected.append(connection)
        
        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)


# 全局 WebSocket 管理器
websocket_manager = WebSocketManager()


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点处理函数（bearer 鉴权 → accept → 订阅循环）"""
    # 先鉴权再 accept；失败时 _authorize_ws 已经 close 过了
    if not await _authorize_ws(websocket):
        return
    await websocket_manager.connect(websocket)
    
    try:
        # 发送欢迎消息
        await websocket_manager.send_personal_message({
            "type": "connection",
            "status": "connected",
            "timestamp": datetime.now().isoformat(),
        }, websocket)
        
        # 监听客户端消息
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                
                # 处理订阅请求
                if message.get("action") == "subscribe":
                    event_type = message.get("event_type")
                    if event_type:
                        websocket_manager.subscribe(websocket, event_type)
                        await websocket_manager.send_personal_message({
                            "type": "subscription",
                            "status": "subscribed",
                            "event_type": event_type,
                            "timestamp": datetime.now().isoformat(),
                        }, websocket)
                
                # 处理取消订阅请求
                elif message.get("action") == "unsubscribe":
                    event_type = message.get("event_type")
                    if event_type:
                        websocket_manager.unsubscribe(websocket, event_type)
                        await websocket_manager.send_personal_message({
                            "type": "subscription",
                            "status": "unsubscribed",
                            "event_type": event_type,
                            "timestamp": datetime.now().isoformat(),
                        }, websocket)
                
            except json.JSONDecodeError:
                await websocket_manager.send_personal_message({
                    "type": "error",
                    "message": "Invalid JSON format",
                    "timestamp": datetime.now().isoformat(),
                }, websocket)
    
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception as e:
        print(f"[WebSocket] 连接错误: {e}")
        websocket_manager.disconnect(websocket)


# 后台任务：定期推送数据更新
async def broadcast_kill_queue_updates(interval: int = 5):
    """定期广播信号更新 — TODO(v5): 已从 V4.3 kill_queue 切换到 V5SignalManager。"""
    # TODO(v5): rewire to V5SignalManager.list_signals() when frontend is ready
    if get_kill_queue_manager is None:
        print("[WebSocket] V4.3 kill_queue_manager 不可用，跳过广播后台任务")
        return
    while True:
        try:
            await asyncio.sleep(interval)

            # 获取最新队列数据
            manager = get_kill_queue_manager()
            result = manager.get_kill_queue(limit=20, min_score=60.0)

            # 广播更新
            await websocket_manager.broadcast({
                "type": "kill_queue_update",
                "data": result["data"],
                "metadata": result["metadata"],
                "timestamp": datetime.now().isoformat(),
            }, event_type="kill_queue_update")

        except Exception as e:
            print(f"[WebSocket] 广播猎杀队列更新失败: {e}")
            await asyncio.sleep(interval)


def start_background_tasks():
    """启动后台任务"""
    # 注意：这需要在 FastAPI 启动时调用
    # 可以使用 FastAPI 的 lifespan 事件
    pass

