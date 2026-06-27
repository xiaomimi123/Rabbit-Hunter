"""V5Strategy AND 合谋决策器测试 — and_strict 模式回归保护。

边界:
- RSI > 70 且 MACD hist 由正变负 → SHORT
- RSI < 30 且 MACD hist 由负变正 → LONG
- 任一条件不满足 → 不开单 + 给清晰 block_reason

所有测试显式设 V5_STRATEGY_MODE=and_strict 以保留旧行为覆盖。
"""
import pytest
from v5_types import Decision, EnrichedItem, Indicators
from v5_strategy import decide


def _enriched(symbol="H/USDT", price=0.166, delta=0.035):
    return EnrichedItem(
        symbol=symbol, current_price=price, delta_15m_pct=delta,
        volume_24h_usdt=50_000_000, klines_15m=[], klines_4h=[],
    )


def _indicators(rsi_15m=50.0, hist=0.0, hist_prev=0.0,
                rsi_4h=50.0, hist_4h=0.0, atr_15m=0.001):
    return Indicators(
        rsi_15m=rsi_15m, macd_15m=0.0, macd_signal_15m=0.0,
        macd_hist_15m=hist, macd_hist_prev_15m=hist_prev,
        rsi_4h=rsi_4h, macd_hist_4h=hist_4h, atr_15m=atr_15m,
    )


def test_short_when_rsi_overbought_and_macd_bearish_cross(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=72.0, hist=-0.001, hist_prev=0.001))
    assert d.should_trade is True
    assert d.side == "SHORT"
    assert "RSI" in d.reasoning


def test_long_when_rsi_oversold_and_macd_bullish_cross(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=28.0, hist=0.001, hist_prev=-0.001))
    assert d.should_trade is True
    assert d.side == "LONG"


def test_reject_when_rsi_not_extreme(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=50.0, hist=-0.001, hist_prev=0.001))
    assert d.should_trade is False
    assert d.side is None
    assert d.block_reason == "NOT_RSI_AND_MACD"


def test_reject_when_rsi_overbought_but_macd_no_bearish_cross(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=72.0, hist=0.001, hist_prev=0.0005))
    assert d.should_trade is False
    assert d.block_reason == "NOT_RSI_AND_MACD"


def test_reject_when_rsi_oversold_but_macd_no_bullish_cross(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=28.0, hist=-0.001, hist_prev=-0.0005))
    assert d.should_trade is False


def test_rsi_exactly_70_does_not_trigger_short(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=70.0, hist=-0.001, hist_prev=0.001))
    assert d.should_trade is False


def test_rsi_exactly_30_does_not_trigger_long(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    d = decide(_enriched(), _indicators(rsi_15m=30.0, hist=0.001, hist_prev=-0.001))
    assert d.should_trade is False


def test_custom_thresholds_from_env(monkeypatch):
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "65")
    monkeypatch.setenv("V5_RSI_OVERSOLD", "35")
    d = decide(_enriched(), _indicators(rsi_15m=66.0, hist=-0.001, hist_prev=0.001))
    assert d.should_trade is True
    assert d.side == "SHORT"


# ── Funding anti-pile filter (trend_aligned mode) ─────────────────────────


def _setup_trend_aligned_env(monkeypatch):
    """Force trend_aligned mode AND a known LONG/SHORT threshold so tests are
    isolated from DB / cache state (CI or prod DB may have non-default values)."""
    monkeypatch.setenv("V5_STRATEGY_MODE", "trend_aligned")
    monkeypatch.setenv("V5_TREND_RSI_LONG_THRESHOLD", "40.0")
    monkeypatch.setenv("V5_TREND_RSI_SHORT_THRESHOLD", "60.0")
    from scripts.v5_params import _CACHE
    _CACHE.clear()   # nuke any stale DB-derived values


def test_funding_anti_pile_blocks_long_when_longs_crowded(monkeypatch):
    """trend_aligned + LONG signal + funding_z >= threshold → blocked."""
    _setup_trend_aligned_env(monkeypatch)
    monkeypatch.setenv("V5_FUNDING_ANTI_PILE_THRESHOLD", "1.5")
    ind = _indicators(rsi_15m=35.0, hist_4h=0.001)
    d = decide(_enriched(), ind, funding_z=2.0)
    assert d.should_trade is False
    assert d.block_reason == "FUNDING_LONGS_CROWDED"


def test_funding_anti_pile_blocks_short_when_shorts_crowded(monkeypatch):
    _setup_trend_aligned_env(monkeypatch)
    monkeypatch.setenv("V5_FUNDING_ANTI_PILE_THRESHOLD", "1.5")
    ind = _indicators(rsi_15m=65.0, hist_4h=-0.001)
    d = decide(_enriched(), ind, funding_z=-2.0)
    assert d.should_trade is False
    assert d.block_reason == "FUNDING_SHORTS_CROWDED"


def test_funding_anti_pile_allows_when_threshold_zero(monkeypatch):
    _setup_trend_aligned_env(monkeypatch)
    monkeypatch.delenv("V5_FUNDING_ANTI_PILE_THRESHOLD", raising=False)
    ind = _indicators(rsi_15m=35.0, hist_4h=0.001)
    d = decide(_enriched(), ind, funding_z=5.0)
    assert d.should_trade is True
    assert d.side == "LONG"


def test_funding_anti_pile_allows_below_threshold(monkeypatch):
    _setup_trend_aligned_env(monkeypatch)
    monkeypatch.setenv("V5_FUNDING_ANTI_PILE_THRESHOLD", "1.5")
    ind = _indicators(rsi_15m=35.0, hist_4h=0.001)
    d = decide(_enriched(), ind, funding_z=0.5)
    assert d.should_trade is True
    assert d.side == "LONG"


def test_funding_anti_pile_allows_when_funding_z_none(monkeypatch):
    _setup_trend_aligned_env(monkeypatch)
    monkeypatch.setenv("V5_FUNDING_ANTI_PILE_THRESHOLD", "1.5")
    ind = _indicators(rsi_15m=35.0, hist_4h=0.001)
    d = decide(_enriched(), ind, funding_z=None)
    assert d.should_trade is True
    assert d.side == "LONG"


# ──────────────────────────────────────────────────────────────────────────────
# macd_reversal_long mode (Variant B from MACD entry timing experiment)
# ──────────────────────────────────────────────────────────────────────────────

def _kline_seq(closes):
    """构造 [ts, o, h, l, c, v] 4h K 线序列,只需控制 close。"""
    return [
        [1_000_000 + i * 14_400_000, c, c * 1.001, c * 0.999, float(c), 1000.0]
        for i, c in enumerate(closes)
    ]


def _enriched_with_klines_4h(klines_4h):
    return EnrichedItem(
        symbol="TEST/USDT", current_price=float(klines_4h[-1][4]),
        delta_15m_pct=0.0, volume_24h_usdt=50_000_000,
        klines_15m=[], klines_4h=klines_4h,
    )


def test_macd_reversal_long_triggers_on_below_zero_golden_cross(monkeypatch):
    """35 根下行 + 2 根温和上扬 → L=37,在零线下方产生金叉 (经探针验证) → LONG。"""
    monkeypatch.setenv("V5_STRATEGY_MODE", "macd_reversal_long")
    # 35 根下行 (100 → 66) 把 MACD 两线压到 dea≈-5.7,dif≈-6.1
    closes = [100.0 - i for i in range(35)]
    # 2 根温和上扬,让 dif 在最后一根刚好上穿 dea (两线仍在零下)
    closes += [67.5, 69.0]
    d = decide(_enriched_with_klines_4h(_kline_seq(closes)), _indicators())
    assert d.should_trade is True, f"expected LONG, got {d}"
    assert d.side == "LONG"
    assert "macd_reversal" in d.reasoning
    assert "金叉" in d.reasoning


def test_macd_reversal_long_rejects_when_no_cross(monkeypatch):
    """单调下行,无金叉 → 拒。"""
    monkeypatch.setenv("V5_STRATEGY_MODE", "macd_reversal_long")
    closes = [100.0 - i * 0.5 for i in range(40)]  # 长期下行,无 cross
    d = decide(_enriched_with_klines_4h(_kline_seq(closes)), _indicators())
    assert d.should_trade is False
    assert d.block_reason == "NO_4H_GOLDEN_CROSS"


def test_macd_reversal_long_rejects_when_cross_above_zero(monkeypatch):
    """整体上行中的小回调 → dif/dea 已在零上 → 即便有 cross 也被 CROSS_NOT_BELOW_ZERO 拒
       (常见情况是 NO_4H_GOLDEN_CROSS,因为上行中没有刚好的 cross)。"""
    monkeypatch.setenv("V5_STRATEGY_MODE", "macd_reversal_long")
    # 35 根上行 + 几根小回调和反弹,MACD 全期都在零上
    closes = [100.0 + i for i in range(35)]
    closes += [134.0, 133.0, 134.5, 136.0]
    d = decide(_enriched_with_klines_4h(_kline_seq(closes)), _indicators())
    assert d.should_trade is False
    assert d.block_reason in ("NO_4H_GOLDEN_CROSS", "CROSS_NOT_BELOW_ZERO")


def test_macd_reversal_long_rejects_when_insufficient_klines(monkeypatch):
    """4h 不足 35 根 → 拒。"""
    monkeypatch.setenv("V5_STRATEGY_MODE", "macd_reversal_long")
    closes = [100.0] * 30  # 仅 30 根
    d = decide(_enriched_with_klines_4h(_kline_seq(closes)), _indicators())
    assert d.should_trade is False
    assert d.block_reason == "INSUFFICIENT_4H_KLINES"


def test_macd_reversal_long_never_returns_short(monkeypatch):
    """无论上行/下行/震荡,本 mode 永不返回 SHORT。"""
    monkeypatch.setenv("V5_STRATEGY_MODE", "macd_reversal_long")
    # 死叉场景: 上行后转跌
    closes = [100.0 + i for i in range(30)] + [128.0, 125.0, 121.0, 117.0]
    d = decide(_enriched_with_klines_4h(_kline_seq(closes)), _indicators())
    # 要么 should_trade=False, 要么 side != "SHORT"
    if d.should_trade:
        assert d.side == "LONG"
    # 死叉不应被识别为可交易信号
    assert d.side != "SHORT"


def test_macd_reversal_long_does_not_affect_default_mode(monkeypatch):
    """显式设 V5_STRATEGY_MODE=trend_aligned → 走 default,与新 mode 隔离。

    注:不能用 delenv 然后 fallback DB,因 system_settings 的 v5_strategy_mode
    在生产环境可能已被前端切换。env 优先于 DB,所以显式 setenv 才能保证测试稳定。
    """
    monkeypatch.setenv("V5_STRATEGY_MODE", "trend_aligned")
    # trend_aligned 标准输入: 4h MACD>0 + RSI<40 应触发 LONG
    closes = [100.0 + i for i in range(35)]
    d = decide(
        _enriched_with_klines_4h(_kline_seq(closes)),
        _indicators(rsi_15m=35.0, hist_4h=0.001),
    )
    # 这种 input 在 trend_aligned 下应为 LONG;只要 reasoning 含 "[trend_aligned]" 就证明走的是 default
    assert "[trend_aligned]" in d.reasoning
