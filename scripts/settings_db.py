"""动态从 system_settings 读运行时可变的设置。

优先级:DB > env > 硬编码 fallback。DB 未启用时降级到 env。
每次调用现读,不缓存 —— 交易频率下 SELECT overhead 可忽略。
"""
import os
import sqlite3
from typing import Optional


def _read_setting(conn: sqlite3.Connection, key: str) -> Optional[str]:
    """读一个 system_settings 键。表不存在 or 键不存在 → None。"""
    try:
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None


def read_sl_tp_fail_open(db_path: str) -> bool:
    """DB > env > False. 现读现返。

    返回:
      - True: system_settings.sl_tp_fail_open 或 env SL_TP_FAIL_OPEN 是
        "1"/"true"/"yes" (大小写空白忽略)
      - False: 上述都不满足
    """
    val: Optional[str] = None
    try:
        conn = sqlite3.connect(db_path)
        try:
            val = _read_setting(conn, "sl_tp_fail_open")
        finally:
            conn.close()
    except sqlite3.Error:
        val = None
    # 空字符串也降级到 env（兼容 v5_settings.py:79 的旧 `or` 行为）
    if not val:
        val = os.environ.get("SL_TP_FAIL_OPEN", "false")
    return str(val).strip().lower() in ("1", "true", "yes")
