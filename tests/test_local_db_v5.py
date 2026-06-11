"""V5 schema 单元测试。"""
import sqlite3
import tempfile
from pathlib import Path

import pytest


def _fresh_db_path():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return tmp.name


def test_trade_scores_v5_schema_has_v5_columns():
    from scripts.local_db import init_local_db
    db_path = _fresh_db_path()
    init_local_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(trade_scores_v5)")}
    conn.close()

    expected = {
        "id", "symbol", "created_at",
        "delta_15m_pct", "volume_24h_usdt",
        "rsi_15m", "macd_15m", "macd_signal_15m",
        "macd_hist_15m", "macd_hist_prev_15m",
        "rsi_4h", "macd_hist_4h", "atr_15m", "current_price",
        "should_trade", "side", "reasoning", "block_reason",
        "ai_confidence", "ai_sl_multiplier", "ai_tp_multiplier",
        "ai_size_multiplier", "ai_reasoning", "ai_decision_id",
        "entry_price", "sl_price", "tp_price", "size_usdt", "expected_rr",
        "executed", "position_id",
    }
    missing = expected - cols
    assert not missing, f"trade_scores_v5 缺字段: {missing}"


def test_positions_v5_has_soft_target():
    from scripts.local_db import init_local_db
    db_path = _fresh_db_path()
    init_local_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(positions_v5)")}
    conn.close()

    assert "target_close_at" in cols
    assert "extension_count" in cols
    assert "exit_reason" in cols
    assert "entry_rsi_15m" in cols


def test_paper_trades_has_v5_fields():
    from scripts.local_db import init_local_db
    db_path = _fresh_db_path()
    init_local_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(paper_trades)")}
    conn.close()

    # 旧字段保留
    assert "symbol" in cols and "entry_price" in cols and "exit_price" in cols
    # 新字段加上
    for new in ["target_close_at", "extension_count", "entry_rsi_15m",
                "entry_macd_hist_15m", "entry_rsi_4h", "entry_atr_15m",
                "ai_decision_id", "source_score_id"]:
        assert new in cols, f"paper_trades 缺 V5 字段 {new}"


def test_old_v43_tables_dropped():
    from scripts.local_db import init_local_db
    db_path = _fresh_db_path()

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE trade_scores_v43 (id INTEGER)")
    conn.execute("CREATE TABLE positions_v43 (id INTEGER)")
    conn.execute("CREATE TABLE ai_weights_v43 (id INTEGER)")
    conn.commit()
    conn.close()

    init_local_db(db_path)

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "trade_scores_v43" not in tables
    assert "positions_v43" not in tables
    assert "ai_weights_v43" not in tables
