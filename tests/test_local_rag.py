"""local_rag 距离 + top-K + 冷启动 + 集成 prompt 注入测试。"""
import sqlite3
import tempfile
import pytest


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _insert_case(db, *, side="SHORT", rsi_15m=72.0, macd_hist_15m=-0.0005,
                 rsi_4h=65.0, delta_15m_pct=0.034, outcome="WIN", pnl_pct=0.004,
                 exit_reason="TP_HIT"):
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO ai_training_data (
            symbol, side, entry_price,
            entry_rsi_15m, entry_macd_hist_15m, entry_rsi_4h, delta_15m_pct,
            outcome, pnl_pct, exit_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-06-12T10:00:00+00:00')
    """, ("H/USDT", side, 0.166,
          rsi_15m, macd_hist_15m, rsi_4h, delta_15m_pct,
          outcome, pnl_pct, exit_reason))
    conn.commit()
    conn.close()


def _ind(rsi_15m=72.0, macd_hist_15m=-0.0005, rsi_4h=65.0):
    from v5_types import Indicators
    return Indicators(
        rsi_15m=rsi_15m, macd_15m=0.0, macd_signal_15m=0.0,
        macd_hist_15m=macd_hist_15m, macd_hist_prev_15m=0.0,
        rsi_4h=rsi_4h, macd_hist_4h=0.0, atr_15m=0.0015,
    )


def test_cold_start_returns_empty():
    """ai_training_data 行数 < 10 → 返回 []。"""
    from scripts.ai.local_rag import find_similar_cases
    db = _fresh_db()
    _insert_case(db)
    cases = find_similar_cases(_ind(), side="SHORT", top_k=5, db_path=db,
                               cold_start_threshold=10)
    assert cases == []


def test_returns_top_k_sorted_by_distance():
    """喂 12 个样本 → 取最近 indicators 的 top-5,按距离升序。"""
    from scripts.ai.local_rag import find_similar_cases
    db = _fresh_db()
    for i in range(8):
        _insert_case(db, rsi_15m=80.0 + i * 0.5, macd_hist_15m=-0.001, delta_15m_pct=0.05)
    _insert_case(db, rsi_15m=72.0, macd_hist_15m=-0.0005, delta_15m_pct=0.034)
    _insert_case(db, rsi_15m=72.5, macd_hist_15m=-0.0006, delta_15m_pct=0.033)
    _insert_case(db, rsi_15m=71.8, macd_hist_15m=-0.0004, delta_15m_pct=0.035)
    _insert_case(db, rsi_15m=73.0, macd_hist_15m=-0.0007, delta_15m_pct=0.032)

    cases = find_similar_cases(_ind(), side="SHORT", top_k=5,
                               source_delta_15m_pct=0.034, db_path=db,
                               cold_start_threshold=10)
    assert len(cases) == 5
    for i in range(len(cases) - 1):
        assert cases[i].distance <= cases[i + 1].distance


def test_filters_by_side():
    """同 side 才算相似。"""
    from scripts.ai.local_rag import find_similar_cases
    db = _fresh_db()
    for _ in range(15):
        _insert_case(db, side="LONG", rsi_15m=28.0, macd_hist_15m=0.0005)
    cases = find_similar_cases(_ind(rsi_15m=28.0, macd_hist_15m=0.0005),
                               side="SHORT", top_k=5, db_path=db,
                               cold_start_threshold=10)
    assert cases == []


def test_excludes_unclosed_samples():
    """outcome IS NULL → 不参与排序。"""
    from scripts.ai.local_rag import find_similar_cases
    db = _fresh_db()
    conn = sqlite3.connect(db)
    for _ in range(15):
        conn.execute("""
            INSERT INTO ai_training_data (symbol, side, entry_rsi_15m, entry_macd_hist_15m,
              entry_rsi_4h, delta_15m_pct, created_at)
            VALUES ('H/USDT', 'SHORT', 72.0, -0.0005, 65.0, 0.034, '2026-06-12T10:00:00+00:00')
        """)
    conn.commit()
    conn.close()
    cases = find_similar_cases(_ind(), side="SHORT", top_k=5, db_path=db,
                               cold_start_threshold=10)
    assert cases == []


def test_format_for_prompt():
    """format_cases_for_prompt 渲染成给 AI 看的文本。"""
    from scripts.ai.local_rag import SimilarCase, format_cases_for_prompt
    cases = [
        SimilarCase(entry_rsi_15m=73.2, entry_macd_hist_15m=-0.0006,
                    entry_rsi_4h=68.0, outcome="WIN", pnl_pct=0.004,
                    exit_reason="TP_HIT", distance=0.08),
        SimilarCase(entry_rsi_15m=71.5, entry_macd_hist_15m=-0.0004,
                    entry_rsi_4h=66.0, outcome="LOSS", pnl_pct=-0.003,
                    exit_reason="SL_HIT", distance=0.12),
    ]
    text = format_cases_for_prompt(cases)
    assert "Historical similar cases" in text
    assert "73.2" in text or "73.20" in text
    assert "WIN" in text
    assert "LOSS" in text


def test_format_empty_returns_empty_string():
    from scripts.ai.local_rag import format_cases_for_prompt
    assert format_cases_for_prompt([]) == ""


def test_rag_utilization_24h(monkeypatch):
    """过去 24h "被注入 ≥1 case" 的占比。"""
    from scripts.ai.local_rag import rag_utilization_24h
    db = _fresh_db()
    conn = sqlite3.connect(db)
    for i, has_rag in enumerate([True, False, True]):
        reasoning = ("Historical similar cases: case1..." if has_rag else "...")
        conn.execute("""
            INSERT INTO trade_scores_v5 (symbol, created_at, should_trade,
              ai_reasoning, executed)
            VALUES (?, datetime('now', '-1 hour'), 1, ?, 1)
        """, (f"S{i}/USDT", reasoning))
    conn.commit()
    conn.close()
    ratio = rag_utilization_24h(db_path=db)
    assert abs(ratio - 2/3) < 0.01
