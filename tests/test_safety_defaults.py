"""安全默认值 + 杠杆反推 — 防回归测试。

宪法 §5 要求:
- 单笔最大风险 1%(本金 < 50k);config / .env / v5_params 默认须与之对齐。
- VULTURE / 自动批量做空默认关闭。
- 起步杠杆 3-5x + 按 SL 距离反推。

本文件的每个测试都对应过去某条"config 写一套、实际跑另一套"的静默偏差。
不要为了让默认值变松而删除断言——动这些值前请回看 docs/readme-vs-code-diff.md。
"""
from __future__ import annotations

import os

import pytest


# ─────────────────────────────────────────────────────────────
# config.py TradingConfig defaults
# ─────────────────────────────────────────────────────────────


def test_config_default_enable_short_trading_is_false():
    """宪法 §5:VULTURE / 自动批量做空默认关闭。"""
    from scripts.config import TradingConfig
    cfg = TradingConfig()
    assert cfg.enable_short_trading is False


def test_config_default_risk_per_trade_is_1pct():
    """宪法 §5 tier 0:单笔风险 1%。

    之前 default=0.015(1.5%),靠 scorer 的 min() 兜底压回 1%。
    现在要求三处默认(dataclass / env / v5_params)都对齐 1%,
    防"看上去从 config 读、实际 env 漏读时直接 1.5%"的静默 bug。
    """
    from scripts.config import TradingConfig
    cfg = TradingConfig()
    assert cfg.risk_per_trade == 0.01


def test_config_default_binance_leverage_is_within_constitution_range():
    """宪法 §5:起步杠杆 3-5x。"""
    from scripts.config import TradingConfig
    cfg = TradingConfig()
    assert 3 <= cfg.binance_leverage <= 5


def test_config_env_default_matches_dataclass():
    """env 默认值(_load_from_env)与 dataclass 默认必须一致——

    历史上这两套默认漂移过一次(dataclass=False 但 env="true"),
    导致没填 .env 时跑的不是想象中的 dataclass 默认。
    """
    from scripts.config import _load_from_env
    # 清掉测试机上可能存在的真实 env(避免污染)
    keys_to_clear = [
        "ENABLE_SHORT_TRADING", "V43_RISK_PER_TRADE", "BINANCE_LEVERAGE",
    ]
    saved = {k: os.environ.pop(k, None) for k in keys_to_clear}
    try:
        cfg = _load_from_env()
        assert cfg.enable_short_trading is False
        assert cfg.risk_per_trade == 0.01
        assert 3 <= cfg.binance_leverage <= 5
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


# ─────────────────────────────────────────────────────────────
# v5_params DEFAULTS dict
# ─────────────────────────────────────────────────────────────


def test_v5_params_defaults_aligned_with_constitution():
    """v5_params.DEFAULTS 是热配置层的回落值,必须与宪法/config 对齐。"""
    from scripts.v5_params import DEFAULTS
    assert DEFAULTS["v5_risk_per_trade"] == 0.01
    assert 3 <= DEFAULTS["v5_leverage"] <= 5


# ─────────────────────────────────────────────────────────────
# derive_safe_leverage — 杠杆反推
# ─────────────────────────────────────────────────────────────


def test_derive_safe_leverage_returns_cap_when_sl_is_narrow():
    """窄 SL(SL 距 << entry / R)时,反推上限会很大,直接取 cap。

    BTC = 100k, atr = 1k, sl_mult = 1.5 → sl_dist = 1.5k
    max_lev = 100k / (2 × 1.5k) = 33.3 → cap=5 生效。
    """
    from scripts.v5_risk_calculator import derive_safe_leverage
    lev = derive_safe_leverage(entry=100_000, atr=1_000, leverage_cap=5)
    assert lev == 5


def test_derive_safe_leverage_lowers_when_sl_is_wide():
    """宽 SL 时反推会降低 leverage 以保证强平距 ≥ 2 × SL 距。

    entry=100, atr=8 → sl_dist = 1.5×8 = 12
    max_lev = 100 / (2 × 12) = 4.17 → floor = 4。
    cap=10 但反推强制到 4。
    """
    from scripts.v5_risk_calculator import derive_safe_leverage
    lev = derive_safe_leverage(entry=100, atr=8, leverage_cap=10)
    assert lev == 4


def test_derive_safe_leverage_floors_at_1_for_extreme_atr():
    """极端宽 SL(SL 距 > entry / 2)时反推到 1,gate_liquidation_distance 会兜底拒单。"""
    from scripts.v5_risk_calculator import derive_safe_leverage
    # entry=100, atr=50 → sl_dist=75 → max_lev = 100/(2*75) = 0.67 → floor 1
    lev = derive_safe_leverage(entry=100, atr=50, leverage_cap=5)
    assert lev == 1


def test_derive_safe_leverage_satisfies_constitution_gate():
    """反推后的 leverage 配合 gate_liquidation_distance 必须能通过。

    即:reverse-derive 出来的杠杆,实际跑 gate 应该是 ✅,不会冲突。
    """
    from scripts.risk_gates import gate_liquidation_distance, IronlawViolation
    from scripts.v5_risk_calculator import derive_safe_leverage
    from scripts.v5_params import get_param

    entry = 100.0
    atr = 8.0
    lev = derive_safe_leverage(entry=entry, atr=atr, leverage_cap=10)

    sl_mult = get_param("v5_sl_atr_mult", 1.5, float)
    sl_distance = sl_mult * atr
    sl_price_long = entry - sl_distance
    # 不应该 raise
    gate_liquidation_distance(
        entry=entry, sl_price=sl_price_long, leverage=lev, side="LONG",
    )


def test_derive_safe_leverage_respects_cap_even_when_more_would_be_safe():
    """SL 极窄时,数学上可以开更高杠杆,但 cap 是硬上限。"""
    from scripts.v5_risk_calculator import derive_safe_leverage
    # entry=100k, atr=1 → sl_dist=1.5 → max_lev = 100k/3 = 33333
    # 但 cap=3,应当返回 3
    lev = derive_safe_leverage(entry=100_000, atr=1, leverage_cap=3)
    assert lev == 3


def test_derive_safe_leverage_invalid_inputs_return_cap():
    """非法输入(entry/atr/cap <= 0)走保守路径——不放大杠杆。"""
    from scripts.v5_risk_calculator import derive_safe_leverage
    assert derive_safe_leverage(entry=0, atr=10, leverage_cap=5) == 5
    assert derive_safe_leverage(entry=100, atr=0, leverage_cap=5) == 5
    assert derive_safe_leverage(entry=100, atr=10, leverage_cap=0) == 1


# ─────────────────────────────────────────────────────────────
# scorer._risk_per_trade — assert 防回归
# ─────────────────────────────────────────────────────────────


def test_scorer_risk_per_trade_never_exceeds_constitution_ceiling():
    """scorer._risk_per_trade 不允许返回超过 EQUITY_TIERS 最高 tier(0.015)的值。"""
    from scripts.tasks.scorer import _risk_per_trade
    # 小本金 → tier 0 = 1%
    assert _risk_per_trade(10_000) <= 0.015 + 1e-9
    # 大本金 → tier 1 = 1.5%,刚好等于 ceiling
    assert _risk_per_trade(100_000) <= 0.015 + 1e-9


def test_scorer_risk_per_trade_small_account_is_1pct():
    """本金 < 50k 时,_risk_per_trade 必须 ≤ 1%(宪法 tier 0)。"""
    from scripts.tasks.scorer import _risk_per_trade
    assert _risk_per_trade(10_000) <= 0.01 + 1e-9
