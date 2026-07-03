"""V5PositionMonitor 退出触发器测试。

`check_exit_triggers` 是纯函数:接收活仓 + 当前市场快照 → CloseIntent | None
"""
from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import MagicMock


def _make_monitor(paper_pm=None, live_pm=None, db_path=":memory:"):
    """构造最小 V5PositionMonitor,测 _resolve_pm 时不需要真实依赖。

    db_path=:memory: 用于不涉及 ws_event_queue 的路径；否则传 tmp_path 建的真库。
    """
    from scripts.v5_position_monitor import V5PositionMonitor
    from scripts.local_db import init_local_db
    if db_path != ":memory:":
        init_local_db(db_path)
    return V5PositionMonitor(
        paper_pm=paper_pm or MagicMock(),
        live_pm=live_pm,
        ai_assistant=MagicMock(),
        indicator_fetcher=MagicMock(),
        mode_resolver=lambda: "LIVE",
        db_path=db_path,
    )


def _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162,
                   target_offset_min=5, extension_count=0):
    now = datetime.now(timezone.utc)
    target = now + timedelta(minutes=target_offset_min)
    return {
        "id": 1, "symbol": "H/USDT", "side": side, "entry_price": entry,
        "stop_loss": sl, "take_profit": tp,
        "target_close_at": target.isoformat(),
        "extension_count": extension_count,
        "entry_time": (now - timedelta(minutes=10)).isoformat(),
    }


def _market(price=0.165, rsi_15m=67.0, macd_hist=-0.0003, macd_hist_prev=-0.0005):
    return {
        "price": price, "rsi_15m": rsi_15m,
        "macd_hist_15m": macd_hist, "macd_hist_prev_15m": macd_hist_prev,
    }


def test_short_hits_tp_returns_tp_hit():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162)
    market = _market(price=0.160)
    intent = check_exit_triggers(pos, market)
    assert intent is not None
    assert intent["exit_reason"] == "TP_HIT"


def test_short_hits_sl_returns_sl_hit():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162)
    intent = check_exit_triggers(pos, _market(price=0.170))
    assert intent["exit_reason"] == "SL_HIT"


def test_long_hits_tp():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="LONG", entry=0.166, sl=0.163, tp=0.170)
    intent = check_exit_triggers(pos, _market(price=0.171))
    assert intent["exit_reason"] == "TP_HIT"


def test_long_hits_sl():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="LONG", entry=0.166, sl=0.163, tp=0.170)
    intent = check_exit_triggers(pos, _market(price=0.162))
    assert intent["exit_reason"] == "SL_HIT"


def test_soft_target_reached_returns_timebox_intent():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162,
                         target_offset_min=-1)
    intent = check_exit_triggers(pos, _market(price=0.165))
    assert intent is not None
    assert intent["exit_reason"] == "SOFT_TARGET_REACHED"


def test_max_extension_force_close():
    from scripts.v5_position_monitor import check_exit_triggers, _max_extensions
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162,
                         target_offset_min=-1, extension_count=_max_extensions())
    intent = check_exit_triggers(pos, _market(price=0.165))
    assert intent["exit_reason"] == "AI_EXTEND_MAX"


def test_signal_reverse_short_when_rsi_drops_below_65():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162)
    intent = check_exit_triggers(pos, _market(price=0.165, rsi_15m=64.0))
    assert intent["exit_reason"] == "SIGNAL_REVERSE"


def test_signal_reverse_long_when_rsi_rises_above_35():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="LONG", entry=0.166, sl=0.163, tp=0.170)
    intent = check_exit_triggers(pos, _market(price=0.167, rsi_15m=36.0))
    assert intent["exit_reason"] == "SIGNAL_REVERSE"


def test_macd_recross_short_triggers_reverse():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162)
    intent = check_exit_triggers(pos, _market(
        price=0.165, rsi_15m=68.0,
        macd_hist=0.0003, macd_hist_prev=-0.0005,
    ))
    assert intent["exit_reason"] == "SIGNAL_REVERSE"


def test_no_trigger_returns_none():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162,
                         target_offset_min=5)
    intent = check_exit_triggers(pos, _market(price=0.165, rsi_15m=68.0,
                                              macd_hist=-0.0003, macd_hist_prev=-0.0005))
    assert intent is None


def test_check_exit_triggers_skips_signal_reverse_for_manual_strategy():
    """v5_manual 策略的持仓即使指标反转,monitor 也不应触发 SIGNAL_REVERSE 平仓。"""
    from scripts.v5_position_monitor import check_exit_triggers

    # SHORT 持仓,RSI 已经跌破 65 (SIGNAL_REVERSE 阈值默认 65) — 如果是 auto 单会被关
    position_manual = {
        "id": 99, "side": "SHORT",
        "stop_loss": 200.0, "take_profit": 100.0,
        "target_close_at": None,
        "extension_count": 0,
        "strategy_id": "v5_manual",
    }
    market = {
        "price": 150.0,
        "rsi_15m": 40.0,           # < 65 → 对 SHORT 反转
        "macd_hist_15m": 0.005,    # > 0
        "macd_hist_prev_15m": -0.005,  # 由负转正 = 反转
    }
    assert check_exit_triggers(position_manual, market) is None, \
        "manual 单不应被 SIGNAL_REVERSE 关掉"

    # 同一市场状态,但 strategy_id != 'v5_manual' → 必须返回 SIGNAL_REVERSE
    position_auto = dict(position_manual, strategy_id="v5_rsi_macd")
    intent = check_exit_triggers(position_auto, market)
    assert intent is not None and intent["exit_reason"] == "SIGNAL_REVERSE"


def test_check_exit_triggers_still_hits_sl_for_manual():
    """v5_manual 不豁免 SL_HIT — SL/TP/SOFT_TARGET 都仍然适用。"""
    from scripts.v5_position_monitor import check_exit_triggers
    position = {
        "id": 99, "side": "SHORT",
        "stop_loss": 100.0, "take_profit": 50.0,
        "target_close_at": None,
        "extension_count": 0,
        "strategy_id": "v5_manual",
    }
    market = {"price": 105.0, "rsi_15m": 80.0,
              "macd_hist_15m": -0.001, "macd_hist_prev_15m": -0.002}
    intent = check_exit_triggers(position, market)
    assert intent is not None and intent["exit_reason"] == "SL_HIT"


def test_resolve_pm_shadow_returns_paper():
    paper = MagicMock(name="paper")
    monitor = _make_monitor(paper_pm=paper, live_pm=None)
    assert monitor._resolve_pm("SHADOW") is paper


def test_resolve_pm_live_returns_live_when_set():
    live = MagicMock(name="live")
    monitor = _make_monitor(paper_pm=MagicMock(), live_pm=live)
    assert monitor._resolve_pm("LIVE") is live


def test_resolve_pm_live_recovers_via_get_trader(tmp_path, monkeypatch):
    """live_pm=None + get_trader mock 返 fake trader → self.live_pm 被替换。"""
    from scripts.local_db import init_local_db
    db = str(tmp_path / "test.db")
    init_local_db(db)

    monitor = _make_monitor(live_pm=None, db_path=db)

    fake_trader = MagicMock(name="trader")
    monkeypatch.setattr(
        "scripts.exchange_factory.get_trader", lambda: fake_trader
    )
    result = monitor._resolve_pm("LIVE")

    assert result is monitor.live_pm     # 已被替换
    assert monitor.live_pm is not None   # 显式再断一次


def test_resolve_pm_live_fails_emits_ws_event(tmp_path, monkeypatch):
    """get_trader 返 None → 返 None + ws_event_queue 一行 monitor_degraded。"""
    import sqlite3
    from scripts.local_db import init_local_db
    db = str(tmp_path / "test.db")
    init_local_db(db)

    monitor = _make_monitor(live_pm=None, db_path=db)
    monkeypatch.setattr(
        "scripts.exchange_factory.get_trader", lambda: None
    )

    result = monitor._resolve_pm("LIVE")
    assert result is None

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT payload_json FROM ws_event_queue"
    ).fetchone()
    conn.close()
    assert row is not None
    assert "monitor_degraded" in row[0]
    assert "live_pm_unavailable" in row[0]


def test_resolve_pm_live_recovery_exception_still_returns_none(tmp_path, monkeypatch):
    """get_trader 抛异常 → helper 不抛,返 None + ws 事件里 error 字段非空。"""
    import sqlite3
    from scripts.local_db import init_local_db
    db = str(tmp_path / "test.db")
    init_local_db(db)

    monitor = _make_monitor(live_pm=None, db_path=db)

    def raiser():
        raise RuntimeError("network timeout")
    monkeypatch.setattr("scripts.exchange_factory.get_trader", raiser)

    result = monitor._resolve_pm("LIVE")
    assert result is None

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT payload_json FROM ws_event_queue"
    ).fetchone()
    conn.close()
    assert row is not None
    assert "RuntimeError" in row[0]
    assert "network timeout" in row[0]
