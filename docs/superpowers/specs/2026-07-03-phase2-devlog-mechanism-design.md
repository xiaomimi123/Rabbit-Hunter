# Phase 2 · 每次改动自动进 dev-log 的机制 · Design

> 日期: 2026-07-03
> 状态: awaiting user review
> 前置: `2026-07-02-project-audit-and-doc-refresh-design.md` § 5 Phase 2 方向 A

---

## 一、问题陈述

audit-refresh 完成后，剩下的第三个痛点仍在：**"每次改动都能记录"**的自动机制缺失。历史上依赖手动写 CHANGELOG，导致 v0.5.0 之后 200+ commits 全靠一次性 audit 补齐。想要一个不需要"记得"的自动记录，配合 CHANGELOG（人可读、筛选后）形成两层：

- `CHANGELOG.md`：人工筛选 + 主题聚簇，release-level narrative
- `docs/dev-log.md`（本 spec）：机器自动 append，commit-level 时间线

## 二、范围

**In scope**：
- Post-commit git hook 自动写入 `docs/dev-log.md`
- 中心化 hook 目录 `.githooks/` + `core.hooksPath` 配置
- 首次启用的 bootstrap（含从既有 209 commits 一次性 seed）
- Setup 说明写入 `CLAUDE.md`（新建）+ `README.md`

**Out of scope**：
- CHANGELOG 的自动化（保持人工，本机制不触碰它）
- pre-commit / commit-msg 层的校验（不阻断 commit）
- Cross-repo / cross-machine 同步（个人本地机制）

## 三、决策与理由（brainstorming session 得出）

| 决策 | 值 | 备用未选原因 |
|---|---|---|
| 粒度 | per-commit | task-based 依赖 Claude 判断，"归档价值"级别太主观 |
| 触发 | post-commit hook | prepare-commit-msg 阻断太激进；pre-commit 时 SHA 未定 |
| 阻断行为 | 无（log-only） | 阻断改动 CHANGELOG 会让日常 chore 变累赘 |
| 存储位置 | in-repo `docs/dev-log.md` | gitignored 版本不共享，未来 Claude 会话看不到 |
| 时间戳错位 | 接受 one-commit lag | 强制 amend 会重写 SHA，破坏 append-only 语义 |

## 四、dev-log.md 文件格式

**Header**：
```markdown
# Rabbit-Hunter Dev Log

> 每个 git commit 自动 append。post-commit hook 生成，无人工整理。
> 与 CHANGELOG.md 的区别：CHANGELOG 是筛选后的人可读版本；dev-log 是全部 commit 的机器可读时间线。
```

**结构**：按月分节（h2 `## YYYY-MM`），新月在上、旧月在下。每月内新条目在上（时间倒序）。

**每行 4 段（`·` 分隔）**：
```
- YYYY-MM-DD · `<sha7>` · +N/-M · <full commit subject>
```

**样例**：
```markdown
## 2026-07

- 2026-07-03 · `0b42f09` · +2/-2 · docs(readme): ASCII 图 V4.3/V4.4 SNIPER/VULTURE → V5Scorer 三 mode
- 2026-07-03 · `1eb344d` · +25/-24 · docs: final review fixes — README /system/mode + SNIPER→v5 modes + 4 minors

## 2026-06

- 2026-06-30 · `<sha>` · +XX/-YY · <subject>
- ...
```

## 五、hook 实现

**位置**: `.githooks/post-commit`（进 git 追踪）

**依赖**: bash + git + awk + grep + mktemp（已确认在 macOS/Linux 默认 shell 上都有）

**核心行为**（伪代码）：
1. 从 `git rev-parse --short HEAD` 取 sha7
2. 从 `git log -1` 取 subject + author-date (YYYY-MM-DD)
3. 从 `git show --shortstat HEAD` 抽 +N/-M
4. 若 `docs/dev-log.md` 不存在 → 建 header
5. 若当前月的 `## YYYY-MM` header 不存在 → 插到内容最顶（在介绍之后、其他月份之前）
6. 在当前月 header 下第一行插入本 commit 的 entry

**具体脚本**：完整代码在 implementation plan 阶段展开。本 spec 只锁定行为约束：
- `set -e`
- 无网络调用
- 无外部依赖（不装任何 npm/pip 包）
- 幂等：同一 commit hook 运行两次不会重复 append（后续 plan 里加"检测 sha7 已存在则跳过"的保护）

**性能约束**：hook 必须在 200ms 内完成（避免 commit 感知延迟）。

## 六、Bootstrap

**首次启用**四步：

1. **建 `.githooks/post-commit`**（可执行，chmod +x）
2. **建 `.githooks/seed-devlog.sh`**：一次性把 `ad19ca1..HEAD` 全部 commits（v0.5.0 之后到本次启用时刻，spec 撰写时约 210 条）灌进 `docs/dev-log.md`（不再往前灌；v0.5.0 之前的历史归 CHANGELOG.md v0.5.0 章节）
3. **建 `CLAUDE.md`（新文件）**，含一段"如何激活 dev-log"：
   ```
   ## dev-log 机制
   本项目用 post-commit hook 自动记录每次 commit 到 docs/dev-log.md。
   激活（一次性）: git config core.hooksPath .githooks
   ```
4. **在 `README.md` 加一小段**（"开发环境"节里）指向 CLAUDE.md 的 setup 说明

**首次自我验证**：seed 完 + 激活 hook 后，做一次空 commit `git commit --allow-empty -m "chore: activate devlog hook"`，观察 `docs/dev-log.md` 是否新增一行。

## 七、Edge cases

| 情况 | 处理 | 备注 |
|---|---|---|
| `git rebase -i` 中每次新 commit | hook 都 fire → 每次都 append | 用户 rebase 完可能想手工整理 dev-log |
| `git cherry-pick` | hook fire，新 SHA 进 log | 老 SHA 的 entry 仍在（如果被 cherry-pick 出去），语义可接受 |
| `git revert X` | hook fire，subject `Revert "..."` 进 log | 一眼可辨 |
| Merge commit | hook fire，subject `Merge branch ...` 进 log | 略噪但可接受 |
| `--amend` | hook fire（新 SHA），老 SHA 的 entry 留在 log 变孤儿 | **CLAUDE.md 里注明**：amend 后手工去掉孤儿行 |
| `--no-verify` | git 尊重，hook 跳过 | 用户明确 opt-out，可接受 |
| dev-log.md 冲突（多分支合并） | 遇到时手工解决 | 单人 solo 项目场景，冲突罕见 |
| Hook 脚本 bug 抛异常 | commit 不受影响（post-commit 后 exit code 不阻断 commit） | 但会打印错误到 stderr，用户能看到 |

## 八、CHANGELOG.md 关系

**Non-goal**：dev-log 不取代 CHANGELOG，也不自动同步到 CHANGELOG。

**Workflow**：
- **每天/每周任何时候**：commit 时自动进 dev-log
- **release 前**（或 audit 时）：人工 review dev-log → 主题聚簇 → append 到 CHANGELOG.md
- **CHANGELOG 章节写完后可以引用 dev-log 时段**（例如 "详见 dev-log 2026-07 段"）作为审计追溯

## 九、Failure modes 与降级

- **Hook 未激活**（用户忘记跑 `git config core.hooksPath .githooks`）→ dev-log 停止更新。检测：Claude 每次开会话时可 `git config --get core.hooksPath` 验证。如返回空，提醒用户激活。
- **Hook 抛错**（比如 dev-log 文件被 chmod 不可写）→ commit 成功但 log 未更新。**No silent failure**：hook 内的 `set -e` 保证错误 stderr 可见。
- **dev-log 被误删**：下次 commit 会自动重建 header（幂等设计的一部分）。历史 entries 丢失需从 git 里 restore。

## 十、验收标准

- `.githooks/post-commit` 存在、可执行、200ms 内跑完
- 一次干净 commit → `docs/dev-log.md` 新增 1 行，格式匹配 § 四
- Bootstrap 完成后 `docs/dev-log.md` 覆盖 v0.5.0 之后全部历史 commits（seed 时 `git log --oneline ad19ca1..HEAD | wc -l` 与 dev-log 行数一致）
- `CLAUDE.md` 存在，内含 setup 说明
- 完整 setup（配置 hooksPath + 空 commit）后能通过 § 六首次自我验证

## 十一、超范围声明

- 本 spec 不含 CHANGELOG.md 的任何自动化
- 本 spec 不含 dev-log 到 remote 的实时同步机制
- 本 spec 不含团队协作场景的冲突解决策略（单人项目）
- 本 spec 不含跨项目共享 hook 的 template 机制（本项目专用）

## 十二、时间线（估算）

| 阶段 | 大致时长 |
|---|---|
| Plan 落地 | 30 min |
| 实现（含测试） | 1-2 小时 |
| Bootstrap + seed 209 commits | 30 min |
| User 验收 | 依用户节奏 |

## 十三、相关

- 前置 spec：`docs/superpowers/specs/2026-07-02-project-audit-and-doc-refresh-design.md` § 5
- 会 co-write：`CLAUDE.md`（新建）、`README.md`（增补一段）
- 不动：`CHANGELOG.md` 结构与内容
