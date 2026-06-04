"""
API 依赖注入模块

提供 FastAPI Depends 函数：
  - get_db()              → LocalDB（SQLite，主要使用）
  - get_supabase()        → Supabase 客户端（已废弃，返回 None）
  - get_supabase_optional() → 同上
  - check_kill_switch()   → 检查 Kill Switch 状态
"""

import os
from fastapi import HTTPException, status
from scripts.local_db import get_local_db, LocalDB


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
