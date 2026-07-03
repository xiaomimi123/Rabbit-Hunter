# Doc vs Code Diff · 2026-07

> 每条 diff 是 Phase 1 doc 修改的一个 shopping-list 条目。
> 格式: `<doc-path>:<line>` + doc 现说法 + 当前代码事实 + 建议改法
> 生成日期: 2026-07-03
> 覆盖: README.md / PROJECT_STRUCTURE.md / CHANGELOG.md / docs/project-structure.md
> 不含: docs/experiment retros、code-audit-report.md、risk-constitution-audit.md、ui-design-brief-*、visual-design-v2/、readme-vs-code-diff.md（历史存档，设计上允许过时）

---

## 一、README.md

### D-R1. collector.py "已归档" 说法失真
- **位置**: `README.md:10`
- **doc 说**: "旧的 `scripts/collector.py` 已归档，直接运行会打印 deprecation 信息并退出。"
- **实际**: `scripts/collector.py` 不存在（`ls scripts/collector.py` 返回 "No such file or directory"）。v0.5.0 时该文件曾作 stub 保留，此后被彻底删除，不存在任何 deprecation 横幅。
- **建议**: 删除该句，或改为"旧的 `scripts/collector.py` 已彻底删除"。

### D-R2. system.py 模式切换接口已删除
- **位置**: `README.md:61`
- **doc 说**: "模式状态持久化在 `system_settings` 表，可通过 `api/routes/system.py` 暴露的接口在线切换。"
- **实际**: `api/routes/system.py` 不存在（`ls api/routes/` 无此文件）。模式切换现由 `api/routes/v5_settings.py` 的 PATCH `/api/v5/settings` 接口提供（`architecture-map.md` §一 routes 节）。
- **建议**: 改为"可通过 `api/routes/v5_settings.py` 的 PATCH `/api/v5/settings` 接口在线切换（key: `enable_auto_trading` / `system_mode`）"。

### D-R3. 核心模块表中 v44/v43 脚本已不存在
- **位置**: `README.md:89`
- **doc 说**: "| `v44_strategy_router.py` | SNIPER / VULTURE 路由 |"
- **实际**: `scripts/v44_strategy_router.py` 不存在（`ls scripts/v44*` 仅返回 .sql 文件）。路由逻辑已迁移至 `scripts/v5_strategy.py`（三 mode: and_strict / trend_aligned / macd_reversal_long）。
- **建议**: 将本行替换为"| `v5_strategy.py` | 三 mode 策略规则引擎（and_strict / trend_aligned / macd_reversal_long）|"

### D-R4. 核心模块表中 v43_position_manager.py 已删除
- **位置**: `README.md:90`
- **doc 说**: "| `v43_position_manager.py` | 持仓管理 |"
- **实际**: `scripts/v43_position_manager.py` 不存在。持仓管理现由 `scripts/v5_position_manager.py`（LIVE）和 `scripts/paper_position_manager.py`（SHADOW）承担（`architecture-map.md` §一 scripts 节）。
- **建议**: 将本行替换为两行："| `v5_position_manager.py` | LIVE 持仓管理（开仓 / 止损 / 回滚）|" 和 "| `paper_position_manager.py` | SHADOW 虚拟持仓管理 |"

### D-R5. "四个异步任务"数量过时
- **位置**: `README.md:81`
- **doc 说**: "| `tasks/collector_main.py` | v45 唯一入口，启动四个异步任务 |"
- **实际**: `scripts/tasks/collector_main.py:335-348` 的 `coroutines` 列表包含 7-8 个协程（scanner、deep_collector、scorer、monitor、_healthcheck_loop、reflection_worker、funding_collector，以及可选的 memory_uploader）。
- **建议**: 改为"v45 唯一入口，启动 7+ 个异步协程（scanner / scorer / monitor / reflection_worker / funding_collector 等）"

### D-R6. API 路由表含三个已删除文件
- **位置**: `README.md:121`
- **doc 说**: "| `system.py` | SHADOW↔LIVE 切换、交易所状态、healthz |"（同表 `README.md:124` weights.py、`README.md:125` market.py）
- **实际**: `api/routes/system.py`、`api/routes/weights.py`、`api/routes/market.py` 均不存在（`ls api/routes/` 确认）。这三个 v4.3 遗留路由在 v5 重构后被删除。
- **建议**: 删除这三行。healthz 现在 `api/main.py` 中直接注册；模式切换改由 `v5_settings.py`；权重/市场相关功能已合并到 `v5_strategy_config.py` 或无专用端点。

### D-R7. API 路由表缺 v5_trader_kpi.py
- **位置**: `README.md:119-137`
- **doc 说**: 列出 17 个路由文件（含 3 个已删除的 v4.3 文件），无 `v5_trader_kpi.py`
- **实际**: `api/routes/v5_trader_kpi.py` 存在，提供 GET `/api/v5/dashboard/trader-kpi`，是 DashboardPage 和 OverviewPage 的 KPI 数据主源（`architecture-map.md` §一、§六）。
- **建议**: 在路由表补充一行"| `v5_trader_kpi.py` | KPI 中控（PF / Sharpe / MaxDD / 宪法违规 / AI 健康度）|"

### D-R8. 前端路由表缺 /overview 路由
- **位置**: `README.md:145-161`
- **doc 说**: 路由表从 `/dashboard` 起始，无 `/overview` 条目
- **实际**: `Rabbit Hunterfronted/App.tsx:25` 将根路径 `/` 重定向至 `/overview`；App.tsx:27 注册了 `OverviewPage`（账户余额概览 + 活仓汇总 + KPI）。`/overview` 是系统实际的默认首页，不经过 `/dashboard`。
- **建议**: 在路由表首行添加"| `/overview` | 账户概览（资产 / 活仓汇总 / KPI，为根路径 `/` 的重定向目标）|"

### D-R9. /v5/* 重定向行号引用错误
- **位置**: `README.md:163`
- **doc 说**: "旧路径 `/v5/*` 全部重定向到新路径（`App.tsx:42-53`）"
- **实际**: `Rabbit Hunterfronted/App.tsx:42-43` 是 `/manual` 和 `/glossary` 的活跃路由，不是重定向。`/v5/*` 重定向段实为 `App.tsx:46-57`（含 11 条 Navigate 重定向 + 1 条活跃 v5/chart route），另有 App.tsx:58 的通配符重定向至 /dashboard）。
- **建议**: 改为"（`App.tsx:46-57`）"

---

## 二、PROJECT_STRUCTURE.md

### D-P1. 文档版本头部过时
- **位置**: `PROJECT_STRUCTURE.md:3`
- **doc 说**: "> 版本：v0.5.x · 最后更新：2026-06-08"
- **实际**: v0.5.0 发布于 2026-06-07；此后 190+ commits，架构已大幅演进（v5 策略引擎、风控宪法、Walk-Forward 实验台等）。
- **建议**: 改为"版本：v0.5.x → v5（当前） · 最后更新：2026-07"，并在 Phase 1 刷新时同步正文内容。

### D-P2. 目录骨架含四个已删除的 v4x 脚本
- **位置**: `PROJECT_STRUCTURE.md:79-82`
- **doc 说**: 目录树列出 `v43_score_calculator.py`、`v43_position_manager.py`、`v44_strategy_router.py`、`v41_structure_analyzer.py`
- **实际**: 四个文件均不存在（`ls scripts/v43* scripts/v44* scripts/v41*` 仅返回 .sql 迁移文件）。替代者为 `v5_strategy.py`、`v5_position_manager.py`、`v5_risk_calculator.py`、`v5_indicator_engine.py`（`architecture-map.md` §一 scripts 节）。
- **建议**: 删除这四行，补充 v5 体系核心文件（见 architecture-map.md §一）。

### D-P3. 目录骨架中 backtest_paper_trades.py 已删除
- **位置**: `PROJECT_STRUCTURE.md:83`
- **doc 说**: "│   ├── backtest_paper_trades.py  # 回测框架"
- **实际**: `scripts/backtest_paper_trades.py` 不存在。回测引擎已重构为 `scripts/backtest/` 子目录（runner.py / cost_model.py / reporter.py / kline_fetcher.py / position_sim.py / schemas.py；`ls scripts/backtest/` 确认）。
- **建议**: 将该行替换为"│   ├── backtest/               # M6 回测引擎子包（runner / cost_model / reporter 等）"并适当展开。

### D-P4. 前端目录树列的所有 V2 组件文件均已不存在
- **位置**: `PROJECT_STRUCTURE.md:89-99`
- **doc 说**: `components/` 下直接列有 `Layout.tsx`、`KillBoard.tsx`、`PositionsPage.tsx`、`OrderPage.tsx`、`Dashboard.tsx`、`AIStatus.tsx`、`TradeScores.tsx`、`StrategyConfig.tsx`、`WeightHistory.tsx`、`TradingViewChart.tsx`、`AnatomyPanel.tsx`（11 个文件）
- **实际**: 以上 11 个文件均不存在（`find "Rabbit Hunterfronted/components" -name "*.tsx" | sort` 共 52 个文件，无上述任何一个）。`components/` 现含子目录 `layout/`、`pages-v4/`（14 页）、`pages/`（3 页）、`primitives-v3/`、`primitives/`、`shared/`。
- **建议**: 将本段替换为当前目录结构（见 architecture-map.md §二 components 节）。

### D-P5. 数据流图 DB 表名为 v43 时代旧名
- **位置**: `PROJECT_STRUCTURE.md:152-154`
- **doc 说**: 数据流图标注 DB 表名 `trade_scores_v43`、`positions_v43`、`orders_history`
- **实际**: 实际表名为 `trade_scores_v5`（19,636 行）、`paper_trades`（55 行）/ `positions_v5`（0 行 LIVE 路径）；`orders_history` 不在 architecture-map.md 的 19 张关键表中。
- **建议**: 将数据流图中三处表名改为 `trade_scores_v5`、`paper_trades` / `positions_v5`；orders_history 无对应替代表 —— 删除该节点标注（或替换为 ws_event_queue：架构图的消息队列节点）。

### D-P6. §5.2 + §5.3 引用已删除模块 + SNIFFER 不复存在
- **位置**: `PROJECT_STRUCTURE.md:191`
- **doc 说**: "§5.2 评分系统（V4.3）：`scripts/v43_score_calculator.py` —— 四维加权"
- **实际**: `scripts/v43_score_calculator.py` 不存在；评分逻辑现在 `scripts/tasks/scorer.py`（V5Scorer）+ `scripts/v5_strategy.py`（`architecture-map.md` §一）。
- **建议**: 将 §5.2 标题和主体改为描述 V5Scorer + v5_strategy.py 的三 mode。

### D-P7. §5.3 SNIFFER 策略在 v5 不存在
- **位置**: `PROJECT_STRUCTURE.md:202`
- **doc 说**: "`scripts/v44_strategy_router.py` 根据评分 + 市场结构选择策略"，含 SNIFFER 潜伏者（P2 吸筹，opt-in）
- **实际**: `scripts/v44_strategy_router.py` 不存在；`scripts/v5_strategy.py` 实现三 mode（and_strict / trend_aligned / macd_reversal_long），无 SNIFFER 概念（`grep -n "SNIFFER" scripts/v5_strategy.py` 无输出）。
- **建议**: 将 §5.3 改为描述 v5_strategy.py 的 three-mode 架构，删除 SNIFFER 相关行。

### D-P8. §5.5 持仓管理引用已删除文件
- **位置**: `PROJECT_STRUCTURE.md:228`
- **doc 说**: "| 持仓管理 | `v43_position_manager.py` | OPEN→CLOSING→CLOSED 状态机、Chandelier Exit 动态止损 |"
- **实际**: `scripts/v43_position_manager.py` 不存在。LIVE 持仓由 `scripts/v5_position_manager.py` 管理，SHADOW 持仓由 `scripts/paper_position_manager.py` 管理（`architecture-map.md` §一 scripts 节）。
- **建议**: 将本行拆为两行：v5_position_manager.py（LIVE）和 paper_position_manager.py（SHADOW）。

### D-P9. §5.6 API 路由表路径前缀错误且含删除文件
- **位置**: `PROJECT_STRUCTURE.md:237`
- **doc 说**: 路由前缀均为 `/api/v43/...`；列出 `routes/weights.py`（/api/v43/weights）、`routes/market.py`（/api/v43/market）、`routes/system.py`（/api/v43/system）、`websocket_server.py`（/ws/v43）
- **实际**: 所有活跃路由使用 `/api/v5/` 前缀；`weights.py`、`market.py`、`system.py` 三文件已删除；主 WebSocket 端点为 `/ws/v5`（`api/websocket_v5.py`），`/ws/v43` 是 legacy stub（`architecture-map.md` §一 api 节）。
- **建议**: 完整替换 §5.6 路由表，参见 architecture-map.md §一 api/routes 节。

### D-P10. §6.2 WebSocket 路径为旧 v43 端点
- **位置**: `PROJECT_STRUCTURE.md:277`
- **doc 说**: "ws://api/ws/v43?token=..."
- **实际**: 主 WebSocket 端点为 `/ws/v5`（`api/websocket_v5.py`）；`/ws/v43` 是 V4.3 legacy stub（`api/websocket_server.py`），architecture-map.md 标注"已 stub"。
- **建议**: 改为"ws://api/ws/v5?token=..."

### D-P11. §七 DB 表名全为 v43 时代旧名
- **位置**: `PROJECT_STRUCTURE.md:294`
- **doc 说**: 列出 `trade_scores_v43`、`positions_v43`、`orders_history`、`ai_training_data`、`market_snapshot`、`ai_weights_v43`
- **实际**: 实际 19 张关键表包括 `trade_scores_v5`、`paper_trades`、`positions_v5`、`reflections`、`system_settings`、`funding_rates`、`ws_event_queue` 等；`orders_history`、`market_snapshot`、`ai_weights_v43` 均未出现在 architecture-map.md §五 的当前 schema 中。
- **建议**: 完整替换 §七 DB 表，参见 architecture-map.md §五（19 张表含写入方/消费方/当前行数）。

### D-P12. 目录骨架缺失 v5 核心模块与 backtest/ experiments/ 子目录
- **位置**: `PROJECT_STRUCTURE.md:37-113`
- **doc 说**: `scripts/` 目录树无 `backtest/`、`experiments/` 子目录；无 `v5_strategy.py`、`v5_risk_calculator.py`、`v5_params.py`、`v5_types.py`、`v5_indicator_engine.py`、`risk_gates.py`、`risk_constitution.py`、`v5_symbol_whitelist.py`、`v5_position_monitor.py`
- **实际**: `ls scripts/v5* scripts/risk* scripts/backtest/ scripts/experiments/` 确认上述文件和目录均存在（`architecture-map.md` §一 scripts 节）。
- **建议**: 刷新目录树，删除 v4.x 文件项，补充 v5_* 模块（至少 9 个）及 backtest/、experiments/ 子目录（分别含 6 和 1 个文件）。

---

## 三、CHANGELOG.md

### D-C1. v0.5.0 之后无任何条目——190 commits 缺口
- **位置**: `CHANGELOG.md:376`
- **doc 说**: 停在 v0.5.0（2026-06-07），为 CHANGELOG.md 最后一行
- **实际**: v0.5.0 tag（commit ad19ca1）到当前 HEAD（8b13b24）共 190 commits（feat 103 / fix 34 / docs 14 / chore 8 / experiment 7 / test 1 / refactor 1）。其中包含 M9 知识层、Walk-Forward 实验台、风控宪法 7 条、v5_strategy 三 mode、Field Instrument UI 等多个重大功能。
- **建议**: 在 CHANGELOG.md 末尾添加 `## v0.5.1 → HEAD (WIP)` 章节，按类型分组列主要变更。具体内容由 Phase 1 Task 8 负责补写，不在本 task 范围。

---

## 四、docs/project-structure.md

> **整体建议**: 本文件按 Phase 1 Task 6 计划合并进根目录 `PROJECT_STRUCTURE.md` 后删除。
> Phase 1 执行时需保留的独有内容（根目录文档缺失但此文有的段落）：
>
> | 段落 | 约略行范围 | 价值 |
> |---|---|---|
> | §5.1 视觉系统 "Field Instrument" token 表（颜色 + 语义 + 字间距）| docs/project-structure.md:254-271 | 前端改样式唯一参考 |
> | §7 风控宪法 7 条详细表（常量 / 执行点 / API 暴露）| docs/project-structure.md:319-330 | 与 risk-constitution-audit.md 互补 |
> | §8.3 热配置 system_settings 变量列表 | docs/project-structure.md:366-380 | 配置层完整参考 |
> | §9 tests/ 53 个文件清单 | docs/project-structure.md:386-415 | 测试覆盖度一览 |
> | §10 关键扩展点速查表（"我想做 X — 改哪"）| docs/project-structure.md:419-432 | 新人上手引导 |
> | §11 Legacy / 半死 / 跳过区表 | docs/project-structure.md:438-451 | 防踩坑 |
> | §12 Docker compose 挂卷拓扑细节 | docs/project-structure.md:454-466 | 部署参考 |

### D-Q1. routes 表中 system.py 标 ✅ 但文件已删除
- **位置**: `docs/project-structure.md:93`
- **doc 说**: "| `system.py` | `/api/system/*` | mode 切换 / healthz | ✅ |"
- **实际**: `api/routes/system.py` 不存在（`ls api/routes/` 确认）。
- **建议**: 删除本行（同 D-R6 建议）；在 Phase 1 Task 6 合并时不携带该行进入根文档。

### D-Q2. routes 表中 weights.py + market.py 标 ✅ 但均已删除
- **位置**: `docs/project-structure.md:96`
- **doc 说**: "| `weights.py` | `/api/v5/weights*` | 权重管理 | ✅ |"（同表第 97 行 market.py）
- **实际**: `api/routes/weights.py` 和 `api/routes/market.py` 均不存在（`ls api/routes/` 确认）。
- **建议**: 删除这两行；合并时不携带进根文档。

### D-Q3. "18 个 HTTP endpoint 文件"计数过时
- **位置**: `docs/project-structure.md:84`
- **doc 说**: "★ 18 个 HTTP endpoint 文件 (见下表)"（同 docs/project-structure.md:89 "#### routes/ 18 个 endpoint"）
- **实际**: `ls api/routes/` 去掉 `__init__.py` 后 15 个文件（3 个 v4.3 文件已删除）。
- **建议**: 将"18 个"改为"15 个"；合并进根文档时同步修正。

---

## 五、汇总

| 主 doc | 过时条目 | 消失条目 | 缺失章节 | 建议动作 |
|---|---|---|---|---|
| `README.md` | 2（四个任务 / App.tsx 行号）| 6（collector.py / system.py 引用 / v44-v43 模块 / 3 个路由文件）| 2（/overview / v5_trader_kpi）| Phase 1 Task 7 定点修 10 条 |
| `PROJECT_STRUCTURE.md` | 6（版本头 / DB 表名×2 / WebSocket / API 前缀 / §5.2-5.3 描述）| 5（v4x 脚本 / backtest_paper_trades / V2 组件 / v43_pos_mgr / 3 路由文件）| 1（v5 模块 + backtest/ 目录）| Phase 1 Task 7 大幅刷新 |
| `CHANGELOG.md` | — | — | 1 大块（190 commits）| Phase 1 Task 8 补 v0.5.1 章节 |
| `docs/project-structure.md` | 1（endpoint 计数）| 2（3 个路由文件 ✅ 标注错误）| — | Phase 1 Task 6 合并后删除；7 段独有内容需转移 |

**总计**: 27 条 diff 条目（过时 9 / 消失 13 / 缺失 5）
