# Rabbit-Hunter — 项目结构 & 设计优化接缝

> 快照: 2026-06-27
> 受众: 准备做 UX / 视觉 / 架构 / 风控优化的人
> 目标: 5 分钟看清"系统有哪些组件、数据怎么流、改哪里影响什么"

---

## 1. 一句话定位

**加密合约量化交易私人中控**: 4h MACD 反转 + 风控宪法 + AI 二次决策 + paper / live 双模式。技术栈 Python (FastAPI + asyncio) + React 19 + SQLite + Docker。

---

## 2. 数据流 (一图看懂)

```
                        ┌───────────────────────────┐
                        │  OKX Futures / Binance    │ (CCXT)
                        └─────────────┬─────────────┘
                                      │ 行情 + K 线 + funding
                                      ▼
   scripts/tasks/scanner.py  ────►  enriched_queue  ◄────  v5_funding_collector
                                      │
                                      ▼
                  scripts/tasks/scorer.py  (管道粘合层)
                     │
                     │  ──► v5_strategy.decide()     ★ 三 mode 路由 (design 接缝)
                     │  ──► v5_risk_calculator.plan() + derive_safe_leverage()
                     │  ──► AI gate (trading_assistant)  ★ DeepSeek / OpenAI
                     │  ──► 风控宪法 risk_gates       ★ 7 条铁律
                     │
              ┌──────┴──────┐
              ▼             ▼
         paper_pm         live_pm  (executes via OkxTrader / BinanceTrader)
              │             │
              ▼             ▼
        paper_trades    positions_v5
              │             │
              └──────┬──────┘
                     ▼
            v5_reflection_worker  →  reflections (用于 AI 学习闭环)
                     │
                     ▼
            ai/memory_uploader  →  OpenAI Vector Store

  并行旁支:
    M6 walk-forward: scripts/walkforward.py + scripts/experiments/macd_cross_entry_wf.py
    M9 知识层:       scripts/m9_*.py + api/routes/v5_m9.py + 前端 /knowledge

  API/WebSocket (FastAPI):
    api/main.py 注册 18 个 route + ws_v5
    前端通过 nginx 反代 /api 到容器内的 api:8000
```

---

## 3. 顶层目录

| 目录 | 职责 |
|---|---|
| `api/` | FastAPI 后端 — routes + schemas + services + WebSocket |
| `scripts/` | Python 核心 — collector / scorer / AI / 风控 / 回测 / 实验 |
| `Rabbit Hunterfronted/` | React 前端 (目录名含空格,docker-compose 用引号) |
| `tests/` | pytest 套件 (53 个文件) |
| `docs/` | 项目文档 — 本文件 + 风控审计 + 设计 brief 等 |
| `data/` | SQLite 主库 + JSONL 日志 + backtest 缓存 (gitignored) |
| `reports/` | walk-forward / 实验 JSON 报告 (commit 留底审计) |

---

## 4. 后端 (Python)

### 4.1 `api/` — FastAPI 服务

**入口**: `api/main.py` (容器内 `0.0.0.0:8000`, host `127.0.0.1:8000`)

```
api/
├── main.py             ★ 注册所有路由 + auth middleware + CORS
├── dependencies.py     auth (require_auth) + DB 注入
├── websocket_v5.py     /ws/v5 — 实时事件推送给前端
├── websocket_server.py legacy V4 ws (跑着但不主推)
├── routes/             ★ 18 个 HTTP endpoint 文件 (见下表)
├── schemas/            Pydantic 模型 — 前后端契约
└── services/           business logic 抽象 — position / score / market
```

#### routes/ 18 个 endpoint

| 文件 | 路径前缀 | 主要功能 | 状态 |
|---|---|---|---|
| `system.py` | `/api/system/*` | mode 切换 / healthz | ✅ |
| `positions.py` | `/api/v5/positions*` | 持仓查询 | ✅ |
| `scores.py` | `/api/v5/signals*` | 信号评分流 | ✅ |
| `weights.py` | `/api/v5/weights*` | 权重管理 | ✅ |
| `market.py` | `/api/v5/market*` | 市场数据 | ✅ |
| `v5_account.py` | `/api/v5/account/*` | OKX 账户余额 + Paper 累计 | ✅ |
| `v5_ai.py` | `/api/v5/ai/*` | AI 决策日志 | ✅ |
| `v5_charts.py` | `/api/v5/charts/*` | K 线数据 | ✅ |
| `v5_constitution.py` | `/api/v5/constitution/*` | 风控宪法读取 | ✅ |
| `v5_funding.py` | `/api/v5/funding/*` | 资金费率视图 | ✅ |
| `v5_m9.py` | `/api/v5/m9/*` | M9 知识库 + 候选规则验证 | ✅ |
| `v5_manual_order.py` | `/api/v5/manual-order` | 手动下单 (paper) | ✅ |
| `v5_position_close.py` | `/api/v5/position/close` | 主动平仓 | ✅ |
| `v5_reflection.py` | `/api/v5/reflection*` | 反思结果 | ✅ |
| `v5_settings.py` | `/api/v5/settings*` | 用户设置持久化 | ✅ |
| `v5_strategy_config.py` | `/api/v5/strategy-config*` | 策略参数 | ✅ |
| `v5_trader_kpi.py` | `/api/v5/dashboard/trader-kpi` | **新加** — KPI 中控 (PF/Sharpe/MaxDD/宪法/AI 健康) | ✅ |
| `v5_walkforward.py` | `/api/v5/walkforward*` | M6 回测报告 | ✅ |

**🎯 设计接缝**: 新加 endpoint 模式参考 `v5_trader_kpi.py` — 单文件 router + Pydantic 模型 + 计算函数,在 `main.py` import + include_router。

### 4.2 `scripts/` — 核心逻辑

```
scripts/
├── tasks/              ★ 异步 worker (collector_main 入口启动 6 个 task)
│   ├── collector_main.py        v45 唯一入口
│   ├── scanner.py               MarketScanner (异动 + volume 过滤)
│   ├── deep_collector.py        OI / funding / CVD / K 线深度
│   ├── scorer.py                ★★ 评分管道粘合层 (动钱核心)
│   ├── writer.py                async SQLite writer
│   ├── v5_funding_collector.py  funding rate 独立 worker
│   ├── v5_reflection_worker.py  平仓后异步反思
│   └── paper_monitor.py         SHADOW 仓位监控
│
├── ai/                 ★ AI 决策 + 反思 + 学习
│   ├── trading_assistant.py     OpenAI Assistants + DeepSeek 兼容初始化
│   ├── guardrails.py            SL/TP/size 限幅
│   ├── kelly_sizing.py          Kelly 仓位
│   ├── memory_uploader.py       平仓 → Vector Store
│   ├── reflection_runner.py     LLM 反思生成
│   ├── reflection_prompt.py     反思 prompt
│   ├── confidence_calibration.py 置信度校准
│   ├── failure_taxonomy.py      失败模式分类 matcher
│   ├── failure_taxonomy_seed.py 8 种子失败模式
│   ├── local_rag.py             本地 LR 兜底 (deprecated)
│   ├── setup_assistant.py       Assistant + Vector Store 首次初始化
│   ├── setup_aggregator.py      setup 性能聚合
│   ├── setup_type.py            setup_type 派生 (RSI/MACD/funding → 类型字符串)
│   ├── funding_rate_calculator.py funding z-score
│   └── prompt.py                system prompt
│
├── backtest/           ★ M6 回测引擎 (核心可复用)
│   ├── __main__.py              CLI: python -m scripts.backtest run --days 30
│   ├── runner.py                BacktestRunner — iterate + score + simulate
│   ├── kline_fetcher.py         OKX 拉历史 K 线 + JSON disk cache
│   ├── position_sim.py          OHLC-touch SL/TP 出场模拟 ★ 可复用
│   ├── cost_model.py            ★ OKX maker/taker fee + 滑点模型
│   ├── reporter.py              build_summary / apply_costs_to_entries
│   └── schemas.py               BacktestEntry / SetupStats / BacktestSummary
│
├── experiments/        ★ 独立实验框架 (本会话新增)
│   └── macd_cross_entry_wf.py   3 个 entry-timing variant + WF + cost
│
├── core/
│   └── risk_calculator.py       (legacy V4)
│
├── 顶层 .py — 核心实现:
├── risk_constitution.py    ★★ 7 条铁律 + 进化层窄区间 — 唯一真相源
├── risk_gates.py           ★★ 8 个 gate_* 函数 + clamp_* + IronlawViolation
├── v5_strategy.py          ★ 三 mode: and_strict / trend_aligned / macd_reversal_long
├── v5_risk_calculator.py   plan() 算 SL/TP/size, derive_safe_leverage() 反推杠杆
├── v5_indicator_engine.py  RSI / MACD / ATR (纯函数,无 I/O)
├── v5_position_manager.py  V5PositionManager (开仓后挂 SL/TP + 回滚)
├── v5_params.py            热参数 5s TTL cache (env > DB > default)
├── v5_symbol_whitelist.py  22 个高流动性主流币池
├── v5_types.py             Dataclass: EnrichedItem / Decision / Indicators / AIResult / RiskPlan
├── walkforward.py          M6 walk-forward CLI 引擎 (跨多窗口 OOS)
├── m9_knowledge.py         M9 候选规则 CRUD
├── m9_validate.py          M9 候选规则异步 walk-forward
├── exchange_factory.py     OkxTrader / BinanceTrader factory (按 EXCHANGE env)
├── okx_trader.py           OKX 下单
├── binance_trader.py       Binance 下单 (备用)
├── paper_position_manager.py  SHADOW 纸面仓位
├── execution_guard.py      执行保障
├── local_db.py             SQLite 初始化 + migration
├── config.py               TradingConfig 单例 — 集中环境变量
├── setup_performance.py    setup_type 聚合 + M8 auto-prune
└── 一堆 diagnose_*.py / check_*.py — 一次性诊断脚本 (不在运行时)
```

#### 🎯 关键设计接缝

| 想改什么 | 改哪里 |
|---|---|
| **加新策略 mode** | `v5_strategy.py` — 加新 `_decide_xxx()` + `decide()` 主入口分支 + 测试 |
| **加新风控闸门** | `risk_gates.py` — 新 `gate_*()` 函数,在 `scorer.py` 串接 |
| **改宪法常量** | `risk_constitution.py` — 例如改 `MAX_PER_TRADE_RISK_PCT` |
| **加新 setup_type** | `scripts/ai/setup_type.py` derive_setup_type() |
| **改 AI 行为** | `scripts/ai/trading_assistant.py` + `prompt.py` |
| **新 backtest 实验** | `scripts/experiments/` 加新 .py (复用 cost_model / position_sim / kline_fetcher) |
| **新 hot 配置项** | `scripts/v5_params.py` 加到 `_ENV_MAP` + `DEFAULTS` + `PARAM_META` |
| **新 KPI 指标** | `api/routes/v5_trader_kpi.py` + 前端 `useV5TraderKpi.ts` |

---

## 5. 前端 (React 19 + Vite 6 + TS + TailwindCSS)

```
Rabbit Hunterfronted/
├── App.tsx                  ★ 路由表 (15 active + 11 legacy /v5/* redirect)
├── index.tsx / index.html / index.css   入口
├── tailwind.config.js       ★ Field Instrument design tokens
├── tsconfig.json / vite.config.ts / vitest.config.ts
├── nginx.conf               生产 nginx 反代 /api 到 api:8000
├── Dockerfile               build → nginx static
├── types.ts                 全局 TS 类型
│
├── components/
│   ├── layout/              ★ AppShell + Sidebar + HeaderBar
│   ├── primitives-v3/       ★ 共 8 个基础组件 + cn helper (全 token 化)
│   │   ├── Card / MetricCard / StatusPill / Alert
│   │   ├── SegmentButton / SectionTitle / FormField / Drawer
│   │   └── cn.ts            cn() 合并 className + cardClassName()
│   ├── pages-v4/            ★ 当前主页面 (12 个,全 token 化)
│   │   ├── DashboardPage.tsx       ★ 交易员中控台 (Hero=宪法 7 行)
│   │   ├── PortfolioPage.tsx
│   │   ├── HistoryPage.tsx
│   │   ├── BacktestPage.tsx
│   │   ├── KnowledgePage.tsx       (M9)
│   │   ├── AuditPage.tsx
│   │   ├── LearningPage.tsx
│   │   ├── DiagnosticsPage.tsx
│   │   ├── CollectPage.tsx
│   │   ├── MarketPage.tsx
│   │   ├── ReliabilityPage.tsx
│   │   └── SettingsPage.tsx
│   ├── pages/               混合 — 3 个 live + 8 个 legacy
│   │   ├── V5ChartPage.tsx         ✅ live (TradingView K 线)
│   │   ├── V5ManualOrderPage.tsx   ✅ live (手动开单 3-step wizard)
│   │   ├── V5GlossaryPage.tsx      ✅ live (术语词典)
│   │   └── 其他 8 个 V5*Page.tsx   ⚠️ legacy (App.tsx 未引用)
│   ├── primitives/          legacy V2 (LoadingSkeleton / Sparkline / ErrorBoundary 等还在用)
│   └── shared/              共享小工具组件
│
├── hooks/                   ★ 数据获取
│   ├── api/                 18 个 React Query hooks (一一对应 endpoint)
│   ├── useV5WebSocket.ts    WS 连接 + 状态
│   └── useSystemMode.ts     SHADOW / LIVE 切换
│
├── services/                ★ 客户端基础设施
│   ├── api.ts               apiGet/Post/Patch/Delete 包装 + Bearer Token
│   ├── apiInterceptor.ts    请求拦截
│   ├── store.ts             Zustand UI store (selectedSymbol / sidebar / ...)
│   ├── tokens.ts            ★ 与 tailwind.config.js mirror (设计 tokens TS 镜像)
│   └── glossary.ts          术语字典
│
├── ui/                      legacy (空或几乎空)
└── tests/                   Vitest 测试
```

### 5.1 视觉系统 — "Field Instrument" tokens

定义在 `tailwind.config.js`,镜像在 `services/tokens.ts`。

| 用途 | Token class | Hex | 语义 |
|---|---|---|---|
| 背景主 | `bg-bg-base` | #0F1115 | 暖深黑 |
| 卡片 | `bg-bg-surface` | #171A20 | 上浮一档 |
| 深底 | `bg-bg-deep` | #0A0C0F | 输入框 |
| 文本 | `text-ivory` / `-70` / `-40` / `-25` | #F1ECDD | 象牙白 + 4 档透明度 |
| 强调 | `text-brass` / `bg-brass-soft` | #C9A14B | 黄铜金 — primary / active |
| LONG / 正盈 | `text-sage` / `bg-sage-soft` | #6B8568 | 鼠灰绿 |
| SHORT / 负盈 | `text-oxblood` / `bg-oxblood-soft` | #A53E32 | 暗红 |
| Info | `text-ink` / `bg-ink-soft` | #5A7691 | 灰蓝 |
| 描边 | `border-hairline` / `-strong` | rgba(241,236,221,.10/.18) | 发丝细线 |
| 字间 | `tracking-wider2/3/4` | .18/.22/.26em | eyebrow letter-spacing |
| 字体 | `font-mono` | Fira Code | tabular-nums |

🎯 **优化此处不要碰 token 名 — 它们已扩散到 50+ 文件**。改 token 值(hex)反而 OK,全局生效。

### 5.2 数据流 (前端)

```
React Query (5-30s refetch)
   ├── useV5Dashboard         24h 信号 + paper 统计
   ├── useV5TraderKpi         ★ 30d 滚动 KPI + 宪法 + AI 健康
   ├── useV5ActivePositions   实时活仓
   ├── useV5AIDecisions       AI 决策日志
   ├── useV5Klines            K 线 (按 symbol + interval)
   ├── useV5Settings          配置 (含 enable_auto_trading 等开关)
   └── ... 12 个其他 hook
   ↓
   Components 消费 + Zustand 维 UI 状态
   ↓
   渲染 Field Instrument 风格 UI
```

---

## 6. 数据库 (SQLite, `data/rabbit_hunter.db`)

19 张关键表:

| 表 | 写入方 | 读取方 | 用途 |
|---|---|---|---|
| `trade_scores_v5` | scorer | dashboard / history / diagnostics | 每个 tick 一行(信号 + AI 决策 + 阻断原因) |
| `paper_trades` | paper_pm | portfolio / dashboard KPI | SHADOW 纸面仓位 |
| `positions_v5` | live_pm | portfolio | LIVE 真实仓位 |
| `system_settings` | api/v5_settings | params loader | 热配置 (mode / whitelist / 阈值) |
| `funding_rates` | v5_funding_collector | strategy / dashboard | 历史资金费率 |
| `funding_zscore_cache` | funding 计算 | scorer | 30d z-score 缓存 |
| `reflections` | reflection_worker | audit page | 每笔平仓的 LLM 反思 |
| `reflection_queue` | scorer 平仓 | reflection_worker | 待反思队列 |
| `ai_training_data` | memory_uploader | (写一次/读) | 喂 Vector Store 的样本 |
| `ai_confidence_calibration` | calibration runner | trading_assistant | confidence 校准曲线 |
| `failure_taxonomy` | seed + reflection | trading_assistant | 8 种失败模式分类 |
| `setup_performance` | M8 aggregator | gate_setup_enabled | 各 setup_type R 累计 |
| `setup_performance_daily` | daily aggregator | analytics | 按日 setup 表现 |
| `position_sizing_recommendations` | Kelly | risk_calculator | 仓位建议 |
| `m9_books` / `m9_candidate_rules` / `m9_knowledge_chunks` | api/v5_m9 | knowledge page | 知识层 |
| `ws_event_queue` | scorer / pm | ws_v5 broadcaster | 跨进程 WS 事件 |

---

## 7. 风控宪法 7 条 — 改这里影响动钱代码

定义在 `scripts/risk_constitution.py`,在 `scripts/risk_gates.py` 实现 gate,在 `scripts/tasks/scorer.py` 串接执行。

| 规则 | 常量 / 函数 | 执行点 | API 暴露 |
|---|---|---|---|
| 1 单笔风险 ≤ 1% | `MAX_PER_TRADE_RISK_PCT` + `resolve_risk_pct_for_equity()` | `scorer._risk_per_trade()` + `gate_per_trade_risk()` | `trader-kpi.constitution.rule_1_*` |
| 2 进场必挂 SL + 失败回滚 | `SL_MANDATORY_AT_ENTRY` + `gate_sl_attached()` | `v5_position_manager.open_position` | `rule_2_*` |
| 3 日内 -3% 锁仓 | `DAILY_DRAWDOWN_LIMIT_PCT = 0.03` + `gate_daily_drawdown()` | `scorer:252` | `rule_3_*` |
| 4 杠杆 3-5x + 反推 | `MIN_LIQ_TO_SL_DISTANCE_RATIO = 2.0` + `derive_safe_leverage()` + `gate_liquidation_distance()` | `v5_risk_calculator` + `scorer:333` | `rule_4_*` |
| 5 SL ratio ∈ [1.5, 2.2] + 仓位 [0.6, 1.1] | `FINAL_SL_ATR_RATIO_MIN/MAX` + `EVOLUTION_SIZE_MULT_MIN/MAX` + `gate_final_sl_ratio()` + `clamp_evolution_*()` | `scorer:317,326` | `rule_5_*` |
| 6 SHORT 默认关 | `config.enable_short_trading = False` + scorer 内联 gate | `scorer:235` (我加的) | `rule_6_*` |
| 7 杀手 setup 禁用 | `DEFAULT_DISABLED_SETUPS` frozenset + `gate_setup_enabled()` | `scorer:244` | `rule_7_*` |

🎯 **关键文件**: `docs/risk-constitution-audit.md` 有完整的"宪法 vs 代码"核对清单 + 修复历史。

---

## 8. 配置 + 环境变量

### 8.1 三层优先级

```
env > system_settings(DB) > 代码 default
```

- env: `.env` (gitignored) / `docker-compose.yml` 顶部 env_file
- DB: `system_settings` table — 前端 Settings 页面 / API patch 写入
- default: `scripts/config.py` (dataclass) / `scripts/v5_params.py:DEFAULTS`

### 8.2 关键变量 (.env)

```
EXCHANGE=okx                      默认交易所 (binance 备用)
OKX_API_KEY/SECRET/PASSPHRASE     OKX 凭证
ENABLE_AUTO_TRADING=false         主开关 (默认 SHADOW)
ENABLE_SHORT_TRADING=false        宪法 §6
BINANCE_LEVERAGE=5                起步杠杆 (宪法 §4)
V43_RISK_PER_TRADE=0.01           单笔风险 (宪法 §1)
AI_FAIL_OPEN=false                AI 故障是否仍下单
SL_TP_FAIL_OPEN=false             SL 挂单失败是否保留仓
DEEPSEEK_ENABLED / DEEPSEEK_API_KEY
OPENAI_API_KEY / OPENAI_ASSISTANT_ID / OPENAI_VECTOR_STORE_ID
PAPER_INITIAL_BALANCE_USDT=10000
API_BEARER_TOKEN                  HTTP auth (可空,127.0.0.1 隔离时)
```

### 8.3 热配置 (system_settings, 前端可改)

```
v5_strategy_mode                  trend_aligned / and_strict / macd_reversal_long
v5_use_symbol_whitelist           true / false
v5_sl_atr_mult / v5_tp_atr_mult   SL/TP ATR 倍数
v5_rsi_overbought / v5_rsi_oversold
v5_trend_rsi_long/short_threshold
v5_funding_anti_pile_threshold
v5_max_concurrent                 同时活仓数上限 (默认 3)
v5_leverage                       杠杆 cap (默认 5, derive_safe_leverage 会再压)
v5_risk_per_trade                 单笔风险 (默认 0.01)
v5_anti_chase_pct / window_bars
v5_symbol_whitelist               逗号分隔字符串覆盖默认 22
deepseek_api_key                  AI key (前端 Settings 填)
okx_api_key / secret / passphrase OKX 凭证 (前端 Settings 填)
```

---

## 9. 测试 (`tests/`, 53 个文件)

```
test_v5_strategy*.py          ★ 决策器 3 mode 边界
test_safety_defaults.py       ★ 风控默认值 + leverage 反推
test_risk_gates.py            ★ 7 个 gate_* 函数
test_v5_scoring_pipeline.py   ★ scorer 端到端
test_v5_risk_calculator.py    plan() 公式
test_walkforward.py           M6 引擎
test_m9_*.py                  M9 知识层
test_paper_position_manager_v5.py
test_v5_position_*.py
test_v5_funding_*.py
test_v5_indicator_engine.py
test_v5_symbol_whitelist.py
test_trading_assistant_*.py
test_deepseek_adapter.py      ⚠️ 3 失败 (158c90f 引入,本会话未触)
test_failure_taxonomy_*.py
test_reflection_*.py
test_ai_v5_adapter.py / test_kelly_sizing.py / test_confidence_calibration.py
test_setup_*.py
test_local_db_v5.py / test_funding_db.py
test_v5_*_api.py              FastAPI 路由 (10+ 文件)
test_websocket_v5.py
test_collector_preflight.py
test_chandelier.py / test_local_rag.py
```

跑全套: `python3 -m pytest tests/ -q`
现状: **425 passed / 3 known-broken (test_deepseek_adapter)**.

---

## 10. 关键扩展点速查表 (✨ "我想做 X — 改哪")

| 想做的事 | 改哪个文件 | 新加文件 |
|---|---|---|
| 加一个新页面 (前端) | `App.tsx` 加 Route | `components/pages-v4/XxxPage.tsx` |
| 加一个新 API endpoint | `api/main.py` import + include | `api/routes/v5_xxx.py` |
| 加一个新前端 hook | — | `Rabbit Hunterfronted/hooks/api/useV5Xxx.ts` |
| 加一个新风控闸门 | `scorer.py` 串接 + 测试 | `risk_gates.py` 加 `gate_xxx()` |
| 加新策略 mode | `v5_strategy.py:decide()` 加分支 + 测试 | 新 `_decide_xxx()` |
| 加新 setup_type | `scripts/ai/setup_type.py:derive_setup_type()` | — |
| 加新指标 (TA) | `v5_indicator_engine.py` 加纯函数 | — |
| 加新 backtest 实验 | — | `scripts/experiments/xxx.py` (复用 cost_model + position_sim) |
| 加新 setting 项 | `v5_params.py:_ENV_MAP/DEFAULTS/PARAM_META` + 前端 SettingsPage | — |
| 改宪法常量 | `scripts/risk_constitution.py` + 跑全测试 | — |
| 加新视觉 token | `tailwind.config.js:colors` + `services/tokens.ts` (mirror) | — |
| 加新 db 表 | `scripts/local_db.py` 加 CREATE + migration | — |

---

## 11. Legacy / 半死 / 跳过区 (改的时候避开)

| 路径 | 状态 | 说明 |
|---|---|---|
| `scripts/collector.py` | 归档 | 旧入口,直接运行打 deprecation 退出。用 `scripts/tasks/collector_main` |
| `scripts/core/risk_calculator.py` | V4 老版 | V5 用 `scripts/v5_risk_calculator.py`,核心计算在那 |
| `scripts/diagnose_*.py / check_*.py` | 一次性诊断 | 不在运行时,不要跑 |
| `Rabbit Hunterfronted/components/pages/V5*` 里 8 个 | legacy | App.tsx 未引用,`/v5/*` 已 redirect 到 pages-v4。改了不生效 |
| `Rabbit Hunterfronted/components/primitives/` | legacy V2 | 当前用 primitives-v3 |
| `api/websocket_server.py` | V4 ws | 不主推,主用 websocket_v5 |
| `scripts/binance_*.py` (除 trader) | 备用 | 主用 OKX。binance 路径需 `EXCHANGE=binance` 才激活 |
| `Rabbit Hunterfronted/ui/` | 空 | 历史目录 |
| `data/rabbit_hunter.db.backup-pre-v5.*` / `*.malformed-*` | 备份 | 不要动 |
| 8 个 `weights_router / system_router / market_router` 注册被 `# TODO(v5)` 注释 | V4.3 残留 | 注释里写 "rewire to SQLite/V5" |

---

## 12. Docker compose 拓扑

```yaml
services:
  api:        FastAPI on 127.0.0.1:8000
  collector:  python -m scripts.tasks.collector_main (no HTTP port)
  frontend:   nginx 静态前端 on 127.0.0.1:5173 (反代 /api → api:8000)

挂卷:
  ./data    → /app/data     (SQLite + JSONL + backtest cache)
  ./reports → /app/reports  (walk-forward 输出)
```

启动: `docker compose up -d`

---

## 13. 已知遗留 / 准备优化的设计债

| 项 | 现状 | 优化建议 |
|---|---|---|
| `disk I/O error` from V5FundingCollector | 偶发,macOS Docker bind mount + WAL 锁竞争 | `PRAGMA journal_mode=DELETE` 或换 Docker named volume |
| Maker-only 下单 | 没实现,scorer 假设 taker | `v5_position_manager` 改成 limit + postOnly + 超时撤单 |
| AI 健康度回流 | 现只在 dashboard 展示 | 可让 `enable_auto_trading` 在 AI 长期兜底时自动关 |
| 白名单 22 vs 17 | 数据上 BTC/ETH/BCH/HYPE/TRX 是负 edge 但仍在白名单 | 用户决定是否真删 |
| 反思层利用率 | reflections 36 行但 ai_training_data 仍 0 | memory_uploader 需要被 cron 触发 |
| 8 个 legacy `pages/` 文件 | 死代码 | 可整文件夹删,或加注释标 deprecated |
| 前端 chunk 大小 600+ KB | 单文件未 code-split | 按路由 dynamic import (大量页面只有一次访问) |

---

## 14. 本会话沉淀的关键文档

| 文档 | 用途 |
|---|---|
| `docs/project-structure.md` | 本文 — 架构 + 设计接缝 |
| `docs/risk-constitution-audit.md` | 风控宪法 vs 代码核对 |
| `docs/readme-vs-code-diff.md` | 文档 vs 代码差异 |
| `docs/ui-design-brief-for-ai-generation.md` | 早期 UI brief (老的) |
| `docs/visual-design-v2/` | Field Instrument v2 设计资产 |
| `reports/exp_q1_stress.json` | Q1 stress test (PF 2.25) |
| `reports/exp_v1_*.json` | A/B/C entry-timing 实验 |
| `reports/wf_*.json` | 各种 walk-forward 报告 |

---

## 15. 关键 commit 树 (本会话)

```
3ccc848 style(ui): sweep 剩 3 个 live 页面到 tokens
ac3f852 style(ui): pages-v4 11 个页面 sweep
7c1c51d feat(ui): 交易员中控 Dashboard + tokens 全面落地
a1eb7bd feat(strategy): 加 macd_reversal_long mode (V1 实验落地)
49f450c feat(experiment): MACD 进场时机对照实验 + 22→17 双 OOS 验证
7cf55b2 feat(whitelist): 扩展高流动性白名单到 25
e5b6de2 fix(collector): _system_mode 是 ghost call
4f1e80d fix(constitution): SHORT/risk/leverage 默认值对齐宪法
```

每个 commit message 都写了 "依据 / 实现 / 测试 / 验证",有完整审计 trail。
