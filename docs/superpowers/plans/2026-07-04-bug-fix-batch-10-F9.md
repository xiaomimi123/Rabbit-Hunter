# Bug Fix Batch 10 · Finding 9 · walkforward 僵尸 job 清理 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `api/routes/v5_walkforward.py` 模块加载时,把 `status IN ('running','queued')` 且 `COALESCE(started_at, created_at) < now - 2h` 的 wf_jobs 标记为 `failed`。防 daemon 线程被杀后 job 永久卡 running。

**Architecture:** 单 task TDD:先写 2 tests(RED —— `_cleanup_stale_jobs` 尚不存在)→ 加函数 + 模块调用 → GREEN → 单 commit。

**Tech Stack:** Python stdlib + pytest tmp_path + sqlite3。无新增 pip 依赖。

## Global Constraints

- Only 2 files touched:
  - `api/routes/v5_walkforward.py` (加 `_cleanup_stale_jobs` 函数 + 模块级调用)
  - `tests/test_v5_walkforward_cleanup.py` (create)
- 函数名 EXACT: `_cleanup_stale_jobs`
- SQL 更新 EXACT:
  - `WHERE status IN ('running','queued') AND COALESCE(started_at, created_at) < datetime('now', '-2 hours')`
  - `SET status='failed', finished_at=datetime('now'), error='进程重启时任务中断 (stale cleanup)'`
- 函数内用 try/except 兜住 Exception,失败打 print WARN,不阻塞 module import
- 模块级 `_ensure_jobs_table()` 后新加 `_cleanup_stale_jobs()` 调用
- 不改 daemon 线程 / 前端 / schema / 其他函数
- 现有 tests 无回归(尤其 F6 的 `test_v5_walkforward_db_path.py` 3/3)
- Single commit, subject EXACT: `fix(v5_walkforward): 模块加载清理僵尸 wf_jobs (Finding 9)`

---

## File Structure

| 路径 | 动作 |
|---|---|
| `api/routes/v5_walkforward.py` | Modify —— 加 `_cleanup_stale_jobs` + 模块调用 |
| `tests/test_v5_walkforward_cleanup.py` | Create —— 2 tests |

---

# Task 1: `_cleanup_stale_jobs` + 模块调用 + 2 tests

**Files:**
- Modify: `api/routes/v5_walkforward.py`
- Create: `tests/test_v5_walkforward_cleanup.py`

**Interfaces:**
- Consumes: pytest `monkeypatch` + `tmp_path` fixtures, sqlite3 stdlib
- Produces: 新 module-level 函数 `_cleanup_stale_jobs()`(无参数,无返回值,幂等)

## RED phase

- [ ] **Step 1: 创建 `tests/test_v5_walkforward_cleanup.py`(2 tests)**

```python
"""Batch 10 Finding 9: 模块加载时把僵尸 wf_jobs 标记为 failed。"""
import sqlite3


def _seed_stale_and_fresh(db_path):
    """建表 + 4 条 job 记录:
    - job_stale_running: status='running', started_at=3h 前 → 应被清理
    - job_stale_queued:  status='queued',  started_at=NULL, created_at=3h 前 → 应被清理
    - job_fresh_running: status='running', started_at=10m 前 → 保留
    - job_done:          status='done',    started_at=3h 前 → 保留(status 不在清理集)
    """
    conn = sqlite3.connect(db_path)
    conn.execute('''
        CREATE TABLE wf_jobs (
            job_id     TEXT PRIMARY KEY,
            status     TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            params     TEXT NOT NULL,
            report_name TEXT,
            error      TEXT,
            stdout_tail TEXT
        )
    ''')
    rows = [
        ('job_stale_running', 'running',
         "datetime('now', '-3 hours')", "datetime('now', '-3 hours')"),
        ('job_stale_queued', 'queued',
         "datetime('now', '-3 hours')", 'NULL'),
        ('job_fresh_running', 'running',
         "datetime('now', '-10 minutes')", "datetime('now', '-10 minutes')"),
        ('job_done', 'done',
         "datetime('now', '-3 hours')", "datetime('now', '-3 hours')"),
    ]
    for job_id, status, created, started in rows:
        conn.execute(
            f"INSERT INTO wf_jobs (job_id, status, created_at, started_at, params) "
            f"VALUES (?, ?, {created}, {started}, '{{}}')",
            (job_id, status)
        )
    conn.commit()
    conn.close()


def test_cleanup_marks_stale_jobs_failed(monkeypatch, tmp_path):
    """僵尸 running/queued(超 2h) → status=failed + error 附说明。"""
    db_path = tmp_path / "test.db"
    _seed_stale_and_fresh(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))

    from api.routes import v5_walkforward
    v5_walkforward._cleanup_stale_jobs()

    conn = sqlite3.connect(str(db_path))
    rows = {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT job_id, status, error FROM wf_jobs")}
    conn.close()

    assert rows['job_stale_running'][0] == 'failed'
    assert '进程重启时任务中断' in rows['job_stale_running'][1]
    assert rows['job_stale_queued'][0] == 'failed'
    assert '进程重启时任务中断' in rows['job_stale_queued'][1]


def test_cleanup_preserves_fresh_and_done(monkeypatch, tmp_path):
    """新鲜 running(<2h) + 已完成 done 应保持不变。"""
    db_path = tmp_path / "test.db"
    _seed_stale_and_fresh(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))

    from api.routes import v5_walkforward
    v5_walkforward._cleanup_stale_jobs()

    conn = sqlite3.connect(str(db_path))
    rows = {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT job_id, status, error FROM wf_jobs")}
    conn.close()

    assert rows['job_fresh_running'][0] == 'running'
    assert rows['job_fresh_running'][1] is None
    assert rows['job_done'][0] == 'done'
    assert rows['job_done'][1] is None
```

- [ ] **Step 2: 跑 tests —— 期望 RED**

```bash
python3 -m pytest tests/test_v5_walkforward_cleanup.py -v
```

Expected: 2/2 FAIL 或 error(`AttributeError: module 'api.routes.v5_walkforward' has no attribute '_cleanup_stale_jobs'`)。

## GREEN phase

- [ ] **Step 3: 加 `_cleanup_stale_jobs()` 函数 + 模块调用**

在 `api/routes/v5_walkforward.py` 中,用 Edit 定位并替换:

**Before**(约 L62,anchor unique):
```python
_ensure_jobs_table()
```

**After**(在 `_ensure_jobs_table` 定义之后、`_ensure_jobs_table()` 调用之前插入函数;然后追加 `_cleanup_stale_jobs()` 调用):

先在 `def _ensure_jobs_table():` 那段结束后、`_ensure_jobs_table()` 调用之前,插入:

```python
def _cleanup_stale_jobs():
    """Finding 9: 模块加载时,把明显超时的 running/queued 任务标记为 failed。

    daemon 线程在 API 进程重启时被杀,wf_jobs 行永久卡 running。
    阈值 2h:单次 walk-forward 正常几分钟内完成,>2h 无更新几乎必是僵尸。
    失败时 print WARN 但不抛,不阻塞 module import。
    """
    try:
        conn = sqlite3.connect(_db_path())
        try:
            conn.execute("""
                UPDATE wf_jobs
                SET status='failed',
                    finished_at=datetime('now'),
                    error='进程重启时任务中断 (stale cleanup)'
                WHERE status IN ('running','queued')
                  AND COALESCE(started_at, created_at) < datetime('now', '-2 hours')
            """)
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[wf cleanup] 启动清理失败: {type(e).__name__}: {e}")
```

然后把原来的 `_ensure_jobs_table()` 单行调用改为两行:
```python
_ensure_jobs_table()
_cleanup_stale_jobs()
```

**具体做法**:用一个 Edit 把 unique anchor 替换掉——

**Before**:
```python
def _ensure_jobs_table():
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wf_jobs (
                job_id     TEXT PRIMARY KEY,
                status     TEXT NOT NULL,    -- queued | running | done | failed
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                params     TEXT NOT NULL,    -- JSON of input params
                report_name TEXT,            -- 成功时填,= reports/{name}.json 不含扩展名
                error      TEXT,             -- 失败时填
                stdout_tail TEXT             -- 最近 4KB stdout
            )
        """)
        conn.commit()
    finally:
        conn.close()


_ensure_jobs_table()
```

**After**:
```python
def _ensure_jobs_table():
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wf_jobs (
                job_id     TEXT PRIMARY KEY,
                status     TEXT NOT NULL,    -- queued | running | done | failed
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                params     TEXT NOT NULL,    -- JSON of input params
                report_name TEXT,            -- 成功时填,= reports/{name}.json 不含扩展名
                error      TEXT,             -- 失败时填
                stdout_tail TEXT             -- 最近 4KB stdout
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _cleanup_stale_jobs():
    """Finding 9: 模块加载时,把明显超时的 running/queued 任务标记为 failed。

    daemon 线程在 API 进程重启时被杀,wf_jobs 行永久卡 running。
    阈值 2h:单次 walk-forward 正常几分钟内完成,>2h 无更新几乎必是僵尸。
    失败时 print WARN 但不抛,不阻塞 module import。
    """
    try:
        conn = sqlite3.connect(_db_path())
        try:
            conn.execute("""
                UPDATE wf_jobs
                SET status='failed',
                    finished_at=datetime('now'),
                    error='进程重启时任务中断 (stale cleanup)'
                WHERE status IN ('running','queued')
                  AND COALESCE(started_at, created_at) < datetime('now', '-2 hours')
            """)
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[wf cleanup] 启动清理失败: {type(e).__name__}: {e}")


_ensure_jobs_table()
_cleanup_stale_jobs()
```

- [ ] **Step 4: 跑 tests —— 期望 GREEN**

```bash
python3 -m pytest tests/test_v5_walkforward_cleanup.py -v
```

Expected: 2/2 PASS

若失败:
- `AttributeError` → 检查函数是否在 module 顶层(不在其他函数内嵌)
- `rows['job_stale_running'][0] != 'failed'` → 检查 SQL 的 status 集合是否含 running
- `rows['job_stale_queued'][0] != 'failed'` → 检查 `COALESCE(started_at, created_at)` 是否正确
- `rows['job_fresh_running'][0] != 'running'` → 检查 2h 时间边界(started_at=-10min 不该匹配)
- `rows['job_done'][0] != 'done'` → 检查 status IN 子句仅含 ('running','queued')

## 邻近回归 + sanity + commit

- [ ] **Step 5: 邻近回归**

```bash
python3 -m pytest tests/test_v5_walkforward_cleanup.py tests/test_v5_walkforward_db_path.py -v
```

Expected: 5/5 pass(2 new + 3 F6)

- [ ] **Step 6: sanity greps**

```bash
# 定义 + 调用各 1
grep -c "_cleanup_stale_jobs" api/routes/v5_walkforward.py
# 期望: 2

# 模块调用在 _ensure_jobs_table() 之后
grep -A1 "^_ensure_jobs_table()" api/routes/v5_walkforward.py
# 期望: 下一行是 _cleanup_stale_jobs()

# SQL 关键部分
grep -c "COALESCE(started_at, created_at)" api/routes/v5_walkforward.py
# 期望: 1
```

- [ ] **Step 7: Commit**

```bash
git add api/routes/v5_walkforward.py tests/test_v5_walkforward_cleanup.py
git commit -m "$(cat <<'EOF'
fix(v5_walkforward): 模块加载清理僵尸 wf_jobs (Finding 9)

修 bug-fix-list.md Finding 9 (P1):walkforward daemon 线程在 API 进程
重启(docker restart / crash)时被强杀,wf_jobs 行永久卡 status='running',
运营无法区分"仍在跑"和"进程已挂"。

Change:
- 新增 _cleanup_stale_jobs():模块加载时把 running/queued 且
  COALESCE(started_at, created_at) 早于 2h 的 job 改为 failed,
  error='进程重启时任务中断 (stale cleanup)'
- 模块级 _ensure_jobs_table() 后调用 _cleanup_stale_jobs()
- 内部 try/except 兜住 sqlite Error,失败打 WARN 不阻塞 API 起动

Tests:
- 新增 tests/test_v5_walkforward_cleanup.py 2 tests
  - stale running + stale queued → 转 failed + error 说明
  - fresh running(<2h) + done 保持不变

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

# Self-Review 记录

- **spec § 四 Change 1 (`_cleanup_stale_jobs` 函数)**: Step 3 ✓
- **spec § 五 Change 2 (模块级调用)**: Step 3 尾部 ✓
- **spec § 六 Change 3 (2 tests)**: Step 1 ✓
- **spec § 七 验收**: Step 4 (2/2) + Step 5 (回归) + Step 6 (sanity) ✓
- **spec § 八 失效模式**: 已声明阈值取舍 + 并发无副作用 ✓
- **spec § 九 鲁棒性**: try/except 在 Step 3 里内嵌 ✓
- **placeholder scan**: 无 TBD ✓
- **type consistency**: `_cleanup_stale_jobs` / SQL text / error message 在 spec + plan + test 一致 ✓
- **测试 RED→GREEN**: Step 2 = RED(AttributeError)；Step 4 = GREEN ✓
- **atomicity**: 单 commit at Step 7 ✓
