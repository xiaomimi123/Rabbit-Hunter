# Bug Fix Batch 10 · Finding 9 · walkforward 僵尸 job 启动清理 · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 9 (P1)

---

## 一、问题陈述

`api/routes/v5_walkforward.py:284-288`:

```python
threading.Thread(target=_run_wf_subprocess, args=(job_id, params, ...), daemon=True).start()
```

- Python daemon 线程在主进程退出时被强制终止,不做任何清理
- `_run_wf_subprocess` 只在 subprocess 完/失败后才写 `wf_jobs.status='done'/'failed'`
- 若 `docker restart` 或 API 崩溃:daemon 被杀 + subprocess 被孤立 → `wf_jobs` 该行永久卡在 `status='running'`
- `GET /walkforward/jobs/{job_id}` 返 `running`,运营无法区分"仍在跑"和"进程已挂"

## 二、目标

API 模块加载时,把所有 `status IN ('running','queued')` 且已明显超时(>2 小时)的 job 一并标记为 `failed`,附错误说明 `进程重启时任务中断 (stale cleanup)`。运营重启后立即看到失败标记,不再迷惑。

## 三、范围

**In scope**:
- `api/routes/v5_walkforward.py` 加 `_cleanup_stale_jobs()` 函数
- 模块级 `_ensure_jobs_table()` 后新增 `_cleanup_stale_jobs()` 调用
- 新增单测 `tests/test_v5_walkforward_cleanup.py`(2 tests)

**Out of scope**:
- 不改 daemon 线程本身(daemon 语义就是主进程死时被杀,那是 Python 特性)
- 不做子进程清理(操作系统已回收)
- 不改 API 前端(前端只看 `wf_jobs.status`,新语义完全兼容)
- 不加"仍在跑"的心跳检测(YAGNI,时间阈值足够)
- 不改 SQLite schema

## 四、Change 1 — `api/routes/v5_walkforward.py` 加 `_cleanup_stale_jobs()`

**位置**:紧跟 `_ensure_jobs_table()` 之后。

```python
def _cleanup_stale_jobs():
    """Finding 9: 模块加载时,把明显超时的 running/queued 任务标记为 failed。

    daemon 线程在 API 进程重启时被杀,wf_jobs 行永久卡 running。
    阈值 2h:单次 walk-forward 正常几分钟内完成,>2h 无更新几乎必是僵尸。
    """
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
```

## 五、Change 2 — 模块加载调用

**Before**(L62):
```python
_ensure_jobs_table()
```

**After**:
```python
_ensure_jobs_table()
_cleanup_stale_jobs()
```

## 六、Change 3 — 新单测 `tests/test_v5_walkforward_cleanup.py`

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

## 七、验收标准

- `python3 -m pytest tests/test_v5_walkforward_cleanup.py -v` → 2/2 pass
- `python3 -m pytest tests/test_v5_walkforward_db_path.py -v` → 3/3 pass(F6 不回归)
- `grep -c "_cleanup_stale_jobs" api/routes/v5_walkforward.py` → 2(定义 + 调用)
- 只 stage 2 文件(`api/routes/v5_walkforward.py` + `tests/test_v5_walkforward_cleanup.py`)
- Commit subject EXACT: `fix(v5_walkforward): 模块加载清理僵尸 wf_jobs (Finding 9)`

## 八、失效模式

- **阈值 2h 太短**:极端复杂的 walk-forward 可能跑 3h+。可接受:该场景应改用异步 subprocess + PID 存活检测(更大改动,YAGNI 到有真实需求)。当前阈值下,大部分场景 running 都在几分钟内。若真发生误清理,操作员看到 `error='...stale cleanup'` 会立刻明白,人手 rerun 即可。
- **阈值 2h 太长**:短暂重启后,前 2h 内 running 记录仍显示 running,前端可能误以为"还在跑"。可接受:重启很少见,且前端可加人手 refresh 或后续加心跳(不在本 fix 范围)。
- **DB 锁定**:模块加载时若 DB 被其他进程独占,`_cleanup_stale_jobs()` 会抛 OperationalError,导致 module import 失败 → API 起不来。**缓解**:catch + print WARN,不让清理阻塞启动。见下方 § 九。
- **并发**:同时多个 API 进程启动(k8s replicas)→ 多个进程各自跑清理,SQLite 有内置 write lock,UPDATE 是幂等的,无副作用。

## 九、鲁棒性:catch 清理异常不阻塞启动

`_cleanup_stale_jobs()` 内部 `try/except` 兜住 sqlite3.Error,失败时打 WARN 继续,不让 API 起不来:

```python
def _cleanup_stale_jobs():
    """Finding 9 ..."""
    try:
        conn = sqlite3.connect(_db_path())
        try:
            conn.execute("""
                UPDATE wf_jobs
                SET status='failed', finished_at=datetime('now'),
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

## 十、超范围声明

- 不改 daemon 线程语义
- 不加子进程 PID 持久化
- 不加运行时心跳
- 不改前端(前端只看 status/error,兼容)
- 不改 SQLite schema

## 十一、相关

- Bug audit: `docs/audit-2026-07/bug-fix-list.md` Finding 9 (P1)
- 引用:
  - `api/routes/v5_walkforward.py:41-62`(`_ensure_jobs_table` + 模块加载)
  - `api/routes/v5_walkforward.py:284-288`(daemon 线程创建)
- 相关 Finding: Finding 6 (Batch 8) —— walkforward DB_PATH 已统一
