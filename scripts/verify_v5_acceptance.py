"""V5 SHADOW 24h 验收 — 跑完打印通过/不通过。

用法:
    python scripts/verify_v5_acceptance.py
    # 或在容器内:
    docker compose exec -T collector python /app/scripts/verify_v5_acceptance.py

退出码:
    0 = 所有硬性检查通过
    1 = 任一硬性检查失败(评分流停滞 / 0 笔 paper trade / AI 拒绝率 >90%)

KPI 项(胜率/PnL/平均持仓)只打印不阻塞,因为它取决于行情,不能作为
功能验收硬性标准。要看决策质量是否达标,改用 KPI 阈值另起一道闸。
"""
from __future__ import annotations

import os
import sqlite3
import sys


def verify(db_path: str = "data/rabbit_hunter.db") -> bool:
    conn = sqlite3.connect(db_path)
    try:
        # 1. 过去 24h 至少 50 笔 trade_scores_v5
        n_scores = conn.execute(
            "SELECT COUNT(*) FROM trade_scores_v5 "
            "WHERE created_at >= datetime('now', '-24 hour')"
        ).fetchone()[0]
        print(f"24h trade_scores_v5: {n_scores}  (要求 ≥ 50)")
        passed_scores = n_scores >= 50

        # 2. 过去 24h 至少 1 笔 paper_trades 处于 OPEN 或最近平仓
        n_open = conn.execute(
            "SELECT COUNT(*) FROM paper_trades "
            "WHERE status='OPEN' AND strategy_id='v5_rsi_macd'"
        ).fetchone()[0]
        n_closed = conn.execute(
            "SELECT COUNT(*) FROM paper_trades "
            "WHERE status='CLOSED' AND strategy_id='v5_rsi_macd' "
            "  AND exit_time >= datetime('now', '-24 hour')"
        ).fetchone()[0]
        print(f"24h paper_trades OPEN: {n_open}  CLOSED: {n_closed}  (要求 ≥ 1)")
        passed_trades = (n_open + n_closed) >= 1

        # 3. 拦截分布(可观察项,不阻塞验收)
        rows = conn.execute(
            "SELECT block_reason, COUNT(*) FROM trade_scores_v5 "
            "WHERE created_at >= datetime('now', '-24 hour') "
            "GROUP BY block_reason ORDER BY 2 DESC LIMIT 10"
        ).fetchall()
        print("\n拦截分布(过去 24h):")
        for br, cnt in rows:
            print(f"  {str(br):40s} = {cnt}")

        # 4. AI 拒绝率
        n_ai_rejected = sum(c for r, c in rows if r == "AI_REJECTED")
        ratio = n_ai_rejected / n_scores if n_scores else 0
        print(f"\nAI 拒绝率: {ratio*100:.1f}%  (要求 ≤ 90%)")
        passed_ai = ratio <= 0.90

        # 5. paper KPI(纯观察项,不影响 pass/fail)
        kpi = conn.execute("""
            SELECT
              COUNT(*) as total,
              SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
              SUM(pnl) as total_pnl,
              AVG(holding_hours * 60) as avg_hold_min
            FROM paper_trades
            WHERE status='CLOSED' AND strategy_id='v5_rsi_macd'
              AND exit_time >= datetime('now', '-24 hour')
        """).fetchone()
        total, wins, total_pnl, avg_hold = kpi
        if total:
            wins = wins or 0
            total_pnl = total_pnl or 0.0
            avg_hold = avg_hold or 0.0
            print(
                f"\nKPI: 总笔 {total}, 胜 {wins} ({wins/total*100:.1f}%), "
                f"PnL {total_pnl:.2f} USDT, 平均持仓 {avg_hold:.1f} 分钟"
            )

        all_passed = passed_scores and passed_trades and passed_ai
        print("\n" + ("✅ 验收通过" if all_passed else "❌ 验收未通过"))
        return all_passed
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = os.environ.get("DB_PATH", "data/rabbit_hunter.db")
    ok = verify(db_path)
    sys.exit(0 if ok else 1)
