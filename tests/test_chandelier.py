"""M5 Chandelier 移动止损测试。

核心特性:
1. 持仓中价格走对 → trailing_sl 收紧
2. 价格回撤 → trailing_sl 不放宽
3. 等价于初始 SL 时优先取静态值
"""
from scripts.chandelier import update_chandelier, effective_sl_price


# ─── update_chandelier ───────────────────────────────


def test_long_first_tick_initializes_trailing():
    """LONG 第一次 tick 初始化所有字段。"""
    high, low, trail = update_chandelier(
        side="LONG", current_price=100.0, entry_atr=2.0,
        highest_seen=None, lowest_seen=None, trailing_sl=None, k=1.5,
    )
    assert high == 100.0
    assert low == 100.0
    # trailing = 100 - 1.5*2 = 97
    assert trail == 97.0


def test_long_price_up_tightens_trailing():
    """LONG 价格上涨 → highest 更新 → trailing 跟着上移。"""
    high, low, trail = update_chandelier(
        side="LONG", current_price=110.0, entry_atr=2.0,
        highest_seen=105.0, lowest_seen=98.0, trailing_sl=102.0, k=1.5,
    )
    assert high == 110.0
    # new candidate = 110 - 3 = 107; old trail = 102; max = 107
    assert trail == 107.0


def test_long_price_drops_keeps_trailing():
    """LONG 价格回撤,highest 不变,trailing 不放宽。"""
    high, low, trail = update_chandelier(
        side="LONG", current_price=103.0, entry_atr=2.0,
        highest_seen=110.0, lowest_seen=100.0, trailing_sl=107.0, k=1.5,
    )
    assert high == 110.0  # 不更新
    # new candidate = 110 - 3 = 107; old trail = 107; max = 107(不变)
    assert trail == 107.0


def test_short_first_tick_initializes_trailing():
    """SHORT 第一次 tick 初始化。"""
    high, low, trail = update_chandelier(
        side="SHORT", current_price=100.0, entry_atr=2.0,
        highest_seen=None, lowest_seen=None, trailing_sl=None, k=1.5,
    )
    assert low == 100.0
    # trailing = 100 + 1.5*2 = 103
    assert trail == 103.0


def test_short_price_down_tightens_trailing():
    """SHORT 价格下跌 → lowest 更新 → trailing 跟着下移。"""
    high, low, trail = update_chandelier(
        side="SHORT", current_price=90.0, entry_atr=2.0,
        highest_seen=98.0, lowest_seen=92.0, trailing_sl=95.0, k=1.5,
    )
    assert low == 90.0
    # candidate = 90 + 3 = 93; old = 95; min = 93
    assert trail == 93.0


def test_short_price_rebounds_keeps_trailing():
    """SHORT 反弹时 trailing 不放宽。"""
    high, low, trail = update_chandelier(
        side="SHORT", current_price=96.0, entry_atr=2.0,
        highest_seen=99.0, lowest_seen=88.0, trailing_sl=91.0, k=1.5,
    )
    assert low == 88.0  # 不更新
    # candidate = 88 + 3 = 91; old = 91; min = 91(不变)
    assert trail == 91.0


def test_invalid_atr_returns_safe_defaults():
    high, low, trail = update_chandelier(
        side="LONG", current_price=100.0, entry_atr=0,
        highest_seen=None, lowest_seen=None, trailing_sl=None,
    )
    assert high == 100.0
    assert trail == 0.0  # 安全 default


# ─── effective_sl_price ───────────────────────────────


def test_effective_sl_uses_static_when_no_trailing():
    assert effective_sl_price(side="LONG", static_sl=95.0, trailing_sl=None) == 95.0


def test_effective_sl_long_uses_tighter_trailing():
    """LONG 静态 95,trailing 收紧到 98 → 用 98(更近 = 更贴 entry)。"""
    assert effective_sl_price(side="LONG", static_sl=95.0, trailing_sl=98.0) == 98.0


def test_effective_sl_long_keeps_static_when_trailing_below():
    """trailing 不应当比 static 还宽,但安全起见取 max。"""
    assert effective_sl_price(side="LONG", static_sl=95.0, trailing_sl=93.0) == 95.0


def test_effective_sl_short_uses_tighter_trailing():
    """SHORT 静态 105,trailing 收紧到 102 → 用 102。"""
    assert effective_sl_price(side="SHORT", static_sl=105.0, trailing_sl=102.0) == 102.0


def test_effective_sl_short_keeps_static_when_trailing_above():
    assert effective_sl_price(side="SHORT", static_sl=105.0, trailing_sl=108.0) == 105.0
