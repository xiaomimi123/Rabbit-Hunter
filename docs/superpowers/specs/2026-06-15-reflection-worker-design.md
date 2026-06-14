# Reflection Worker 设计文档

> **核心目的:** 让 Rabbit Hunter 从"按固定规则跑"的静态机器人,进化为"按策略思路跑 → 自动复盘 → AI 矫正 → 自我学习仓位管理 → 持续吃更多利润"的动态机器人。
>
> **重点不在于"记录"**,而在于把每笔输赢转化为可以应用到下一次决策的结构化信号:失败模式分类 / 仓位修正建议 / AI 置信度校准 / 入场规则演化。
>
> **底层纪律:** AI 提案,人类批准,系统 A/B,赢家升级。永不让 AI 自动重写策略。

---

## §1 战略动机

### 1.1 当前 V5 的根本缺陷

V5 是**静态规则机器人**:RSI×MACD 合谋 → 开单。规则不会自己变。

这有两个致命弱点:
1. **市场制度变化时**,固定规则一定阶段性失效,你看不到信号
2. **你的策略思路本身可能有盲区**(比如 V6 funding rate 上线后,有些 setup 是糟糕的),但没有机制告诉你"这类 setup 历史 80% 是亏的,该停"

零售机器人 95% 死在这里:策略上线时回测漂亮,3 个月后市场变了,机器人继续按老规则跑亏,主人不知道。

### 1.2 Reflection Worker 解决什么

把每笔关仓的交易**转化为对下一次决策的修正信号**,具体形式:

| 输入 | Reflection 产出 | 下次决策时如何用 |
|---|---|---|
| 平仓的 paper_trade(含 entry/exit 指标 + AI reasoning + 真实结果) | 5 问结构化复盘 | 写入 RAG,下次类似 setup 时 AI 看得到 |
| 关仓事件 | 失败模式分类(taxonomy 标签) | 下次 setup 命中已知失败模式 → veto |
| 平仓后真实 R 倍 | 该 setup 类型的仓位修正建议 | 经你批准后,更新 size_multiplier |
| AI 当时声称 70% 信心 vs 实际 50% 胜率 | 该模型的 confidence calibration 曲线 | AI 下次说 70%,系统实际按 50% 处理 |
| 多笔类似失败的共性 | 新的入场过滤规则提案 | 经你批准 + A/B 验证后,加入策略 |

**关键比喻:**
- V5 = 你给机器人一本剑谱,它照练
- Reflection Worker = 机器人练完一招会自己回看录像,标"这招施展时机不对,以后避开",再让你过目同意

### 1.3 这跟 RAG-lite 有什么区别

V5 已经有 RAG-lite,记录入场参数。但它只做"找相似的过去案例丢给 AI 看",**没有结构化的学习**。

| RAG-lite(现有) | Reflection Worker(本文) |
|---|---|
| 存"过去类似的 setup 长什么样" | 存"过去类似 setup 错在哪 + 该怎么改" |
| 只在入场时查 | 入场时 + 平仓后 + 日 / 周聚合 |
| AI 看一眼自由发挥 | 5 问结构化,每问答案有 schema |
| 数据基本不被加工 | 聚合成 failure taxonomy / sizing / calibration 三套衍生 |
| 无介入策略本身的能力 | 提案新规则,经你批准后改策略 |

Reflection Worker **包含 RAG-lite**(把答案写回 ai_training_data),但**远不止 RAG**。

---

## §2 架构总览

### 2.1 五层学习闭环

```
┌────────────────────────────────────────────────────────────────────┐
│ Layer 0: 交易事件                                                   │
│   v5_position_monitor 触发关仓 → paper_trade.status = CLOSED        │
│                              ↓                                      │
│                       reflection_queue ← 入队                       │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ Layer 1: 每笔复盘(实时 / 单笔)                                    │
│   v5_reflection_worker 每 30s poll 队列                            │
│   ↓                                                                 │
│   Load context:                                                     │
│     - entry 指标 + AI reasoning + RAG cases 当时引用                │
│     - 持仓期间 K 线轨迹(15m + 4h)                                 │
│     - exit reason + 实际 R                                          │
│   ↓                                                                 │
│   AI 5 问 reflection prompt → 结构化 ReflectionOutput               │
│   ↓                                                                 │
│   reflections 表 ← 入库                                             │
│   ai_training_data ← 同步写(向后兼容 RAG)                          │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ Layer 2: 失败模式分类(实时累积)                                    │
│   - 8 个预置 failure_mode 种子(下文 §4.3)                          │
│   - AI 在每笔 reflection 时给一个 failure_mode 标签                  │
│   - 命中 ≥5 次的新模式 → 推送给你 review                            │
│   ↓                                                                 │
│   failure_taxonomy 表 累积                                          │
│   每个 mode 带 detection_rule(伪 SQL)                              │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ Layer 3: 日聚合(每日 03:00 UTC)                                    │
│   按 setup_type × 日 聚合:                                          │
│     - 样本数 / 胜率 / 平均 R / expectancy / Sharpe                   │
│     - 主要失败模式                                                   │
│   ↓                                                                 │
│   setup_performance_daily 表                                       │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ Layer 4: 仓位 + 置信度校准(每周日 04:00 UTC)                       │
│   ① 按 setup_type 跑 fractional Kelly                              │
│      → position_sizing_recommendations(待批准)                      │
│   ② 按 ai_model × confidence_bucket 算实际胜率                     │
│      → ai_confidence_calibration(自动应用)                          │
│   ③ AI 扫描最近 1 周失败案例 → 提议新 entry filter 规则             │
│      → entry_filter_proposals(待批准 + A/B)                         │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ 反馈到 trading_assistant.decide()                                   │
│   入场时 AI 现在看到:                                                │
│     ① 相似历史案例(RAG-lite 已有)                                   │
│     ② 失败模式匹配(NEW)— 命中 → veto 并标记理由                    │
│     ③ AI 自己声称的信心 × 该模型的 calibration 倍数                 │
│     ④ 该 setup_type 的 size_multiplier(NEW)                       │
│     ⑤ 已生效的 entry filter 规则(NEW)                              │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 进程层

新增一个独立后台 Python 进程,跟 `v5_position_monitor` 同级:

```
scripts/tasks/
├── deep_collector.py          # 已存在
├── scorer.py                  # 已存在
├── v5_position_monitor.py     # 已存在
└── v5_reflection_worker.py    # ★ 本文新建
```

job 调度:
- 每 30s:poll reflection_queue,处理新关仓的笔(Layer 1+2)
- 每天 03:00 UTC:跑日聚合(Layer 3)
- 每周日 04:00 UTC:跑周校准 + 提案生成(Layer 4)

实现:`v5_reflection_worker.py` 启动一个 asyncio 主循环 + 内嵌 cron-like 调度器(参考 `v5_position_monitor.py` 的模式)。

---

## §3 数据模型

### 3.1 reflection_queue(任务队列)

```sql
CREATE TABLE IF NOT EXISTS reflection_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_trade_id INTEGER NOT NULL,
    enqueued_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    UNIQUE(paper_trade_id)
);
```

由 `v5_position_monitor` 在 close_position 后插入。worker 取 `WHERE completed_at IS NULL AND retry_count < 3` 处理。

### 3.2 reflections(核心表)

```sql
CREATE TABLE IF NOT EXISTS reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_trade_id INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    -- 5 问的结构化答案
    why_entered TEXT NOT NULL,
    what_was_expected TEXT NOT NULL,
    what_actually_happened TEXT NOT NULL,
    correction_idea TEXT NOT NULL,
    failure_mode_key TEXT,                  -- FK → failure_taxonomy.key, 或 NULL(成功 / 新模式提案)

    -- 用于聚合的结构化字段
    setup_type TEXT NOT NULL,               -- e.g. 'rsi_overbought_short', 'funding_extreme_long', 'macd_flip_long'
    outcome_class TEXT NOT NULL,            -- 'WIN' / 'LOSS' / 'SCRATCH'(|R|<0.2)
    realized_r REAL NOT NULL,               -- (pnl_pct / sl_distance_pct) — 真实 R 倍
    holding_minutes INTEGER NOT NULL,
    confidence_at_entry REAL NOT NULL,

    -- AI 自身评估(用于 confidence calibration)
    self_assessed_prediction_accuracy REAL, -- 0-1, AI 自评"我之前的 prediction 跟实际有多近"
    is_in_predicted_failure_mode INTEGER,   -- AI 自评"这次失败方式是不是我预料过的"

    -- Audit
    ai_provider TEXT,
    ai_model TEXT,
    ai_latency_ms INTEGER,
    prompt_version TEXT,                    -- 用于追溯 prompt 变更
    raw_response_json TEXT                  -- 完整 AI response 原文(debug 用)
);

CREATE INDEX idx_reflections_setup_type ON reflections(setup_type, created_at);
CREATE INDEX idx_reflections_failure_mode ON reflections(failure_mode_key) WHERE failure_mode_key IS NOT NULL;
```

### 3.3 failure_taxonomy(失败模式词典)

```sql
CREATE TABLE IF NOT EXISTS failure_taxonomy (
    key TEXT PRIMARY KEY,                    -- 'late_entry_signal_decay'
    label_zh TEXT NOT NULL,                  -- '信号衰减后晚入场'
    label_en TEXT NOT NULL,                  -- 'Late entry after signal decay'
    description TEXT NOT NULL,
    detection_rule TEXT,                     -- 伪 SQL DSL(下文 §4.4)
    is_active INTEGER DEFAULT 1,             -- 0 = 软停用,但保留历史

    -- 统计(由 Layer 3 日聚合维护)
    sample_count INTEGER DEFAULT 0,
    avg_loss_pct REAL,
    last_seen_at TEXT,

    -- 来源
    seeded INTEGER DEFAULT 0,                -- 1 = 系统预置 / 0 = AI 提案后批准
    approved_by TEXT,                        -- 'user' / 'system'
    approved_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### 3.4 setup_performance_daily(日聚合)

```sql
CREATE TABLE IF NOT EXISTS setup_performance_daily (
    date TEXT NOT NULL,
    setup_type TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    win_count INTEGER NOT NULL,
    loss_count INTEGER NOT NULL,
    scratch_count INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    avg_realized_r REAL NOT NULL,
    avg_holding_minutes REAL,
    expectancy REAL,                         -- win_rate * avg_win_r - loss_rate * avg_loss_r
    sharpe_30d REAL,                         -- 滚动 30 天该 setup_type 的 sharpe
    top_failure_mode TEXT,
    PRIMARY KEY (date, setup_type)
);
```

### 3.5 position_sizing_recommendations(仓位提案)

```sql
CREATE TABLE IF NOT EXISTS position_sizing_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setup_type TEXT NOT NULL,
    proposed_at TEXT DEFAULT (datetime('now')),

    -- 现状
    current_size_multiplier REAL NOT NULL,   -- 当前 AI 倾向用的 size_multiplier

    -- 建议
    recommended_size_multiplier REAL NOT NULL,
    confidence_score REAL NOT NULL,          -- 0-1,建议的稳定性
    rationale TEXT NOT NULL,

    -- 计算依据
    sample_count_30d INTEGER,
    sample_count_60d INTEGER,
    sample_count_90d INTEGER,
    kelly_f_30d REAL,
    kelly_f_60d REAL,
    kelly_f_90d REAL,
    fractional_kelly_applied REAL,            -- 0.25 / 0.5 等,看 confidence

    -- 用户决策
    status TEXT DEFAULT 'pending',           -- 'pending' / 'approved' / 'rejected' / 'modified' / 'expired'
    user_decision_at TEXT,
    user_decision_note TEXT,
    user_modified_value REAL,                -- 如果 user 改了数

    -- A/B
    ab_test_started_at TEXT,
    ab_test_target_sample INTEGER,           -- 通常 30 笔
    ab_test_result TEXT                      -- JSON,A/B 结果
);
```

### 3.6 ai_confidence_calibration(置信度校准)

```sql
CREATE TABLE IF NOT EXISTS ai_confidence_calibration (
    ai_model TEXT NOT NULL,                  -- 'deepseek-chat' / 'gpt-4o' / 'claude-sonnet-4.6'
    confidence_bucket REAL NOT NULL,         -- 0.5 / 0.6 / 0.7 / 0.8 / 0.9
    predicted_win_rate REAL NOT NULL,        -- bucket 中心
    actual_win_rate REAL NOT NULL,
    sample_count INTEGER NOT NULL,
    calibration_multiplier REAL NOT NULL,    -- actual / predicted, 用于实时修正
    last_updated TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (ai_model, confidence_bucket)
);
```

### 3.7 entry_filter_proposals(入场过滤规则提案)

```sql
CREATE TABLE IF NOT EXISTS entry_filter_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposed_at TEXT DEFAULT (datetime('now')),

    -- 规则描述
    rule_name TEXT NOT NULL,
    rule_description_zh TEXT NOT NULL,
    detection_rule_dsl TEXT NOT NULL,         -- 伪 SQL DSL

    -- 来源证据
    based_on_failures_count INTEGER,
    based_on_setup_type TEXT,
    based_on_failure_mode_key TEXT,
    sample_evidence_json TEXT,                -- 3-5 笔代表性失败案例 ID

    -- 历史回算(规则若早就生效,会过滤掉多少笔?其中赢的多少 / 输的多少)
    backtest_filtered_count INTEGER,
    backtest_would_have_blocked_wins INTEGER,
    backtest_would_have_blocked_losses INTEGER,
    backtest_net_pnl_impact_usdt REAL,

    -- 用户审批 + A/B
    status TEXT DEFAULT 'pending',           -- 'pending' / 'approved' / 'rejected' / 'ab_testing' / 'active' / 'retired'
    user_decision_at TEXT,
    ab_started_at TEXT,
    ab_target_sample INTEGER DEFAULT 50,
    ab_actual_sample INTEGER DEFAULT 0,
    ab_pnl_with_rule REAL,
    ab_pnl_without_rule REAL,
    ab_winner TEXT                            -- 'rule' / 'no_rule' / 'inconclusive'
);
```

---

## §4 关键算法

### 4.1 setup_type 的派生

每笔交易的 setup_type 是 reflection 的主要 dimension。它由 entry 时的状态机械派生(不靠 AI):

```python
def derive_setup_type(entry: EntrySnapshot) -> str:
    side = entry.side  # SHORT/LONG
    if entry.strategy_id == 'v5_manual':
        return f'manual_{side.lower()}'

    # 自动单看 RSI + MACD 状态
    rsi = entry.rsi_15m
    macd_state = (
        'macd_bullish_cross' if entry.macd_hist_prev < 0 and entry.macd_hist > 0
        else 'macd_bearish_cross' if entry.macd_hist_prev > 0 and entry.macd_hist < 0
        else 'macd_extending'
    )
    rsi_state = (
        'rsi_overbought' if rsi >= 70
        else 'rsi_oversold' if rsi <= 30
        else 'rsi_neutral'
    )

    # V6 funding rate 上线后扩展
    if entry.funding_z_score and abs(entry.funding_z_score) >= 2.0:
        return f'funding_extreme_{"short" if entry.funding_z_score > 0 else "long"}_{rsi_state}'

    return f'{rsi_state}_{macd_state}_{side.lower()}'
```

**这一步必须确定性 + 可枚举**,因为后面所有聚合按它分桶。AI 不参与 setup_type 派生。

### 4.2 Reflection Prompt(5 问)

每笔关仓后,worker 给 AI 发的 prompt 主结构:

```
[CONTEXT]
Symbol: H/USDT
Side: SHORT
Strategy: v5_rsi_macd
Entry: 0.166 @ 2026-06-13T09:48:00Z
Exit: 0.169 @ 2026-06-13T10:15:00Z (SL_HIT)
Realized R: -1.0 (full SL hit)
Holding: 27 minutes

[ENTRY SNAPSHOT]
Indicators at entry:
  RSI 15m: 72.1
  RSI 4h: 68
  MACD hist 15m: -0.0012 (prev: +0.0008, just flipped)
  ATR 15m: 0.0015
  Funding rate (1h before): +0.045% (z-score: +2.1)

Rule decision: SHORT, reason="RSI overbought + MACD bearish cross"
AI decision: execute=true, confidence=0.7, reasoning="..."
RAG cases AI saw at entry:
  case1: RSI=73.2 hist=-0.0006 → WIN +0.4% TP_HIT
  case2: RSI=71.5 hist=-0.0004 → LOSS -0.3% SL_HIT
  case3: ... (5 cases total, 3W/2L, avg pnl +0.12%)

[DURING-HOLD MARKET PATH]
T+0: price 0.166, RSI 72.1
T+5: price 0.167, RSI 73 (extending against us)
T+15: price 0.1685, RSI 75 (RSI making new high but bot's TP not moved)
T+27: SL hit at 0.169

[PRE-SEEDED FAILURE_TAXONOMY]
1. late_entry_signal_decay: 信号衰减后晚入场
2. macd_false_cross: MACD 假拐点(单根 K 线翻转后又翻回)
3. against_4h_trend_no_funding_filter: 逆 4h 趋势无 funding 确认
4. sl_too_tight_in_high_atr: 高波动期 SL 过紧
... (full list of 8)

[YOUR TASK]
Answer the following 5 questions in JSON. Be specific. Use evidence from
the context above. Do NOT confabulate generic trading advice.

{
  "why_entered": "<causal: what specific combination triggered entry>",
  "what_was_expected": "<reconstruct: based on SL/TP/confidence, what was the AI's predicted path>",
  "what_actually_happened": "<realized: how did price actually move vs expectation>",
  "failure_mode_key": "<one of the taxonomy keys, OR 'NEW:<your_proposed_key>' if none fits>",
  "correction_idea": "<actionable: what rule, if added, would have prevented or improved this trade>",
  "self_assessed_prediction_accuracy": <0-1>,
  "is_in_predicted_failure_mode": <true/false>
}
```

**Prompt 设计原则:**
- 提供完整证据(entry snapshot + 持仓轨迹 + RAG cases AI 当时引用)
- 强制选 taxonomy(或提新)— 不允许"分类:其他"
- 要求 actionable 答案(correction_idea 必须是可写成 detection rule 的)
- 跟踪 self-assessment(用于 confidence calibration)

### 4.3 预置 failure_taxonomy(种子数据)

8 个种子模式,系统启动时 seed 进表:

| key | label_zh | detection_rule(伪 SQL DSL) |
|---|---|---|
| `late_entry_signal_decay` | 信号衰减后晚入场 | `entry_rsi_15m > 70 AND macd_hist_prev_15m / macd_hist_15m < 0.3`(MACD 已经从拐点退太远) |
| `macd_false_cross` | MACD 假拐点 | 由后续 reflection 反向归类:连续 ≤2 根反方向后回归原方向 |
| `against_4h_trend_no_funding_filter` | 逆 4h 趋势无 funding 确认 | `SIGN(entry.side_as_int) != SIGN(macd_hist_4h)` AND `funding_z_score IS NULL OR ABS(funding_z_score) < 1.5` |
| `sl_too_tight_in_high_atr` | 高波动期 SL 过紧 | `atr_15m > P75(atr_15m, 30d)` AND `sl_distance / atr_15m < 1.2` |
| `tp_too_far_in_low_atr` | 低波动期 TP 过远 | `atr_15m < P25(atr_15m, 30d)` AND `tp_distance / atr_15m > 2.8` |
| `news_event_30min_blackout` | 宏观数据 30min 内入场 | 入场时间 ± 30min 内有 CPI/FOMC/NFP(需挂日历) |
| `chase_after_3pct_move` | 追在 3% 大幅之后 | `ABS(delta_15m_pct) > 0.025` AND `executed = 1`(FOMO 陷阱) |
| `repeat_failure_same_symbol_24h` | 24h 内同币重复亏 | 该 symbol 过去 24h 内已有 ≥2 笔 LOSS |

**这些都是 deterministic detection rule**,可以离线对历史 paper_trades 跑回算。

### 4.4 detection_rule DSL

简单到能直接转 SQL 的 mini-DSL:

```
rule := condition (AND condition)*
condition := field operator value
           | field operator FIELD(other_field)
           | field operator FUNCTION(args...)

FUNCTIONS := P25 / P75 / P90  -- 分位数(基于 30/60/90d 窗口)
           | SIGN             -- 符号
           | ABS

Examples:
  atr_15m > P75(atr_15m, 30d) AND sl_distance / atr_15m < 1.2
  ABS(delta_15m_pct) > 0.025 AND executed = 1
```

**实现:** parser 把 DSL 转为 SQL 子句,执行时跑在 paper_trades JOIN trade_scores_v5 上。

### 4.5 fractional Kelly 仓位计算

每周日跑一次:

```python
def calculate_recommended_size(setup_type: str) -> SizingRecommendation:
    # 拿 30/60/90 天滚动窗口的数据
    windows = [30, 60, 90]
    kelly_fs = []
    sample_counts = []

    for d in windows:
        rows = fetch_setup_performance(setup_type, last_d_days=d)
        n = len(rows)
        if n < 10:                              # 样本不够
            kelly_fs.append(None)
            sample_counts.append(n)
            continue

        wins = [r.realized_r for r in rows if r.outcome_class == 'WIN']
        losses = [r.realized_r for r in rows if r.outcome_class == 'LOSS']

        if not wins or not losses:              # 全赢或全输,Kelly 无意义
            kelly_fs.append(None)
            sample_counts.append(n)
            continue

        p = len(wins) / n
        b = sum(wins) / len(wins)               # 平均赢的 R
        a = sum(abs(r) for r in losses) / len(losses)   # 平均输的 R
        # Kelly fraction(基于 R 倍率,不是赔率)
        f = (p / a) - ((1 - p) / b)
        kelly_fs.append(max(0, f))              # 不允许负仓
        sample_counts.append(n)

    # 三窗口一致性检查
    valid_fs = [f for f in kelly_fs if f is not None]
    if len(valid_fs) < 2:
        return SizingRecommendation(
            recommended=current_size_multiplier(setup_type),
            confidence=0.0,
            rationale='样本不足,维持现状'
        )

    spread = (max(valid_fs) - min(valid_fs)) / (max(valid_fs) + 1e-6)

    # confidence 由三窗口一致性 + 总样本量决定
    confidence = (1 - min(spread, 1.0)) * min(sum(sample_counts) / 90, 1.0)

    # fractional Kelly 系数:稳定性越高,系数越接近 0.5;不稳定时 0.25
    fk_coefficient = 0.25 + 0.25 * confidence
    raw_f = sum(f * c for f, c in zip(valid_fs, sample_counts) if f is not None) / sum(c for f, c in zip(valid_fs, sample_counts) if f is not None)
    recommended = raw_f * fk_coefficient

    # 硬性边界:[0.5%, 2%] of account
    recommended = max(0.005, min(0.02, recommended))

    return SizingRecommendation(
        recommended=recommended,
        confidence=confidence,
        rationale=f'30d Kelly={kelly_fs[0]}, 60d={kelly_fs[1]}, 90d={kelly_fs[2]}; '
                  f'三窗口一致性{(1-spread)*100:.0f}%; fractional_k={fk_coefficient}'
    )
```

**关键纪律:**
- 不是 full Kelly(理论最优,实际致命),用 fractional(0.25-0.5)
- 三窗口一致性是 confidence 的核心 — 短期 spike 不算 evidence
- 硬性边界 [0.5%, 2%] 防止任何单笔超额风险
- **永不自动应用**,生成 recommendation,前端推给用户决策

### 4.6 AI Confidence Calibration

每次 reflection 写入后增量更新:

```python
def update_calibration(ai_model: str, confidence_at_entry: float, won: bool):
    # 把 confidence 落到 0.5 / 0.6 / 0.7 / 0.8 / 0.9 桶
    bucket = round(confidence_at_entry, 1)
    if bucket < 0.5 or bucket > 0.95:
        return

    row = db.fetch_one(
        'SELECT actual_win_rate, sample_count FROM ai_confidence_calibration '
        'WHERE ai_model=? AND confidence_bucket=?',
        (ai_model, bucket)
    )
    if row is None:
        actual_wr = 1.0 if won else 0.0
        n = 1
    else:
        old_wr, n_old = row
        n = n_old + 1
        actual_wr = (old_wr * n_old + (1 if won else 0)) / n

    multiplier = actual_wr / bucket if bucket > 0 else 1.0

    db.upsert(
        'ai_confidence_calibration',
        keys=('ai_model', 'confidence_bucket'),
        values={
            'predicted_win_rate': bucket,
            'actual_win_rate': actual_wr,
            'sample_count': n,
            'calibration_multiplier': multiplier,
        }
    )
```

**应用:** trading_assistant.decide() 拿到 AI 自报的 confidence 后:

```python
ai_says_70_pct = ai_result.confidence
calibrated = ai_says_70_pct * get_calibration_multiplier(model, ai_says_70_pct)
# 比如 AI 说 0.7,但该模型 0.7 桶的真实胜率是 0.5 → 校准后 0.5
```

仓位最终 size 由校准后的 confidence 决定,不由原始 confidence。

---

## §5 前端

### 5.1 新页面 `/v5/reflection`

四个 tab:

#### Tab 1: 最近复盘流(实时)
最近 20 笔关仓的 reflection 卡片,每张卡显示 5 问答案。可点开看完整 raw_response_json。失败标签可点击进入 taxonomy 详情。

#### Tab 2: 失败模式分布
| failure_mode | 标签 | 样本数 | 平均损失 | detection_rule | 最近一次 |
|---|---|---|---|---|---|
| late_entry_signal_decay | 信号衰减后晚入场 | 12 | -0.8% | `rsi_15m > 70 AND ...` | 2 小时前 |
| ... | ... | ... | ... | ... | ... |

行可展开,显示该 mode 的代表性 3-5 笔交易链接。

#### Tab 3: 仓位建议(审批队列)
卡片列表,每张:
- setup_type:`rsi_overbought_macd_bearish_short`
- 现 size_multiplier:1.0 → **推荐:0.6** (- 40%)
- confidence:0.78
- rationale:30d Kelly=0.012, 60d=0.014, 90d=0.011;一致性 86%
- 30 笔样本:11W 19L,胜率 37%,平均 R -0.3
- 按钮:**[批准]** / [拒绝] / [修改后批准:[__]]

批准后,A/B 框架自动启动:接下来 30 笔该 setup_type 用新 multiplier,30 笔后跟旧的 PnL 对比。

#### Tab 4: 入场规则提案(审批队列)
跟 Tab 3 结构类似,但每个 proposal 多了**历史回算结果**:

| | 应用规则前 | 应用规则后(回算) |
|---|---|---|
| 交易笔数 | 87 | 65 (- 22) |
| 胜率 | 41% | 49% |
| 总 PnL | -3.2 USDT | +1.8 USDT |
| 被过滤掉的 22 笔里,赢 | 4 | — |
| 被过滤掉的 22 笔里,输 | 18 | — |

规则的"杀错率"(过滤掉本来会赢的)清晰可见,你来决定值不值。

### 5.2 AI Status 页扩展

在现有 cyber 风格 AI 页加一个新 Card:**置信度校准曲线**

```
Confidence Calibration (deepseek-chat)
────────────────────────────────────────
0.5 ●─────────●  AI 说 50% → 实际 52% (✓ 校准)
0.6     ●─────●  AI 说 60% → 实际 55% (轻微高估)
0.7     ●───────────────●  AI 说 70% → 实际 41% (⚠ 严重高估)
0.8                 ●─●  AI 说 80% → 实际 76% (✓)
0.9   ●         ●  AI 说 90% → 实际 60% (⚠ 严重高估)

Calibration multiplier 已自动应用到决策层
```

### 5.3 Dashboard 扩展

在现有"24h 胜率总览"下方加一个"**按 setup_type 胜率**"小表:

```
setup_type                    n   胜率   平均R   expect
rsi_overbought_macd_bearish  19   37%   +0.2   -0.15
funding_extreme_short        8    63%   +1.1   +0.49
rsi_oversold_macd_bullish    14   57%   +0.9   +0.21
```

让你一眼看出哪些 setup 在赚钱,哪些在亏钱。

---

## §6 关键风险与缓解

设计 reflection 系统最容易掉的几个坑,需要明确防御:

### 风险 1:AI 在 reflection 时事后合理化

AI 看到结果后说"我当时就该看出来",但其实是马后炮。

**缓解:**
- prompt 强制 AI 把 reasoning 锚定到 entry 时**已经存在的证据**(给 entry snapshot 里的 RSI/MACD/funding,不给 exit 后的数据)
- 跟踪 `self_assessed_prediction_accuracy` 跟实际的相关性。如果 AI 总是说"我之前的 prediction 50% 准",但 PnL 跟 prediction 几乎不相关,说明 AI 在合理化

### 风险 2:Reflection 回声室

AI reflection → 写入 RAG → 下次决策 AI 看到自己以前的 reflection → 强化既有偏见。

**缓解:**
- reflection 写入 ai_training_data 时,带 `reflection_origin=true` 标签
- 下次决策时,RAG 优先返回**结果数据**(WIN/LOSS, R 倍),次要返回 reflection text
- 每 30 天人工抽检 5 笔 reflection,看 AI 有没有发明虚假规律

### 风险 3:过拟合到老市场制度

90 天前的数据,跟今天市场可能完全不同(BTC 减半 / ETF 通过 / 一次大跌之后)。

**缓解:**
- Kelly 计算时,30d 权重 > 60d > 90d(指数衰减)
- 引入"制度检测":如果过去 7d 的 BTC 波动率 / funding 均值 / 持仓量与过去 90d 中位数偏离 > 2σ,触发警报:"市场制度可能已变,建议暂停 sizing 自动建议 7 天等数据"

### 风险 4:仓位 sizing 军备竞赛

Kelly 说"赢得越多越该加仓",连胜后仓位拉满,一次反转把所有积累吞掉。

**缓解:**
- 硬性边界 [0.5%, 2%] 不可逾越
- 滚动 7d 回撤 > 8% 自动锁定 sizing 不再上调
- A/B 框架:新 sizing 在前 30 笔强制减半应用,30 笔后再 review

### 风险 5:Reflection 算力成本

每笔关仓 1 次 AI 调用,假设 100 笔/月 × 0.05 USD/call = 5 USD/月。可接受。但如果策略月几千笔,成本飙到 100 USD/月。

**缓解:**
- 普通笔用 DeepSeek(低成本)
- 异常笔(实际 R < -2 或 > +3,或第一次进入未知 failure mode)用 Claude/GPT-4o(高质量)
- 配额上限:单日 reflection 调用 > 200 自动降级到 DeepSeek-only

### 风险 6:Failure taxonomy 杀过头

太激进过滤 = 机器人不开单。

**缓解:**
- 规则 active 前必须 ≥5 笔历史失败匹配
- 规则启用后,允许"试探"开仓(每月 5 笔,看规则是不是过度严格)
- 规则连续 14 天 0 触发 → 自动 retired,下次再被 AI 提案要重新走审批

### 风险 7:Reflection AI 跟交易 AI 同源 → 同盲区

如果 reflection AI 用同一个 DeepSeek 模型,它看不出来自己当时的 reasoning 错在哪。

**缓解:**
- reflection 用**跟交易决策不同的 LLM**(DeepSeek 交易 → Claude 复盘,或反过来)
- 长期目标:reflection AI 用 ensemble(多模型投票决定 failure_mode 标签)

---

## §7 上线路线(5 阶段)

每个阶段验证通过才进下一阶段。

### 阶段 1(1 周):数据基础 + Layer 1 实时复盘
- DB schema 落库
- v5_position_monitor 关仓后 enqueue 到 reflection_queue
- v5_reflection_worker 启动,Layer 1 reflection 跑起来
- 前端 Reflection 页 Tab 1(最近复盘流)上线
- 预置 8 个 failure_taxonomy 种子
- **目标:** 平仓后 1 分钟内看到 5 问答案,RAG 库新增 reflection_origin 标签

### 阶段 2(1 周):Layer 2 失败模式 + 入场端集成
- failure_taxonomy 表 + detection_rule DSL parser
- trading_assistant.decide() 入场前检查 failure mode 匹配,命中 → 输出 `block_reason=FAILURE_MODE_MATCH:<key>`
- 前端 Tab 2(失败模式分布)上线
- **目标:** 至少 1 笔被 failure_mode veto 掉,前端能看到原因

### 阶段 3(1 周):Layer 3 日聚合 + Layer 4 仓位 + 置信度校准
- setup_performance_daily 聚合 cron 上线
- 周日 fractional Kelly recommendation 生成
- ai_confidence_calibration 增量更新
- trading_assistant.decide() 应用 calibration_multiplier
- 前端 Tab 3(仓位建议审批队列)+ AI Status 页校准曲线上线
- **目标:** 第一周生成至少 1 个 sizing recommendation,人工批准后 A/B 启动

### 阶段 4(2 周):Layer 4 入场规则提案 + A/B 框架
- AI 提案新 entry filter 规则(每周日扫上周失败案例)
- detection_rule DSL 回算引擎
- 前端 Tab 4(规则审批队列 + 历史回算)上线
- 批准后规则进入 A/B(50 笔窗口对比)
- **目标:** 至少 1 条规则通过审批进入 A/B

### 阶段 5(持续):监控 + 风险熔断
- 把所有 §6 列的缓解机制全部上线
- 监控 dashboard:reflection 队列健康度 / AI 成本 / calibration 准确度 / failure mode active 数量 / sizing recommendation 接受率
- 自动告警:reflection queue 积压 > 50 / 单日 AI 成本 > 5 USD / calibration multiplier 突变 > 30%
- **目标:** 30 天内系统自治运行,每周你只看推送的建议表决

---

## §8 验收标准

跑满 90 天后,以下都达成 = 系统真正在帮你赚钱:

1. **复盘覆盖率** ≥ 95%:几乎每笔关仓都有 reflection
2. **失败模式标记率** ≥ 80%:reflection 中 80%+ 落到具体 taxonomy(不是 NEW)
3. **calibration 收敛**:任一模型 × confidence bucket 的样本 ≥ 30 时,calibration_multiplier 稳定在 ±10% 内
4. **sizing recommendation 接受率** ≥ 50%:你不是每个都否决(说明系统提的建议有意义)
5. **接受的 sizing recommendation 在 A/B 中胜率** ≥ 60%(60% 的提案确实让你赚得更多)
6. **入场规则提案命中率**:每月 ≥ 1 条规则进入 active,active 规则的"过滤掉的笔"中输>赢比例 ≥ 2:1
7. **总 PnL 改善**:Reflection Worker 上线前 30 天 vs 上线后 30 天(可比期),Sharpe 提升 ≥ 0.3 或回撤降低 ≥ 5pp

**任何一项不达标 = 系统设计需要迭代,不是用户用错。**

---

## §9 跟现有 V5 / 未来 V6 的关系

### 与 V5 的关系
- **完全向后兼容**:reflection 写入 ai_training_data 时保持原有 schema,RAG-lite 透明继续工作
- 只新增 `reflection_origin=true` 字段区分 reflection 来源 vs entry 来源
- v5_position_monitor 增加 1 行 enqueue 调用,其他不变
- trading_assistant 接入 calibration / failure_mode 检查需改,但都是非破坏性

### 与 V6 funding rate 的关系
**这套 reflection 系统是 V6 的前置必备组件。** 没有 reflection,V6 funding rate 上线后:
- 你无法分辨"funding 策略本身错"还是"参数选错"
- 无法在 funding 制度变化时及时降仓
- AI confidence 完全不可校准,sizing 是赌运气

**建议顺序:**
1. 先做本文(reflection worker)的 阶段 1-3 → 跑 4 周建立基线
2. V6 funding rate 上线作为新的 setup_type
3. Reflection 系统天然把 V6 当成 setup_type 之一来评估,无需特殊处理
4. 第 6-8 周看 V6 在 reflection 中的表现,决定要不要扩展

---

## §10 终态:这套机器到底变成什么

90 天后,你的机器应该是:

- 你给它**策略思路**(比如"funding rate 极端反转 + RSI 确认")
- 它**自己派生**该思路下的所有 setup_type(funding_extreme_short_rsi_70+, funding_extreme_short_rsi_60-70, ...)
- 它每天聚合**每个 setup_type 的胜率/R/Sharpe**
- 它每周**推荐仓位调整 + 入场过滤新规则**给你批准
- 它持续**校准 AI 的盲目自信**
- 它在你**没注意时阻止**已知失败模式的开单
- 它在策略**失效时主动告警**,不是无声继续亏

这才是"策略想法 → 持续赚钱的策略"的真正含义。**不是找到一个完美策略,是建一个把任何策略想法逼成持续赚钱的机器。**

---

**[End of design document]**
