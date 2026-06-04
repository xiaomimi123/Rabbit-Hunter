"""
Rabbit Hunter FastAPI 控制层

应用入口：创建 FastAPI 实例并注册所有路由。
业务逻辑已分拆至 routes/、schemas/、services/ 子模块。
"""

import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# 添加项目根目录到路径（scripts/ 等模块依赖此路径）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print("[INFO] Rabbit Hunter API 启动中...")

    # 启动 WebSocket 后台任务
    try:
        from api.websocket_server import broadcast_kill_queue_updates
        import asyncio
        asyncio.create_task(broadcast_kill_queue_updates(interval=5))
        print("[INFO] WebSocket 后台任务已启动")
    except Exception as e:
        print(f"[WARNING] WebSocket 后台任务启动失败: {e}")

    yield

    print("[INFO] Rabbit Hunter API 关闭中...")


# ============================================
# 初始化 FastAPI 应用
# ============================================

app = FastAPI(
    title="Rabbit Hunter API",
    description="Rabbit Hunter 交易系统 API",
    version="4.3.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# 注册路由
# ============================================

from api.routes.positions import router as positions_router
from api.routes.scores import router as scores_router
from api.routes.weights import router as weights_router
from api.routes.market import router as market_router
from api.routes.system import router as system_router

app.include_router(positions_router)
app.include_router(scores_router)
app.include_router(weights_router)
app.include_router(market_router)
app.include_router(system_router)

# ============================================
# WebSocket 端点（直接挂载，不走 APIRouter）
# ============================================


@app.websocket("/ws/v43")
async def websocket_v43(websocket: WebSocket):
    """V4.3 WebSocket 端点"""
    from api.websocket_server import websocket_endpoint
    await websocket_endpoint(websocket)
