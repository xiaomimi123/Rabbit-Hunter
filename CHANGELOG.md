# Rabbit Hunter 更新日志

---

## v0.5.x-dev — v0.5.0 之后的持续迭代（205 commits）
**日期区间**: 2026-06-08 → 2026-07-03

> 这一段没有正式 release tag，是 v0.5.0 之后累积的所有变更。
> 按 conventional commit type 分组，同类里按主题聚簇。
> 完整 git log: `git log ad19ca1..HEAD`
> 窗口截点: 生成于 2026-07-03 Phase 1 结束时 (HEAD=9101699)。同期 doc-vs-code-diff.md 记录的 "190 commits" 是 Phase 0 生成时的快照，两者相差 15 条自身生成的 docs commits，不矛盾。

### feat（103 条）

#### 前端基础架构（设计系统 + 骨架 + hooks）
- `ac02120` feat(frontend): V5 types.ts mirroring backend Pydantic schemas
- `637c862` feat(frontend): design tokens + Tailwind + base CSS, drop V4.3 orphans
- `7796ae1` feat(frontend): Zustand UI store (no server state)
- `6207b31` feat(frontend): typed fetch wrapper + ApiError + interceptor bus
- `33f3acd` feat(frontend): /ws/v5 client hook + system-mode mirror
- `d040292` feat(frontend): 10 React-Query hooks for V5 endpoints
- `273891f` feat(frontend): primitives (Card/Badge/ProgressBar/GaugeArc/Modal/Slider/NumberInput/LoadingSkeleton/Toast/ErrorBoundary/Select/VirtualList)
- `1d592ff` feat(frontend): shared composites (gauges/kpi/funnel/decisions/position)
- `3626689` feat(frontend): IndicatorOverlayChart (Lightweight Charts main + RSI + MACD)

#### 前端页面（V5 初版）
- `2ae9b3b` feat(frontend): AppShell + Sidebar + TopBar + routing + placeholders
- `6711927` feat(frontend): V5SignalsPage + V5SignalHistoryPage
- `a2c97ff` feat(frontend): V5ActivePositionsPage + V5OrderHistoryPage
- `31b91ef` feat(frontend): V5DashboardPage + V5AIStatusPage
- `5d0bb0d` feat(frontend): V5StrategyConfigPage + V5SettingsPage
- `daaa2ac` feat(frontend): V5ManualOrderPage + V5ChartPage
- `6ed160a` feat(dashboard): 24h 胜率分项 (by side / strategy / exit reason)
- `ec7864c` feat(frontend): glossary tooltips on jargon + /v5/glossary page
- `fa7a895` feat(chart): synchronized crosshair across K/RSI/MACD + hover data row

#### UI 视觉重设计（V2 → V3 → Field Instrument）
- `0df24d3` feat(ui v2): BacktestPage 实验台 + Overview 回撤监控区 + walkforward POST API
- `ba605de` feat(ui): 把 4 个 V2 有用页面接入 V3，Sidebar 主导航扩到 8 项
- `a1b9f27` feat(ui): V3 UI 原型落地 — 4 页面重写 + 宪法签名条 + 模式指示器
- `7c1c51d` feat(ui): 交易员中控 Dashboard + Field Instrument tokens 全面落地
- `0aa5c83` feat(UI): 侧栏精简 6 项 + 仪表盘 OKX 资产 + 修复 BacktestPage TypeError

#### V5 核心引擎（指标 / 评分 / 仓位 / 数据采集）
- `7639c78` feat(db): V5 schema + drop V4.3/V4.4 tables
- `a9b9a89` feat(v5): pure indicator engine (RSI/MACD/ATR + calculate_indicators)
- `cd65404` feat(v5): AND-conjunction strategy decider
- `a333cec` feat(v5): risk calculator (SL/TP/size from ATR + risk budget)
- `ac4d0a5` feat(v5): DeepCollector pulls 15m+4h klines, filters |ΔP|>3%
- `3dd4a71` feat(v5): AI layer adapted to V5 types
- `b162384` feat(v5): PaperPositionManager with 15min soft target + indicator snapshot
- `fa481ad` feat(v5): position monitor — 30s polling with exit triggers
- `d906545` feat(v5): LIVE V5PositionManager with fail-closed SL/TP rollback
- `3a4a48b` feat(v5): scorer rewritten as pure V5 pipeline glue
- `e004317` feat(v5): API rename to /api/v5/* + V5SignalManager
- `bdcdb70` feat(v5): preflight check + healthcheck loop
- `9aa764f` feat(v5): DeepSeek adapter + deep_collector stat fix + dead-script cleanup
- `9fac54c` feat(v5): v5_params hot-reload layer + integrate 6 modules
- `4a5c32a` feat(v5): DeepSeek-friendly local RAG-lite

#### API 服务层（REST + WebSocket）
- `8239f70` feat(api): V5 Pydantic schemas for Plan B routes
- `92d026d` feat(api): /api/v5/strategy-config GET/PATCH/preview
- `bc98376` feat(api): /api/v5/settings GET/PATCH
- `6d73cdf` feat(api): /api/v5/ai/status + /decisions
- `f9ed5df` feat(api): /api/v5/klines/{symbol} + /events/{symbol}
- `e085c5a` feat(api): /api/v5/manual-order preview + execute
- `73cf39b` feat(api): POST /api/v5/positions/{id}/close
- `8ee0f5f` feat(ws): /ws/v5 broadcast + cross-process event bus

#### 交易所接入 + 配置管理
- `096505f` feat(exchange): pluggable market-data source — Binance/OKX backends via EXCHANGE env
- `8b90c75` feat(exchange): OkxTrader + exchange_factory + frontend active-exchange badge
- `4c02019` feat(config): unified Exchange + AI configuration with DB-backed persistence
- `d414d10` feat(shadow): make SHADOW mode a real paper-trading loop, end-to-end
- `5802c57` feat(settings): AI connection test endpoint + button
- `31a70e4` feat(ai): make SettingsPage AI config actually wire up + auto-upload memory

#### 策略规则 + 门控 + 参数调优
- `b3e4c3f` feat(paper config): 应用最优出场 — max_hold=240min + SIGNAL_REVERSE 30min 最短门槛
- `ff9d454` feat(params): v5_max_extensions default 3 → 30 (paper 一周观察验证 α 方向)
- `9adeb8f` feat(check): --start-date flag for trial cutoff date
- `5dd0ac4` feat(scanner+whitelist): 100M USDT mover floor + XAU exclude + drop MATIC
- `7cf55b2` feat(whitelist): 扩展高流动性白名单到 25 个 (+6 加密主流)
- `a1eb7bd` feat(strategy): 加 macd_reversal_long mode (Variant B 实验落地)
- `cc8f46b` feat(strategy): funding anti-pile filter + backtest sim bug fix
- `cba2d08` feat(strategy): live scorer passes funding_z to decide() for filter activation
- `a7e0d6f` feat(v5.1): top-20 USDT perp whitelist filter (default on)
- `a4cb4c3` feat(v5.1): trend_aligned strategy mode (Plan C) — default
- `1adb63c` feat(safety): SHADOW → LIVE promotion hard gates + auto-check script
- `6fcbef4` feat(gates): SHADOW/LIVE-aware expected-return threshold
- `3121a46` feat(M9): 策略书籍知识层 + 候选规则审核闸门
- `b533d8a` feat(M3/M8 frontend): 宪法 + setup_performance 透明化
- `2297b93` feat(M8): setup_performance 自动剪枝 + 运行时禁用清单
- `da4d291` feat(M5): RR 硬锁 + Chandelier 移动止损
- `7413601` feat(M3): 阶段0立宪 + 铁律层硬断言

#### Funding Rate（v6 资金费率体系）
- `967476b` feat(v6): reflection card + dashboard setup breakdown 显示 funding
- `10e9e11` feat(v6): AI Status FundingHeatmapCard
- `2281570` feat(v6): GET /api/v5/funding/status + /history/{symbol}
- `1d7c1ec` feat(v6): reflection 集成 funding_z_score_at_entry
- `92afd73` feat(v6): trading_assistant 注入 funding context 到 AI prompt
- `b183ebf` feat(v6): failure_taxonomy 真正用上 funding_z_score
- `4a2f4e5` feat(v6): scorer 注入 funding_z_score → trade_scores_v5
- `9922a13` feat(v6): setup_type 派生 funding_extreme_* 分支
- `d961472` feat(v6): V5FundingCollector worker + z-score calculator
- `c3c4886` feat(v6): OKX public funding API client + symbol mapping
- `0b7d0d0` feat(v6): DB schema for funding_rates + zscore_cache + ALTER
- `1a9098f` feat(funding): compute_zscore_as_of for backtest historical replay

#### AI 复盘 / 学习闭环（Reflection Worker）
- `c43bb09` feat(reflection): Phase 3 APIs + frontend Tab 3 + AI calibration curve
- `e69c8f6` feat(reflection): fractional Kelly sizing engine + weekly cron
- `48de020` feat(reflection): AI confidence calibration
- `2aed5b4` feat(reflection): daily aggregator by setup_type + worker cron
- `3d848c2` feat(reflection): GET /failure-taxonomy + Tab 2 (失败模式分布)
- `c5f17ca` feat(reflection): trading_assistant veto on failure_taxonomy match
- `9e8b079` feat(reflection): failure_taxonomy matcher with 8 handlers
- `158c90f` feat(reflection): failure_taxonomy 表 + 8 种子模式
- `26b5a7a` feat(reflection): GET /api/v5/reflections + 复盘工作台 Tab 1
- `7071041` feat(reflection): V5ReflectionWorker 进程 + enqueue 集成
- `94ba7c6` feat(reflection): runner — load context → AI → validate → persist
- `c4eb04d` feat(reflection): 5 问 prompt builder + Pydantic schemas
- `3f32918` feat(reflection): DB schema (reflection_queue + reflections) + setup_type 派生

#### 数据 / 回测 / 实验台
- `a8113be` feat(backtest): requests + larger retry budget, README, 30d baseline
- `2bf0134` feat(backtest): CLI entry point
- `7a0acee` feat(backtest): reporter + aggregator
- `f69b3d6` feat(backtest): BacktestRunner orchestration loop
- `6c51b71` feat(backtest): schemas + position_sim
- `c4edefb` feat(backtest): kline_fetcher with OKX history + JSON disk cache
- `69382b3` feat(M6): 写实成本模型 + walk-forward + 前端报告查看
- `dac27ff` feat(experiment): 出场对照实验 (维加斯通道 vs 固定 ATR 倍数)
- `49f450c` feat(experiment): MACD 进场时机对照实验 + 22→17 symbol 双 OOS 验证

### fix（34 条）
- `a1cbb72` fix(KnowledgePage): 加"导入书籍" UI Modal — 后端早就有但前端没暴露
- `fc40ca8` fix(audit HIGH-1+2): v5_position_manager 三阶段状态机 + ERROR_RECONCILE_NEEDED
- `7187aeb` fix(audit HIGH-3,4): OkxTrader fail-closed + AIResult.error_kind 枚举
- `e5b6de2` fix(collector): _system_mode 是 ghost call，改为 _resolve_mode_db
- `4f1e80d` fix(constitution): SHORT/risk/leverage 默认值对齐宪法 + 杠杆反推
- `f396ccc` fix(KnowledgePage): ValidateModal still read sync ValidationResult fields after async refactor
- `de6101d` fix(scorer): SHADOW mode pass-through on AI infra errors (DeepSeek 余额不足)
- `f415179` fix(M9 + scorer): WF 验证异步化 + 扫描开关实时生效
- `20bcc00` fix(HeaderBar): scope symbol selector + price block to symbol-aware routes only
- `5e250f8` fix(MarketPage): normalize symbol for funding/signal lookup
- `44330fc` fix(okx encoder): tolerate slash format for binance_symbol_to_okx_inst
- `ffce6f1` fix(HeaderBar): bump kline limit 2 → 10 to satisfy backend ge=10 validator
- `45eea56` fix(M6 CLI): handle None profit_factor in print format
- `a664418` fix(klines/events): URL-encode slash → underscore to match backend route
- `90e2d64` fix(network): retry wrapper around all OKX HTTP calls in live pipeline
- `67549f2` fix(ai): TradingAssistant hot-reload key + DB-first DeepSeek (no more stale clients)
- `68c2aff` fix(manual-order): URL params are 'symbol' and 'side', not Chinese keys
- `ca39709` fix(collector): silence fetch_balance noise in SHADOW + move trial config to env
- `9e4b03f` fix(backtest): manual urllib retry + skip missing OKX instruments
- `77362bb` fix(api+ui): raise signals limit to 5000; Settings save feedback
- `4b4cfbc` fix(v5.1): deep_collector also enriches top-20 each cycle (not just movers)
- `7f1a549` fix(reflection): enqueue reflection after manual /positions/:id/close
- `b5aaea6` fix(v5): manual orders survive SIGNAL_REVERSE in position monitor
- `8bb81a5` fix(frontend): align types/hooks/pages with actual API shape
- `d1fa459` fix(nginx): proxy /ws/v5 to api:8000 for V5 WebSocket upgrade
- `46d7ebb` fix(v5): hot-fixes from first SHADOW startup
- `b18e974` fix(v5): quick_yes_no should await AsyncOpenAI client directly
- `08789da` fix(features): make range_left ATR fallback unconditional
- `8d77b9a` fix(timezone): make DB timestamps UTC-aware end-to-end
- `d1be9fd` fix(kill-board): expose 4D scores + AI fields, switch UI to Chinese
- `1e76ff9` fix(scanner): rank by USDT quote volume, not token count
- `a256b2c` fix(shadow): make paper KPI a credible signal of live performance
- `84a31b3` fix(routing): apiInterceptor double-prefix + add missing /system-state endpoint
- `061a833` fix(deadcode): revive 4 API endpoints — kill-queue / anatomy / entry-validator / scores

### experiment（5 条）
> 实验条目保留证伪 / 采纳结论。
- `20e5bca` experiment(BTC trend-follow): 用户复审 — max_hold/SL/TP grid + 独立期验证 → 证伪加固 (证伪)
- `98c4fa1` experiment(M9 候选): BTC 顺势 Pine 翻译 + 4 组 wf 对照 → 证伪 (证伪)
- `3531a42` experiment: max-hold 6 档扫描 — 找到甜蜜点 = 240 min (PF 顶 + 周转最快) (采纳)
- `0780a69` experiment: max-hold 时间窗对照 — 找到 paper PF 0.77 vs backtest 2.08 主因 (进行中)
- `035d68a` experiment(backtest): funding z-score threshold 2.0 vs 1.5 (revert) (证伪)

### docs（29 条）
- `2d092ac` docs(structure): §七 §九 加回 architecture-map 反向引用
- `2ccfaef` docs(structure): 刷新 PROJECT_STRUCTURE.md 对齐 v0.5.x → HEAD
- `98d0516` docs: 合并 docs/project-structure.md 独有段落到 PROJECT_STRUCTURE.md 并删除重复
- `68242ac` docs(audit): fix D-R7 range + D-R9 count + D-P5 orders_history clarity
- `8d6a2dc` docs(audit): doc-vs-code-diff — Phase 1 的 shopping list
- `8b13b24` docs(audit): tech-debt Finding 8 snippet 加回 try: 行避免误读为语法错
- `9f68064` docs(audit): dead-code § 二 deepseek_ai_learner 与 § 一 保持一致
- `8cbb9db` docs(audit): tech-debt — findings + CONFIRMED/PLAUSIBLE + failure scenarios
- `6df98cd` docs(audit): fix ai_training_data write-path citation across Task 2+3 + note strategy_config dup
- `a4f6403` docs(audit): dead-code-and-tables — 0 行表 + 无调用者模块 + 未读 config 字段
- `c8578e6` docs(audit): fix KnowledgePage hooks + refresh funding_rates count
- `42dc896` docs(plan): fix existence-check regex to include digits
- `ff32991` docs(audit): architecture-map — 后端/前端目录 + 数据流 + DB 读写路径
- `e247ef1` docs(audit): 体检目录 + index 骨架
- `d894917` docs(plan): 项目全面体检 + 开发文档刷新 implementation plan
- `9385ee1` docs(spec): 项目全面体检 + 开发文档刷新 design (Phase 0/1/2)
- `c0f3721` docs: 加项目结构 + 设计优化接缝指南
- `168e6b3` docs: SHADOW trial contract for exp3b 2-week verification
- `843e103` docs: UI design brief for AI generation
- `43f54d9` docs(v6): funding rate phases 1-6 implementation plan (12 tasks, ~44 BE tests)
- `1165342` docs(v6): funding rate design spec
- `43a9415` docs(reflection): Phases 1-3 implementation plan (14 tasks, ~65 BE tests)
- `9811a6e` docs(reflection): Reflection Worker design spec
- `2fee7b7` docs(v5): Plan B-2 frontend implementation plan (17 tasks)
- `a6c8d0c` docs(plan): V5 Plan B-1 backend implementation plan
- `cd34b79` docs: V5 frontend rebuild + AI learning loop design (Plan B)
- `6479699` docs(plan): V5 backend rebuild implementation plan
- `290bfa8` docs: V5 RSI-MACD 15min rebuild design
- `2c383c5` docs: add project structure overview

### chore（8 条）
- `1c3304a` chore(sidebar): 移除深链区"中控仪表 V2"和"手动开单"入口
- `261ca60` chore: 死代码 Phase 1 清理 (-26 文件) + 审计报告
- `600fdd9` chore(v6): verify_v5_acceptance covers Funding Phases 1-6 schema
- `47c0e37` chore(reflection): verify_v5_acceptance covers Phases 1-3 schema
- `c3f7b89` chore(v5): verify_v5_acceptance covers Plan B-2 frontend dist
- `168b86c` chore(frontend): wipe V4.3, scaffold V5 skeleton, add deps
- `47e93ed` chore(v5): verify_v5_acceptance covers Plan B-1 schema
- `2b9c017` chore(v5): SHADOW 24h acceptance script

### test / refactor（2 条）
- `d98b764` test: bootstrap pytest infra + V5 shared types
- `7b83ff8` refactor(v5): physically delete V4.3/V4.4, rewire collector_main

### 其他 / misc（24 条，非标准 type）
- `3ccc848` style(ui): sweep 剩 3 个 live 页面到 Field Instrument tokens
- `ac3f852` style(ui): pages-v4 11 个页面 sweep 到 Field Instrument tokens
- `20735df` ui(v4): 1:1 architectural port from cryptoquant-ai reference
- `07e40c4` ui(v3): convert all remaining 10 pages to cryptoquant-ai style
- `e734081` ui(v3-sample): redesign V5SignalsPage as dense data table
- `8964a25` ui(v3-sample): Dashboard sample in cryptoquant-ai style (zinc + indigo)
- `e0b9786` ui+ai: switch to system fonts; translate English labels; reflection in Chinese
- `1cf3b26` spec+plan: backtest engine MVP (CLI, 8 tasks)
- `d4147ba` ui(v2): Phase 7+8 — V5GlossaryPage + final cleanup
- `8c0b321` ui(v2): Phase 7.1 — V5SettingsPage + V5ManualOrderPage
- `0f5c740` ui(v2): Phase 6.4 — V5StrategyConfigPage rewrite
- `4babe30` ui(v2): Phase 6.3 — V5ChartPage + IndicatorOverlayChart re-skin
- `06b6d56` ui(v2): Phase 6.2 — V5OrderHistoryPage + V5SignalHistoryPage
- `c09f878` ui(v2): Phase 6.1 — V5ReflectionPage rewrite (3 tabs)
- `bed28ff` ui(v2): Phase 5.3 — V5SignalsPage rewrite
- `c2c157c` ui(v2): Phase 5.2 — V5AIStatusPage rewrite, kill HoloCard
- `03ace09` ui(v2): Phase 5.1 — V5ActivePositionsPage + ActivePositionCard
- `1e21b28` ui(v2): Phase 4 — V5DashboardPage rewrite (flagship)
- `1cb5a0a` ui(v2): Phase 3 primitives — Card/Badge/KpiCard/ProgressBar/etc
- `3e738ab` ui(v2): Phase 2 shell — Sidebar + TopBar + AppShell
- `6908a7b` ui(v2): Phase 1 foundation — fonts + tokens + Tailwind + CSS + Aperture
- `9c447e8` plan: V2 Field Instrument UI migration (23 tasks, 8 phases)
- `22aa696` design(v2): add ActivePositions + AIStatus preview pages
- `dea9232` design(v2): Field Instrument visual direction + Dashboard preview

---

## v0.5.0 — 安全 + 正确性 + 学习闭环（v45 大检修）
**日期**: 2026-06-07

> 本次释出是对整个代码库的一次系统性体检 + 修复，覆盖 12 个独立工作单元、
> 30+ 文件改动、~80 个新增/迁移测试。如果你之前在跑 v5.1 或更早版本，
> **强烈建议先在测试网跑通 v0.5.0 再切实盘** —— 多个默认行为发生了改变。

### 行为变化一句话总结

| 维度 | v5.1 | v0.5.0 |
|---|---|---|
| AI 不可用时 | 默认放行交易 | **默认跳过** (`AI_FAIL_OPEN=false`) |
| SL/TP 挂单失败 | 仓位裸奔 | **立即回滚平仓** (`SL_TP_FAIL_OPEN=false`) |
| 平仓顺序 | DB 先 / broker 后 | **broker 先 / DB 后**（broker 失败 DB 保 OPEN 让重试）|
| sync API blip | 全部仓位标 CLOSED → 再开 → 仓位翻倍 | **三道防线**：异常分类 + bulk-blip 检测 + 连续 N 次缺失才关闭 |
| SHORT 入场 | 数学错（chandelier/funding/router/risk）默认开启 | **数学修正 + 默认关闭**（显式 `ENABLE_SHORT_TRADING=true` 才入场）|
| API 默认绑定 | `0.0.0.0:8000`（暴露到 LAN）| `127.0.0.1:8000` + 可选 bearer 鉴权；非本机绑定无 token 启动**拒绝** |
| `/docs` | 公开 | 默认关闭 (`API_ENABLE_DOCS=true` 开启) |
| AI 学习记忆 | log_trade_result 零调用 → Vector Store 永远空 | **平仓自动写 JSONL** → memory_uploader 上传 → AI 真能查到 |
| `trade_scores_v43` | `UNIQUE(symbol)` + `INSERT OR IGNORE` → 每个币只存首条 | UNIQUE 去掉、append-only 时序，索引补齐 |
| `ai_training_data` 表 | 不存在 → scorer 每次写"no such table"静默失败 | **建表 + 索引** + scorer 端 ImportError 修复 |
| collector 入口 | `scripts/collector.py` (2670 行) vs `scripts/tasks/collector_main.py` 并存 | 唯一入口 `scripts.tasks.collector_main`；旧的删除归档 |
| 本地 LR judge | 默认开（未训练时输出噪声）| 默认关 + DEPRECATED 横幅 |
| backtest 策略层 | 读 DB 里写好的 `strategy_score` (replay) | **重新执行当前 `route_strategy()`** —— 改 router 直接反映 |
| backtest 退出判定 | 稀疏 snapshot.price，3% wick 被漏掉 → winner bias | **逐 15m bar 检查 high/low** 精确触发 |
| 订单层 | broad `@retry` + 无幂等键 + closePosition+amount 互斥被拒 | `_safe_create_order()` 统一封装：precision + clientOrderId + reduceOnly |
| requirements | 全部 `>=`，openai 未列 | 全部 `==`，**openai 锁 1.54.5**（防 vector_stores beta 迁移）|
| 前端 Dashboard / OrderPage | 用死的 `useV43Store` shim → 永远空 | 接入真实 React Query，引入 ConfirmModal |
| 前端 UI 风格 | gaming neon glow | "简约高级" 单 accent + hairline |

---

### 12 个工作单元 & 提交

| # | 主题 | Commit | 关键测试 |
|---|---|---|---|
| 1 | fail-open 反转（AI/SL-TP/close）| `0f058e1` | guardrails 6 + 角色路径 7 + smoke |
| 2 | `_safe_create_order` 统一订单层 | `0f058e1` | 9 个订单边界测试 |
| 3 | SHORT kill switch + `lowest_price` 列 | `0f058e1` | 7 个迁移 + 数据库测试 |
| 4 | sync blip 三道防线 | `0f058e1` | 9 个 blip 场景测试 |
| 5 | API bearer 鉴权 + localhost + docs gating | `b29b18c` | 10 个 require_auth + 5 个结构检查 |
| 6 | AI 学习闭环 + `ai_training_data` 表 | `89322c6` | 9 个端到端学习闭环测试 |
| 7 | collector + AI judge 收敛 | `89322c6` | 编译 + import 安全检查 |
| 8 | 前端 Dashboard/OrderPage 复活 + UI 焕新 | `be483eb` | vite build 1.04s 通过 |
| 9 | WebSocket bearer 鉴权（query token） | `b4ea093` | 7 个 WS 鉴权测试 |
| 10 | requirements 锁版本 + openai 补齐 | `f52301d` | — |
| 11 | SHORT 端到端数学修正 | `8812bf2` | 9 个 SHORT/funding/router/risk 测试 |
| 12 | backtest 对齐 live router + OHLC 退出判定 | `1cc77b0` + 本 release | 4 + 8 个 backtest 测试 |

加上本 release 的"收尾批"：

| # | 主题 | 内容 |
|---|---|---|
| ★ | 前端 `apiGet/apiPost` 注入 `Authorization: Bearer` | `services/apiInterceptor.ts` 读 `VITE_API_TOKEN`，401 时给开发者清晰提示 |
| ★ | WebSocket 断线 UI banner | store 加 `wsStatus`，Layout 顶栏在 reconnecting/failed 时显示警告条 |
| ★ | backtest exit price 用 OHLC bar.high/low（消除 winner bias） | 新增 `_fetch_klines_range` + `_bar_hits_exit_*`，同 bar 双触发悲观假设 SL 先触 |
| ★ | 删 `scripts/_legacy_collector.py` | git rm，stub `scripts/collector.py` 已经接管 |
| ★ | Docker 化部署 | `Dockerfile` + `Rabbit Hunterfronted/Dockerfile` + `docker-compose.yml` + `nginx.conf` + `.dockerignore` + `.env.example` |

---

### Docker 快速启动

```bash
git clone https://github.com/xiaomimi123/Rabbit-Hunter.git
cd Rabbit-Hunter
cp .env.example .env
# 编辑 .env — 至少填 BINANCE_API_KEY/SECRET（BINANCE_TESTNET=true 默认）

docker compose up -d
# 浏览器访问 http://localhost:5173
```

**栈内部**：

```
┌─────────────────────────────────────────────────┐
│  ports 127.0.0.1:5173  →  frontend (nginx)       │
│                         ↳ /api/* 反代到 api      │
│                         ↳ /ws/v43 反代到 api     │
│  ports 127.0.0.1:8000  →  api    (FastAPI)       │
│                                                  │
│  (no port)             →  collector (主循环)     │
│                                                  │
│  共享 ./data/ volume：SQLite + ai_trade_log.jsonl │
└─────────────────────────────────────────────────┘
```

**安全姿态**：

- 端口默认绑 host loopback `127.0.0.1` —— LAN 无法访问
- 容器内 API 必须绑 `0.0.0.0`（Docker 端口转发硬要求）→ `API_ALLOW_REMOTE_NO_AUTH=true` 显式放行
- 要开放到 LAN：(1) 改 compose 端口为 `"0.0.0.0:5173:80"`；(2) `.env` 里设
  `API_BEARER_TOKEN=$(openssl rand -hex 32)`（compose 会自动同步到前端 `VITE_API_TOKEN`）

---

### 新增环境变量索引

| 变量 | 默认 | 说明 |
|---|---|---|
| `AI_FAIL_OPEN` | `false` | AI 不可用时是否仍交易（推荐 false）|
| `SL_TP_FAIL_OPEN` | `false` | SL/TP 挂不上时是否保留仓位（推荐 false）|
| `ENABLE_SHORT_TRADING` | `false` | 是否允许 SHORT 入场（数学已修，仍建议测试网先验）|
| `BINANCE_SYNC_REQUIRED_MISSES` | `2` | 连续多少次 sync 缺失才关闭仓位 |
| `BINANCE_SYNC_GRACE_SECONDS` | `60` | 新仓位多久内免疫 sync 关闭 |
| `BINANCE_SYNC_BLIP_MIN_POSITIONS` | `2` | bulk-blip 检测的最小 OPEN 仓位数 |
| `API_BIND_HOST` | `127.0.0.1` | uvicorn 绑定地址 |
| `API_PORT` | `8000` | API 端口 |
| `API_BEARER_TOKEN` | (空) | 设了 → 所有 HTTP/WS 路由强制 `Authorization: Bearer` |
| `API_ENABLE_DOCS` | `false` | 是否开 `/docs` `/redoc` `/openapi.json` |
| `API_ALLOW_ORIGINS` | localhost 默认 | CORS allowlist 逗号分隔 |
| `API_ALLOW_REMOTE_NO_AUTH` | `false` | 远端绑定 + 无 token 的逃生阀（Docker 用）|
| `AI_JUDGE_ENABLED` | `false` | 本地 LR judge（deprecated）|
| `VITE_API_TOKEN` | (空) | 前端 bundle 内的 bearer token —— 必须与 `API_BEARER_TOKEN` 一致 |
| `AI_TRADE_LOG_PATH` | `data/ai_trade_log.jsonl` | AI 学习日志路径 |

---

### Supabase 用户的迁移步骤

如果你的部署在用 Supabase（而不是默认 SQLite），需要手动执行：

```bash
psql "$SUPABASE_URL" -f scripts/v45_short_kill_switch_migration.sql
```

SQLite 用户什么都不用做，下次 `get_connection()` 自动迁移。

---

### 已知未修（明示，不在 v0.5.0 范围）

- `v43_anatomy_analyzer.py` / `v43_kill_queue_manager.py` 还有 pre-existing 的
  `from v43_score_calculator import calculate_scores` 引用（实际函数名是
  `aggregate_score`）—— 影响 AnatomyPanel 和部分 kill-queue 路径
- ErrorBoundary.tsx / WeightHistory.tsx / vitest.config.ts 有 pre-existing TS 错误
  （不阻断 vite build）
- backtest 现在用 OHLC 检查退出触发，但 `account_balance` 仪表 / equity curve
  逻辑还需要更细致测试

---

## v5.1 — 本地化重构（SQLite + UI 修复）
**日期**: 2026-03-13

### 核心改动：Supabase → 本地 SQLite

彻底移除对 Supabase 云数据库的依赖，改用本地 SQLite 文件存储，实现零网络延迟读写。

#### 新增文件

| 文件 | 说明 |
|------|------|
| `scripts/local_db.py` | SQLite 核心模块：建表、Supabase 兼容接口、自动清理 |
| `data/rabbit_hunter.db` | 运行时自动创建的本地数据库文件 |

#### `scripts/local_db.py` 核心特性

- **Supabase 兼容接口**：`.table().select().eq().order().limit().execute()`，所有路由代码无需修改
- **WAL 模式**：支持采集器写入与 API 读取并发，不互相阻塞
- **JSON 自动序列化**：dict/list 字段自动转换为 JSON 字符串存储
- **自动清理策略**（每次采集器启动时执行）：

| 数据表 | 保留策略 |
|--------|---------|
| `trade_scores_v43` | 保留最新快照（UPSERT，始终只有 20 行） |
| `positions_v43` | OPEN 永久保留，CLOSED 保留 90 天 |
| `market_snapshot` | 保留 7 天 |
| `ai_weights_v43` | 保留 90 天 |
| `paper_trades` | 保留 90 天 |

预计长期运行数据库文件大小：**30-50 MB**

#### 修改文件

**`scripts/tasks/writer.py`**
- `_supabase_write_worker` → `_sqlite_write_worker`
- `DatabaseWriter` 保留相同队列接口（`safe_enqueue`、`start`、`stop`），内部改为写入 LocalDB
- 保留 `supabase=` 参数名以兼容旧调用，实际已不使用

**`api/dependencies.py`**
- 新增 `get_db()` → 返回 `LocalDB` 单例
- `get_supabase()` / `get_supabase_optional()` 均改为返回 `LocalDB`（向后兼容，路由无需修改）
- Supabase 初始化改为静默忽略（不影响启动）

**`scripts/tasks/collector_main.py`**
- 移除 `init_supabase()` 调用
- 改为 `get_local_db()` 初始化数据库
- 启动时自动执行 `prune_old_data()` 清理过期数据
- `DatabaseWriter` 不再需要传入 `supabase` 参数
- 打印信息更新：`[INFO] 本地 SQLite 数据库已就绪`

---

### Bug 修复

#### 后端

**`api/routes/positions.py`** — 平仓接口参数错误
- 修复 `close_position()` 调用参数名：`reason=` → `exit_reason=`
- 修复缺少必填参数 `exit_price`：优先从 Binance 获取市价，兜底从 DB 取 `current_price`
- 此 bug 导致所有「平仓」和「一键平仓」操作均静默失败（500 错误）

**`api/routes/system.py`** — 账户余额端点
- `get_account_balance` 依赖从 `get_supabase` 改为 `get_supabase_optional`
- 之前 Supabase 失败时返回 500，前端只处理 404，导致余额永远不显示

**`scripts/tasks/deep_collector.py`** — `ccxt_symbol` 字段缺失
- `_collect_one` 构建的 `metrics` dict 补充 `ccxt_symbol` 字段
- `binance_symbol_to_ccxt_symbol(binance_symbol)` 已有工具函数，直接复用
- 此 bug 导致所有评分处理报 `KeyError: 'ccxt_symbol'`

**`scripts/tasks/scorer.py`** — `ccxt_symbol` 兜底
- `item["ccxt_symbol"]` 改为 `item.get("ccxt_symbol") or symbol`，避免未来重现

**`start_api.bat`** — 引用不存在的测试脚本
- 删除 `%PY_CMD% test_api_start.py` 调用（文件在 v5.0 清理时被删除）
- 此 bug 导致后端启动流程在环境测试步骤卡住，uvicorn 从未真正启动

#### 前端

**`Rabbit Hunterfronted/components/KillBoard.tsx`** — `TypeError: Cannot read properties of undefined (reading 'icon')`
- 错误原因：`useMemo` 中的启发式判断错误，当 `first.final_score === undefined` 时返回未经 `transformRaw` 处理的原始数据，导致 `item.riskLabel` 为 `undefined`，`RISK_STYLE[undefined]` 崩溃
- 修复：移除启发式判断，`useMemo` 始终对原始数据调用 `transformRaw`
- 防御：渲染处加 `?? RISK_STYLE['BLOCK']` 兜底

**`Rabbit Hunterfronted/services/api.ts`** — 账户余额错误处理
- `accountAPI.getBalance` 改为所有错误均静默返回 `null`（原来只忽略 404）

---

### 持仓管理页面优化

**`Rabbit Hunterfronted/components/PositionsPage.tsx`**

新增/优化显示内容：

| 列 | 改动 |
|----|------|
| 开仓 / 现价 | 分标签显示，现价带方向箭头 ↗/↘，颜色区分盈亏，显示相对开仓涨跌幅 |
| 止损 / 止盈（原「止损距离」） | SL 红色 + 价格 + 距现价 %；TP 绿色 + 价格 + 距现价 %；中间进度条显示当前价格在 SL↔TP 区间中的位置 |
| 规模 / 杠杆 | 更清晰显示张数、杠杆倍数、保证金 USDT |
| 统计栏 | 已显示账户余额、可用余额（需后端正常响应） |

---

## v5.0 — OpenAI AI 决策层 + 项目整理
**日期**: 2026-03-13

### 新增：OpenAI AI 决策层 (`scripts/ai/`)

在规则引擎（SNIPER/VULTURE）之上增加 GPT-4o 二次审查层，实现真正的 AI 自主交易决策。

| 文件 | 说明 |
|------|------|
| `scripts/ai/__init__.py` | 模块入口 |
| `scripts/ai/trading_assistant.py` | OpenAI Assistants API 核心，每个信号创建独立 Thread |
| `scripts/ai/guardrails.py` | 硬规则限幅：SL 1.2–3.0×、TP 2.0–6.0×、size 0.3–1.2×，最低 1.5:1 风险收益比 |
| `scripts/ai/prompt.py` | GPT System Prompt，描述策略背景和决策规范 |
| `scripts/ai/memory_uploader.py` | 交易结果写入 JSONL + 上传 Vector Store（学习闭环） |
| `scripts/ai/setup_assistant.py` | 一次性初始化工具，创建 Assistant + Vector Store |

**AI 决策流程：**
```
规则引擎评分 → AI 审查 → execute_trade() / skip_trade() → 下单
                ↑
        Vector Store (历史交易记录，持续学习)
```

**Guardrails 规则（AI 无法突破）：**
- SL: 1.2× — 3.0× ATR
- TP: 2.0× — 6.0× ATR，且 TP ≥ SL × 1.5
- 仓位: 0.3× — 1.2×
- 超时 20 秒自动降级到规则引擎默认值

---

### 修改：后端集成

**`scripts/v43_position_manager.py`**
- 新增 `take_profit_atr_multiplier` 字段支持

**`scripts/tasks/scorer.py`**
- `StrategyScorer.__init__` 新增 `openai_assistant` 参数
- `_process_v43` 改为 `async def`（修复 await 语法错误）
- AI 决策结果注入 `v43_decision_result`

**`scripts/tasks/collector_main.py`**
- 新增 `_init_openai_assistant()` 异步函数
- 通过环境变量 `OPENAI_AI_ENABLED` 控制 AI 层开关

**`api/routes/system.py`**
- 新增 `GET /api/v43/openai-status`
- 新增 `POST /api/v43/openai-memory/upload`

---

### 修改：前端 UI

**`Rabbit Hunterfronted/components/Layout.tsx`** — 完整重写为左侧边栏布局
- TopBar（48px）：折叠按钮、Logo、SNIPER/VULTURE 策略徽章、影子/实盘模式切换
- Sidebar（220px 展开 / 64px 折叠）：分组导航（交易 / AI 系统 / 系统）、底部系统状态指示灯
- 使用 `useSystemStatus` hook 实时显示采集器和 API 状态

**`Rabbit Hunterfronted/App.tsx`**
- 移除所有 Feature Flag 判断，所有页面直接渲染
- 删除 `FeatureFlagsPanel` 相关代码

**`Rabbit Hunterfronted/components/AIStatus.tsx`** — 完整重写
- 4 个信息卡片：OpenAI Assistant 状态 / Vector Store 记忆统计 / AI 决策流程 / Guardrails 规则
- 胜率进度条、一键上传记忆按钮

**`Rabbit Hunterfronted/components/KillBoard.tsx`**
- 展开区新增「OpenAI 决策」区块

**`Rabbit Hunterfronted/types.ts`**
- `KillBoardItem` 新增：`aiReasoning`、`aiSlMultiplier`、`aiTpMultiplier`

---

### 新增环境变量

```env
OPENAI_API_KEY=sk-...
OPENAI_AI_ENABLED=true
OPENAI_TRADING_MODEL=gpt-4o
OPENAI_DECISION_TIMEOUT=20
OPENAI_ASSISTANT_ID=asst_xxx
OPENAI_VECTOR_STORE_ID=vs_xxx
AI_TRADE_LOG_PATH=data/ai_trade_log.jsonl
AI_MEMORY_MAX_TRADES=300
```

---

### 文档与脚本整理

- 删除 `docs/` 目录（130+ 个旧版文档）
- 删除根目录旧 MD：`REVIEW_REPORT_v5.md`、`SETUP_ENV.md`、`STARTUP_GUIDE.md`
- 删除 37 个过时脚本（所有 `run_v44_*`、`debug_*`、`diagnose_*`、`test_*`）
- 重写 `README.md` 为 v5.0 完整说明文档

---

## v4.5 — 前端重构（React Query）
**日期**: 2026-02

- 引入 `@tanstack/react-query` v5，替代 Zustand 管理服务端状态
- 新增 `hooks/useKillQueue.ts`、`usePositions.ts`、`useWeights.ts`、`useSystemStatus.ts`
- 重写 `KillBoard.tsx`（~200行）、`PositionsPage.tsx`（~150行）
- 新增 UI 原子组件：`Badge.tsx`、`PnlDisplay.tsx`、`ScoreBar.tsx`、`LoadingSkeleton.tsx`
- TailwindCSS 引入 trading terminal 主题色彩系统

---

## v4.4 — 策略路由升级
**日期**: 2026-01

- 新增 `scripts/v44_strategy_router.py`：SNIPER / VULTURE 双策略路由
- OI 变化统一为百分比形式（始终 ÷100 转为小数）
- 新增动态配置缓存（5分钟）

---

## v4.3 — 四维评分系统
**日期**: 2025-12

- 新增四维评分体系：结构 / 波动 / 情绪 / 操控
- `scripts/v43_position_manager.py` 持仓管理（含 Chandelier Exit 动态止损）
- API 层从 `api/main.py` 拆分为 `api/routes/`、`api/schemas/`、`api/services/`
- 采集层从 `scripts/collector.py` 拆分为 `scripts/tasks/`
