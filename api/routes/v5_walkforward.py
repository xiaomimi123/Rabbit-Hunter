"""M6 walk-forward 报告读取 + 触发 API。

GET  /walkforward/reports        — 列出所有报告 (带 KPI 摘要)
GET  /walkforward/reports/{name} — 读完整报告 JSON
POST /walkforward/run            — 触发新 walk-forward 跑,异步,返回 job_id
GET  /walkforward/jobs/{job_id}  — 查任务状态/进度
GET  /walkforward/jobs           — 列最近任务 (含状态)
"""
import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/v5", tags=["walkforward"])


def _reports_dir() -> str:
    return os.environ.get("WF_REPORTS_DIR", "reports")


def _db_path() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


# ─────────────────────────────────────────────────────────────
# Jobs table — 单独建,跟踪 wf 任务状态
# ─────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────


class ReportListItem(BaseModel):
    name: str                # filename without .json
    size_bytes: int
    modified_at: str
    n_oos_trades: Optional[int] = None
    net_avg_r: Optional[float] = None
    net_profit_factor: Optional[float] = None
    kpi_passes_doc_15_2: Optional[bool] = None
    setup_filter: Optional[str] = None
    symbols: Optional[List[str]] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None


class ReportListResponse(BaseModel):
    reports: List[ReportListItem]


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────


@router.get("/walkforward/reports", response_model=ReportListResponse)
async def list_walkforward_reports() -> ReportListResponse:
    """列出所有 reports/wf_*.json,带 KPI 摘要,便于前端一眼看哪个 PASS。"""
    d = _reports_dir()
    if not os.path.isdir(d):
        return ReportListResponse(reports=[])
    items: List[ReportListItem] = []
    for fname in sorted(os.listdir(d), reverse=True):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(d, fname)
        try:
            stat = os.stat(path)
            with open(path, "r") as f:
                data = json.load(f)
            cfg = data.get("config") or {}
            kpi = data.get("pass_doc_kpi") or {}
            items.append(ReportListItem(
                name=fname[:-5],
                size_bytes=stat.st_size,
                modified_at=datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
                n_oos_trades=kpi.get("n_oos_trades"),
                net_avg_r=kpi.get("net_avg_r"),
                net_profit_factor=kpi.get("net_profit_factor"),
                kpi_passes_doc_15_2=kpi.get("kpi_passes_doc_15_2"),
                setup_filter=cfg.get("setup_filter"),
                symbols=cfg.get("symbols"),
                period_start=cfg.get("start_iso"),
                period_end=cfg.get("end_iso"),
            ))
        except (OSError, json.JSONDecodeError, KeyError):
            continue
    return ReportListResponse(reports=items)


@router.get("/walkforward/reports/{name}")
async def get_walkforward_report(name: str):
    """读完整报告 JSON。"""
    if not name.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(400, "invalid name")
    path = os.path.join(_reports_dir(), f"{name}.json")
    if not os.path.isfile(path):
        raise HTTPException(404, f"report {name} not found")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(500, f"read failed: {e}")


# ─────────────────────────────────────────────────────────────
# POST /walkforward/run — 触发新 walk-forward 任务 (异步)
# ─────────────────────────────────────────────────────────────


class RunRequest(BaseModel):
    """前端 BacktestPage 提交的参数。"""
    variant: Literal["A", "B", "C"] = "B"
    start: str = Field(..., description="ISO start, e.g. 2026-01-01T00:00:00Z")
    end: str = Field(..., description="ISO end")
    symbols: List[str] = Field(..., description="e.g. ['NEARUSDT', 'ARBUSDT']")
    train_days: int = 60
    oos_days: int = 14
    step_days: int = 14
    exit_strategy: Literal["baseline", "vegas_full", "vegas_sl_only"] = "baseline"
    max_hold_minutes: int = 480
    cost_preset: Literal["realistic", "optimistic", "pessimistic"] = "realistic"
    cross_threshold_pct: float = 0.0
    a_proximity_pct: float = 0.20


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    params: dict
    report_name: Optional[str] = None
    error: Optional[str] = None
    stdout_tail: Optional[str] = None


class RunResponse(BaseModel):
    job_id: str
    status: str


def _run_wf_subprocess(job_id: str, params: dict):
    """后台线程跑 walk-forward CLI,更新 wf_jobs 表。"""
    conn = sqlite3.connect(_db_path())
    try:
        now = datetime.utcnow().isoformat() + "Z"
        conn.execute(
            "UPDATE wf_jobs SET status='running', started_at=? WHERE job_id=?",
            (now, job_id),
        )
        conn.commit()
    finally:
        conn.close()

    report_name = f"wf_{job_id[:8]}_v{params['variant']}_{params['exit_strategy']}_mh{params['max_hold_minutes']}"
    report_path = os.path.join(_reports_dir(), f"{report_name}.json")
    os.makedirs(_reports_dir(), exist_ok=True)

    cmd = [
        sys.executable, "-m", "scripts.experiments.macd_cross_entry_wf",
        "--variant", params["variant"],
        "--start", params["start"],
        "--end", params["end"],
        "--symbols", ",".join(params["symbols"]),
        "--train-days", str(params["train_days"]),
        "--oos-days", str(params["oos_days"]),
        "--step-days", str(params["step_days"]),
        "--exit-strategy", params["exit_strategy"],
        "--max-hold-minutes", str(params["max_hold_minutes"]),
        "--cost-preset", params["cost_preset"],
        "--cross-threshold-pct", str(params["cross_threshold_pct"]),
        "--a-proximity-pct", str(params["a_proximity_pct"]),
        "--out", report_path,
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
         os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts"),
         env.get("PYTHONPATH", "")]
    )

    stdout_buf = ""
    err_msg = None
    success = False
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env, bufsize=1,
        )
        # 流式读 stdout,保留最后 4KB
        for line in proc.stdout:
            stdout_buf = (stdout_buf + line)[-4096:]
        proc.wait()
        if proc.returncode == 0 and os.path.isfile(report_path):
            success = True
        else:
            err_msg = f"exit code {proc.returncode}"
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"

    # 写回 DB
    conn = sqlite3.connect(_db_path())
    try:
        finished_at = datetime.utcnow().isoformat() + "Z"
        conn.execute(
            "UPDATE wf_jobs SET status=?, finished_at=?, report_name=?, "
            "error=?, stdout_tail=? WHERE job_id=?",
            ("done" if success else "failed",
             finished_at, report_name if success else None,
             err_msg, stdout_buf, job_id),
        )
        conn.commit()
    finally:
        conn.close()


@router.post("/walkforward/run", response_model=RunResponse)
async def run_walkforward(req: RunRequest) -> RunResponse:
    """触发新 walk-forward 跑。
    返回 job_id 即返回 (不等任务完成);前端轮询 /walkforward/jobs/{job_id}。
    """
    if not req.symbols:
        raise HTTPException(400, "symbols 不能为空")
    if req.train_days < 1 or req.oos_days < 1 or req.step_days < 1:
        raise HTTPException(400, "train/oos/step days 必须 ≥ 1")
    if req.max_hold_minutes < 15 or req.max_hold_minutes > 1440:
        raise HTTPException(400, "max_hold_minutes 区间 [15, 1440]")

    job_id = uuid.uuid4().hex
    params_json = json.dumps(req.dict())
    now = datetime.utcnow().isoformat() + "Z"

    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(
            "INSERT INTO wf_jobs (job_id, status, created_at, params) VALUES (?, ?, ?, ?)",
            (job_id, "queued", now, params_json),
        )
        conn.commit()
    finally:
        conn.close()

    # 后台线程跑 (不用 asyncio,因为 subprocess 是阻塞的)
    threading.Thread(
        target=_run_wf_subprocess,
        args=(job_id, req.dict()),
        daemon=True,
    ).start()

    return RunResponse(job_id=job_id, status="queued")


@router.get("/walkforward/jobs/{job_id}", response_model=JobStatus)
async def get_wf_job(job_id: str) -> JobStatus:
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute(
            "SELECT job_id, status, created_at, started_at, finished_at, "
            "params, report_name, error, stdout_tail FROM wf_jobs WHERE job_id=?",
            (job_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "job not found")
        return JobStatus(
            job_id=row[0], status=row[1], created_at=row[2],
            started_at=row[3], finished_at=row[4],
            params=json.loads(row[5]),
            report_name=row[6], error=row[7], stdout_tail=row[8],
        )
    finally:
        conn.close()


class JobListResponse(BaseModel):
    jobs: List[JobStatus]


@router.get("/walkforward/jobs", response_model=JobListResponse)
async def list_wf_jobs(limit: int = 20) -> JobListResponse:
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute(
            "SELECT job_id, status, created_at, started_at, finished_at, "
            "params, report_name, error, stdout_tail FROM wf_jobs "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        jobs = [
            JobStatus(
                job_id=r[0], status=r[1], created_at=r[2],
                started_at=r[3], finished_at=r[4],
                params=json.loads(r[5]),
                report_name=r[6], error=r[7], stdout_tail=r[8],
            )
            for r in cur.fetchall()
        ]
        return JobListResponse(jobs=jobs)
    finally:
        conn.close()
