"""Failure taxonomy matcher — 把 candidate dict 跟 active taxonomy 比对。

DSL 故意保持非通用化:每个 rule 直接对应一个 handler 函数。这避免了
写一个完整 SQL DSL parser,代价是 detection_rule 字段在 Phase 2 主要起
"自描述"作用,真正的匹配逻辑由 _HANDLERS 注册。

后续如需 AI 提案新模式自动转 DSL,可在 Phase 4 加 parser。
"""
import os
import sqlite3
from typing import Callable, List, Optional


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


Handler = Callable[[dict, str], bool]


def _h_late_entry_signal_decay(c: dict, db_path: str) -> bool:
    rsi = c.get("rsi_15m") or 0
    hist = c.get("macd_hist_15m") or 0
    hist_prev = c.get("macd_hist_prev_15m") or 0
    if rsi <= 70:
        return False
    if hist == 0:
        return False
    return abs(hist_prev / hist) < 0.3


def _h_macd_false_cross(c: dict, db_path: str) -> bool:
    """假拐点要看过去 3 根 K 线 — 单根 entry snapshot 看不出来。
    Phase 2 暂时返回 False (留作 Phase 4 给历史数据回算)。"""
    return False


_4H_HIST_THRESHOLD = 0.004  # 4H MACD hist 绝对值需超过此阈值才视为有效趋势信号


def _h_against_4h_trend_no_funding(c: dict, db_path: str) -> bool:
    side_int = c.get("side_int") or 0
    macd_4h = c.get("macd_hist_4h") or 0
    fz = c.get("funding_z_score")
    if side_int == 0 or abs(macd_4h) < _4H_HIST_THRESHOLD:
        return False
    same_dir = (side_int > 0 and macd_4h > 0) or (side_int < 0 and macd_4h < 0)
    if same_dir:
        return False
    # 反向 + funding 没给极端确认 → 触发
    if fz is None:
        return True
    return abs(fz) < 1.5


def _h_sl_too_tight_high_atr(c: dict, db_path: str) -> bool:
    atr = c.get("atr_15m") or 0
    ratio = c.get("sl_distance_atr_ratio") or 999
    p75 = _percentile_atr(db_path, 75, 30)
    if p75 is None or atr == 0:
        return False
    return atr > p75 and ratio < 1.2


def _h_tp_too_far_low_atr(c: dict, db_path: str) -> bool:
    atr = c.get("atr_15m") or 0
    ratio = c.get("tp_distance_atr_ratio") or 0
    p25 = _percentile_atr(db_path, 25, 30)
    if p25 is None or atr == 0:
        return False
    return atr < p25 and ratio > 2.8


def _h_news_event_blackout(c: dict, db_path: str) -> bool:
    """需挂日历,Phase 2 始终返回 False。"""
    return False


def _h_chase_after_3pct(c: dict, db_path: str) -> bool:
    dp = c.get("delta_15m_pct") or 0
    return abs(dp) > 0.025


def _h_repeat_failure_same_symbol(c: dict, db_path: str) -> bool:
    symbol = c.get("symbol")
    if not symbol:
        return False
    conn = sqlite3.connect(db_path)
    try:
        n = conn.execute("""
            SELECT COUNT(*) FROM paper_trades
             WHERE symbol = ? AND status = 'CLOSED'
               AND pnl_percent < 0
               AND exit_time >= datetime('now', '-24 hours')
        """, (symbol,)).fetchone()[0]
        return n >= 2
    finally:
        conn.close()


_HANDLERS: dict = {
    "late_entry_signal_decay":              _h_late_entry_signal_decay,
    "macd_false_cross":                      _h_macd_false_cross,
    "against_4h_trend_no_funding_filter":    _h_against_4h_trend_no_funding,
    "sl_too_tight_in_high_atr":              _h_sl_too_tight_high_atr,
    "tp_too_far_in_low_atr":                 _h_tp_too_far_low_atr,
    "news_event_30min_blackout":             _h_news_event_blackout,
    "chase_after_3pct_move":                 _h_chase_after_3pct,
    "repeat_failure_same_symbol_24h":        _h_repeat_failure_same_symbol,
}


def _percentile_atr(db_path: str, percentile: int, days: int) -> Optional[float]:
    """简化版:取 trade_scores_v5 过去 N 天的 atr_15m,按内存排序取分位。"""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT atr_15m FROM trade_scores_v5 "
            f"WHERE atr_15m IS NOT NULL "
            f"AND created_at >= datetime('now', '-{days} days') "
            f"ORDER BY atr_15m"
        ).fetchall()
    finally:
        conn.close()
    if len(rows) < 20:
        return None
    idx = int(len(rows) * percentile / 100)
    return rows[idx][0]


def match_failure_modes(candidate: dict, *, db_path: Optional[str] = None) -> List[str]:
    """对一个入场 candidate 跑所有 active taxonomy handlers,返回命中 keys."""
    db = db_path or _db()
    conn = sqlite3.connect(db)
    try:
        active_keys = [r[0] for r in conn.execute(
            "SELECT key FROM failure_taxonomy WHERE is_active=1"
        ).fetchall()]
    finally:
        conn.close()

    hits: List[str] = []
    for key in active_keys:
        handler = _HANDLERS.get(key)
        if handler is None:
            continue   # AI-proposed key not yet implemented
        try:
            if handler(candidate, db):
                hits.append(key)
        except Exception as e:
            print(f"[taxonomy] handler {key} raised {type(e).__name__}: {e}")
    return hits
