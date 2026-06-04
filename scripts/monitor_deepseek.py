"""
DeepSeek AI 监控脚本

功能：
- 检查 DeepSeek API 是否被调用
- 分析 AI 决策质量
- 验证 AI 是否真正在分析数据
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

try:
    from supabase import create_client, Client
except ImportError:
    print("[ERROR] 请安装 supabase: pip install supabase")
    sys.exit(1)


def check_deepseek_status():
    """检查 DeepSeek 调用状态"""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        print("❌ Supabase 配置缺失")
        return
    
    supabase: Client = create_client(supabase_url, supabase_key)
    
    print("=" * 60)
    print("DeepSeek AI 监控报告")
    print("=" * 60)
    print()
    
    # 1. 检查最近 24 小时调用情况
    print("📊 最近 24 小时调用统计")
    print("-" * 60)
    
    recent_24h = supabase.table("ai_training_data")\
        .select("id, symbol, created_at, ai_score, ai_allowed, ai_reason, market_phase")\
        .eq("ai_version", "deepseek-chat")\
        .not_.is_("ai_score", "null")\
        .gte("created_at", (datetime.now() - timedelta(hours=24)).isoformat())\
        .execute()
    
    total_calls = len(recent_24h.data)
    unique_symbols = len(set(row['symbol'] for row in recent_24h.data))
    
    if total_calls == 0:
        print("❌ DeepSeek 最近 24 小时未被调用")
        print()
        print("可能原因：")
        print("  1. DEEPSEEK_ENABLED=0（未启用）")
        print("  2. DEEPSEEK_API_KEY 未配置")
        print("  3. Shadow Mode 未触发（数据未满足存储条件）")
        return
    
    print(f"✅ 总调用次数: {total_calls:,}")
    print(f"✅ 涉及币种: {unique_symbols} 个")
    print(f"✅ 平均每小时: {total_calls / 24:.1f} 次")
    print()
    
    # 2. 分析分数分布
    print("📈 AI 分数分布")
    print("-" * 60)
    
    scores = [float(row['ai_score']) for row in recent_24h.data if row['ai_score']]
    if scores:
        avg_score = sum(scores) / len(scores)
        min_score = min(scores)
        max_score = max(scores)
        
        print(f"平均分数: {avg_score:.3f}")
        print(f"最低分数: {min_score:.3f}")
        print(f"最高分数: {max_score:.3f}")
        print()
        
        # 分数区间分布
        low_scores = sum(1 for s in scores if s < 0.3)
        mid_scores = sum(1 for s in scores if 0.3 <= s < 0.6)
        high_scores = sum(1 for s in scores if s >= 0.6)
        
        print(f"低分 (0-0.3): {low_scores} ({low_scores/len(scores)*100:.1f}%)")
        print(f"中分 (0.3-0.6): {mid_scores} ({mid_scores/len(scores)*100:.1f}%)")
        print(f"高分 (0.6-1.0): {high_scores} ({high_scores/len(scores)*100:.1f}%)")
        print()
    
    # 3. 分析决策结果
    print("🎯 决策结果统计")
    print("-" * 60)
    
    allowed_count = sum(1 for row in recent_24h.data if row.get('ai_allowed'))
    rejected_count = total_calls - allowed_count
    
    print(f"允许交易: {allowed_count} ({allowed_count/total_calls*100:.1f}%)")
    print(f"拒绝交易: {rejected_count} ({rejected_count/total_calls*100:.1f}%)")
    print()
    
    # 4. 按市场阶段分析
    print("📊 按市场阶段分析")
    print("-" * 60)
    
    phase_stats = {}
    for row in recent_24h.data:
        phase = row.get('market_phase') or 'UNKNOWN'
        if phase not in phase_stats:
            phase_stats[phase] = {'count': 0, 'scores': [], 'allowed': 0}
        
        phase_stats[phase]['count'] += 1
        if row.get('ai_score'):
            phase_stats[phase]['scores'].append(float(row['ai_score']))
        if row.get('ai_allowed'):
            phase_stats[phase]['allowed'] += 1
    
    for phase, stats in sorted(phase_stats.items(), key=lambda x: x[1]['count'], reverse=True):
        avg_phase_score = sum(stats['scores']) / len(stats['scores']) if stats['scores'] else 0
        allowed_pct = stats['allowed'] / stats['count'] * 100 if stats['count'] > 0 else 0
        
        print(f"{phase:20s}: {stats['count']:5d} 次 | "
              f"平均分数: {avg_phase_score:.3f} | "
              f"允许率: {allowed_pct:.1f}%")
    print()
    
    # 5. 检查决策理由多样性
    print("🔍 决策理由分析")
    print("-" * 60)
    
    reasons = [row.get('ai_reason', '')[:50] for row in recent_24h.data if row.get('ai_reason')]
    unique_reasons = len(set(reasons))
    
    print(f"总理由数: {len(reasons)}")
    print(f"唯一理由数: {unique_reasons}")
    print(f"多样性: {unique_reasons/len(reasons)*100:.1f}%")
    print()
    
    if unique_reasons < len(reasons) * 0.3:
        print("⚠️  警告：决策理由过于单一，AI 可能没有真正分析数据")
        print()
    else:
        print("✅ 决策理由多样化，AI 正在分析不同情况")
        print()
    
    # 6. 显示最近 10 条决策
    print("📋 最近 10 条决策")
    print("-" * 60)
    
    recent_decisions = sorted(recent_24h.data, key=lambda x: x['created_at'], reverse=True)[:10]
    
    for row in recent_decisions:
        symbol = row.get('symbol', 'N/A')
        score = float(row.get('ai_score', 0))
        allowed = row.get('ai_allowed', False)
        phase = row.get('market_phase', 'UNKNOWN')
        reason = (row.get('ai_reason') or '')[:60]
        
        status = "✅ 允许" if allowed else "❌ 拒绝"
        print(f"{symbol:12s} | {status} | score={score:.2f} | phase={phase:15s}")
        if reason:
            print(f"             理由: {reason}")
    print()
    
    # 7. 总结
    print("=" * 60)
    print("总结")
    print("=" * 60)
    
    if total_calls > 0:
        print("✅ DeepSeek API 正在被调用")
        print("✅ AI 正在分析市场数据")
        
        if avg_score < 0.3:
            print("⚠️  AI 分数普遍较低，可能是：")
            print("   - 市场处于垃圾时间（大部分是 P1 阶段）")
            print("   - 动态阈值设置过高（当前阈值可能 > 0.65）")
            print("   - AI 判断标准过于保守")
        
        if allowed_count == 0:
            print("⚠️  所有交易都被拒绝，建议：")
            print("   - 检查 AI_JUDGE_THRESHOLD 设置（当前可能过高）")
            print("   - 检查动态阈值逻辑（confidence_level 可能过高）")
            print("   - 等待更好的市场机会（P3A 阶段）")
    else:
        print("❌ DeepSeek 未被调用，请检查配置")


if __name__ == "__main__":
    try:
        check_deepseek_status()
    except Exception as e:
        print(f"[ERROR] 监控失败: {e}")
        import traceback
        traceback.print_exc()

