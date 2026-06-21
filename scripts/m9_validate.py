"""M9 候选规则 walk-forward 验证管线。

依据:文档 §11 第 3 步 + §15 KPI #2 #3。

trigger_validation(candidate_id):
  1. 取候选规则的 rule_spec_json
  2. 若 spec 指明 setup_type_name → 用 --setup-filter 跑 WF
  3. 把 WF 报告路径回写到 candidate
  4. 根据 pass_doc_kpi 写 kpi_passes 标记

简化:此版本只支持把 setup_type_name 直接交给 walkforward(因为现有 backtest engine
就是按 V5 策略派生 setup_type)。后续 M9.4 接入"规则注入参数"时,本函数会被扩展。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import List, Optional

from scripts.backtest.cost_model import COST_REALISTIC
from scripts.m9_knowledge import get_candidate, record_validation
from scripts.walkforward import (
    WalkForwardConfig,
    run_walkforward,
)


def _utcnow_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def trigger_validation(
    *,
    db_path: str,
    candidate_id: int,
    start_iso: str,
    end_iso: str,
    symbols: List[str],
    train_days: int = 30,
    oos_days: int = 14,
    step_days: int = 14,
    cache_root: str = "data/backtest_cache",
    reports_dir: str = "reports",
) -> dict:
    """同步跑 walk-forward,把报告路径 + KPI 标记落回 candidate。

    返回 {wf_report_path, kpi_passes, n_oos_trades, net_avg_r, net_profit_factor}
    """
    candidate = get_candidate(db_path, candidate_id)
    if not candidate:
        raise ValueError(f"candidate {candidate_id} not found")

    spec = json.loads(candidate["rule_spec_json"])
    setup_filter = spec.get("setup_type_name")

    out_name = f"m9_cand_{candidate_id}_{_utcnow_slug()}.json"
    out_path = os.path.join(reports_dir, out_name)
    os.makedirs(reports_dir, exist_ok=True)

    cfg = WalkForwardConfig(
        start_iso=start_iso, end_iso=end_iso,
        symbols=symbols,
        train_days=train_days, oos_days=oos_days, step_days=step_days,
        cache_root=cache_root, db_path=db_path,
        cost_config=COST_REALISTIC,
        setup_filter=setup_filter,
        quiet=True,
    )
    report = run_walkforward(cfg)
    with open(out_path, "w") as f:
        f.write(report.to_json())

    kpi = report.pass_doc_kpi
    record_validation(
        db_path, candidate_id,
        wf_report_path=out_name,
        kpi_passes=bool(kpi["kpi_passes_doc_15_2"]),
    )

    return {
        "wf_report_path": out_name,
        "kpi_passes": kpi["kpi_passes_doc_15_2"],
        "n_oos_trades": kpi["n_oos_trades"],
        "net_avg_r": kpi["net_avg_r"],
        "net_profit_factor": kpi["net_profit_factor"],
    }


__all__ = ["trigger_validation"]
