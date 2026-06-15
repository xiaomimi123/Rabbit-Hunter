"""8 个预置失败模式 — 系统启动时 seed 进 DB。

key 是 snake_case 唯一标识。
detection_rule 是 mini-DSL,Task 7 的 matcher 会解释。
"""
from typing import List


SEEDS: List[dict] = [
    {
        "key": "late_entry_signal_decay",
        "label_zh": "信号衰减后晚入场",
        "label_en": "Late entry after signal decay",
        "description": "RSI 已极端但 MACD hist 已经从拐点退太远,等于追在反转点之后。",
        "detection_rule": "entry_rsi_15m > 70 AND ABS(macd_hist_prev_15m / macd_hist_15m) < 0.3",
    },
    {
        "key": "macd_false_cross",
        "label_zh": "MACD 假拐点",
        "label_en": "MACD false crossover",
        "description": "MACD hist 单根 K 线翻转后又翻回,实际不是趋势转折。",
        "detection_rule": "macd_recross_within_3_bars",
    },
    {
        "key": "against_4h_trend_no_funding_filter",
        "label_zh": "逆 4h 趋势无 funding 确认",
        "label_en": "Counter-trend without funding rate confirmation",
        "description": "15m 入场方向跟 4h MACD 主趋势相反,且 funding rate 没给极端反向信号,大概率被趋势收割。",
        "detection_rule": "SIGN(side_int) != SIGN(macd_hist_4h) AND ABS(funding_z_score) < 1.5",
    },
    {
        "key": "sl_too_tight_in_high_atr",
        "label_zh": "高波动期 SL 过紧",
        "label_en": "SL too tight under high ATR regime",
        "description": "ATR 在历史高分位,但 SL 距离不到 1.2x ATR,容易被正常波动吃掉。",
        "detection_rule": "atr_15m > P75_atr_30d AND sl_distance_atr_ratio < 1.2",
    },
    {
        "key": "tp_too_far_in_low_atr",
        "label_zh": "低波动期 TP 过远",
        "label_en": "TP too far under low ATR regime",
        "description": "ATR 在历史低分位,但 TP 距离超过 2.8x ATR,时间窗内根本走不到。",
        "detection_rule": "atr_15m < P25_atr_30d AND tp_distance_atr_ratio > 2.8",
    },
    {
        "key": "news_event_30min_blackout",
        "label_zh": "宏观数据 30 分钟内入场",
        "label_en": "Entry within 30 min of macro event",
        "description": "CPI / FOMC / NFP 发布前后 30 分钟,波动方向不可预测,纪律性回避。",
        "detection_rule": None,    # 需挂日历,Phase 2 暂留 NULL
    },
    {
        "key": "chase_after_3pct_move",
        "label_zh": "追在 3% 大幅之后",
        "label_en": "Chase after 3% rapid move",
        "description": "15m 已经走出 ≥2.5% 单边,这时候开同方向单是典型 FOMO 陷阱。",
        "detection_rule": "ABS(delta_15m_pct) > 0.025",
    },
    {
        "key": "repeat_failure_same_symbol_24h",
        "label_zh": "24h 内同币重复亏",
        "label_en": "Repeat failure on same symbol within 24h",
        "description": "过去 24h 该 symbol 已经有 ≥2 笔 LOSS,大概率市场制度对该币不友好。",
        "detection_rule": "symbol_loss_count_24h >= 2",
    },
]
