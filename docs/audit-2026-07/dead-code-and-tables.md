# Dead Code & Dead Tables · 2026-07

> 生成日期: 2026-07-03
> Git HEAD: 见 README.md 前置条件
> 扫描范围: `scripts/` + `api/` + `data/rabbit_hunter.db` + `strategy_config.json`
> 每条 finding 必须标 **预留** 或 **建议删除** + 1 句理由

---

## 一、DB 表 · 0 行且无活跃 INSERT 路径

### 行数总览（sqlite3 扫描结果）

| 表 | 行数 |
|---|---|
| `positions_v5` | 0 |
| `ai_training_data` | 0 |
| `ws_event_queue` | 0 |
| `m9_books` | 0 |
| `m9_candidate_rules` | 0 |
| `m9_knowledge_chunks` | 1（边界） |

---

### positions_v5

- **行数**: 0
- **INSERT 路径**: `scripts/v5_position_manager.py:44`（存在，代码完整，但从未触发）
- **触发条件**: `_resolve_mode_db()` 返回 `"LIVE"` 时，`V5PositionManager.open_position()` 才执行此 INSERT
- **当前 blocker**: `system_settings` 表中无 `system_state` 键（当前仅 3 行，均为 API 配置），`_resolve_mode_db()`（`scripts/tasks/collector_main.py:40`）缺省返回 `"SHADOW"`，从而只走 `paper_trades`
- **判断**: **预留** — LIVE 交易目标表，INSERT 路径完整，仅等待 `system_settings.system_state='LIVE'` 激活；参见 `architecture-map.md § 五` 中对 SHADOW/LIVE 分支的完整说明
- **建议**: 保留；待 LIVE 升级后将自动填入

---

### ai_training_data

- **行数**: 0
- **INSERT 路径**: 本地 SQLite 无 INSERT 语句；schema 在 `scripts/local_db.py:119` 定义；历史写入路径为 `scripts/deepseek_ai_learner.py:80`，该文件写入的是 **Supabase**（外部云服务），并非本地 SQLite
- **消费方**: `scripts/ai/local_rag.py:55` SELECT COUNT（RAG 检索）；`api/routes/v5_ai.py:61` SELECT COUNT（状态页展示）；两处均永远返回 0
- **Supabase 写入现状**: `scripts/deepseek_ai_learner.py` 属于 V4.2 遗留，依赖 Supabase 客户端，当前 Supabase 断连，且无 V5 代码对其 import
- **判断**: **建议删除** — 本地 SQLite 的 `ai_training_data` 表是空壳；原始数据在 Supabase（断连），RAG 消费方永远命中 0 行，继续保留会在 AI status 页面给出误导性"训练样本 = 0"指标
- **建议**: 删除本地 SQLite 表定义（`scripts/local_db.py:119` 起），同时在 `scripts/ai/local_rag.py` 和 `api/routes/v5_ai.py` 中清除对应 SELECT；如未来重启 RAG，改用 `reflections` 表（已有 41 行）作为来源

---

### ws_event_queue

- **行数**: 0（常驻 0 行，属正常）
- **INSERT 路径 1**: `scripts/tasks/scorer.py:40`（每次评分后推入事件）
- **INSERT 路径 2**: `scripts/v5_position_monitor.py:22`（SL/TP 触发后推入事件）
- **消费方**: `api/main.py:135` 每秒 SELECT 最多 50 行 → 广播 → `DELETE`（`api/main.py:145`）
- **说明**: SELECT→DELETE 环形队列模式导致消费后即清空，常驻 0 行为设计预期
- **判断**: **预留** — 正常工作的临时广播队列，INSERT 和消费路径均完整，0 行是消费速度快于生产的正常结果

---

### m9_books

- **行数**: 0
- **INSERT 路径**: `scripts/m9_knowledge.py:152`（前端调 POST /api/v5/m9/books 触发）
- **消费方**: `scripts/m9_knowledge.py:170` SELECT（列出书籍）；`api/routes/v5_m9.py` 路由完整
- **说明**: M9 知识库功能在 v0.5.x 中完整实现，用户尚未导入任何书籍
- **判断**: **预留** — 功能路径完整，等待用户通过 `/knowledge` 页面导入首本书

---

### m9_candidate_rules

- **行数**: 0
- **INSERT 路径**: `scripts/m9_knowledge.py:249`（对 m9_books 中的内容提取候选规则后写入）
- **说明**: 上游依赖 `m9_books`；`m9_books` 为空，故候选规则无从生成
- **判断**: **预留** — 依赖 `m9_books` 行存在方可生成，当前为级联空状态；路径完整

---

### m9_knowledge_chunks（1 行边界）

- **行数**: 1
- **INSERT 路径**: `scripts/m9_knowledge.py:220`（书籍入库后切片写入）
- **说明**: 1 行为测试或首次小批导入残留；随书籍正式入库自动增长
- **判断**: **预留** — 数据极少但路径完整，随 m9_books 填充自然增长

---

## 二、代码 · 无调用者的模块

> 扫描方法：对 `scripts/*.py`（含 `scripts/tasks/`），在 `scripts/` `api/` 下全量 grep
> `(from|import).*<模块名>`，排除自身；命中 0 则列入候选，再人工核查是否为
> 独立 CLI 工具（有 `if __name__ == '__main__'` + 无 Supabase 依赖）。

---

### 建议删除组（Supabase 时代遗留，当前断连）

#### scripts/ai_learning_loop.py

- **版本标记**: V4.2 AI 自动学习循环
- **外部依赖**: Supabase（`strategy_config.json`、`ai_auto_tuner.py`）
- **现状**: 无任何 V5 代码对其 import；Supabase 已断连
- **判断**: **建议删除** — V4.2 Supabase 调优循环，V5 已由 `scripts/ai/reflection_runner.py` + `v5_reflection_worker.py` 替代学习路径

#### scripts/backfill_p3a_match_and_thr.py

- **版本标记**: V4.0 一次性回填脚本
- **外部依赖**: Supabase
- **现状**: docstring 明确说明为历史 `ai_training_data` 回填，已执行完毕
- **判断**: **建议删除** — 一次性历史 Supabase 回填任务，已完结，无再运行价值

#### scripts/binance_position_sync.py

- **版本标记**: V4.5
- **外部依赖**: Supabase；无 `__main__`（不可独立运行）
- **现状**: 无调用方，被 `scripts/v5_position_monitor.py` 替代
- **判断**: **建议删除** — V4.5 Supabase 持仓同步，已被 V5 的 `v5_position_monitor.py` 完整替代

#### scripts/clear_open_positions.py

- **版本标记**: 测试网运维工具
- **外部依赖**: Supabase
- **现状**: 仅用于测试网已平仓但 DB 遗留 OPEN 状态时的清理，依赖 Supabase
- **判断**: **建议删除** — 测试网一次性清理工具，依赖 Supabase（断连）；V5 本地 SQLite 若需清理可直接用 `sqlite3` 命令操作

#### scripts/compute_rewards.py

- **版本标记**: V4.0 强化学习准备
- **外部依赖**: Supabase（读写 `ai_training_data`）
- **现状**: V5 未引入强化学习 reward 体系
- **判断**: **建议删除** — V4.0 Supabase reward 计算，V5 策略优化通过反思+walkforward 进行，此文件无接入点

#### scripts/data_quality_check.py

- **版本标记**: V4.2 数据质量检查
- **外部依赖**: Supabase
- **现状**: 验证 P-State/ATR 入 Supabase，已无目标数据
- **判断**: **建议删除** — V4.2 Supabase 数据质量脚本，当前断连且 V5 无对应 P-State 概念

#### scripts/execute_sql_with_key.py

- **版本标记**: Supabase 管理工具
- **外部依赖**: Supabase REST API
- **现状**: 通过 Supabase API key 执行 SQL，无 V5 调用方
- **判断**: **建议删除** — Supabase 管理工具，外部服务断连，V5 直接操作本地 SQLite

#### scripts/execution_guard.py

- **版本标记**: V4.0 反身性压制引擎
- **外部依赖**: Supabase；无 `__main__`
- **现状**: 无 V5 代码 import，反身性逻辑未在 V5 引入
- **判断**: **建议删除** — V4.0 Supabase 护栏逻辑，V5 风险管控由 `scripts/risk_gates.py` 担当

#### scripts/monitor_deepseek.py

- **版本标记**: Supabase 时代 DeepSeek 监控
- **外部依赖**: Supabase（读 `ai_training_data`）
- **现状**: V5 AI 状态监控已由 `api/routes/v5_ai.py` + `/diagnostics` 页面替代
- **判断**: **建议删除** — Supabase 时代遗留，V5 已有等价监控端点

#### scripts/position_stats.py

- **版本标记**: V4 持仓统计
- **外部依赖**: Supabase
- **现状**: 无 V5 调用方，V5 持仓统计由 `api/routes/v5_trader_kpi.py` 提供
- **判断**: **建议删除** — V4 Supabase 持仓统计，V5 前端已有等价 KPI 看板

#### scripts/report_paper_trades.py

- **版本标记**: V4.0 paper_trades 报表
- **外部依赖**: Supabase
- **现状**: 拉取 Supabase `paper_trades`；V5 本地 SQLite `paper_trades` 已有 55 行，V5 前端可直接查询
- **判断**: **建议删除** — V4 Supabase 报表工具，V5 本地 DB + 前端已替代

#### scripts/verify_and_setup.py

- **版本标记**: Supabase 连接验证
- **外部依赖**: Supabase
- **现状**: 验证 Supabase 连接并帮助设置数据库，V5 用本地 SQLite
- **判断**: **建议删除** — Supabase 连接验证工具，V5 迁移本地 SQLite 后已无使用场景

#### scripts/deepseek_ai_learner.py

- **版本标记**: V4.2 AI 学习器
- **外部依赖**: Supabase（`ai_training_data` 的唯一写入者，但写入 Supabase 而非本地 SQLite）
- **现状**: `scripts/local_db.py:119` 的 `ai_training_data` 本地 SQLite 表因此永远为 0 行；无 V5 代码 import 此文件
- **判断**: **建议删除** — V4.2 Supabase AI 学习器，是 `ai_training_data`（本地 SQLite 0 行）问题的根源；V5 学习路径已由 `reflection_runner.py` + `local_rag.py` 负责

---

### 预留组（独立 CLI 工具，有 V5 本地 SQLite 交互，无调用方属正常）

#### scripts/check_live_readiness.py

- **功能**: SHADOW → LIVE 升级硬门槛自动检查
- **外部依赖**: 无 Supabase；读本地 SQLite
- **判断**: **预留** — 升级 LIVE 模式前的一次性验收工具，独立运行属设计意图，保留供上线前使用

#### scripts/test_binance_api.py

- **功能**: 验证币安测试网 API Key/Secret 是否有效
- **外部依赖**: 无 Supabase；Binance API 直连
- **判断**: **预留** — 交易所连接验证工具，随环境迁移可能复用，体积小、低风险

#### scripts/verify_auto_trading.py

- **功能**: 检查自动交易相关环境变量配置
- **外部依赖**: 无 Supabase；env-only
- **判断**: **预留** — 环境配置快速诊断工具，无副作用，保留供运维使用

#### scripts/verify_v5_acceptance.py

- **功能**: V5 SHADOW 24h 验收测试，输出通过/不通过
- **外部依赖**: 无 Supabase；读本地 SQLite（`ai_training_data`、`paper_trades`、`trade_scores_v5`）
- **判断**: **预留** — V5 24h 验收脚本，设计为独立运行，与本地 DB 交互；无调用方属正常

---

### 预留组（低置信度，建议 owner 确认）

#### scripts/cvd_analyzer.py

- **功能**: CVD（累计成交量差）分析
- **外部依赖**: 无 Supabase；无 `__main__`
- **现状**: 未发现任何 import；V5 评分器（`scripts/tasks/scorer.py`）未使用 CVD 指标
- **判断**: **预留** — 低置信度，建议 owner 确认；CVD 分析模块无已知调用路径，但不依赖 Supabase，若为未来指标储备则保留

#### scripts/golden_wick_detector.py

- **功能**: 金针形态（下影线 > 60% K 线全长）检测
- **外部依赖**: 无 Supabase；无 `__main__`
- **现状**: 未发现任何 import；`scripts/v5_strategy.py` 中无对此模块的引用
- **判断**: **预留** — 低置信度，建议 owner 确认；可能为 V5 策略形态识别储备，若无引入计划可删除

---

### 预留组（已明确标注为遗留兼容层）

#### scripts/tasks/paper_monitor.py

- **功能**: 任务级 paper 持仓轮询（更新价格、触发 SL/TP）
- **现状**: 无调用方；`architecture-map.md § 一` 已明确记录"已被 v5_position_monitor 替代，保留兼容"
- **判断**: **预留** — 现有代码明确保留作兼容层；如确认 `v5_position_monitor.py` 功能完整覆盖，可升级为建议删除

---

## 三、strategy_config.json · 无读取的字段

> 背景说明：`strategy_config.json` 是 V4.2 参数文件，仅被 `scripts/ai_auto_tuner.py`
> （经 `load_strategy_config()`）读取，后者属于 Supabase 时代遗留（无 V5 调用方）。
> V5 活跃流水线的参数全部存储于 `system_settings` 表，通过 `scripts/v5_params.py` 热读；
> `strategy_config.json` 与 V5 active pipeline 无任何交集。

---

### ai_judge_threshold

- **文件中的值**: `0.65`
- **代码命中数**: 0（在 `scripts/` 和 `api/` 全量 grep，包括 V4.2 文件在内，无一命中）
- **说明**: 即使在唯一消费 `strategy_config.json` 的 `ai_auto_tuner.py` 中也未读取此字段（`scripts/ai_auto_tuner.py:162` 起只读 `atr_multiplier_*`、`structure_gap_threshold` 等，不含 `ai_judge_threshold`）
- **判断**: **建议删除** — 0 命中，V4.2 配置文件中的孤立字段，连其唯一消费者 `ai_auto_tuner.py` 都不读取

---

### 其余 9 个字段（仅在 V4.2 孤立代码中有命中）

| 字段 | 值 | 命中文件 | 性质 |
|---|---|---|---|
| `atr_multiplier_p2` | 2.5 | `scripts/time_machine.py:23`，`scripts/ai_auto_tuner.py:162` | V4.2 孤立 |
| `atr_multiplier_p3a_early` | 2.5 | `scripts/time_machine.py:24`，`scripts/ai_auto_tuner.py:163` | V4.2 孤立 |
| `atr_multiplier_p3a_normal` | 2.0 | `scripts/time_machine.py:25`，`scripts/ai_auto_tuner.py:164` | V4.2 孤立 |
| `atr_multiplier_p3b` | 1.5 | `scripts/time_machine.py:26`，`scripts/ai_auto_tuner.py:165` | V4.2 孤立 |
| `structure_gap_threshold` | 0.02 | `scripts/time_machine.py:27`，`scripts/ai_auto_tuner.py:166` | V4.2 孤立 |
| `phase_age_max_candles` | 100 | `scripts/time_machine.py:28`，`scripts/ai_auto_tuner.py:167` | V4.2 孤立 |
| `context_gate_required` | true | `scripts/time_machine.py:29` | V4.2 孤立 |
| `golden_wick_bypass_structure` | true | `scripts/time_machine.py:30` | V4.2 孤立 |
| `risk_per_trade` | 0.015 | `scripts/time_machine.py:97` | V4.2 孤立（V5 用 `v5_risk_per_trade` 键，见 `scripts/v5_params.py:29`） |

- **判断**: **预留** — 上述 9 个字段的所有命中均在 V4.2 孤立文件（`ai_auto_tuner.py` + `time_machine.py`）中，与 V5 活跃流水线无关；一旦 Section 二中的建议删除组（`ai_learning_loop.py`、`ai_auto_tuner.py` 及 `time_machine.py` 的调用链）被清理，这 9 个字段及整个 `strategy_config.json` 可一并删除

---

## 四、汇总

| 类别 | 预留 | 建议删除 | 合计 |
|---|---|---|---|
| DB 表（含 1 行边界）| 5 | 1 | 6 |
| 代码模块 | 7 | 13 | 20 |
| Config 字段 | 9 | 1 | 10 |
| **合计** | **21** | **15** | **36** |

### 优先处理建议

1. **高优先级（立即可删）**: Section 二中的"建议删除组"（13 个 Supabase 时代脚本）— 均无 V5 调用方且外部服务断连，删除无功能风险
2. **配套操作**: 删除 `ai_training_data` 本地 SQLite 表（Section 一 finding），同步清理 `scripts/ai/local_rag.py:55` 和 `api/routes/v5_ai.py:61` 的无效 SELECT
3. **后续跟进**: `strategy_config.json` 整体（Section 三）在 Supabase 孤立脚本删除后可随之清除
4. **低优先级**: `scripts/tasks/paper_monitor.py`、`scripts/cvd_analyzer.py`、`scripts/golden_wick_detector.py` — 需 owner 确认后决定

---

*tech-debt.md 将引用本文档的 "dead path" 结论；LIVE 模式 `positions_v5` 未激活的完整机制详见 `architecture-map.md § 五`。*
