"""
V4.2 AI 自动调优系统

功能：
- 定期自动运行 AI 调优
- 调优前验证当前配置的盈利情况
- 调优后验证新配置的盈利情况
- 只有在新配置确实更好时才应用
- 记录学习数据，用于持续改进
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta, date, timezone
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from supabase import create_client

# 添加 scripts 目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.ai_tuner import apply_tuning, load_strategy_config
from scripts.time_machine import replay_history, SimulationConfig, SimulationResult

load_dotenv()


class ProfitMetrics:
    """盈利指标"""
    def __init__(
        self,
        win_rate: float,
        avg_profit: float,
        total_trades: int,
        total_profit: float,
        max_drawdown: float,
        sharpe_ratio: float = 0.0,
    ):
        self.win_rate = win_rate
        self.avg_profit = avg_profit
        self.total_trades = total_trades
        self.total_profit = total_profit
        self.max_drawdown = max_drawdown
        self.sharpe_ratio = sharpe_ratio
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "win_rate": self.win_rate,
            "avg_profit": self.avg_profit,
            "total_trades": self.total_trades,
            "total_profit": self.total_profit,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
        }
    
    def __str__(self):
        return f"WinRate: {self.win_rate:.2%}, AvgProfit: {self.avg_profit:.4f}, Trades: {self.total_trades}, TotalProfit: {self.total_profit:.2f}"


def calculate_profit_metrics_from_paper_trades(
    supabase,
    days: int = 7,
    config_name: str = "current"
) -> Optional[ProfitMetrics]:
    """
    从 paper_trades 表计算盈利指标
    
    Args:
        supabase: Supabase 客户端
        days: 查询最近 N 天的数据
        config_name: 配置名称（用于标识）
    
    Returns:
        ProfitMetrics 或 None
    """
    try:
        from datetime import datetime, timedelta, timezone
        
        start_time = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        response = (
            supabase.table("paper_trades")
            .select("ret, pnl_usdt, status")
            .gte("created_at", start_time)
            .execute()
        )
        
        trades = response.data or []
        
        if not trades:
            return None
        
        # 计算指标
        returns = [float(t.get("ret", 0.0)) for t in trades]
        pnls = [float(t.get("pnl_usdt", 0.0)) for t in trades]
        
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]
        
        win_rate = len(wins) / len(returns) if returns else 0.0
        avg_profit = sum(returns) / len(returns) if returns else 0.0
        total_profit = sum(pnls)
        
        # 计算最大回撤（简化版）
        cumulative = []
        cumsum = 0.0
        for r in returns:
            cumsum += r
            cumulative.append(cumsum)
        
        max_drawdown = 0.0
        if cumulative:
            peak = cumulative[0]
            for val in cumulative:
                if val > peak:
                    peak = val
                drawdown = (peak - val) / (peak + 1e-6)  # 避免除零
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        
        return ProfitMetrics(
            win_rate=win_rate,
            avg_profit=avg_profit,
            total_trades=len(trades),
            total_profit=total_profit,
            max_drawdown=max_drawdown,
        )
    except Exception as e:
        print(f"[ERROR] 计算盈利指标失败: {e}")
        return None


def calculate_profit_metrics_from_time_machine(
    supabase,
    config: Dict[str, Any],
    days: int = 7
) -> Optional[ProfitMetrics]:
    """
    使用 Time Machine 模拟计算盈利指标
    
    Args:
        supabase: Supabase 客户端
        config: 策略配置
        days: 模拟最近 N 天的数据
    
    Returns:
        ProfitMetrics 或 None
    """
    try:
        from scripts.ai_tuner import prepare_tuning_data
        
        # 准备数据
        tuning_data = prepare_tuning_data(supabase, days=days)
        
        if tuning_data.get("data_points", 0) < 10:
            return None
        
        # 创建模拟配置
        sim_config = SimulationConfig(
            atr_multiplier_p2=config.get("atr_multiplier_p2", 2.5),
            atr_multiplier_p3a_early=config.get("atr_multiplier_p3a_early", 2.5),
            atr_multiplier_p3a_normal=config.get("atr_multiplier_p3a_normal", 2.0),
            atr_multiplier_p3b=config.get("atr_multiplier_p3b", 1.5),
            structure_gap_threshold=config.get("structure_gap_threshold", 0.02),
            phase_age_max_candles=config.get("phase_age_max_candles", 100),
        )
        
        # 运行模拟
        result: SimulationResult = replay_history(tuning_data["training_data"], sim_config)
        
        # 计算盈利指标（使用 SimulationResult 的统计属性）
        if result.total_trades == 0:
            return None
        
        # 使用 SimulationResult 已有的统计信息
        win_rate = result.win_rate
        avg_profit = result.avg_profit if result.winning_trades > 0 else 0.0
        total_profit = result.total_profit
        
        return ProfitMetrics(
            win_rate=win_rate,
            avg_profit=avg_profit,
            total_trades=result.total_trades,
            total_profit=total_profit,
            max_drawdown=result.max_drawdown,
        )
    except Exception as e:
        print(f"[ERROR] Time Machine 计算盈利指标失败: {e}")
        return None


def verify_profit_before_tuning(
    supabase,
    config: Dict[str, Any],
    method: str = "time_machine"  # "time_machine" 或 "paper_trades"
) -> Optional[ProfitMetrics]:
    """
    调优前验证当前配置的盈利情况
    
    Args:
        supabase: Supabase 客户端
        config: 当前策略配置
        method: 验证方法
    
    Returns:
        ProfitMetrics 或 None
    """
    if method == "paper_trades":
        return calculate_profit_metrics_from_paper_trades(supabase, days=7)
    else:
        return calculate_profit_metrics_from_time_machine(supabase, config, days=7)


def compare_metrics(
    old_metrics: ProfitMetrics,
    new_metrics: ProfitMetrics
) -> Dict[str, Any]:
    """
    比较两个配置的盈利指标
    
    Returns:
        比较结果字典
    """
    win_rate_improvement = new_metrics.win_rate - old_metrics.win_rate
    profit_improvement = new_metrics.total_profit - old_metrics.total_profit
    drawdown_change = new_metrics.max_drawdown - old_metrics.max_drawdown
    
    # 综合评分（可以调整权重）
    score_old = (
        old_metrics.win_rate * 0.3 +
        (old_metrics.total_profit / max(old_metrics.total_trades, 1)) * 0.5 -
        old_metrics.max_drawdown * 0.2
    )
    score_new = (
        new_metrics.win_rate * 0.3 +
        (new_metrics.total_profit / max(new_metrics.total_trades, 1)) * 0.5 -
        new_metrics.max_drawdown * 0.2
    )
    
    is_better = score_new > score_old
    
    return {
        "is_better": is_better,
        "score_old": score_old,
        "score_new": score_new,
        "win_rate_improvement": win_rate_improvement,
        "profit_improvement": profit_improvement,
        "drawdown_change": drawdown_change,
        "improvement_pct": ((score_new - score_old) / abs(score_old) * 100) if score_old != 0 else 0.0,
    }


def run_auto_tuning_with_verification(
    supabase,
    config_path: str = "strategy_config.json",
    verification_method: str = "time_machine",
    min_improvement_pct: float = 1.0  # 最小改进百分比
) -> Dict[str, Any]:
    """
    运行自动调优（带盈利验证）
    
    Args:
        supabase: Supabase 客户端
        config_path: 配置文件路径
        verification_method: 验证方法
        min_improvement_pct: 最小改进百分比（低于此值不应用）
    
    Returns:
        调优结果字典
    """
    print("=" * 60)
    print("🚀 开始自动 AI 调优（带盈利验证）")
    print("=" * 60)
    
    # 1. 加载当前配置
    current_config = load_strategy_config(config_path)
    print(f"📋 当前配置: {json.dumps(current_config, indent=2, ensure_ascii=False)}")
    
    # 2. 验证当前配置的盈利情况
    print("\n📊 验证当前配置的盈利情况...")
    current_metrics = verify_profit_before_tuning(supabase, current_config, verification_method)
    
    if not current_metrics:
        return {
            "success": False,
            "reason": "无法验证当前配置的盈利情况（数据不足）",
        }
    
    print(f"✅ 当前配置指标: {current_metrics}")
    
    # 3. 运行 AI 调优
    print("\n🤖 运行 AI 调优...")
    tuning_result = apply_tuning(supabase, config_path)
    
    if not tuning_result.get("success"):
        return {
            "success": False,
            "reason": f"AI 调优失败: {tuning_result.get('reason', '未知错误')}",
            "current_metrics": current_metrics.to_dict(),
        }
    
    new_config = tuning_result.get("new_config")
    if not new_config:
        return {
            "success": False,
            "reason": "AI 调优未返回新配置",
            "current_metrics": current_metrics.to_dict(),
        }
    
    # 4. 验证新配置的盈利情况
    print("\n📊 验证新配置的盈利情况...")
    new_metrics = verify_profit_before_tuning(supabase, new_config, verification_method)
    
    if not new_metrics:
        return {
            "success": False,
            "reason": "无法验证新配置的盈利情况（数据不足）",
            "current_metrics": current_metrics.to_dict(),
            "tuning_result": tuning_result,
        }
    
    print(f"✅ 新配置指标: {new_metrics}")
    
    # 5. 比较两个配置
    print("\n📈 比较配置...")
    comparison = compare_metrics(current_metrics, new_metrics)
    
    print(f"当前配置评分: {comparison['score_old']:.4f}")
    print(f"新配置评分: {comparison['score_new']:.4f}")
    print(f"改进: {comparison['improvement_pct']:.2f}%")
    print(f"胜率改进: {comparison['win_rate_improvement']:.2%}")
    print(f"盈利改进: {comparison['profit_improvement']:.2f} USDT")
    
    # 6. 决定是否应用
    should_apply = (
        comparison["is_better"] and
        comparison["improvement_pct"] >= min_improvement_pct
    )
    
    if should_apply:
        print(f"\n✅ 新配置更好（改进 {comparison['improvement_pct']:.2f}%），将应用新配置")
        # 如果新配置更好，应用它
        from scripts.ai_tuner import save_strategy_config
        save_strategy_config(new_config, config_path)
        print("📝 新配置已保存到 strategy_config.json")
    else:
        print(f"\n❌ 新配置未达到改进阈值（需要至少 {min_improvement_pct}%，实际 {comparison['improvement_pct']:.2f}%），不应用")
    
    # 7. 记录学习数据
    learning_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_config": current_config,
        "new_config": new_config,
        "current_metrics": current_metrics.to_dict(),
        "new_metrics": new_metrics.to_dict(),
        "comparison": comparison,
        "applied": should_apply,
        "verification_method": verification_method,
    }
    
    # 保存学习数据到数据库
    try:
        supabase.table("ai_learning_logs").insert({
            "created_at": learning_data["timestamp"],
            "data": json.dumps(learning_data, ensure_ascii=False),
        }).execute()
        print("✅ 学习数据已保存到数据库")
    except Exception as e:
        print(f"[WARNING] 保存学习数据失败: {e}")
        # 如果表不存在，创建本地文件备份
        try:
            os.makedirs("logs", exist_ok=True)
            with open(f"logs/ai_learning_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w", encoding="utf-8") as f:
                json.dump(learning_data, f, indent=2, ensure_ascii=False)
            print("✅ 学习数据已保存到本地文件")
        except Exception as e2:
            print(f"[ERROR] 保存学习数据到本地文件也失败: {e2}")
    
    return {
        "success": True,
        "current_metrics": current_metrics.to_dict(),
        "new_metrics": new_metrics.to_dict(),
        "comparison": comparison,
        "should_apply": should_apply,
        "tuning_result": tuning_result,
        "learning_data": learning_data,
    }


if __name__ == "__main__":
    # 测试运行
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        print("❌ 未配置 Supabase")
        exit(1)
    
    supabase = create_client(supabase_url, supabase_key)
    
    result = run_auto_tuning_with_verification(
        supabase,
        verification_method="time_machine",
        min_improvement_pct=1.0
    )
    
    if result.get("success"):
        print("\n✅ 自动调优完成")
        if result.get("should_apply"):
            print("📝 新配置已应用")
        else:
            print("⚠️  新配置未应用（未达到改进阈值）")
    else:
        print(f"\n❌ 自动调优失败: {result.get('reason')}")

