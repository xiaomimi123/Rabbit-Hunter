"""Reflection runner — 用 mock AI 跑完整管道,确认入库正确。"""
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


def _insert_closed_paper_trade(db_path, *, pid=1, side="SHORT", strategy="v5_rsi_macd",
                                entry_rsi=72.0, macd_hist=-0.0012, macd_hist_prev=0.0008):
    conn = sqlite3.connect(db_path)
    entry_t = (datetime.now(timezone.utc) - timedelta(minutes=27)).isoformat()
    exit_t = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO paper_trades (
            id, symbol, side, entry_price, entry_time, status,
            stop_loss, take_profit, position_size_usdt, leverage,
            strategy_id, created_at, exit_price, exit_time, exit_reason,
            pnl_percent, entry_rsi_15m, entry_macd_hist_15m,
            ai_confidence, ai_reason
        ) VALUES (?, 'HUSDT', ?, 0.166, ?, 'CLOSED',
                  0.169, 0.162, 15.0, 10,
                  ?, ?, 0.169, ?, 'SL_HIT',
                  -1.8, ?, ?,
                  0.7, 'short setup')
    """, (pid, side, entry_t, strategy, entry_t, exit_t, entry_rsi, macd_hist))
    # 同时塞个 trade_scores_v5 行,reflection runner 会查它拿 macd_hist_prev
    conn.execute("""
        INSERT INTO trade_scores_v5 (
            symbol, created_at, rsi_15m, macd_hist_15m, macd_hist_prev_15m,
            atr_15m, current_price, executed, position_id, should_trade, side
        ) VALUES ('HUSDT', ?, ?, ?, ?, 0.0015, 0.166, 1, ?, 1, ?)
    """, (entry_t, entry_rsi, macd_hist, macd_hist_prev, pid, side))
    conn.commit()
    conn.close()


def test_run_reflection_writes_reflection_row(db, monkeypatch):
    """成功路径 — mock AI 返回有效 JSON,reflection 被持久化。"""
    from scripts.ai.reflection_runner import run_reflection_for_trade

    _insert_closed_paper_trade(db, pid=1)

    fake_ai_response = json.dumps({
        "why_entered": "RSI 72.1 overbought + MACD hist 由正转负 (death cross at this bar)",
        "what_was_expected": "AI 期望 1.5-2 ATR 反弹完成 then mean revert to RSI 60",
        "what_actually_happened": "价格继续 push up 至 0.169 触发 SL,RSI 反而到 75",
        "correction_idea": "在 4h RSI 也 < 70 时才允许 SHORT,避免单 timeframe 误判",
        "failure_mode_key": "against_4h_trend_no_funding_filter",
        "self_assessed_prediction_accuracy": 0.3,
        "is_in_predicted_failure_mode": False,
    })
    mock_ai = AsyncMock(return_value=fake_ai_response)

    import asyncio
    asyncio.run(run_reflection_for_trade(
        paper_trade_id=1, db_path=db,
        ai_call=mock_ai, taxonomy_keys=[
            "late_entry_signal_decay", "macd_false_cross",
            "against_4h_trend_no_funding_filter", "sl_too_tight_in_high_atr",
        ],
    ))

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT setup_type, outcome_class, realized_r, failure_mode_key, "
        "       confidence_at_entry, self_assessed_prediction_accuracy, "
        "       prompt_version FROM reflections WHERE paper_trade_id=1"
    ).fetchone()
    conn.close()
    assert row is not None
    setup_type, outcome, r, fm_key, conf, sapa, pv = row
    assert setup_type == "rsi_overbought_macd_bearish_short"
    assert outcome == "LOSS"
    assert abs(r - (-1.0)) < 0.5    # SL_HIT → realized_r ≈ -1
    assert fm_key == "against_4h_trend_no_funding_filter"
    assert conf == 0.7
    assert sapa == 0.3
    assert pv == "reflection-prompt-v1"


def test_run_reflection_persists_audit_fields(db, monkeypatch):
    """AI provider / model / latency 写入。"""
    from scripts.ai.reflection_runner import run_reflection_for_trade

    _insert_closed_paper_trade(db, pid=2)

    fake_ai_response = json.dumps({
        "why_entered": "test reason for entry",
        "what_was_expected": "test expectation",
        "what_actually_happened": "test reality",
        "correction_idea": "test correction idea",
        "failure_mode_key": None,
        "self_assessed_prediction_accuracy": 0.5,
        "is_in_predicted_failure_mode": False,
    })
    mock_ai = AsyncMock(return_value=fake_ai_response)

    import asyncio
    asyncio.run(run_reflection_for_trade(
        paper_trade_id=2, db_path=db,
        ai_call=mock_ai, ai_provider="deepseek", ai_model="deepseek-chat",
        taxonomy_keys=[],
    ))

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT ai_provider, ai_model, ai_latency_ms FROM reflections "
        "WHERE paper_trade_id=2"
    ).fetchone()
    conn.close()
    assert row[0] == "deepseek"
    assert row[1] == "deepseek-chat"
    assert row[2] is not None and row[2] >= 0


def test_run_reflection_rejects_invalid_json(db, monkeypatch):
    """AI 返回非 JSON → 抛 ValueError,不写 reflections。"""
    from scripts.ai.reflection_runner import run_reflection_for_trade

    _insert_closed_paper_trade(db, pid=3)
    mock_ai = AsyncMock(return_value="this is not json")

    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(run_reflection_for_trade(
            paper_trade_id=3, db_path=db,
            ai_call=mock_ai, taxonomy_keys=[],
        ))
    conn = sqlite3.connect(db)
    n = conn.execute(
        "SELECT COUNT(*) FROM reflections WHERE paper_trade_id=3"
    ).fetchone()[0]
    conn.close()
    assert n == 0


def test_run_reflection_rejects_schema_violation(db, monkeypatch):
    """AI 返回 JSON 但字段不全 → ValueError。"""
    from scripts.ai.reflection_runner import run_reflection_for_trade

    _insert_closed_paper_trade(db, pid=4)
    fake_ai_response = json.dumps({"why_entered": "x"})    # missing fields
    mock_ai = AsyncMock(return_value=fake_ai_response)

    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(run_reflection_for_trade(
            paper_trade_id=4, db_path=db, ai_call=mock_ai, taxonomy_keys=[],
        ))


def test_run_reflection_idempotent_skip_if_already_done(db, monkeypatch):
    """如果 paper_trade 已经有 reflection,跳过。"""
    from scripts.ai.reflection_runner import run_reflection_for_trade

    _insert_closed_paper_trade(db, pid=5)
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO reflections (paper_trade_id, why_entered, what_was_expected,
            what_actually_happened, correction_idea, setup_type, outcome_class,
            realized_r, holding_minutes, confidence_at_entry, prompt_version)
        VALUES (5, 'x', 'y', 'z', 'w', 'manual_short', 'WIN', 1.0, 30, 0.7, 'v1')
    """)
    conn.commit()
    conn.close()

    mock_ai = AsyncMock(return_value="{}")
    import asyncio
    # should not call AI
    asyncio.run(run_reflection_for_trade(
        paper_trade_id=5, db_path=db, ai_call=mock_ai, taxonomy_keys=[]
    ))
    mock_ai.assert_not_called()
