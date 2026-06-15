"""AI confidence calibration — bucket-wise actual win rate, multiplier."""
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


def test_update_creates_new_bucket(db):
    from scripts.ai.confidence_calibration import update_calibration
    update_calibration(ai_model="deepseek-chat", confidence_at_entry=0.7,
                       won=True, db_path=db)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT actual_win_rate, sample_count, calibration_multiplier "
        "FROM ai_confidence_calibration WHERE ai_model='deepseek-chat' AND confidence_bucket=0.7"
    ).fetchone()
    conn.close()
    actual_wr, n, mult = row
    assert n == 1
    assert actual_wr == 1.0
    assert abs(mult - (1.0 / 0.7)) < 1e-9


def test_update_running_average(db):
    from scripts.ai.confidence_calibration import update_calibration
    # 3 wins + 2 losses at confidence 0.7 → actual_wr = 0.6
    for won in [True, True, False, True, False]:
        update_calibration(ai_model="deepseek-chat", confidence_at_entry=0.7,
                           won=won, db_path=db)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT actual_win_rate, sample_count, calibration_multiplier "
        "FROM ai_confidence_calibration WHERE confidence_bucket=0.7"
    ).fetchone()
    conn.close()
    actual_wr, n, mult = row
    assert n == 5
    assert abs(actual_wr - 0.6) < 1e-9
    assert abs(mult - (0.6 / 0.7)) < 1e-9


def test_get_multiplier_returns_1_when_no_data(db):
    from scripts.ai.confidence_calibration import get_calibration_multiplier
    mult = get_calibration_multiplier(ai_model="unknown", confidence=0.7, db_path=db)
    assert mult == 1.0


def test_get_multiplier_falls_back_when_sample_too_small(db):
    """sample < 10 → 不用校准,返回 1.0。"""
    from scripts.ai.confidence_calibration import update_calibration, get_calibration_multiplier
    for _ in range(5):
        update_calibration(ai_model="deepseek-chat", confidence_at_entry=0.7,
                           won=False, db_path=db)
    mult = get_calibration_multiplier(ai_model="deepseek-chat", confidence=0.7, db_path=db)
    assert mult == 1.0


def test_get_multiplier_after_sufficient_samples(db):
    from scripts.ai.confidence_calibration import update_calibration, get_calibration_multiplier
    # 15 samples, 6 wins → actual 0.4, predicted 0.8 → multiplier = 0.5
    for i in range(15):
        update_calibration(ai_model="deepseek-chat", confidence_at_entry=0.8,
                           won=(i < 6), db_path=db)
    mult = get_calibration_multiplier(ai_model="deepseek-chat", confidence=0.8, db_path=db)
    assert abs(mult - 0.5) < 1e-9


def test_buckets_round_to_nearest_tenth(db):
    from scripts.ai.confidence_calibration import update_calibration
    update_calibration(ai_model="deepseek-chat", confidence_at_entry=0.72,
                       won=True, db_path=db)
    update_calibration(ai_model="deepseek-chat", confidence_at_entry=0.68,
                       won=False, db_path=db)
    conn = sqlite3.connect(db)
    buckets = sorted(r[0] for r in conn.execute(
        "SELECT confidence_bucket FROM ai_confidence_calibration "
        "WHERE ai_model='deepseek-chat'"
    ).fetchall())
    conn.close()
    assert buckets == [0.7, 0.7] or buckets == [0.7]   # both rounded to 0.7
