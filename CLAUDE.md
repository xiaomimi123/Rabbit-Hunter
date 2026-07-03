# Claude Code · Rabbit-Hunter 项目指令

> 项目层 Claude Code instructions。会话开始时自动加载。

## dev-log 机制

**首次启用（每台开发机跑一次）：**

```bash
git config core.hooksPath .githooks
```

激活后每个 `git commit` 会自动 append 一行到 `docs/dev-log.md`。若你 (Claude) 或用户观察到多个 commit 落下但 dev-log 没更新，先检查：

```bash
git config --get core.hooksPath
```

应输出 `.githooks`。若为空，运行上面的激活命令。

## dev-log 使用规范

- `docs/dev-log.md` 是**机器生成的时间线**，覆盖 v0.5.0 之后每个 commit。**不手工编辑**
- 手工筛选 + 主题聚簇的版本走 `CHANGELOG.md`（release-level）
- 需要回顾 v0.5.0 之后某段时间做了什么 → 读 dev-log
- 需要给外部读者讲 v0.5.x → HEAD 的 narrative → 读 / 更新 CHANGELOG

## Amend caveat

`git commit --amend` 会生成新 SHA。post-commit hook 会为 amend 后的新 commit 再 append 一行，**老 SHA 的孤儿 entry 仍在 dev-log**。amend 后请手工去掉孤儿行（搜索老 SHA7 删除对应行）。

## `--no-verify`

`git commit --no-verify` 会跳过 post-commit hook，该 commit 不进 dev-log。当且仅当你 (Claude) 或用户明确要求 opt-out 时使用。

## 相关文档

- 设计: `docs/superpowers/specs/2026-07-03-phase2-devlog-mechanism-design.md`
- 实施 plan: `docs/superpowers/plans/2026-07-03-phase2-devlog-mechanism.md`
- 项目结构: `PROJECT_STRUCTURE.md`
