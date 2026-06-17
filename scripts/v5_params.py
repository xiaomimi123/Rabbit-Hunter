"""V5 参数热读层 — 5s 缓存,env > DB > default 优先级。"""
import os
import sqlite3
import time
from typing import Any, Callable, Optional


_DEFAULT_TTL = 5.0
_CACHE: dict = {}              # key → (value_str, expire_ts)


def _db_path() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


# DB key → env var name
_ENV_MAP = {
    "v5_rsi_overbought":          "V5_RSI_OVERBOUGHT",
    "v5_rsi_oversold":            "V5_RSI_OVERSOLD",
    "v5_sl_atr_mult":             "V5_SL_ATR_MULT",
    "v5_tp_atr_mult":             "V5_TP_ATR_MULT",
    "v5_delta_15m_threshold":     "V5_DELTA_15M_THRESHOLD",
    "v5_min_expected_move_pct":   "MIN_EXPECTED_MOVE_PCT",
    "v5_max_concurrent":          "V5_MAX_CONCURRENT",
    "v5_max_extensions":          "V5_MAX_EXTENSIONS",
    "v5_rsi_reverse_short":       "V5_RSI_REVERSE_SHORT",
    "v5_rsi_reverse_long":        "V5_RSI_REVERSE_LONG",
    "v5_risk_per_trade":          "V43_RISK_PER_TRADE",
    "v5_leverage":                "BINANCE_LEVERAGE",
    "v5_soft_target_minutes":     "V5_SOFT_TARGET_MINUTES",
    "v5_strategy_mode":             "V5_STRATEGY_MODE",
    "v5_trend_rsi_short_threshold": "V5_TREND_RSI_SHORT_THRESHOLD",
    "v5_trend_rsi_long_threshold":  "V5_TREND_RSI_LONG_THRESHOLD",
    "v5_anti_chase_pct":            "V5_ANTI_CHASE_PCT",
    "v5_anti_chase_window_bars":    "V5_ANTI_CHASE_WINDOW_BARS",
    "v5_use_symbol_whitelist":      "V5_USE_SYMBOL_WHITELIST",
    "v5_symbol_whitelist":          "V5_SYMBOL_WHITELIST",
}


def get_param(key: str, default: Any, cast: Callable[[str], Any] = str) -> Any:
    """读参数。优先级 env > DB > default。"""
    # 1. env
    env_name = _ENV_MAP.get(key)
    if env_name:
        raw = os.environ.get(env_name, "").strip()
        if raw:
            try:
                return cast(raw)
            except (ValueError, TypeError):
                pass

    # 2. cache
    now = time.time()
    cached = _CACHE.get(key)
    if cached and cached[1] > now:
        if cached[0] is None:
            return default
        try:
            return cast(cached[0])
        except (ValueError, TypeError):
            return default

    # 3. DB
    try:
        conn = sqlite3.connect(_db_path())
        try:
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key = ? ORDER BY rowid DESC LIMIT 1",
                (key,),
            ).fetchone()
        finally:
            conn.close()
        if row and row[0] is not None:
            _CACHE[key] = (str(row[0]), now + _DEFAULT_TTL)
            try:
                return cast(row[0])
            except (ValueError, TypeError):
                return default
        else:
            # Cache the miss so repeated calls within TTL don't hit the DB
            _CACHE[key] = (None, now + _DEFAULT_TTL)
    except Exception:
        pass

    # 4. default
    return default


def invalidate_cache(key: Optional[str] = None) -> None:
    """清缓存。前端 PATCH 后调一次。"""
    if key is None:
        _CACHE.clear()
    else:
        _CACHE.pop(key, None)


DEFAULTS = {
    "v5_rsi_overbought":          70.0,
    "v5_rsi_oversold":            30.0,
    "v5_sl_atr_mult":             1.5,
    "v5_tp_atr_mult":             2.5,
    "v5_delta_15m_threshold":     0.03,
    "v5_min_expected_move_pct":   0.01,
    "v5_max_concurrent":          3,
    "v5_max_extensions":          3,
    "v5_rsi_reverse_short":       65.0,
    "v5_rsi_reverse_long":        35.0,
    "v5_risk_per_trade":          0.015,
    "v5_leverage":                10,
    "v5_soft_target_minutes":     15,
    "v5_strategy_mode":             "trend_aligned",   # "trend_aligned" | "and_strict"
    "v5_trend_rsi_short_threshold": 60.0,
    "v5_trend_rsi_long_threshold":  40.0,
    "v5_anti_chase_pct":            0.005,
    "v5_anti_chase_window_bars":    5,
    "v5_use_symbol_whitelist":      True,
    "v5_symbol_whitelist":          "",     # 空 = 用默认 V5_TOP20_WHITELIST
}

PARAM_META = {
    "v5_rsi_overbought":          (60.0, 80.0, "", "开空 RSI 阈值(>)"),
    "v5_rsi_oversold":            (20.0, 40.0, "", "开多 RSI 阈值(<)"),
    "v5_sl_atr_mult":             (0.5, 5.0,  "x", "SL 距离 ATR 倍数"),
    "v5_tp_atr_mult":             (1.0, 8.0,  "x", "TP 距离 ATR 倍数"),
    "v5_delta_15m_threshold":     (0.005, 0.10, "", "最低 15min |ΔP|"),
    "v5_min_expected_move_pct":   (0.005, 0.05, "", "最低预期收益"),
    "v5_max_concurrent":          (1, 10, "", "同时活仓数上限"),
    "v5_max_extensions":          (0, 10, "次", "AI 续仓上限"),
    "v5_rsi_reverse_short":       (50.0, 70.0, "", "SHORT 仓 RSI 反向阈值"),
    "v5_rsi_reverse_long":        (30.0, 50.0, "", "LONG 仓 RSI 反向阈值"),
    "v5_risk_per_trade":          (0.001, 0.05, "", "单笔风险预算"),
    "v5_leverage":                (1, 100, "x", "杠杆"),
    "v5_soft_target_minutes":     (5, 60, "分钟", "持仓软目标"),
    "v5_strategy_mode":             (None, None, "", "策略模式 trend_aligned 或 and_strict"),
    "v5_trend_rsi_short_threshold": (50.0, 75.0, "", "trend_aligned SHORT RSI 触发阈值"),
    "v5_trend_rsi_long_threshold":  (25.0, 50.0, "", "trend_aligned LONG RSI 触发阈值"),
    "v5_anti_chase_pct":            (0.0, 0.02, "", "anti-chase 缓冲 % (0 = 关闭)"),
    "v5_anti_chase_window_bars":    (0, 20, "", "anti-chase 回看 K 线根数 (0 = 关闭)"),
    "v5_use_symbol_whitelist":      (None, None, "", "是否启用 top-20 白名单(false = 全币)"),
    "v5_symbol_whitelist":          (None, None, "", "自定义白名单(逗号分隔,空 = 用默认 top-20)"),
}
