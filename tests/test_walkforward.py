"""M6 walk-forward 测试。

覆盖:
- generate_windows 拆分逻辑
- 短/长窗口、不能整除场景
- run_walkforward 端到端(用 mocked BacktestRunner)
- 文档 §15 KPI 判定逻辑
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from scripts.backtest.cost_model import COST_OPTIMISTIC, COST_REALISTIC
from scripts.backtest.schemas import BacktestEntry
from scripts.walkforward import (
    WalkForwardConfig,
    WindowSpec,
    generate_windows,
    run_walkforward,
)


# ─── generate_windows ─────────────────────────


def test_windows_simple_60_14_14():
    """60 天训练 + 14 天 OOS + 14 天 step 滚动 90 天。

    第一个窗口:train [day 0, 60),oos [60, 74)
    第二个:train [14, 74),oos [74, 88)
    第三个:oos_end = 102 > end(90) → 停。
    """
    windows = generate_windows(
        start_iso="2026-01-01", end_iso="2026-04-01",  # ~90 天
        train_days=60, oos_days=14, step_days=14,
    )
    assert len(windows) >= 1
    w0 = windows[0]
    assert w0.train_start.startswith("2026-01-01")
    # train_end ≈ 60 天后
    assert w0.train_end.startswith("2026-03-02")
    # oos_end ≈ 14 天后
    assert w0.oos_end.startswith("2026-03-16")


def test_windows_no_room_returns_empty():
    """train_days + oos_days > total → 0 个窗口。"""
    windows = generate_windows(
        start_iso="2026-01-01", end_iso="2026-01-10",
        train_days=60, oos_days=14, step_days=14,
    )
    assert windows == []


def test_windows_rolling_overlap():
    """两个窗口 train 段重叠,oos 不重叠。"""
    windows = generate_windows(
        start_iso="2026-01-01", end_iso="2026-05-01",
        train_days=60, oos_days=14, step_days=14,
    )
    # 至少 4 个滚动窗口
    assert len(windows) >= 3
    # 相邻 OOS 不重叠
    for a, b in zip(windows[:-1], windows[1:]):
        assert a.oos_end <= b.oos_start


# ─── run_walkforward end-to-end (mocked) ─────────────────────────


def _make_entry(realized_r: float, sl_price: float = 98.0) -> BacktestEntry:
    return BacktestEntry(
        symbol="X/USDT", side="LONG", setup_type="test",
        entry_time="2026-01-01T00:00:00+00:00", entry_price=100.0,
        sl_price=sl_price, tp_price=103.0,
        exit_time="2026-01-01T01:00:00+00:00", exit_price=103.0,
        exit_reason="TP_HIT", realized_r=realized_r,
        holding_minutes=60, funding_z_at_entry=None,
        rsi_15m_at_entry=50.0, macd_hist_15m_at_entry=0.0,
    )


def test_run_walkforward_combines_oos_and_passes_kpi():
    """所有 OOS 都是 +1.5R 胜单 → net PF 仍 > 1。"""
    cfg = WalkForwardConfig(
        start_iso="2026-01-01", end_iso="2026-05-01",
        symbols=["X/USDT"],
        train_days=60, oos_days=14, step_days=14,
        cost_config=COST_OPTIMISTIC,    # 无滑点,只扣 maker fee
    )

    fake_entries = [_make_entry(+1.5) for _ in range(20)]

    with patch("scripts.walkforward.run_window_oos", return_value=fake_entries):
        report = run_walkforward(cfg)

    assert len(report.windows) >= 1
    # 拼接后 OOS entries
    n_windows = len(report.windows)
    assert len(report.oos_combined_entries) == 20 * n_windows
    # gross
    assert report.oos_summary["n"] == 20 * n_windows
    assert report.oos_summary["avg_r"] == pytest.approx(1.5)
    # net 视图存在
    assert report.oos_summary_net["n"] == 20 * n_windows
    # 扣成本后 avg_R 略低但仍正
    assert report.oos_summary_net["avg_r"] < 1.5
    assert report.oos_summary_net["avg_r"] > 0
    # KPI 通过
    assert report.pass_doc_kpi["kpi_passes_doc_15_2"] is True


def test_run_walkforward_fails_kpi_on_overfit_setup():
    """50% win @ +1R / 50% loss @ -1R(gross break-even)→ 扣成本后变负。"""
    cfg = WalkForwardConfig(
        start_iso="2026-01-01", end_iso="2026-03-01",
        symbols=["X/USDT"],
        train_days=30, oos_days=7, step_days=7,
        cost_config=COST_REALISTIC,
    )
    wins = [_make_entry(+1.0) for _ in range(10)]
    losses = [_make_entry(-1.0) for _ in range(10)]
    with patch("scripts.walkforward.run_window_oos", return_value=wins + losses):
        report = run_walkforward(cfg)

    # gross avg ≈ 0 → PF = 1.0
    # net 扣完手续费 + 滑点 → 必定 < 0
    assert report.pass_doc_kpi["gross_profit_factor"] == pytest.approx(1.0)
    assert report.pass_doc_kpi["net_avg_r"] < 0
    assert report.pass_doc_kpi["kpi_passes_doc_15_2"] is False


def test_run_walkforward_filters_by_setup():
    """setup_filter 只统计指定 setup。"""
    cfg = WalkForwardConfig(
        start_iso="2026-01-01", end_iso="2026-03-01",
        symbols=["X/USDT"],
        train_days=30, oos_days=7, step_days=7,
        setup_filter="rsi_oversold_macd_extending_long",
    )
    # 模拟时已经被 run_window_oos 自己过滤了,这里 mock 返回过滤后的结果。
    target_entries = [_make_entry(+2.0) for _ in range(5)]
    with patch("scripts.walkforward.run_window_oos", return_value=target_entries):
        report = run_walkforward(cfg)
    # 全是 setup_type='test'(_make_entry 默认),但因为 run_window_oos 已经
    # 模拟过滤过了,这里只验证 entries 数量
    assert report.oos_summary["n"] == 5 * len(report.windows)


def test_run_walkforward_with_zero_entries():
    """没有任何 OOS entries → 报告仍能生成,KPI fail。"""
    cfg = WalkForwardConfig(
        start_iso="2026-01-01", end_iso="2026-03-01",
        symbols=["X/USDT"],
        train_days=30, oos_days=7, step_days=7,
    )
    with patch("scripts.walkforward.run_window_oos", return_value=[]):
        report = run_walkforward(cfg)
    assert report.oos_summary["n"] == 0
    assert report.pass_doc_kpi["n_oos_trades"] == 0
    assert report.pass_doc_kpi["kpi_passes_doc_15_2"] is False
