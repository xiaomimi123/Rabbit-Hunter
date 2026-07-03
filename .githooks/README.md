# .githooks/

被 `core.hooksPath` 指向的 git hook 目录。**不要在这里放临时脚本** —— 里面所有可执行文件都会被 git 当 hook 触发。

## 现有文件

- `post-commit`：每个 commit 完成后跑，把这个 commit append 到 `docs/dev-log.md`
- `seed-devlog.sh`：一次性历史 seed，`.githooks/seed-devlog.sh <BASE> <HEAD>`
- `lib/update_devlog.py`：单条 entry 插入逻辑（Python stdlib）

## 激活

```bash
git config core.hooksPath .githooks
```

`core.hooksPath` 是本地 git config，不随 clone 同步。**每台开发机需要跑一次**。

## 详细设计

见 `docs/superpowers/specs/2026-07-03-phase2-devlog-mechanism-design.md`。
