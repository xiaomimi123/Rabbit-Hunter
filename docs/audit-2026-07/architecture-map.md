# Architecture Map · 2026-07

> 生成日期: 2026-07-02
> Git HEAD: e247ef118479bef76715d6316418c34da708c43e
> DB 快照时间: 2026-07-03（行数现查）
>
> 注：文档内 `file.py:NNN` 格式引用均经 Step-7 脚本验证。
> `v5_*` 命名的文件路径因存在数字前缀（`v5_`）会被验证脚本的字符集截断，
> 故此类文件仅标注 `(line NNN)` 而非 `:NNN` 格式，以避免误报。

---

## 一、后端目录

### api/

| 模块 | 职责 | 主入口 |
|---|---|---|
| `api/main.py` | FastAPI 应用实例、路由注册（14 个 router）、lifespan 钩子、/healthz、WebSocket 后台任务 | `app = FastAPI(...)` — `api/main.py:195` |
| `api/dependencies.py` | 全局 Bearer Token 鉴权依赖（`_global_auth`），所有 HTTP router 注入此依赖 | — |
| `api/routes/positions.py` | GET /api/v5/positions（live）、GET /api/v5/paper-positions（shadow）| `api/routes/positions.py:8` |
| `api/routes/scores.py` | GET /api/v5/signals（调用 V5SignalManager 查 trade_scores_v5）| `api/routes/scores.py:8` |
| `api/routes/v5_account.py` | GET /api/v5/account/balance | — |
| `api/routes/v5_ai.py` | GET /api/v5/ai/status，GET /api/v5/ai/decisions | — |
| `api/routes/v5_charts.py` | GET /api/v5/klines/{symbol}，GET /api/v5/events/{symbol} | — |
| `api/routes/v5_constitution.py` | GET /api/v5/constitution，GET /api/v5/ironlaw-state，GET /api/v5/setup-performance | — |
| `api/routes/v5_funding.py` | GET /api/v5/funding/status，GET /api/v5/funding/history/{symbol} | — |
| `api/routes/v5_m9.py` | M9 知识库 CRUD — books / candidates / validate / approve / reject | — |
| `api/routes/v5_manual_order.py` | POST /api/v5/manual-order/preview，POST /api/v5/manual-order/execute | — |
| `api/routes/v5_position_close.py` | POST /api/v5/positions/{position_id}/close | — |
| `api/routes/v5_reflection.py` | GET /api/v5/reflections，GET /api/v5/failure-taxonomy，GET /api/v5/setup-performance，GET /api/v5/sizing-recommendations，PATCH /api/v5/sizing-recommendations/{rec_id}，GET /api/v5/confidence-calibration | — |
| `api/routes/v5_settings.py` | GET /api/v5/settings，PATCH /api/v5/settings，POST /api/v5/settings/test-ai | — |
| `api/routes/v5_strategy_config.py` | GET /api/v5/strategy-config，PATCH /api/v5/strategy-config，POST /api/v5/strategy-config/preview | — |
| `api/routes/v5_trader_kpi.py` | GET /api/v5/dashboard/trader-kpi（KPI 聚合，读 paper_trades + trade_scores_v5）| — |
| `api/routes/v5_walkforward.py` | Walkforward 实验：GET /reports，GET /reports/{name}，POST /run，GET /jobs，GET /jobs/{job_id} | — |
| `api/schemas/` | Pydantic 请求/响应 schema（8 个文件，对应各 route） | — |
| `api/services/market_service.py` | 通用工具：normalize_symbol、build_ccxt_config、fetch_market_price_and_change | `api/services/market_service.py:12` |
| `api/services/position_service.py` | 查询 positions_v5 / paper_trades，供 positions.py route 调用 | `api/services/position_service.py:22` |
| `api/services/score_service.py` | 时间字段规范化工具 ensure_utc_iso / normalize_time_fields | `api/services/score_service.py:10` |
| `api/services/v5_broadcast.py` | V5Broadcaster：WebSocket 多连接广播，api/main.py 后台任务从 ws_event_queue 拉取并广播 | — |
| `api/websocket_v5.py` | WebSocket 端点 /ws/v5（心跳 30s，broadcaster 注册/注销）| — |
| `api/websocket_server.py` | V4.3 WebSocket 遗留端点 /ws/v43（已 stub）| — |

### scripts/tasks/（主流水线编排层）

| 模块 | 职责 | 主类/入口 |
|---|---|---|
| `scripts/tasks/collector_main.py` | **主入口**：组装并运行 Scanner → DeepCollector → V5Scorer → Writer + V5PositionMonitor + V5FundingCollector + V5ReflectionWorker + MemoryAutoUploader | `_resolve_mode_db()` — `scripts/tasks/collector_main.py:32` |
| `scripts/tasks/scanner.py` | MarketScanner：轮询交易所，筛 top mover，推入 movers_queue | `class MarketScanner` — `scripts/tasks/scanner.py:129` |
| `scripts/tasks/deep_collector.py` | DeepCollector：从 movers_queue 取标的，拉 klines + 资金费率 + 深度，推入 enriched_queue | `class DeepCollector` — `scripts/tasks/deep_collector.py:232` |
| `scripts/tasks/scorer.py` | V5Scorer：从 enriched_queue 取数据，计算指标，过 AI gate，写 trade_scores_v5，触发 paper_pm / live_pm 开仓 | `class V5Scorer` — `scripts/tasks/scorer.py:436` |
| `scripts/tasks/writer.py` | DatabaseWriter：异步写队列，批量写 SQLite | `class DatabaseWriter` — `scripts/tasks/writer.py:90` |
| `scripts/tasks/v5_funding_collector.py` | V5FundingCollector：周期从交易所拉资金费率，INSERT OR IGNORE 入 funding_rates | `class V5FundingCollector` (line 21) |
| `scripts/tasks/v5_reflection_worker.py` | V5ReflectionWorker：从 reflection_queue 取已平仓 paper_trade，调 AI 生成 reflection，写 reflections | `class V5ReflectionWorker` (line 21) |
| `scripts/tasks/paper_monitor.py` | 任务级 paper 持仓轮询（已被 v5_position_monitor 替代，保留兼容）| — |
| `scripts/tasks/exchange_endpoints.py` | 交易所端点配置（testnet/mainnet URL）| — |
| `scripts/tasks/utils.py` | 任务级通用工具 | — |

### scripts/（核心业务逻辑）

| 模块 | 职责 | 主类/入口 |
|---|---|---|
| `scripts/local_db.py` | SQLite schema 初始化 + 迁移（CREATE TABLE + ALTER 列），seed failure_taxonomy | `init_local_db()` — `scripts/local_db.py:974` |
| `scripts/config.py` | TradingConfig dataclass，从环境变量读取所有运行参数 | `class TradingConfig` — `scripts/config.py:16` |
| `scripts/v5_position_manager.py` | V5PositionManager：LIVE 模式持仓管理，走 Broker 真实下单，写 positions_v5 | `class V5PositionManager` (line 27) |
| `scripts/paper_position_manager.py` | PaperPositionManager：SHADOW 模式虚拟持仓，写 paper_trades | `class PaperPositionManager` — `scripts/paper_position_manager.py:47` |
| `scripts/v5_position_monitor.py` | V5PositionMonitor：30s 轮询活仓，管理 SL/TP/trailing，INSERT ws_event_queue | `class V5PositionMonitor` (line 157) |
| `scripts/v5_signal_manager.py` | V5SignalManager：查询 trade_scores_v5，供 api/routes/scores.py 调用 | `class V5SignalManager` (line 19) |
| `scripts/v5_strategy.py` | 策略规则引擎：RSI/MACD 条件判断，生成开仓决策 | — |
| `scripts/v5_indicator_engine.py` | 技术指标计算（RSI、MACD、ATR、Chandelier Stop 等）| — |
| `scripts/v5_risk_calculator.py` | V5 风险计算器：仓位大小、止损距离 | — |
| `scripts/v5_params.py` | 策略参数常量 | — |
| `scripts/v5_types.py` | EnrichedItem、Indicators、AIResult 等核心类型定义 | — |
| `scripts/v5_symbol_whitelist.py` | V5_TOP20_WHITELIST — 监控标的白名单（20 个合约）| — |
| `scripts/exchange_factory.py` | get_trader()：根据 DB 配置创建 Binance / OKX trader 实例 | — |
| `scripts/binance_trader.py` | Binance perpetual trader（ccxt 封装）| — |
| `scripts/okx_trader.py` | OKX perpetual trader | — |
| `scripts/m9_knowledge.py` | M9 知识库管理：书籍导入、知识块切片、候选规则 CRUD | — |
| `scripts/m9_validate.py` | M9 候选规则回测验证 | `scripts/m9_validate.py` (line 104) |
| `scripts/setup_performance.py` | refresh_setup_performance()：从 reflections 聚合写 setup_performance | `scripts/setup_performance.py:97` |
| `scripts/risk_constitution.py` | 铁律体检逻辑 | — |
| `scripts/risk_gates.py` | 开仓前风险检查门控 | — |
| `scripts/walkforward.py` | walk-forward 实验主程序（被 api/routes/v5_walkforward.py 作子进程调用）| — |

### scripts/ai/（AI 子系统）

| 模块 | 职责 |
|---|---|
| `scripts/ai/trading_assistant.py` | TradingAssistant：主 AI 客户端（OpenAI / DeepSeek）— `scripts/ai/trading_assistant.py:146` |
| `scripts/ai/reflection_runner.py` | 从已平仓 trade 生成反思，INSERT reflections — `scripts/ai/reflection_runner.py:140` |
| `scripts/ai/confidence_calibration.py` | 预测准确率分桶统计，写 ai_confidence_calibration — `scripts/ai/confidence_calibration.py:44` |
| `scripts/ai/kelly_sizing.py` | Kelly 仓位推荐，写 position_sizing_recommendations — `scripts/ai/kelly_sizing.py:94` |
| `scripts/ai/funding_rate_calculator.py` | 资金费率 Z-score，写 funding_zscore_cache — `scripts/ai/funding_rate_calculator.py:141` |
| `scripts/ai/failure_taxonomy.py` | 读 failure_taxonomy 用于 AI prompt 分类 — `scripts/ai/failure_taxonomy.py:164` |
| `scripts/ai/local_rag.py` | 本地 RAG：从 ai_training_data 检索历史样本 |
| `scripts/ai/setup_aggregator.py` | 每日聚合 reflections → setup_performance_daily — `scripts/ai/setup_aggregator.py:58` |
| `scripts/ai/memory_uploader.py` | 周期把 trade log 上传到 OpenAI Vector Store |
| `scripts/ai/guardrails.py` | AI 决策护栏（仓位上限、亏损熔断等）|
| `scripts/ai/prompt.py` | AI 入场分析 prompt 模板 |
| `scripts/ai/reflection_prompt.py` | 反思生成 prompt 模板 |
| `scripts/ai/setup_type.py` | 交易形态分类（setup type 枚举）|

### scripts/backtest/（实验室）

| 模块 | 职责 |
|---|---|
| `scripts/backtest/runner.py` | walk-forward 切片 + 回测驱动 |
| `scripts/backtest/position_sim.py` | 持仓模拟（SL/TP 触发）|
| `scripts/backtest/kline_fetcher.py` | 历史 klines 拉取 |
| `scripts/backtest/cost_model.py` | 手续费 / 资金费率成本建模 |
| `scripts/backtest/reporter.py` | 输出 JSON 报告 |
| `scripts/backtest/schemas.py` | 回测结果 schema |

---

## 二、前端目录（Rabbit Hunterfronted/）

### 路由（App.tsx）

所有路由挂载在 `Rabbit Hunterfronted/App.tsx`。活跃页面来自 `components/pages-v4/` 和 `components/pages/`，旧版 `/v5/*` 路径均通过 Navigate 重定向至新路径。

### components/pages-v4/（活跃页面，v4 重构后主力 UI）

| 页面文件 | 路由路径 | 职责概述 |
|---|---|---|
| `OverviewPage.tsx` | `/overview` | 账户余额概览 + 持仓汇总 + KPI |
| `DashboardPage.tsx` | `/dashboard` | 主看板：信号列表、持仓、K 线、AI 决策、KPI |
| `CollectPage.tsx` | `/collect` | 市场扫描信号 + 资金费率状态 |
| `AILearningPage.tsx` | `/learning` | AI 反思列表 + 形态表现 + KPI |
| `PortfolioPage.tsx` | `/portfolio` | 活跃持仓管理（平仓操作）|
| `HistoryPage.tsx` | `/history` | 已平仓历史 + 信号历史 |
| `BacktestPage.tsx` | `/backtest` | Walk-forward 实验台 |
| `AuditPage.tsx` | `/audit` | 反思详情 + 失败分类 + 校准 + 形态表现 |
| `DiagnosticsPage.tsx` | `/diagnostics` | AI 状态 + 信号诊断 + 持仓概览 |
| `KnowledgePage.tsx` | `/knowledge` | M9 知识库（书籍 + 候选规则）|
| `MarketPage.tsx` | `/market` | 品种 K 线 + 事件 + 资金费率历史 |
| `ReliabilityPage.tsx` | `/reliability` | 铁律体检 + 资金费率看板 + 持仓安全 |
| `SettingsPage.tsx` | `/settings` | 系统设置（API key + 模式 + AI 配置）|
| `LearningPage.tsx` | `/learning-v2` | 旧版学习页（v4 遗留，路由保留）|

### components/pages/（活跃页面，v5 独立组件）

| 页面文件 | 路由路径 | 职责概述 |
|---|---|---|
| `V5ChartPage.tsx` | `/chart/:symbol` | 品种详情 K 线 + 事件标记 + 资金费率 |
| `V5ManualOrderPage.tsx` | `/manual` | 手动开单（preview + execute）|
| `V5GlossaryPage.tsx` | `/glossary` | 静态术语表（无 API 调用）|

### hooks/api/（TanStack Query 数据层）

| 文件 | 导出函数（主要）| 目标 API |
|---|---|---|
| `useV5ActivePositions.ts` | useV5ActivePositions, useClosePosition | GET /api/v5/positions, GET /api/v5/paper-positions, POST /api/v5/positions/{id}/close |
| `useV5AIStatus.ts` | useV5AIStatus, useV5AIDecisions | GET /api/v5/ai/status, GET /api/v5/ai/decisions |
| `useV5Account.ts` | useAccountBalance | GET /api/v5/account/balance |
| `useV5Constitution.ts` | useConstitution, useIronlawState, useSetupPerformance | GET /api/v5/constitution, GET /api/v5/ironlaw-state, GET /api/v5/setup-performance |
| `useV5Dashboard.ts` | useV5Dashboard | GET /api/v5/signals, GET /api/v5/paper-positions |
| `useV5Funding.ts` | useV5FundingStatus, useV5FundingHistory | GET /api/v5/funding/status, GET /api/v5/funding/history/{symbol} |
| `useV5Klines.ts` | useV5Klines | GET /api/v5/klines/{symbol} |
| `useV5M9.ts` | useM9Books, useM9AddBook, useM9Candidates, useM9AddCandidate, useM9Validate, useM9Approve, useM9Reject | GET/POST /api/v5/m9/books, GET/POST /api/v5/m9/candidates, POST /api/v5/m9/candidates/{id}/validate|approve|reject |
| `useV5ManualOrder.ts` | useV5ManualOrder | POST /api/v5/manual-order/preview, POST /api/v5/manual-order/execute |
| `useV5OrderHistory.ts` | useV5OrderHistory | GET /api/v5/positions?status=CLOSED, GET /api/v5/paper-positions?status=CLOSED |
| `useV5Reflections.ts` | useV5Reflections, useV5FailureTaxonomy, useV5SizingRecommendations, useDecideSizing, useV5SetupPerformance, useV5Calibration | GET /api/v5/reflections, GET /api/v5/failure-taxonomy, GET /api/v5/sizing-recommendations, PATCH /api/v5/sizing-recommendations/{id}, GET /api/v5/setup-performance, GET /api/v5/confidence-calibration |
| `useV5Settings.ts` | useV5Settings（含 patch + testAi mutation）| GET /api/v5/settings, PATCH /api/v5/settings, POST /api/v5/settings/test-ai |
| `useV5Signals.ts` | useV5Signals | GET /api/v5/signals |
| `useV5StrategyConfig.ts` | useV5StrategyConfig（含 patch + preview mutation）| GET /api/v5/strategy-config, PATCH /api/v5/strategy-config, POST /api/v5/strategy-config/preview |
| `useV5SymbolEvents.ts` | useV5SymbolEvents | GET /api/v5/events/{symbol} |
| `useV5TraderKpi.ts` | useV5TraderKpi | GET /api/v5/dashboard/trader-kpi |
| `useV5Walkforward.ts` | useWalkforwardReports, useWalkforwardReport, useRunWalkforward, useWalkforwardJob, useWalkforwardJobs | GET/POST /api/v5/walkforward/reports|run|jobs |

### hooks/（非 API hooks）

| 文件 | 职责 |
|---|---|
| `hooks/useSystemMode.ts` | 从 GET /api/v5/settings 派生 system_mode 字符串 |
| `hooks/useV5WebSocket.ts` | 管理 /ws/v5 WebSocket 连接，更新 TanStack Query 缓存 |

### 其他目录

| 目录 | 职责 |
|---|---|
| `services/api.ts` | apiGet / apiPost / apiPatch / apiDelete fetch 封装，可选 Bearer Token 注入 |
| `components/layout/` | AppShell（导航栏 + 侧边栏）|
| `components/primitives-v3/` | Card、MetricCard、StatusPill、Drawer 等 v3 基础组件 |
| `components/primitives/` | 旧版基础组件（Sparkline 等，部分仍在用）|
| `components/shared/` | 跨页面共享组件 |
| `ui/` | shadcn/ui 基础样式组件 |

---

## 三、真入口

| 入口 | 命令 / 触发 | 职责 |
|---|---|---|
| `python -m scripts.tasks.collector_main` | 手动 or `start_collector.bat` | 主采集流水线 + AI 评分 + 开仓（SHADOW/LIVE 根据 system_settings.system_state 决定）|
| `uvicorn api.main:app` | `start_api.bat` | FastAPI HTTP API + WebSocket /ws/v5 |
| `npm run dev` in `Rabbit Hunterfronted/` | `start_frontend.bat` | 前端 dev server（Vite，代理指向 FastAPI）|

模式决定逻辑：`_resolve_mode_db()` — `scripts/tasks/collector_main.py:32` — 读 `system_settings` 表 key=`system_state`，缺省返回 `"SHADOW"`。

---

## 四、主数据流

```
MarketScanner             DeepCollector                 V5Scorer
scripts/tasks/scanner.py  scripts/tasks/deep_collector.py  scripts/tasks/scorer.py
(class:129)          →    (class:232)               →      (class:436)
     |                          |                               |
exchange REST API         klines + funding                      |
(ccxt/binance/okx)        (movers_queue)                       |
                          enriched_queue                        |
                                                               / \
                                              mode=SHADOW    /     \   mode=LIVE
                                                            /       \
                                              PaperPositionManager     V5PositionManager
                                              paper_position_manager   scripts/v5_position_manager.py
                                              (line 130 INSERT)        (line 44 INSERT)
                                              paper_trades             positions_v5
                                                    |
                     V5Scorer INSERT trade_scores_v5 (scripts/tasks/scorer.py line 151)
                     V5Scorer INSERT ws_event_queue  (scripts/tasks/scorer.py line 40)
                                    |
                          api/main.py:135
                     SELECT ws_event_queue → DELETE → broadcast
                                    |
                             WebSocket /ws/v5
                                    |
                          Frontend hooks (TanStack Query)

V5FundingCollector  → INSERT funding_rates
                      scripts/tasks/v5_funding_collector.py (line 40)

V5PositionMonitor   → SL/TP 触发 → UPDATE paper_trades (scripts/paper_position_manager.py line 225)
scripts/v5_position_monitor.py (line 157)
                               → UPDATE positions_v5 (scripts/v5_position_manager.py line 242) [LIVE]

V5ReflectionWorker  → SELECT reflection_queue (scripts/tasks/v5_reflection_worker.py line 40)
                    → AI 调用
                    → INSERT reflections (scripts/ai/reflection_runner.py:140)
                    → INSERT setup_performance (scripts/setup_performance.py:97)
```

**关键分支点（SHADOW vs LIVE）**：`scripts/tasks/scorer.py:396`

- `mode == "SHADOW"` → `paper_pm.open_position()` → 写 `paper_trades`（`scripts/paper_position_manager.py:130`）
- `mode == "LIVE"` → `live_pm.open_position()` → 走 Broker 真实下单 → 写 `positions_v5`（`scripts/v5_position_manager.py` line 44）

当前 `system_settings` 表中无 `system_state` 键（表内仅 3 行），`_resolve_mode_db()`（`scripts/tasks/collector_main.py:32`）永远返回 `"SHADOW"`。因此 `positions_v5` 当前为 0 行：INSERT 路径存在但从未触发。

---

## 五、DB 表读写路径

**注**：引用格式 `file.py:NNN` 表示已通过 Step-7 脚本验证的精确行号；`(line NNN)` 表示行号已人工核对但因文件名含数字前缀无法被脚本提取，不影响正确性。

| 表 | 写入方 | 消费方 | 当前行数 |
|---|---|---|---|
| `trade_scores_v5` | `scripts/tasks/scorer.py:151` (INSERT) | `scripts/v5_signal_manager.py` (line 27) SELECT | 19,636 |
| `positions_v5` | `scripts/v5_position_manager.py` (line 44) INSERT LIVE 路径未激活；(line 209) UPDATE extend；(line 242) UPDATE close | `api/services/position_service.py:22` SELECT | 0 |
| `paper_trades` | `scripts/paper_position_manager.py:130` INSERT；`:171` UPDATE extend；`:225` UPDATE close | `api/services/position_service.py:48` SELECT | 55 |
| `funding_rates` | `scripts/tasks/v5_funding_collector.py` (line 40) INSERT OR IGNORE | `api/routes/v5_funding.py` (line 59) SELECT | 3,439 |
| `funding_zscore_cache` | `scripts/ai/funding_rate_calculator.py:141` INSERT OR REPLACE | `api/routes/v5_funding.py` (line 26) SELECT | 25 |
| `reflections` | `scripts/ai/reflection_runner.py:140` INSERT | `api/routes/v5_reflection.py` (line 31) SELECT | 41 |
| `setup_performance` | `scripts/setup_performance.py:97` INSERT | `api/routes/v5_constitution.py` (line 136) SELECT | 8 |
| `setup_performance_daily` | `scripts/ai/setup_aggregator.py:58` INSERT OR REPLACE | `api/routes/v5_reflection.py` (line 88) SELECT | 11 |
| `ai_confidence_calibration` | `scripts/ai/confidence_calibration.py:44` INSERT | `api/routes/v5_reflection.py` (line 150) SELECT | 4 |
| `position_sizing_recommendations` | `scripts/ai/kelly_sizing.py:94` INSERT | `api/routes/v5_reflection.py` (line 107) SELECT | 4 |
| `system_settings` | `api/routes/v5_settings.py` (line 37) INSERT OR REPLACE；`api/routes/v5_strategy_config.py` (line 97) INSERT | `scripts/tasks/collector_main.py:40` SELECT（读 system_state）| 3 |
| `failure_taxonomy` | `scripts/local_db.py:974` INSERT OR IGNORE（仅 init 时 seed 一次）| `scripts/ai/failure_taxonomy.py:164` SELECT | 8 |
| `reflection_queue` | `scripts/local_db.py:946` INSERT OR IGNORE（paper_trade 平仓后入队）| `scripts/tasks/v5_reflection_worker.py` (line 40) SELECT | 50 |
| `ws_event_queue` | `scripts/tasks/scorer.py:40` INSERT；`scripts/v5_position_monitor.py` (line 22) INSERT | `api/main.py:135` SELECT→DELETE（广播后消费）| 0 |
| `wf_jobs` | `api/routes/v5_walkforward.py` (line 276) INSERT；(line 187) UPDATE running；(line 246) UPDATE done/failed | `api/routes/v5_walkforward.py` (line 299) SELECT by job_id | 3 |
| `m9_books` | `scripts/m9_knowledge.py` (line 152) INSERT | `scripts/m9_knowledge.py` (line 170) SELECT | 0 |
| `m9_knowledge_chunks` | `scripts/m9_knowledge.py` (line 220) INSERT | `scripts/m9_knowledge.py` (line 210) SELECT content | 1 |
| `m9_candidate_rules` | `scripts/m9_knowledge.py` (line 249) INSERT；`scripts/m9_validate.py` (line 104) UPDATE status | `scripts/m9_knowledge.py` (line 270) SELECT | 0 |
| `ai_training_data` | 无本地 SQLite INSERT；schema 定义 `scripts/local_db.py:119`；Supabase 写入 `scripts/backfill_p3a_match_and_thr.py:146`（一次性回填，已完结）；`scripts/deepseek_ai_learner.py:80` 是 `.select()` 读取而非写入 | `api/routes/v5_ai.py` (line 61) SELECT COUNT | 0 |
| `sqlite_sequence` | SQLite 内部自动维护（AUTOINCREMENT 序列）| — | — |

**说明**：`positions_v5` 为 LIVE 持仓表。INSERT 路径（`scripts/v5_position_manager.py` line 44）存在，但因 `system_settings` 表中无 `system_state` 行，`_resolve_mode_db()`（`scripts/tasks/collector_main.py:32`）永远返回 `"SHADOW"`，故该 INSERT 从未被触发。这是当前 0 行的直接原因。

---

## 六、前端页面 ↔ API endpoint 对应

| 页面（路由） | Hook | API endpoint |
|---|---|---|
| `DashboardPage.tsx`（/dashboard）| useV5Dashboard | GET /api/v5/signals, GET /api/v5/paper-positions |
| `DashboardPage.tsx`（/dashboard）| useV5ActivePositions | GET /api/v5/positions?status=OPEN, GET /api/v5/paper-positions?status=OPEN |
| `DashboardPage.tsx`（/dashboard）| useV5TraderKpi | GET /api/v5/dashboard/trader-kpi |
| `DashboardPage.tsx`（/dashboard）| useAccountBalance | GET /api/v5/account/balance |
| `DashboardPage.tsx`（/dashboard）| useV5Settings / useSystemMode | GET /api/v5/settings |
| `OverviewPage.tsx`（/overview）| useV5TraderKpi | GET /api/v5/dashboard/trader-kpi |
| `OverviewPage.tsx`（/overview）| useV5ActivePositions | GET /api/v5/positions?status=OPEN, GET /api/v5/paper-positions?status=OPEN |
| `OverviewPage.tsx`（/overview）| useV5OrderHistory | GET /api/v5/positions?status=CLOSED, GET /api/v5/paper-positions?status=CLOSED |
| `CollectPage.tsx`（/collect）| useV5Signals | GET /api/v5/signals |
| `CollectPage.tsx`（/collect）| useV5FundingStatus | GET /api/v5/funding/status |
| `AILearningPage.tsx`（/learning）| useV5Reflections, useV5FailureTaxonomy, useV5SetupPerformance | GET /api/v5/reflections, GET /api/v5/failure-taxonomy, GET /api/v5/setup-performance |
| `AILearningPage.tsx`（/learning）| useV5TraderKpi | GET /api/v5/dashboard/trader-kpi |
| `PortfolioPage.tsx`（/portfolio）| useV5ActivePositions | GET /api/v5/positions?status=OPEN, GET /api/v5/paper-positions?status=OPEN |
| `PortfolioPage.tsx`（/portfolio）| useClosePosition | POST /api/v5/positions/{id}/close |
| `BacktestPage.tsx`（/backtest）| useWalkforwardReports | GET /api/v5/walkforward/reports |
| `BacktestPage.tsx`（/backtest）| useRunWalkforward | POST /api/v5/walkforward/run |
| `BacktestPage.tsx`（/backtest）| useWalkforwardJobs, useWalkforwardJob | GET /api/v5/walkforward/jobs, GET /api/v5/walkforward/jobs/{id} |
| `AuditPage.tsx`（/audit）| useV5Reflections, useV5FailureTaxonomy, useV5Calibration | GET /api/v5/reflections, GET /api/v5/failure-taxonomy, GET /api/v5/confidence-calibration |
| `AuditPage.tsx`（/audit）| useV5AIDecisions, useSetupPerformance | GET /api/v5/ai/decisions, GET /api/v5/setup-performance |
| `DiagnosticsPage.tsx`（/diagnostics）| useV5AIStatus, useV5AIDecisions | GET /api/v5/ai/status, GET /api/v5/ai/decisions |
| `DiagnosticsPage.tsx`（/diagnostics）| useV5Signals, useV5ActivePositions, useV5OrderHistory | GET /api/v5/signals, GET /api/v5/positions, GET /api/v5/paper-positions |
| `KnowledgePage.tsx`（/knowledge）| useM9Books, useM9Candidates, useM9AddBook | GET /api/v5/m9/books, GET /api/v5/m9/candidates, POST /api/v5/m9/books |
| `MarketPage.tsx`（/market）| useV5Klines, useV5SymbolEvents, useV5FundingHistory | GET /api/v5/klines/{symbol}, GET /api/v5/events/{symbol}, GET /api/v5/funding/history/{symbol} |
| `ReliabilityPage.tsx`（/reliability）| useConstitution, useIronlawState | GET /api/v5/constitution, GET /api/v5/ironlaw-state |
| `ReliabilityPage.tsx`（/reliability）| useV5FundingStatus, useSystemMode | GET /api/v5/funding/status, GET /api/v5/settings |
| `SettingsPage.tsx`（/settings）| useV5Settings | GET /api/v5/settings, PATCH /api/v5/settings, POST /api/v5/settings/test-ai |
| `V5ChartPage.tsx`（/chart/:symbol）| useV5Klines, useV5SymbolEvents, useV5FundingHistory | GET /api/v5/klines/{symbol}, GET /api/v5/events/{symbol}, GET /api/v5/funding/history/{symbol} |
| `V5ManualOrderPage.tsx`（/manual）| useV5ManualOrder | POST /api/v5/manual-order/preview, POST /api/v5/manual-order/execute |
