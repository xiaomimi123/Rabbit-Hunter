"""M9 验证管线测试 — mock walkforward 测控制流。"""
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from scripts.m9_knowledge import (
    add_candidate_rule, ensure_tables, get_candidate,
)


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        ensure_tables(path)
        yield path
    finally:
        os.unlink(path)


def _fake_report(passes: bool, n: int = 30) -> MagicMock:
    rep = MagicMock()
    rep.pass_doc_kpi = {
        "kpi_passes_doc_15_2": passes,
        "n_oos_trades": n,
        "net_avg_r": 0.5 if passes else -0.2,
        "net_profit_factor": 1.6 if passes else 0.8,
    }
    rep.to_json = MagicMock(return_value=json.dumps({"pass_doc_kpi": rep.pass_doc_kpi}))
    return rep


def test_trigger_validation_passing_setup_marks_validated(db_path, tmp_path):
    """WF 通过 → candidate.status='validated', kpi_passes=1。"""
    cid = add_candidate_rule(
        db_path, name="x",
        rule_spec={"setup_type_name": "test_setup", "side": "LONG"},
    )
    from scripts.m9_validate import trigger_validation

    with patch("scripts.m9_validate.run_walkforward",
               return_value=_fake_report(passes=True)) as mock_wf:
        result = trigger_validation(
            db_path=db_path, candidate_id=cid,
            start_iso="2026-01-01", end_iso="2026-03-01",
            symbols=["BTC/USDT"],
            reports_dir=str(tmp_path),
        )

    mock_wf.assert_called_once()
    # 检查 setup_filter 被传入
    call_cfg = mock_wf.call_args[0][0]
    assert call_cfg.setup_filter == "test_setup"

    # candidate 状态
    c = get_candidate(db_path, cid)
    assert c["status"] == "validated"
    assert c["kpi_passes"] == 1
    assert c["wf_report_path"] is not None
    assert result["kpi_passes"] is True


def test_trigger_validation_failing_marks_kpi_zero(db_path, tmp_path):
    cid = add_candidate_rule(
        db_path, name="overfit",
        rule_spec={"setup_type_name": "bad_setup"},
    )
    from scripts.m9_validate import trigger_validation
    with patch("scripts.m9_validate.run_walkforward",
               return_value=_fake_report(passes=False)):
        trigger_validation(
            db_path=db_path, candidate_id=cid,
            start_iso="2026-01-01", end_iso="2026-03-01",
            symbols=["BTC/USDT"],
            reports_dir=str(tmp_path),
        )
    c = get_candidate(db_path, cid)
    assert c["status"] == "validated"
    assert c["kpi_passes"] == 0


def test_trigger_validation_writes_report_file(db_path, tmp_path):
    cid = add_candidate_rule(db_path, name="x", rule_spec={"setup_type_name": "s"})
    from scripts.m9_validate import trigger_validation
    with patch("scripts.m9_validate.run_walkforward",
               return_value=_fake_report(passes=True)):
        result = trigger_validation(
            db_path=db_path, candidate_id=cid,
            start_iso="2026-01-01", end_iso="2026-03-01",
            symbols=["BTC/USDT"],
            reports_dir=str(tmp_path),
        )
    # 报告文件名落在 tmp_path
    full = tmp_path / result["wf_report_path"]
    assert full.exists()
    saved = json.loads(full.read_text())
    assert saved["pass_doc_kpi"]["kpi_passes_doc_15_2"] is True


def test_trigger_validation_missing_candidate_raises(db_path, tmp_path):
    from scripts.m9_validate import trigger_validation
    with pytest.raises(ValueError, match="not found"):
        trigger_validation(
            db_path=db_path, candidate_id=999,
            start_iso="2026-01-01", end_iso="2026-03-01",
            symbols=["BTC/USDT"],
            reports_dir=str(tmp_path),
        )
