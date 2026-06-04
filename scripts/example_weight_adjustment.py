"""
示例：AI 权重调整并保存到数据库

这是一个完整的示例，展示如何：
1. 调用 AI 进行权重调整
2. 将调整结果保存到数据库
3. 验证保存结果
"""

import os
import sys
from datetime import date
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

load_dotenv()

try:
    from supabase import create_client, Client
    from v43_weight_manager import load_weights
    from v43_deepseek_constrained import DeepSeekConstrained
    from v43_weight_history_helper import save_weight_adjustment_to_database
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

print("=" * 60)
print("AI 权重调整示例")
print("=" * 60)
print()

# 1. 加载当前权重
print("1. 加载当前权重配置")
print("-" * 60)
current_weights = load_weights()
print(f"   当前权重: {current_weights}")
print()

# 2. 准备性能指标（实际应用中应从数据库查询）
print("2. 准备性能指标")
print("-" * 60)
performance_metrics = {
    "win_rate": 0.68,
    "avg_profit": 0.025,
    "total_trades": 120,
    "profit_factor": 1.6,
    "max_drawdown": 0.04
}
print(f"   性能指标: {performance_metrics}")
print()

# 3. 准备机会密度分数（实际应用中应从数据库计算）
print("3. 准备机会密度分数")
print("-" * 60)
opportunity_density_score = 0.80
print(f"   机会密度分数: {opportunity_density_score}")
print()

# 4. 初始化 AI
print("4. 初始化 DeepSeek AI")
print("-" * 60)
ai = DeepSeekConstrained(debug=True)

if not ai.is_ready():
    print("   ⚠️  DeepSeek API Key 未配置（DEEPSEEK_API_KEY）")
    print("   将跳过 AI 调整，仅演示保存功能")
    print()
    
    # 创建模拟的权重调整（用于演示）
    from v43_deepseek_constrained import WeightAdjustment
    from v43_weight_manager import get_next_version
    
    new_version = get_next_version(current_weights.get("version", "v4.3.0"))
    adjustment = WeightAdjustment(
        new_weights={
            "structure": 0.38,
            "volatility": 0.23,
            "sentiment": 0.24,
            "manipulation": 0.15,
            "version": new_version
        },
        reasoning="示例：提高结构权重以捕捉更多趋势机会（模拟调整）",
        explainability_check=True,
        opportunity_density_impact="quality",
        version=new_version
    )
    print(f"   使用模拟调整: {adjustment.version}")
else:
    print("   ✅ DeepSeek AI 已就绪")
    print()
    
    # 5. AI 调整权重
    print("5. AI 调整权重")
    print("-" * 60)
    adjustment = ai.adjust_weights(
        current_weights=current_weights,
        performance_metrics=performance_metrics,
        opportunity_density_score=opportunity_density_score,
    )
    
    if not adjustment:
        print("   ❌ AI 调整失败")
        sys.exit(1)
    
    print(f"   ✅ AI 调整成功: {adjustment.version}")
    print(f"   新权重: {adjustment.new_weights}")
    print(f"   调整理由: {adjustment.reasoning[:100]}...")
    print()

# 6. 保存到数据库
print("6. 保存权重调整到数据库")
print("-" * 60)
success = save_weight_adjustment_to_database(
    adjustment=adjustment,
    performance_metrics=performance_metrics,
    opportunity_density_score=opportunity_density_score,
    applied=False,  # 需要人工审核后应用
    supabase=supabase,
)

if success:
    print(f"   ✅ 权重调整已保存到数据库: {adjustment.version}")
else:
    print(f"   ❌ 权重调整保存失败")
    sys.exit(1)

print()

# 7. 验证保存结果
print("7. 验证保存结果")
print("-" * 60)
try:
    response = supabase.table("ai_weights_v43")\
        .select("id, weights_version, applied, created_at, ai_reason")\
        .eq("weights_version", adjustment.version)\
        .order("created_at", desc=True)\
        .limit(1)\
        .execute()
    
    if response.data:
        record = response.data[0]
        print(f"   ✅ 找到保存的记录:")
        print(f"      ID: {record.get('id')}")
        print(f"      版本: {record.get('weights_version')}")
        print(f"      应用: {record.get('applied')}")
        print(f"      时间: {record.get('created_at')}")
        print(f"      理由: {record.get('ai_reason', '')[:80]}...")
    else:
        print("   ⚠️  未找到保存的记录")
except Exception as e:
    print(f"   ❌ 验证失败: {e}")

print()
print("=" * 60)
print("✅ 示例完成")
print("=" * 60)
print()
print("现在可以：")
print("1. 刷新前端权重历史页面，查看新保存的记录")
print("2. 在数据库中查看完整的权重调整历史")
print("3. 根据需要应用权重配置")

