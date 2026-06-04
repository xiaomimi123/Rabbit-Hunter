"""
V4.3 权重历史辅助函数

提供便捷函数，用于在 AI 权重调整后保存到数据库
"""

from typing import Dict, Any, Optional
from v43_weight_manager import save_weights_to_database
from v43_deepseek_constrained import WeightAdjustment, DailyReport


def save_weight_adjustment_to_database(
    adjustment: WeightAdjustment,
    performance_metrics: Optional[Dict[str, Any]] = None,
    opportunity_density_score: Optional[float] = None,
    applied: bool = False,
    supabase: Optional[Any] = None,
) -> bool:
    """
    保存权重调整到数据库
    
    Args:
        adjustment: WeightAdjustment 对象
        performance_metrics: 性能指标（可选）
        opportunity_density_score: 机会密度分数（可选，如果为 None 则从 adjustment 中提取）
        applied: 是否已应用
        supabase: Supabase 客户端（可选）
    
    Returns:
        success: 是否成功
    """
    return save_weights_to_database(
        weights=adjustment.new_weights,
        weights_version=adjustment.version,
        performance_metrics=performance_metrics,
        opportunity_density_score=opportunity_density_score or (getattr(adjustment, 'opportunity_density_score', None)),
        ai_reason=adjustment.reasoning,
        applied=applied,
        supabase=supabase,
    )


def save_daily_report_to_database(
    report: DailyReport,
    supabase: Optional[Any] = None,
) -> bool:
    """
    保存每日报告中的权重调整到数据库
    
    Args:
        report: DailyReport 对象
        supabase: Supabase 客户端（可选）
    
    Returns:
        success: 是否成功
    """
    if not report.weight_adjustments:
        return False
    
    return save_weight_adjustment_to_database(
        adjustment=report.weight_adjustments,
        performance_metrics=None,  # 可以从 report 中提取
        opportunity_density_score=report.opportunity_density_analysis.get("current_ods") if report.opportunity_density_analysis else None,
        applied=report.applied,
        supabase=supabase,
    )


__all__ = [
    "save_weight_adjustment_to_database",
    "save_daily_report_to_database",
]

