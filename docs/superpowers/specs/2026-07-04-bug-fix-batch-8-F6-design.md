# Bug Fix Batch 8 · Finding 6 · LOCAL_DB_PATH → DB_PATH · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 6 (P1)

---

## 一、问题陈述

`api/routes/v5_walkforward.py:33`:

```python
def _db_path() -> str:
    return os.environ.get("LOCAL_DB_PATH", "data/rabbit_hunter.db")
```

其他 15+ API 路由文件（如 `v5_signals.py` / `v5_positions.py` / `v5_strategy_config.py`）都用 `os.environ.get("DB_PATH", "data/rabbit_hunter.db")`。当运维 `export DB_PATH=data/custom.db` 后:

- `POST /api/v5/walkforward/run` 将 `wf_jobs` 写入 `data/rabbit_hunter.db`（因 `LOCAL_DB_PATH` 未设）
- `GET /api/v5/signals`、`GET /api/v5/positions` 全部读 `data/custom.db`
- 逻辑上是两个 DB —— walkforward 结果与主业务数据完全隔离，运维不易察觉

## 二、目标

统一 walkforward 路由的 DB 定位到 `DB_PATH` env var，与其他路由保持一致。

## 三、范围

**In scope**：
- `api/routes/v5_walkforward.py:33` env key 从 `LOCAL_DB_PATH` 改为 `DB_PATH`
- 追加 1 test 覆盖 `DB_PATH` 生效路径

**Out of scope**：
- 不改 default fallback `"data/rabbit_hunter.db"`
- 不改 `_reports_dir()`（用的是 `WF_REPORTS_DIR`，与本 Finding 无关）
- 不改其他文件（grep 已确认 `LOCAL_DB_PATH` 只在此 1 处代码 + audit docs 里）
- 不做 backward-compat（`LOCAL_DB_PATH` 在生产未见使用，audit 建议直接换）
- 不改 audit docs 里的原文引用（tech-debt.md L37 是在描述当前 buggy 状态，保留引用可读性）

## 四、Change 1 — `api/routes/v5_walkforward.py:33`

**Before**：
```python
def _db_path() -> str:
    return os.environ.get("LOCAL_DB_PATH", "data/rabbit_hunter.db")
```

**After**：
```python
def _db_path() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")
```

## 五、Change 2 — 新增测试 `tests/test_v5_walkforward_db_path.py`

```python
"""Batch 8 Finding 6: walkforward 路由 DB 定位统一到 DB_PATH env var。"""
import os


def test_db_path_reads_db_path_env(monkeypatch):
    """_db_path() 应读 DB_PATH env,与其他 API 路由一致(Finding 6)。"""
    monkeypatch.setenv("DB_PATH", "data/custom_test.db")
    monkeypatch.delenv("LOCAL_DB_PATH", raising=False)

    from api.routes import v5_walkforward
    assert v5_walkforward._db_path() == "data/custom_test.db"


def test_db_path_ignores_local_db_path_env(monkeypatch):
    """老 LOCAL_DB_PATH env 不再生效,防回归(Finding 6)。"""
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.setenv("LOCAL_DB_PATH", "data/should_be_ignored.db")

    from api.routes import v5_walkforward
    # 无 DB_PATH → fallback 到 default,不能读 LOCAL_DB_PATH
    assert v5_walkforward._db_path() == "data/rabbit_hunter.db"


def test_db_path_default_when_unset(monkeypatch):
    """两个 env 都不设时,返回 default(Finding 6)。"""
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("LOCAL_DB_PATH", raising=False)

    from api.routes import v5_walkforward
    assert v5_walkforward._db_path() == "data/rabbit_hunter.db"
```

## 六、验收标准

- `python3 -m pytest tests/test_v5_walkforward_db_path.py -v` → 3/3 pass
- `grep -n "LOCAL_DB_PATH" api/` → 0 hits
- `grep -c 'os.environ.get("DB_PATH"' api/routes/v5_walkforward.py` → ≥1
- 只 stage 2 文件（`api/routes/v5_walkforward.py` + `tests/test_v5_walkforward_db_path.py`）
- 邻近 tests 无回归：与 walkforward 相关的现有 tests 不动
- Commit subject EXACT: `fix(v5_walkforward): _db_path() 改读 DB_PATH env,与其他路由统一 (Finding 6)`

## 七、失效模式

- **老运维仍 export `LOCAL_DB_PATH`**：该 env 从此被忽略,walkforward 会落到 default `data/rabbit_hunter.db`（与主库一致）。属于对齐,而非新故障。若担心,可在部署 CHANGELOG 里加一行提醒。
- **测试环境有 stale `DB_PATH` env**：monkeypatch 已用 `setenv` / `delenv` 隔离,不会污染。

## 八、超范围声明

- 不改 wf_jobs schema
- 不改 daemon 线程逻辑（那是 Finding 9)
- 不改 `_reports_dir()`
- 不加 backward-compat 读 LOCAL_DB_PATH

## 九、相关

- Bug audit: `docs/audit-2026-07/bug-fix-list.md` Finding 6 (P1)
- 引用：`api/routes/v5_walkforward.py:33`
- 相关 Finding: Finding 9（walkforward daemon 僵尸 job）—— 下一 batch
