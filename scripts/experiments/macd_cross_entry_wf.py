"""MACD 金叉 进场时机 对照实验 (walk-forward, 扣实付成本)。

依据: docs/给终端的指令-进场时机对照测试.md (2026-06-26)

锁死条件 (全 variant 共用):
  - LONG only
  - 4h MACD 判信号,15m 找入场
  - 进场时 DIF 和 DEA 都 < 0 (反转打法,过滤多头延续)
  - SL = 1.5 × ATR(14, 15m),TP = 2.5 × ATR(14, 15m)
  - Max hold 8h (32 × 15m bars),超时按 close 出场
  - 扣 OKX realistic 成本 (default maker_ratio=0.5, slip=0.05% per side)

变量一 — 3 个 entry timing variant:
  A 埋伏: DIF/DEA gap 收窄、dif 上扬,在金叉前进
  B 确认: 4h K 线收盘确认金叉成立后进
  C 零轴: DIF 上穿零轴时进 (之前在零下)

变量二 (在 V1 胜者上跑) — 交叉强度阈值:
  --cross-threshold-pct: B/C 变量额外要求 (DIF-DEA)/|DEA| ≥ 该值
  --a-proximity-pct: A 变量的 gap proximity 阈值
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional, Tuple

# Add project root for imports (works both in container /app and host)
_THIS = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "scripts"))

from scripts.backtest.cost_model import (
    COST_OPTIMISTIC,
    COST_PESSIMISTIC,
    COST_REALISTIC,
    CostConfig,
    compute_cost_breakdown,
)
from scripts.backtest.kline_fetcher import fetch_klines_with_cache
from scripts.backtest.position_sim import simulate_exit
from scripts.v5_indicator_engine import _ema, calculate_atr


Variant = Literal["A", "B", "C"]


# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────


@dataclass
class ExperimentConfig:
    variant: Variant
    start_iso: str
    end_iso: str
    symbols: List[str]
    train_days: int = 60
    oos_days: int = 14
    step_days: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 2.5
    atr_period: int = 14
    max_hold_minutes: int = 8 * 60       # 同 backtest MVP
    cache_root: str = "data/backtest_cache"
    cost: CostConfig = field(default_factory=lambda: COST_REALISTIC)
    # 变量二: cross strength threshold
    cross_threshold_pct: float = 0.0     # B/C variant: 要求 (DIF-DEA)/|DEA| ≥ 此值
    a_proximity_pct: float = 0.20        # A variant: gap < 此 × 近 20 根 abs(dif) 均值


@dataclass
class TradeEntry:
    symbol: str
    side: str
    setup_type: str
    entry_ts: int
    entry_price: float
    sl_price: float
    tp_price: float
    atr_at_entry: float
    macd_dif_at_signal: float
    macd_dea_at_signal: float
    exit_ts: Optional[int] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    gross_r: Optional[float] = None
    net_r: Optional[float] = None
    fee_cost_r: Optional[float] = None
    slippage_cost_r: Optional[float] = None


# ─────────────────────────────────────────────────────────────
# Indicator helpers
# ─────────────────────────────────────────────────────────────


def _macd_series(
    closes: List[float], fast: int, slow: int, signal: int,
) -> Tuple[List[float], List[float], List[float]]:
    """返回逐根的 (dif, dea, hist) 序列,长度同 closes。

    复用 v5_indicator_engine._ema 保持公式一致。
    """
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    dif = [f - s for f, s in zip(ema_fast, ema_slow)]
    dea = _ema(dif, signal)
    hist = [d - e for d, e in zip(dif, dea)]
    return dif, dea, hist


# ─────────────────────────────────────────────────────────────
# Entry detectors — 三个 variant
# ─────────────────────────────────────────────────────────────


def detect_entries_variant_A(
    klines_4h: List[List[float]], cfg: ExperimentConfig,
) -> List[Tuple[int, float, float]]:
    """A 埋伏: DIF 还在 DEA 之下、但 gap 收窄到阈值内 + dif 上扬 + 两线 < 0。"""
    closes = [float(k[4]) for k in klines_4h]
    dif, dea, _ = _macd_series(closes, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
    signals: List[Tuple[int, float, float]] = []
    for i in range(20, len(klines_4h)):
        d_now, d_prev = dif[i], dif[i - 1]
        e_now, e_prev = dea[i], dea[i - 1]
        if not (d_now < 0 and e_now < 0):
            continue
        gap = e_now - d_now            # > 0 means dif 还在 dea 下方
        gap_prev = e_prev - d_prev
        if gap <= 0 or gap >= gap_prev:
            continue                   # 已交叉 或 gap 在扩大
        if d_now <= d_prev:
            continue                   # dif 没上扬
        recent_abs = sum(abs(x) for x in dif[i - 20:i]) / 20
        if recent_abs == 0:
            continue
        if (gap / recent_abs) > cfg.a_proximity_pct:
            continue                   # gap 还没收窄到阈值内
        signals.append((int(klines_4h[i][0]), d_now, e_now))
    return signals


def detect_entries_variant_B(
    klines_4h: List[List[float]], cfg: ExperimentConfig,
) -> List[Tuple[int, float, float]]:
    """B 确认: 4h 收盘 dif 上穿 dea + 交叉前两线都 < 0 + (可选)交叉强度阈值。"""
    closes = [float(k[4]) for k in klines_4h]
    dif, dea, _ = _macd_series(closes, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
    signals: List[Tuple[int, float, float]] = []
    for i in range(1, len(klines_4h)):
        if not (dif[i] > dea[i] and dif[i - 1] <= dea[i - 1]):
            continue                   # 当根没出现金叉
        if not (dif[i - 1] < 0 and dea[i - 1] < 0):
            continue                   # 交叉点不在零轴下方
        strength = (dif[i] - dea[i]) / max(abs(dea[i]), 1e-9)
        if strength < cfg.cross_threshold_pct:
            continue
        signals.append((int(klines_4h[i][0]), dif[i], dea[i]))
    return signals


def detect_entries_variant_C(
    klines_4h: List[List[float]], cfg: ExperimentConfig,
) -> List[Tuple[int, float, float]]:
    """C 零轴: DIF 上穿 0,且最近 5 根里至少一根两线都 < 0 (确认之前在零下)。"""
    closes = [float(k[4]) for k in klines_4h]
    dif, dea, _ = _macd_series(closes, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
    signals: List[Tuple[int, float, float]] = []
    for i in range(5, len(klines_4h)):
        if not (dif[i] > 0 and dif[i - 1] <= 0):
            continue
        had_below_zero = any(
            dif[i - j] < 0 and dea[i - j] < 0 for j in range(1, 6)
        )
        if not had_below_zero:
            continue
        # 变量二: 强度阈值在 C 上 = dif 越过零轴的"力度"
        # 用 dif[i] / recent_abs_dif 衡量
        recent_abs = sum(abs(x) for x in dif[i - 20:i]) / 20 if i >= 20 else 1.0
        if recent_abs > 0 and (dif[i] / recent_abs) < cfg.cross_threshold_pct:
            continue
        signals.append((int(klines_4h[i][0]), dif[i], dea[i]))
    return signals


DETECTORS = {
    "A": detect_entries_variant_A,
    "B": detect_entries_variant_B,
    "C": detect_entries_variant_C,
}


# ─────────────────────────────────────────────────────────────
# Trade execution
# ─────────────────────────────────────────────────────────────


def execute_trades(
    symbol: str,
    klines_15m: List[List[float]],
    signals: List[Tuple[int, float, float]],
    cfg: ExperimentConfig,
) -> List[TradeEntry]:
    """对每个 4h 信号,在下一根 15m 收盘进,用 OHLC-touch 模拟 SL/TP 出场,扣成本。"""
    trades: List[TradeEntry] = []
    for sig_ts, dif_val, dea_val in signals:
        # 在 15m 上找 ≥ sig_ts 的第一根作为 entry bar
        idx = None
        for i, k in enumerate(klines_15m):
            if k[0] >= sig_ts:
                idx = i
                break
        if idx is None or idx + 1 >= len(klines_15m):
            continue
        # 用该 15m bar 的 close 作 entry price
        entry_bar = klines_15m[idx]
        entry_ts = int(entry_bar[0])
        entry_price = float(entry_bar[4])
        # 在 entry 前算 ATR(14, 15m)
        atr_window = klines_15m[max(0, idx - cfg.atr_period):idx + 1]
        if len(atr_window) < cfg.atr_period + 1:
            continue
        try:
            atr = calculate_atr(atr_window, period=cfg.atr_period)
        except ValueError:
            continue
        sl_distance = cfg.sl_atr_mult * atr
        tp_distance = cfg.tp_atr_mult * atr
        sl_price = entry_price - sl_distance      # LONG only
        tp_price = entry_price + tp_distance

        klines_after = klines_15m[idx + 1:]
        exit_ts, exit_price, exit_reason, gross_r = simulate_exit(
            entry_ts=entry_ts,
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            side="LONG",
            klines_after=klines_after,
            max_hold_minutes=cfg.max_hold_minutes,
            interval_min=15,
        )
        if gross_r is None:
            continue
        bk = compute_cost_breakdown(
            gross_r=gross_r,
            entry_price=entry_price,
            sl_price=sl_price,
            cfg=cfg.cost,
        )
        trades.append(TradeEntry(
            symbol=symbol,
            side="LONG",
            setup_type=f"macd_cross_variant_{cfg.variant}",
            entry_ts=entry_ts,
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            atr_at_entry=atr,
            macd_dif_at_signal=dif_val,
            macd_dea_at_signal=dea_val,
            exit_ts=exit_ts,
            exit_price=exit_price,
            exit_reason=exit_reason,
            gross_r=gross_r,
            net_r=bk.net_r,
            fee_cost_r=bk.fee_cost_r,
            slippage_cost_r=bk.slippage_cost_r,
        ))
    return trades


# ─────────────────────────────────────────────────────────────
# Aggregation
# ─────────────────────────────────────────────────────────────


def aggregate_stats(trades: List[TradeEntry], use_net: bool = True) -> dict:
    if not trades:
        return {"n": 0, "win_rate": 0.0, "avg_r": 0.0, "total_r": 0.0,
                "pf": None, "max_dd_r": 0.0}
    rs = [t.net_r if use_net else t.gross_r for t in trades]
    rs = [r for r in rs if r is not None]
    if not rs:
        return {"n": 0, "win_rate": 0.0, "avg_r": 0.0, "total_r": 0.0,
                "pf": None, "max_dd_r": 0.0}
    n = len(rs)
    wins = sum(1 for r in rs if r > 0)
    total = sum(rs)
    pos = sum(r for r in rs if r > 0)
    neg = sum(abs(r) for r in rs if r < 0)
    pf = (pos / neg) if neg > 0 else float("inf")
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        if cum - peak < max_dd:
            max_dd = cum - peak
    return {
        "n": n,
        "win_rate": wins / n,
        "avg_r": total / n,
        "total_r": total,
        "pf": pf if pf != float("inf") else None,
        "max_dd_r": max_dd,
    }


# ─────────────────────────────────────────────────────────────
# Walk-Forward orchestration
# ─────────────────────────────────────────────────────────────


def run_walkforward(cfg: ExperimentConfig) -> dict:
    detector = DETECTORS[cfg.variant]
    start_dt = datetime.fromisoformat(cfg.start_iso.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(cfg.end_iso.replace("Z", "+00:00"))

    # Build rolling WF windows
    windows = []
    train_end = start_dt + timedelta(days=cfg.train_days)
    while train_end + timedelta(days=cfg.oos_days) <= end_dt:
        oos_start = train_end
        oos_end = oos_start + timedelta(days=cfg.oos_days)
        windows.append({
            "train_start": start_dt.isoformat(),
            "train_end": train_end.isoformat(),
            "oos_start": oos_start.isoformat(),
            "oos_end": oos_end.isoformat(),
        })
        train_end = train_end + timedelta(days=cfg.step_days)

    print(
        f"[EXP] variant={cfg.variant} symbols={cfg.symbols} "
        f"windows={len(windows)} cost_preset={cfg.cost}",
        file=sys.stderr,
    )

    all_trades: List[TradeEntry] = []
    skipped: List[str] = []
    for symbol in cfg.symbols:
        try:
            klines_4h = fetch_klines_with_cache(
                cfg.cache_root, symbol, "4h", cfg.start_iso, cfg.end_iso,
            )
            klines_15m = fetch_klines_with_cache(
                cfg.cache_root, symbol, "15m", cfg.start_iso, cfg.end_iso,
            )
        except Exception as e:
            print(f"[EXP] skip {symbol}: {type(e).__name__}: {e}", file=sys.stderr)
            skipped.append(symbol)
            continue
        signals = detector(klines_4h, cfg)
        sym_trades = execute_trades(symbol, klines_15m, signals, cfg)
        all_trades.extend(sym_trades)
        print(
            f"[EXP]   {symbol}: 4h sigs={len(signals)} → closed trades={len(sym_trades)}",
            file=sys.stderr,
        )

    # Filter to OOS-only entries
    oos_trades: List[TradeEntry] = []
    for t in all_trades:
        entry_dt = datetime.fromtimestamp(t.entry_ts / 1000, tz=timezone.utc)
        for w in windows:
            oos_s = datetime.fromisoformat(w["oos_start"])
            oos_e = datetime.fromisoformat(w["oos_end"])
            if oos_s <= entry_dt < oos_e:
                oos_trades.append(t)
                break

    # By-symbol breakdown (OOS net)
    by_symbol: dict = {}
    for sym in cfg.symbols:
        sym_t = [t for t in oos_trades if t.symbol == sym]
        if sym_t:
            by_symbol[sym] = aggregate_stats(sym_t, use_net=True)

    print(
        f"[EXP] all closed trades: {len(all_trades)}, OOS-only: {len(oos_trades)}",
        file=sys.stderr,
    )

    return {
        "variant": cfg.variant,
        "config": {
            **{k: v for k, v in asdict(cfg).items() if k != "cost"},
            "cost_config": {
                "maker_fee_rate": cfg.cost.maker_fee_rate,
                "taker_fee_rate": cfg.cost.taker_fee_rate,
                "slippage_pct": cfg.cost.slippage_pct,
                "maker_ratio": cfg.cost.maker_ratio,
                "effective_fee_per_side": cfg.cost.effective_fee_per_side(),
            },
        },
        "windows": windows,
        "skipped_symbols": skipped,
        "all_trades_n": len(all_trades),
        "oos_n": len(oos_trades),
        "oos_gross": aggregate_stats(oos_trades, use_net=False),
        "oos_net": aggregate_stats(oos_trades, use_net=True),
        "by_symbol_net": by_symbol,
        "oos_entries": [asdict(t) for t in oos_trades],
    }


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--variant", required=True, choices=["A", "B", "C"])
    p.add_argument("--start", required=True, help="ISO start (UTC)")
    p.add_argument("--end", required=True, help="ISO end (UTC)")
    p.add_argument("--symbols", required=True, help="CSV: APTUSDT,NEARUSDT,...")
    p.add_argument("--train-days", type=int, default=60)
    p.add_argument("--oos-days", type=int, default=14)
    p.add_argument("--step-days", type=int, default=14)
    p.add_argument("--cost-preset", choices=["optimistic", "realistic", "pessimistic"],
                   default="realistic")
    p.add_argument("--cross-threshold-pct", type=float, default=0.0,
                   help="变量二: B/C variant 交叉强度阈值 (dif-dea)/|dea| ≥ 此值")
    p.add_argument("--a-proximity-pct", type=float, default=0.20,
                   help="A variant: gap < 此 × 近 20 根 abs(dif) 均值")
    p.add_argument("--out", required=True)
    p.add_argument("--cache-root", default="data/backtest_cache")
    args = p.parse_args()

    cost = {
        "realistic": COST_REALISTIC,
        "optimistic": COST_OPTIMISTIC,
        "pessimistic": COST_PESSIMISTIC,
    }[args.cost_preset]

    cfg = ExperimentConfig(
        variant=args.variant,
        start_iso=args.start,
        end_iso=args.end,
        symbols=[s.strip() for s in args.symbols.split(",") if s.strip()],
        train_days=args.train_days,
        oos_days=args.oos_days,
        step_days=args.step_days,
        cache_root=args.cache_root,
        cost=cost,
        cross_threshold_pct=args.cross_threshold_pct,
        a_proximity_pct=args.a_proximity_pct,
    )

    result = run_walkforward(cfg)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"[EXP] report → {args.out}")
    net = result["oos_net"]
    if net["n"] > 0:
        pf_str = f"{net['pf']:.2f}" if net["pf"] is not None else "∞"
        print(
            f"[EXP] OOS net: n={net['n']} win={net['win_rate']*100:.0f}% "
            f"avg_R={net['avg_r']:+.3f} PF={pf_str} maxDD={net['max_dd_r']:+.2f}R"
        )
    else:
        print("[EXP] OOS net: n=0 (no trades, suspect data range / detector)")


if __name__ == "__main__":
    main()
