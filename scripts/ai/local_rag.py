"""V5 本地 RAG-lite — DeepSeek-friendly,Vector Store-free。

decide() 之前查 ai_training_data 中已平仓且同 side 的样本,按加权欧氏距离
排序取 top-K,把结果格式化注入 system prompt。

距离公式按重要性加权:
  d = sqrt(
        ((rsi_15m   - entry_rsi_15m)        / 100  ) ** 2 +
        ((macd_hist - entry_macd_hist_15m)  * 1000 ) ** 2 +
        ((rsi_4h    - entry_rsi_4h)         / 100  ) ** 2 * 0.5 +
        ((delta     - delta_15m_pct)        * 10   ) ** 2 * 0.3
      )
"""
import os
import sqlite3
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class SimilarCase:
    entry_rsi_15m: float
    entry_macd_hist_15m: float
    entry_rsi_4h: float
    outcome: str            # WIN / LOSS / FLAT
    pnl_pct: float
    exit_reason: str
    distance: float


def _db_path(explicit: Optional[str]) -> str:
    return explicit or os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def find_similar_cases(
    indicators,
    side: str,
    top_k: int = 5,
    *,
    source_delta_15m_pct: float = 0.0,
    db_path: Optional[str] = None,
    cold_start_threshold: int = 10,
) -> List[SimilarCase]:
    """查 ai_training_data 同 side 已平仓样本,返回 top-K 最近。

    冷启动:同 side 已平仓样本 < cold_start_threshold 行 → 返回 []。
    """
    db = _db_path(db_path)
    try:
        conn = sqlite3.connect(db)
    except Exception:
        return []
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM ai_training_data "
            "WHERE side = ? AND outcome IS NOT NULL", (side,)
        ).fetchone()[0]
        if count < cold_start_threshold:
            return []

        rows = conn.execute(
            "SELECT entry_rsi_15m, entry_macd_hist_15m, entry_rsi_4h, "
            "       delta_15m_pct, outcome, pnl_pct, exit_reason "
            "  FROM ai_training_data "
            " WHERE side = ? AND outcome IS NOT NULL", (side,)
        ).fetchall()
    finally:
        conn.close()

    candidates = []
    for (entry_rsi, entry_hist, entry_rsi_4h, entry_delta,
         outcome, pnl_pct, exit_reason) in rows:
        if entry_rsi is None or entry_hist is None or entry_rsi_4h is None:
            continue
        d_rsi   = (indicators.rsi_15m       - entry_rsi)      / 100.0
        d_hist  = (indicators.macd_hist_15m - entry_hist)     * 1000.0
        d_rsi4  = (indicators.rsi_4h        - entry_rsi_4h)   / 100.0
        d_delta = (source_delta_15m_pct     - (entry_delta or 0.0)) * 10.0
        dist = (d_rsi ** 2 + d_hist ** 2
                + d_rsi4 ** 2 * 0.5
                + d_delta ** 2 * 0.3) ** 0.5
        candidates.append(SimilarCase(
            entry_rsi_15m=float(entry_rsi),
            entry_macd_hist_15m=float(entry_hist),
            entry_rsi_4h=float(entry_rsi_4h),
            outcome=outcome or "FLAT",
            pnl_pct=float(pnl_pct or 0.0),
            exit_reason=exit_reason or "",
            distance=dist,
        ))

    candidates.sort(key=lambda c: c.distance)
    return candidates[:top_k]


def format_cases_for_prompt(cases: List[SimilarCase]) -> str:
    """渲染成给 AI 看的文本。空 list 返回空串。"""
    if not cases:
        return ""
    lines = ["Historical similar cases (top {} by weighted indicator distance):".format(len(cases))]
    for i, c in enumerate(cases, 1):
        lines.append(
            f"  case{i}: entry_rsi={c.entry_rsi_15m:.1f} "
            f"hist={c.entry_macd_hist_15m:+.4f} rsi_4h={c.entry_rsi_4h:.1f} "
            f"→ {c.outcome} pnl={c.pnl_pct*100:+.2f}% exit={c.exit_reason} "
            f"(distance={c.distance:.3f})"
        )
    n_win = sum(1 for c in cases if c.outcome == "WIN")
    avg_pnl = sum(c.pnl_pct for c in cases) / len(cases)
    lines.append(
        f"Aggregate: {n_win}/{len(cases)} win,avg pnl {avg_pnl*100:+.2f}%. "
        "Use these as base-rate hints; don't blindly follow."
    )
    return "\n".join(lines)


def rag_utilization_24h(*, db_path: Optional[str] = None) -> float:
    """过去 24h 决策中"被注入 ≥1 case"的占比。

    用 ai_reasoning 字段是否含 "Historical similar cases" 探测。
    """
    db = _db_path(db_path)
    try:
        conn = sqlite3.connect(db)
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM trade_scores_v5 "
                "WHERE should_trade=1 AND ai_reasoning IS NOT NULL "
                "  AND created_at >= datetime('now', '-24 hour')"
            ).fetchone()[0]
            with_rag = conn.execute(
                "SELECT COUNT(*) FROM trade_scores_v5 "
                "WHERE should_trade=1 "
                "  AND ai_reasoning LIKE '%Historical similar cases%' "
                "  AND created_at >= datetime('now', '-24 hour')"
            ).fetchone()[0]
        finally:
            conn.close()
    except Exception:
        return 0.0
    if total == 0:
        return 0.0
    return with_rag / total
