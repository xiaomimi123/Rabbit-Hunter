# Bug 修复清单 audit · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 产出 `docs/audit-2026-07/bug-fix-list.md` —— 单一 markdown，按 P0/P1/P2 排序的可执行 bug 修复清单。沿用 Phase 0 的 10 findings（补 Fix 建议 + 分级），追加后端未覆盖模块 + 全部前端。

**Architecture:** 单一 sonnet subagent 执行完整 audit：读代码 → 找 bug → 写 md → 结构 + 存在性 self-verify → commit。控制层（controller）预先跑 grep 找 anchor 点喂给 subagent，事后跑硬指标验收（P0 ≥ 1、前端 findings ≥ 5、Phase 0 十条全在），不达标就 dispatch fix subagent 补窟窿。

**Tech Stack:** Bash（grep、sqlite3、wc）+ Markdown。零代码变更 → 零单元测试。"test" 是结构 + 存在性检查，用 grep / sed / test 命令直接验证。

## Global Constraints

- **交付物**：单个 md 文件 `docs/audit-2026-07/bug-fix-list.md`，UTF-8，无 emoji
- **每条 finding 必须 6 段**：`**位置**` + `**置信度**`（CONFIRMED | PLAUSIBLE）+ `**优先级**`（P0 | P1 | P2）+ `**描述**` + `**Failure scenario**` + `**Fix 建议**` + `**测试建议**` —— 全都要，不能省
- **每个 `file:line` 引用必须通过存在性 grep 检查**
- **不写 fix 时用"应重构 X"这种空话**：Fix 建议必须给替代实现方向或伪代码
- **不改代码**：本 plan 只产出 audit 文档，不修任何 bug
- **Phase 0 tech-debt.md 的 10 findings 全在场**（不遗漏，全都补 Fix + 分级）
- **前端 findings ≥ 5**
- **P0 findings ≥ 1**（否则可疑）
- **Non-goal**：性能 profile、安全渗透测试、需求提议、未覆盖模块的深读（超范围列附录说明）
- **提交范围**：只 stage `docs/audit-2026-07/bug-fix-list.md`
- **Commit message subject**：`docs(audit): bug-fix-list — Phase 0 十条 + 新增 findings 按 P0/P1/P2 分级`

---

## File Structure

**新建**：
| 路径 | 职责 |
|---|---|
| `docs/audit-2026-07/bug-fix-list.md` | 单一交付，按优先级排序的 bug 清单 |

**辅助（.superpowers/sdd/ 下的 scratch，不 commit）**：
| 路径 | 职责 |
|---|---|
| `.superpowers/sdd/audit-anchors.md` | 控制层预扫的 anchor（可疑文件 + 命中的 anti-pattern grep 行号）——喂给 subagent 少走弯路 |

---

# Task 1: 生成 bug-fix-list.md（single sonnet subagent）

**Files:**
- Create: `docs/audit-2026-07/bug-fix-list.md`
- Read (subagent depth): `scripts/tasks/scorer.py`、`scripts/v5_position_manager.py`、`scripts/paper_position_manager.py`、`scripts/tasks/collector_main.py`、`scripts/risk_constitution.py`、`scripts/core/risk_calculator.py`、`scripts/exchange_factory.py`、`scripts/okx_trader.py`、`scripts/binance_trader.py`
- Read (subagent breadth): 全部 `api/routes/v5_*.py`、前端 6 个交易关键页
- Reuse: `docs/audit-2026-07/tech-debt.md`（Phase 0 十条）

**Interfaces:**
- Consumes: `.superpowers/sdd/audit-anchors.md`（Step 1 生成，包含 grep 命中列表）
- Produces: `docs/audit-2026-07/bug-fix-list.md`

## 控制层准备（Steps 1-2）

- [ ] **Step 1: 生成 anchor 文件（控制层 bash）**

controller 跑以下 grep，把结果写入 `.superpowers/sdd/audit-anchors.md`，作为 subagent 的入手 anchor（不写死 finding，只是让 subagent 少走冷启动）：

```bash
mkdir -p .superpowers/sdd

cat > .superpowers/sdd/audit-anchors.md <<'EOF'
# Audit anchors (2026-07-03)

Controller 预扫的 anti-pattern 命中列表。仅作 anchor，不代表就是 finding —— subagent 需自行判断触发场景。

## bare / broad except

EOF

grep -rnE "except\s*(Exception)?\s*:" scripts/ api/ --include="*.py" \
  | grep -v "raise" | grep -v "test_" | head -40 >> .superpowers/sdd/audit-anchors.md

echo "" >> .superpowers/sdd/audit-anchors.md
echo "## sqlite3.connect without with" >> .superpowers/sdd/audit-anchors.md
echo "" >> .superpowers/sdd/audit-anchors.md
grep -rn "sqlite3.connect" scripts/ api/ --include="*.py" \
  | grep -v "with " | head -20 >> .superpowers/sdd/audit-anchors.md

echo "" >> .superpowers/sdd/audit-anchors.md
echo "## os.environ.get with suspicious defaults" >> .superpowers/sdd/audit-anchors.md
echo "" >> .superpowers/sdd/audit-anchors.md
grep -rnE "os\.environ\.get\([^)]+\)" scripts/ api/ --include="*.py" | head -30 >> .superpowers/sdd/audit-anchors.md

echo "" >> .superpowers/sdd/audit-anchors.md
echo "## frontend fetch/axios no error handling" >> .superpowers/sdd/audit-anchors.md
echo "" >> .superpowers/sdd/audit-anchors.md
grep -rnE "(fetch|axios)\([^)]*\)\s*\.then" "Rabbit Hunterfronted/components" 2>/dev/null | head -20 >> .superpowers/sdd/audit-anchors.md

echo "" >> .superpowers/sdd/audit-anchors.md
echo "## frontend queryClient.invalidateQueries without keys or stale time issue" >> .superpowers/sdd/audit-anchors.md
echo "" >> .superpowers/sdd/audit-anchors.md
grep -rnE "useQuery|useMutation" "Rabbit Hunterfronted/hooks" 2>/dev/null | head -30 >> .superpowers/sdd/audit-anchors.md
```

Expected: `.superpowers/sdd/audit-anchors.md` 存在，包含 5 段 grep 命中（大概 100-150 行）。

- [ ] **Step 2: 验证前端页面路径（controller 预调查）**

前端 v5 页面部分在 `pages/`、部分在 `pages-v4/`，spec 里的路径是估的。controller 用 find 定位实际路径，附加到 anchor 文件：

```bash
echo "" >> .superpowers/sdd/audit-anchors.md
echo "## Actual frontend page paths (for the 6 deep-read targets)" >> .superpowers/sdd/audit-anchors.md
echo "" >> .superpowers/sdd/audit-anchors.md
for name in StrategyConfigPage ActivePositionsPage BacktestPage SettingsPage DashboardPage ManualOrderPage V5DashboardPage V5ManualOrderPage; do
  find "Rabbit Hunterfronted/components" -name "${name}.tsx" 2>/dev/null \
    | sed "s|^|# ${name}: |" >> .superpowers/sdd/audit-anchors.md
done
```

Expected: subagent 后续按此表读实际路径，不再猜。

## Subagent dispatch（Step 3）

- [ ] **Step 3: Dispatch sonnet subagent 执行完整 audit**

Controller 用 SDD 的 subagent-driven pattern，dispatch 1 个 sonnet subagent。subagent 的 prompt 结构参考 SDD implementer 模板，重点带上：

- Task 描述：读代码 + 找 bug + 写 `docs/audit-2026-07/bug-fix-list.md` + 结构自查 + commit
- Anchor：`.superpowers/sdd/audit-anchors.md`（Step 1-2 生成）
- 现有输入：`docs/audit-2026-07/tech-debt.md`（Phase 0 十条，需要沿用 + 补 Fix + 分级）
- 覆盖清单：spec § 三 3.1 + 3.2（深读 / 中读 / 浅扫分级）
- 输出契约：spec § 四（每条 6 段）、§ 五（P0/P1/P2 判定）、§ 六（md 分节结构）
- 硬指标：前端 findings ≥ 5、P0 ≥ 1、Phase 0 十条全在、每 `file:line` 通过 grep 存在性
- Commit：只 stage `docs/audit-2026-07/bug-fix-list.md`，subject 用 Global Constraints 里的那句

Subagent 内部执行：
1. 读 spec 全文（`docs/superpowers/specs/2026-07-03-bug-fix-audit-design.md`）
2. 读 Phase 0 tech-debt.md，提取 10 finding 作为 baseline（原样保留 + 补 Fix + 分级）
3. 按覆盖清单深读后端 9 文件 + 中读 15 API 路由 + 前端 6 页
4. 每发现一个 bug → 按 spec § 四 结构写下来
5. 全部写完 → 按 P0/P1/P2 排序 → 按 spec § 六 分节
6. 结构自查：
   ```bash
   # 每 finding 6 段完整
   grep -c "^## Finding " docs/audit-2026-07/bug-fix-list.md
   for section in "位置" "置信度" "优先级" "描述" "Failure scenario" "Fix 建议" "测试建议"; do
     grep -c "^- \*\*${section}\*\*" docs/audit-2026-07/bug-fix-list.md
   done
   # 7 个数应该相等（有些 findings 位置多行，"位置" 可能 ≥ finding 数，可接受）

   # 存在性校验（regex 含数字，Phase 0 后已修正）
   grep -oE '`?[a-zA-Z0-9_./ -]+\.(py|tsx|ts):[0-9]+' docs/audit-2026-07/bug-fix-list.md \
     | sort -u \
     | while read ref; do
         file="${ref%:*}"; line="${ref##*:}"
         test -f "$file" && [ "$(wc -l < "$file")" -ge "$line" ] || echo "MISSING: $ref"
       done
   ```
7. 分级 sanity check：
   ```bash
   grep -c "\*\*优先级\*\*: P0" docs/audit-2026-07/bug-fix-list.md   # ≥ 1
   # 前端 findings 数（用 .tsx / .ts 引用做判断）
   grep -E "\*\*位置\*\*.*\.(tsx|ts):" docs/audit-2026-07/bug-fix-list.md | wc -l   # ≥ 5
   ```
8. Commit：
   ```bash
   git add docs/audit-2026-07/bug-fix-list.md
   git commit -m "$(cat <<'CMSG'
   docs(audit): bug-fix-list — Phase 0 十条 + 新增 findings 按 P0/P1/P2 分级

   Solo sonnet audit：后端深读 9 文件 + 中读 15 API + 前端深读 6 页。
   每条 finding 6 段（位置/置信度/优先级/描述/Failure scenario/Fix/测试建议）。
   Phase 0 十条沿用，补 Fix + 分级。P0 ≥ 1，前端 ≥ 5。

   Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
   CMSG
   )"
   ```

Subagent 报告：Status、commit SHA、findings 分布（P0/P1/P2 × 后端/前端）、存在性 check 结果、报告文件路径。

## 控制层验收（Steps 4-5）

- [ ] **Step 4: Controller 硬指标验收**

Subagent 完成后，controller 跑硬指标：

```bash
LIST=docs/audit-2026-07/bug-fix-list.md
test -f "$LIST" || echo "FAIL: file missing"

# 硬指标 1: P0 ≥ 1
P0_COUNT=$(grep -c "\*\*优先级\*\*: P0" "$LIST")
[ "$P0_COUNT" -ge 1 ] && echo "P0 OK ($P0_COUNT)" || echo "FAIL: P0 = $P0_COUNT"

# 硬指标 2: 前端 findings ≥ 5
FRONTEND_COUNT=$(grep -E "\*\*位置\*\*.*\.(tsx|ts):" "$LIST" | wc -l | tr -d ' ')
[ "$FRONTEND_COUNT" -ge 5 ] && echo "frontend OK ($FRONTEND_COUNT)" || echo "FAIL: frontend = $FRONTEND_COUNT"

# 硬指标 3: Phase 0 十条全在（用 Phase 0 里的关键 identifiers 做 grep）
for kw in "LOCAL_DB_PATH" "SL_TP_FAIL_OPEN" "close_position" "preview" "get_param" "walkforward daemon" "_resolve_leverage" "V5Scorer.run" "max_concurrent" "LIVE 模式余额"; do
  grep -q "$kw" "$LIST" && echo "phase0 kw OK: $kw" || echo "FAIL: missing phase0 kw: $kw"
done

# 硬指标 4: 每 finding 结构完整
FINDING_COUNT=$(grep -c "^## Finding " "$LIST")
for section in "位置" "置信度" "优先级" "描述" "Failure scenario" "Fix 建议" "测试建议"; do
  N=$(grep -c "^- \*\*${section}\*\*" "$LIST")
  [ "$N" -ge "$FINDING_COUNT" ] && echo "$section OK ($N ≥ $FINDING_COUNT)" || echo "FAIL: $section = $N < $FINDING_COUNT"
done

# 硬指标 5: 存在性
MISSING=$(grep -oE '`?[a-zA-Z0-9_./ -]+\.(py|tsx|ts):[0-9]+' "$LIST" \
  | sort -u \
  | while read ref; do
      file="${ref%:*}"; line="${ref##*:}"
      test -f "$file" && [ "$(wc -l < "$file")" -ge "$line" ] || echo "MISSING: $ref"
    done | wc -l | tr -d ' ')
[ "$MISSING" = "0" ] && echo "existence OK" || echo "FAIL: $MISSING missing refs"
```

Expected: 所有 5 类硬指标不出现 `FAIL:`。若出现，进 Step 5。

- [ ] **Step 5: 硬指标不达标时的处理**

若 Step 4 报 `FAIL:`：

- **P0 = 0**：dispatch 一个 sonnet 补丁 subagent，重点复看 `v5_position_manager.py` + `scorer.py` 的 fail-closed 路径，找至少 1 条 CONFIRMED 的真钱风险（往往和 SL/TP 状态机 / 平仓路径有关）
- **前端 < 5**：dispatch 一个 sonnet 补丁 subagent，深读前端 6 页 + hooks，找并补足
- **Phase 0 关键词缺失**：可能 subagent 换了措辞，让补丁 subagent 用 Phase 0 原文对照修正
- **结构不齐 / 存在性 MISSING**：dispatch 一个 haiku 补丁 subagent，机械纠正格式或删除 fabricated 引用

补丁 subagent 完成后重跑 Step 4 硬指标，直到全通。

## 处理 Ready 后（Step 6）

- [ ] **Step 6: Push（可选，视用户）**

```bash
git push origin main
```

（若用户选 Keep as-is 则跳过；finishing-a-development-branch skill 会问）

---

# Self-Review 记录

- **spec § 一 目标**：Task 1 产出 bug-fix-list.md 覆盖 ✓
- **spec § 三 覆盖范围**：Step 3 subagent prompt 明确列出深读/中读/浅扫清单 ✓
- **spec § 四 finding 结构 6 段**：Step 3 subagent 自查 + Step 4 硬指标校验 ✓
- **spec § 五 优先级**：subagent prompt 引 spec，Step 4 硬指标校验 P0 ≥ 1 ✓
- **spec § 六 md 分节**：subagent prompt 引 spec ✓
- **spec § 七 执行方式**：controller Step 1-2 anchor 预扫 + Step 3 subagent + Step 4 controller 验收 ✓
- **spec § 八 验收标准**：全部映射到 Step 4 硬指标 ✓
- **placeholder scan**：无 TBD / TODO / "similar to Task N" ✓
- **type consistency**：所有路径引用带 `.py` / `.tsx` / `.ts` 后缀，Phase 0 关键词硬编码列出 ✓
- **spec § 九 超范围声明**：subagent prompt 内会强调不做 fix、不做性能 profile ✓
