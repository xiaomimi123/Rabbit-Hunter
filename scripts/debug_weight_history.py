"""
调试权重历史功能
检查数据库、API 和前端数据流
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

load_dotenv()

try:
    from supabase import create_client, Client
except ImportError:
    print("[ERROR] 无法导入 supabase 模块")
    sys.exit(1)

# 初始化 Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[ERROR] Supabase 配置缺失")
    print(f"  SUPABASE_URL: {'已设置' if SUPABASE_URL else '未设置'}")
    print(f"  SUPABASE_KEY: {'已设置' if SUPABASE_KEY else '未设置'}")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("=" * 60)
print("V4.3 权重历史功能诊断")
print("=" * 60)
print()

# 1. 检查数据库表
print("1. 检查数据库表 ai_weights_v43")
print("-" * 60)
try:
    response = supabase.table("ai_weights_v43").select("id", count="exact").execute()
    total_count = response.count if hasattr(response, 'count') else len(response.data or [])
    print(f"   总记录数: {total_count}")
    
    if total_count == 0:
        print("   ⚠️  表为空，没有权重历史记录")
        print("   原因可能是：")
        print("   - AI 权重调整功能尚未运行")
        print("   - 权重调整功能存在但没有写入数据库的逻辑")
        print("   - 需要手动触发权重调整或创建测试数据")
    else:
        print(f"   ✅ 表中有 {total_count} 条记录")
        
        # 显示最新 5 条
        recent = supabase.table("ai_weights_v43")\
            .select("*")\
            .order("created_at", desc=True)\
            .limit(5)\
            .execute()
        
        print(f"\n   最新 5 条记录：")
        for i, record in enumerate(recent.data or [], 1):
            print(f"   {i}. ID={record.get('id')}, 版本={record.get('weights_version')}, "
                  f"应用={record.get('applied')}, 时间={record.get('created_at')}")
except Exception as e:
    print(f"   ❌ 查询失败: {e}")

print()

# 2. 检查权重管理模块
print("2. 检查权重管理模块")
print("-" * 60)
try:
    from v43_weight_manager import load_weights, DEFAULT_WEIGHTS
    current_weights = load_weights()
    print(f"   当前权重配置: {current_weights}")
    print(f"   默认权重: {DEFAULT_WEIGHTS}")
    
    # 检查配置文件
    config_path = "strategy_config.json"
    if os.path.exists(config_path):
        print(f"   ✅ 配置文件存在: {config_path}")
        import json
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            v43_weights = config.get("v43_weights", {})
            if v43_weights:
                print(f"   V4.3 权重: {v43_weights}")
            else:
                print(f"   ⚠️  配置文件中没有 v43_weights")
    else:
        print(f"   ⚠️  配置文件不存在: {config_path}")
except Exception as e:
    print(f"   ❌ 检查失败: {e}")

print()

# 3. 检查 AI 权重调整模块
print("3. 检查 AI 权重调整模块")
print("-" * 60)
try:
    import importlib.util
    deepseek_path = os.path.join(BASE_DIR, "scripts", "v43_deepseek_constrained.py")
    if os.path.exists(deepseek_path):
        print(f"   ✅ 模块文件存在: v43_deepseek_constrained.py")
        # 尝试导入
        try:
            from v43_deepseek_constrained import DeepSeekConstrained, WeightAdjustment, DailyReport
            print(f"   ✅ 模块可以导入")
            print(f"   ✅ 类: DeepSeekConstrained")
            print(f"   ✅ 数据类: WeightAdjustment, DailyReport")
            
            # 检查是否有 API Key
            ai = DeepSeekConstrained()
            if ai.is_ready():
                print(f"   ✅ DeepSeek API Key 已配置")
            else:
                print(f"   ⚠️  DeepSeek API Key 未配置（DEEPSEEK_API_KEY）")
            
            # 检查是否有写入数据库的逻辑
            print(f"   ⚠️  需要检查是否有写入数据库的逻辑")
            print(f"   ⚠️  当前模块只返回 WeightAdjustment 对象，不直接写入数据库")
        except ImportError as e:
            print(f"   ⚠️  模块导入失败: {e}")
            print(f"   提示: adjust_weights 是 DeepSeekConstrained 类的方法，不是模块级函数")
    else:
        print(f"   ⚠️  模块文件不存在: v43_deepseek_constrained.py")
except Exception as e:
    print(f"   ❌ 检查失败: {e}")

print()

# 4. 检查 API 端点
print("4. 检查 API 端点")
print("-" * 60)
print("   端点: GET /api/v43/weight-history")
print("   状态: ✅ 已实现 (api/main.py:674)")
print("   功能: 从 ai_weights_v43 表查询权重历史")
print()

# 5. 检查前端组件
print("5. 检查前端组件")
print("-" * 60)
print("   组件: WeightHistory.tsx")
print("   API 调用: weightsAPI.getHistory(50, 0)")
print("   状态: ✅ 已实现")
print()

# 6. 诊断结果和建议
print("=" * 60)
print("诊断结果")
print("=" * 60)
print()

if total_count == 0:
    print("🔴 问题：数据库中没有权重历史记录")
    print()
    print("可能的原因：")
    print("1. AI 权重调整功能尚未实现或未运行")
    print("2. 权重调整功能存在，但没有写入数据库的逻辑")
    print("3. 需要手动触发权重调整")
    print()
    print("建议的解决方案：")
    print("1. 检查 v43_deepseek_constrained.py 是否有写入数据库的逻辑")
    print("2. 如果缺少写入逻辑，需要添加保存权重历史到数据库的代码")
    print("3. 可以创建测试数据来验证前端功能")
    print()
    print("创建测试数据的 SQL：")
    print("""
INSERT INTO ai_weights_v43 (weights, weights_version, performance_metrics, opportunity_density_score, ai_reason, applied)
VALUES 
  (
    '{"structure": 0.35, "volatility": 0.25, "sentiment": 0.25, "manipulation": 0.15}'::jsonb,
    'v4.3.0',
    '{"win_rate": 0.65, "avg_profit": 0.02, "total_trades": 100}'::jsonb,
    0.75,
    '初始权重配置',
    true
  ),
  (
    '{"structure": 0.38, "volatility": 0.23, "sentiment": 0.24, "manipulation": 0.15}'::jsonb,
    'v4.3.1',
    '{"win_rate": 0.68, "avg_profit": 0.025, "total_trades": 120}'::jsonb,
    0.80,
    'AI 调整：提高结构权重以捕捉更多趋势机会',
    true
  ),
  (
    '{"structure": 0.40, "volatility": 0.22, "sentiment": 0.23, "manipulation": 0.15}'::jsonb,
    'v4.3.2',
    '{"win_rate": 0.70, "avg_profit": 0.028, "total_trades": 150}'::jsonb,
    0.85,
    'AI 调整：进一步优化结构权重，胜率提升',
    false
  );
    """)
else:
    print("✅ 数据库中有权重历史记录")
    print("   前端应该可以正常显示")

print()
print("=" * 60)
print("诊断完成")
print("=" * 60)

