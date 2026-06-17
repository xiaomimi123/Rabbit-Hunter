"""Reflection runner — load context → AI → validate → persist.

异步 + 注入 ai_call (Callable[[str], Awaitable[str]]) 便于测试。
"""
import json
import sqlite3
import time
from typing import Awaitable, Callable, List, Optional

from pydantic import ValidationError

from api.schemas.v5_reflection import PROMPT_VERSION, ReflectionAIOutput
from scripts.ai.reflection_prompt import build_reflection_prompt
from scripts.ai.setup_type import derive_setup_type


AICall = Callable[[str], Awaitable[str]]


def _classify_outcome(realized_r: float) -> str:
    if abs(realized_r) < 0.2:
        return "SCRATCH"
    return "WIN" if realized_r > 0 else "LOSS"


def _holding_minutes(entry_iso: str, exit_iso: str) -> int:
    from datetime import datetime
    dt_e = datetime.fromisoformat(entry_iso.replace("Z", "+00:00"))
    dt_x = datetime.fromisoformat(exit_iso.replace("Z", "+00:00"))
    return int((dt_x - dt_e).total_seconds() / 60)


def _load_close_context(db_path: str, paper_trade_id: int,
                         taxonomy_keys: List[str]) -> Optional[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        pt = conn.execute(
            "SELECT * FROM paper_trades WHERE id=?", (paper_trade_id,)
        ).fetchone()
        if pt is None or (pt["status"] or "").upper() != "CLOSED":
            return None

        # 取入场时的 trade_scores_v5 (拿 macd_hist_prev / 4h refs)
        ts = conn.execute(
            "SELECT * FROM trade_scores_v5 WHERE position_id=? ORDER BY id DESC LIMIT 1",
            (paper_trade_id,)
        ).fetchone()
    finally:
        conn.close()

    entry_price = float(pt["entry_price"] or 0.0)
    exit_price = float(pt["exit_price"] or entry_price)
    sl_price = float(pt["stop_loss"] or 0.0)
    side = (pt["side"] or "").upper()

    # realized_r = pnl / |sl_distance|
    pnl_pct = float(pt["pnl_percent"] or 0.0) / 100.0
    sl_dist_pct = (
        abs(sl_price - entry_price) / entry_price if entry_price > 0 and sl_price > 0
        else 0.01
    )
    realized_r = pnl_pct / sl_dist_pct if sl_dist_pct > 0 else 0.0

    rsi_15m = float(pt["entry_rsi_15m"] or (ts["rsi_15m"] if ts else 50.0))
    macd_hist = float(pt["entry_macd_hist_15m"] or (ts["macd_hist_15m"] if ts else 0.0))
    macd_hist_prev = float(ts["macd_hist_prev_15m"] if ts else 0.0)

    # V6: 拉 funding state at entry
    funding_z_score_at_entry = None
    funding_rate_at_entry = None
    try:
        # Prefer trade_scores_v5.funding_z_score (scorer 写入时刻的快照)
        if ts is not None and ts["funding_z_score"] is not None:
            funding_z_score_at_entry = float(ts["funding_z_score"])
            funding_rate_at_entry = (
                float(ts["funding_rate_8h"]) if ts["funding_rate_8h"] is not None
                else None
            )
        else:
            # Fallback: 找最接近 entry_time 的 funding_rates 行
            conn2 = sqlite3.connect(db_path)
            try:
                fr_row = conn2.execute("""
                    SELECT funding_rate FROM funding_rates
                     WHERE symbol = ? AND funding_time <= ?
                     ORDER BY funding_time DESC LIMIT 1
                """, (pt["symbol"], pt["entry_time"])).fetchone()
                if fr_row:
                    funding_rate_at_entry = float(fr_row[0])
            finally:
                conn2.close()
    except Exception as e:
        print(f"[reflection_runner] funding lookup failed: {e}")

    setup_type = derive_setup_type({
        "side": side, "strategy_id": pt["strategy_id"] or "v5_rsi_macd",
        "rsi_15m": rsi_15m,
        "macd_hist": macd_hist, "macd_hist_prev": macd_hist_prev,
        "funding_z_score": funding_z_score_at_entry,
    })

    return {
        "paper_trade_id": paper_trade_id,
        "symbol": pt["symbol"],
        "side": side,
        "strategy_id": pt["strategy_id"],
        "entry_price": entry_price,
        "exit_price": exit_price,
        "entry_time": pt["entry_time"],
        "exit_time": pt["exit_time"],
        "exit_reason": pt["exit_reason"],
        "realized_r": realized_r,
        "holding_minutes": _holding_minutes(pt["entry_time"], pt["exit_time"]),
        "confidence_at_entry": float(pt["ai_confidence"] or 0.0),
        "entry_rsi_15m": rsi_15m,
        "entry_rsi_4h": float(ts["rsi_4h"]) if ts and ts["rsi_4h"] is not None else None,
        "entry_macd_hist_15m": macd_hist,
        "entry_macd_hist_prev_15m": macd_hist_prev,
        "entry_atr_15m": float(pt["atr_k"] or (ts["atr_15m"] if ts else 0.0)),
        "funding_z_score": funding_z_score_at_entry,
        "funding_rate_at_entry": funding_rate_at_entry,
        "rule_reasoning": ts["reasoning"] if ts else None,
        "ai_reasoning": pt["ai_reason"],
        "rag_cases_text": None,    # 阶段 1 暂不回填,留 prompt 优雅处理 None
        "during_hold_path": None,
        "taxonomy_keys": taxonomy_keys,
        "_setup_type": setup_type,
        "_pnl_pct": pnl_pct,
    }


def _persist(db_path: str, ctx: dict, ai_out: ReflectionAIOutput,
              raw: str, latency_ms: int, ai_provider: Optional[str],
              ai_model: Optional[str]) -> None:
    realized_r = ctx["realized_r"]
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            INSERT INTO reflections (
                paper_trade_id, why_entered, what_was_expected, what_actually_happened,
                correction_idea, failure_mode_key, setup_type, outcome_class,
                realized_r, holding_minutes, confidence_at_entry,
                self_assessed_prediction_accuracy, is_in_predicted_failure_mode,
                ai_provider, ai_model, ai_latency_ms, prompt_version, raw_response_json,
                funding_z_score_at_entry, funding_rate_at_entry
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ctx["paper_trade_id"], ai_out.why_entered, ai_out.what_was_expected,
            ai_out.what_actually_happened, ai_out.correction_idea,
            ai_out.failure_mode_key, ctx["_setup_type"],
            _classify_outcome(realized_r), realized_r,
            ctx["holding_minutes"], ctx["confidence_at_entry"],
            ai_out.self_assessed_prediction_accuracy,
            1 if ai_out.is_in_predicted_failure_mode else 0,
            ai_provider, ai_model, latency_ms, PROMPT_VERSION, raw,
            ctx.get("funding_z_score"), ctx.get("funding_rate_at_entry"),
        ))
        conn.commit()
    finally:
        conn.close()


def _already_reflected(db_path: str, paper_trade_id: int) -> bool:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM reflections WHERE paper_trade_id=? LIMIT 1",
            (paper_trade_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


async def run_reflection_for_trade(*, paper_trade_id: int, db_path: str,
                                    ai_call: AICall,
                                    taxonomy_keys: List[str],
                                    ai_provider: Optional[str] = None,
                                    ai_model: Optional[str] = None) -> None:
    """主入口。pre-check idempotent → load ctx → ai → validate → persist。"""
    if _already_reflected(db_path, paper_trade_id):
        return

    ctx = _load_close_context(db_path, paper_trade_id, taxonomy_keys)
    if ctx is None:
        raise ValueError(f"paper_trade {paper_trade_id} not found or not CLOSED")

    prompt = build_reflection_prompt(ctx)
    t0 = time.monotonic()
    raw = await ai_call(prompt)
    latency_ms = int((time.monotonic() - t0) * 1000)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"reflection AI response is not JSON: {e}") from e

    try:
        ai_out = ReflectionAIOutput.model_validate(parsed)
    except ValidationError as e:
        raise ValueError(f"reflection AI response failed schema: {e}") from e

    _persist(db_path, ctx, ai_out, raw, latency_ms, ai_provider, ai_model)

    # B-Phase-3: 更新 calibration
    if ai_model:
        try:
            from scripts.ai.confidence_calibration import update_calibration
            update_calibration(
                ai_model=ai_model,
                confidence_at_entry=ctx["confidence_at_entry"],
                won=(ctx["realized_r"] > 0),
                db_path=db_path,
            )
        except Exception as e:
            print(f"[reflection] calibration update failed: {e}")
