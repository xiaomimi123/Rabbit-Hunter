"""
API 依赖注入模块

提供 FastAPI Depends 函数：
  - get_db()              → LocalDB（SQLite，主要使用）
  - get_supabase()        → Supabase 客户端（已废弃，返回 None）
  - get_supabase_optional() → 同上
  - check_kill_switch()   → 检查 Kill Switch 状态
  - require_auth()        → Bearer token 校验（v45 新增）
"""

import os
import secrets
from typing import Optional
from fastapi import Header, HTTPException, status
from scripts.local_db import get_local_db, LocalDB


# ============================================
# Bearer Token 鉴权（v45 新增）
# ============================================

def _read_bearer_token() -> Optional[str]:
    """运行时读取 API_BEARER_TOKEN，避免模块加载时锁死值（便于测试 + 热重载）"""
    tok = os.environ.get("API_BEARER_TOKEN", "").strip()
    return tok or None


async def require_auth(authorization: Optional[str] = Header(default=None)) -> None:
    """
    FastAPI 依赖：要求 Authorization: Bearer <API_BEARER_TOKEN> 头。

    行为模型：
      - 未设置 API_BEARER_TOKEN → 跳过校验（兼容默认 127.0.0.1 单机模式）
      - 设置了 API_BEARER_TOKEN → 缺失/不匹配返回 401

    比较用 secrets.compare_digest，避免时序侧信道。
    """
    expected = _read_bearer_token()
    if expected is None:
        return  # 未配置 token = 走默认本机模式

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization scheme (expected 'Bearer <token>')",
            headers={"WWW-Authenticate": "Bearer"},
        )

    provided = parts[1].strip()
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ============================================
# SQLite 本地数据库（主要依赖）
# ============================================

def get_db() -> LocalDB:
    """获取本地 SQLite 数据库实例（永不失败）。"""
    return get_local_db()


# ============================================
# Supabase 兼容层（已废弃，保留向后兼容）
# ============================================

# 尝试初始化 Supabase（如果配置了的话，用于迁移期过渡）
_supabase = None

try:
    from supabase import create_client  # type: ignore[import-not-found]

    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

    if SUPABASE_URL and SUPABASE_KEY:
        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("[INFO] Supabase 客户端初始化成功（迁移期兼容）")
except Exception:
    pass  # Supabase 不可用时静默忽略


def get_supabase():
    """
    已废弃：返回 LocalDB 实例替代 Supabase。
    保留此函数是为了不修改路由签名。
    """
    return get_local_db()


def get_supabase_optional():
    """已废弃：返回 LocalDB 实例替代 Supabase（可选版本）。"""
    return get_local_db()


# ============================================
# 辅助函数
# ============================================

def check_kill_switch(db=None) -> bool:
    """
    检查 Kill Switch 状态。
    从 system_settings 表读取 kill_switch 键。
    """
    client = db if db is not None else get_local_db()
    try:
        response = (
            client.table("system_settings")
            .select("value")
            .eq("key", "kill_switch")
            .execute()
        )
        if response.data and response.data[0].get("value") == "ON":
            return True
        return False
    except Exception:
        return False
