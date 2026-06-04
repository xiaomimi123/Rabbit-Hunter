"""
创建测试权重历史数据
用于验证前端权重历史页面功能
"""

import os
import sys
from datetime import datetime, timedelta
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
print("创建测试权重历史数据")
print("=" * 60)
print()

# 检查现有数据
try:
    response = supabase.table("ai_weights_v43").select("id", count="exact").execute()
    existing_count = response.count if hasattr(response, 'count') else len(response.data or [])
    print(f"当前数据库中的记录数: {existing_count}")
    
    if existing_count > 0:
        print()
        print("⚠️  警告：数据库中已有权重历史记录")
        response = input("是否继续创建测试数据？(y/n): ")
        if response.lower() != 'y':
            print("已取消")
            sys.exit(0)
except Exception as e:
    print(f"⚠️  检查现有数据失败: {e}")
    print("继续创建测试数据...")

print()

# 创建测试数据
test_data = [
    {
        "weights": {
            "structure": 0.35,
            "volatility": 0.25,
            "sentiment": 0.25,
            "manipulation": 0.15
        },
        "weights_version": "v4.3.0",
        "performance_metrics": {
            "win_rate": 0.65,
            "avg_profit": 0.02,
            "total_trades": 100,
            "profit_factor": 1.5,
            "max_drawdown": 0.05
        },
        "opportunity_density_score": 0.75,
        "ai_reason": "初始权重配置，基于历史回测结果",
        "applied": True,
        "created_at": (datetime.now() - timedelta(days=7)).isoformat()
    },
    {
        "weights": {
            "structure": 0.38,
            "volatility": 0.23,
            "sentiment": 0.24,
            "manipulation": 0.15
        },
        "weights_version": "v4.3.1",
        "performance_metrics": {
            "win_rate": 0.68,
            "avg_profit": 0.025,
            "total_trades": 120,
            "profit_factor": 1.6,
            "max_drawdown": 0.04
        },
        "opportunity_density_score": 0.80,
        "ai_reason": "AI 调整：提高结构权重以捕捉更多趋势机会，基于过去一周的表现分析",
        "applied": True,
        "created_at": (datetime.now() - timedelta(days=5)).isoformat()
    },
    {
        "weights": {
            "structure": 0.40,
            "volatility": 0.22,
            "sentiment": 0.23,
            "manipulation": 0.15
        },
        "weights_version": "v4.3.2",
        "performance_metrics": {
            "win_rate": 0.70,
            "avg_profit": 0.028,
            "total_trades": 150,
            "profit_factor": 1.7,
            "max_drawdown": 0.035
        },
        "opportunity_density_score": 0.85,
        "ai_reason": "AI 调整：进一步优化结构权重，胜率提升至 70%，同时保持风险控制",
        "applied": False,
        "created_at": (datetime.now() - timedelta(days=2)).isoformat()
    },
    {
        "weights": {
            "structure": 0.36,
            "volatility": 0.24,
            "sentiment": 0.25,
            "manipulation": 0.15
        },
        "weights_version": "v4.3.3",
        "performance_metrics": {
            "win_rate": 0.72,
            "avg_profit": 0.03,
            "total_trades": 180,
            "profit_factor": 1.8,
            "max_drawdown": 0.03
        },
        "opportunity_density_score": 0.88,
        "ai_reason": "AI 调整：微调权重平衡，在保持高胜率的同时提高平均收益",
        "applied": False,
        "created_at": (datetime.now() - timedelta(hours=12)).isoformat()
    },
]

print("准备插入以下测试数据：")
print("-" * 60)
for i, data in enumerate(test_data, 1):
    print(f"{i}. 版本: {data['weights_version']}")
    print(f"   权重: Structure={data['weights']['structure']:.2f}, "
          f"Volatility={data['weights']['volatility']:.2f}, "
          f"Sentiment={data['weights']['sentiment']:.2f}, "
          f"Manipulation={data['weights']['manipulation']:.2f}")
    print(f"   胜率: {data['performance_metrics']['win_rate']*100:.1f}%")
    print(f"   应用: {'是' if data['applied'] else '否'}")
    print()

try:
    # 批量插入
    response = supabase.table("ai_weights_v43").insert(test_data).execute()
    
    inserted_count = len(response.data) if response.data else 0
    print(f"✅ 成功插入 {inserted_count} 条测试数据")
    print()
    
    # 验证插入结果
    verify_response = supabase.table("ai_weights_v43")\
        .select("id, weights_version, applied, created_at")\
        .order("created_at", desc=True)\
        .limit(10)\
        .execute()
    
    print("验证：数据库中的最新记录：")
    print("-" * 60)
    for record in verify_response.data or []:
        print(f"  ID={record.get('id')}, 版本={record.get('weights_version')}, "
              f"应用={record.get('applied')}, 时间={record.get('created_at')}")
    
    print()
    print("=" * 60)
    print("✅ 测试数据创建完成！")
    print("=" * 60)
    print()
    print("现在可以：")
    print("1. 刷新前端权重历史页面，应该能看到 4 条记录")
    print("2. 验证前端显示是否正常")
    print("3. 测试刷新、排序等功能")
    
except Exception as e:
    print(f"❌ 插入失败: {e}")
    print()
    print("如果遇到错误，可以手动执行以下 SQL：")
    print("-" * 60)
    print("""
INSERT INTO ai_weights_v43 (weights, weights_version, performance_metrics, opportunity_density_score, ai_reason, applied, created_at)
VALUES 
  (
    '{"structure": 0.35, "volatility": 0.25, "sentiment": 0.25, "manipulation": 0.15}'::jsonb,
    'v4.3.0',
    '{"win_rate": 0.65, "avg_profit": 0.02, "total_trades": 100}'::jsonb,
    0.75,
    '初始权重配置',
    true,
    NOW() - INTERVAL '7 days'
  ),
  (
    '{"structure": 0.38, "volatility": 0.23, "sentiment": 0.24, "manipulation": 0.15}'::jsonb,
    'v4.3.1',
    '{"win_rate": 0.68, "avg_profit": 0.025, "total_trades": 120}'::jsonb,
    0.80,
    'AI 调整：提高结构权重以捕捉更多趋势机会',
    true,
    NOW() - INTERVAL '5 days'
  ),
  (
    '{"structure": 0.40, "volatility": 0.22, "sentiment": 0.23, "manipulation": 0.15}'::jsonb,
    'v4.3.2',
    '{"win_rate": 0.70, "avg_profit": 0.028, "total_trades": 150}'::jsonb,
    0.85,
    'AI 调整：进一步优化结构权重，胜率提升',
    false,
    NOW() - INTERVAL '2 days'
  );
    """)
    sys.exit(1)

