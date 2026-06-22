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
from scripts.risk_constitution import (
    MAX_PER_TRADE_RISK_PCT, resolve_risk_pct_for_equity,
)
from scripts.risk_gates import (
    IronlawViolation,
    clamp_evolution_size_mult, clamp_evolution_sl_mult, clamp_evolution_tp_mult,
    gate_daily_drawdown, gate_final_sl_ratio, gate_liquidation_distance,
    gate_min_rr, gate_per_trade_risk, gate_setup_enabled, gate_sl_attached,
    get_today_realized_pnl,
)


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


def _risk_per_trade(equity_usdt: float = 10_000.0) -> float:
    """M3 立宪后:风险百分比从 risk_constitution 资格层映射,而非 param。

    保留 v5_risk_per_trade 仅作为软上限(若 <宪法上限 则使用 param 值)。
    永远不超过宪法允许的 tier 值。
    """
    constitution_pct = resolve_risk_pct_for_equity(equity_usdt)
    param_pct = float(get_param("v5_risk_per_trade", MAX_PER_TRADE_RISK_PCT, float))
    return min(constitution_pct, param_pct)


def _leverage() -> int:
    return int(get_param("v5_leverage", 10, int))


def _enable_auto_trading(db_path: str) -> bool:
    """实时读 system_settings.enable_auto_trading。

    Dashboard 切开关后,scorer 下次 tick 立即看到(5s TTL 内可能多此一击,但写入会
    立即可见,因为这是直接的 SQLite 读)。默认 True — 没显式关时正常开仓。
    """
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key='enable_auto_trading' "
                "ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            if row and row[0] is not None:
                return str(row[0]).strip().lower() in ("1", "true", "yes")
            return True
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return True  # 表/库不存在时 fail-open(开发期不阻塞)


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
                       block_reason: Optional[str] = None,
                       funding_z_score: Optional[float] = None,
                       funding_rate_8h: Optional[float] = None) -> int:
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
                executed, position_id,
                funding_z_score, funding_rate_8h
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            funding_z_score, funding_rate_8h,
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

    # V6: 拉 funding z-score 并注入 trade_scores
    funding_z_score: Optional[float] = None
    funding_rate_8h: Optional[float] = None
    try:
        from scripts.ai.funding_rate_calculator import get_cached_zscore
        fz_row = get_cached_zscore(enriched.symbol, db_path=db_path)
        if fz_row:
            funding_z_score = fz_row["zscore_30d"]
            funding_rate_8h = fz_row["current_funding_rate"]
    except Exception as e:
        print(f"[V5Scorer] funding lookup 失败 ({enriched.symbol}): {e}")

    decision = decide(enriched, indicators, funding_z=funding_z_score)
    if not decision.should_trade:
        _write_trade_score(db_path, enriched, indicators, decision,
                          funding_z_score=funding_z_score,
                          funding_rate_8h=funding_rate_8h)
        return

    if _count_open_positions(db_path) >= _max_concurrent():
        _write_trade_score(db_path, enriched, indicators, decision,
                          block_reason="MAX_CONCURRENT_POSITIONS",
                          funding_z_score=funding_z_score,
                          funding_rate_8h=funding_rate_8h)
        return

    # Dashboard 启动/暂停扫描:每次 tick 读 system_settings.enable_auto_trading。
    # 关掉时仍写 trade_scores(诊断有价值)但不开仓 — 立即生效,不必重启容器。
    if not _enable_auto_trading(db_path):
        _write_trade_score(db_path, enriched, indicators, decision,
                          block_reason="AUTO_TRADING_DISABLED",
                          funding_z_score=funding_z_score,
                          funding_rate_8h=funding_rate_8h)
        return

    # M3 铁律层:setup 禁用清单 + 日熔断(开仓前两道闸门)。
    try:
        from scripts.ai.setup_type import derive_setup_type
        setup_type = derive_setup_type({
            "side": decision.side,
            "rsi_15m": indicators.rsi_15m,
            "macd_hist": indicators.macd_hist_15m,
            "macd_hist_prev": indicators.macd_hist_prev_15m,
            "funding_z_score": funding_z_score,
        })
        gate_setup_enabled(setup_type=setup_type, db_path=db_path)
    except IronlawViolation as e:
        _write_trade_score(db_path, enriched, indicators, decision,
                          block_reason=f"IRONLAW:{e.kind}",
                          funding_z_score=funding_z_score,
                          funding_rate_8h=funding_rate_8h)
        return

    try:
        today_pnl = get_today_realized_pnl(db_path)
        gate_daily_drawdown(equity_usdt=balance_usdt, today_realized_pnl=today_pnl)
    except IronlawViolation as e:
        _write_trade_score(db_path, enriched, indicators, decision,
                          block_reason=f"IRONLAW:{e.kind}",
                          funding_z_score=funding_z_score,
                          funding_rate_8h=funding_rate_8h)
        return

    # 单点解析风险百分比:同一值喂给 plan() 和后续 gate,确保一致。
    risk_pct = _risk_per_trade(balance_usdt)
    risk = plan(
        side=decision.side, entry=enriched.current_price,
        atr=indicators.atr_15m, balance=balance_usdt,
        risk_pct=risk_pct, leverage=_leverage(),
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
                              block_reason="AI_UNAVAILABLE_LIVE_FAIL_CLOSED",
                              funding_z_score=funding_z_score,
                              funding_rate_8h=funding_rate_8h)
            return
    else:
        ai_result = await ai.decide(enriched, indicators, decision, risk)
        if not ai_result.execute:
            _write_trade_score(db_path, enriched, indicators, decision,
                              ai=ai_result, risk=risk, block_reason="AI_REJECTED",
                              funding_z_score=funding_z_score,
                              funding_rate_8h=funding_rate_8h)
            return

    # M3 进化层 clamp:把 AI multipliers 钳在文档 §5 第二层窄区间内。
    ai_result = AIResult(
        execute=ai_result.execute,
        sl_multiplier=clamp_evolution_sl_mult(ai_result.sl_multiplier),
        tp_multiplier=clamp_evolution_tp_mult(ai_result.tp_multiplier),
        size_multiplier=clamp_evolution_size_mult(ai_result.size_multiplier),
        confidence=ai_result.confidence,
        reasoning=ai_result.reasoning,
    )

    # M3 铁律层(开仓前最后一道):SL ratio / RR / SL 必挂 / 强平距 / 单笔风险。
    try:
        final_sl_dist = abs(risk.entry_price - risk.sl_price) * ai_result.sl_multiplier
        final_tp_dist = abs(risk.tp_price - risk.entry_price) * ai_result.tp_multiplier
        gate_final_sl_ratio(sl_distance=final_sl_dist, atr=indicators.atr_15m)
        gate_min_rr(sl_distance=final_sl_dist, tp_distance=final_tp_dist)
        final_sl_price = (
            risk.entry_price - final_sl_dist if decision.side == "LONG"
            else risk.entry_price + final_sl_dist
        )
        gate_sl_attached(sl_price=final_sl_price)
        gate_liquidation_distance(
            entry=risk.entry_price, sl_price=final_sl_price,
            leverage=risk.leverage, side=decision.side,
        )
        # 单笔风险:size × leverage × sl_dist_pct,SL 放宽时按比例重算 size 再 gate。
        final_sl_dist_pct = final_sl_dist / risk.entry_price
        max_size_for_cap = (balance_usdt * risk_pct) / (final_sl_dist_pct * risk.leverage)
        final_size = min(
            risk.size_usdt * ai_result.size_multiplier,
            max_size_for_cap,
        )
        # 反算 size_multiplier 给 paper_pm 落库
        actual_size_mult = final_size / risk.size_usdt if risk.size_usdt > 0 else 1.0
        ai_result = AIResult(
            execute=ai_result.execute,
            sl_multiplier=ai_result.sl_multiplier,
            tp_multiplier=ai_result.tp_multiplier,
            size_multiplier=actual_size_mult,
            confidence=ai_result.confidence,
            reasoning=ai_result.reasoning,
        )
        planned_loss = final_size * risk.leverage * final_sl_dist_pct
        gate_per_trade_risk(
            equity_usdt=balance_usdt, planned_loss_usdt=planned_loss,
            cap_pct=risk_pct,
        )
    except IronlawViolation as e:
        _write_trade_score(db_path, enriched, indicators, decision,
                          ai=ai_result, risk=risk,
                          block_reason=f"IRONLAW:{e.kind}",
                          funding_z_score=funding_z_score,
                          funding_rate_8h=funding_rate_8h)
        print(f"[V5Scorer] {enriched.symbol} IRONLAW reject: {e}")
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
                          block_reason=f"OPEN_FAILED:{type(e).__name__}",
                          funding_z_score=funding_z_score,
                          funding_rate_8h=funding_rate_8h)
        return

    _write_trade_score(db_path, enriched, indicators, decision,
                      ai=ai_result, risk=risk, executed=True,
                      position_id=position_id,
                      funding_z_score=funding_z_score,
                      funding_rate_8h=funding_rate_8h)
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
