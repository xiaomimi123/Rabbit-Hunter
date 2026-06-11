"""Paper Position Manager V5 测试 — 加 target_close_at 等字段。"""
import sqlite3
import tempfile
import pytest
from datetime import datetime, timezone, timedelta

from v5_types import AIResult, Decision, EnrichedItem, Indicators, RiskPlan


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _open_intent_kwargs():
    return dict(
        enriched=EnrichedItem(symbol="H/USDT", current_price=0.166, delta_15m_pct=0.034,
                              volume_24h_usdt=50_000_000, klines_15m=[], klines_4h=[]),
        indicators=Indicators(rsi_15m=72.0, macd_15m=0.001, macd_signal_15m=0.0005,
                              macd_hist_15m=-0.0005, macd_hist_prev_15m=0.0008,
                              rsi_4h=65.0, macd_hist_4h=0.003, atr_15m=0.0015),
        decision=Decision(should_trade=True, side="SHORT", reasoning="...", block_reason=None),
        risk=RiskPlan(entry_price=0.166, sl_price=0.169, tp_price=0.162,
                      size_usdt=15.0, leverage=10, expected_rr=1.67),
        ai=AIResult(execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
                    size_multiplier=1.0, confidence=0.7, reasoning="ok"),
    )


def test_open_position_writes_target_close_at():
    from scripts.paper_position_manager import PaperPositionManager
    db = _fresh_db()
    pm = PaperPositionManager(db_path=db)
    pid = pm.open_position(**_open_intent_kwargs())

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT entry_time, target_close_at, extension_count FROM paper_trades WHERE id=?",
        (pid,),
    ).fetchone()
    conn.close()
    entry_time, target_close_at, extension_count = row
    assert target_close_at is not None
    assert extension_count == 0
    et = datetime.fromisoformat(entry_time)
    tc = datetime.fromisoformat(target_close_at)
    assert abs((tc - et).total_seconds() - 900) < 5


def test_open_position_writes_indicator_snapshot():
    from scripts.paper_position_manager import PaperPositionManager
    db = _fresh_db()
    pm = PaperPositionManager(db_path=db)
    pid = pm.open_position(**_open_intent_kwargs())

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT entry_rsi_15m, entry_macd_hist_15m, entry_rsi_4h, entry_atr_15m "
        "FROM paper_trades WHERE id=?", (pid,)).fetchone()
    conn.close()
    assert row[0] == 72.0
    assert abs(row[1] - (-0.0005)) < 1e-9
    assert row[2] == 65.0
    assert abs(row[3] - 0.0015) < 1e-9


def test_extend_position_advances_target_and_count():
    from scripts.paper_position_manager import PaperPositionManager
    db = _fresh_db()
    pm = PaperPositionManager(db_path=db)
    pid = pm.open_position(**_open_intent_kwargs())

    pm.extend_position(pid, extra_minutes=15)

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT target_close_at, extension_count FROM paper_trades WHERE id=?",
        (pid,)).fetchone()
    conn.close()
    target_close_at, extension_count = row
    assert extension_count == 1


def test_close_position_fills_exit_fields():
    from scripts.paper_position_manager import PaperPositionManager
    db = _fresh_db()
    pm = PaperPositionManager(db_path=db)
    pid = pm.open_position(**_open_intent_kwargs())

    pm.close_position(pid, exit_price=0.162, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    # Use actual column name for PnL. Default is `pnl` (not `pnl_usdt`)
    row = conn.execute(
        "SELECT status, exit_price, exit_reason, pnl, holding_hours "
        "FROM paper_trades WHERE id=?", (pid,)).fetchone()
    conn.close()
    status, exit_price, exit_reason, pnl, holding_hours = row
    assert status == "CLOSED"
    assert exit_price == 0.162
    assert exit_reason == "TP_HIT"
    # SHORT entry=0.166 exit=0.162 → profitable
    assert pnl is not None and pnl > 0
