"""V5 信号服务 — 纯工具函数层。

ensure_utc_iso / normalize_time_fields 保留供 system.py 等路由引用。
V4.3 kill_queue 格式化函数已删除。
"""

from typing import Any, Dict


def ensure_utc_iso(ts: Any) -> Any:
    """
    把 naive ISO 8601 字符串补成 UTC-aware (+00:00)，前端 new Date()
    才会按 UTC 解析、再转浏览器本地时区显示。
    """
    if not isinstance(ts, str) or not ts:
        return ts
    # 已带时区(+/-HH:MM 或 Z) → 不改
    if ts.endswith("Z") or "+" in ts[10:] or "-" in ts[10:]:
        return ts
    return ts + "+00:00"


def normalize_time_fields(row: Dict[str, Any], *fields: str) -> Dict[str, Any]:
    """对 row 的若干时间字段就地补 UTC 标记，返回同一个 row 引用。"""
    if not isinstance(row, dict):
        return row
    for f in fields:
        if f in row:
            row[f] = ensure_utc_iso(row[f])
    return row
