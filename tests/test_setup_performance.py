"""M8 setup_performance 测试。

覆盖:
- 聚合数学正确
- 状态机:noisy → active / disabled
- n=29 仍 noisy,n=30 触发判定
- 已 disabled 的 setup 反映在 get_disabled_setups
- DEFAULT_DISABLED_SETUPS 永远在结果里
"""
import os
import sqlite3
import tempfile

import pytest

from scripts.risk_constitution import DEFAULT_DISABLED_SETUPS, MIN_SAMPLE_SIZE_FOR_DECISION
from scripts.setup_performance import (
    ensure_table, refresh_setup_performance, get_disabled_setups,
)


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        conn.execute("""
            CREATE TABLE reflections (
                id INTEGER PRIMARY KEY,
                paper_trade_id INTEGER,
                setup_type TEXT,
                outcome_class TEXT,
                realized_r REAL
            )
        """)
        conn.commit()
        conn.close()
        yield path
    finally:
        os.unlink(path)


def _seed(db_path, setup_type, outcomes_and_rs):
    """outcomes_and_rs: list of (outcome_class, realized_r)"""
    conn = sqlite3.connect(db_path)
    for outcome, r in outcomes_and_rs:
        conn.execute(
            "INSERT INTO reflections(setup_type, outcome_class, realized_r) VALUES (?, ?, ?)",
            (setup_type, outcome, r),
        )
    conn.commit()
    conn.close()


# ─── refresh_setup_performance ───────────────────────────────


def test_empty_reflections_returns_empty(db_path):
    result = refresh_setup_performance(db_path)
    assert result == {}


def test_under_30_marked_noisy(db_path):
    """n < 30 → status='noisy',即使 avg_R 很负。"""
    _seed(db_path, "rsi_neutral_macd_extending_short",
          [("LOSS", -1.0)] * 29)
    result = refresh_setup_performance(db_path)
    assert result["rsi_neutral_macd_extending_short"]["sample_count"] == 29
    assert result["rsi_neutral_macd_extending_short"]["status"] == "noisy"


def test_30_negative_avg_marked_disabled(db_path):
    """n ≥ 30 且 avg_R < 0 → status='disabled'。"""
    _seed(db_path, "evil_setup",
          [("LOSS", -1.0)] * 30 + [("WIN", +0.5)] * 5)
    result = refresh_setup_performance(db_path)
    s = result["evil_setup"]
    assert s["sample_count"] == 35
    assert s["status"] == "disabled"
    assert s["disabled_reason"] == "NEGATIVE_EXPECTANCY_30PLUS"


def test_30_positive_avg_marked_active(db_path):
    """n ≥ 30 且 avg_R > 0 → status='active'。"""
    _seed(db_path, "good_setup",
          [("WIN", +2.0)] * 30 + [("LOSS", -1.0)] * 5)
    result = refresh_setup_performance(db_path)
    s = result["good_setup"]
    assert s["sample_count"] == 35
    assert s["status"] == "active"
    assert s["disabled_reason"] is None


def test_avg_math_correct(db_path):
    """avg_realized_r 等于 sum/n。"""
    _seed(db_path, "x", [("WIN", 2.0), ("LOSS", -1.0), ("WIN", 1.0)])
    result = refresh_setup_performance(db_path)
    assert result["x"]["avg_realized_r"] == pytest.approx(2.0 / 3)
    assert result["x"]["total_realized_r"] == 2.0


def test_win_loss_scratch_counts(db_path):
    _seed(db_path, "x", [("WIN", 1), ("WIN", 1), ("LOSS", -1), ("SCRATCH", 0)])
    result = refresh_setup_performance(db_path)
    assert result["x"]["win_count"] == 2
    assert result["x"]["loss_count"] == 1
    assert result["x"]["scratch_count"] == 1


def test_rerun_updates_existing_row(db_path):
    """二次 refresh 应当 UPDATE 而非 INSERT,主键 setup_type 不重复。"""
    _seed(db_path, "x", [("LOSS", -1.0)] * 30)
    refresh_setup_performance(db_path)
    _seed(db_path, "x", [("WIN", +2.0)] * 20)  # 加 20 笔胜
    result = refresh_setup_performance(db_path)
    assert result["x"]["sample_count"] == 50
    # avg = (-30 + 40)/50 = 0.2 → 正期望 → active
    assert result["x"]["status"] == "active"


# ─── get_disabled_setups ───────────────────────────────


def test_disabled_setups_always_contain_defaults():
    """文档 §4 默认禁用清单永远在,即使无 DB。"""
    disabled = get_disabled_setups(db_path=None)
    for k in DEFAULT_DISABLED_SETUPS:
        assert k in disabled


def test_disabled_setups_with_no_table(db_path):
    """DB 没建过 setup_performance 表也要 graceful。"""
    disabled = get_disabled_setups(db_path=db_path)
    for k in DEFAULT_DISABLED_SETUPS:
        assert k in disabled


def test_disabled_setups_includes_auto_disabled(db_path):
    """DB 里 status='disabled' 的 setup 进入返回集。"""
    _seed(db_path, "killer", [("LOSS", -1.0)] * 30)
    refresh_setup_performance(db_path)
    disabled = get_disabled_setups(db_path=db_path)
    assert "killer" in disabled
    # 默认禁用清单也在
    for k in DEFAULT_DISABLED_SETUPS:
        assert k in disabled


def test_active_setup_not_in_disabled(db_path):
    _seed(db_path, "winner", [("WIN", 2.0)] * 30)
    refresh_setup_performance(db_path)
    disabled = get_disabled_setups(db_path=db_path)
    assert "winner" not in disabled
