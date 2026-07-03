# Rabbit Hunter 项目逻辑结构总览

> 版本：v0.5.x → HEAD · 最后更新：2026-07-03
> 事实来源: docs/audit-2026-07/architecture-map.md

---

## 一、项目定位

**Rabbit Hunter** 是一套面向 Binance / OKX 永续合约的**量化交易系统**，核心闭环：

> 市场扫描 → 深度采集 → V5 评分 → AI 二次审查 → 开仓执行 → 持仓监控 → 平仓学习 → AI 反思

支持三种运行模式：
- **LIVE 实盘** —— 真实下单（当前 `system_settings` 无 `system_state` 行，未激活）
- **SHADOW 影子（纸面交易）** —— 信号同实盘，只写 `paper_trades`，用真实行情验证策略
- **TESTNET 测试网** —— Binance/OKX 测试环境

设计哲学：**Fail-Closed 安全姿态**——不确定 = 拒绝交易，而非冒险放行。AI 调用超时、SL/TP 下单失败、Broker 同步异常，全部选择最保守路径。

**七大设计理念：**

1. **异步管道** —— Scanner → DeepCollector → V5Scorer → Writer 通过 asyncio.Queue 串联，各自独立扩缩，互不阻塞
2. **本地优先** —— SQLite 单文件，零网络延迟，支持离线分析
3. **规则 + AI 双层** —— 规则引擎提供可解释下限，TradingAssistant（OpenAI/DeepSeek）提供学习上限，Guardrails 兜底
4. **学习闭环** —— 平仓 → AI 反思 → `setup_performance` 聚合 → 下次决策参考；M9 知识层持续沉淀可机器验证的交易知识
5. **Fail-Closed** —— AI 不可用 = 拒绝交易；SL 挂单失败 = 立即市价平仓回滚主仓
6. **三服务 Docker 化** —— api / collector / frontend 独立扩缩，共享 data volume
7. **宪法约束** —— 7 条铁律在 `risk_constitution.py` + `risk_gates.py` 全程把守，无论 AI 如何决策均不得越界

---

## 二、技术栈

| 层 | 技术 |
|----|------|
| 交易执行 | Python 3.11 + CCXT 4.4 + Binance / OKX Futures API |
| 数据库 | SQLite（本地，单文件；`data/rabbit_hunter.db`）|
| 采集 & 评分 | asyncio + Pandas + NumPy |
| AI 决策 | OpenAI（GPT-4o）/ DeepSeek API + 本地 RAG（`ai_training_data`）|
| API 服务 | FastAPI 0.115 + Uvicorn + WebSocket + Bearer Token 鉴权 |
| 前端 | React 19 + Vite 6 + TypeScript + TailwindCSS + TanStack Query 5 |
| 容器 | Docker + docker-compose（api / collector / frontend 三服务）|

---

## 三、目录骨架

```
Rabbit-Hunter/
├── api/                              # FastAPI 后端
│   ├── main.py                       # 入口：FastAPI + 14 个 router + lifespan + /healthz + WebSocket 后台任务
│   ├── dependencies.py               # 全局 Bearer Token 鉴权依赖（_global_auth）
│   ├── websocket_v5.py               # WebSocket 端点 /ws/v5（心跳 30s，主 WebSocket）
│   ├── websocket_server.py           # V4.3 legacy stub /ws/v43（已不主推）
│   ├── routes/                       # 15 个 HTTP endpoint 文件（v5 前缀）
│   │   ├── positions.py              # GET /api/v5/positions, /paper-positions
│   │   ├── scores.py                 # GET /api/v5/signals
│   │   ├── v5_account.py             # GET /api/v5/account/balance
│   │   ├── v5_ai.py                  # GET /api/v5/ai/status, /decisions
│   │   ├── v5_charts.py              # GET /api/v5/klines/{symbol}, /events/{symbol}
│   │   ├── v5_constitution.py        # GET /api/v5/constitution, /ironlaw-state, /setup-performance
│   │   ├── v5_funding.py             # GET /api/v5/funding/status, /history/{symbol}
│   │   ├── v5_m9.py                  # M9 知识库 CRUD（books / candidates / validate / approve / reject）
│   │   ├── v5_manual_order.py        # POST /api/v5/manual-order/preview|execute
│   │   ├── v5_position_close.py      # POST /api/v5/positions/{id}/close
│   │   ├── v5_reflection.py          # GET /api/v5/reflections, /failure-taxonomy, /sizing-recommendations 等
│   │   ├── v5_settings.py            # GET|PATCH /api/v5/settings，POST test-ai
│   │   ├── v5_strategy_config.py     # GET|PATCH /api/v5/strategy-config，POST preview
│   │   ├── v5_trader_kpi.py          # GET /api/v5/dashboard/trader-kpi（KPI 聚合）
│   │   └── v5_walkforward.py         # Walk-Forward 实验：GET /reports, POST /run, GET /jobs
│   ├── services/                     # 业务逻辑层
│   │   ├── market_service.py         # normalize_symbol / build_ccxt_config / fetch_market_price_and_change
│   │   ├── position_service.py       # 查询 positions_v5 / paper_trades
│   │   ├── score_service.py          # 时间字段规范化（ensure_utc_iso）
│   │   └── v5_broadcast.py           # V5Broadcaster：WebSocket 多连接广播
│   └── schemas/                      # Pydantic 请求/响应 schema（8 个文件）
│
├── scripts/                          # 核心采集 / 评分 / 交易逻辑
│   ├── config.py                     # TradingConfig dataclass（环境变量集中读取）
│   ├── local_db.py                   # SQLite schema 初始化 + 迁移 + failure_taxonomy seed
│   ├── exchange_factory.py           # get_trader()：Binance / OKX 切换
│   ├── binance_trader.py             # Binance perpetual trader（ccxt 封装）
│   ├── okx_trader.py                 # OKX perpetual trader
│   ├── v5_position_manager.py        # LIVE 持仓管理，走 Broker 真实下单，写 positions_v5
│   ├── paper_position_manager.py     # SHADOW 虚拟持仓，写 paper_trades
│   ├── v5_position_monitor.py        # 30s 轮询活仓，管理 SL/TP/trailing，INSERT ws_event_queue
│   ├── v5_signal_manager.py          # 查询 trade_scores_v5，供 API 调用
│   ├── v5_strategy.py                # 策略规则引擎（三 mode：and_strict / trend_aligned / macd_reversal_long）
│   ├── v5_indicator_engine.py        # 技术指标（RSI / MACD / ATR / Chandelier Stop）
│   ├── v5_risk_calculator.py         # 仓位大小、止损距离计算
│   ├── v5_params.py                  # 策略参数常量（_ENV_MAP / DEFAULTS / PARAM_META）
│   ├── v5_types.py                   # 核心类型定义（EnrichedItem / Indicators / AIResult）
│   ├── v5_symbol_whitelist.py        # V5_TOP20_WHITELIST（20 个监控合约）
│   ├── risk_constitution.py          # 铁律体检逻辑（7 条宪法常量）
│   ├── risk_gates.py                 # 开仓前风险检查门控（7 个 gate_* 函数）
│   ├── setup_performance.py          # refresh_setup_performance()
│   ├── walkforward.py                # Walk-Forward 实验主程序（被 v5_walkforward.py 作子进程调用）
│   ├── m9_knowledge.py               # M9 知识库：书籍导入、知识块切片、候选规则 CRUD
│   ├── m9_validate.py                # M9 候选规则回测验证
│   │
│   ├── tasks/                        # 主流水线编排层（异步采集管道）
│   │   ├── collector_main.py         # 主入口：组装并运行 7+ 协程（scanner / scorer / monitor / reflection_worker 等）
│   │   ├── scanner.py                # MarketScanner：轮询交易所，筛 top mover，推入 movers_queue
│   │   ├── deep_collector.py         # DeepCollector：从 movers_queue 拉 klines + 资金费率 + 深度，推入 enriched_queue
│   │   ├── scorer.py                 # V5Scorer：计算指标、过 AI gate、写 trade_scores_v5、触发 paper_pm / live_pm 开仓
│   │   ├── writer.py                 # DatabaseWriter：异步批量写 SQLite
│   │   ├── v5_funding_collector.py   # V5FundingCollector：周期拉资金费率，INSERT OR IGNORE funding_rates
│   │   ├── v5_reflection_worker.py   # V5ReflectionWorker：SELECT reflection_queue → AI 调用 → INSERT reflections
│   │   ├── paper_monitor.py          # 任务级 paper 持仓轮询（已被 v5_position_monitor 替代，保留兼容）
│   │   ├── exchange_endpoints.py     # 交易所端点配置（testnet/mainnet URL）
│   │   └── utils.py                  # 任务级通用工具
│   │
│   ├── ai/                           # AI 子系统
│   │   ├── trading_assistant.py      # TradingAssistant：主 AI 客户端（OpenAI / DeepSeek）
│   │   ├── reflection_runner.py      # 生成反思，INSERT reflections
│   │   ├── confidence_calibration.py # 预测准确率分桶统计，写 ai_confidence_calibration
│   │   ├── kelly_sizing.py           # Kelly 仓位推荐，写 position_sizing_recommendations
│   │   ├── funding_rate_calculator.py# 资金费率 Z-score，写 funding_zscore_cache
│   │   ├── failure_taxonomy.py       # 读 failure_taxonomy，用于 AI prompt 分类
│   │   ├── local_rag.py              # 本地 RAG：从 ai_training_data 检索历史样本
│   │   ├── setup_aggregator.py       # 每日聚合 reflections → setup_performance_daily
│   │   ├── memory_uploader.py        # 周期把 trade log 上传到 OpenAI Vector Store
│   │   ├── guardrails.py             # AI 决策护栏（仓位上限、亏损熔断）
│   │   ├── prompt.py                 # AI 入场分析 prompt 模板
│   │   ├── reflection_prompt.py      # 反思生成 prompt 模板
│   │   └── setup_type.py             # 交易形态分类（setup type 枚举）
│   │
│   └── backtest/                     # M6 回测引擎子包
│       ├── runner.py                 # Walk-Forward 切片 + 回测驱动
│       ├── position_sim.py           # 持仓模拟（SL/TP 触发）
│       ├── kline_fetcher.py          # 历史 klines 拉取
│       ├── cost_model.py             # 手续费 / 资金费率成本建模
│       ├── reporter.py               # 输出 JSON 报告
│       └── schemas.py                # 回测结果 schema
│
├── Rabbit Hunterfronted/             # React 前端 SPA
│   ├── App.tsx                       # 路由注册；根路径 / 重定向至 /overview；/v5/* 重定向至 pages-v4（:46-57）
│   ├── components/
│   │   ├── layout/                   # AppShell（导航栏 + 侧边栏）
│   │   ├── pages-v4/                 # 活跃主力页面（14 页，见 §八）
│   │   ├── pages/                    # V5 独立组件页（3 页：V5ChartPage / V5ManualOrderPage / V5GlossaryPage）
│   │   ├── primitives-v3/            # 当前基础组件（Card / MetricCard / StatusPill / Drawer 等）
│   │   ├── primitives/               # V2 基础组件（Sparkline 等，部分仍在用）
│   │   └── shared/                   # 跨页面共享组件
│   ├── hooks/
│   │   ├── api/                      # TanStack Query hooks（17 个文件，详见 §八）
│   │   ├── useSystemMode.ts          # 从 GET /api/v5/settings 派生 system_mode 字符串
│   │   └── useV5WebSocket.ts         # 管理 /ws/v5 连接，更新 TanStack Query 缓存
│   ├── services/
│   │   └── api.ts                    # apiGet / apiPost / apiPatch / apiDelete（可选 Bearer Token 注入）
│   └── ui/                           # shadcn/ui 基础样式组件
│
├── data/                             # 运行时数据（.gitignore）
│   └── rabbit_hunter.db              # SQLite 主库
│
├── reports/                          # Walk-Forward 实验输出（JSON，.gitignore）
├── tests/                            # 53 个测试文件（见 §十一）
├── docker-compose.yml                # 3 服务编排
├── Dockerfile                        # 后端镜像
├── .env.example                      # 环境变量模板
├── requirements.txt                  # Python 依赖
├── PROJECT_STRUCTURE.md              # 本文件：项目逻辑骨架
├── README.md                         # 快速上手
└── CHANGELOG.md                      # 版本日志
```

---

## 四、真入口 / 主数据流

### 启动命令

| 入口 | 命令 / 触发 | 职责 |
|------|-----------|------|
| 采集 + 开仓 | `python -m scripts.tasks.collector_main`（或 `start_collector.bat`）| 主采集流水线 + AI 评分 + 开仓（模式由 `system_settings.system_state` 决定）|
| API 服务 | `uvicorn api.main:app`（或 `start_api.bat`）| FastAPI HTTP API + WebSocket /ws/v5 |
| 前端 | `npm run dev` in `Rabbit Hunterfronted/`（或 `start_frontend.bat`）| Vite dev server（代理指向 FastAPI）|

模式决定逻辑：`_resolve_mode_db()` — `scripts/tasks/collector_main.py:32` — 读 `system_settings` 表 key=`system_state`，缺省返回 `"SHADOW"`。

### 主数据流

```
MarketScanner             DeepCollector                   V5Scorer
scripts/tasks/scanner.py  scripts/tasks/deep_collector.py  scripts/tasks/scorer.py
(class:129)          →    (class:232)                 →    (class:436)
     |                          |                               |
exchange REST API         klines + funding                      |
(ccxt/binance/okx)        movers_queue → enriched_queue        |
                                                               / \
                                             mode=SHADOW     /     \  mode=LIVE
                                                            /       \
                                         PaperPositionManager     V5PositionManager
                                         paper_position_manager   scripts/v5_position_manager.py
                                         paper_trades (line 130)  positions_v5 (line 44, 未激活)
                                                    |
                     V5Scorer INSERT trade_scores_v5 (scorer.py:151)
                     V5Scorer INSERT ws_event_queue  (scorer.py:40)
                                    |
                          api/main.py:135 SELECT → DELETE → broadcast
                                    |
                            WebSocket /ws/v5 → 前端 TanStack Query 缓存更新

V5FundingCollector  → INSERT funding_rates (v5_funding_collector.py line 40)
V5PositionMonitor   → SL/TP 触发 → UPDATE paper_trades / positions_v5
V5ReflectionWorker  → SELECT reflection_queue → AI 调用 → INSERT reflections → setup_performance 聚合
```

**当前状态**：`system_settings` 表内无 `system_state` 键（表内仅 3 行），`_resolve_mode_db()` 永远返回 `"SHADOW"`，故 `positions_v5` 当前为 0 行——INSERT 路径（`scripts/v5_position_manager.py` line 44）存在但从未触发。

**关键分支点（SHADOW vs LIVE）**：`scripts/tasks/scorer.py:396`

详见 `docs/audit-2026-07/architecture-map.md § 三、四`。

---

## 五、模式与配置

### 运行模式对比

| 模式 | 信号 | 下单 | 用途 |
|------|------|------|------|
| **LIVE 实盘** | 真实 | 真实 Broker 下单，写 `positions_v5` | 生产（当前 `system_state` 未设置，路径未激活）|
| **SHADOW 影子** | 真实 | 内存模拟，写 `paper_trades` | 验证策略 / 评估 AI 决策 KPI |
| **TESTNET 测试网** | 真实 | Binance/OKX 测试网下单 | 集成验证 |

SHADOW 模式（当前默认）：与实盘共用同一套信号 + AI 决策，不调用 Broker，直接写 `paper_trades` 表。前端各页面展示 paper KPI（纸面胜率、PnL），作为上 LIVE 前的"温度计"。

### 热配置（system_settings 表，前端可改）

通过 `api/routes/v5_settings.py` PATCH `/api/v5/settings` 或 `v5_strategy_config.py` 实时写入 `system_settings` 表，**无需重启 collector**（collector 每轮从 DB 重读）：

```
v5_strategy_mode                  trend_aligned / and_strict / macd_reversal_long
v5_use_symbol_whitelist           true / false
v5_sl_atr_mult / v5_tp_atr_mult   SL/TP ATR 倍数
v5_rsi_overbought / v5_rsi_oversold
v5_trend_rsi_long/short_threshold
v5_funding_anti_pile_threshold
v5_max_concurrent                 同时活仓数上限（默认 3）
v5_leverage                       杠杆 cap（默认 5，derive_safe_leverage 会再压）
v5_risk_per_trade                 单笔风险（默认 0.01）
v5_anti_chase_pct / window_bars
v5_symbol_whitelist               逗号分隔字符串覆盖默认 20 标的
deepseek_api_key                  AI key（前端 Settings 填）
okx_api_key / secret / passphrase OKX 凭证（前端 Settings 填）
```

### 环境变量（.env）关键分组

**交易所：**
```bash
EXCHANGE=okx                 # 或 binance
OKX_API_KEY=...
OKX_API_SECRET=...
OKX_API_PASSPHRASE=...
```

**安全：**
```bash
API_BEARER_TOKEN=$(openssl rand -hex 32)
API_BIND_HOST=127.0.0.1      # 强制绑定本机
API_ENABLE_DOCS=false
```

**风控（Fail-Closed 核心）：**
```bash
AI_FAIL_OPEN=false           # AI 不可用 = 拒绝交易
SL_TP_FAIL_OPEN=false        # 止损失败 = 立即市价平仓回滚
```

---

## 六、DB 表全貌

SQLite 主库 `data/rabbit_hunter.db`，19 张关键表（行数截至 2026-07-02）：

| 表 | 写入方 | 消费方 | 行数 |
|----|-------|-------|------|
| `trade_scores_v5` | `scorer.py:151` INSERT | `v5_signal_manager.py` line 27 SELECT | 19,636 |
| `paper_trades` | `paper_position_manager.py:130` INSERT | `position_service.py:48` SELECT | 55 |
| `positions_v5` | `v5_position_manager.py` line 44 INSERT（LIVE 路径未激活）| `position_service.py:22` SELECT | 0 |
| `funding_rates` | `v5_funding_collector.py` line 40 INSERT OR IGNORE | `v5_funding.py` line 59 SELECT | 3,439 |
| `funding_zscore_cache` | `funding_rate_calculator.py:141` INSERT OR REPLACE | `v5_funding.py` line 26 SELECT | 25 |
| `reflections` | `reflection_runner.py:140` INSERT | `v5_reflection.py` line 31 SELECT | 41 |
| `setup_performance` | `setup_performance.py:97` INSERT | `v5_constitution.py` line 136 SELECT | 8 |
| `setup_performance_daily` | `setup_aggregator.py:58` INSERT OR REPLACE | `v5_reflection.py` line 88 SELECT | 11 |
| `ai_confidence_calibration` | `confidence_calibration.py:44` INSERT | `v5_reflection.py` line 150 SELECT | 4 |
| `position_sizing_recommendations` | `kelly_sizing.py:94` INSERT | `v5_reflection.py` line 107 SELECT | 4 |
| `system_settings` | `v5_settings.py` line 37 INSERT OR REPLACE | `collector_main.py:40` SELECT（读 system_state）| 3 |
| `failure_taxonomy` | `local_db.py:974` INSERT OR IGNORE（init seed 一次）| `failure_taxonomy.py:164` SELECT | 8 |
| `reflection_queue` | `local_db.py:946` INSERT（paper_trade 平仓后入队）| `v5_reflection_worker.py` line 40 SELECT | 50 |
| `ws_event_queue` | `scorer.py:40` INSERT；`v5_position_monitor.py` line 22 INSERT | `api/main.py:135` SELECT→DELETE（广播后消费）| 0 |
| `wf_jobs` | `v5_walkforward.py` line 276 INSERT | `v5_walkforward.py` line 299 SELECT | 3 |
| `m9_books` | `m9_knowledge.py` line 152 INSERT | `m9_knowledge.py` line 170 SELECT | 0 |
| `m9_knowledge_chunks` | `m9_knowledge.py` line 220 INSERT | `m9_knowledge.py` line 210 SELECT | 1 |
| `m9_candidate_rules` | `m9_knowledge.py` line 249 INSERT；`m9_validate.py` line 104 UPDATE status | `m9_knowledge.py` line 270 SELECT | 0 |
| `ai_training_data` | Supabase 回填（一次性，已完结）| `v5_ai.py` line 61 SELECT COUNT | 0 |

详见 `docs/audit-2026-07/architecture-map.md § 五`（含完整写入方/消费方及精确行号）。

---

## 七、风控宪法 7 条

定义在 `scripts/risk_constitution.py`，在 `scripts/risk_gates.py` 实现 gate，在 `scripts/tasks/scorer.py` 串接执行。

| 规则 | 常量 / 函数 | 执行点 | API 暴露 |
|------|-----------|-------|---------|
| 1 单笔风险 ≤ 1% | `MAX_PER_TRADE_RISK_PCT` + `resolve_risk_pct_for_equity()` | `scorer._risk_per_trade()` + `gate_per_trade_risk()` | `constitution.rule_1_*` |
| 2 进场必挂 SL + 失败回滚 | `SL_MANDATORY_AT_ENTRY` + `gate_sl_attached()` | `v5_position_manager.open_position` | `rule_2_*` |
| 3 日内 -3% 锁仓 | `DAILY_DRAWDOWN_LIMIT_PCT = 0.03` + `gate_daily_drawdown()` | `scorer:252` | `rule_3_*` |
| 4 杠杆 3-5x + 反推 | `MIN_LIQ_TO_SL_DISTANCE_RATIO = 2.0` + `derive_safe_leverage()` + `gate_liquidation_distance()` | `v5_risk_calculator` + `scorer:333` | `rule_4_*` |
| 5 SL ratio ∈ [1.5, 2.2] + 仓位 [0.6, 1.1] | `FINAL_SL_ATR_RATIO_MIN/MAX` + `gate_final_sl_ratio()` + `clamp_evolution_*()` | `scorer:317,326` | `rule_5_*` |
| 6 SHORT 默认关 | `config.enable_short_trading = False` + scorer 内联 gate | `scorer:235` | `rule_6_*` |
| 7 杀手 setup 禁用 | `DEFAULT_DISABLED_SETUPS` frozenset + `gate_setup_enabled()` | `scorer:244` | `rule_7_*` |

完整"宪法 vs 代码"核对清单 + 修复历史：`docs/risk-constitution-audit.md`。

**Fail-Closed 安全姿态 4 场景：**

| 失败场景 | 默认行为 |
|---------|---------|
| AI 调用超时 / 异常 | 跳过该信号（不放行）|
| SL / TP 下单失败 | **立即市价平仓**回滚主仓 |
| `AI_FAIL_OPEN=false` | AI 不可用 = 拒绝交易 |
| API 绑定非本机且无 Token | **拒绝启动** |

---

## 八、前端结构

主路由：`Rabbit Hunterfronted/App.tsx`；根路径 `/` 重定向至 `/overview`；旧 `/v5/*` 路径通过 `App.tsx:46-57` Navigate 重定向至新路径。

### pages-v4/（主力活跃页面，14 页）

| 页面文件 | 路由 | 职责概述 |
|---------|------|---------|
| `OverviewPage.tsx` | `/overview`（默认首页）| 账户余额 + 持仓汇总 + KPI |
| `DashboardPage.tsx` | `/dashboard` | 信号列表、持仓、K 线、AI 决策、KPI |
| `CollectPage.tsx` | `/collect` | 市场扫描信号 + 资金费率状态 |
| `AILearningPage.tsx` | `/learning` | AI 反思列表 + 形态表现 + KPI |
| `PortfolioPage.tsx` | `/portfolio` | 活跃持仓管理（平仓操作）|
| `HistoryPage.tsx` | `/history` | 已平仓历史 + 信号历史 |
| `BacktestPage.tsx` | `/backtest` | Walk-Forward 实验台 |
| `AuditPage.tsx` | `/audit` | 反思详情 + 失败分类 + 校准 + 形态表现 |
| `DiagnosticsPage.tsx` | `/diagnostics` | AI 状态 + 信号诊断 + 持仓概览 |
| `KnowledgePage.tsx` | `/knowledge` | M9 知识库（书籍 + 候选规则）|
| `MarketPage.tsx` | `/market` | 品种 K 线 + 事件 + 资金费率历史 |
| `ReliabilityPage.tsx` | `/reliability` | 铁律体检 + 资金费率看板 + 持仓安全 |
| `SettingsPage.tsx` | `/settings` | 系统设置（API key + 模式 + AI 配置）|
| `LearningPage.tsx` | `/learning-v2` | 旧版学习页（v4 遗留，路由保留）|

### pages/（V5 独立组件页，3 页）

| 页面文件 | 路由 | 职责 |
|---------|------|------|
| `V5ChartPage.tsx` | `/chart/:symbol` | 品种详情 K 线 + 事件标记 + 资金费率 |
| `V5ManualOrderPage.tsx` | `/manual` | 手动开单（preview + execute）|
| `V5GlossaryPage.tsx` | `/glossary` | 静态术语表（无 API 调用）|

### 数据层（TanStack Query）

17 个 hook 文件（`hooks/api/useV5Xxx.ts`）对应各 API endpoint，详见 `docs/audit-2026-07/architecture-map.md § 六`（前端页面 ↔ API endpoint 全表）。

数据流向：

```
前端组件 → TanStack Query hook (hooks/api/useV5Xxx.ts)
         → services/api.ts (apiGet / apiPost，注入 Bearer Token)
         → FastAPI HTTP API / WebSocket /ws/v5
                ↕
         useV5WebSocket.ts → /ws/v5 → 实时推送更新 Query 缓存
```

---

## 九、视觉系统 Design Tokens

定义在 `tailwind.config.js`，镜像在 `services/tokens.ts`。**不要改 token 名**——已扩散到 50+ 文件；改 token 值（hex）可全局生效。

| 用途 | Token class | Hex | 语义 |
|------|-----------|-----|------|
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

---

## 十、扩展点速查（改 X 应改哪）

| 想做的事 | 改哪个文件 | 新加文件 |
|---------|----------|---------|
| 加一个新页面（前端）| `App.tsx` 加 Route | `components/pages-v4/XxxPage.tsx` |
| 加一个新 API endpoint | `api/main.py` import + include_router | `api/routes/v5_xxx.py` |
| 加一个新前端 hook | — | `hooks/api/useV5Xxx.ts` |
| 加一个新风控闸门 | `scorer.py` 串接 + 测试 | `risk_gates.py` 加 `gate_xxx()` |
| 加新策略 mode | `v5_strategy.py:decide()` 加分支 + 测试 | 新 `_decide_xxx()` |
| 加新 setup_type | `scripts/ai/setup_type.py:derive_setup_type()` | — |
| 加新指标（TA）| `v5_indicator_engine.py` 加纯函数 | — |
| 加新 backtest 实验 | — | `scripts/experiments/xxx.py`（复用 cost_model + position_sim）|
| 加新 setting 项 | `v5_params.py:_ENV_MAP/DEFAULTS/PARAM_META` + 前端 SettingsPage | — |
| 改宪法常量 | `scripts/risk_constitution.py` + 跑全测试套件 | — |
| 加新视觉 token | `tailwind.config.js:colors` + `services/tokens.ts`（mirror）| — |
| 加新 DB 表 | `scripts/local_db.py` 加 CREATE + migration ALTER | — |

---

## 十一、测试（tests/，53 个文件）

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
test_deepseek_adapter.py      ⚠️ 3 失败（158c90f 引入，已知问题）
test_failure_taxonomy_*.py
test_reflection_*.py
test_ai_v5_adapter.py / test_kelly_sizing.py / test_confidence_calibration.py
test_setup_*.py
test_local_db_v5.py / test_funding_db.py
test_v5_*_api.py              FastAPI 路由（10+ 文件）
test_websocket_v5.py
test_collector_preflight.py
test_chandelier.py / test_local_rag.py
```

运行全套：`python3 -m pytest tests/ -q`
现状：**425 passed / 3 known-broken（test_deepseek_adapter）**

---

## 十二、Docker 拓扑

```yaml
services:
  api:        FastAPI on 127.0.0.1:8000
  collector:  python -m scripts.tasks.collector_main（无 HTTP 端口）
  frontend:   nginx 静态前端 on 127.0.0.1:5173（反代 /api → api:8000）

挂卷:
  ./data    → /app/data     # SQLite + JSONL + backtest cache
  ./reports → /app/reports  # Walk-Forward 输出（JSON）
```

启动：`docker compose up -d`

---

## 十三、Legacy 区（改代码时避开）

| 路径 | 状态 | 说明 |
|------|------|------|
| `api/websocket_server.py` | V4 stub | `/ws/v43` 未删但不主推；主用 `/ws/v5`（`api/websocket_v5.py`）|
| `scripts/tasks/paper_monitor.py` | 被替代 | `v5_position_monitor.py` 是当前主力；paper_monitor 保留兼容 |
| `scripts/core/risk_calculator.py` | V4 老版 | V5 用 `scripts/v5_risk_calculator.py`，核心计算在那 |
| `Rabbit Hunterfronted/components/primitives/` | legacy V2 | 当前主用 `primitives-v3/`；Sparkline 等少量仍在用 |
| `scripts/binance_*.py`（除 binance_trader.py）| 备用 | 主用 OKX；binance 路径需 `EXCHANGE=binance` 才激活 |
| `data/rabbit_hunter.db.backup-pre-v5.*` / `*.malformed-*` | 备份 | 不要动 |
| `scripts/experiments/` | 实验脚本 | 一次性实验（BTC 顺势等），不在运行时 |

---

**文档定位：** 这份文档是项目的"逻辑地图"——模块边界、数据流向、关键设计。实现细节读源码；版本演进读 `CHANGELOG.md`；快速上手读 `README.md`；技术事实权威来源 `docs/audit-2026-07/architecture-map.md`。
