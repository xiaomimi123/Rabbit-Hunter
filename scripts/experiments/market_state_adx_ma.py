"""市场状态识别 · 第一类探索实验:ADX(14) + EMA20/50 标签。

**性质**:纯离线研究,只读 kline 缓存 + walkforward 报告 JSON;
       不写 DB、不改生产配置、不干扰 paper 前向测试。

**规则**(初值固定,由用户拍板后再调):
  TREND_UP   : ADX > 25 且 EMA20 > EMA50 且 EMA50 斜率 > 0
  TREND_DOWN : ADX > 25 且 EMA20 < EMA50 且 EMA50 斜率 < 0
  RANGE      : ADX < 20 (趋势弱)
  TRANSITION : 其余(ADX 20-25,或 ADX>25 但均线未对齐)

**用法**:
  python3 -m scripts.experiments.market_state_adx_ma \
      --start 2026-03-07 --end 2026-07-04 \
      --symbols BTCUSDT,ETHUSDT,SOLUSDT \
      --wf-report reports/wf_2beb79ee_vB_baseline_mh240.json \
      --out reports/market_state_adx_ma_report.md
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional

# 让 script 能直接从 project root 跑
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from scripts.backtest.kline_fetcher import fetch_klines_with_cache


# ── 阈值(初值,别调参凑数)─────────────────────────────────────
ADX_STRONG = 25.0
ADX_WEAK = 20.0
ADX_PERIOD = 14
EMA_FAST = 20
EMA_SLOW = 50
SLOPE_LOOKBACK = 5  # EMA50 与 5 bar 前对比看方向


# ── 指标计算 ──────────────────────────────────────────────────

def _ema(values: List[float], period: int) -> List[float]:
    """标准 EMA。返回长度与 values 相同,前 period-1 个为 None。"""
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return out  # type: ignore
    alpha = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    for i in range(period, len(values)):
        out[i] = values[i] * alpha + out[i - 1] * (1 - alpha)  # type: ignore
    return out  # type: ignore


def _wilder_rma(values: List[Optional[float]], period: int) -> List[Optional[float]]:
    """Wilder's RMA (used in ADX). values 可以含 None (前若干个),
    从第一个非 None 位置起做累加平均。"""
    out: List[Optional[float]] = [None] * len(values)
    # 找第一个非 None
    start = 0
    while start < len(values) and values[start] is None:
        start += 1
    if start + period > len(values):
        return out
    seed = sum(values[start:start + period]) / period  # type: ignore
    out[start + period - 1] = seed
    for i in range(start + period, len(values)):
        prev = out[i - 1]
        cur = values[i]
        if prev is None or cur is None:
            continue
        out[i] = (prev * (period - 1) + cur) / period
    return out


def _adx(highs: List[float], lows: List[float], closes: List[float],
         period: int = 14) -> List[Optional[float]]:
    """Wilder's ADX。"""
    n = len(highs)
    if n < period * 2:
        return [None] * n
    # +DM, -DM, TR
    plus_dm: List[Optional[float]] = [None] * n
    minus_dm: List[Optional[float]] = [None] * n
    tr: List[Optional[float]] = [None] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    # Wilder smoothing (RMA)
    plus_dm_rma = _wilder_rma(plus_dm, period)
    minus_dm_rma = _wilder_rma(minus_dm, period)
    tr_rma = _wilder_rma(tr, period)
    # +DI, -DI
    plus_di: List[Optional[float]] = [None] * n
    minus_di: List[Optional[float]] = [None] * n
    for i in range(n):
        if plus_dm_rma[i] is None or tr_rma[i] is None or tr_rma[i] == 0:
            continue
        plus_di[i] = 100.0 * plus_dm_rma[i] / tr_rma[i]
        minus_di[i] = 100.0 * minus_dm_rma[i] / tr_rma[i]  # type: ignore
    # DX = 100 * |+DI - -DI| / (+DI + -DI)
    dx: List[Optional[float]] = [None] * n
    for i in range(n):
        p = plus_di[i]
        m = minus_di[i]
        if p is None or m is None:
            continue
        s = p + m
        if s == 0:
            continue
        dx[i] = 100.0 * abs(p - m) / s
    # ADX = Wilder RMA(DX)
    return _wilder_rma(dx, period)


# ── 标签规则 ──────────────────────────────────────────────────

def label_bar(adx: Optional[float], ema20: Optional[float], ema50: Optional[float],
              ema50_prev: Optional[float]) -> str:
    """给一根 K 线打标签。初值规则,别调。"""
    if adx is None or ema20 is None or ema50 is None or ema50_prev is None:
        return "UNKNOWN"
    slope = ema50 - ema50_prev  # 正 = 向上
    if adx < ADX_WEAK:
        return "RANGE"
    if adx > ADX_STRONG:
        if ema20 > ema50 and slope > 0:
            return "TREND_UP"
        if ema20 < ema50 and slope < 0:
            return "TREND_DOWN"
    # ADX 20-25 中间地带,或 ADX>25 但均线不对齐
    return "TRANSITION"


def label_series(klines: List[List[float]]) -> List[Tuple[int, str]]:
    """输入 klines (OHLCV list),返回 [(timestamp_ms, label), ...]。"""
    if len(klines) < max(EMA_SLOW, ADX_PERIOD * 2) + SLOPE_LOOKBACK:
        return []
    ts_ms = [int(k[0]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    closes = [float(k[4]) for k in klines]

    ema20 = _ema(closes, EMA_FAST)
    ema50 = _ema(closes, EMA_SLOW)
    adx = _adx(highs, lows, closes, ADX_PERIOD)

    out = []
    for i in range(len(klines)):
        if i < SLOPE_LOOKBACK:
            ema50_prev = None
        else:
            ema50_prev = ema50[i - SLOPE_LOOKBACK]
        out.append((ts_ms[i], label_bar(adx[i], ema20[i], ema50[i], ema50_prev)))
    return out


def find_state_at(labels: List[Tuple[int, str]], entry_time) -> str:
    """在 labels 序列里查找入场时刻的状态。取最近一根已收盘的 4h bar。

    entry_time 可以是 ISO string 或 Unix ms (int)。
    """
    if isinstance(entry_time, (int, float)):
        target_ms = int(entry_time)
    else:
        t = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
        target_ms = int(t.timestamp() * 1000)
    last_label = "UNKNOWN"
    for ts, lab in labels:
        if ts > target_ms:
            break
        last_label = lab
    return last_label


# ── 分析 ─────────────────────────────────────────────────────

def summarize_dist(labels: List[Tuple[int, str]]) -> Dict[str, int]:
    """标签占比统计。"""
    from collections import Counter
    return dict(Counter(lab for _, lab in labels))


def _entry_time_field(tr: dict):
    """兼容 entry_ts (Unix ms) / entry_time / entry_iso。"""
    return tr.get("entry_ts") or tr.get("entry_time") or tr.get("entry_iso")


def _net_r_field(tr: dict) -> float:
    """兼容 net_r / r_net / gross_r / r_gross。"""
    for k in ("net_r", "r_net", "gross_r", "r_gross"):
        v = tr.get(k)
        if v is not None:
            return float(v)
    return 0.0


def group_trades_by_state(entries: List[dict], sym_labels: Dict[str, List[Tuple[int, str]]]) -> Dict[str, List[dict]]:
    """把 wf oos_entries 按入场时市场状态分组。"""
    groups: Dict[str, List[dict]] = {}
    for tr in entries:
        sym = tr.get("symbol")
        et = _entry_time_field(tr)
        if not sym or et is None or sym not in sym_labels:
            continue
        state = find_state_at(sym_labels[sym], et)
        groups.setdefault(state, []).append(tr)
    return groups


def group_trades_by_symbol_state(entries: List[dict], sym_labels: Dict[str, List[Tuple[int, str]]]) -> Dict[Tuple[str, str], List[dict]]:
    """按 (symbol, state) 双维分组。"""
    groups: Dict[Tuple[str, str], List[dict]] = {}
    for tr in entries:
        sym = tr.get("symbol")
        et = _entry_time_field(tr)
        if not sym or et is None or sym not in sym_labels:
            continue
        state = find_state_at(sym_labels[sym], et)
        groups.setdefault((sym, state), []).append(tr)
    return groups


def stats(entries: List[dict]) -> Dict[str, float]:
    """计算 net PF / win rate / avgR / totalR / n。"""
    if not entries:
        return {"n": 0, "win_rate": 0.0, "avg_r": 0.0, "total_r": 0.0, "pf": 0.0}
    rs = [_net_r_field(e) for e in entries]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    total_win = sum(wins)
    total_loss = abs(sum(losses))
    pf = total_win / total_loss if total_loss > 0 else (float("inf") if total_win > 0 else 0.0)
    return {
        "n": len(rs),
        "win_rate": len(wins) / len(rs),
        "avg_r": sum(rs) / len(rs),
        "total_r": sum(rs),
        "pf": pf,
    }


# ── 报告输出 ─────────────────────────────────────────────────

def render_report(cfg: dict, dist_by_sym: Dict[str, Dict[str, int]],
                  main_groups: Dict[str, Dict[str, float]],
                  indep_groups: Dict[str, Dict[str, float]]) -> str:
    lines: List[str] = []
    L = lines.append

    L("# 市场状态识别 · 第一类实验报告(ADX + 均线)")
    L("")
    L(f"> **日期**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ")
    L(f"> **性质**: 探索性离线研究,不改动 paper 前向测试。  ")
    L(f"> **数据范围**: {cfg['start']} → {cfg['end']}  ")
    L(f"> **周期**: 4h  ")
    L(f"> **标的**: {', '.join(cfg['symbols'])}  ")
    L(f"> **策略**: macd_reversal_long (variant B) —— 由 walkforward 报告 `{os.path.basename(cfg['wf_report'])}` 提供 26 OOS 笔  ")
    L("")

    L("## 标签规则(初值,固定)")
    L("")
    L("| 标签 | 条件 |")
    L("|---|---|")
    L(f"| TREND_UP | ADX({ADX_PERIOD}) > {ADX_STRONG} 且 EMA{EMA_FAST} > EMA{EMA_SLOW} 且 EMA{EMA_SLOW} 斜率 > 0 |")
    L(f"| TREND_DOWN | ADX({ADX_PERIOD}) > {ADX_STRONG} 且 EMA{EMA_FAST} < EMA{EMA_SLOW} 且 EMA{EMA_SLOW} 斜率 < 0 |")
    L(f"| RANGE | ADX({ADX_PERIOD}) < {ADX_WEAK} |")
    L("| TRANSITION | 其他(ADX 20-25 中间带,或 ADX>25 但均线未对齐)|")
    L("")
    L(f"斜率判据: EMA{EMA_SLOW} 当前 - EMA{EMA_SLOW}[{SLOPE_LOOKBACK} 根前]。")
    L("")

    L("## 一、各标的标签分布")
    L("")
    L("| 币种 | 总 bar 数 | TREND_UP | TREND_DOWN | RANGE | TRANSITION | UNKNOWN |")
    L("|---|---|---|---|---|---|---|")
    for sym, dist in dist_by_sym.items():
        total = sum(dist.values())
        def pct(k: str) -> str:
            v = dist.get(k, 0)
            return f"{v} ({v/total:.1%})" if total > 0 else "0"
        L(f"| {sym} | {total} | {pct('TREND_UP')} | {pct('TREND_DOWN')} | {pct('RANGE')} | {pct('TRANSITION')} | {pct('UNKNOWN')} |")
    L("")

    L("### 分布合理性判断")
    L("")
    L("- 若某标签占比 < 5%,规则可能失效(该状态几乎不出现)")
    L("- 若 TREND_UP + TREND_DOWN + RANGE + TRANSITION ≠ 100%,有 UNKNOWN 表示 kline 数据前期热身不够 —— 属正常")
    L("")

    def render_group(title: str, groups: Dict[str, Dict[str, float]]) -> None:
        L(f"## {title}")
        L("")
        L("| 状态 | n | 胜率 | avg_R | total_R | PF |")
        L("|---|---|---|---|---|---|")
        order = ["TREND_UP", "TREND_DOWN", "RANGE", "TRANSITION", "UNKNOWN"]
        for st in order:
            if st not in groups:
                continue
            g = groups[st]
            pf_str = f"{g['pf']:.3f}" if g['pf'] != float('inf') else "∞ (无损)"
            L(f"| {st} | {g['n']} | {g['win_rate']:.1%} | {g['avg_r']:+.3f}R | {g['total_r']:+.2f}R | {pf_str} |")
        L("")
        # 综合行
        totals = {"n": 0, "win_rate": 0, "avg_r": 0, "total_r": 0}
        for g in groups.values():
            totals["n"] += g["n"]
            totals["total_r"] += g["total_r"]
        L(f"合计 n={totals['n']}, total_R={totals['total_r']:+.2f}")
        L("")

    render_group("二、主样本(walkforward 全部 OOS 笔)· 按状态分组", main_groups)
    render_group("三、独立段验证(样本前半 vs 后半按时间切割)", indep_groups)

    L("## 三·延伸 · 按币种 × 状态双维拆解(主样本)")
    L("")
    L("回答关键问题:TREND_DOWN 组的好表现是不是 SOL 独扛?")
    L("")
    L("| 币种 | 状态 | n | 胜率 | avg_R | total_R | PF |")
    L("|---|---|---|---|---|---|---|")
    order_states = ["TREND_UP", "TREND_DOWN", "RANGE", "TRANSITION", "UNKNOWN"]
    for sym in cfg["symbols"]:
        for st in order_states:
            key = (sym, st)
            entries_ss = cfg["_sym_state_groups"].get(key, [])
            if not entries_ss:
                continue
            s = stats(entries_ss)
            pf_str = f"{s['pf']:.3f}" if s['pf'] != float('inf') else "∞ (无损)"
            L(f"| {sym} | {st} | {s['n']} | {s['win_rate']:.1%} | {s['avg_r']:+.3f}R | {s['total_r']:+.2f}R | {pf_str} |")
    L("")
    L("### 独扛检验")
    L("")
    td_all = [e for (sym, st), es in cfg["_sym_state_groups"].items() if st == "TREND_DOWN" for e in es]
    td_by_sym = {}
    for (sym, st), es in cfg["_sym_state_groups"].items():
        if st == "TREND_DOWN":
            td_by_sym[sym] = stats(es)
    if td_all:
        total_r_td = sum(_net_r_field(e) for e in td_all)
        L(f"TREND_DOWN 全部 {len(td_all)} 笔, total_R = {total_r_td:+.2f}R")
        L("")
        L("各币种贡献:")
        L("")
        for sym, s in td_by_sym.items():
            share = s['total_r'] / total_r_td * 100 if total_r_td != 0 else 0
            L(f"- {sym}: n={s['n']} total_R={s['total_r']:+.2f}R ({share:+.0f}% 贡献)")
    L("")

    L("## 四、结论与下一步")
    L("")
    L("### 客观判断标准")
    L("")
    L("状态识别**有价值** 需要满足 **两条同时**:")
    L("")
    L("1. **主样本**里不同状态的 PF 有**显著差异**(比如最好 vs 最差 > 1.0 或 winRate > 20pp)")
    L("2. **独立段**里同一状态排序**方向一致**(比如主样本 RANGE 最好,独立段 RANGE 仍最好或至少不最差)")
    L("")
    L("若主样本有差异但独立段消失,视为**过拟合**,不算数。")
    L("")
    L("### 具体解读")
    L("")
    # 自动生成一句结论 hint(供人 review,不代替人判断)
    main_pfs = {k: v['pf'] for k, v in main_groups.items() if v['n'] >= 3}
    if len(main_pfs) >= 2:
        pf_max = max(main_pfs.values())
        pf_min = min(main_pfs.values())
        L(f"- 主样本 PF 极差(有 n≥3 的组): {pf_max:.2f} - {pf_min:.2f} = **{pf_max - pf_min:.2f}**")
    else:
        L("- 主样本样本太少(每组 n<3),无法给出客观差异判断")
    L("")
    L("- 独立段是否与主样本方向一致,请人工对比上面两张表")
    L("")
    L("### 红线遵守")
    L("")
    L("- ✅ 未修改任何生产策略 / paper 配置")
    L("- ✅ 阈值使用初值(ADX 25/20, EMA 20/50, slope lookback 5),未 grid search")
    L("- ✅ 仅做 ADX+均线一类方法,未与其他方法混跑")
    L("")
    L("**用户拍板下一步**:")
    L("1. 差异显著 + 独立段一致 → 值得下一步(把状态标签当开关加到 scorer,或先手工验证几笔)")
    L("2. 差异显著 + 独立段消失 → 判为过拟合,换方法(下一类方法:价格结构 or 波动率)")
    L("3. 差异不显著 → ADX+均线对此策略无区分价值,同样换方法")
    L("")
    return "\n".join(lines)


# ── main ─────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="ISO date, e.g. 2026-03-07")
    ap.add_argument("--end", required=True, help="ISO date, e.g. 2026-07-04")
    ap.add_argument("--symbols", required=True, help="comma-separated e.g. BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--wf-report", required=True, help="path to walkforward JSON report (macd_reversal_long OOS entries)")
    ap.add_argument("--out", required=True, help="output markdown path")
    ap.add_argument("--cache", default=os.path.join(REPO_ROOT, "data", "backtest_cache"))
    args = ap.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    start_iso = args.start + "T00:00:00Z" if "T" not in args.start else args.start
    end_iso = args.end + "T00:00:00Z" if "T" not in args.end else args.end

    print(f"[market_state] fetching 4h klines for {symbols} from {start_iso} to {end_iso}")
    dist_by_sym: Dict[str, Dict[str, int]] = {}
    sym_labels: Dict[str, List[Tuple[int, str]]] = {}
    for sym in symbols:
        klines = fetch_klines_with_cache(args.cache, sym, "4h", start_iso, end_iso)
        print(f"[market_state] {sym}: {len(klines)} 4h bars")
        labels = label_series(klines)
        sym_labels[sym] = labels
        dist_by_sym[sym] = summarize_dist(labels)

    print(f"[market_state] loading walkforward report {args.wf_report}")
    with open(args.wf_report, "r") as f:
        wf = json.load(f)
    all_entries = wf.get("oos_entries", []) or []
    all_entries = [e for e in all_entries if e.get("symbol") in symbols]
    print(f"[market_state] {len(all_entries)} OOS entries matched")

    # 主样本 = 全部 OOS
    main_groups_raw = group_trades_by_state(all_entries, sym_labels)
    main_groups = {k: stats(v) for k, v in main_groups_raw.items()}

    # 独立段 = 按入场时间排序,取后 50% (前 50% 相当于 train-adjacent,后 50% 独立性更高)
    dated = sorted([e for e in all_entries if _entry_time_field(e) is not None],
                   key=lambda e: _entry_time_field(e))
    half = len(dated) // 2
    indep_entries = dated[half:]
    indep_groups_raw = group_trades_by_state(indep_entries, sym_labels)
    indep_groups = {k: stats(v) for k, v in indep_groups_raw.items()}
    print(f"[market_state] independent set: last {len(indep_entries)}/{len(dated)} trades")

    sym_state_groups = group_trades_by_symbol_state(all_entries, sym_labels)

    cfg = {
        "start": args.start,
        "end": args.end,
        "symbols": symbols,
        "wf_report": args.wf_report,
        "_sym_state_groups": sym_state_groups,
    }
    report = render_report(cfg, dist_by_sym, main_groups, indep_groups)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(report)
    print(f"[market_state] report → {args.out}")


if __name__ == "__main__":
    main()
