"""
V4.2 数据质量检查脚本

功能：
- 验证所有 P-State 和 ATR 数据都正确入库
- 检查数据完整性
- 生成数据质量报告
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
from supabase import Client


def check_data_quality(supabase: Client, days: int = 7) -> Dict[str, any]:
    """
    检查数据质量
    
    Args:
        supabase: Supabase 客户端
        days: 检查天数
    
    Returns:
        数据质量报告
    """
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # 获取数据
    response = (
        supabase.table("ai_training_data")
        .select("*")
        .gte("created_at", start_date)
        .execute()
    )
    
    records = response.data or []
    total_count = len(records)
    
    if total_count == 0:
        return {
            "success": False,
            "message": "没有数据可检查",
            "total_count": 0
        }
    
    # 检查各字段的完整性
    field_stats = {}
    
    required_fields = [
        "market_phase",
        "kill_zone_signal",
        "atr_value",
        "atr_multiplier",
        "chandelier_stop_price",
        "structure_gap",
        "phase_age_candles",
        "phase_age_percent",
        "is_golden_wick",
    ]
    
    for field in required_fields:
        non_null_count = sum(1 for r in records if r.get(field) is not None)
        null_count = total_count - non_null_count
        field_stats[field] = {
            "non_null": non_null_count,
            "null": null_count,
            "coverage": non_null_count / total_count * 100 if total_count > 0 else 0
        }
    
    # 检查数据有效性
    validation_errors = []
    
    # 检查 market_phase 是否在有效枚举值内
    valid_phases = {
        "P1_NO_WHALE",
        "P2_ACCUMULATION",
        "P3A_PUMP_START",
        "P3B_PUMP_LATE",
        "P4_DISTRIBUTION"
    }
    invalid_phases = [
        r for r in records
        if r.get("market_phase") and r.get("market_phase") not in valid_phases
    ]
    if invalid_phases:
        validation_errors.append(f"发现 {len(invalid_phases)} 条记录的 market_phase 不在有效枚举值内")
    
    # 检查 ATR 值是否合理（应该 > 0）
    invalid_atr = [
        r for r in records
        if r.get("atr_value") is not None and float(r.get("atr_value", 0)) <= 0
    ]
    if invalid_atr:
        validation_errors.append(f"发现 {len(invalid_atr)} 条记录的 atr_value <= 0")
    
    # 检查 structure_gap 是否在合理范围内（0-1）
    invalid_structure_gap = [
        r for r in records
        if r.get("structure_gap") is not None and (
            float(r.get("structure_gap", 0)) < 0 or float(r.get("structure_gap", 1)) > 1
        )
    ]
    if invalid_structure_gap:
        validation_errors.append(f"发现 {len(invalid_structure_gap)} 条记录的 structure_gap 不在 [0, 1] 范围内")
    
    # 计算总体覆盖率
    overall_coverage = sum(
        field_stats[f]["coverage"] for f in required_fields
    ) / len(required_fields)
    
    return {
        "success": True,
        "total_count": total_count,
        "field_stats": field_stats,
        "overall_coverage": overall_coverage,
        "validation_errors": validation_errors,
        "check_date": datetime.now(timezone.utc).isoformat(),
    }


def format_quality_report(report: Dict[str, any]) -> str:
    """
    格式化数据质量报告
    
    Args:
        report: 数据质量报告
    
    Returns:
        格式化的报告字符串
    """
    if not report.get("success"):
        return f"❌ {report.get('message', '数据质量检查失败')}"
    
    lines = [
        "=== 数据质量检查报告 ===",
        f"检查时间: {report.get('check_date', 'N/A')}",
        f"总记录数: {report.get('total_count', 0)}",
        f"总体覆盖率: {report.get('overall_coverage', 0):.2f}%",
        "",
        "字段完整性:",
    ]
    
    field_stats = report.get("field_stats", {})
    for field, stats in field_stats.items():
        coverage = stats.get("coverage", 0)
        non_null = stats.get("non_null", 0)
        null_count = stats.get("null", 0)
        status = "✅" if coverage >= 80 else "⚠️" if coverage >= 50 else "❌"
        lines.append(
            f"  {status} {field}: {coverage:.1f}% ({non_null}/{non_null + null_count})"
        )
    
    validation_errors = report.get("validation_errors", [])
    if validation_errors:
        lines.append("")
        lines.append("⚠️ 数据验证错误:")
        for error in validation_errors:
            lines.append(f"  - {error}")
    else:
        lines.append("")
        lines.append("✅ 未发现数据验证错误")
    
    return "\n".join(lines)


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    from supabase import create_client
    
    load_dotenv()
    
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        print("❌ 未配置 Supabase URL 或 Key")
        exit(1)
    
    supabase = create_client(supabase_url, supabase_key)
    
    report = check_data_quality(supabase, days=7)
    print(format_quality_report(report))

