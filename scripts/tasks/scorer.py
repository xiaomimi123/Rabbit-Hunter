"""V5 Scorer — 管道粘合层。

输入:enriched_queue(EnrichedItem)
输出:write_queue(trade_scores_v5 行)+ 触发 paper_pm / live_pm 开仓
"""
import asyncio
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from v5_indicator_engine import calculate_indicators
from v5_strategy import decide
from v5_risk_calculator import plan
from v5_types import AIResult, Decision, EnrichedItem, Indicators, RiskPlan


from scripts.v5_params import get_param


def _enqueue_ws(db_path: str, payload: dict) -> None:
    """跨进程 WS 消息总线:写 ws_event_queue,api 进程 poll 后广播。"""
    import json, sqlite3
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "INSERT INTO ws_event_queue (payload_json) VALUES (?)",
                (json.dumps(payload, ensure_ascii=False),),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[V5Scorer] WS enqueue 失败: {e}")


def _max_concurrent() -> int:
    return int(get_param("v5_max_concurrent", 3, int))


def _risk_per_trade() -> float:
    return float(get_param("v5_risk_per_trade", 0.015, float))


def _leverage() -> int:
    return int(get_param("v5_leverage", 10, int))


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _count_open_positions(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        n_paper = conn.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'").fetchone()[0]
        n_live = conn.execute(
            "SELECT COUNT(*) FROM positions_v5 WHERE status='OPEN'").fetchone()[0]
        return n_paper + n_live
    finally:
        conn.close()


def _write_trade_score(db_path: str, enriched: EnrichedItem, indicators: Indicators,
                       decision: Decision, ai: Optional[AIResult] = None,
                       risk: Optional[RiskPlan] = None, executed: bool = False,
                       position_id: Optional[int] = None,
                       block_reason: Optional[str] = None) -> int:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("""
            INSERT INTO trade_scores_v5 (
                symbol, created_at, delta_15m_pct, volume_24h_usdt,
                rsi_15m, macd_15m, macd_signal_15m, macd_hist_15m, macd_hist_prev_15m,
                rsi_4h, macd_hist_4h, atr_15m, current_price,
                should_trade, side, reasoning, block_reason,
                ai_confidence, ai_sl_multiplier, ai_tp_multiplier, ai_size_multiplier,
                ai_reasoning,
                entry_price, sl_price, tp_price, size_usdt, expected_rr,
                executed, position_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            enriched.symbol, _utcnow(), enriched.delta_15m_pct, enriched.volume_24h_usdt,
            indicators.rsi_15m, indicators.macd_15m, indicators.macd_signal_15m,
            indicators.macd_hist_15m, indicators.macd_hist_prev_15m,
            indicators.rsi_4h, indicators.macd_hist_4h, indicators.atr_15m,
            enriched.current_price,
            1 if decision.should_trade else 0, decision.side,
            decision.reasoning, block_reason or decision.block_reason,
            ai.confidence if ai else None,
            ai.sl_multiplier if ai else None,
            ai.tp_multiplier if ai else None,
            ai.size_multiplier if ai else None,
            ai.reasoning if ai else None,
            risk.entry_price if risk else None,
            risk.sl_price if risk else None,
            risk.tp_price if risk else None,
            risk.size_usdt if risk else None,
            risk.expected_rr if risk else None,
            1 if executed else 0, position_id,
        ))
        sid = cur.lastrowid
        conn.commit()
        return sid
    finally:
        conn.close()


async def process_enriched_v5(*, enriched: EnrichedItem, ai, paper_pm, live_pm,
                              mode: str, db_path: str, balance_usdt: float) -> None:
    """处理一个 enriched item 走完 V5 管道。"""
    # Top-20 whitelist filter (V5.1)
    if get_param("v5_use_symbol_whitelist", True,
                 lambda v: str(v).lower() not in ("false", "0", "no")):
        from scripts.v5_symbol_whitelist import parse_whitelist_param, is_symbol_allowed
        whitelist_raw = get_param("v5_symbol_whitelist", "", str)
        whitelist = parse_whitelist_param(whitelist_raw)
        if not is_symbol_allowed(enriched.symbol, whitelist):
            return    # Skip silently — not in whitelist, don't even write a trade_score

    try:
        indicators = calculate_indicators(enriched.klines_15m, enriched.klines_4h)
    except ValueError as e:
        print(f"[V5Scorer] {enriched.symbol} 指标计算失败: {e}")
        return

    decision = decide(enriched, indicators)
    if not decision.should_trade:
        _write_trade_score(db_path, enriched, indicators, decision)
        return

    if _count_open_positions(db_path) >= _max_concurrent():
        _write_trade_score(db_path, enriched, indicators, decision,
                          block_reason="MAX_CONCURRENT_POSITIONS")
        return

    risk = plan(
        side=decision.side, entry=enriched.current_price,
        atr=indicators.atr_15m, balance=balance_usdt,
        risk_pct=_risk_per_trade(), leverage=_leverage(),
    )

    # ai=None 兼容(OPENAI_AI_ENABLED=false 或 AI 初始化失败):
    # SHADOW 模式下走纯规则引擎,直接构造一个 pass-through AIResult;
    # LIVE 模式 fail-closed 拒绝,理由清晰可追溯。
    if ai is None:
        if mode == "SHADOW":
            ai_result = AIResult(execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
                                  size_multiplier=1.0, confidence=0.5,
                                  reasoning="AI disabled — SHADOW pass-through")
        else:
            _write_trade_score(db_path, enriched, indicators, decision,
                              block_reason="AI_UNAVAILABLE_LIVE_FAIL_CLOSED")
            return
    else:
        ai_result = await ai.decide(enriched, indicators, decision, risk)
        if not ai_result.execute:
            _write_trade_score(db_path, enriched, indicators, decision,
                              ai=ai_result, risk=risk, block_reason="AI_REJECTED")
            return

    try:
        if mode == "SHADOW":
            position_id = paper_pm.open_position(
                enriched=enriched, indicators=indicators,
                decision=decision, risk=risk, ai=ai_result,
            )
        else:
            position_id = live_pm.open_position(
                symbol=enriched.symbol, side=decision.side,
                entry_price=risk.entry_price, sl_price=risk.sl_price,
                tp_price=risk.tp_price, size_usdt=risk.size_usdt,
                leverage=risk.leverage,
            )
    except Exception as e:
        _write_trade_score(db_path, enriched, indicators, decision,
                          ai=ai_result, risk=risk,
                          block_reason=f"OPEN_FAILED:{type(e).__name__}")
        return

    _write_trade_score(db_path, enriched, indicators, decision,
                      ai=ai_result, risk=risk, executed=True,
                      position_id=position_id)
    print(f"[V5Scorer] {enriched.symbol} OPEN {decision.side} executed,position_id={position_id}")
    _enqueue_ws(db_path, {
        "type": "position_opened",
        "symbol": enriched.symbol,
        "side": decision.side,
        "entry": risk.entry_price,
        "sl": risk.sl_price,
        "tp": risk.tp_price,
        "size_usdt": risk.size_usdt,
        "position_id": position_id,
        "strategy_id": "v5_rsi_macd" if mode == "SHADOW" else "v5_live",
        "mode": mode,
    })


class V5Scorer:
    """异步任务包装,从 enriched_queue 消费,调 process_enriched_v5。"""

    def __init__(self, enriched_queue, ai, paper_pm, live_pm,
                 mode_resolver, balance_fetcher, db_path: str = "data/rabbit_hunter.db"):
        self.enriched_queue = enriched_queue
        self.ai = ai
        self.paper_pm = paper_pm
        self.live_pm = live_pm
        self.resolve_mode = mode_resolver
        self.fetch_balance = balance_fetcher
        self.db_path = db_path

    async def run(self):
        print("[V5Scorer] 启动")
        while True:
            try:
                enriched: EnrichedItem = await self.enriched_queue.get()
            except asyncio.CancelledError:
                return
            try:
                mode = self.resolve_mode()
                balance = self.fetch_balance()
                await process_enriched_v5(
                    enriched=enriched, ai=self.ai,
                    paper_pm=self.paper_pm, live_pm=self.live_pm,
                    mode=mode, db_path=self.db_path, balance_usdt=balance,
                )
            except Exception as e:
                print(f"[V5Scorer] {enriched.symbol} 处理异常: {type(e).__name__}: {e}")
