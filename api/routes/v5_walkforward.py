"""M6 walk-forward 报告读取 API。

将 reports/wf_*.json 暴露给前端 BacktestPage。
报告生成走 CLI:
    python -m scripts.walkforward --start ... --end ... --out reports/wf_X.json
"""
import json
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/api/v5", tags=["walkforward"])


def _reports_dir() -> str:
    return os.environ.get("WF_REPORTS_DIR", "reports")


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
