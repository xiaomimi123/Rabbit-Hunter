# Bug Fix Batch 8 · Finding 6 · walkforward _db_path 改读 DB_PATH · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `api/routes/v5_walkforward.py:33` 的 env key 从 `LOCAL_DB_PATH` 改为 `DB_PATH`，与其他 API 路由文件一致。

**Architecture:** 单 task TDD 循环：先写 3 test（RED — 老代码读 LOCAL_DB_PATH，新期望读 DB_PATH）→ 改 1 词 → GREEN → 单 commit。

**Tech Stack:** Python stdlib + pytest monkeypatch。无新增 pip 依赖。

## Global Constraints

- Only 2 files touched: `api/routes/v5_walkforward.py` (modify) + `tests/test_v5_walkforward_db_path.py` (create)
- 改动仅限 L33：`LOCAL_DB_PATH` → `DB_PATH`
- Default fallback `"data/rabbit_hunter.db"` 不变
- 不改 `_reports_dir()`（不同 env, 无关）
- 不加 backward-compat 读 LOCAL_DB_PATH
- 不改 audit docs 里的历史引用（tech-debt.md L37 是历史现状记录）
- 邻近 tests 无回归：
  - `tests/test_v5_walkforward*.py`（若已存在）保持
  - 其他 `test_v5_*.py` 无关，无回归
- Single commit, subject EXACT: `fix(v5_walkforward): _db_path() 改读 DB_PATH env,与其他路由统一 (Finding 6)`

---

## File Structure

| 路径 | 动作 |
|---|---|
| `api/routes/v5_walkforward.py` | Modify L33 —— 单词换 |
| `tests/test_v5_walkforward_db_path.py` | Create —— 3 tests |

---

# Task 1: _db_path() 换 env key + 3 tests

**Files:**
- Modify: `api/routes/v5_walkforward.py`
- Create: `tests/test_v5_walkforward_db_path.py`

**Interfaces:**
- Consumes: pytest `monkeypatch` fixture (设 env)
- Produces: 无新 API；`_db_path()` 语义变化：只认 `DB_PATH` 不认 `LOCAL_DB_PATH`

## RED phase

- [ ] **Step 1: 创建 `tests/test_v5_walkforward_db_path.py`（3 tests）**

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

- [ ] **Step 2: 跑 tests —— 期望 RED**

```bash
python3 -m pytest tests/test_v5_walkforward_db_path.py -v
```

Expected:
- `test_db_path_reads_db_path_env` FAIL —— 老代码读 LOCAL_DB_PATH，DB_PATH 被忽略，返回 default
- `test_db_path_ignores_local_db_path_env` FAIL —— 老代码读 LOCAL_DB_PATH，返回 `"data/should_be_ignored.db"` 而非 default
- `test_db_path_default_when_unset` PASS（default fallback 两代码都对）

至少 2/3 FAIL。

## GREEN phase

- [ ] **Step 3: 改 `api/routes/v5_walkforward.py:33`**

用 Edit：unique substring anchor `os.environ.get("LOCAL_DB_PATH", "data/rabbit_hunter.db")`。

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

- [ ] **Step 4: 跑 tests —— 期望 GREEN**

```bash
python3 -m pytest tests/test_v5_walkforward_db_path.py -v
```

Expected: 3/3 PASS

若失败：
- Test 1 FAIL → 检查 env key 是否真的改成了 `"DB_PATH"`
- Test 2 FAIL → 检查是否残留 `LOCAL_DB_PATH` 分支（应该没有）
- Test 3 FAIL → 检查 default 字符串是否被误改

## 邻近回归 + sanity + commit

- [ ] **Step 5: 邻近 tests 无回归**

```bash
# 若 test_v5_walkforward.py 存在,跑一遍
find tests -name "test_v5_walkforward*.py" -type f
python3 -m pytest tests/test_v5_walkforward_db_path.py -v 2>&1 | tail -10
# 若还有 test_v5_walkforward*.py 其他文件,一并跑
```

Expected: 无 test 因此改动 FAIL。

- [ ] **Step 6: sanity greps**

```bash
# 老 env key 从 api/ 消失
grep -rn "LOCAL_DB_PATH" api/ 2>&1
# 期望：0 hits

# 新 env key 到位
grep -n 'os.environ.get("DB_PATH"' api/routes/v5_walkforward.py
# 期望：1 hit（L33)

# 与其他路由格式一致
grep -c 'os.environ.get("DB_PATH", "data/rabbit_hunter.db")' api/routes/v5_walkforward.py
# 期望：1
```

- [ ] **Step 7: Commit**

```bash
git add api/routes/v5_walkforward.py tests/test_v5_walkforward_db_path.py
git commit -m "$(cat <<'EOF'
fix(v5_walkforward): _db_path() 改读 DB_PATH env,与其他路由统一 (Finding 6)

修 bug-fix-list.md Finding 6 (P1):api/routes/v5_walkforward.py:33
单独用 LOCAL_DB_PATH env,其他 15+ 路由文件均用 DB_PATH。运维
export DB_PATH=data/custom.db 时,walkforward 会落到 default
data/rabbit_hunter.db 而非 custom 路径,形成两个逻辑 DB 断层。

Change:
- os.environ.get("LOCAL_DB_PATH", ...) → os.environ.get("DB_PATH", ...)
- default fallback "data/rabbit_hunter.db" 保持

Tests:
- 新增 tests/test_v5_walkforward_db_path.py 3 tests
  - DB_PATH env 生效
  - LOCAL_DB_PATH env 被忽略(防回归)
  - 两 env 都不设时返 default

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

# Self-Review 记录

- **spec § 四 Change 1**: Step 3 ✓
- **spec § 五 Change 2 (3 tests)**: Step 1 完整 ✓
- **spec § 六 验收**: Step 4 (3/3) + Step 5 (回归) + Step 6 (sanity) ✓
- **placeholder scan**: 无 TBD ✓
- **type consistency**: env key `DB_PATH` 在 spec + plan + test 一致 ✓
- **测试 RED→GREEN**: Step 2 = RED (2/3 fail)；Step 4 = GREEN (3/3) ✓
- **atomicity**: 单 commit at Step 7 ✓
