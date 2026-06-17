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


def verify_plan_b_backend(db_path: str = "data/rabbit_hunter.db") -> bool:
    conn = sqlite3.connect(db_path)
    try:
        print("\n=== Plan B-1 后端 ===")
        try:
            n_settings = conn.execute(
                "SELECT COUNT(*) FROM system_settings WHERE key LIKE 'v5_%'"
            ).fetchone()[0]
            print(f"system_settings v5_* keys: {n_settings}")
        except Exception as e:
            print(f"system_settings 检查失败: {e}")
            return False

        try:
            conn.execute("SELECT COUNT(*) FROM ws_event_queue").fetchone()
            print("ws_event_queue table OK")
        except Exception as e:
            print(f"ws_event_queue 不存在: {e}")
            return False

        n_manual = conn.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE strategy_id='v5_manual'"
        ).fetchone()[0]
        print(f"v5_manual paper_trades: {n_manual}(可选指标)")

        try:
            n_rag = conn.execute(
                "SELECT COUNT(*) FROM ai_training_data WHERE outcome IS NOT NULL"
            ).fetchone()[0]
            print(f"ai_training_data 已平仓: {n_rag}(冷启动 < 10)")
        except Exception:
            # ai_training_data 可能还没建表 — 这是冷启动条件,不算失败
            print(f"ai_training_data 尚未创建(冷启动)")

        print("\n✅ Plan B-1 后端结构验收通过")
        return True
    finally:
        conn.close()


def verify_plan_b_frontend(repo_root: str = "/app") -> bool:
    """Frontend build artifact check. Looks for dist/index.html after vite build."""
    print("\n=== Plan B-2 前端 ===")
    candidates = [
        os.path.join(repo_root, "Rabbit Hunterfronted", "dist", "index.html"),
        os.path.join(os.path.dirname(repo_root), "Rabbit Hunterfronted", "dist", "index.html"),
        "/Users/lizhishaoniange/Documents/Rabbit-Hunter/Rabbit Hunterfronted/dist/index.html",
    ]
    for path in candidates:
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"frontend dist/index.html OK ({size} bytes) at {path}")
            return True
    print(f"frontend dist/index.html 不存在 — 跑过 vite build 了吗?候选: {candidates}")
    return False


def verify_reflection_phase_1_3(db_path: str = "data/rabbit_hunter.db") -> bool:
    import os, sqlite3
    print("\n=== Reflection Worker (Phases 1-3) ===")
    if not os.path.exists(db_path):
        print(f"db not found: {db_path}")
        return False
    conn = sqlite3.connect(db_path)
    try:
        for table in ("reflection_queue", "reflections", "failure_taxonomy",
                      "setup_performance_daily", "position_sizing_recommendations",
                      "ai_confidence_calibration"):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"  {table}: {n} rows")
            except sqlite3.OperationalError as e:
                print(f"  {table}: MISSING ({e})")
                return False

        n_seeds = conn.execute(
            "SELECT COUNT(*) FROM failure_taxonomy WHERE seeded=1"
        ).fetchone()[0]
        if n_seeds != 8:
            print(f"  expected 8 seeded failure modes, got {n_seeds}")
            return False
        print(f"  ✓ 8 seeded failure_taxonomy modes present")

        print("\n✅ Reflection Phases 1-3 schema verification passed")
        return True
    finally:
        conn.close()


def verify_v6_funding_phase_1_6(db_path: str = "data/rabbit_hunter.db") -> bool:
    import os, sqlite3
    print("\n=== V6 Funding Rate (Phases 1-6) ===")
    if not os.path.exists(db_path):
        print(f"db not found: {db_path}")
        return False
    conn = sqlite3.connect(db_path)
    try:
        # Tables present
        for table in ("funding_rates", "funding_zscore_cache"):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"  {table}: {n} rows")
            except sqlite3.OperationalError as e:
                print(f"  {table}: MISSING ({e})")
                return False

        # Columns added to existing tables
        for tbl, col in (
            ("trade_scores_v5", "funding_z_score"),
            ("trade_scores_v5", "funding_rate_8h"),
            ("reflections", "funding_z_score_at_entry"),
            ("reflections", "funding_rate_at_entry"),
        ):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
            if col not in cols:
                print(f"  {tbl}.{col} MISSING")
                return False
        print("  ✓ all funding columns present in trade_scores_v5 + reflections")
        print("\n✅ V6 Funding Phases 1-6 schema verification passed")
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    db = os.environ.get("DB_PATH", "data/rabbit_hunter.db")
    ok_a = verify(db)
    ok_b = verify_plan_b_backend(db)
    ok_c = verify_plan_b_frontend()
    ok_d = verify_reflection_phase_1_3(db)
    ok_e = verify_v6_funding_phase_1_6(db)
    sys.exit(0 if (ok_a and ok_b and ok_c and ok_d and ok_e) else 1)
