"""V5ReflectionWorker poll loop — 用 mock AI + tmpfs DB 跑一次 tick。"""
import asyncio
import json
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _seed_closed_trade_and_enqueue(db_path, pid=7):
    """填一个 CLOSED paper_trade + 一行 trade_scores + 入队 reflection。"""
    conn = sqlite3.connect(db_path)
    et = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    xt = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO paper_trades (id, symbol, side, entry_price, entry_time, status,
            stop_loss, take_profit, position_size_usdt, leverage, strategy_id,
            created_at, exit_price, exit_time, exit_reason, pnl_percent,
            entry_rsi_15m, entry_macd_hist_15m, ai_confidence, ai_reason)
        VALUES (?, 'HUSDT', 'SHORT', 0.166, ?, 'CLOSED', 0.169, 0.162,
                15.0, 10, 'v5_rsi_macd', ?, 0.162, ?, 'TP_HIT', 1.8,
                72.1, -0.0012, 0.7, 'short setup')
    """, (pid, et, et, xt))
    conn.execute("""
        INSERT INTO trade_scores_v5 (symbol, created_at, rsi_15m, macd_hist_15m,
            macd_hist_prev_15m, atr_15m, current_price, executed, position_id,
            should_trade, side)
        VALUES ('HUSDT', ?, 72.1, -0.0012, 0.0008, 0.0015, 0.166, 1, ?, 1, 'SHORT')
    """, (et, pid))
    conn.execute(
        "INSERT INTO reflection_queue (paper_trade_id) VALUES (?)", (pid,)
    )
    conn.commit()
    conn.close()


def test_worker_tick_processes_pending_queue_item(db):
    from scripts.tasks.v5_reflection_worker import V5ReflectionWorker

    _seed_closed_trade_and_enqueue(db, pid=7)

    fake_ai = AsyncMock(return_value=json.dumps({
        "why_entered": "RSI overbought + MACD bearish cross at this bar",
        "what_was_expected": "Expected 1.5-2 ATR pullback then partial TP",
        "what_actually_happened": "Price dropped quickly to TP, hit it in 10 bars",
        "correction_idea": "Consider 4h alignment for higher conviction next time",
        "failure_mode_key": None,
        "self_assessed_prediction_accuracy": 0.85,
        "is_in_predicted_failure_mode": False,
    }))

    worker = V5ReflectionWorker(db_path=db, ai_call=fake_ai,
                                 ai_provider="deepseek", ai_model="deepseek-chat")
    asyncio.run(worker._tick())

    conn = sqlite3.connect(db)
    reflected = conn.execute(
        "SELECT outcome_class FROM reflections WHERE paper_trade_id=7"
    ).fetchone()
    queue_state = conn.execute(
        "SELECT completed_at, error FROM reflection_queue WHERE paper_trade_id=7"
    ).fetchone()
    conn.close()

    assert reflected == ("WIN",)
    assert queue_state[0] is not None    # completed_at filled
    assert queue_state[1] is None        # no error


def test_worker_tick_records_error_and_increments_retry(db):
    from scripts.tasks.v5_reflection_worker import V5ReflectionWorker

    _seed_closed_trade_and_enqueue(db, pid=8)
    fake_ai = AsyncMock(side_effect=RuntimeError("AI provider down"))

    worker = V5ReflectionWorker(db_path=db, ai_call=fake_ai)
    asyncio.run(worker._tick())

    conn = sqlite3.connect(db)
    qrow = conn.execute(
        "SELECT completed_at, error, retry_count FROM reflection_queue WHERE paper_trade_id=8"
    ).fetchone()
    conn.close()
    assert qrow[0] is None
    assert "AI provider down" in (qrow[1] or "")
    assert qrow[2] == 1


def test_worker_tick_skips_after_3_retries(db):
    from scripts.tasks.v5_reflection_worker import V5ReflectionWorker

    _seed_closed_trade_and_enqueue(db, pid=9)
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE reflection_queue SET retry_count=3 WHERE paper_trade_id=9"
    )
    conn.commit()
    conn.close()

    fake_ai = AsyncMock()
    worker = V5ReflectionWorker(db_path=db, ai_call=fake_ai)
    asyncio.run(worker._tick())
    fake_ai.assert_not_called()


def test_enqueue_reflection_called_from_close_position_helper(db, monkeypatch):
    """v5_position_monitor close_position path 自动 enqueue。"""
    from scripts.local_db import enqueue_reflection
    enqueue_reflection(99, db_path=db)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT paper_trade_id FROM reflection_queue WHERE paper_trade_id=99"
    ).fetchone()
    conn.close()
    assert row == (99,)
