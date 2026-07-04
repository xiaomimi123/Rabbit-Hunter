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
