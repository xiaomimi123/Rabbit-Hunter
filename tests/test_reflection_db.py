"""reflection_queue + reflections schema + enqueue_reflection helper。"""
import os
import sqlite3
import tempfile
import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def test_reflection_queue_table_created(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(reflection_queue)").fetchall()]
    conn.close()
    assert "id" in cols
    assert "paper_trade_id" in cols
    assert "enqueued_at" in cols
    assert "started_at" in cols
    assert "completed_at" in cols
    assert "error" in cols
    assert "retry_count" in cols


def test_reflections_table_created(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(reflections)").fetchall()]
    conn.close()
    for required in (
        "paper_trade_id", "why_entered", "what_was_expected",
        "what_actually_happened", "correction_idea", "failure_mode_key",
        "setup_type", "outcome_class", "realized_r",
        "confidence_at_entry", "self_assessed_prediction_accuracy",
        "ai_provider", "ai_model", "prompt_version", "raw_response_json",
    ):
        assert required in cols, f"missing column: {required}"


def test_paper_trade_id_unique_in_queue(db):
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO reflection_queue (paper_trade_id) VALUES (1)")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO reflection_queue (paper_trade_id) VALUES (1)")
    conn.close()


def test_enqueue_reflection_helper_inserts(db):
    from scripts.local_db import enqueue_reflection
    enqueue_reflection(123, db_path=db)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT paper_trade_id, started_at, completed_at FROM reflection_queue WHERE paper_trade_id=123"
    ).fetchone()
    conn.close()
    assert row == (123, None, None)


def test_enqueue_reflection_helper_is_idempotent(db):
    """重复 enqueue 同一 paper_trade 不抛异常 (use INSERT OR IGNORE)。"""
    from scripts.local_db import enqueue_reflection
    enqueue_reflection(456, db_path=db)
    enqueue_reflection(456, db_path=db)
    conn = sqlite3.connect(db)
    count = conn.execute(
        "SELECT COUNT(*) FROM reflection_queue WHERE paper_trade_id=456"
    ).fetchone()[0]
    conn.close()
    assert count == 1
