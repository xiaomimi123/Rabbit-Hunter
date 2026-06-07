"""
StrategyScorer - V4.3 feature extraction, scoring, and V4.4 routing.

Responsibility:
  Layer-3 (storage & scoring) of the three-layer funnel:
  - Consumes enriched metric dicts from *enriched_queue* (produced by
    DeepCollector).
  - Applies the Phase/Kill-Zone/Exit-Clarity inference pipeline (V4.0+).
  - Runs V4.1 ATR/structure gap/phase-age calculations.
  - Runs V4.2 Golden Wick detection.
  - Runs V4.3 feature extraction + aggregate scoring + decision policy.
  - Optionally runs V4.4 strategy routing.
  - Optionally calls AI judge (DeepSeek / local LR).
  - Determines storage policy (Shadow Mode: PERFECT / POTENTIAL / SHADOW).
  - Enqueues write tasks onto *write_queue* (consumed by DatabaseWriter).

All module imports that might be absent (v43_*, v41_*, whale_detector, etc.)
are wrapped in try/except ImportError so the scorer degrades gracefully when
optional modules are not installed.
"""

from __future__ import annotations

import asyncio
import os
import time
import traceback
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supabase import Client

from .utils import symbol_to_binance_symbol, normalize_binance_symbol
from .writer import safe_enqueue

# ---------------------------------------------------------------------------
# Optional module flags – set at import time
# ---------------------------------------------------------------------------

try:
    from cvd_analyzer import CVDAnalyzer as _CVDAnalyzer  # type: ignore
    _CVD_AVAILABLE = True
except Exception:
    _CVD_AVAILABLE = False
    _CVDAnalyzer = None  # type: ignore

try:
    from v43_feature_extractor import extract_features  # type: ignore
    from v43_score_calculator import aggregate_score  # type: ignore
    from v43_hard_filters import pass_hard_filters  # type: ignore
    from v43_decision_policy import decision_policy, detect_market_regime, get_account_stage  # type: ignore
    from v43_weight_manager import load_weights, DEFAULT_WEIGHTS  # type: ignore
    from v43_chandelier_stop import initialize_position, update_chandelier_stop, should_exit_position  # type: ignore
    from v43_position_manager import V43PositionManager  # type: ignore
    _V43_AVAILABLE = True
except Exception as _v43_err:
    print(f"[WARNING] V4.3 模块导入失败: {_v43_err}")
    _V43_AVAILABLE = False
    V43PositionManager = None  # type: ignore

    def extract_features(*a, **kw): return {}  # noqa: E704
    def aggregate_score(*a, **kw): return {"final_score": 0.0, "block_reason": "V4.3 未加载"}  # noqa: E704
    def pass_hard_filters(*a, **kw): return (False, "V4.3 未加载")  # noqa: E704
    def decision_policy(*a, **kw): return {"should_trade": False, "reason": "V4.3 未加载"}  # noqa: E704
    def detect_market_regime(*a, **kw): return "UNCERTAIN"  # noqa: E704
    def get_account_stage(*a, **kw): return "CONSERVATIVE"  # noqa: E704
    def load_weights(*a, **kw): return {}  # noqa: E704
    DEFAULT_WEIGHTS = {}

# ---------------------------------------------------------------------------
# Snapshot helper (V4 UI snapshot field builder)
# ---------------------------------------------------------------------------

def compute_v4_snapshot(
    *,
    market_phase: str | None,
    kill_zone_signal: str | None,
    exit_clarity_score: int | None,
    funding_rate: float,
    confidence_level: int | None,
    ls_ratio: float | None,
) -> tuple[str, list[str], int]:
    """
    Build the market_regime / risk_reasons / risk_score triple used by the
    UI snapshot and ai_training_data display fields.

    NOTE: risk_score is purely for UI ordering/visualisation; it no longer
    gates trading decisions (those are governed by phase/kill_zone/exit_clarity).
    """
    reasons: list[str] = []
    kz = (kill_zone_signal or "NONE").upper()
    phase = market_phase or "UNKNOWN"
    exit_score = int(exit_clarity_score) if exit_clarity_score is not None else 0

    def _to_db_regime(kz_: str, phase_: str) -> str:
        kz_u = kz_.upper()
        ph_u = phase_.upper()
        if kz_u in ("SQUEEZE", "SHORT_SQUEEZE"):
            return "SQUEEZE"
        if kz_u in ("SHAKEOUT", "ACCUMULATION"):
            return "MANIPULATED"
        if ph_u in ("P3A_PUMP_START", "P3B_PUMP_LATE"):
            return "TREND_UP"
        if ph_u in ("P4_DISTRIBUTION",):
            return "TREND_DOWN"
        return "NORMAL"

    regime = _to_db_regime(kz, phase)
    if kz in ("SQUEEZE", "ACCUMULATION", "SHAKEOUT"):
        reasons.append(f"KZ_{kz}")
    else:
        reasons.append(f"PHASE_{phase}")

    score = 20
    if kz == "SQUEEZE":
        score = 92
    elif kz == "SHAKEOUT":
        score = 78
    elif kz == "ACCUMULATION":
        score = 55
    elif phase == "P3A_PUMP_START":
        score = 70
    elif phase in ("P3B_PUMP_LATE", "P4_DISTRIBUTION"):
        score = 85
    elif phase == "P1_NO_WHALE":
        score = 25

    if funding_rate < -0.0005:
        reasons.append("NEGATIVE_FUNDING")
        score = max(score, 90)

    score = max(10, min(100, score - int(exit_score / 10)))

    if confidence_level is not None and confidence_level >= 80:
        reasons.append("ANTI_CONFIDENCE_BRAKE")
        score = min(100, score + 5)

    if ls_ratio is not None and float(ls_ratio) > 2.5:
        reasons.append("HIGH_LS_RATIO")
        score = min(100, score + 5)

    return regime, reasons, int(score)


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------

def _build_snapshot_row(symbol: str, now_iso: str, metrics: dict) -> dict:
    price = float(metrics["price"])
    funding_rate = float(metrics["funding_rate"])
    market_phase = metrics.get("market_phase")
    kill_zone_signal = metrics.get("kill_zone_signal")
    exit_clarity_score = metrics.get("exit_clarity_score")
    confidence_level = metrics.get("confidence_level")
    ai_score = metrics.get("ai_score")
    ai_allowed = metrics.get("ai_allowed")
    ai_reason = metrics.get("ai_reason")
    ai_version = metrics.get("ai_version")
    p3a_match_score = metrics.get("p3a_match_score")
    ai_effective_threshold = metrics.get("ai_effective_threshold")
    ls_ratio = metrics.get("ls_ratio")

    market_regime, risk_reasons, risk_score = compute_v4_snapshot(
        market_phase=market_phase,
        kill_zone_signal=kill_zone_signal,
        exit_clarity_score=exit_clarity_score,
        funding_rate=funding_rate,
        confidence_level=confidence_level,
        ls_ratio=ls_ratio,
    )

    return {
        "symbol": symbol,
        "price": price,
        "funding_rate": funding_rate,
        "risk_score": risk_score,
        "risk_level": ("DANGER" if risk_score >= 80 else "WARNING" if risk_score >= 50 else "SAFE"),
        "regime": market_regime,
        "updated_at": now_iso,
        "ai_score": ai_score,
        "ai_allowed": ai_allowed,
        "ai_reason": ai_reason,
        "ai_version": ai_version,
        "p3a_match_score": p3a_match_score,
        "ai_effective_threshold": ai_effective_threshold,
    }


# ---------------------------------------------------------------------------
# Storage-policy evaluation (Shadow Mode)
# ---------------------------------------------------------------------------

_STORE_TOP_COUNT_DEFAULT = 10


def should_store_to_ai_training(
    symbol: str,
    top_movers: list[tuple[str, float, str]],
    metrics: dict,
    store_top_count: int = _STORE_TOP_COUNT_DEFAULT,
) -> tuple[bool, str]:
    """
    Determine whether *symbol* should be written to ai_training_data and what
    training tag to attach.

    Returns (should_store: bool, training_tag: str).
    Tags: 'PERFECT' | 'POTENTIAL' | 'SHADOW' | 'NONE'

    Shadow Mode (wide in, strict out):
    - Store: top-N movers OR any loose signal (neg funding, price up 1%,
      wick > 40%, P2+ phase, kill zone, golden wick, exit clarity >= 40).
    - PERFECT: trade allowed + structure_gap > 2% + neg funding + P2/P3a.
    - POTENTIAL: P2/P3a/P3b + light neg funding.
    - SHADOW: everything else that satisfies at least one loose condition.
    """
    sym_binance = normalize_binance_symbol(symbol)
    top_symbols = [normalize_binance_symbol(m[0]) for m in top_movers[:store_top_count]]
    is_top_mover = sym_binance in top_symbols

    funding_rate = metrics.get("funding_rate")
    price_change_1h = metrics.get("price_change") or metrics.get("price_change_1h")
    price_change_24h = metrics.get("price_change_24h")
    kz = (metrics.get("kill_zone_signal") or "NONE").upper()
    phase = (metrics.get("market_phase") or "P1_NO_WHALE").upper()
    exit_score = metrics.get("exit_clarity_score")
    is_golden_wick = metrics.get("is_golden_wick", False)

    wick_ratio = 0.0
    try:
        ohlcv_15m = metrics.get("ohlcv_15m")
        if ohlcv_15m and len(ohlcv_15m) > 0:
            latest = ohlcv_15m[-1]
            high = float(latest.get("high", 0))
            low = float(latest.get("low", 0))
            open_price = float(latest.get("open", 0))
            close_price = float(latest.get("close", 0))
            if high > low > 0:
                upper_wick = high - max(open_price, close_price)
                lower_wick = min(open_price, close_price) - low
                candle_range = high - low
                wick_ratio = max(upper_wick, lower_wick) / candle_range if candle_range > 0 else 0.0
    except Exception:
        pass

    loose: list[str] = []
    if is_top_mover:
        loose.append("TOP_MOVER")
    if funding_rate is not None and funding_rate < -0.00001:
        loose.append("NEG_FUNDING")
    if price_change_1h is not None and price_change_1h > 1.0:
        loose.append("PRICE_UP_1H")
    if price_change_24h is not None and abs(price_change_24h) > 5.0:
        loose.append("PRICE_MOVE_24H")
    if wick_ratio > 0.4:
        loose.append("WICK_PATTERN")
    if phase not in ("P1_NO_WHALE", "UNKNOWN"):
        loose.append(f"PHASE_{phase}")
    if kz != "NONE":
        loose.append(f"KZ_{kz}")
    if is_golden_wick:
        loose.append("GOLDEN_WICK")
    if isinstance(exit_score, int) and exit_score >= 40:
        loose.append("EXIT_CLARITY")

    if not loose:
        return False, "NONE"

    is_trade_allowed = metrics.get("is_trade_allowed", False)
    structure_gap = metrics.get("structure_gap")

    if is_trade_allowed and structure_gap is not None and structure_gap > 0.02:
        if funding_rate is not None and funding_rate < -0.0002:
            if phase in ("P2_ACCUMULATION", "P3A_PUMP_START"):
                return True, "PERFECT"

    if phase in ("P2_ACCUMULATION", "P3A_PUMP_START", "P3B_PUMP_LATE"):
        if funding_rate is not None and funding_rate < -0.0001:
            return True, "POTENTIAL"

    return True, "SHADOW"


# ---------------------------------------------------------------------------
# Phase/KillZone inference helper
# ---------------------------------------------------------------------------

def _infer_phase_and_kz(metrics: dict) -> dict:
    """
    Run the whale-detector Phase / Kill-Zone / exit-clarity pipeline on
    *metrics* and return a patch dict with the results.

    This mirrors the inline logic originally in collector.py's main_loop.
    """
    patch: dict[str, Any] = {
        "market_phase": "UNKNOWN",
        "kill_zone_signal": "NONE",
        "exit_clarity_score": None,
    }

    try:
        from whale_detector import (  # type: ignore
            check_kill_zones,
            compute_exit_clarity_score,
            detect_phase,
            is_oi_second_spike_confirmed,
            PHASE_P2,
            PHASE_P3A,
        )

        price_change = metrics.get("price_change")
        oi_change = metrics.get("oi_change")
        oi_series = metrics.get("oi_series")
        cvd_data = metrics.get("cvd_data")
        funding_rate = float(metrics.get("funding_rate", 0.0))

        if price_change is None:
            return patch

        cvd_intent = "NEUTRAL"
        cvd_1h: float | None = None

        if cvd_data and _CVD_AVAILABLE:
            try:
                analyzer = _CVDAnalyzer(None)
                cvd_1h = float(cvd_data.get("cvd_1h", 0.0) or 0.0)
                cvd_intent = analyzer.analyze_cvd_intent(
                    float(price_change) / 100.0, cvd_data
                )
            except Exception:
                cvd_intent = "NEUTRAL"

        whale_cvd_1h = float((cvd_data or {}).get("whale_cvd_1h", 0.0) or 0.0)

        market_phase = detect_phase(
            price_change_1h=price_change,
            oi_change_1h=oi_change,
            cvd_intent=cvd_intent,
            cvd_1h=cvd_1h,
            whale_cvd_1h=whale_cvd_1h,
        )

        oi_second_spike_ok = is_oi_second_spike_confirmed(oi_series)
        if market_phase == PHASE_P3A and not oi_second_spike_ok:
            market_phase = PHASE_P2

        price_breakout = price_change is not None and float(price_change) > 2.0
        flash_crash = price_change is not None and float(price_change) < -2.0
        oi_stable = oi_change is None or float(oi_change) > -1.0

        kill_zone_signal = check_kill_zones(
            funding_rate=funding_rate,
            oi_change_1h=oi_change,
            price_breakout=price_breakout,
            cvd_intent=cvd_intent,
            phase=market_phase,
            flash_crash=flash_crash,
            oi_stable=oi_stable,
        ) or "NONE"

        exit_clarity_score = compute_exit_clarity_score(
            phase=market_phase,
            kill_zone=kill_zone_signal,
            funding_rate=funding_rate,
            oi_change_1h=oi_change,
            price_change_1h=price_change,
            cvd_intent=cvd_intent,
            oi_second_spike_confirmed=oi_second_spike_ok,
        )

        patch = {
            "market_phase": market_phase or "UNKNOWN",
            "kill_zone_signal": kill_zone_signal,
            "exit_clarity_score": exit_clarity_score,
            "_cvd_intent": cvd_intent,
            "_cvd_1h": cvd_1h,
            "_oi_second_spike_ok": oi_second_spike_ok,
        }
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] Phase/KZ 推断失败: {e}")

    return patch


# ---------------------------------------------------------------------------
# AI Training row builder
# ---------------------------------------------------------------------------

def _build_ai_training_row(
    ccxt_symbol: str,
    now_iso: str,
    metrics: dict,
    supabase: "Client | None" = None,
    exchange: Any = None,
) -> dict:
    """
    Build the dict to be inserted into ai_training_data.

    This is the full V4.x row including V4.1 ATR/structure/phase-age fields,
    V4.2 Golden Wick detection, and V4.0 phase/kill-zone/exit-clarity fields.
    """
    from .deep_collector import (
        fetch_klines_full,
        fetch_klines_ohlcv,
    )

    price = float(metrics["price"])
    funding_rate = float(metrics["funding_rate"])
    oi_value = metrics.get("oi_value")
    ls_ratio = metrics.get("ls_ratio")
    price_change = metrics.get("price_change")
    oi_change = metrics.get("oi_change")
    cvd_data = metrics.get("cvd_data")
    oi_series = metrics.get("oi_series")

    is_oi_divergence = False
    if price_change is not None and oi_change is not None:
        if (price_change > 0 and oi_change < -5) or (price_change < 0 and oi_change < -5):
            is_oi_divergence = True

    # --- Phase / Kill Zone ---
    phase_kz = _infer_phase_and_kz(metrics)
    market_phase: str = phase_kz.get("market_phase") or "UNKNOWN"
    kill_zone_signal: str = phase_kz.get("kill_zone_signal") or "NONE"
    exit_clarity_score = phase_kz.get("exit_clarity_score")
    cvd_intent: str = phase_kz.get("_cvd_intent", "NEUTRAL")
    cvd_1h: float | None = phase_kz.get("_cvd_1h")
    oi_second_spike_ok: bool = phase_kz.get("_oi_second_spike_ok", False)

    # CVD values
    cvd_value: float | None = None
    cvd_15m: float | None = None
    if cvd_data:
        cvd_15m = float(cvd_data.get("cvd_15m", cvd_data.get("cvd_volume", 0.0)) or 0.0)
        cvd_value = cvd_15m

    # V4 trade allowed
    v4_trade_allowed = False
    if market_phase == "P3A_PUMP_START" and (exit_clarity_score or 0) >= 70:
        v4_trade_allowed = True
    elif market_phase == "P2_ACCUMULATION" and kill_zone_signal == "ACCUMULATION" and (exit_clarity_score or 0) >= 55:
        v4_trade_allowed = True

    # Anti-confidence engine
    confidence_level: int | None = None
    final_trade_allowed = v4_trade_allowed

    # Market regime for snapshot/display
    market_regime = "UNKNOWN"
    risk_reasons: list[str] = []
    risk_score = 0
    try:
        market_regime, risk_reasons, risk_score = compute_v4_snapshot(
            market_phase=market_phase,
            kill_zone_signal=kill_zone_signal,
            exit_clarity_score=exit_clarity_score,
            funding_rate=funding_rate,
            confidence_level=confidence_level,
            ls_ratio=ls_ratio,
        )
    except Exception:
        pass

    # --- V4.1: ATR, structure gap, phase age ---
    binance_sym = symbol_to_binance_symbol(ccxt_symbol)

    atr_value: float | None = None
    atr_multiplier: float | None = None
    structure_gap: float | None = None
    structure_gap_method: str | None = None
    phase_age_candles: int | None = None
    phase_age_percent: float | None = None
    v41_block_reason: str | None = None
    chandelier_stop_price: float | None = None
    position_size_coin: float | None = None
    phase_4h: str | None = None
    phase_1h: str | None = None

    try:
        highs_15m, lows_15m, closes_15m = fetch_klines_full(binance_sym, interval="15m", limit=100)
        if len(highs_15m) >= 15:
            try:
                from v41_risk_manager import calculate_atr, get_atr_multiplier, calculate_chandelier_stop, calculate_position_size  # type: ignore
                atr_value = calculate_atr(highs_15m, lows_15m, closes_15m, length=14)
                if atr_value and atr_value > 0 and market_phase and market_phase != "UNKNOWN":
                    atr_multiplier = get_atr_multiplier(market_phase, phase_age_percent)
                    if atr_multiplier:
                        chandelier_stop_price = calculate_chandelier_stop(
                            entry_price=price,
                            atr_value=atr_value,
                            atr_multiplier=atr_multiplier,
                            highest_high_since_entry=None,
                            is_long=True,
                        )
                        position_size_coin = calculate_position_size(
                            account_balance=10000.0,
                            entry_price=price,
                            stop_loss_price=chandelier_stop_price,
                            risk_per_trade=0.015,
                        )
            except ImportError:
                pass
            except Exception as e:  # noqa: BLE001
                print(f"[WARNING] {ccxt_symbol} V4.1 ATR 计算失败: {e}")

        highs_1h, lows_1h, closes_1h = fetch_klines_full(binance_sym, interval="1h", limit=100)
        if len(highs_1h) >= 20:
            try:
                from v41_structure_analyzer import calculate_structure_gap  # type: ignore
                from v41_context_gate import get_phase_for_timeframe  # type: ignore
                structure_gap, structure_gap_method = calculate_structure_gap(
                    current_price=price,
                    highs_1h=highs_1h,
                    closes_1h=closes_1h,
                    use_bollinger=True,
                )
                if price_change is not None and oi_change is not None:
                    phase_1h = get_phase_for_timeframe(
                        price_change_1h=price_change,
                        oi_change_1h=oi_change,
                        cvd_intent=cvd_intent,
                        cvd_1h=cvd_1h,
                        whale_cvd_1h=float((cvd_data or {}).get("whale_cvd_1h", 0.0) or 0.0),
                    )
            except ImportError:
                pass
            except Exception as e:  # noqa: BLE001
                print(f"[WARNING] {ccxt_symbol} V4.1 结构空间计算失败: {e}")

        # 4H context (approximated)
        try:
            from v41_context_gate import get_phase_for_timeframe  # type: ignore
            if price_change is not None and oi_change is not None:
                phase_4h = get_phase_for_timeframe(
                    price_change_1h=price_change * 0.5,
                    oi_change_1h=oi_change * 0.5,
                    cvd_intent=cvd_intent,
                    cvd_1h=cvd_1h,
                    whale_cvd_1h=float((cvd_data or {}).get("whale_cvd_1h", 0.0) or 0.0),
                )
        except ImportError:
            pass
        except Exception as e:  # noqa: BLE001
            print(f"[WARNING] {ccxt_symbol} V4.1 4H 阶段计算失败: {e}")

    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] {ccxt_symbol} V4.1 计算失败: {e}")

    # --- V4.2: Golden Wick detection ---
    is_golden_wick = False
    golden_wick_details: dict | None = None
    try:
        ohlcv_15m = fetch_klines_ohlcv(binance_sym, interval="15m", limit=20)
        if len(ohlcv_15m) >= 10:
            try:
                from golden_wick_detector import detect_golden_wick  # type: ignore
                lookback = min(20, len(ohlcv_15m))
                is_golden_wick, golden_wick_details = detect_golden_wick(
                    ohlcv_15m=ohlcv_15m,
                    min_wick_ratio=0.6,
                    lookback_period=lookback,
                    sweep_window=2,
                )
                if is_golden_wick:
                    print(f"[INFO] {ccxt_symbol} 检测到定海神针: {(golden_wick_details or {}).get('reason', '')}")
            except ImportError:
                pass
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] {ccxt_symbol} Golden Wick 检测失败: {e}")

    # Safe phase enum mapping (DB only accepts specific values)
    valid_phase_values = {
        "P1_NO_WHALE", "P2_ACCUMULATION", "P3A_PUMP_START",
        "P3B_PUMP_LATE", "P4_DISTRIBUTION",
    }
    db_market_phase = market_phase if market_phase in valid_phase_values else None

    return {
        "created_at": now_iso,
        "symbol": ccxt_symbol,
        "price": price,
        "funding_rate": funding_rate,
        "long_short_ratio": ls_ratio,
        "oi_value": float(oi_value) if oi_value is not None else None,
        "oi_change_1h": oi_change,
        "price_change_1h": price_change,
        "is_oi_divergence": is_oi_divergence if price_change is not None and oi_change is not None else None,
        "market_regime": market_regime,
        "risk_reasons": risk_reasons or None,
        "is_trade_allowed": final_trade_allowed,
        "technical_signal": None,
        "cvd_15m": cvd_15m,
        "cvd_1h": cvd_1h,
        "cvd_value": cvd_value,
        "market_phase": db_market_phase,
        "kill_zone_signal": kill_zone_signal,
        "exit_clarity_score": exit_clarity_score,
        "confidence_level": confidence_level,
        "price_breakout": price_change is not None and price_change > 2.0,
        "time_stop_loss_triggered": None,
        "profit_1h": None,
        # V4.1
        "atr_value": atr_value,
        "atr_multiplier": atr_multiplier,
        "structure_gap": structure_gap,
        "structure_gap_method": structure_gap_method,
        "phase_age_candles": phase_age_candles,
        "phase_age_percent": phase_age_percent,
        "v41_block_reason": v41_block_reason,
        "chandelier_stop_price": chandelier_stop_price,
        "position_size_coin": position_size_coin,
        "phase_4h": phase_4h,
        "phase_1h": phase_1h,
        # V4.2
        "is_golden_wick": is_golden_wick,
    }


# ---------------------------------------------------------------------------
# Class
# ---------------------------------------------------------------------------

class StrategyScorer:
    """
    Async task: scores enriched market data and routes write tasks to
    DatabaseWriter.

    Input:  enriched_queue  – asyncio.Queue[dict] from DeepCollector.
    Output: write_queue     – asyncio.Queue[dict] consumed by DatabaseWriter.

    Constructor args:
        enriched_queue      – source of enriched metric items.
        write_queue         – sink for database write tasks.
        supabase            – Supabase client (for AI judge history queries).
        exchange            – optional ccxt exchange instance.
        v43_enabled         – whether to run V4.3 scoring pipeline.
        v44_enabled         – whether to run V4.4 strategy routing.
        store_top_count     – shadow-mode storage threshold.
        ai_judge_threshold  – minimum AI score to allow a trade.
        deepseek_cache_secs – seconds to cache DeepSeek responses per symbol.
        v43_position_manager – optional V43PositionManager for auto-trading.
    """

    def __init__(
        self,
        enriched_queue: asyncio.Queue,
        write_queue: asyncio.Queue,
        *,
        supabase: "Client | None" = None,
        exchange: Any = None,
        v43_enabled: bool = True,
        v44_enabled: bool = False,
        store_top_count: int = _STORE_TOP_COUNT_DEFAULT,
        ai_judge_threshold: float = 0.65,
        deepseek_cache_secs: int = 60,
        v43_position_manager: Any = None,
        openai_assistant: Any = None,
    ) -> None:
        self.enriched_queue = enriched_queue
        self.write_queue = write_queue
        self.supabase = supabase
        self.exchange = exchange
        self.v43_enabled = v43_enabled and _V43_AVAILABLE
        self.v44_enabled = v44_enabled
        self.store_top_count = store_top_count
        self.ai_judge_threshold = ai_judge_threshold
        self.deepseek_cache_secs = deepseek_cache_secs
        self.v43_position_manager = v43_position_manager
        self.openai_assistant = openai_assistant  # TradingAssistant instance (optional)

        # Deepseek response cache: {ccxt_symbol: (ts, patch_dict)}
        self._deepseek_cache: dict[str, tuple[float, dict]] = {}

        # Optional AI judges – lazy-loaded in _init_ai_judges()
        self._ai_judge: Any = None
        self._deepseek_judge: Any = None
        self._p3a_matcher: Any = None
        # v0.5.5: balance 默认 fallback 改成 PAPER_INITIAL_BALANCE_USDT（用户可配）
        # 真账户余额会在 _refresh_account_balance() 启动 + 周期刷新时覆盖
        _default_bal = float(os.environ.get("PAPER_INITIAL_BALANCE_USDT", "1000"))
        self._account_balance_cache: dict[str, Any] = {
            "balance": _default_bal,
            "source":  "default",
            "last_update": 0.0,
            "update_interval": 30.0,
        }
        # v0.5.5: mode 决议加 cache（避免每个 symbol 都查一次 DB）+ 上报 last_active_mode
        self._mode_cache: dict[str, Any] = {"mode": "SHADOW", "last_check": 0.0, "ttl": 5.0}

    # v0.5.5：SHADOW/LIVE 决议 + 真账户余额刷新（统一在这里，让 audit 列出的 silent
    # default 风险变成可见的）—— 调用方有 scorer 路由开仓判断（line ~986）和 AI 跳过判断（~944）

    def _resolve_system_mode(self) -> str:
        """读 system_settings.system_state，返回 'SHADOW' or 'LIVE'。
        失败时降级 SHADOW + WARN + 写 last_active_mode 让 UI 能看到真相。"""
        import time
        now = time.monotonic()
        if (now - self._mode_cache["last_check"]) < self._mode_cache["ttl"]:
            return self._mode_cache["mode"]

        mode = "SHADOW"
        source = "default_no_row"
        try:
            sr = (
                self.supabase.table("system_settings")
                .select("value").eq("key", "system_state").execute()
            )
            if sr.data:
                v = (sr.data[0].get("value") or "").strip().upper()
                if v in ("SHADOW", "LIVE"):
                    mode = v
                    source = "db"
                else:
                    source = f"db_unparseable:{v[:20]}"
        except Exception as e:
            source = f"error:{type(e).__name__}:{str(e)[:60]}"
            print(f"[WARN][scorer] _resolve_system_mode 失败 — 安全降级 SHADOW: {source}")

        self._mode_cache.update({"mode": mode, "last_check": now})
        self._report_effective_mode(mode, source)
        return mode

    def _report_effective_mode(self, mode: str, source: str):
        """写 scorer 当前生效的 mode 到 system_settings.last_active_mode，
        UI 可读出来跟 desired mode 对比 — round-trip 校验。"""
        try:
            value = f"{mode}|{source}|{datetime.now(timezone.utc).isoformat()}"
            self.supabase.table("system_settings").upsert(
                {"key": "last_active_mode", "value": value},
                on_conflict="key",
            ).execute()
        except Exception:
            pass  # best-effort，不要因为日志写失败而影响主流程

    def _refresh_account_balance(self):
        """v0.5.5: 从真账户拉 balance，给 paper 仓位规模算用。OKX 鉴权失败时
        fallback 到 PAPER_INITIAL_BALANCE_USDT env。每 update_interval 秒最多调一次。"""
        import time
        now = time.monotonic()
        if (now - self._account_balance_cache["last_update"]) < self._account_balance_cache["update_interval"]:
            return

        bal = None
        source = "default"
        try:
            try:
                from exchange_factory import get_trader  # type: ignore[import-not-found]
            except ImportError:
                from scripts.exchange_factory import get_trader  # type: ignore[import-not-found]
            trader = get_trader()
            if trader and hasattr(trader, "fetch_balance"):
                resp = trader.fetch_balance()
                # _safe API 既可能 raise，也可能返 dict 带 "error"
                if isinstance(resp, dict) and not resp.get("error"):
                    b = resp.get("balance") or resp.get("availableBalance")
                    if b is not None and float(b) > 0:
                        bal = float(b)
                        source = "trader"
        except Exception as e:
            print(f"[WARN][scorer] fetch_balance 失败，用 PAPER_INITIAL_BALANCE_USDT 兜底: {e}")

        if bal is None:
            bal = float(os.environ.get("PAPER_INITIAL_BALANCE_USDT", "1000"))
            source = "env_fallback"

        self._account_balance_cache.update({
            "balance":     bal,
            "source":      source,
            "last_update": now,
        })

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_ai_judges(self) -> None:
        """Lazy-initialise AI judges.  Called once at the start of run()."""
        # v45: 默认关闭本地 LR AIJudge — 未训练的模型会污染 ai_score
        # 显式 AI_JUDGE_ENABLED=true 才启用（scripts/ai_judge.py 头有完整说明）
        ai_judge_enabled = os.environ.get("AI_JUDGE_ENABLED", "0") not in ("0", "false", "False")
        deepseek_enabled = os.environ.get("DEEPSEEK_ENABLED", "0") in ("1", "true", "True")

        if ai_judge_enabled:
            try:
                from ai_judge import AIJudge  # type: ignore
                self._ai_judge = AIJudge(allowed_threshold=self.ai_judge_threshold)
            except Exception:
                self._ai_judge = None

        if deepseek_enabled:
            try:
                from deepseek_ai import DeepSeekJudge  # type: ignore
                j = DeepSeekJudge(
                    model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
                    enable_learning=True,
                    supabase=self.supabase,
                )
                self._deepseek_judge = j if j.is_ready() else None
                if self._deepseek_judge and getattr(j, "learner", None):
                    print("[INFO] DeepSeek AI 学习功能已启用（V4.2）")
            except Exception:
                self._deepseek_judge = None

        p3a_enabled = os.environ.get("P3A_MATCH_ENABLED", "1") in ("1", "true", "True")
        if p3a_enabled and self.supabase is not None:
            try:
                from p3a_pattern_matcher import P3APatternMatcher, PatternConfig  # type: ignore
                days = int(os.environ.get("P3A_MATCH_DAYS", "14"))
                min_samples = int(os.environ.get("P3A_MATCH_MIN_SAMPLES", "50"))
                matcher = P3APatternMatcher(
                    self.supabase,
                    PatternConfig(days=days, min_success_samples=min_samples),
                )
                prof = matcher.fit()
                if prof is not None and matcher.is_ready():
                    print(f"[INFO] P3a 模式匹配已启用：samples={prof.n} days={days}")
                    self._p3a_matcher = matcher
                else:
                    print("[WARNING] P3a 模式匹配样本不足：将返回默认 0.5 分")
                    self._p3a_matcher = matcher
            except Exception as e:  # noqa: BLE001
                print(f"[WARNING] P3a 模式匹配初始化失败：{e}")

    # ------------------------------------------------------------------
    # AI judge helpers
    # ------------------------------------------------------------------

    def _run_ai_judges(self, ccxt_symbol: str, ai_row: dict) -> dict:
        """Apply DeepSeek / local LR judge and dynamic threshold to ai_row."""
        ai_judge_threshold = self.ai_judge_threshold
        ai_dynamic_enabled = os.environ.get("AI_DYNAMIC_THRESHOLD_ENABLED", "1") in ("1", "true", "True")
        max_boost = float(os.environ.get("AI_DYNAMIC_THRESHOLD_MAX_BOOST", "0.20"))

        p3a_match_score = 0.5
        if self._p3a_matcher is not None:
            try:
                p3a_match_score = float(self._p3a_matcher.score(ai_row))
            except Exception:
                pass

        dynamic_thr = float(ai_judge_threshold)
        if ai_dynamic_enabled:
            try:
                cl = ai_row.get("confidence_level")
                clv = float(cl) if cl is not None else 0.0
                boost = (clv / 100.0) * max_boost
                dynamic_thr = min(0.95, max(0.05, dynamic_thr + boost))
            except Exception:
                pass

        # DeepSeek (with cache)
        if self._deepseek_judge is not None:
            try:
                now_ts = time.time()
                cached = self._deepseek_cache.get(ccxt_symbol)
                if cached and (now_ts - cached[0]) < self.deepseek_cache_secs:
                    ai_row.update(cached[1])
                else:
                    features = dict(ai_row)
                    features["p3a_match_score"] = p3a_match_score
                    features["dynamic_threshold"] = dynamic_thr
                    d = self._deepseek_judge.judge(features)
                    if d is not None:
                        patch = {
                            "ai_score": d.ai_score,
                            "ai_allowed": d.ai_allowed,
                            "ai_reason": d.ai_reason,
                            "ai_version": d.ai_version,
                        }
                        ai_row.update(patch)
                        self._deepseek_cache[ccxt_symbol] = (now_ts, patch)
            except Exception:
                pass

        # Local LR fallback
        if self._ai_judge is not None and ai_row.get("ai_score") is None:
            try:
                features = dict(ai_row)
                features["p3a_match_score"] = p3a_match_score
                features["dynamic_threshold"] = dynamic_thr
                res = self._ai_judge.predict(features)
                if res is not None:
                    ai_row["ai_score"] = res.ai_score
                    ai_row["ai_allowed"] = res.ai_allowed
                    ai_row["ai_reason"] = res.ai_reason
                    ai_row["ai_version"] = res.ai_version
            except Exception:
                pass

        # Dynamic threshold post-processing
        eff_thr = dynamic_thr
        try:
            if ai_row.get("ai_score") is not None:
                s = float(ai_row.get("ai_score"))
                base_allowed = bool(ai_row.get("ai_allowed"))
                if p3a_match_score >= 0.75:
                    eff_thr = max(0.05, dynamic_thr - 0.05)
                ai_row["ai_allowed"] = bool(base_allowed and (s >= eff_thr))
                r0 = str(ai_row.get("ai_reason") or "")
                ai_row["ai_reason"] = (
                    f"{r0} | dyn_thr={dynamic_thr:.2f}"
                    f" p3a_match={p3a_match_score:.2f}"
                    f" eff_thr={eff_thr:.2f}"
                )
        except Exception:
            pass

        ai_row["p3a_match_score"] = float(p3a_match_score) if p3a_match_score else None
        ai_row["ai_effective_threshold"] = float(eff_thr)

        # Log AI result
        if ai_row.get("ai_version") and ai_row.get("ai_score") is not None:
            try:
                print(
                    f"[DEEPSEEK] {ccxt_symbol:12s} | "
                    f"score={float(ai_row.get('ai_score', 0)):.2f} | "
                    f"allowed={ai_row.get('ai_allowed')} | "
                    f"phase={ai_row.get('market_phase', 'UNKNOWN')} | "
                    f"reason={(ai_row.get('ai_reason') or '')[:60]}"
                )
            except Exception:
                pass

        return ai_row

    # ------------------------------------------------------------------
    # V4.3 processing
    # ------------------------------------------------------------------

    async def _process_v43(
        self,
        ccxt_symbol: str,
        price: float,
        metrics: dict,
        ai_row: dict,
    ) -> None:
        """Run V4.3 feature extraction + scoring + V4.4 routing and enqueue result."""
        if not self.v43_enabled:
            return
        try:
            from v43_collector_integration import (  # type: ignore
                process_v43_trading_decision,
                build_v43_trade_score_row,
            )

            v43_metrics = {
                "funding_rate": ai_row.get("funding_rate") or metrics.get("funding_rate"),
                "ls_ratio": ai_row.get("long_short_ratio") or metrics.get("ls_ratio"),
                "oi_value": ai_row.get("oi_value") or metrics.get("oi_value"),
                "oi_change": ai_row.get("oi_change_1h") or metrics.get("oi_change"),
                "price_change": ai_row.get("price_change_1h") or metrics.get("price_change"),
                "cvd_data": metrics.get("cvd_data"),
                "oi_series": metrics.get("oi_series"),
                "phase_4h": ai_row.get("phase_4h") or metrics.get("phase_4h"),
                "phase_1h": ai_row.get("phase_1h") or metrics.get("phase_1h"),
                "phase_age_candles": ai_row.get("phase_age_candles"),
                "atr_value": ai_row.get("atr_value"),
                "highs_1h": metrics.get("highs_1h"),
                "closes_1h": metrics.get("closes_1h"),
                "ohlcv_15m": metrics.get("ohlcv_15m"),
                "prices": metrics.get("prices"),
            }

            v43_weights = load_weights()
            v43_features, v43_score_result, v43_decision_result = process_v43_trading_decision(
                symbol=ccxt_symbol,
                price=price,
                metrics=v43_metrics,
                weights=v43_weights,
                supabase_client=self.supabase,
            )

            v43_score_row = build_v43_trade_score_row(
                symbol=ccxt_symbol,
                features=v43_features,
                score_result=v43_score_result,
                decision_result=v43_decision_result,
                weights=v43_weights,
            )

            safe_enqueue(
                self.write_queue,
                {"op": "insert", "table": "trade_scores_v43", "row": v43_score_row},
                symbol=ccxt_symbol,
                table="trade_scores_v43",
            )

            final_score = v43_score_result.get("final_score", 0.0)
            should_trade = v43_decision_result.get("should_trade", False)
            block_reason = v43_decision_result.get("block_reason", "")
            strategy_id = v43_decision_result.get("strategy_id")
            side = v43_decision_result.get("side", "LONG")
            strategy_score = v43_decision_result.get("strategy_score")

            structure_score = v43_score_result.get("structure_score", 0.0)
            volatility_score = v43_score_result.get("volatility_score", 0.0)
            sentiment_score = v43_score_result.get("sentiment_score", 0.0)
            manipulation_score = v43_score_result.get("manipulation_score", 0.0)
            phase = v43_features.get("phase", "N/A")

            version_tag = "[V4.4]" if (self.v44_enabled and strategy_id) else "[V4.3]"

            if self.v44_enabled and strategy_id and strategy_id != "WAIT":
                display_score = (
                    float(strategy_score)
                    if isinstance(strategy_score, (int, float))
                    else float(final_score) * 100.0
                )
                print(
                    f"[V4.4] {ccxt_symbol:15s} | "
                    f"Strategy: {strategy_id:8s} | "
                    f"Score: {display_score:5.1f} | "
                    f"Side: {side:5s} | "
                    f"{v43_decision_result.get('reason', '')[:60]}"
                )

            if should_trade:
                print(
                    f"{version_tag} {ccxt_symbol:12s} | "
                    f"score={final_score*100:5.1f} | "
                    f"decision=TRADE | "
                    f"结构={structure_score*100:4.1f} 波动={volatility_score*100:4.1f} "
                    f"情绪={sentiment_score*100:4.1f} 操控={manipulation_score*100:4.1f} | "
                    f"phase={phase} | "
                    f"reason={v43_decision_result.get('reason', '')[:50]}"
                )

                # ── OpenAI AI Layer (second opinion + TP/SL tuning) ──────────
                # v0.5.5: SHADOW 模式默认跳过 AI — paper KPI 反映规则引擎本身效果，
                # 不被 AI 决策污染。要在 SHADOW 也用 AI 测试时设 AI_SKIP_IN_SHADOW=false。
                _ai_skip_in_shadow = os.environ.get("AI_SKIP_IN_SHADOW", "true").lower() in ("1", "true")
                _ai_gated_by_shadow = _ai_skip_in_shadow and self._resolve_system_mode() == "SHADOW"
                if self.openai_assistant and not _ai_gated_by_shadow:
                    try:
                        ai_result = await self.openai_assistant.decide(
                            symbol=ccxt_symbol,
                            side=side,
                            price=price,
                            features=v43_features,
                            score_result=v43_score_result,
                            decision_result=v43_decision_result,
                        )
                        if not ai_result.execute:
                            print(f"[AI] {ccxt_symbol} 被 AI 过滤: {ai_result.reasoning}")
                            should_trade = False
                        else:
                            # Inject AI parameters into decision_result
                            v43_decision_result["stop_loss_atr_multiplier"] = ai_result.sl_multiplier
                            v43_decision_result["take_profit_atr_multiplier"] = ai_result.tp_multiplier
                            # AI size_multiplier stacks with existing position_size_multiplier
                            existing_size = float(v43_decision_result.get("position_size_multiplier", 1.0))
                            v43_decision_result["position_size_multiplier"] = existing_size * ai_result.size_multiplier
                            v43_decision_result["ai_confidence"] = ai_result.confidence
                            v43_decision_result["ai_reasoning"] = ai_result.reasoning
                    except Exception as ai_err:
                        # decide() 现在内部捕获自己的异常并返回 execute=False，
                        # 所以这里只会兜住罕见的 import/类型错误。仍然遵守 AI_FAIL_OPEN。
                        ai_fail_open = os.environ.get("AI_FAIL_OPEN", "false").lower() in ("1", "true")
                        if ai_fail_open:
                            print(
                                f"[AI] {ccxt_symbol} AI 决策异常 (AI_FAIL_OPEN=true)，继续规则引擎: {ai_err}"
                            )
                        else:
                            print(
                                f"[AI] {ccxt_symbol} AI 决策异常 (AI_FAIL_OPEN=false)，跳过: {ai_err}"
                            )
                            should_trade = False
                # ─────────────────────────────────────────────────────────────

                # v0.5.4: SHADOW 时走 PaperPositionManager（写虚拟仓位到 paper_trades）
                # LIVE 时走 V43PositionManager（真下单）
                if should_trade:
                    # v0.5.5: 走 _resolve_system_mode 统一决议（带 cache、WARN log、上报 last_active_mode）
                    is_shadow = self._resolve_system_mode() == "SHADOW"

                    try:
                        atr_val = float(v43_features.get("atr") or v43_features.get("atr_1h") or 0.0)
                        # v0.5.5: balance 从真账户拉（OKX/Binance），失败回退 PAPER_INITIAL_BALANCE_USDT
                        self._refresh_account_balance()
                        account_balance = self._account_balance_cache.get("balance", 1000.0)

                        if is_shadow:
                            # SHADOW — 写虚拟仓位
                            try:
                                from paper_position_manager import PaperPositionManager  # type: ignore[import-not-found]
                            except ImportError:
                                from scripts.paper_position_manager import PaperPositionManager  # type: ignore[import-not-found]
                            paper_pm = PaperPositionManager(supabase_client=self.supabase)
                            position = paper_pm.open_position(
                                symbol=ccxt_symbol, side=side, entry_price=price,
                                features=v43_features, decision_result=v43_decision_result,
                                account_balance=account_balance, atr_value=atr_val,
                                write_queue=self.write_queue,
                                signal_score=float(final_score) if final_score is not None else None,
                            )
                            if position:
                                print(f"[V4.3 SHADOW] 已开虚拟仓: {ccxt_symbol} {side} @ {price}（不下真单）")
                        elif self.v43_position_manager:
                            # LIVE — 真下单
                            position = self.v43_position_manager.open_position(
                                symbol=ccxt_symbol, side=side, entry_price=price,
                                features=v43_features, decision_result=v43_decision_result,
                                account_balance=account_balance, atr_value=atr_val,
                                write_queue=self.write_queue,
                            )
                            if position:
                                print(f"[V4.3 LIVE] 自动开仓成功: {ccxt_symbol} {side} @ {price}")
                            else:
                                print(f"[WARNING] LIVE 开仓失败: {ccxt_symbol}（可能已有持仓或计算失败）")
                        else:
                            print(f"[WARNING] LIVE 模式但 v43_position_manager 未注入，跳过: {ccxt_symbol}")
                    except Exception as trade_err:
                        print(f"[ERROR] 开仓异常: {ccxt_symbol} - {trade_err}")
            else:
                if os.environ.get("V43_DEBUG", "0") in ("1", "true", "True") or final_score > 0.0:
                    decision_status = "BLOCKED" if block_reason else "SKIP"
                    print(
                        f"{version_tag} {ccxt_symbol:12s} | "
                        f"score={final_score*100:5.1f} | "
                        f"decision={decision_status} | "
                        f"结构={structure_score*100:4.1f} 波动={volatility_score*100:4.1f} "
                        f"情绪={sentiment_score*100:4.1f} 操控={manipulation_score*100:4.1f} | "
                        f"phase={phase}"
                        + (f" | block={block_reason[:30]}" if block_reason else "")
                    )

        except ImportError as e:
            print(f"[WARNING] V4.3 模块导入失败: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"[WARNING] V4.3 处理失败 ({type(e).__name__}): {str(e)[:200]}")
            if os.environ.get("V43_DEBUG", "0") in ("1", "true", "True"):
                traceback.print_exc()

    # ------------------------------------------------------------------
    # Per-symbol processing
    # ------------------------------------------------------------------

    async def _process_symbol(self, item: dict) -> None:
        """Score one enriched item and enqueue the resulting writes."""
        symbol = item["symbol"]
        ccxt_symbol = item.get("ccxt_symbol") or symbol
        price = float(item["price"])
        funding_rate = float(item["funding_rate"])
        movers: list[tuple[str, float, str]] = item.get("_movers", [])

        # Build metrics dict for downstream logic
        metrics = {
            "price": price,
            "funding_rate": funding_rate,
            "oi_value": item.get("oi_value"),
            "ls_ratio": item.get("ls_ratio"),
            "price_change": item.get("price_change"),
            "oi_change": item.get("oi_change"),
            "cvd_data": item.get("cvd_data"),
            "oi_series": item.get("oi_series"),
        }

        # Infer phase/kz early so should_store can use them
        phase_kz = _infer_phase_and_kz(metrics)
        metrics.update(phase_kz)

        ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        extra = f"  OI={float(metrics['oi_value']):.1f}" if metrics.get("oi_value") else ""
        extra += f"  ls={float(metrics['ls_ratio']):.2f}" if metrics.get("ls_ratio") else ""
        print(f"[{ts_str}] {ccxt_symbol:12s} price={price:.4f} funding={funding_rate:.6f}{extra}")

        if self.supabase is None:
            return

        now_iso = datetime.now(timezone.utc).isoformat()

        should_store, training_tag = should_store_to_ai_training(
            symbol, movers, metrics, self.store_top_count
        )

        ai_row: dict | None = None
        if should_store:
            ai_row = await asyncio.to_thread(
                lambda: _build_ai_training_row(
                    ccxt_symbol, now_iso, metrics, self.supabase, self.exchange
                )
            )

            # AI judge enrichment
            ai_row = self._run_ai_judges(ccxt_symbol, ai_row)

            safe_enqueue(
                self.write_queue,
                {"op": "insert", "table": "ai_training_data", "row": ai_row},
                symbol=ccxt_symbol,
                table="ai_training_data",
            )
            print(f"[INFO] 已存储 {ccxt_symbol} 到 ai_training_data（tag={training_tag}）")

            # V4.3 / V4.4 scoring
            await self._process_v43(ccxt_symbol, price, metrics, ai_row)

        # Market snapshot (always updated for movers)
        snapshot_metrics = {
            "price": price,
            "funding_rate": funding_rate,
            "ls_ratio": metrics.get("ls_ratio"),
            "price_change": metrics.get("price_change"),
            "oi_change": metrics.get("oi_change"),
            "market_phase": (ai_row.get("market_phase") if ai_row else None) or metrics.get("market_phase") or "UNKNOWN",
            "kill_zone_signal": (ai_row.get("kill_zone_signal") if ai_row else None) or metrics.get("kill_zone_signal") or "NONE",
            "exit_clarity_score": ai_row.get("exit_clarity_score") if ai_row else metrics.get("exit_clarity_score"),
            "confidence_level": ai_row.get("confidence_level") if ai_row else metrics.get("confidence_level"),
            "ai_score": ai_row.get("ai_score") if ai_row else None,
            "ai_allowed": ai_row.get("ai_allowed") if ai_row else None,
            "ai_reason": ai_row.get("ai_reason") if ai_row else None,
            "ai_version": ai_row.get("ai_version") if ai_row else None,
            "p3a_match_score": ai_row.get("p3a_match_score") if ai_row else None,
            "ai_effective_threshold": ai_row.get("ai_effective_threshold") if ai_row else None,
        }
        snapshot_row = _build_snapshot_row(ccxt_symbol, now_iso, snapshot_metrics)
        safe_enqueue(
            self.write_queue,
            {
                "op": "upsert",
                "table": "market_snapshot",
                "row": snapshot_row,
                "on_conflict": "symbol",
            },
            symbol=ccxt_symbol,
            table="market_snapshot",
        )

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Main coroutine.  Consumes enriched_queue, scores each item, and
        enqueues write tasks.  Designed to run as an asyncio task.
        """
        # v0.5.5: 启动 banner — 让运营看清 active exchange + 当前 system_state
        try:
            try:
                from exchange_factory import get_active_exchange  # type: ignore[import-not-found]
            except ImportError:
                from scripts.exchange_factory import get_active_exchange  # type: ignore[import-not-found]
            active_ex = get_active_exchange()
        except Exception:
            active_ex = os.environ.get("EXCHANGE", "okx")
        startup_mode = self._resolve_system_mode()  # 同时也写一次 last_active_mode
        ai_skip = os.environ.get("AI_SKIP_IN_SHADOW", "true").lower() in ("1", "true")
        print(
            f"[StrategyScorer] 启动 | exchange={active_ex.upper()} | mode={startup_mode} | "
            f"AI_SKIP_IN_SHADOW={ai_skip} | "
            f"PAPER_INITIAL_BALANCE_USDT={os.environ.get('PAPER_INITIAL_BALANCE_USDT', '1000')}"
        )
        self._init_ai_judges()

        # v0.5.5: 每 30s 周期性写一次 last_active_mode，让 UI 能持续看到 scorer 仍活着
        # cache 5s 去重，开销可控
        _last_mode_heartbeat = 0.0

        while True:
            try:
                # 心跳：每 30s 把当前 effective mode 重写一次 last_active_mode
                import time as _time
                _now = _time.monotonic()
                if _now - _last_mode_heartbeat > 30:
                    self._resolve_system_mode()  # 写 last_active_mode
                    _last_mode_heartbeat = _now

                item = await self.enriched_queue.get()
                try:
                    await self._process_symbol(item)
                except Exception as e:  # noqa: BLE001
                    symbol = item.get("symbol", "?")
                    print(f"[ERROR] {symbol} 评分处理出错：{type(e).__name__}: {e}")
                    traceback.print_exc()
                finally:
                    self.enriched_queue.task_done()

            except asyncio.CancelledError:
                print("[StrategyScorer] 收到取消信号，退出评分循环")
                return
            except Exception as e:  # noqa: BLE001
                print(f"[StrategyScorer] 循环出错：{type(e).__name__}: {e}")
                await asyncio.sleep(1)
