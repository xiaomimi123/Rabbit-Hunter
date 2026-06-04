"""
持仓统计和报告生成模块

功能：
1. 生成持仓统计报告
2. 计算总盈亏、风险分布等
3. 导出报告（JSON/CSV）
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client, Client

# 载入环境变量
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def init_supabase() -> Optional[Client]:
    """初始化 Supabase 客户端。"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    try:
        client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return client
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] Supabase 初始化失败: {e}")
        return None


def get_position_statistics(supabase: Client, symbol: Optional[str] = None, days: int = 7) -> dict:
    """
    获取持仓统计信息
    
    Args:
        supabase: Supabase 客户端
        symbol: 币种（可选，None 表示所有币种）
        days: 统计天数（默认 7 天）
    
    Returns:
        统计信息字典
    """
    try:
        # 计算时间范围
        start_time = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # 构建查询
        query = (
            supabase.table("position_history")
            .select("*")
            .gte("created_at", start_time)
        )

        if symbol:
            query = query.eq("symbol", symbol)

        response = query.order("created_at", desc=False).execute()

        if not response.data:
            return {
                "total_records": 0,
                "symbols": [],
                "total_unrealized_pnl": 0,
                "risk_distribution": {},
            }

        records = response.data

        # 统计信息
        symbols = list(set(r["symbol"] for r in records))
        total_unrealized_pnl = sum(float(r.get("unrealized_pnl", 0) or 0) for r in records)

        # 风险分布
        risk_distribution = {
            "SAFE": 0,
            "WARNING": 0,
            "DANGER": 0,
            "UNKNOWN": 0,
        }
        for r in records:
            risk_level = r.get("market_risk_level", "UNKNOWN")
            risk_distribution[risk_level] = risk_distribution.get(risk_level, 0) + 1

        # 按币种统计
        symbol_stats = {}
        for sym in symbols:
            sym_records = [r for r in records if r["symbol"] == sym]
            if sym_records:
                latest = sym_records[-1]  # 最新记录
                symbol_stats[sym] = {
                    "total_snapshots": len(sym_records),
                    "latest_size": float(latest.get("size", 0)),
                    "latest_entry_price": float(latest.get("entry_price", 0)),
                    "latest_pnl": float(latest.get("unrealized_pnl", 0) or 0),
                    "latest_risk_level": latest.get("market_risk_level", "UNKNOWN"),
                    "latest_risk_score": latest.get("market_risk_score", 0),
                    "avg_pnl": sum(float(r.get("unrealized_pnl", 0) or 0) for r in sym_records) / len(sym_records),
                }

        return {
            "total_records": len(records),
            "symbols": symbols,
            "symbol_count": len(symbols),
            "total_unrealized_pnl": total_unrealized_pnl,
            "risk_distribution": risk_distribution,
            "symbol_stats": symbol_stats,
            "period_days": days,
            "start_time": start_time,
            "end_time": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] 获取持仓统计失败: {e}")
        return {}


def get_risk_alerts_summary(supabase: Client, days: int = 7, resolved: bool = False) -> dict:
    """
    获取风险警报摘要
    
    Args:
        supabase: Supabase 客户端
        days: 统计天数
        resolved: 是否只查询已解决的警报
    
    Returns:
        警报摘要字典
    """
    try:
        start_time = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        query = (
            supabase.table("position_risk_alerts")
            .select("*")
            .gte("created_at", start_time)
        )

        if resolved:
            query = query.eq("is_resolved", True)
        else:
            query = query.eq("is_resolved", False)

        response = query.order("created_at", desc=True).execute()

        if not response.data:
            return {
                "total_alerts": 0,
                "by_level": {},
                "by_type": {},
                "alerts": [],
            }

        alerts = response.data

        # 按级别统计
        by_level = {}
        for alert in alerts:
            level = alert.get("alert_level", "UNKNOWN")
            by_level[level] = by_level.get(level, 0) + 1

        # 按类型统计
        by_type = {}
        for alert in alerts:
            alert_type = alert.get("alert_type", "UNKNOWN")
            by_type[alert_type] = by_type.get(alert_type, 0) + 1

        return {
            "total_alerts": len(alerts),
            "by_level": by_level,
            "by_type": by_type,
            "alerts": alerts[:20],  # 只返回最近 20 条
        }

    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] 获取风险警报摘要失败: {e}")
        return {}


def generate_report(supabase: Client, days: int = 7) -> dict:
    """
    生成完整的持仓分析报告
    
    Args:
        supabase: Supabase 客户端
        days: 统计天数
    
    Returns:
        完整报告字典
    """
    stats = get_position_statistics(supabase, days=days)
    alerts = get_risk_alerts_summary(supabase, days=days, resolved=False)

    report = {
        "report_time": datetime.now(timezone.utc).isoformat(),
        "period_days": days,
        "statistics": stats,
        "risk_alerts": alerts,
        "summary": {
            "total_positions": stats.get("symbol_count", 0),
            "total_unrealized_pnl": stats.get("total_unrealized_pnl", 0),
            "active_alerts": alerts.get("total_alerts", 0),
            "risk_distribution": stats.get("risk_distribution", {}),
        },
    }

    return report


def print_report(report: dict) -> None:
    """打印报告到控制台"""
    print("\n" + "=" * 60)
    print("📊 Rabbit Hunter 持仓分析报告")
    print("=" * 60)

    summary = report.get("summary", {})
    print(f"\n📈 持仓概览（最近 {report.get('period_days', 7)} 天）")
    print(f"   持仓币种数: {summary.get('total_positions', 0)}")
    print(f"   总未实现盈亏: {summary.get('total_unrealized_pnl', 0):.2f} USDT")

    risk_dist = summary.get("risk_distribution", {})
    print(f"\n⚠️ 风险分布")
    print(f"   SAFE: {risk_dist.get('SAFE', 0)} 条记录")
    print(f"   WARNING: {risk_dist.get('WARNING', 0)} 条记录")
    print(f"   DANGER: {risk_dist.get('DANGER', 0)} 条记录")

    alerts = report.get("risk_alerts", {})
    print(f"\n🚨 风险警报")
    print(f"   活跃警报数: {alerts.get('total_alerts', 0)}")
    if alerts.get("by_level"):
        print("   按级别分布:")
        for level, count in alerts["by_level"].items():
            print(f"     {level}: {count}")

    symbol_stats = report.get("statistics", {}).get("symbol_stats", {})
    if symbol_stats:
        print(f"\n💰 币种详情")
        for symbol, stats in symbol_stats.items():
            print(f"   {symbol}:")
            print(f"     持仓数量: {stats['latest_size']:.4f}")
            print(f"     开仓价格: {stats['latest_entry_price']:.4f}")
            print(f"     当前盈亏: {stats['latest_pnl']:.2f} USDT")
            print(f"     风险等级: {stats['latest_risk_level']}")
            print(f"     风险评分: {stats['latest_risk_score']}")

    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    # 测试代码
    print("生成持仓分析报告...")
    supabase = init_supabase()
    if supabase:
        report = generate_report(supabase, days=7)
        print_report(report)
    else:
        print("[ERROR] 无法连接 Supabase")

