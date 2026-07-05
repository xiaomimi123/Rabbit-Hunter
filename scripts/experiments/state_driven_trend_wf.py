"""纯状态驱动 · 顺势策略 · 候选策略回测。

**性质**: 全新候选策略,和 macd_reversal_long 彻底独立。
**信号源**: 仅 ADX(14) + EMA20/50 状态标签,**不用 MACD 任何信号**。
**方向**: 顺势 —— TREND_UP 开 LONG, TREND_DOWN 开 SHORT。RANGE/TRANSITION 不开。

**入场规则**:
  状态从非 TREND_UP 变到 TREND_UP → 下一根 4h bar 开盘 LONG
  状态从非 TREND_DOWN 变到 TREND_DOWN → 下一根 4h bar 开盘 SHORT
  (只在"状态首次转入"时开,同状态持续中不重复开)

**出场规则**(同 macd_reversal_long 保持公平比较):
  SL_HIT   : 触碰 entry ∓ 1.5 × ATR
  TP_HIT   : 触碰 entry ± 2.5 × ATR (计划 RR = 1.67)
  HORIZON_TIMEOUT: 持仓超 max_hold_bars (默认 6 根 4h bar = 24h)

**成本**: realistic 预设(fee 0.11R + slippage 0.17R = ~0.28R/笔),
        对齐 macd_reversal_long 使用的成本模型。

**用法**:
  python3 -m scripts.experiments.state_driven_trend_wf \
      --start 2026-03-07 --end 2026-07-04 \
      --symbols BTCUSDT,ETHUSDT,SOLUSDT \
      --out reports/state_driven_trend_wf.json

**红线**:
  - 只测试,不进 scorer,不改任何生产策略
  - 阈值用 market_state_adx_ma.py 同一初值,未 grid search
  - 不与 macd_reversal_long 交互,输出独立 JSON 报告
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from scripts.backtest.kline_fetcher import fetch_klines_with_cache
from scripts.experiments.market_state_adx_ma import (
    label_series, ADX_STRONG, ADX_WEAK, EMA_FAST, EMA_SLOW, SLOPE_LOOKBACK,
    ADX_PERIOD,
)


# ── 策略参数(固定,别调) ──────────────────────────────────
ATR_PERIOD = 14
SL_ATR_MULT = 1.5
TP_ATR_MULT = 2.5
MAX_HOLD_BARS = 6  # 6 × 4h = 24h
# 成本 (realistic preset, 单位: R multiple)
FEE_R = 0.11
SLIPPAGE_R = 0.17


def _atr(highs: List[float], lows: List[float], closes: List[float],
         period: int = 14) -> List[Optional[float]]:
    """Wilder ATR。"""
    n = len(highs)
    if n < period + 1:
        return [None] * n
    tr: List[Optional[float]] = [None] * n
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    out: List[Optional[float]] = [None] * n
    # 首个 ATR = simple average of first period TRs (从 i=1 起)
    if period + 1 > n:
        return out
    seed = sum(tr[1:period + 1]) / period  # type: ignore
    out[period] = seed
    for i in range(period + 1, n):
        prev = out[i - 1]
        cur = tr[i]
        if prev is None or cur is None:
            continue
        out[i] = (prev * (period - 1) + cur) / period
    return out


def backtest_symbol(symbol: str, klines: List[List[float]],
                    allow_long: bool = True, allow_short: bool = True) -> List[dict]:
    """在单个 symbol 的 4h kline 上跑纯状态驱动策略,返回 trades list。"""
    n = len(klines)
    if n < max(EMA_SLOW, ADX_PERIOD * 2, ATR_PERIOD) + SLOPE_LOOKBACK + 2:
        return []

    ts_ms = [int(k[0]) for k in klines]
    opens = [float(k[1]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    closes = [float(k[4]) for k in klines]

    labels = label_series(klines)  # [(ts, label), ...]
    atr = _atr(highs, lows, closes, ATR_PERIOD)

    trades: List[dict] = []
    # 记录"上一根 bar 状态",遇到状态首次转入 TREND_UP/DOWN 就开仓
    for i in range(1, n - 1):
        prev_state = labels[i - 1][1]
        curr_state = labels[i][1]
        if curr_state == prev_state:
            continue
        side = None
        if curr_state == "TREND_UP" and prev_state != "TREND_UP" and allow_long:
            side = "LONG"
        elif curr_state == "TREND_DOWN" and prev_state != "TREND_DOWN" and allow_short:
            side = "SHORT"
        if side is None:
            continue

        # 下一根 4h bar 开盘入场
        entry_idx = i + 1
        entry_price = opens[entry_idx]
        entry_ts = ts_ms[entry_idx]
        entry_atr = atr[i]  # 用信号出现时(i)的 ATR
        if entry_atr is None or entry_atr <= 0 or entry_price <= 0:
            continue

        if side == "LONG":
            sl_price = entry_price - SL_ATR_MULT * entry_atr
            tp_price = entry_price + TP_ATR_MULT * entry_atr
        else:
            sl_price = entry_price + SL_ATR_MULT * entry_atr
            tp_price = entry_price - TP_ATR_MULT * entry_atr

        # 向后扫描 4h bars 找 SL/TP/timeout
        exit_price = None
        exit_ts = None
        exit_reason = None
        for j in range(entry_idx, min(entry_idx + MAX_HOLD_BARS, n)):
            h = highs[j]
            l = lows[j]
            if side == "LONG":
                # 保守假设: 一根 bar 内 SL 先于 TP 触发
                if l <= sl_price:
                    exit_price = sl_price
                    exit_ts = ts_ms[j]
                    exit_reason = "SL_HIT"
                    break
                if h >= tp_price:
                    exit_price = tp_price
                    exit_ts = ts_ms[j]
                    exit_reason = "TP_HIT"
                    break
            else:  # SHORT
                if h >= sl_price:
                    exit_price = sl_price
                    exit_ts = ts_ms[j]
                    exit_reason = "SL_HIT"
                    break
                if l <= tp_price:
                    exit_price = tp_price
                    exit_ts = ts_ms[j]
                    exit_reason = "TP_HIT"
                    break

        if exit_price is None:
            # 用 max_hold 最后一根 close 平仓
            j_last = min(entry_idx + MAX_HOLD_BARS - 1, n - 1)
            exit_price = closes[j_last]
            exit_ts = ts_ms[j_last]
            exit_reason = "HORIZON_TIMEOUT"

        # 计算 R multiple
        sl_dist = abs(entry_price - sl_price)
        if sl_dist == 0:
            continue
        if side == "LONG":
            gross_r = (exit_price - entry_price) / sl_dist
        else:
            gross_r = (entry_price - exit_price) / sl_dist
        net_r = gross_r - FEE_R - SLIPPAGE_R

        trades.append({
            "symbol": symbol,
            "side": side,
            "state_at_entry": curr_state,
            "state_prev": prev_state,
            "setup_type": "state_driven_trend",
            "entry_ts": entry_ts,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "atr_at_entry": entry_atr,
            "exit_ts": exit_ts,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "gross_r": gross_r,
            "net_r": net_r,
            "fee_cost_r": FEE_R,
            "slippage_cost_r": SLIPPAGE_R,
        })
    return trades


# ── OOS 折叠 · 与 macd_cross_entry_wf 相同结构 ─────────────

def split_folds(start: datetime, end: datetime, oos_days: int, step_days: int) -> List[Tuple[datetime, datetime]]:
    """按 step 切成非重叠 OOS 窗口。"""
    folds: List[Tuple[datetime, datetime]] = []
    # 与前作对齐:跳过前 60 天(相当于 train warm-up),从第 60 天起 14 天一 OOS 窗口
    train_start = start + timedelta(days=60)
    cur = train_start
    while cur + timedelta(days=oos_days) <= end:
        folds.append((cur, cur + timedelta(days=oos_days)))
        cur = cur + timedelta(days=step_days)
    return folds


def filter_by_ts_range(trades: List[dict], start: datetime, end: datetime) -> List[dict]:
    s_ms = int(start.timestamp() * 1000)
    e_ms = int(end.timestamp() * 1000)
    return [t for t in trades if s_ms <= t["entry_ts"] < e_ms]


def compute_summary(trades: List[dict], gross: bool = False) -> Dict[str, float]:
    if not trades:
        return {"n": 0, "win_rate": 0.0, "avg_r": 0.0, "total_r": 0.0, "pf": 0.0, "max_dd_r": 0.0}
    key = "gross_r" if gross else "net_r"
    rs = [t[key] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    total_win = sum(wins)
    total_loss = abs(sum(losses))
    pf = total_win / total_loss if total_loss > 0 else (float("inf") if total_win > 0 else 0.0)
    # cumulative R + max drawdown
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rs:
        cum += r
        if cum > peak:
            peak = cum
        dd = cum - peak
        if dd < max_dd:
            max_dd = dd
    return {
        "n": len(rs),
        "win_rate": len(wins) / len(rs),
        "avg_r": sum(rs) / len(rs),
        "total_r": sum(rs),
        "pf": pf,
        "max_dd_r": max_dd,
    }


# ── main ─────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default=os.path.join(REPO_ROOT, "data", "backtest_cache"))
    ap.add_argument("--oos-days", type=int, default=14)
    ap.add_argument("--step-days", type=int, default=14)
    ap.add_argument("--long-only", action="store_true", help="只测 LONG (与 macd_reversal_long 对齐)")
    args = ap.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    start_dt = datetime.fromisoformat((args.start + "T00:00:00+00:00") if "T" not in args.start else args.start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat((args.end + "T00:00:00+00:00") if "T" not in args.end else args.end.replace("Z", "+00:00"))
    start_iso = args.start + "T00:00:00Z" if "T" not in args.start else args.start
    end_iso = args.end + "T00:00:00Z" if "T" not in args.end else args.end

    # 全部时段的 trades
    all_trades: List[dict] = []
    per_sym_trades: Dict[str, List[dict]] = {}
    for sym in symbols:
        print(f"[state_driven] fetching {sym} 4h from {start_iso} to {end_iso}")
        klines = fetch_klines_with_cache(args.cache, sym, "4h", start_iso, end_iso)
        print(f"[state_driven] {sym}: {len(klines)} bars")
        trades = backtest_symbol(sym, klines,
                                  allow_long=True,
                                  allow_short=not args.long_only)
        print(f"[state_driven] {sym}: {len(trades)} candidate trades")
        per_sym_trades[sym] = trades
        all_trades.extend(trades)

    # OOS 折叠
    folds = split_folds(start_dt, end_dt, args.oos_days, args.step_days)
    print(f"[state_driven] {len(folds)} OOS folds")

    oos_trades: List[dict] = []
    windows_out: List[dict] = []
    for i, (fold_start, fold_end) in enumerate(folds):
        fold_trades = filter_by_ts_range(all_trades, fold_start, fold_end)
        oos_trades.extend(fold_trades)
        windows_out.append({
            "index": i,
            "oos_start": fold_start.isoformat(),
            "oos_end": fold_end.isoformat(),
            "n": len(fold_trades),
        })
        print(f"  fold {i}: {fold_start.date()} → {fold_end.date()}: {len(fold_trades)} trades")

    # 聚合
    oos_gross = compute_summary(oos_trades, gross=True)
    oos_net = compute_summary(oos_trades, gross=False)

    # 按 symbol 拆分 (OOS net)
    by_symbol_net: Dict[str, Dict[str, float]] = {}
    for sym in symbols:
        sym_trades = [t for t in oos_trades if t["symbol"] == sym]
        by_symbol_net[sym] = compute_summary(sym_trades, gross=False)

    # 按 side 拆分 (OOS net)
    by_side_net: Dict[str, Dict[str, float]] = {}
    for side in ("LONG", "SHORT"):
        side_trades = [t for t in oos_trades if t["side"] == side]
        by_side_net[side] = compute_summary(side_trades, gross=False)

    # 状态入场分布
    from collections import Counter
    state_counts = Counter(t["state_at_entry"] for t in oos_trades)

    report = {
        "strategy": "state_driven_trend",
        "description": "纯 ADX(14)+EMA20/50 状态驱动·顺势·无 MACD",
        "config": {
            "start_iso": args.start,
            "end_iso": args.end,
            "symbols": symbols,
            "adx_period": ADX_PERIOD,
            "adx_strong": ADX_STRONG,
            "adx_weak": ADX_WEAK,
            "ema_fast": EMA_FAST,
            "ema_slow": EMA_SLOW,
            "slope_lookback": SLOPE_LOOKBACK,
            "atr_period": ATR_PERIOD,
            "sl_atr_mult": SL_ATR_MULT,
            "tp_atr_mult": TP_ATR_MULT,
            "planned_rr": TP_ATR_MULT / SL_ATR_MULT,
            "max_hold_bars": MAX_HOLD_BARS,
            "fee_r": FEE_R,
            "slippage_r": SLIPPAGE_R,
            "long_only": args.long_only,
            "oos_days": args.oos_days,
            "step_days": args.step_days,
        },
        "windows": windows_out,
        "all_trades_n": len(all_trades),
        "oos_n": len(oos_trades),
        "oos_gross": oos_gross,
        "oos_net": oos_net,
        "by_symbol_net": by_symbol_net,
        "by_side_net": by_side_net,
        "entry_state_counts": dict(state_counts),
        "oos_entries": oos_trades,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print()
    print(f"=== 报告 → {args.out} ===")
    print(f"OOS trades: {oos_gross['n']}")
    print(f"  gross: winRate={oos_gross['win_rate']:.1%} avgR={oos_gross['avg_r']:+.3f} totalR={oos_gross['total_r']:+.2f} PF={oos_gross['pf']:.3f}")
    print(f"  net:   winRate={oos_net['win_rate']:.1%} avgR={oos_net['avg_r']:+.3f} totalR={oos_net['total_r']:+.2f} PF={oos_net['pf']:.3f}")
    print()
    print("按币种 (net):")
    for sym, s in by_symbol_net.items():
        print(f"  {sym}: n={s['n']} winRate={s['win_rate']:.1%} totalR={s['total_r']:+.2f}R PF={s['pf']:.3f}")
    print()
    print("按方向 (net):")
    for side, s in by_side_net.items():
        print(f"  {side}: n={s['n']} winRate={s['win_rate']:.1%} totalR={s['total_r']:+.2f}R PF={s['pf']:.3f}")
    print()
    print(f"入场时状态分布: {dict(state_counts)}")


if __name__ == "__main__":
    main()
