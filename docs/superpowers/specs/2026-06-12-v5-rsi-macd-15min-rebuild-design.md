# V5 RSI-MACD 15min 重构 — 设计稿

- **状态**:已对齐(待用户最终 review)
- **作者**:lizhishaoniange + Claude
- **日期**:2026-06-12
- **目标**:用经典指标 + 时间盒 scalping 替换现有 V4.3 P 阶段策略,SHADOW 跑出可验证的 paper KPI

---

## §1 总览 + 拆除清单

### 1.1 策略简介

> **V5 RSI-MACD 15min Scalper**
> 在 15min K 线上扫"已经动起来"的热门币(|ΔP| > 3%),用 **RSI 极值 + MACD 同向拐点 AND 合谋**作为入场触发,4h K 线状态作为参考给 AI 二次审查,持仓 15min 为软目标 — 真正止盈止损由 AI 学习决定。同时最多 3 个活仓,单笔 1.5% 风险 × 10x 杠杆,无同币冷却。

### 1.2 已对齐的决策清单

| # | 维度 | 决策 |
|---|----|----|
| 1 | 与 P1-P4 关系 | **完全替换**(C 方案,物理删旧代码) |
| 2 | RSI × MACD 触发 | **AND 合谋**:RSI 超买/超卖 ∩ MACD 同向拐点 |
| 3 | 4h K 线作用 | **不强制拦截**,作为 AI 决策的参考信息 |
| 4 | 15min 持仓 | **软目标**,真实 SL/TP 让 AI 学习决定 |
| 5 | 选币门槛 | 现 Scanner 当热门池 + DeepCollector 加 15min |ΔP| > 3% 过滤 |
| 6 | 同币冷却 | **无**,信号到就开 |
| 7 | 同时持仓数 | 最多 **3** 个 |
| 8 | 单笔风险 | 1.5%(保持现状) |
| 9 | 杠杆 | 10x(保持现状) |
| 10 | 前端 | **完全重写**,API 重命名 `/api/v5/*` |

### 1.3 物理删除清单(后端)

| 文件 | 删除原因 |
|----|----|
| `scripts/v41_structure_analyzer.py` | P 阶段识别 |
| `scripts/v41_context_gate.py` | 同上 |
| `scripts/v43_score_calculator.py` | 四维评分 |
| `scripts/v43_decision_policy.py` | should_trade 决策 |
| `scripts/v43_hard_filters.py` | PHASE_NOT_ALLOWED 等 |
| `scripts/v43_feature_extractor.py` | range_left/atr_expand 等结构特征 |
| `scripts/v43_chandelier_stop.py` | Chandelier 止损,V5 用 ATR×倍数 |
| `scripts/v43_collector_integration.py` | V4.3 集成层 |
| `scripts/v43_entry_validator.py` | V4.3 校验 |
| `scripts/v43_kill_queue_manager.py` | 改名为 `v5_signal_manager.py` |
| `scripts/v43_weight_manager.py` / `run_ai_weight_adjustment.py` | 四维权重 |
| `scripts/v43_opportunity_density.py` | V5 不用 |
| `scripts/v43_position_manager.py` | 改名为 `v5_position_manager.py` |
| `scripts/v44_strategy_router.py` / `v44_strategy_backtest.py` / `v44_strategy_validation_analysis.py` | SNIPER/VULTURE |
| `scripts/whale_detector.py` | detect_phase |
| `scripts/deepseek_ai.py` / `scripts/ai_judge.py` | deprecated,顺手清 |

### 1.4 保留并改造(后端)

- `scripts/tasks/scanner.py`(几乎不动)
- `scripts/tasks/deep_collector.py`(加 15min K 线 + ΔP 过滤)
- `scripts/tasks/scorer.py`(瘦身,只剩管道粘合)
- `scripts/tasks/writer.py`(几乎不动)
- `scripts/ai/`(保留,prompt 改写)
- `scripts/paper_position_manager.py`(加 15min 软目标 + AI 续仓钩子)
- `scripts/local_db.py`(schema 调整)
- `scripts/binance_trader.py` / `okx_trader.py` / `exchange_factory.py`(下单底座不动)

### 1.5 数据库表变更

- **删除**:`trade_scores_v43` / `positions_v43` / `ai_weights_v43` / `ai_training_data`(旧 schema)/ `market_snapshot`
- **新建**:`trade_scores_v5` / `positions_v5` / `ai_training_data`(新 schema)
- **改造**:`paper_trades`(加 V5 字段)
- **清理**:`system_settings` 里 V4.3/V4.4 相关 key

### 1.6 风险声明

- 一次性大改 ~15 个后端文件 + 9+ 前端组件 + 4 张 DB 表 — **不可逆**
- 现有 5000+ 评分快照 + ai_trade_log.jsonl 会留 backup(`data/rabbit_hunter.db.backup-pre-v5.<timestamp>`)
- 上线后才发现 V5 不如 V4.3 想回退 = `git revert` + 重建 DB 表(详见 §6)

---

## §2 新架构组件

### 2.1 管道总图

```
                     [OKX 24h tickers]
                            │
                            ▼
              ┌─────────────────────────┐
              │  MarketScanner          │ 几乎不动
              │  (tasks/scanner.py)     │ 24h ΔP×成交额排序
              └───────────┬─────────────┘
                          │ movers_queue (Top 20)
                          ▼
              ┌─────────────────────────┐
              │  DeepCollector v5       │ ✱ 改造
              │  - 拉 15min × 50 根     │
              │  - 拉 4h    × 30 根     │
              │  - 计算最新 15min ΔP    │
              │  - 过滤 |ΔP| ≤ 3% 丢弃  │
              └───────────┬─────────────┘
                          │ enriched_queue
                          ▼
              ┌─────────────────────────┐  ┌──────────────┐
              │  IndicatorEngine        │  │ v5_strategy   │
              │  (v5_indicator_engine)  │──│ AND 合谋决策器 │
              │  - RSI(14) on 15min     │  │   → Decision  │
              │  - MACD(12,26,9)        │  └──────┬───────┘
              │  - 4h RSI/MACD (参考)   │         │
              └─────────────────────────┘         ▼
                                       ┌──────────────────┐
                                       │ RiskCalculator    │
                                       │ - SL/TP 价格      │
                                       │ - position size   │
                                       └──────┬───────────┘
                                              ▼
                                       ┌──────────────────┐
                                       │ TradingAssistant  │
                                       │ AI 二次审查 + 调参│
                                       └──────┬───────────┘
                                              │ 通过/拒绝/调整
                                              ▼
                                  ┌─────────┴────────┐
                                  ▼ SHADOW           ▼ LIVE
                       PaperPositionManager   v5_position_manager
                       + 15min 软目标钩子      → Binance/OKX 下单
                                  │                  │
                                  ▼                  ▼
                            paper_trades      positions_v5

              ┌─────────────────────────┐
              │  PositionMonitor        │ 每 30s 轮询
              │  - 持仓 ≥ 15min ?        │
              │  - RSI/MACD 反转 ?       │
              │  - 命中 SL/TP ?          │
              │  → 让 AI 决定要不要平    │
              └─────────────────────────┘
```

### 2.2 组件清单 + 接口

| 组件 | 文件 | 职责 | 输入 / 输出 |
|---|---|---|---|
| Scanner | `tasks/scanner.py` | 热门池筛选 | tickers → `[(symbol, score, reason)]` Top 20 |
| DeepCollector v5 | `tasks/deep_collector.py` | 拉 15min/4h K 线 + 15min ΔP 预过滤 | symbol → `EnrichedItem{symbol, klines_15m, klines_4h, current_price, delta_15m_pct}` |
| **IndicatorEngine**(新) | `v5_indicator_engine.py` | 纯函数:K 线 → 指标值 | klines → `Indicators` |
| **V5Strategy**(新) | `v5_strategy.py` | AND 合谋决策器 | `(Enriched, Indicators)` → `Decision` |
| **RiskCalculator**(新) | `v5_risk_calculator.py` | 算 SL/TP/size | `(side, entry, atr_15m, balance, risk_pct=1.5%)` → `RiskPlan` |
| TradingAssistant | `ai/trading_assistant.py` | AI 二次审查 + 调参 | `(Decision, RiskPlan, klines, 4h_ctx)` → `AIResult` |
| Scorer(瘦身) | `tasks/scorer.py` | 管道粘合 | enriched → write_queue + 触发开仓 |
| PaperPositionManager | `paper_position_manager.py` | SHADOW 下单 + 标记 `target_close_at` | `OpenIntent` → `paper_trades` |
| V5PositionManager | `v5_position_manager.py` | LIVE 走 Binance/OKX | `OpenIntent` → broker order |
| **PositionMonitor v5**(新) | `v5_position_monitor.py` | 每 30s 检查活仓 | 活仓 → `CloseIntent` |
| Writer | `tasks/writer.py` | 异步写 DB + WS 广播 | write_queue → `trade_scores_v5` + WS |

### 2.3 数据契约(`scripts/v5_types.py`)

```python
@dataclass
class Indicators:
    rsi_15m: float
    macd_15m: float
    macd_signal_15m: float
    macd_hist_15m: float
    macd_hist_prev_15m: float   # 拐点检测
    rsi_4h: float
    macd_hist_4h: float
    atr_15m: float

@dataclass
class Decision:
    should_trade: bool
    side: Literal["LONG", "SHORT", None]
    reasoning: str
    block_reason: Optional[str]  # NOT_RSI_AND_MACD / MAX_CONCURRENT / ...

@dataclass
class RiskPlan:
    entry_price: float
    sl_price: float
    tp_price: float
    size_usdt: float
    leverage: int
    expected_rr: float

@dataclass
class AIResult:
    execute: bool
    sl_multiplier: float
    tp_multiplier: float
    size_multiplier: float
    confidence: float
    reasoning: str
```

### 2.4 隔离与可测性

每个新模块都是 **pure(无 side effect)**,除了 PositionManager 和 Writer。这意味着 IndicatorEngine / V5Strategy / RiskCalculator 都能直接单元测试不需要任何 mock。

---

## §3 数据流(端到端时序)

### 3.1 开仓流程

```
T+0s    Scanner 每 1s 扫 OKX 24h tickers
        └─ 选 Top 20 → movers_queue

T+0~60s DeepCollector 消费 movers_queue,每个币:
        ├─ 拉 15min × 50 根 K 线
        ├─ 拉 4h    × 30 根 K 线
        ├─ 算 last 15min ΔP = (close[-1] - open[-1]) / open[-1]
        ├─ 过滤:|ΔP| ≤ 3% → drop
        └─ 否则推入 enriched_queue

        Scorer 消费 enriched_queue,每个 EnrichedItem:

T+~1s   ① IndicatorEngine.calculate(klines_15m, klines_4h) → Indicators
        ② V5Strategy.decide(enriched, indicators)
            ├─ RSI > 70 ∧ MACD hist 由正变负 → side=SHORT
            ├─ RSI < 30 ∧ MACD hist 由负变正 → side=LONG
            ├─ 否则 should_trade=False, block_reason="NOT_RSI_AND_MACD"
        ③ should_trade=False → 仍然写 trade_scores_v5,return
        ④ should_trade=True → 查"活仓数 < 3"
            ├─ ≥ 3 → block_reason="MAX_CONCURRENT_POSITIONS",写表 return
            └─ < 3 → 继续
        ⑤ RiskCalculator.plan(...) → RiskPlan
        ⑥ TradingAssistant.decide(...) → AIResult
            ├─ AI 调 sl_multiplier / tp_multiplier / size_multiplier
            └─ AI 看 4h 上下文 → 拒绝 / 批准 / 调参
        ⑦ ai.execute=False → 写表 block_reason="AI_REJECTED",return
        ⑧ 应用 AI 调整后的最终 RiskPlan
        ⑨ mode 分支:
            ├─ SHADOW → PaperPositionManager.open_position(plan)
            │           写 paper_trades,target_close_at = now + 15min
            └─ LIVE   → V5PositionManager.open_position(plan)
                       下 broker 单(market + SL + TP),写 positions_v5
        ⑩ 写 trade_scores_v5(决策快照)
        ⑪ Writer 触发 WebSocket broadcast 给前端
```

### 3.2 关键过滤数

```
24h ticker            ~150 个币(OKX U 本位永续)
  ↓ 30M USDT 门槛       ~40 个
  ↓ Top 20 by score      20 个 → movers_queue
  ↓ |15min ΔP| > 3%      预计 0~5 个
  ↓ AND 合谋               预计 0~2 个
  ↓ AI 二次审查            预计 0~1 个 / 分钟
  ↓ 活仓数 < 3
  → 写 paper_trades        预计 5~20 笔 / 小时(SHADOW)
```

### 3.3 平仓流程(PositionMonitor 30s 轮询)

```
每 30 秒 PositionMonitor 跑一轮:
  loop over status=OPEN 的活仓:
    ① 拉当前 mark price + 最新 15min K 线
    ② 算当前 indicators(RSI_15m + MACD_hist_15m)
    ③ 检查触发条件(优先级从上到下):

       (a) 命中硬 SL/TP        → 立刻平,exit_reason=SL_HIT/TP_HIT
       (b) 持仓 ≥ 15min(软目标)→ 调 AI ask
           ├─ AI 说"留" → extension_count+=1(最多 3)→ target_close_at += 15min
           ├─ AI 说"平" → exit_reason=AI_TIMEBOX
           ├─ AI 超时(> 20s)→ 默认平,exit_reason=AI_EXTEND_TIMEOUT
           └─ extension_count 已达上限 → 强制平,exit_reason=AI_EXTEND_MAX
       (c) 指标反转(分方向判断):
           - LONG 仓:RSI 涨过 35(脱离超卖)或 MACD 由金叉重新死叉 → 平
           - SHORT 仓:RSI 跌破 65(脱离超买)或 MACD 由死叉重新金叉 → 平
           - exit_reason=SIGNAL_REVERSE

    ④ 没有任何触发 → continue

  写 DB + WebSocket 广播平仓事件
```

### 3.4 队列设计

| 队列 | maxsize | 满了怎么办 |
|---|---|---|
| `movers_queue` | 1 | drop 旧(最新快照覆盖) |
| `enriched_queue` | 100 | DeepCollector 等(背压) |
| `write_queue` | 500 | 阻塞 Scorer(不丢数据) |

### 3.5 状态机(单笔仓位)

```
                       open_position()
   (none)  ───────────────────────────────►  OPEN
                                              │
              ┌───────────────────────────────┼──────────────────┐
              │ SL/TP 命中                    │ 15min 软目标到    │ 指标反转
              ▼                               ▼                  ▼
           CLOSED                       AI re-evaluate        CLOSED
           (exit_reason=                      │                (exit_reason=
            SL_HIT/TP_HIT)             ┌──────┴──────┐         SIGNAL_REVERSE)
                                       ▼ 续          ▼ 平
                                  EXTENDED(回 OPEN)  CLOSED
                                  (最多续 3 次)       (exit_reason=AI_TIMEBOX)
```

---

## §4 数据库 Schema

### 4.1 删除的表

`trade_scores_v43` / `positions_v43` / `ai_weights_v43` / `ai_training_data`(旧)/ `market_snapshot`。
启动脚本 `local_db.py` 加一次性 `DROP TABLE IF EXISTS`。

### 4.2 新建/改造的表

#### `trade_scores_v5`(新)
```sql
CREATE TABLE trade_scores_v5 (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol          TEXT NOT NULL,
  created_at      TEXT NOT NULL,

  -- 选币层
  delta_15m_pct   REAL,
  volume_24h_usdt REAL,

  -- 指标
  rsi_15m         REAL,
  macd_15m        REAL,
  macd_signal_15m REAL,
  macd_hist_15m   REAL,
  macd_hist_prev_15m REAL,
  rsi_4h          REAL,
  macd_hist_4h    REAL,
  atr_15m         REAL,
  current_price   REAL,

  -- 决策
  should_trade    INTEGER DEFAULT 0,
  side            TEXT,
  reasoning       TEXT,
  block_reason    TEXT,

  -- AI 层
  ai_confidence   REAL,
  ai_sl_multiplier REAL,
  ai_tp_multiplier REAL,
  ai_size_multiplier REAL,
  ai_reasoning    TEXT,
  ai_decision_id  INTEGER,

  -- 风险
  entry_price     REAL,
  sl_price        REAL,
  tp_price        REAL,
  size_usdt       REAL,
  expected_rr     REAL,

  executed        INTEGER DEFAULT 0,
  position_id     INTEGER
);
CREATE INDEX idx_trade_scores_v5_symbol_created ON trade_scores_v5(symbol, created_at);
CREATE INDEX idx_trade_scores_v5_executed ON trade_scores_v5(executed, created_at);
CREATE INDEX idx_trade_scores_v5_should_trade ON trade_scores_v5(should_trade, created_at);
```

#### `positions_v5`(新)
```sql
CREATE TABLE positions_v5 (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol          TEXT NOT NULL,
  side            TEXT NOT NULL,
  status          TEXT NOT NULL,
  entry_price     REAL,
  entry_time      TEXT,

  sl_price        REAL,
  tp_price        REAL,
  size_usdt       REAL,
  leverage        INTEGER,
  position_size_coins REAL,

  -- 15min 软目标
  target_close_at TEXT,
  extension_count INTEGER DEFAULT 0,

  -- 入场快照
  entry_rsi_15m   REAL,
  entry_macd_hist_15m REAL,
  entry_rsi_4h    REAL,
  entry_atr_15m   REAL,

  -- 平仓
  exit_price      REAL,
  exit_time       TEXT,
  exit_reason     TEXT,
  pnl_usdt        REAL,
  pnl_pct         REAL,
  holding_minutes REAL,

  source_score_id INTEGER,
  ai_decision_id  INTEGER,

  created_at      TEXT,
  updated_at      TEXT
);
CREATE INDEX idx_positions_v5_status_symbol ON positions_v5(status, symbol);
CREATE INDEX idx_positions_v5_status_entry ON positions_v5(status, entry_time);
CREATE INDEX idx_positions_v5_exit_time ON positions_v5(exit_time);
```

#### `paper_trades`(改造,加字段)
现有列保留,新增:`target_close_at` / `extension_count` / `entry_rsi_15m` / `entry_macd_hist_15m` / `entry_rsi_4h` / `entry_atr_15m` / `ai_decision_id` / `source_score_id`。

#### `ai_training_data`(重 schema)
```sql
CREATE TABLE ai_training_data (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at      TEXT,
  symbol          TEXT,
  side            TEXT,
  entry_price     REAL,

  entry_rsi_15m   REAL,
  entry_macd_hist_15m REAL,
  entry_rsi_4h    REAL,
  delta_15m_pct   REAL,
  ai_reasoning    TEXT,

  exit_price      REAL,
  exit_reason     TEXT,
  holding_minutes REAL,
  pnl_pct         REAL,
  outcome         TEXT,

  uploaded_to_vector_store INTEGER DEFAULT 0,
  uploaded_at     TEXT
);
```

### 4.3 数据库迁移策略

启动脚本 `local_db.py`:
1. **第一次升 v5**:检测旧表存在 → `cp data/rabbit_hunter.db data/rabbit_hunter.db.backup-pre-v5.<UTC-timestamp>` → 然后 `DROP TABLE` 旧表 + `CREATE TABLE` 新表
2. **正常运行**:发现新表已存在,跳过

备份文件留 30 天后用户手动清理。

### 4.4 保留期

| 表 | 保留期 | 自动清理 |
|----|----|----|
| `trade_scores_v5` | 30 天 | 是 |
| `positions_v5` | CLOSED 90 天 / OPEN 永久 | 是 |
| `paper_trades` | CLOSED 90 天 / OPEN 永久 | 是 |
| `ai_training_data` | 永久 | 否 |
| `system_settings` | 永久 | 否 |

---

## §5 错误处理 + 测试策略

### 5.1 错误处理矩阵

| 失败点 | 默认行为 | 旋钮(.env) |
|---|---|---|
| OKX API 拉 24h ticker 失败 | Scanner sleep 5s 重试 | — |
| OKX API 拉 15min/4h K 线失败 | DeepCollector 跳过该币 | — |
| K 线条数不够(< 26 根) | IndicatorEngine 抛 `InsufficientKlines`,Scorer skip | — |
| RSI/MACD 计算 NaN/异常 | log + skip | — |
| V5Strategy 异常 | 写 `block_reason="STRATEGY_ERROR:<exc>"` | — |
| AI 调用超时(20s) | **fail-closed**:跳过 | `AI_FAIL_OPEN` |
| 账户余额拉取失败 | cache → fallback `PAPER_INITIAL_BALANCE_USDT` | — |
| Broker 开仓失败 | 重试 3 次,仍失败 → 写 `executed=0, error=...` | — |
| Broker SL/TP 失败 | **fail-closed**:立刻市价平回滚 | `SL_TP_FAIL_OPEN` |
| PositionMonitor 拉 mark price 失败 | log + skip 这一笔仓位 | — |
| AI 续仓决策超时 | **平**(time-box 到点不让 AI 拖) | `AI_EXTEND_FAIL_OPEN` |
| 同币种短期重复信号(< 5s) | Scorer 签名去重 | — |
| DB 写入失败 | log + retry 1 次,失败 drop | — |
| WebSocket 广播失败 | log,不影响 DB 写入 | — |
| 进程崩溃 | docker restart + `load_open_positions()` 恢复 | — |

**统一原则:** 单笔异常 ≠ 系统停摆;广义"不确定"= 不下单(fail-closed)。

### 5.2 启动自检

```
1. 检查 OKX/Binance API key(若 ENABLE_AUTO_TRADING=true 必须有)
2. 检查 OpenAI key(若 OPENAI_AI_ENABLED=true 必须有)
3. 检查 DB schema 版本(写 system_settings.v5_schema_version=1)
4. 拉一次余额成功 + 拉一次 BTC ticker 成功 → 才进 while True
5. 任一项失败 → log + exit 1,docker 会重启
```

### 5.3 测试策略

#### 单元测试(pure 函数,覆盖率 ≥ 80%)

| 模块 | 测试要点 |
|---|---|
| `v5_indicator_engine.py` | 已知 K 线序列 → RSI/MACD 值是否吻合 |
| `v5_strategy.py` | RSI=72+MACD 死叉拐点 → SHORT;RSI=72+MACD 仍金叉 → 无信号 |
| `v5_risk_calculator.py` | balance/risk/atr/leverage → size_usdt 和 sl_distance 是否符合 |
| `tasks/deep_collector.py:filter_by_delta` | 边界 |ΔP|=2.5/3.0/3.1 → drop / 边界 / 保留 |
| `paper_position_manager.py:open_position` | RiskPlan → paper_trades + target_close_at 字段 |
| `v5_position_monitor.py:check_exit_triggers` | 命中 SL / TP / 15min / 反转 → 输出预期 |

#### 集成测试

| 名字 | 范围 |
|---|---|
| `test_scoring_pipeline.py` | Mock OKX → DeepCollector + Scorer + V5Strategy → 断言 `trade_scores_v5` |
| `test_shadow_open_close.py` | Mock 信号 → SHADOW 开仓 → 推进时间 16min → PositionMonitor → CLOSED |
| `test_sl_tp_fail_closed.py` | Mock SL 下单失败 → 主仓被市价平回滚 |

#### 端到端(real OKX,SHADOW)

- 启动后 30 分钟内 ≥ 1 笔 `trade_scores_v5`
- 启动后 24 小时内 ≥ 1 笔 `paper_trades` 写入
- 24 小时 paper KPI 指标可计算

#### 性能预算

| 环节 | 预算 |
|---|---|
| Scanner 单轮 | < 2s |
| DeepCollector 单币 | < 1s |
| IndicatorEngine | < 50ms |
| V5Strategy | < 10ms |
| AI 调用 | 5-15s(GPT-4o) |
| 整条 enriched_item 端到端(不含 AI) | < 2s |

### 5.4 运行时可观测性

日志固定格式:
```
[Scanner] 发现 20 个异动币(Top 5: ...)
[DeepCollector] BEAT/USDT 15min ΔP=3.42% → 入 enriched
[V5Strategy] H/USDT rsi=72.1 macd_hist=-0.0012(死叉拐点)→ SHORT
[AI] H/USDT 二次审查:execute=True sl=1.8x tp=2.5x conf=0.68
[PaperPM] OPEN H/USDT SHORT entry=0.166 size=15 USDT target_close=10:48
[PositionMonitor] H/USDT 持仓 14:23 PnL=+0.42% 暂不平
[PaperPM] CLOSE H/USDT exit_reason=TP_HIT exit_price=0.162 PnL=+2.40%
```

健康度告警(每分钟自检):
- 过去 5min 没有任何 `trade_scores_v5` 写入 → `[WARN] 评分流停滞`
- 过去 1h 0 笔入场但 |15min ΔP|>3% 的币 ≥ 10 个 → `[WARN] 信号全被 AI 拒`
- 余额拉取连续失败 5 次 → `[ERROR] 账户连接断,SHADOW 用 fallback`

---

## §6 部署 / 回滚 / 验收

### 6.1 部署步骤

```
1. 在新分支 v5-refactor 上做所有改动
2. 跑完单元 + 集成测试 → 绿
3. 本地 docker compose up -d --build 跑 SHADOW 模式 24h
4. 24h 验收(见 §6.4)通过 → merge 到 main
5. 用户在 main 上拉最新,docker compose up -d --build
6. 启动自检 → DB 自动备份 + DROP + CREATE 新表
7. 前端刷新看 V5SignalBoard
8. 监控 24h paper KPI
```

### 6.2 回滚预案

**软回滚(2 小时内):**
```bash
git revert <merge-commit-sha>
docker compose up -d --build
mv data/rabbit_hunter.db data/rabbit_hunter.db.v5-broken
cp data/rabbit_hunter.db.backup-pre-v5.* data/rabbit_hunter.db
docker compose restart collector api
```

**硬回滚(几天后):**
- 回滚前先 `python scripts/export_v5_paper_trades.py > export.json` 留底
- 或者干脆不回滚,在 V5 上修

### 6.3 API 路径 + 前端策略

**API 重命名 `/api/v5/*`**,前端**完全重写**。旧字段(`structure_score`/`phase`/`P3B_PUMP_LATE`)在 V5 没对应 — 一刀切干净。

### 6.4 验收清单(SHADOW 24h)

| 类别 | 要求 |
|---|---|
| 必须 | ≥ 50 笔 `trade_scores_v5` 写入 |
| 必须 | ≥ 1 笔 `paper_trades` 开仓 + 平仓 |
| 必须 | 无 collector / api 容器重启 |
| 必须 | 无 `[ERROR]` 级别日志 |
| 观察 | 24h paper KPI:胜率、累计 PnL、平均持仓 |
| 观察 | `block_reason` 分布(AI_REJECTED ≤ 90%) |
| 观察 | AI 平均决策延迟(< 15s) |

**切 LIVE 的额外硬性条件:**
- SHADOW 跑 ≥ 7 天
- ≥ 30 笔 CLOSED paper_trades
- 胜率 ≥ 50% **且** 累计 PnL ≥ 0

### 6.5 工作量估算

| 阶段 | 工时 |
|---|---|
| 后端 §1-§6 | 6 天 |
| 前端:信息架构 + 设计语言 | 1 天 |
| 前端:核心组件实现 | 3 天 |
| 前端:API hooks + WS 适配 | 1 天 |
| 端到端联调 + UI 抛光 | 1 天 |
| **合计** | **12 天**(纯净工时) |

并行度:前端可在后端跑 SHADOW 验收期间并行做,wall-clock 约 **9-10 天**。

### 6.6 风险登记表

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| RSI/MACD 低波动期不出信号 | 高 | SHADOW 跑 0 笔 | 阈值 70/30 调成 65/35 试 |
| AI 提示词拒绝率 100% | 中 | 卡在 AI 关 | 分迭代,先用 SHADOW 真实数据微调 |
| AI 续仓决策延迟过大 | 中 | 错过平仓点 | 续仓用 haiku?平仓规则兜底 |
| OKX 15min K 线限频 | 低 | DeepCollector 失败率上升 | cache 5s + 重试 + 流控 |
| DB 备份失败但旧表已删 | 低 | 历史数据丢 | `cp` 而非 `mv`,先确认备份再 DROP |
| Vector Store 旧记忆 schema 不一致 | 中 | AI RAG 检索不到 | 接受:V5 上线 = AI 重新积累 1-2 周 |
| 前端 + 后端同时大改联调失败 | 中 | 上不了 SHADOW | 后端 API 先稳,前端一页跑通后再批量 |

---

## §7 前端重设计

### 7.1 信息架构

| 当前页面 | V5 新页面 | 变化 |
|---|---|---|
| 信号面板(KillBoard) | **实时信号** | RSI/MACD 仪表,不再有 P 阶段、四维评分条 |
| 持仓 | **活仓监控** | 加 15min 倒计时、AI 续仓徽章、SL/TP 进度条 |
| 手动下单 | **手动下单** | 字段精简,只剩 symbol/side/size |
| AI 状态 | **AI 状态** | Vector Store + 最近 AI 决策日志 |
| 权重历史 | **删除** | V5 没"四维权重"概念 |
| 评分 | **信号历史** | 字段重做 |
| 策略 | **策略配置** | RSI 阈值、MACD 参数、|ΔP| 门槛、续仓上限 |
| 概览 | **Dashboard** | 信号→入场→平仓漏斗、胜率、累计 PnL |
| 设置 | **设置** | 交易所 + AI 配置,加 V5 旋钮 |

### 7.2 核心新组件

| 组件 | 职责 |
|---|---|
| `V5SignalBoard.tsx` | 替代 KillBoard,信号列表 + 展开看 RSI/MACD/4h |
| `IndicatorGauges.tsx` | RSI 表盘 + MACD 柱状图 |
| `ActivePositionCard.tsx` | 单个活仓卡:15min 倒计时环、SL/TP 进度条、AI 续仓徽章 |
| `SignalFunnel.tsx` | Dashboard 漏斗图 |
| `KpiCard.tsx` | 通用 KPI 卡 |
| `RsiMacdConfig.tsx` | 策略页:阈值滑杆 + 实时预览过去 100 笔信号命中分布 |
| `RecentAIDecisions.tsx` | 最近 20 笔 AI 决策表格 |

### 7.3 视觉草图

#### 整体布局母版

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Rabbit Hunter  v5.0           [OKX] [SHADOW]                  实时 ●  ⓘ 帮助│
├──────┬───────────────────────────────────────────────────────────────────────┤
│ 实时  │                                                                       │
│ 信号  │                                                                       │
│ 活仓  │                                                                       │
│ ─监控 │                       <主内容区域>                                     │
│ 信号  │                                                                       │
│ 历史  │                                                                       │
│ ─────│                                                                       │
│ AI   │                                                                       │
│ 状态  │                                                                       │
│ 策略  │                                                                       │
│ 配置  │                                                                       │
│ ─────│                                                                       │
│ Dash │                                                                       │
│ 设置  │                                                                       │
└──────┴───────────────────────────────────────────────────────────────────────┘
```

#### Page 1 · 实时信号

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 实时信号                              过去 1h: 47 个扫到 → 8 通过 AND → 2 入场│
│ 筛选: [全部 ▾]   方向: [全部 ▾]   仅显示已入场 [○]              [手动刷新⟳]│
├─────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │ H/USDT          ΔP15m: +3.42%        09:48:21  ●●●  [▾]                 ││
│ │ ┌──RSI 15min──┐  ┌──MACD 15min──┐    🎯 SHORT  📊 score 78              ││
│ │ │     72.1    │  │  hist:-0.0012 │   AI 已批准 ✓                        ││
│ │ │ ██████████░ │  │  prev:+0.0008 │   sl 2.0x  tp 2.8x                   ││
│ │ │  超买 ⚠️    │  │  死叉拐点 ✓   │   size 14.8 USDT                     ││
│ │ └─────────────┘  └───────────────┘                                       ││
│ │ 4h 参考: rsi=68 macd_hist=+0.003(上扬)  → AI: "短线反弹中带空有利"      ││
│ └─────────────────────────────────────────────────────────────────────────┘│
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │ BEAT/USDT       ΔP15m: -3.18%        09:47:55  ●●○  [▾]                 ││
│ │ rsi=29 macd金叉拐点 → LONG   AI ✗ 拒  "4h趋势仍向下,逆势风险高"          ││
│ └─────────────────────────────────────────────────────────────────────────┘│
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │ MOVE/USDT       ΔP15m: +3.02%        09:47:30  ●○○  [▾]                 ││
│ │ rsi=64 macd 死叉拐点  → 拦截: NOT_RSI_AND_MACD (rsi未达 70)              ││
│ └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

**设计意图:**
- 头部漏斗一行讲清"系统在工作但筛得严"
- 每张卡左有 ●●●/●●○/●○○ 视觉灯:三层全过 / AI 拒 / 规则拦截
- 折叠卡展开后,RSI 仪表 + MACD 柱作为视觉核心
- 默认显示全部信号(用灰色 dot 区分状态)

#### Page 2 · 活仓监控

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 活仓监控          2 / 3                                  下一次轮询 18s 后 ⟳ │
├─────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │  H/USDT  SHORT  -10x          软目标剩 04:23      [立即平]              ││
│ │      入场             当前             SL         TP                    ││
│ │     $0.1665         $0.1641         $0.1715    $0.1592                  ││
│ │  ●═══════════●═══════════════════════>○         ○                       ││
│ │   PnL: +0.42% (+0.62 USDT)  当前 RSI: 67 ✓还在超买区                    ││
│ │   持仓 10:37  续仓 0/3                                                  ││
│ │  最近 AI 决策: "信号方向继续,maintain"  09:38:11                         ││
│ └─────────────────────────────────────────────────────────────────────────┘│
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │  ZEC/USDT  LONG  -10x         软目标剩 12:08      [立即平]              ││
│ │  入场 $48.20  当前 $48.35  SL $47.60  TP $49.45                          ││
│ │  PnL: +0.31%   RSI: 33(已脱离超卖,⚠ 信号弱化中)  续仓 0/3              ││
│ └─────────────────────────────────────────────────────────────────────────┘│
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │  [+] 空闲槽位 (最多 3)                                                  ││
│ └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

**设计意图:**
- 顶部 `2 / 3` 一眼看出还能开几仓
- 核心三件事:**软目标倒计时**、**进度条**、**AI 续仓状态**
- 进度条按距离按比例:SL/TP 按 ATR 倍数远近反映在条上
- 信号弱化时(RSI 跌出区间)`⚠ 信号弱化中`

#### Page 3 · Dashboard

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Dashboard          24h 总览                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                            │
│ │  胜率   │ │累计 PnL │ │ 平均持仓│ │  活仓数 │                            │
│ │  63%    │ │ +18.40  │ │  17 min │ │   2/3   │                            │
│ │ ▴ +5pt  │ │  USDT   │ │ ─ 持平  │ │ 全部 ●● │                            │
│ │ vs 昨天 │ │ +1.84%  │ │         │ │         │                            │
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘                            │
│                                                                              │
│ ─── 24h 信号漏斗 ───                                                         │
│ Scanner 扫到      ████████████████████████████████████████████  872          │
│ 15min ΔP>3%        █████████████████░░░░░░░░░░░░░░░░░░░░░░░░  213           │
│ RSI×MACD AND        ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   34           │
│ AI 批准              █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   12           │
│ 实际开仓             █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   11           │
│                                                                              │
│ ─── 拦截分布 ───                              ─── 最近 24h PnL 曲线 ───       │
│ NOT_RSI_AND_MACD       42%                  PnL                              │
│ MAX_CONCURRENT          8%               20 │                       ╱─       │
│ AI_REJECTED            38%               10 │              ╱──╲   ╱          │
│ AI_TIMEBOX_EXTEND       7%                0 │─────╲╱╲╱──╱     ╲─╱            │
│ (其他)                  5%             -10 │   ╲╱                            │
│                                            └─────────────────────────────    │
│                                              0h  4h  8h  12h  16h  20h  24h  │
│                                                                              │
│ ─── 平仓原因分布 ───                                                          │
│ TP_HIT     ███████████  42%    SL_HIT      █████  18%                       │
│ AI_TIMEBOX █████████    34%    SIGNAL_REV  ██     6%                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

**设计意图:**
- 4 张 KPI 大卡 + 跟前一天对比的小箭头
- **信号漏斗**:看出系统在哪一层"卡得最紧"
- PnL 曲线以 USDT 为基准(更直观)

#### Page 4 · 策略配置

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 策略配置                                              [恢复默认] [保存修改] │
├─────────────────────────────────────────────────────────────────────────────┤
│ ── 选币层 ──                                                                 │
│ 最低 24h 成交额(USDT)         [30,000,000]   过滤微价 meme                   │
│ 最低 15min |ΔP|                [3.0 %]        ▭▭▭▭●▭▭▭▭▭ (1% — 5%)         │
│                                                                              │
│ ── RSI 触发器 ──                                                             │
│ RSI 周期                       [14]                                          │
│ 超买阈值(开空)                [70.0]      ▭▭▭▭▭▭▭●▭▭ (60 — 80)           │
│ 超卖阈值(开多)                [30.0]      ▭●▭▭▭▭▭▭▭▭ (20 — 40)           │
│                                                                              │
│ ── MACD 触发器 ──                                                            │
│ MACD 快/慢/信号                 [12]  [26]  [9]                              │
│ 拐点确认: histogram 变号        [○]  必须  [●]  允许刚要变号(下一柱预测)   │
│                                                                              │
│ ── 风险参数 ──                                                               │
│ 单笔风险预算                    [1.5 %]      ▭▭▭●▭▭▭▭▭▭ (0.5% — 3%)        │
│ 杠杆                            [10 x]                                        │
│ 同时活仓上限                    [3]          ▭▭●▭▭ (1 — 5)                   │
│                                                                              │
│ ── 软目标 ──                                                                 │
│ 持仓软目标(分钟)              [15]                                          │
│ AI 续仓上限                     [3]   续到最长 15+15×3 = 60 分钟              │
│                                                                              │
│ ── 模拟预览 ── (基于过去 7 天数据)                                            │
│ 当前阈值预计每小时入场: 0.8 笔   ╱── 调整到 65/35 试试 ──╲                   │
│ 预计胜率: 58%                    [   预览新阈值的回测结果   ]                │
└─────────────────────────────────────────────────────────────────────────────┘
```

**设计意图:**
- 每个参数有当前值 + 滑杆 + 范围;不再隐式 .env
- 底部**模拟预览**:基于历史 `trade_scores_v5` 实时算"如果改成 65/35,过去 7 天的入场频率和胜率"
- 这是最大的运营价值

#### Page 5 · AI 状态

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ AI 状态                                                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │   Assistant      │  │  Vector Store    │  │   决策延迟       │          │
│  │   asst_xxx       │  │   142 条记忆     │  │   平均 7.8s      │          │
│  │   ● 在线          │  │  最新上传 02:14  │  │   P95: 14.2s     │          │
│  │   GPT-4o         │  │  [上传最新批次]   │  │                  │          │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
│                                                                              │
│ ── 最近 20 笔 AI 决策 ──                                                     │
│ ┌──────┬─────────────┬──────┬──────────────────────────────────────────────┐│
│ │09:48 │ H/USDT      │ ✓ 批准│ 4h趋势中性 + 15min 超买 + 死叉,sl=2.0 tp=2.8 ││
│ │09:47 │ BEAT/USDT   │ ✗ 拒 │ 4h MACD 仍下行,逆势开多风险高               ││
│ │09:46 │ MOVE/USDT   │ ✗ 拒 │ 历史相似案例 LOSS 比例 67%,建议跳过          ││
│ │09:45 │ ZEC/USDT    │ ✓ 批准│ ATR 健康,信号清晰,sl=1.8 tp=2.5             ││
│ └──────┴─────────────┴──────┴──────────────────────────────────────────────┘│
│                                                                              │
│ ── 续仓决策(过去 24h) ──                                                    │
│ 总续仓请求 18    续(让 AI 决定继续) 11    平(15min 到点平) 7                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.4 设计语言

- **配色基调**:深蓝 `#1a1f2e` + 高对比白 `#ffffff` + LONG `#10b981` + SHORT `#ef4444` + 警示 `#f59e0b`
- **字体**:数字用 JetBrains Mono / IBM Plex Mono,正文 PingFang / Noto Sans CJK
- **图表库**:沿用 Lightweight Charts(K 线已经在用);新增 Recharts 画 RSI/MACD 仪表

### 7.5 路由

`App.tsx` 全部路由换成 `/v5/*` 前缀,旧路由做 301 重定向。

### 7.6 状态管理

- React Query 不变
- Zustand UI store 重写(旧 store 有 V4 残留)
- WebSocket 路径 `/ws/v5`(内部 payload schema 改成 V5)

### 7.7 删除的前端文件

```
Rabbit Hunterfronted/components/
  KillBoard.tsx                  → 替换为 V5SignalBoard
  TradeScores.tsx                → 替换为 SignalHistory
  PositionsPage.tsx              → 替换为 V5PositionsPage
  Dashboard.tsx                  → 重写
  AIStatus.tsx                   → 重写
  StrategyConfig.tsx             → 替换为 RsiMacdConfig
  WeightHistory.tsx              → 删
  AnatomyPanel.tsx               → 删(P 阶段相关)
  TradingViewChart.tsx           → 留(改字段映射)
```

---

## 终态:进入实现阶段

设计稿全部确认后,下一步:

1. 调用 `superpowers:writing-plans` skill 把这份 design 拆成可执行的实现计划
2. plan 拆分按 §6.5 的 12 天工作量分阶段
3. 每个阶段独立可验证(单元 + 集成测试通过 + 本地 SHADOW 跑通)

---

**[End of design document]**
