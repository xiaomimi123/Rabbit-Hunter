"""M6 写实成本模型 — maker/taker fee + 保守滑点。

依据:Rabbit-Hunter 完整开发设计文档 v1.0 §8。

短线 edge 薄(实测扣前 PF≈1.06),成本必须算:
- maker/taker 手续费(按 OKX 实际费率)
- 保守滑点(按盘口价差 × 系数,这里用固定百分比简化)
- 手续费按**杠杆放大后的名义仓位**计,不是按保证金

cost_as_R 公式推导:
  设 SL 距离 = sl_distance_pct × entry。
  1R = notional × sl_distance_pct(SL 命中时的亏损)。
  round-trip cost = 2 × (fee_rate + slippage_rate) × notional
  cost_as_R = 2 × (fee + slippage) / sl_distance_pct

notional 在分子分母都出现,约掉 — cost 只依赖于费率和 SL 相对距离。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostConfig:
    """成本配置。默认值按 OKX 永续合约。"""

    maker_fee_rate: float = 0.0002
    """OKX 永续 maker 费率(0.02%)。"""

    taker_fee_rate: float = 0.0005
    """OKX 永续 taker 费率(0.05%)。"""

    slippage_pct: float = 0.0005
    """单边滑点 0.05%(保守值)。盘口价差 × 系数的简化形式。"""

    maker_ratio: float = 0.5
    """maker 成交占比(中性假设 50%)。LIVE 接入后用真实统计回填。"""

    def effective_fee_per_side(self) -> float:
        """加权平均单边费率。"""
        return (
            self.maker_ratio * self.maker_fee_rate
            + (1.0 - self.maker_ratio) * self.taker_fee_rate
        )


@dataclass(frozen=True)
class CostBreakdown:
    """单笔成本拆解。"""
    gross_r: float
    net_r: float
    fee_cost_r: float           # 手续费占用多少 R
    slippage_cost_r: float      # 滑点占用多少 R
    sl_distance_pct: float       # 入场时的 SL/entry 比例


def compute_cost_breakdown(
    *,
    gross_r: float,
    entry_price: float,
    sl_price: float,
    cfg: CostConfig = CostConfig(),
) -> CostBreakdown:
    """把 gross_r 调整为 net_r,并拆分手续费 / 滑点占多少 R。

    sl_distance_pct = |entry - sl| / entry
    cost_as_R = 2 × (fee + slippage) / sl_distance_pct
    """
    if entry_price <= 0:
        return CostBreakdown(gross_r, gross_r, 0.0, 0.0, 0.0)
    sl_distance_pct = abs(entry_price - sl_price) / entry_price
    if sl_distance_pct <= 0:
        return CostBreakdown(gross_r, gross_r, 0.0, 0.0, 0.0)

    fee_per_side = cfg.effective_fee_per_side()
    fee_cost_r = 2 * fee_per_side / sl_distance_pct
    slippage_cost_r = 2 * cfg.slippage_pct / sl_distance_pct

    net_r = gross_r - fee_cost_r - slippage_cost_r
    return CostBreakdown(
        gross_r=gross_r,
        net_r=net_r,
        fee_cost_r=fee_cost_r,
        slippage_cost_r=slippage_cost_r,
        sl_distance_pct=sl_distance_pct,
    )


def adjust_r_for_costs(
    gross_r: float,
    *,
    entry_price: float,
    sl_price: float,
    cfg: CostConfig = CostConfig(),
) -> float:
    """简化入口:gross_r → net_r。"""
    return compute_cost_breakdown(
        gross_r=gross_r, entry_price=entry_price, sl_price=sl_price, cfg=cfg,
    ).net_r


# ─────────────────────────────────────────────────────────────
# 预置场景 — 用于敏感度分析
# ─────────────────────────────────────────────────────────────

# Optimistic:全 maker,无滑点(理想化执行)
COST_OPTIMISTIC = CostConfig(
    maker_fee_rate=0.0002, taker_fee_rate=0.0005,
    slippage_pct=0.0, maker_ratio=1.0,
)

# Realistic:文档默认假设
COST_REALISTIC = CostConfig()

# Pessimistic:全 taker + 大滑点(逆境)
COST_PESSIMISTIC = CostConfig(
    maker_fee_rate=0.0002, taker_fee_rate=0.0005,
    slippage_pct=0.0010, maker_ratio=0.0,
)


__all__ = [
    "CostConfig",
    "CostBreakdown",
    "compute_cost_breakdown",
    "adjust_r_for_costs",
    "COST_OPTIMISTIC",
    "COST_REALISTIC",
    "COST_PESSIMISTIC",
]
