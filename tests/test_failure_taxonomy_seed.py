"""Failure taxonomy table + 8 种子记录。"""
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


def test_failure_taxonomy_table_exists(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(failure_taxonomy)").fetchall()]
    conn.close()
    for c in ("key", "label_zh", "label_en", "description",
              "detection_rule", "is_active", "sample_count",
              "avg_loss_pct", "seeded", "created_at"):
        assert c in cols


def test_8_seeds_inserted_on_init(db):
    conn = sqlite3.connect(db)
    n = conn.execute(
        "SELECT COUNT(*) FROM failure_taxonomy WHERE seeded=1"
    ).fetchone()[0]
    conn.close()
    assert n == 8


def test_all_seeded_keys_present(db):
    conn = sqlite3.connect(db)
    keys = {r[0] for r in conn.execute(
        "SELECT key FROM failure_taxonomy WHERE seeded=1"
    ).fetchall()}
    conn.close()
    expected = {
        "late_entry_signal_decay",
        "macd_false_cross",
        "against_4h_trend_no_funding_filter",
        "sl_too_tight_in_high_atr",
        "tp_too_far_in_low_atr",
        "news_event_30min_blackout",
        "chase_after_3pct_move",
        "repeat_failure_same_symbol_24h",
    }
    assert keys == expected


def test_each_seed_has_label_and_detection_rule(db):
    conn = sqlite3.connect(db)
    rows = conn.execute("""
        SELECT key, label_zh, label_en, detection_rule FROM failure_taxonomy WHERE seeded=1
    """).fetchall()
    conn.close()
    for k, lz, le, rule in rows:
        assert lz and len(lz) > 0
        assert le and len(le) > 0
        if k != "news_event_30min_blackout":
            assert rule is not None


def test_seed_idempotent(db, monkeypatch):
    """二次 init 不应重复插入。"""
    from scripts.local_db import init_local_db
    init_local_db(db)
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM failure_taxonomy WHERE seeded=1").fetchone()[0]
    conn.close()
    assert n == 8
