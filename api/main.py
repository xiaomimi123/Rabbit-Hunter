"""
Rabbit Hunter FastAPI 控制层

应用入口：创建 FastAPI 实例并注册所有路由。
业务逻辑已分拆至 routes/、schemas/、services/ 子模块。

v5 安全加固：
  - 默认绑 127.0.0.1（环境变量 API_BIND_HOST 覆盖）
  - 默认关闭 /docs、/redoc、/openapi.json（API_ENABLE_DOCS=true 开启）
  - CORS 默认 allowlist 限制到本机常见端口（API_ALLOW_ORIGINS 逗号分隔列表覆盖）
  - 设置 API_BEARER_TOKEN 后所有 HTTP 路由强制 Authorization: Bearer
  - 绑非 127.0.0.1 时若无 token，启动直接拒绝
"""

import os
import sys
from contextlib import asynccontextmanager
from typing import List

from fastapi import Depends, FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# 添加项目根目录到路径（scripts/ 等模块依赖此路径）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))


# ============================================
# 环境变量 → 配置
# ============================================

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return [s.strip() for s in raw.split(",") if s.strip()]


API_BIND_HOST = os.environ.get("API_BIND_HOST", "127.0.0.1").strip()
API_PORT = int(os.environ.get("API_PORT", "8000"))
API_BEARER_TOKEN = os.environ.get("API_BEARER_TOKEN", "").strip()
API_ENABLE_DOCS = _env_bool("API_ENABLE_DOCS", default=False)
API_ALLOW_REMOTE_NO_AUTH = _env_bool("API_ALLOW_REMOTE_NO_AUTH", default=False)

# 默认 CORS allowlist — Vite dev + 本机访问。生产请用 API_ALLOW_ORIGINS 覆盖。
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
CORS_ORIGINS = _env_list("API_ALLOW_ORIGINS", DEFAULT_CORS_ORIGINS)


# ============================================
# 启动前安全检查 — 防 LAN 裸奔
# ============================================

def _is_localhost(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


def _safety_check_or_exit() -> None:
    """绑非本机口而没设 token 时直接拒绝启动 — 防止 LAN 攻击。"""
    if _is_localhost(API_BIND_HOST):
        return
    if API_BEARER_TOKEN:
        return
    if API_ALLOW_REMOTE_NO_AUTH:
        print(
            f"[CRITICAL] API_BIND_HOST={API_BIND_HOST} 暴露到非本机，且无 API_BEARER_TOKEN — "
            f"已通过 API_ALLOW_REMOTE_NO_AUTH=true 显式放行 (不推荐)"
        )
        return
    print(
        f"[FATAL] API_BIND_HOST={API_BIND_HOST} 不是本机，但未设置 API_BEARER_TOKEN。\n"
        f"        任何能访问此地址的客户端都能直接调用 /trade/open 等接口。\n"
        f"        修复方法（三选一）：\n"
        f"          1) 改回本机：unset API_BIND_HOST 或设为 127.0.0.1\n"
        f"          2) 配置鉴权：export API_BEARER_TOKEN=$(openssl rand -hex 32)\n"
        f"          3) 显式放行（不推荐）：export API_ALLOW_REMOTE_NO_AUTH=true",
        file=sys.stderr,
    )
    sys.exit(2)


_safety_check_or_exit()


# ============================================
# 启动 banner — 让操作员一眼看清当前安全姿态
# ============================================

def _print_startup_banner() -> None:
    docs_state = "开启" if API_ENABLE_DOCS else "关闭"
    auth_state = "已配置 (Bearer token 必需)" if API_BEARER_TOKEN else "未配置 (依赖 127.0.0.1 隔离)"
    host_warn = "" if _is_localhost(API_BIND_HOST) else "  非本机绑定"
    print("=" * 60)
    print(f"[INIT] Rabbit Hunter API 启动配置")
    print(f"[INIT]   绑定地址: {API_BIND_HOST}:{API_PORT}{host_warn}")
    print(f"[INIT]   /docs:    {docs_state}  (API_ENABLE_DOCS)")
    print(f"[INIT]   鉴权:     {auth_state}")
    print(f"[INIT]   CORS:     {', '.join(CORS_ORIGINS) if CORS_ORIGINS else '(空)'}")
    print("=" * 60)


# ============================================
# 应用生命周期
# ============================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    _print_startup_banner()
    print("[INFO] Rabbit Hunter API 启动中...")

    # 启动 WebSocket 后台任务（V4.3 kill_queue 已 stub，若不可用则跳过）
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

# 仅在 API_ENABLE_DOCS=true 时开放 OpenAPI 文档界面
_docs_kwargs = {} if API_ENABLE_DOCS else {
    "docs_url": None,
    "redoc_url": None,
    "openapi_url": None,
}

app = FastAPI(
    title="Rabbit Hunter API",
    description="Rabbit Hunter 交易系统 API",
    version="5.0.0",
    lifespan=lifespan,
    **_docs_kwargs,
)

# CORS 配置 — 显式 allowlist，**绝不**与 allow_credentials=True 搭配 "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


# ============================================
# 注册路由 — 所有 HTTP 路由统一过 require_auth
# ============================================

from api.dependencies import require_auth
from api.routes.positions import router as positions_router
from api.routes.scores import router as scores_router
from api.routes import v5_strategy_config
from api.routes import v5_settings
from api.routes import v5_ai
from api.routes import v5_charts
from api.routes import v5_manual_order

# TODO(v5): weights/system/market routers still use V4.3 DB schema (Supabase).
# They are stubbed out here to keep the API importable while V5 migration proceeds.
# Re-enable each once rewired to SQLite/V5.

_global_auth = [Depends(require_auth)]

# V5 routes
app.include_router(positions_router, dependencies=_global_auth)
app.include_router(scores_router,    dependencies=_global_auth)
app.include_router(v5_strategy_config.router, dependencies=_global_auth)
app.include_router(v5_settings.router,        dependencies=_global_auth)
app.include_router(v5_ai.router,              dependencies=_global_auth)
app.include_router(v5_charts.router,          dependencies=_global_auth)
app.include_router(v5_manual_order.router,    dependencies=_global_auth)

# V4.3 routes — disabled pending V5 rewire
# app.include_router(weights_router,   dependencies=_global_auth)  # TODO(v5): rewire weights
# app.include_router(market_router,    dependencies=_global_auth)  # TODO(v5): rewire market
# app.include_router(system_router,    dependencies=_global_auth)  # TODO(v5): rewire system


# ============================================
# 健康检查 — 公开，便于 LB / 监控探活
# ============================================


@app.get("/healthz")
async def healthz() -> dict:
    """无鉴权健康检查端点。不暴露任何内部状态。"""
    return {"status": "ok"}


# ============================================
# WebSocket 端点（直接挂载，不走 APIRouter）
# 注意：require_auth 不会自动应用到 WS — 后续需要在 websocket_endpoint
# 内单独校验 query token / subprotocol 后再 accept。
# ============================================


@app.websocket("/ws/v43")
async def websocket_v43(websocket: WebSocket):
    """V4.3 WebSocket 端点（鉴权见 websocket_server 内部）"""
    from api.websocket_server import websocket_endpoint
    await websocket_endpoint(websocket)
