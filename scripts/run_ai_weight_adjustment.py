"""
AI 权重调整定时任务

定期调用 AI 进行权重调整，并保存到数据库
可以手动运行或作为定时任务运行
"""

import os
import sys
from datetime import datetime, timedelta, date, timezone
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

load_dotenv()

try:
    from supabase import create_client, Client
    from v43_weight_manager import load_weights
    from v43_deepseek_constrained import DeepSeekConstrained
    from v43_weight_history_helper import save_weight_adjustment_to_database
    from v43_opportunity_density import (
        calculate_opportunity_density_score,
        calculate_trades_per_week,
        calculate_average_expectancy,
    )
except ImportError as e:
    print(f"[ERROR] 无法导入模块: {e}")
    sys.exit(1)

# 初始化 Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[ERROR] Supabase 配置缺失")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def calculate_performance_metrics(days: int = 7) -> dict:
    """
    从数据库计算性能指标
    
    Args:
        days: 统计天数（默认 7 天）
    
    Returns:
        performance_metrics: 性能指标字典
    """
    try:
        # 计算时间范围
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        # 查询已执行的交易（从 trade_scores_v43 或 paper_trades）
        # 优先使用 paper_trades（如果有实际交易记录）
        try:
            trades_response = (
                supabase.table("paper_trades")
                .select("entry_time, exit_time, pnl_usdt, ret, status")
                .gte("entry_time", cutoff_date)
                .eq("status", "CLOSED")
                .execute()
            )
            trades = trades_response.data or []
        except Exception:
            # 如果没有 paper_trades，使用 trade_scores_v43 中已执行的记录
            try:
                scores_response = (
                    supabase.table("trade_scores_v43")
                    .select("created_at, executed, final_score")
                    .gte("created_at", cutoff_date)
                    .eq("executed", True)
                    .execute()
                )
                trades = scores_response.data or []
            except Exception:
                trades = []
        
        if not trades:
            # 如果没有交易记录，返回默认值
            return {
                "win_rate": 0.5,
                "avg_profit": 0.0,
                "total_trades": 0,
                "profit_factor": 1.0,
                "max_drawdown": 0.0,
            }
        
        # 计算胜率
        wins = [t for t in trades if (t.get("pnl_usdt") or t.get("ret") or 0) > 0]
        win_rate = len(wins) / len(trades) if trades else 0.0
        
        # 计算平均收益
        profits = []
        for trade in trades:
            pnl = trade.get("pnl_usdt") or trade.get("ret") or 0
            if pnl:
                profits.append(float(pnl))
        
        avg_profit = sum(profits) / len(profits) if profits else 0.0
        
        # 计算盈亏比（简化版）
        winning_profits = [p for p in profits if p > 0]
        losing_profits = [abs(p) for p in profits if p < 0]
        profit_factor = (
            sum(winning_profits) / sum(losing_profits)
            if losing_profits and sum(losing_profits) > 0
            else 1.0
        )
        
        # 计算最大回撤（简化版）
        if profits:
            cumulative = []
            cumsum = 0.0
            for p in profits:
                cumsum += p
                cumulative.append(cumsum)
            peak = max(cumulative) if cumulative else 0.0
            max_drawdown = abs(min([c - peak for c in cumulative])) if cumulative else 0.0
        else:
            max_drawdown = 0.0
        
        return {
            "win_rate": win_rate,
            "avg_profit": avg_profit,
            "total_trades": len(trades),
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
        }
    except Exception as e:
        print(f"[WARNING] 计算性能指标失败: {e}")
        return {
            "win_rate": 0.5,
            "avg_profit": 0.0,
            "total_trades": 0,
            "profit_factor": 1.0,
            "max_drawdown": 0.0,
        }


def calculate_opportunity_density(days: int = 7) -> float:
    """
    计算机会密度分数
    
    Args:
        days: 统计天数（默认 7 天）
    
    Returns:
        opportunity_density_score: 机会密度分数 (0-1)
    """
    try:
        # 计算时间范围
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        # 查询交易记录
        try:
            trades_response = (
                supabase.table("paper_trades")
                .select("entry_time, pnl_usdt, ret")
                .gte("entry_time", cutoff_date)
                .execute()
            )
            trades = trades_response.data or []
        except Exception:
            trades = []
        
        # 计算每周交易次数
        trades_per_week = calculate_trades_per_week(trades, days=days)
        
        # 计算平均期望收益
        average_expectancy = calculate_average_expectancy(trades)
        
        # 计算性能指标
        performance_metrics = calculate_performance_metrics(days=days)
        
        # 计算机会密度分数
        ods = calculate_opportunity_density_score(
            trades_per_week=trades_per_week,
            average_expectancy=average_expectancy,
            recent_performance={
                "win_rate": performance_metrics["win_rate"],
                "profit_factor": performance_metrics["profit_factor"],
            },
        )
        
        return ods
    except Exception as e:
        print(f"[WARNING] 计算机会密度分数失败: {e}")
        return 0.5  # 默认值


def run_weight_adjustment(force: bool = False) -> bool:
    """
    运行 AI 权重调整
    
    Args:
        force: 是否强制运行（即使最近已调整过）
    
    Returns:
        success: 是否成功
    """
    print("=" * 60)
    print("AI 权重调整任务")
    print("=" * 60)
    print()
    
    # 1. 检查是否最近已调整过（避免频繁调整）
    if not force:
        try:
            recent_response = (
                supabase.table("ai_weights_v43")
                .select("created_at")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            
            if recent_response.data:
                last_adjustment = recent_response.data[0].get("created_at")
                if last_adjustment:
                    last_time = datetime.fromisoformat(last_adjustment.replace("Z", "+00:00"))
                    hours_since = (datetime.now(last_time.tzinfo) - last_time).total_seconds() / 3600
                    
                    if hours_since < 6:  # 6 小时内不重复调整
                        print(f"⚠️  最近 {hours_since:.1f} 小时前已调整过，跳过")
                        print("   使用 --force 参数强制运行")
                        return False
        except Exception as e:
            print(f"[WARNING] 检查最近调整时间失败: {e}")
    
    # 2. 加载当前权重
    print("1. 加载当前权重配置")
    print("-" * 60)
    current_weights = load_weights()
    print(f"   当前权重: {current_weights}")
    print()
    
    # 3. 计算性能指标
    print("2. 计算性能指标（最近 7 天）")
    print("-" * 60)
    performance_metrics = calculate_performance_metrics(days=7)
    print(f"   胜率: {performance_metrics['win_rate']*100:.1f}%")
    print(f"   平均收益: {performance_metrics['avg_profit']:.4f}")
    print(f"   交易次数: {performance_metrics['total_trades']}")
    print(f"   盈亏比: {performance_metrics['profit_factor']:.2f}")
    print()
    
    # 4. 计算机会密度分数
    print("3. 计算机会密度分数")
    print("-" * 60)
    opportunity_density_score = calculate_opportunity_density(days=7)
    print(f"   机会密度分数: {opportunity_density_score:.2f}")
    print()
    
    # 5. 初始化 AI
    print("4. 初始化 DeepSeek AI")
    print("-" * 60)
    ai = DeepSeekConstrained(debug=True)
    
    if not ai.is_ready():
        print("   ❌ DeepSeek API Key 未配置（DEEPSEEK_API_KEY）")
        print("   无法进行 AI 权重调整")
        return False
    
    print("   ✅ DeepSeek AI 已就绪")
    print()
    
    # 6. AI 调整权重
    print("5. AI 调整权重")
    print("-" * 60)
    adjustment = ai.adjust_weights(
        current_weights=current_weights,
        performance_metrics=performance_metrics,
        opportunity_density_score=opportunity_density_score,
    )
    
    if not adjustment:
        print("   ❌ AI 调整失败")
        return False
    
    print(f"   ✅ AI 调整成功: {adjustment.version}")
    print(f"   新权重: {adjustment.new_weights}")
    print(f"   调整理由: {adjustment.reasoning[:100]}...")
    print()
    
    # 7. 保存到数据库
    print("6. 保存权重调整到数据库")
    print("-" * 60)
    success = save_weight_adjustment_to_database(
        adjustment=adjustment,
        performance_metrics=performance_metrics,
        opportunity_density_score=opportunity_density_score,
        applied=False,  # 先保存为未应用，然后自动应用
        supabase=supabase,
    )
    
    if not success:
        print("   ❌ 权重调整保存失败")
        return False
    
    print(f"   ✅ 权重调整已保存: {adjustment.version}")
    print()
    
    # 8. 自动应用权重调整
    print("7. 自动应用权重调整")
    print("-" * 60)
    try:
        from v43_weight_manager import save_weights
        
        # 应用权重（保存到配置文件）
        apply_success = save_weights(
            weights=adjustment.new_weights,
            save_to_database=False,  # 已经保存过了，不再重复保存
        )
        
        if apply_success:
            # 更新数据库中的 applied 状态
            try:
                # 获取刚保存的权重记录 ID
                recent_response = (
                    supabase.table("ai_weights_v43")
                    .select("id")
                    .eq("weights_version", adjustment.version)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                
                if recent_response.data:
                    weight_id = recent_response.data[0].get("id")
                    # 将所有其他权重配置标记为未应用
                    supabase.table("ai_weights_v43").update({"applied": False}).neq("id", weight_id).execute()
                    # 将当前权重配置标记为已应用
                    supabase.table("ai_weights_v43").update({"applied": True}).eq("id", weight_id).execute()
                    
                    print(f"   ✅ 权重调整已自动应用: {adjustment.version}")
                    print(f"   📝 新权重: {adjustment.new_weights}")
                    print()
                    
                    # 9. 发送通知
                    print("8. 发送通知")
                    print("-" * 60)
                    try:
                        # 保存通知到数据库（用于前端显示）
                        notification = {
                            "type": "WEIGHT_ADJUSTMENT_APPLIED",
                            "title": "权重调整已自动应用",
                            "message": f"AI 权重调整 {adjustment.version} 已自动应用。新权重: {adjustment.new_weights}",
                            "data": {
                                "weights_version": adjustment.version,
                                "new_weights": adjustment.new_weights,
                                "reasoning": adjustment.reasoning[:200],  # 截取前200字符
                                "performance_metrics": performance_metrics,
                            },
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                        
                        # 尝试保存到通知表（如果表存在）
                        try:
                            supabase.table("notifications").insert(notification).execute()
                            print("   ✅ 通知已保存到数据库")
                        except Exception:
                            # 如果通知表不存在，只打印日志
                            print("   ⚠️  通知表不存在，仅打印日志")
                            print(f"   📢 通知: {notification['title']} - {notification['message']}")
                    except Exception as e:
                        print(f"   ⚠️  发送通知失败: {e}")
                        # 即使通知失败，也不影响主流程
                    
                    print()
                    print("=" * 60)
                    print("✅ 权重调整任务完成（已自动应用）")
                    print("=" * 60)
                    print()
                    print("📊 调整摘要:")
                    print(f"   - 版本: {adjustment.version}")
                    print(f"   - 新权重: {adjustment.new_weights}")
                    print(f"   - 调整理由: {adjustment.reasoning[:100]}...")
                    print(f"   - 性能指标: 胜率={performance_metrics.get('win_rate', 0)*100:.1f}%, 交易数={performance_metrics.get('total_trades', 0)}")
                    print()
                    return True
                else:
                    print("   ⚠️  无法找到权重记录，跳过数据库更新")
                    return True  # 文件已保存，仍然算成功
            except Exception as e:
                print(f"   ⚠️  更新数据库状态失败: {e}")
                print("   ✅ 但权重已保存到配置文件，仍然生效")
                return True  # 文件已保存，仍然算成功
        else:
            print("   ❌ 应用权重失败")
            return False
    except Exception as e:
        print(f"   ❌ 自动应用失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="AI 权重调整定时任务")
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制运行（即使最近已调整过）",
    )
    
    args = parser.parse_args()
    
    success = run_weight_adjustment(force=args.force)
    sys.exit(0 if success else 1)

