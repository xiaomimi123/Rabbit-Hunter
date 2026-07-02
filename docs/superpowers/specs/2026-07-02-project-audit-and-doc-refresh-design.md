# 项目全面体检 + 开发文档刷新 · Design

> 日期: 2026-07-02
> 状态: awaiting user review
> 前置: brainstorming 会话 (2026-07-02) 已对齐目标、顺序、方案

---

## 一、问题陈述

三个并存的痛点：

1. **文档已经追不上代码** —— `PROJECT_STRUCTURE.md` 顶部写 "最后更新 2026-06-08"，之后有 20+ commits (v5 位置管理、backtest 引擎、UI v2、BTC trend-follow 实验等) 未进文档；`CHANGELOG.md` 停在 v0.5.0。
2. **缺少"每次改动都被记录"的机制** —— 依赖手动写 CHANGELOG，很多改动（尤其 experiment/hotfix）漏记。
3. **不清楚项目当前长什么样** —— 半年多迭代下来，用户对全局把握不足。

## 二、总体顺序

按 Phase 0 → 1 → 2 严格串行执行：

- **Phase 0 · 体检**：产出"当前状态快照"，作为 Phase 1 的原料。
- **Phase 1 · 补文档**：基于 Phase 0 的 diff 清单，把主 doc 对齐到代码。
- **Phase 2 · 建机制**：在准的基线上，谈"如何保证不再腐化"。

顺序理由：
- `3 → 1`：不做体检就更新文档 = 凭印象写；现在这份过时的 `PROJECT_STRUCTURE.md` 就是这么来的。
- `1 → 2`：先有准的基线，机制才有意义；反过来会锁死一份不准的文档。

Phase 2 的**讨论**可以和 Phase 1 并行，但**执行**必须等 Phase 1 完成。

## 三、Phase 0 · 体检（方案 B · 结构化主题 doc）

### 3.1 覆盖范围

- 后端: `api/` + `scripts/` (含 `scripts/tasks/`) + `data/rabbit_hunter.db` schema + `strategy_config.json`
- 前端: `Rabbit Hunterfronted/`（全部页面 + hooks + 状态管理）
- 配置 / 环境: `.env` schema、`docker-compose.yml`、`requirements.txt`
- 现有 4 份主 doc: `README.md` / `PROJECT_STRUCTURE.md` / `CHANGELOG.md` / `docs/project-structure.md`

### 3.2 输出目录 `docs/audit-2026-07/`

| 文件 | 内容与验收标准 |
|---|---|
| `README.md` | index，链到下列 4 份 + 一段 "如何使用这份 audit" 的说明 |
| `architecture-map.md` | (1) 后端模块划分、真正的入口 (collector_main / api entry)；(2) 主数据流：scanner → deep → scorer → position_manager → DB → api → frontend；(3) DB 每张表的**写入路径 + 消费方**（就像我们对 positions_v5 做的那种梳理）；(4) 前端页面 vs 后端 endpoint 对应关系表。 |
| `dead-code-and-tables.md` | (1) DB 中 0 行且无写入路径的表（当前已知：`positions_v5`、`ai_training_data`、`ws_event_queue`、`m9_books`）；(2) 代码里存在但没有调用者的模块 / 函数；(3) `strategy_config.json` 里定义但代码从不读的字段；(4) 每一项附"是预留 vs 该删"的判断建议。 |
| `tech-debt.md` | (1) 潜在 bug、可疑逻辑、资源泄漏；(2) 命名 / 结构可清理的地方；(3) 每条 finding 用 CONFIRMED / PLAUSIBLE 标注置信度。**不含修复动作，只列观察**。 |
| `doc-vs-code-diff.md` | 4 份主 doc 里哪些描述已过时；每条包含 `<doc-path>:<line>` + 当前代码事实 + 建议改法。**直接作为 Phase 1 的 shopping list**。 |

### 3.3 执行方式

- 我单线扫（不启 Workflow 多 agent）
- Phase 0 结束后，5 份 md 一次性 commit
- 用户 review 5 份 md，签 "OK" 才进 Phase 1

## 四、Phase 1 · 补文档

### 4.1 动作清单（顺序执行，每步一个 commit）

1. **删 `docs/project-structure.md`** —— 内容合并进根目录版本（已确认策略）。
2. **改 `PROJECT_STRUCTURE.md`** —— 用 `architecture-map.md` 的结果整段刷新；顶部 "最后更新" 打今天日期。
3. **改 `CHANGELOG.md`** —— 补齐 v0.5.0 到今天的**全部** commits（不精选），按类型分组 (feat / fix / experiment / chore)；实验条目保留证伪结论的一句话总结。目标是补上缺失的时间段，不重写已有 v0.5.0 章节。
4. **改 `README.md`** —— 只更新和当前代码不符的段落，不做全文重写。

### 4.2 不动的文档

- `docs/` 下的实验复盘 md (`btc-trend-follow-validation.md`、`exit-time-experiment.md`、`max-hold-scan-experiment.md`、`applied-optimal-exit-config.md`) —— 已是历史快照，不该改。
- `docs/code-audit-report.md` / `docs/risk-constitution-audit.md` —— 同上，是当时的审计快照。
- `docs/ui-design-brief-*.md` / `docs/visual-design-v2/` —— 除非 Phase 0 发现前端和它偏离严重，否则本轮不动。
- `docs/readme-vs-code-diff.md` —— 已被 `doc-vs-code-diff.md` 取代，但保留作为历史。

### 4.3 验收

- 4 份主 doc 里没有和代码明显冲突的描述
- 用户从 Phase 0 的 `doc-vs-code-diff.md` 抽 3 条 spot check，全部通过

## 五、Phase 2 · 建长期记录机制（本 spec 只列方向，不锁定）

**推迟到 Phase 1 完成后单开一次 brainstorming** 决定具体形态，因为选型依赖 Phase 1 最终的目录结构 (CHANGELOG 分节、doc 位置等)。

当前记录 3 个候选方向：

- **A · Claude Code hook** — 在 `settings.json` 挂 `PostToolUse` / `Stop` hook，会话内改代码后自动 append 到 `dev-log.md`（走 `update-config` skill）。
- **B · Git hook + 约定** — `prepare-commit-msg` 检查 commit 是否更新 CHANGELOG，未更新则拒绝。
- **C · CLAUDE.md 硬约束** — 让 Claude 每次改文件后自觉在 CHANGELOG append 一行。最轻但可靠性最低。

三者可以组合（如 A + C）。选型时会考虑：可靠性、维护成本、对现有 workflow 的干扰。

## 六、超范围声明 (What this spec is NOT)

- **不含实际代码修复** —— tech-debt.md 只列观察，本 spec 不承诺修哪些
- **不含前端设计重构** —— 只梳理现状
- **不含 Phase 2 的具体机制实现** —— 单开 spec
- **不含 audit-2026-07 的持续维护** —— 这是一次性快照

## 七、交付时间线（估算）

| 阶段 | 大致时长 |
|---|---|
| Phase 0 (5 份 md) | 2-4 小时 |
| 用户 review Phase 0 | 依用户节奏 |
| Phase 1 (4 步 commit) | 2-3 小时 |
| 用户 review Phase 1 | 依用户节奏 |
| Phase 2 spec | 单独会话 |

## 八、相关会话

- 2026-07-01 首次会话：查看数据采集现状，发现 `positions_v5` / `ai_training_data` / `ws_event_queue` 均为 0 行。
- 2026-07-02 本次会话：追踪 `positions_v5` 的写入路径，确认从未进 LIVE 模式；随后开启本次 brainstorming。
