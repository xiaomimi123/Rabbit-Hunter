"""SHADOW → LIVE 升级硬门槛自动检查。

跑法:
  docker exec rabbit-hunter-api python /app/scripts/check_live_readiness.py
"""
from __future__ import annotations

import sqlite3
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple


DB_PATH = os.environ.get("DB_PATH", "/app/data/rabbit_hunter.db")

# 成本假设(跟 backtest 一致)
ROUND_TRIP_COST_PCT = 0.002          # 0.20% notional 来回手续费 + 滑点估计

# trial 起算时间 — 默认看最近 14 天。改这里可以看更长窗口。
TRIAL_DAYS = int(os.environ.get("TRIAL_DAYS", "14"))

# ──────────────────────────────────────────────────────────────────────────────
# Gate definitions
# ──────────────────────────────────────────────────────────────────────────────

PASS = "✓"
FAIL = "✗"
SKIP = "?"


def fmt_gate(code: str, label: str, status: str, detail: str = "") -> str:
    color = "\033[32m" if status == PASS else ("\033[31m" if status == FAIL else "\033[33m")
    reset = "\033[0m"
    return f"  [{color}{status}{reset}] {code} {label:<50} {detail}"


def _auto_closed(conn, since: str):
    return conn.execute("""
        SELECT pnl, pnl_percent, exit_reason, side, holding_hours,
               entry_price, position_size_usdt, entry_time
          FROM paper_trades
         WHERE status='CLOSED'
           AND strategy_id='v5_rsi_macd'
           AND pnl IS NOT NULL
           AND entry_time >= ?
         ORDER BY entry_time ASC
    """, (since,)).fetchall()


def _all_closed_since(conn, since: str):
    return conn.execute("""
        SELECT pnl, exit_reason, strategy_id, entry_time, side, entry_price, position_size_usdt
          FROM paper_trades
         WHERE entry_time >= ?
    """, (since,)).fetchall()


def net_pnl(row):
    """模拟成本:notional × 0.20% 来回。"""
    pnl, _, _, _, _, entry_price, size_usdt, _ = row
    if entry_price is None or size_usdt is None:
        return pnl or 0
    cost = entry_price * 0 + size_usdt * ROUND_TRIP_COST_PCT
    return (pnl or 0) - cost


def calc_max_drawdown(pnls_in_order):
    cum, peak, mdd = 0.0, 0.0, 0.0
    for p in pnls_in_order:
        cum += p
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return cum, peak, mdd


def calc_longest_losing_streak(pnls_in_order):
    streak = 0
    longest = 0
    for p in pnls_in_order:
        if p < 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
    return longest


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(DB_PATH):
        print(f"DB 不存在: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    since = (datetime.now(timezone.utc) - timedelta(days=TRIAL_DAYS)).isoformat()

    print(f"\n=== SHADOW → LIVE 升级硬门槛检查 ===")
    print(f"窗口: 最近 {TRIAL_DAYS} 天 (since {since[:10]})")
    print(f"成本假设: {ROUND_TRIP_COST_PCT*100:.2f}% notional 来回\n")

    # ── 一类:数据量 ─────────────────────────────────────────
    print("一类:数据量 (Sample Size)")
    auto = _auto_closed(conn, since)
    all_24h_check = _all_closed_since(conn, since)

    # A1: trial 已 ≥ 14 天
    if auto:
        first_entry = auto[0][7]
        days_since = (datetime.now(timezone.utc) - datetime.fromisoformat(first_entry.replace("Z", "+00:00"))).days
    else:
        days_since = 0
    print(fmt_gate("A1.", "trial 运行 ≥ 14 天", PASS if days_since >= 14 else FAIL,
                  f"({days_since} 天)"))

    # A2: 自动单 ≥ 100
    n_auto = len(auto)
    print(fmt_gate("A2.", "自动 v5_rsi_macd closed ≥ 100 笔", PASS if n_auto >= 100 else FAIL,
                  f"({n_auto})"))

    # A3: ≥ 2 个 setup_type 桶各 ≥ 30 笔 — 需要 reflection 表
    setup_counts = conn.execute("""
        SELECT setup_type, COUNT(*) FROM reflections
         WHERE created_at >= ?
         GROUP BY setup_type HAVING COUNT(*) >= 30
    """, (since,)).fetchall()
    print(fmt_gate("A3.", "≥ 2 个 setup_type 桶各 ≥ 30 笔",
                  PASS if len(setup_counts) >= 2 else FAIL,
                  f"({len(setup_counts)} 桶达标)"))

    # ── 二类:盈利能力 ────────────────────────────────────
    print("\n二类:盈利能力 (Profitability)")
    if not auto:
        for code, label in [("B1.", "毛 PnL > 0"), ("B2.", "净 PnL > 0"),
                            ("B3.", "净 PF ≥ 1.20"), ("B4.", "avg 净 PnL ≥ +0.05"),
                            ("B5.", "胜率 ≥ 42%")]:
            print(fmt_gate(code, label, SKIP, "(无自动单)"))
    else:
        gross_pnls = [(r[0] or 0) for r in auto]
        net_pnls = [net_pnl(r) for r in auto]

        # B1 毛
        gross_total = sum(gross_pnls)
        print(fmt_gate("B1.", "毛 PnL > 0", PASS if gross_total > 0 else FAIL,
                      f"({gross_total:+.2f} USDT)"))

        # B2 净
        net_total = sum(net_pnls)
        print(fmt_gate("B2.", "净 PnL > 0", PASS if net_total > 0 else FAIL,
                      f"({net_total:+.2f} USDT)"))

        # B3 净 PF
        net_pos = sum(p for p in net_pnls if p > 0)
        net_neg = -sum(p for p in net_pnls if p < 0)
        net_pf = (net_pos / net_neg) if net_neg > 0 else None
        if net_pf is None:
            print(fmt_gate("B3.", "净 PF ≥ 1.20", PASS, "(零亏损)"))
        else:
            print(fmt_gate("B3.", "净 PF ≥ 1.20",
                          PASS if net_pf >= 1.20 else FAIL,
                          f"({net_pf:.2f})"))

        # B4 avg 净
        net_avg = net_total / len(net_pnls)
        print(fmt_gate("B4.", "avg 净 PnL/笔 ≥ +0.05 USDT",
                      PASS if net_avg >= 0.05 else FAIL,
                      f"({net_avg:+.3f})"))

        # B5 胜率
        wins = sum(1 for p in gross_pnls if p > 0)
        wr = wins / len(gross_pnls)
        print(fmt_gate("B5.", "胜率 ≥ 42%",
                      PASS if wr >= 0.42 else FAIL,
                      f"({wr*100:.0f}%)"))

    # ── 三类:风险控制 ────────────────────────────────────
    print("\n三类:风险控制 (Risk Control)")
    if not auto:
        for code, label in [("C1.", "最大回撤 ≤ 30%"), ("C2.", "单笔亏损 ≤ 3%"),
                            ("C3.", "连续亏损 ≤ 8 笔"), ("C4.", "0 笔 OPEN_FAILED")]:
            print(fmt_gate(code, label, SKIP, "(无自动单)"))
    else:
        # C1 max drawdown
        cum, peak, mdd = calc_max_drawdown(gross_pnls)
        if peak > 0:
            dd_pct = abs(mdd) / peak * 100
            print(fmt_gate("C1.", "最大回撤 ≤ 30% of peak",
                          PASS if dd_pct <= 30 else FAIL,
                          f"({dd_pct:.0f}% · peak {peak:+.2f}, mdd {mdd:+.2f})"))
        else:
            print(fmt_gate("C1.", "最大回撤 ≤ 30% of peak", FAIL,
                          "(峰值 ≤ 0)"))

        # C2 单笔亏损 ≤ 3% 账户 (假设账户 1000 USDT)
        worst = min(gross_pnls)
        # 假设账户 1000 USDT, 3% = -30 USDT
        max_loss_per_trade_usdt = 30.0
        print(fmt_gate("C2.", "单笔亏损 ≤ 3% (≤ 30 USDT 假设账户 1000)",
                      PASS if worst >= -max_loss_per_trade_usdt else FAIL,
                      f"(worst {worst:+.2f})"))

        # C3 连续亏损
        max_streak = calc_longest_losing_streak(gross_pnls)
        print(fmt_gate("C3.", "最长连续亏损 ≤ 8 笔",
                      PASS if max_streak <= 8 else FAIL,
                      f"({max_streak} 连败)"))

    # C4 0 笔 OPEN_FAILED
    open_failed = conn.execute("""
        SELECT COUNT(*) FROM trade_scores_v5
         WHERE created_at >= ?
           AND block_reason LIKE 'OPEN_FAILED%'
    """, (since,)).fetchone()[0]
    print(fmt_gate("C4.", "0 笔 OPEN_FAILED",
                  PASS if open_failed == 0 else FAIL,
                  f"({open_failed})"))

    # ── 四类:系统行为 ────────────────────────────────────
    print("\n四类:系统行为 (Behavior Hygiene)")
    n_manual_close = conn.execute("""
        SELECT COUNT(*) FROM paper_trades
         WHERE entry_time >= ? AND exit_reason = 'MANUAL_USER'
    """, (since,)).fetchone()[0]
    print(fmt_gate("D1.", "0 笔 MANUAL_USER 平仓",
                  PASS if n_manual_close == 0 else FAIL,
                  f"({n_manual_close} 笔)"))

    n_manual_strat = conn.execute("""
        SELECT COUNT(*) FROM paper_trades
         WHERE entry_time >= ? AND strategy_id = 'v5_manual'
    """, (since,)).fetchone()[0]
    print(fmt_gate("D2.", "0 笔 v5_manual 策略",
                  PASS if n_manual_strat == 0 else FAIL,
                  f"({n_manual_strat} 笔)"))

    ai_calls = conn.execute("""
        SELECT COUNT(*), SUM(CASE WHEN ai_reasoning LIKE '%调用异常%' THEN 1 ELSE 0 END)
          FROM trade_scores_v5
         WHERE created_at >= ?
           AND (ai_reasoning IS NOT NULL OR block_reason='AI_REJECTED')
    """, (since,)).fetchone()
    total_ai, ai_failed = ai_calls
    if total_ai and total_ai > 0:
        fail_pct = (ai_failed or 0) / total_ai * 100
        print(fmt_gate("D3.", "AI 失败率 ≤ 5%",
                      PASS if fail_pct <= 5 else FAIL,
                      f"({fail_pct:.0f}% · {ai_failed}/{total_ai})"))
    else:
        print(fmt_gate("D3.", "AI 失败率 ≤ 5%", SKIP, "(0 AI 调用)"))

    n_unavail = conn.execute("""
        SELECT COUNT(*) FROM trade_scores_v5
         WHERE created_at >= ? AND block_reason = 'AI_UNAVAILABLE_LIVE_FAIL_CLOSED'
    """, (since,)).fetchone()[0]
    print(fmt_gate("D4.", "0 AI_UNAVAILABLE_LIVE_FAIL_CLOSED",
                  PASS if n_unavail == 0 else FAIL,
                  f"({n_unavail})"))

    print(fmt_gate("D5.", "trial 期间未改 v5_* 参数", SKIP,
                  "(手动确认 — 看 docker-compose.yml + system_settings 历史)"))

    # ── 五类:配置一致性 ────────────────────────────────────
    print("\n五类:配置一致性 (Config Consistency)")
    print("  这些需要人工确认 — 当前 env / system_settings 的值,跟你 trial 第 1 天的快照对比。")
    print("  E1-E7 都标 SKIP,执行人需要核对 docs/superpowers/notes/ 里 trial 启动时的配置快照。")
    for code, label in [
        ("E1.", "v5_funding_anti_pile_threshold"),
        ("E2.", "v5_trend_rsi_long_threshold"),
        ("E3.", "v5_sl_atr_mult / v5_tp_atr_mult"),
        ("E4.", "v5_risk_per_trade"),
        ("E5.", "v5_leverage"),
        ("E6.", "AI provider + model"),
        ("E7.", "MIN_VOLUME_24H_USDT"),
    ]:
        print(fmt_gate(code, label, SKIP, "(人工核对)"))

    # ── 六类:基础设施 ────────────────────────────────────
    print("\n六类:基础设施 (Infrastructure)")
    okx_key = os.environ.get("OKX_API_KEY", "")
    okx_sec = os.environ.get("OKX_API_SECRET", "")
    okx_pp = os.environ.get("OKX_API_PASSPHRASE", "")
    print(fmt_gate("F1.", "OKX key + secret + passphrase 全配置",
                  PASS if (okx_key and okx_sec and okx_pp) else FAIL,
                  f"(key={'Y' if okx_key else 'N'} sec={'Y' if okx_sec else 'N'} pp={'Y' if okx_pp else 'N'})"))

    for code, label in [
        ("F2.", "OKX fetch_balance 返回正常"),
        ("F3.", "enable_auto_trading=true"),
        ("F4.", "OKX 账户 USDT 余额 ≥ 100"),
        ("F5.", "OKX 杠杆设到 10x"),
        ("F6.", "OKX 0 个手动 position"),
        ("F7.", "已执行 LIVE+no-auto 30 分钟观察"),
    ]:
        print(fmt_gate(code, label, SKIP, "(人工 / 切 LIVE 当下确认)"))

    # ── 七类:认知准备 ────────────────────────────────────
    print("\n七类:认知准备 (Mental — 自己回答)")
    for code, label in [
        ("G1.", "我能接受 30% 回撤,不会去刷 K 线"),
        ("G2.", "我读完 backtest 持仓时间 18 倍水分报告"),
        ("G3.", "我承诺数据全部公开统计不挑好的看"),
        ("G4.", "LIVE 第 1 天亏 > 5% 我会立刻停"),
    ]:
        print(fmt_gate(code, label, SKIP, "(自我承诺)"))

    # ── 总结 ────────────────────────────────────
    print("\n=== 总结 ===")
    print("打满所有勾再切 LIVE。任何一个 ✗ 都是 STOP 信号。")
    print("缺哪条 → 改 / 等 / 重做 SHADOW。")
    print("\n下一步:跑 14 天后再来跑一次此脚本对照。")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
