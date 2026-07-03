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
| [architecture-map.md](./architecture-map.md) | ✅ 已生成 |
| [dead-code-and-tables.md](./dead-code-and-tables.md) | ✅ 已生成 |
| [tech-debt.md](./tech-debt.md) | ✅ 已生成 |
| [doc-vs-code-diff.md](./doc-vs-code-diff.md) | 待生成 |

## 前置条件

生成本次 audit 时使用的锚点：

- Git HEAD: `d894917`
- v0.5.0 参照 commit: `ad19ca1`
- DB 快照时间: `2026-07-02T15:44:29Z`

## 局限性

- 单线扫，未做 workflow 多 agent 交叉验证
- 前端只覆盖 `Rabbit Hunterfronted/`，不含 `node_modules` 或 build 产物
- Tech-debt 仅为观察，不含修复方案（那属于后续 spec）
