"""DeepCollector V5 测试 — 拉 K 线 + ΔP 过滤。"""
import pytest
from tests.conftest import _build_klines


def test_filter_by_delta_drops_below_threshold():
    from scripts.tasks.deep_collector import passes_delta_filter
    klines_15m = _build_klines([100, 101])  # ΔP = +1.0%
    assert passes_delta_filter(klines_15m, threshold=0.03) is False


def test_filter_by_delta_accepts_above_threshold():
    from scripts.tasks.deep_collector import passes_delta_filter
    klines_15m = _build_klines([100, 103.5])  # +3.5%
    assert passes_delta_filter(klines_15m, threshold=0.03) is True


def test_filter_by_delta_accepts_negative_above_threshold():
    from scripts.tasks.deep_collector import passes_delta_filter
    klines_15m = _build_klines([100, 96.0])  # -4.0%
    assert passes_delta_filter(klines_15m, threshold=0.03) is True


def test_filter_by_delta_exact_threshold_is_inclusive():
    """3.0% 正好等于阈值 → 拒(用 > 而不是 ≥)。"""
    from scripts.tasks.deep_collector import passes_delta_filter
    klines_15m = _build_klines([100, 103.0])  # 正好 +3.0%
    assert passes_delta_filter(klines_15m, threshold=0.03) is False


def test_filter_by_delta_empty_klines_rejects():
    from scripts.tasks.deep_collector import passes_delta_filter
    assert passes_delta_filter([], threshold=0.03) is False


def test_compute_delta_returns_open_to_close_pct():
    from scripts.tasks.deep_collector import compute_delta_15m_pct
    klines = _build_klines([100, 105])
    assert abs(compute_delta_15m_pct(klines) - 0.05) < 1e-6
