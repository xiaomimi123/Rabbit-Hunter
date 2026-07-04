"""/api/v5/manual-order/{preview,execute}

复用 V5 完整管道:fetch_klines → calculate_indicators → V5Strategy →
RiskCalculator → TradingAssistant(含 RAG)。preview 不写库,execute 走
PaperPositionManager.open_position 并打 strategy_id='v5_manual'。
"""
import os
from typing import Optional

from fastapi import APIRouter, HTTPException

from api.schemas.v5_manual_order import (
    ManualOrderPreviewRequest, ManualOrderPreviewResponse,
    ManualOrderDecisionSnapshot, ManualOrderRagCase,
    ManualOrderExecuteRequest, ManualOrderExecuteResponse,
)
from scripts.risk_gates import (
    IronlawViolation, gate_setup_enabled,
    gate_daily_drawdown, gate_per_trade_risk,
    get_today_realized_pnl,
)
from scripts.config import get_config


router = APIRouter(prefix="/api/v5", tags=["manual-order"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


async def _build_full_context(symbol: str, side_hint: Optional[str]):
    """共用:拉 K 线 → indicators → enriched → decision → risk → AI → rag。"""
    from scripts.tasks.exchange_endpoints import fetch_klines
    from v5_indicator_engine import calculate_indicators
    from v5_strategy import decide as strategy_decide
    from v5_risk_calculator import plan as risk_plan
    from v5_types import EnrichedItem
    from scripts.ai.trading_assistant import TradingAssistant
    from scripts.ai.local_rag import find_similar_cases

    klines_15m = fetch_klines(symbol, "15m", 50)
    klines_4h = fetch_klines(symbol, "4h", 50)
    indicators = calculate_indicators(klines_15m, klines_4h)

    current_price = float(klines_15m[-1][4]) if klines_15m else 0.0
    delta_15m_pct = (klines_15m[-1][4] - klines_15m[-1][1]) / (klines_15m[-1][1] or 1.0) if klines_15m else 0.0

    enriched = EnrichedItem(
        symbol=symbol, current_price=current_price,
        delta_15m_pct=delta_15m_pct, volume_24h_usdt=0.0,
        klines_15m=klines_15m, klines_4h=klines_4h,
    )

    decision = strategy_decide(enriched, indicators)
    effective_side = decision.side or side_hint or "SHORT"

    balance = float(os.environ.get("PAPER_INITIAL_BALANCE_USDT", "1000"))
    from scripts.v5_params import get_param
    risk = risk_plan(
        side=effective_side, entry=current_price, atr=indicators.atr_15m,
        balance=balance, risk_pct=float(get_param("v5_risk_per_trade", 0.015, float)),
        leverage=int(get_param("v5_leverage", 10, int)),
    )

    ta = TradingAssistant()
    if ta.client:
        ai_result = await ta.decide(enriched, indicators, decision, risk,
                                     strategy_id="v5_manual")
        ai_dict = {
            "execute": ai_result.execute,
            "sl_multiplier": ai_result.sl_multiplier,
            "tp_multiplier": ai_result.tp_multiplier,
            "size_multiplier": ai_result.size_multiplier,
            "confidence": ai_result.confidence,
            "reasoning": ai_result.reasoning,
        }
    else:
        ai_dict = {"execute": False, "sl_multiplier": 1.0, "tp_multiplier": 1.0,
                   "size_multiplier": 0.0, "confidence": 0.0,
                   "reasoning": "AI 未配置"}

    rag = find_similar_cases(
        indicators, side=effective_side, top_k=5,
        source_delta_15m_pct=delta_15m_pct,
    )
    return enriched, indicators, decision, risk, ai_dict, rag, effective_side


@router.post("/manual-order/preview", response_model=ManualOrderPreviewResponse)
async def preview(req: ManualOrderPreviewRequest) -> ManualOrderPreviewResponse:
    try:
        enriched, indicators, decision, risk, ai_dict, rag, eff_side = \
            await _build_full_context(req.symbol, req.side)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"preview 失败: {type(e).__name__}: {e}")

    rag_cases = [
        ManualOrderRagCase(
            entry_rsi_15m=c.entry_rsi_15m,
            entry_macd_hist_15m=c.entry_macd_hist_15m,
            outcome=c.outcome,
            pnl_pct=c.pnl_pct,
            exit_reason=c.exit_reason,
            distance=c.distance,
        ) for c in rag
    ]

    rag_summary = None
    if rag_cases:
        wins = sum(1 for c in rag_cases if c.outcome == "WIN")
        avg = sum(c.pnl_pct for c in rag_cases) / len(rag_cases)
        rag_summary = f"{wins}/{len(rag_cases)} win,avg pnl {avg*100:+.2f}%"

    return ManualOrderPreviewResponse(
        symbol=req.symbol,
        side=eff_side,
        current_price=enriched.current_price,
        indicators={
            "rsi_15m": indicators.rsi_15m,
            "macd_hist_15m": indicators.macd_hist_15m,
            "macd_hist_prev_15m": indicators.macd_hist_prev_15m,
            "atr_15m": indicators.atr_15m,
            "rsi_4h": indicators.rsi_4h,
            "macd_hist_4h": indicators.macd_hist_4h,
        },
        decision=ManualOrderDecisionSnapshot(
            should_trade=decision.should_trade,
            side=decision.side,
            reasoning=decision.reasoning,
            block_reason=decision.block_reason,
        ),
        risk_plan={
            "entry_price": risk.entry_price,
            "sl_price": risk.sl_price,
            "tp_price": risk.tp_price,
            "size_usdt": risk.size_usdt,
            "leverage": risk.leverage,
            "expected_rr": risk.expected_rr,
        },
        ai_result=ai_dict,
        rag_cases=rag_cases,
        rag_summary=rag_summary,
    )


@router.post("/manual-order/execute", response_model=ManualOrderExecuteResponse)
async def execute(req: ManualOrderExecuteRequest) -> ManualOrderExecuteResponse:
    try:
        enriched, indicators, decision, risk, ai_dict, _rag, _eff = \
            await _build_full_context(req.symbol, req.side)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"execute 准备失败: {type(e).__name__}: {e}")

    from v5_types import AIResult, Decision
    ai = AIResult(
        execute=True,
        sl_multiplier=req.sl_multiplier,
        tp_multiplier=req.tp_multiplier,
        size_multiplier=req.size_multiplier,
        confidence=float(ai_dict.get("confidence") or 0.0),
        reasoning=f"[v5_manual] " + (ai_dict.get("reasoning") or ""),
        error_kind="ok",
    )
    forced_decision = Decision(
        should_trade=True, side=req.side,
        reasoning=decision.reasoning, block_reason=None,
    )

    # ── M3 铁律层 (Finding 13):manual 与 scorer 走同一层守卫 ──
    # 1. SHORT 全局开关
    if req.side == "SHORT" and not get_config(reload=True).enable_short_trading:
        raise HTTPException(
            status_code=400,
            detail={
                "error_kind": "SHORT_DISABLED",
                "gate": "enable_short_trading",
                "message": "ENABLE_SHORT_TRADING=false;SHORT 交易被全局关闭",
            },
        )

    # 2. Setup 禁用清单
    try:
        from scripts.ai.setup_type import derive_setup_type
        setup_type = derive_setup_type({
            "side": req.side,
            "rsi_15m": indicators.rsi_15m,
            "macd_hist": indicators.macd_hist_15m,
            "macd_hist_prev": indicators.macd_hist_prev_15m,
            "funding_z_score": None,
        })
        gate_setup_enabled(setup_type=setup_type, db_path=_db())
    except IronlawViolation as e:
        raise HTTPException(
            status_code=400,
            detail={"error_kind": e.kind, "gate": "gate_setup_enabled", "message": str(e)},
        )

    # 3. 日熔断
    balance = float(os.environ.get("PAPER_INITIAL_BALANCE_USDT", "1000"))
    try:
        today_pnl = get_today_realized_pnl(_db())
        gate_daily_drawdown(equity_usdt=balance, today_realized_pnl=today_pnl)
    except IronlawViolation as e:
        raise HTTPException(
            status_code=400,
            detail={"error_kind": e.kind, "gate": "gate_daily_drawdown", "message": str(e)},
        )

    # 4. 单笔风险
    from scripts.v5_params import get_param
    cap_pct = float(get_param("v5_risk_per_trade", 0.015, float))
    sl_dist = abs(risk.entry_price - risk.sl_price) * req.sl_multiplier
    sl_dist_pct = sl_dist / max(risk.entry_price, 1e-9)
    final_size = risk.size_usdt * req.size_multiplier
    planned_loss = final_size * risk.leverage * sl_dist_pct
    try:
        gate_per_trade_risk(
            equity_usdt=balance, planned_loss_usdt=planned_loss, cap_pct=cap_pct,
        )
    except IronlawViolation as e:
        raise HTTPException(
            status_code=400,
            detail={"error_kind": e.kind, "gate": "gate_per_trade_risk", "message": str(e)},
        )

    from scripts.paper_position_manager import PaperPositionManager
    pm = PaperPositionManager(db_path=_db())
    pid = pm.open_position(
        enriched=enriched, indicators=indicators,
        decision=forced_decision, risk=risk, ai=ai,
    )
    import sqlite3
    conn = sqlite3.connect(_db())
    try:
        conn.execute("UPDATE paper_trades SET strategy_id='v5_manual' WHERE id=?", (pid,))
        conn.commit()
        row = conn.execute(
            "SELECT symbol, side, entry_price, stop_loss, take_profit, position_size_usdt "
            "FROM paper_trades WHERE id=?", (pid,)).fetchone()
    finally:
        conn.close()

    return ManualOrderExecuteResponse(
        position_id=pid,
        symbol=row[0],
        side=row[1],
        entry_price=float(row[2] or 0.0),
        sl_price=float(row[3] or 0.0),
        tp_price=float(row[4] or 0.0),
        size_usdt=float(row[5] or 0.0),
        strategy_id="v5_manual",
    )
