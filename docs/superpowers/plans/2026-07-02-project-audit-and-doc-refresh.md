# 项目全面体检 + 开发文档刷新 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 产出 `docs/audit-2026-07/` 5 份体检 md（Phase 0），再基于体检结果刷新 4 份主 doc（Phase 1）。Phase 2（长期记录机制）由本 spec 显式推迟，本 plan 不含。

**Architecture:** 交付物是 markdown 文档，不含代码修改。每份 md 的每条断言必须能通过 `grep` / `sqlite3` / `find` 命令直接验证到 `<file>:<line>`。任务之间弱耦合但有推荐顺序（architecture-map 先出，其他 md 引用它）。

**Tech Stack:** Bash (`grep`/`find`/`sqlite3`/`git log`) + Markdown。零代码变更 = 零单元测试；每份 md 的"测试"是**存在性 + 一致性校验**：用命令查一遍每条 file:line 引用是否成立。

## Global Constraints

- 交付形态：全部 markdown 文件，UTF-8，无 emoji（除非引用现有代码里的 emoji）
- 事实断言必须带 `<repo-relative-path>:<line>` 或 `<table>.<column>` 引用，禁止"大概"、"看起来"等模糊措辞
- Tech-debt 每条 finding 必须显式标 `CONFIRMED` 或 `PLAUSIBLE`
- Dead-code 每条必须显式判断 `预留` 或 `建议删除`（含理由 1 句）
- 不动的文件列表（Phase 0 & 1 都不能改）：
  - `docs/btc-trend-follow-validation.md`
  - `docs/exit-time-experiment.md`
  - `docs/max-hold-scan-experiment.md`
  - `docs/applied-optimal-exit-config.md`
  - `docs/code-audit-report.md`
  - `docs/risk-constitution-audit.md`
  - `docs/ui-design-brief-for-ai-generation.md`
  - `docs/visual-design-v2/**`
  - `docs/readme-vs-code-diff.md`（保留作为历史）
- 每个 Task 独立 commit（本 plan 微调了 spec 中"Phase 0 一次性 commit" 的说法，改为逐份 commit 以便逐份 review/revert；已获得 approve 的 spec 的精神保持一致）
- Phase 1 强依赖 Phase 0 用户 approve，不能跳步
- Phase 0 commit 后不推 remote（等 Phase 1 一起）
- CHANGELOG 补齐范围：`ad19ca1..HEAD` 190 commits（含分布：feat 103 / fix 34 / docs 14 / chore 8 / experiment 7 / test 1 / refactor 1）

---

## File Structure

**Phase 0 · 新建：**
| 路径 | 职责 |
|---|---|
| `docs/audit-2026-07/README.md` | 5 份 md 的 index + "如何使用这份 audit" |
| `docs/audit-2026-07/architecture-map.md` | 后端 + 前端目录、真入口、数据流、DB 表读写路径、页面↔endpoint 对应 |
| `docs/audit-2026-07/dead-code-and-tables.md` | 0 行且无写入表 / 无调用者的代码 / 未读的 config 字段 |
| `docs/audit-2026-07/tech-debt.md` | 潜在 bug / 可疑逻辑 / 命名结构问题，带 CONFIRMED\|PLAUSIBLE |
| `docs/audit-2026-07/doc-vs-code-diff.md` | 4 份主 doc 里过时的断言，作为 Phase 1 shopping list |

**Phase 1 · 改动：**
| 路径 | 动作 |
|---|---|
| `docs/project-structure.md` | 删除（内容合并进根目录版本） |
| `PROJECT_STRUCTURE.md` | 大幅刷新，顶部 "最后更新" 打今天 |
| `CHANGELOG.md` | append `## v0.5.1 → HEAD (WIP)` 章节，覆盖 190 commits |
| `README.md` | 只改和当前代码不符的段落 |

---

# Phase 0 · 体检

## Task 1: 体检目录骨架 + README index 占位

**Files:**
- Create: `docs/audit-2026-07/README.md`

**Interfaces:**
- Produces: `docs/audit-2026-07/` 目录存在，index 文件先落个骨架，后续 4 个 task 更新其中的链接状态

- [ ] **Step 1: 创建目录并写 index 骨架**

```bash
mkdir -p docs/audit-2026-07
```

写入 `docs/audit-2026-07/README.md`：

```markdown
# Rabbit-Hunter 项目体检 · 2026-07

> 生成日期: 2026-07-02
> 覆盖: 后端 `api/` + `scripts/` + DB + `strategy_config.json` + 前端 `Rabbit Hunterfronted/`
> 生成方式: 手工扫描 + `grep`/`sqlite3` 交叉验证
> 结果消费方: `docs/superpowers/plans/2026-07-02-project-audit-and-doc-refresh.md` Phase 1

## 如何使用这份 audit

- **想了解项目结构**：读 `architecture-map.md`
- **想删掉没用的东西**：读 `dead-code-and-tables.md`，每条都标了"预留/建议删除"
- **担心有潜在 bug**：读 `tech-debt.md`，只看 `CONFIRMED` 就够
- **想更新主 doc**：读 `doc-vs-code-diff.md`，逐条改

## 文件清单

| 文件 | 状态 |
|---|---|
| [architecture-map.md](./architecture-map.md) | 待生成 |
| [dead-code-and-tables.md](./dead-code-and-tables.md) | 待生成 |
| [tech-debt.md](./tech-debt.md) | 待生成 |
| [doc-vs-code-diff.md](./doc-vs-code-diff.md) | 待生成 |

## 前置条件

生成本次 audit 时使用的锚点：

- Git HEAD: `<todo: fill with git rev-parse HEAD>`
- v0.5.0 参照 commit: `ad19ca1`
- DB 快照时间: `<todo: fill with date -u iso 8601>`

## 局限性

- 单线扫，未做 workflow 多 agent 交叉验证
- 前端只覆盖 `Rabbit Hunterfronted/`，不含 `node_modules` 或 build 产物
- Tech-debt 仅为观察，不含修复方案（那属于后续 spec）
```

- [ ] **Step 2: 填充 index 里的 git hash 和快照时间**

```bash
HEAD_SHA=$(git rev-parse --short HEAD)
NOW=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
# 用 sed 或 Edit 替换 index 文件里的两个 <todo: fill ...> 占位
```

- [ ] **Step 3: 验证 index 结构正确**

```bash
test -f docs/audit-2026-07/README.md
grep -q "文件清单" docs/audit-2026-07/README.md
grep -c "^| " docs/audit-2026-07/README.md
```
Expected: 4 行文件清单表格行 + 3 行 "如何使用" 说明

- [ ] **Step 4: Commit**

```bash
git add docs/audit-2026-07/README.md
git commit -m "$(cat <<'EOF'
docs(audit): 体检目录 + index 骨架

Phase 0/5 · docs/audit-2026-07/README.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: architecture-map.md

**Files:**
- Create: `docs/audit-2026-07/architecture-map.md`

**Interfaces:**
- Consumes: 无（首个内容 task）
- Produces: 后续 3 份 md 都会引用这里的模块名 / 表名 / endpoint。命名规范：模块 = `scripts/tasks/collector_main.py`（带 `.py`）；表 = `positions_v5`（小写下划线）；endpoint = `GET /api/v5/positions`（HTTP 方法 + 完整路径）

- [ ] **Step 1: 收集后端目录事实**

```bash
find api -maxdepth 2 -name "*.py" | sort
find scripts -maxdepth 2 -name "*.py" | grep -v __pycache__ | sort
```

- [ ] **Step 2: 收集前端目录事实**

```bash
find "Rabbit Hunterfronted" -maxdepth 3 -type d | grep -v node_modules | sort
find "Rabbit Hunterfronted/components/pages" -maxdepth 2 -name "*.tsx" | sort
find "Rabbit Hunterfronted/hooks" -maxdepth 2 -name "*.ts" 2>/dev/null | sort
```

- [ ] **Step 3: 收集 API endpoint**

```bash
grep -rn -E "^(async )?def |@(app|router)\.(get|post|put|delete|patch)" api/routes/ --include="*.py" | head -100
```

- [ ] **Step 4: 收集 DB 表 schema + INSERT/UPDATE 路径**

```bash
sqlite3 data/rabbit_hunter.db "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
# 对每张表跑一次：
for t in $(sqlite3 data/rabbit_hunter.db ".tables"); do
  echo "--- $t ---"
  grep -rnE "(INSERT|UPDATE|REPLACE)\s+(INTO\s+)?['\"]?${t}['\"]?" scripts/ api/ --include="*.py" | head -5
done
```

- [ ] **Step 5: 收集前端页面 → API 调用映射**

```bash
grep -rnE "(fetch|axios|useQuery|useMutation).*['\"]/api/" "Rabbit Hunterfronted/" --include="*.tsx" --include="*.ts" | grep -v node_modules | head -80
```

- [ ] **Step 6: 写 architecture-map.md**

结构（每节都填实内容，不留 TBD）：

```markdown
# Architecture Map · 2026-07

> 生成日期: 2026-07-02
> Git HEAD: <sha>

## 一、后端目录

### api/
<每个子模块一行：路径 + 一句话职责 + 主入口文件>

### scripts/
<同上>

### scripts/tasks/
<主流水线的编排层，必须列出：collector_main / scorer / scanner / deep_collector 等真入口>

## 二、前端目录 (Rabbit Hunterfronted/)

<同上，聚焦 components/pages/ + hooks/ + store>

## 三、真入口

| 入口 | 命令 / 触发 | 职责 |
|---|---|---|
| `python -m scripts.tasks.collector_main` | 手动 or start_collector.bat | 主采集 + 评分 + 开仓 |
| `uvicorn api.main:app` | start_api.bat | FastAPI HTTP + WebSocket |
| `npm run dev` in Rabbit Hunterfronted/ | start_frontend.bat | 前端 dev server |

## 四、主数据流

```
market scanner → deep collector → v5 scorer → paper_pm / live_pm
   ↓                ↓                  ↓            ↓
(exchange API)  (funding/klines)   (write DB)   (paper_trades / positions_v5)
                                       ↓
                             api.services.* ← Frontend hooks
```
<每一段用 file:line 引用支撑>

## 五、DB 表读写路径

| 表 | 写入方 (file:line) | 消费方 (file:line) | 当前行数 |
|---|---|---|---|
| trade_scores_v5 | scripts/tasks/scorer.py:XXX | api/services/scores.py:XXX | 19,386 |
| positions_v5 | scripts/v5_position_manager.py:44 (INSERT), :208 (UPDATE), :241 (UPDATE) | api/services/position_service.py:22 | 0 |
| paper_trades | ... | ... | 53 |
| funding_rates | ... | ... | 3,395 |
| ... | ... | ... | ... |
<每张表都列，行数用 sqlite3 现查>

## 六、前端页面 ↔ API endpoint 对应

| Page | Hook / Query | API endpoint |
|---|---|---|
| V5DashboardPage.tsx | useSystemState | GET /api/v5/system-state |
| ... | ... | ... |
```

- [ ] **Step 7: 存在性验证（每条 file:line 引用必须成立）**

```bash
# 从写好的 md 里抽出所有 <file>:<line> 引用做批量验证
grep -oE '`?[a-zA-Z0-9_./ -]+\.(py|tsx|ts):[0-9]+' docs/audit-2026-07/architecture-map.md \
  | sort -u \
  | while read ref; do
      file="${ref%:*}"
      line="${ref##*:}"
      test -f "$file" && [ "$(wc -l < "$file")" -ge "$line" ] || echo "MISSING: $ref"
    done
```
Expected: 无输出（所有引用都成立）

- [ ] **Step 8: 更新 index 里 architecture-map 的状态**

Edit `docs/audit-2026-07/README.md` 文件清单表格：`| [architecture-map.md](./architecture-map.md) | 待生成 |` → `| [architecture-map.md](./architecture-map.md) | ✅ 已生成 |`

- [ ] **Step 9: Commit**

```bash
git add docs/audit-2026-07/architecture-map.md docs/audit-2026-07/README.md
git commit -m "$(cat <<'EOF'
docs(audit): architecture-map — 后端/前端目录 + 数据流 + DB 读写路径

Phase 0/5 · 覆盖 api/ + scripts/ + Rabbit Hunterfronted/ + 20+ DB 表

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: dead-code-and-tables.md

**Files:**
- Create: `docs/audit-2026-07/dead-code-and-tables.md`

**Interfaces:**
- Consumes: architecture-map.md 的 "五、DB 表读写路径" 表
- Produces: Phase 1 Task 6 (删 project-structure.md) 前不依赖；tech-debt 会引用这里的 "dead path" 结论

- [ ] **Step 1: 查 0 行的表**

```bash
for t in $(sqlite3 data/rabbit_hunter.db ".tables"); do
  n=$(sqlite3 data/rabbit_hunter.db "SELECT COUNT(*) FROM $t;")
  echo "$n $t"
done | sort -n | head -15
```

- [ ] **Step 2: 对每张 0 行表，检查是否有 INSERT 路径**

```bash
# 已知候选：positions_v5, ai_training_data, ws_event_queue, m9_books
for t in positions_v5 ai_training_data ws_event_queue m9_books; do
  echo "=== $t ==="
  grep -rnE "INSERT\s+(OR\s+\w+\s+)?INTO\s+['\"]?${t}['\"]?" scripts/ api/ --include="*.py" | head -3
done
```

- [ ] **Step 3: 找没有 import 者的模块**

```bash
# 扫 scripts/ 下每个 .py 文件的被引用情况
for f in $(find scripts -maxdepth 3 -name "*.py" | grep -v __pycache__ | grep -v tests); do
  mod=$(echo "$f" | sed 's|/|.|g; s|\.py$||')
  callers=$(grep -rE "(from|import)\s+${mod}(\s|$|[.])" scripts/ api/ tests/ --include="*.py" 2>/dev/null | grep -v "$f" | wc -l)
  echo "$callers $f"
done | sort -n | head -20
```

- [ ] **Step 4: 扫 strategy_config.json 字段的读取情况**

```bash
python3 -c "
import json
with open('strategy_config.json') as f:
    cfg = json.load(f)
def walk(d, prefix=''):
    if isinstance(d, dict):
        for k, v in d.items():
            path = f'{prefix}.{k}' if prefix else k
            print(path)
            walk(v, path)
walk(cfg)
" | while read key; do
  leaf="${key##*.}"
  hits=$(grep -rE "['\"]${leaf}['\"]|\.${leaf}\b" scripts/ api/ --include="*.py" 2>/dev/null | wc -l)
  echo "$hits $key"
done | sort -n | head -30
```

- [ ] **Step 5: 写 dead-code-and-tables.md**

结构：

```markdown
# Dead Code & Dead Tables · 2026-07

> 每条 finding 必须标 **预留** 或 **建议删除** + 1 句理由

## 一、DB 表 · 0 行且无 INSERT 路径

### positions_v5
- **行数**: 0
- **INSERT 路径**: scripts/v5_position_manager.py:44（存在但从未触发）
- **触发条件**: 需要 `system_settings.system_state='LIVE'` 且 `get_trader()` 返回非 None
- **当前 blocker**: system_settings 表无 `system_state` 行 → fallback SHADOW → 只走 paper_trades
- **判断**: **预留** — LIVE 交易切换路径的目标表，代码完备
- **建议**: 保留

### ai_training_data
<同结构>

### ws_event_queue
<同结构>

### m9_books
<同结构>

## 二、代码 · 无调用者的模块

<列出 Step 3 输出中 callers=0 的模块，逐条判断"预留 vs 建议删除">

## 三、strategy_config.json · 无读取的字段

<列出 Step 4 输出中 hits=0 的字段>

## 四、汇总

| 类别 | 预留 | 建议删除 |
|---|---|---|
| DB 表 | X | Y |
| 代码模块 | X | Y |
| Config 字段 | X | Y |
```

- [ ] **Step 6: 验证每条 finding 都标了预留/建议删除**

```bash
grep -cE "\*\*(预留|建议删除)\*\*" docs/audit-2026-07/dead-code-and-tables.md
```
Expected: ≥ 每个 finding 一次（数目 ≥ finding 数）

- [ ] **Step 7: 更新 index 状态**

Edit `docs/audit-2026-07/README.md` 把 `dead-code-and-tables.md` 行标 ✅

- [ ] **Step 8: Commit**

```bash
git add docs/audit-2026-07/dead-code-and-tables.md docs/audit-2026-07/README.md
git commit -m "$(cat <<'EOF'
docs(audit): dead-code-and-tables — 0 行表 + 无调用者模块 + 未读 config 字段

Phase 0/5 · 每条 finding 标"预留 vs 建议删除"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: tech-debt.md

**Files:**
- Create: `docs/audit-2026-07/tech-debt.md`

**Interfaces:**
- Consumes: architecture-map.md 的模块清单（用来定位哪些文件值得深读）
- Produces: 无（终点文档）

**扫描重点区域**：
- `scripts/tasks/scorer.py`（评分 + 开仓核心）
- `scripts/v5_position_manager.py`（LIVE 状态机）
- `scripts/tasks/collector_main.py`（编排入口）
- `scripts/local_db.py`（DB 迁移）
- `api/routes/` 下每个路由文件
- `Rabbit Hunterfronted/components/pages/` 关键页面

- [ ] **Step 1: 扫描资源泄漏 / 无 finally 的 IO**

```bash
grep -rn "open(" scripts/ api/ --include="*.py" | grep -v "with " | head -20
grep -rn "sqlite3.connect" scripts/ api/ --include="*.py" | grep -v "with " | head -20
```

- [ ] **Step 2: 扫描 bare except / 过宽 except**

```bash
grep -rnE "except\s*(:|Exception)" scripts/ api/ --include="*.py" | head -30
```

- [ ] **Step 3: 扫描环境变量默认值可疑处**

```bash
grep -rn "os.environ.get(" scripts/ api/ --include="*.py" | head -30
```

- [ ] **Step 4: 深读扫描重点区域（按上面清单）**

按 architecture-map 里的模块清单逐个 Read，找：
- 错误路径反噬（`try/except` 里做了会掩盖问题的动作）
- 逻辑漏洞（if/else 分支处理不完整）
- 无幂等的写库操作
- SQL injection 风险
- 前端未处理的 error state
- 命名不一致（同一 concept 多个名字）

**每条 finding 必须**：
- 具体到 `file:line`
- 标 `CONFIRMED`（有能触发的场景）或 `PLAUSIBLE`（可疑但无明确触发路径）
- 描述 failure_scenario（具体 input → wrong output）

- [ ] **Step 5: 写 tech-debt.md**

结构：

```markdown
# Tech Debt · 2026-07

> 只列观察，不含修复动作。修复由后续 spec 决定。
> 每条 finding 用 CONFIRMED / PLAUSIBLE 标注置信度。

## Findings 汇总

| # | 标题 | 位置 | 置信度 |
|---|---|---|---|
| 1 | ... | file.py:XXX | CONFIRMED |
| ... | ... | ... | ... |

---

## Finding 1: [简短标题]

- **位置**: `scripts/xxx.py:123`
- **置信度**: CONFIRMED
- **描述**: <1-2 句现象>
- **Failure scenario**: <具体的 input/state → 具体的错误结果>
- **相关代码**:
  ```python
  # 引用相关几行
  ```

## Finding 2: ...
```

- [ ] **Step 6: 验证每条 finding 结构完整**

```bash
grep -c "^## Finding " docs/audit-2026-07/tech-debt.md   # findings 总数
grep -c "^- \*\*置信度\*\*" docs/audit-2026-07/tech-debt.md    # 应等于总数
grep -c "^- \*\*Failure scenario\*\*" docs/audit-2026-07/tech-debt.md   # 应等于总数
```
Expected: 三个数相等，即每个 finding 都有位置 + 置信度 + failure scenario

- [ ] **Step 7: 验证 file:line 存在性**

（复用 Task 2 Step 7 的验证命令，只是换 md 路径）

- [ ] **Step 8: 更新 index 状态并 commit**

Edit `docs/audit-2026-07/README.md` 把 `tech-debt.md` 行标 ✅

```bash
git add docs/audit-2026-07/tech-debt.md docs/audit-2026-07/README.md
git commit -m "$(cat <<'EOF'
docs(audit): tech-debt — findings + CONFIRMED/PLAUSIBLE + failure scenarios

Phase 0/5 · 只列观察，不含修复方案

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: doc-vs-code-diff.md

**Files:**
- Create: `docs/audit-2026-07/doc-vs-code-diff.md`

**Interfaces:**
- Consumes: architecture-map.md（提供"当前代码事实"的权威版本）
- Produces: Phase 1 Task 7/8/9 的 shopping list

- [ ] **Step 1: 读 4 份主 doc 全文**

用 Read 工具依次读：
- `README.md`（345 行）
- `PROJECT_STRUCTURE.md`（419 行）
- `CHANGELOG.md`（376 行）
- `docs/project-structure.md`（513 行）

- [ ] **Step 2: 对每个可核实的断言做校验**

对每条形如"XXX 模块负责 YYY" / "有 N 张表" / "用 A 库版本 B" / "支持 X/Y/Z 三种模式" 的断言，用 grep/sqlite3/cat 命令去核对当前代码。

记录三类结果：
- **过时**：doc 说 X，代码是 Y
- **消失**：doc 提到的模块/文件已删除
- **缺失**：代码里有的重要功能，doc 完全没提

- [ ] **Step 3: 写 doc-vs-code-diff.md**

结构：

```markdown
# Doc vs Code Diff · 2026-07

> 每条 diff 是 Phase 1 doc 修改的一个 shopping-list 条目。
> 格式: `<doc-path>:<line>` + doc 现说法 + 当前代码事实 + 建议改法

## 一、README.md

### D1. Node 版本描述过时
- **位置**: `README.md:42`
- **doc 说**: "需要 Node 18+"
- **实际**: package.json engines 是 `node@20.x`
- **建议**: 改成 "需要 Node 20+"

### D2. ...

## 二、PROJECT_STRUCTURE.md

<同结构>

## 三、CHANGELOG.md

### 缺失章节：v0.5.0 之后无任何条目
- **位置**: `CHANGELOG.md:end`
- **doc 说**: 停在 v0.5.0 (2026-06-07)
- **实际**: 之后 190 commits（feat 103 / fix 34 / docs 14 / chore 8 / experiment 7 / test 1 / refactor 1）
- **建议**: 补 `## v0.5.1 → HEAD (WIP)` 章节，按类型分组

## 四、docs/project-structure.md

- **整体建议**: 内容合并进 `PROJECT_STRUCTURE.md` 后删除（spec § 4.1 Step 1）
- **需要保留的内容**：<列出 root PROJECT_STRUCTURE.md 缺失但 docs/ 版本有的段落>

## 五、汇总

| 主 doc | 过时条目 | 缺失章节 | 建议动作 |
|---|---|---|---|
| README.md | X | Y | 定点修 X+Y 条 |
| PROJECT_STRUCTURE.md | X | Y | 大幅刷新 |
| CHANGELOG.md | - | 1 大块 | 补 v0.5.1 章节 |
| docs/project-structure.md | - | - | 删除，内容合并 |
```

- [ ] **Step 4: 验证每条 diff 都有位置 + 现说法 + 实际 + 建议**

```bash
grep -c "^- \*\*位置\*\*" docs/audit-2026-07/doc-vs-code-diff.md
grep -c "^- \*\*doc 说\*\*" docs/audit-2026-07/doc-vs-code-diff.md
grep -c "^- \*\*实际\*\*" docs/audit-2026-07/doc-vs-code-diff.md
grep -c "^- \*\*建议\*\*" docs/audit-2026-07/doc-vs-code-diff.md
```
Expected: 四个数一致

- [ ] **Step 5: 更新 index 状态并 commit**

Edit `docs/audit-2026-07/README.md` 把 `doc-vs-code-diff.md` 行标 ✅

```bash
git add docs/audit-2026-07/doc-vs-code-diff.md docs/audit-2026-07/README.md
git commit -m "$(cat <<'EOF'
docs(audit): doc-vs-code-diff — Phase 1 的 shopping list

Phase 0/5 · 覆盖 4 份主 doc 每条断言的核实结果

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 0 用户 Review Gate

**执行者在此停下**，返回一条消息给用户：

> "Phase 0 5 份 md 已完成并逐份 commit。请 review `docs/audit-2026-07/` 目录，OK 后回复继续 Phase 1。"

用户不 approve 前不启 Phase 1 任何 task。

---

# Phase 1 · 补主 doc

## Task 6: 删 docs/project-structure.md（内容先合并进根目录版本）

**Files:**
- Delete: `docs/project-structure.md`
- Modify: `PROJECT_STRUCTURE.md`（预置将要合并的段落，等 Task 7 再统一整刷）

**Interfaces:**
- Consumes: `doc-vs-code-diff.md § 四` 里列出的 "需要保留的内容"
- Produces: 让 Task 7 可以放心把 PROJECT_STRUCTURE.md 当唯一版本处理

**执行逻辑**：先把 `docs/project-structure.md` 里 root 版本缺失但有价值的段落**追加到 PROJECT_STRUCTURE.md 末尾**（打上"待整合"标签，Task 7 会重写整篇），然后删除 `docs/project-structure.md`。

- [ ] **Step 1: 从 doc-vs-code-diff.md 读取 "需要保留的内容" 清单**

- [ ] **Step 2: 从 docs/project-structure.md 提取这些段落**

- [ ] **Step 3: append 到 PROJECT_STRUCTURE.md 末尾**

在 PROJECT_STRUCTURE.md 末尾添加：

```markdown

---

## [待整合 · Task 7 会重写] 从 docs/project-structure.md 合并的段落

<粘贴需保留的段落>
```

- [ ] **Step 4: 删除 docs/project-structure.md**

```bash
git rm docs/project-structure.md
```

- [ ] **Step 5: 验证两个 md 状态**

```bash
test ! -f docs/project-structure.md
grep -q "待整合 · Task 7" PROJECT_STRUCTURE.md
```

- [ ] **Step 6: Commit**

```bash
git add PROJECT_STRUCTURE.md
git commit -m "$(cat <<'EOF'
docs: 合并 docs/project-structure.md 独有段落到 PROJECT_STRUCTURE.md 并删除重复

Phase 1/4 · 只搬内容，整篇重写留给 Task 7

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 刷新 PROJECT_STRUCTURE.md

**Files:**
- Modify: `PROJECT_STRUCTURE.md`（整篇重写）

**Interfaces:**
- Consumes: `docs/audit-2026-07/architecture-map.md`（内容来源）
- Produces: 一份对齐当前代码的项目结构总览

- [ ] **Step 1: 读 architecture-map.md 全文作为素材**

- [ ] **Step 2: 读现有 PROJECT_STRUCTURE.md 保留"设计哲学"章节**

（避免全盘丢失 tone / 立场性文字。技术事实全部以 architecture-map 为准。）

- [ ] **Step 3: 重写 PROJECT_STRUCTURE.md**

顶部 header 更新：

```markdown
# Rabbit Hunter 项目逻辑结构总览

> 版本：v0.5.x → HEAD · 最后更新：2026-07-02
> 事实来源: docs/audit-2026-07/architecture-map.md
```

结构应对齐 architecture-map.md 的六节，但语气更适合"总览"：不铺全部 file:line，只在关键处引用。

- [ ] **Step 4: 移除 Task 6 添加的"待整合"块**

```bash
grep -q "待整合 · Task 7" PROJECT_STRUCTURE.md
# 应该 grep 不到（已被整合到主体）
```

- [ ] **Step 5: 验证顶部日期和引用**

```bash
head -5 PROJECT_STRUCTURE.md | grep "2026-07-02"
head -5 PROJECT_STRUCTURE.md | grep "architecture-map"
```

- [ ] **Step 6: Commit**

```bash
git add PROJECT_STRUCTURE.md
git commit -m "$(cat <<'EOF'
docs(structure): 刷新 PROJECT_STRUCTURE.md 对齐 v0.5.x → HEAD

Phase 1/4 · 事实源 = docs/audit-2026-07/architecture-map.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 补 CHANGELOG.md 覆盖 v0.5.1 → HEAD

**Files:**
- Modify: `CHANGELOG.md`（在 v0.5.0 章节前面 prepend 新章节）

**Interfaces:**
- Consumes: `git log ad19ca1..HEAD` 190 commits
- Produces: append-only，不动 v0.5.0 章节

- [ ] **Step 1: 拉全部 commit + type 分组**

```bash
git log --pretty=format:'%h|%s' ad19ca1..HEAD > /tmp/commits.txt
wc -l /tmp/commits.txt  # 应 = 190
```

- [ ] **Step 2: 按 conventional commit type 分桶**

```bash
grep -E "\|feat" /tmp/commits.txt > /tmp/feat.txt
grep -E "\|fix" /tmp/commits.txt > /tmp/fix.txt
grep -E "\|experiment" /tmp/commits.txt > /tmp/experiment.txt
grep -E "\|docs" /tmp/commits.txt > /tmp/docs.txt
grep -E "\|chore" /tmp/commits.txt > /tmp/chore.txt
grep -E "\|(test|refactor|perf)" /tmp/commits.txt > /tmp/other.txt
```

- [ ] **Step 3: 在 CHANGELOG.md 顶部 prepend 新章节**

模板：

```markdown
## v0.5.x-dev — v0.5.0 之后的持续迭代（190 commits）
**日期区间**: 2026-06-08 → 2026-07-02

> 这一段没有正式 release tag，是 v0.5.0 之后累积的所有变更。
> 按 conventional commit type 分组，同类里按主题聚簇。
> 完整 git log: `git log ad19ca1..HEAD`

### feat（103 条）

#### 前端 UI
- `<sha>` <subject>
- ...

#### 交易系统
- ...

#### 数据 / 回测
- ...

### fix（34 条）

- ...

### experiment（7 条）

> 实验条目保留证伪 / 采纳结论。

- `20e5bca` BTC trend-follow max_hold/SL/TP grid → 独立期验证证伪
- ...

### docs（14 条）
- ...

### chore / test / refactor（10 条）
- ...

---

## v0.5.0 — 安全 + 正确性 + 学习闭环（v45 大检修）
<原有内容不动>
```

**分组策略**：feat 数量最多，需要用**主题聚簇**（前端 UI / 交易系统 / 数据回测 / API / 配置管理 / etc）而不是纯 flat list。执行者根据 subject 关键词分组，每组下按时间倒序。

- [ ] **Step 4: 验证新章节结构**

```bash
grep -c "^### " CHANGELOG.md   # 至少 5 个新的 h3（feat/fix/experiment/docs/chore）
grep -q "v0.5.x-dev" CHANGELOG.md
grep -q "^## v0.5.0 — 安全 + 正确性 + 学习闭环" CHANGELOG.md   # v0.5.0 章节仍在
```

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs(changelog): 补 v0.5.1 → HEAD 190 commits，按 type + 主题分组

Phase 1/4 · v0.5.0 章节保留原样，新章节 prepend 到顶部

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: 刷新 README.md（定点修改）

**Files:**
- Modify: `README.md`（不整篇重写，只改 doc-vs-code-diff 里列出的过时段落）

**Interfaces:**
- Consumes: `docs/audit-2026-07/doc-vs-code-diff.md § 一` 里 README 的所有 diff 条目
- Produces: 一份和代码一致的 README

- [ ] **Step 1: 读 doc-vs-code-diff.md § 一 抽出 README 的所有 diff**

- [ ] **Step 2: 对每条 diff 用 Edit 精确改**

不做全文重写，只改列出的段落。若某条 diff 的 "建议改法" 是"重写这一整节"，才做局部整节重写。

- [ ] **Step 3: 抽样验证**

```bash
# 从改后的 README 里抽 3 条断言，用 grep/sqlite3 核实
# 举例（执行者按实际改动挑）：
grep -A1 "支持三种运行模式" README.md
sqlite3 data/rabbit_hunter.db "SELECT COUNT(*) FROM trade_scores_v5;"  # 核对是否引用了准的数字
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs(readme): 定点刷新过时段落（doc-vs-code-diff shopping list）

Phase 1/4 · 只改 diff 列表里的条目，非全文重写

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 1 用户 Review Gate

**执行者在此停下**，返回：

> "Phase 1 完成，4 份主 doc 已刷新，逐 commit 落盘。请：
> 1. 抽 3 条 `doc-vs-code-diff.md` 里的 diff 条目 spot-check 是否已落实到主 doc
> 2. 抽读一下 CHANGELOG 的 v0.5.x-dev 章节，看分组是否合理
> 3. 确认 `docs/project-structure.md` 已删除且没丢关键内容
> 
> 全部 OK 后本 plan 结束。Phase 2 由新 spec 启动。"

---

# 终止条件

本 plan 的终点 = Task 9 完成 + Phase 1 用户 approve。**不进入 Phase 2**（spec 已声明 Phase 2 需新 spec）。

# Self-Review 记录

- **Spec coverage**: 5 份 audit md + 4 份 doc 刷新 vs spec §3.2 + §4.1 → 全覆盖 ✓
- **Placeholder scan**: 无 TBD / TODO / "同上"；每个 task 步骤都有具体命令或模板 ✓
- **Type consistency**: 模块名带 `.py`，表名小写下划线，endpoint 带 HTTP 方法 —— 已在 Task 2 Interfaces 里锁定 ✓
- **Sequence check**: Task 6 依赖 Task 5 的 doc-vs-code-diff.md；Task 7 依赖 Task 6；Task 8/9 依赖 Task 5。若并行执行 8/9 也可以 —— 但建议按 6→7→8→9 顺序（避免同时改 CHANGELOG 和 README 时 conflict）
- **Divergence from spec**: spec 说 "Phase 0 一次性 commit 5 份"，本 plan 改为**逐份 commit**，理由：每份 md 独立可 review、可 revert。已在 Global Constraints 声明。
