# Bug 修复清单 audit · Design

> 日期: 2026-07-03
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/tech-debt.md`（Phase 0，10 findings，observation only）

---

## 一、问题陈述

Phase 0 产出的 `tech-debt.md` 是纯观察（只列现象，不提修法），且只覆盖后端关键 4-5 个模块。用户下一步的实际动作是**排优先级修 bug**，需要一份 actionable 清单：每条带 fix 建议、优先级、测试建议。同时要把 Phase 0 未覆盖的部分（其余后端 + 全部前端）扫一遍，得到完整视角。

## 二、目标

产出 **`docs/audit-2026-07/bug-fix-list.md`**（约 400-700 行），单一 markdown，按优先级排序：

- 沿用 Phase 0 的 10 findings（**不重复分析、原样保留、补 Fix 建议 + 优先级**）
- **追加**新扫出的 findings（后端未覆盖模块 + 全部前端）
- 每条 finding 独立可执行：读了就知道改哪、怎么改、加什么测试

## 三、覆盖范围

### 3.1 后端 Python

**深读**（每个文件 Read + 逐段推理）：
- `scripts/tasks/scorer.py`（评分 + 开仓主流程）
- `scripts/v5_position_manager.py`（LIVE 状态机）
- `scripts/paper_position_manager.py`（SHADOW 状态机）
- `scripts/tasks/collector_main.py`（编排 + 环境读取）
- `scripts/risk_constitution.py`（风控铁律）
- `scripts/core/risk_calculator.py`（ATR / 仓位 / SL 数学）
- `scripts/exchange_factory.py` + `scripts/okx_trader.py` + `scripts/binance_trader.py`（下单层）

**中读**（顶层结构 + 关键函数）：
- 全部 `api/routes/v5_*.py`（约 15 个）
- `scripts/tasks/v5_reflection_worker.py` / `v5_funding_collector.py` / `paper_monitor.py` / `v5_position_monitor.py`

**浅扫**（grep + 挑 anti-pattern 深看）：
- 其余 `scripts/` 文件（找 `except: pass`、`os.environ.get` 无默认值、`sqlite3.connect` 无 with、等）

### 3.2 前端 TypeScript

**深读**：
- `components/pages/StrategyConfigPage.tsx`
- `components/pages/ActivePositionsPage.tsx`
- `components/pages/BacktestPage.tsx`
- `components/pages/SettingsPage.tsx`
- `components/pages-v4/V5DashboardPage.tsx`
- `components/pages/ManualOrderPage.tsx`

**中读**：
- 上述页面用到的 hooks + 相关 Zustand store 分片
- API interceptor / query client 配置

**浅扫**：
- 其他页面 + 通用组件（找无 error boundary、stale query cache、race condition-shaped hooks）

## 四、Finding 结构（每条严格如下）

```markdown
## Finding N: <一行标题>

- **位置**: `<file>:<line>` (可多个)
- **置信度**: CONFIRMED | PLAUSIBLE
- **优先级**: P0 | P1 | P2
- **描述**: 1-2 句现状
- **Failure scenario**: 具体触发 input/state → 具体错误结果
- **相关代码**:
  ```lang
  # 3-6 行引用（含文件:行号 header）
  ```
- **Fix 建议**: 具体改法（含替代实现方向或伪代码；禁止"应重构 X"这种空话）
- **测试建议**: 修完后加什么测试防止回归
```

## 五、优先级判定

| 级别 | 标准 | 例子 |
|---|---|---|
| **P0** | 会导致钱丢 / 状态永久错乱 | DB vs 交易所仓位不一致；仓位翻倍；静默丢单；SL/TP 缺失 |
| **P1** | 数据错误但可查可回滚 | 评分记录 wrong；显示 wrong；日志缺；仓位本身仍安全 |
| **P2** | 体验退化 / 维护性 | 命名混乱；错误信息模糊；未来可能触发的坑 |

判定时若不确定，**上偏一档**（异步风险倾向 P0）。

## 六、md 分节结构

```
一、执行摘要
   - Phase 0 结论: X 条 → 分级为 P0×A P1×B P2×C
   - 本次新增: Y 条 (后端 M / 前端 N)
   - 合计: A+? P0, B+? P1, C+? P2
   - 建议修复顺序（P0 全修 → P1 前 5 修）

二、P0 findings（真钱风险 — 逐条完整格式）

三、P1 findings（数据 / 状态一致性 — 逐条完整格式）

四、P2 findings（体验 / 维护性 — 逐条完整格式）

五、Phase 0 tech-debt.md 的 10 findings 落位
   - Finding N (原 Phase 0 编号) → 本次编号 M，P0/P1/P2, Fix 建议 …

六、附录 — 本次未覆盖模块列表（读者知道盲区）
   - scripts/*_deprecated.py（V4.x 遗留，已计入 dead-code-and-tables.md）
   - Rabbit Hunterfronted/components/ui/ (通用 UI 组件，非交易关键)
   - scripts/ai/local_rag.py（deprecated LR 兜底）
```

## 七、执行方式

**Solo sonnet subagent，单流水**：

1. **主 loop 做初步 grep**（scanner 阶段）：产出深读/中读文件列表 + 已知 anti-pattern 命中列表，作为 anchor 喂给 subagent
2. **1 个 sonnet subagent 拿 anchor + 覆盖清单**，独立完成：
   - 深读所有 3.1 + 3.2 深读文件
   - 中读所有中读文件
   - 从 Phase 0 的 tech-debt.md 提取 10 findings 补 Fix 建议 + 分级
   - 写入 `docs/audit-2026-07/bug-fix-list.md`
   - 跑存在性校验 + commit
3. **主 loop 收到 subagent 报告后做二级 review**（检查 P0 数量 + 前端 finding 数是否达标）

**预期规模**: 25-40 findings，1.5-2.5 小时 wall-clock，token 中等。

**Non-goal**: 本次 spec 不含修复动作。清单落盘后，你 review，我们再单开 spec 决定"修哪些、按什么顺序、每条几个 task"。

## 八、验收标准

- md 落盘、commit
- 每 finding 4 段结构完整（位置 / 置信度 / 描述 / Failure scenario / Fix / 测试）
- 每个 `file:line` 引用都通过存在性检查
- Phase 0 的 10 findings 全在场（不遗漏）
- **前端 findings ≥ 5**（否则 subagent 前端浅扫不够，需 re-dispatch）
- **P0 ≥ 1**（否则可疑 —— 后端跑通零 P0 概率低）
- 无 `<placeholder>` / `TBD`

## 九、超范围声明

- 本 spec 不含任何代码修改
- 不含性能 profile（如 profile scorer 主循环 latency）— 那是另一维度
- 不含安全渗透测试（AuthN/AuthZ / 输入过滤）— 除非本次深读时明显发现
- 不含"未来可能想加什么功能" — 那是需求
- 不含跨项目共享 audit template 的机制 — 本项目专用

## 十、后续路径

1. bug-fix-list.md 落盘 → 用户 review
2. 单开新 spec：`2026-07-XX-bug-fix-batch-1-design.md`，圈定"这批修哪几条 P0" + 每条 1 个 task
3. 该 spec 走 writing-plans → SDD 循环 → 修完

## 十一、相关

- 前置 Phase 0：`docs/audit-2026-07/tech-debt.md`
- 前置 spec：`docs/superpowers/specs/2026-07-02-project-audit-and-doc-refresh-design.md` § 三 3.2
- 输出目录：`docs/audit-2026-07/`（Phase 0 已建）
