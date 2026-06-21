"""M6 写实成本模型测试。"""
import pytest

from scripts.backtest.cost_model import (
    CostConfig,
    CostBreakdown,
    compute_cost_breakdown,
    adjust_r_for_costs,
    COST_OPTIMISTIC,
    COST_REALISTIC,
    COST_PESSIMISTIC,
)


# ─── CostConfig.effective_fee_per_side ─────────────────────────


def test_default_effective_fee_is_average():
    cfg = CostConfig()
    # 50% maker (0.0002) + 50% taker (0.0005) = 0.00035
    assert cfg.effective_fee_per_side() == pytest.approx(0.00035)


def test_all_maker_effective_fee():
    cfg = CostConfig(maker_ratio=1.0)
    assert cfg.effective_fee_per_side() == 0.0002


def test_all_taker_effective_fee():
    cfg = CostConfig(maker_ratio=0.0)
    assert cfg.effective_fee_per_side() == 0.0005


# ─── compute_cost_breakdown ─────────────────────────


def test_cost_breakdown_typical_case():
    """entry=100, sl=98 → sl_dist_pct=0.02,50/50 maker/taker + 0.05% slip。"""
    br = compute_cost_breakdown(
        gross_r=1.0, entry_price=100.0, sl_price=98.0,
        cfg=CostConfig(),
    )
    # fee_cost_r = 2 × 0.00035 / 0.02 = 0.035
    assert br.fee_cost_r == pytest.approx(0.035)
    # slippage_cost_r = 2 × 0.0005 / 0.02 = 0.05
    assert br.slippage_cost_r == pytest.approx(0.05)
    # net_r = 1.0 - 0.035 - 0.05 = 0.915
    assert br.net_r == pytest.approx(0.915)
    assert br.sl_distance_pct == pytest.approx(0.02)


def test_cost_breakdown_tighter_sl_higher_cost():
    """SL 越近,成本占 R 比例越高 — 接飞刀的代价。"""
    br_loose = compute_cost_breakdown(
        gross_r=1.0, entry_price=100, sl_price=95,  # 5% 距
        cfg=CostConfig(),
    )
    br_tight = compute_cost_breakdown(
        gross_r=1.0, entry_price=100, sl_price=99,  # 1% 距
        cfg=CostConfig(),
    )
    # 同样的费率,SL 距越窄 → cost_as_R 越大
    assert br_tight.fee_cost_r > br_loose.fee_cost_r
    assert br_tight.slippage_cost_r > br_loose.slippage_cost_r


def test_cost_breakdown_handles_zero_sl_distance():
    br = compute_cost_breakdown(
        gross_r=1.0, entry_price=100, sl_price=100, cfg=CostConfig(),
    )
    assert br.net_r == 1.0  # 无 SL 距 → 不扣
    assert br.fee_cost_r == 0
    assert br.slippage_cost_r == 0


def test_cost_breakdown_handles_invalid_entry():
    br = compute_cost_breakdown(
        gross_r=1.0, entry_price=0, sl_price=98, cfg=CostConfig(),
    )
    assert br.net_r == 1.0


# ─── 三档场景 ─────────────────────────


def test_optimistic_costs_lower_than_realistic():
    e, sl = 100.0, 98.0
    br_opt = compute_cost_breakdown(
        gross_r=1.0, entry_price=e, sl_price=sl, cfg=COST_OPTIMISTIC,
    )
    br_real = compute_cost_breakdown(
        gross_r=1.0, entry_price=e, sl_price=sl, cfg=COST_REALISTIC,
    )
    assert br_opt.net_r > br_real.net_r


def test_pessimistic_costs_higher_than_realistic():
    e, sl = 100.0, 98.0
    br_real = compute_cost_breakdown(
        gross_r=1.0, entry_price=e, sl_price=sl, cfg=COST_REALISTIC,
    )
    br_pess = compute_cost_breakdown(
        gross_r=1.0, entry_price=e, sl_price=sl, cfg=COST_PESSIMISTIC,
    )
    assert br_pess.net_r < br_real.net_r


# ─── adjust_r_for_costs ─────────────────────────


def test_adjust_r_matches_breakdown_net():
    """简化入口和详细 breakdown 应返回相同 net_r。"""
    net = adjust_r_for_costs(gross_r=1.0, entry_price=100, sl_price=98)
    br = compute_cost_breakdown(gross_r=1.0, entry_price=100, sl_price=98)
    assert net == br.net_r


def test_adjust_negative_gross_gets_more_negative():
    """loss + cost = 更亏。"""
    net = adjust_r_for_costs(gross_r=-1.0, entry_price=100, sl_price=98)
    assert net < -1.0


# ─── 文档 PF=1.06 校准:扣成本后 win rate 50% / RR=1.5 ─────────────────────────


def test_doc_calibration_sl_dist_2pct():
    """文档实测 PF≈1.06,验证我们的成本档位合理。

    模型:50% win @ +1.5R, 50% loss @ -1R(gross PF=1.5)。
    扣成本(SL 2%)后,PF 应当显著下降但仍 > 1。
    """
    e, sl, tp = 100.0, 98.0, 103.0  # SL 2%, TP 3%, gross RR=1.5
    win_net = adjust_r_for_costs(
        gross_r=1.5, entry_price=e, sl_price=sl, cfg=COST_REALISTIC,
    )
    loss_net = adjust_r_for_costs(
        gross_r=-1.0, entry_price=e, sl_price=sl, cfg=COST_REALISTIC,
    )
    # 50/50 mix
    avg_net = (win_net + loss_net) / 2
    pf_net = win_net / abs(loss_net)
    # 扣成本后 PF 应当下降但仍 > 1
    assert 1.0 < pf_net < 1.5
    # avg R 应当为正
    assert avg_net > 0
