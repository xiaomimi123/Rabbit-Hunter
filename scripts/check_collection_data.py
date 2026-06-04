"""
检查数据采集情况
快速诊断 V4.3 数据采集是否正常
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
    print("[ERROR] 无法导入 supabase")
    sys.exit(1)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[ERROR] Supabase 配置缺失")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("=" * 60)
print("V4.3 数据采集情况检查")
print("=" * 60)
print()

# 1. 检查 trade_scores_v43 数据
print("1️⃣ 检查 trade_scores_v43 数据")
print("-" * 60)

try:
    # 总记录数
    total_response = supabase.table("trade_scores_v43").select("id", count="exact").execute()
    total_count = total_response.count if hasattr(total_response, 'count') else len(total_response.data)
    
    # 最近 1 小时的记录
    one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
    recent_response = supabase.table("trade_scores_v43").select("id", count="exact").gte("created_at", one_hour_ago).execute()
    recent_count = recent_response.count if hasattr(recent_response, 'count') else len(recent_response.data)
    
    # 最近 24 小时的记录
    one_day_ago = (datetime.now() - timedelta(days=1)).isoformat()
    daily_response = supabase.table("trade_scores_v43").select("id", count="exact").gte("created_at", one_day_ago).execute()
    daily_count = daily_response.count if hasattr(daily_response, 'count') else len(daily_response.data)
    
    # 唯一币种数
    symbols_response = supabase.table("trade_scores_v43").select("symbol").execute()
    unique_symbols = len(set([r["symbol"] for r in symbols_response.data])) if symbols_response.data else 0
    
    print(f"总记录数:           {total_count:,} 条")
    print(f"唯一币种数:         {unique_symbols} 个")
    print(f"最近 1 小时:         {recent_count} 条")
    print(f"最近 24 小时:        {daily_count} 条")
    
    # 分数分布
    if total_count > 0:
        scores_response = supabase.table("trade_scores_v43").select("final_score").limit(1000).execute()
        if scores_response.data:
            scores = [float(r.get("final_score", 0) or 0) for r in scores_response.data]
            non_zero_scores = [s for s in scores if s > 0]
            high_scores = [s for s in scores if s >= 50]
            
            print(f"非零分数记录:       {len(non_zero_scores)} / {len(scores)} ({len(non_zero_scores)/len(scores)*100:.1f}%)")
            print(f"高分记录 (≥50):     {len(high_scores)} / {len(scores)} ({len(high_scores)/len(scores)*100:.1f}%)")
            if non_zero_scores:
                print(f"平均分数:           {sum(non_zero_scores)/len(non_zero_scores):.2f}")
                print(f"最高分数:           {max(non_zero_scores):.2f}")
    
    # 阶段分布
    phases_response = supabase.table("trade_scores_v43").select("features").limit(1000).execute()
    if phases_response.data:
        phases = {}
        for r in phases_response.data:
            features = r.get("features", {})
            if isinstance(features, dict):
                phase = features.get("phase", "UNKNOWN")
                phases[phase] = phases.get(phase, 0) + 1
        
        print(f"\n阶段分布 (最近 1000 条):")
        for phase, count in sorted(phases.items(), key=lambda x: x[1], reverse=True):
            print(f"  {phase:20s}: {count:4d} ({count/len(phases_response.data)*100:.1f}%)")
    
    # 拦截原因分布
    block_reasons_response = supabase.table("trade_scores_v43").select("decision_policy").limit(1000).execute()
    if block_reasons_response.data:
        block_reasons = {}
        for r in block_reasons_response.data:
            policy = r.get("decision_policy", {})
            if isinstance(policy, dict):
                reason = policy.get("block_reason", "NONE")
                if reason:
                    block_reasons[reason] = block_reasons.get(reason, 0) + 1
        
        print(f"\n拦截原因分布 (最近 1000 条):")
        for reason, count in sorted(block_reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  {reason:25s}: {count:4d} ({count/len(block_reasons_response.data)*100:.1f}%)")
    
    print()
    
except Exception as e:
    print(f"[ERROR] 查询失败: {e}")
    import traceback
    traceback.print_exc()

# 2. 检查 ai_training_data 数据
print("2️⃣ 检查 ai_training_data 数据")
print("-" * 60)

try:
    training_response = supabase.table("ai_training_data").select("id", count="exact").execute()
    training_count = training_response.count if hasattr(training_response, 'count') else len(training_response.data)
    
    recent_training_response = supabase.table("ai_training_data").select("id", count="exact").gte("created_at", one_hour_ago).execute()
    recent_training_count = recent_training_response.count if hasattr(recent_training_response, 'count') else len(recent_training_response.data)
    
    print(f"总记录数:           {training_count:,} 条")
    print(f"最近 1 小时:         {recent_training_count} 条")
    
    # 最近记录的币种
    if training_count > 0:
        recent_symbols_response = supabase.table("ai_training_data").select("symbol, created_at").order("created_at", desc=True).limit(10).execute()
        if recent_symbols_response.data:
            print(f"\n最近存储的币种 (Top 10):")
            for r in recent_symbols_response.data:
                symbol = r.get("symbol", "UNKNOWN")
                created_at = r.get("created_at", "")
                print(f"  {symbol:15s} - {created_at}")
    
    print()
    
except Exception as e:
    print(f"[ERROR] 查询失败: {e}")

# 3. 检查最新记录详情
print("3️⃣ 最新记录详情 (Top 5)")
print("-" * 60)

try:
    latest_response = supabase.table("trade_scores_v43").select("*").order("created_at", desc=True).limit(5).execute()
    if latest_response.data:
        for i, record in enumerate(latest_response.data, 1):
            symbol = record.get("symbol", "UNKNOWN")
            final_score = record.get("final_score", 0)
            structure_score = record.get("structure_score", 0)
            volatility_score = record.get("volatility_score", 0)
            sentiment_score = record.get("sentiment_score", 0)
            manipulation_score = record.get("manipulation_score", 0)
            
            features = record.get("features", {})
            phase = features.get("phase", "UNKNOWN") if isinstance(features, dict) else "UNKNOWN"
            
            decision_policy = record.get("decision_policy", {})
            should_trade = decision_policy.get("should_trade", False) if isinstance(decision_policy, dict) else False
            block_reason = decision_policy.get("block_reason", "") if isinstance(decision_policy, dict) else ""
            
            created_at = record.get("created_at", "")
            
            print(f"\n记录 #{i}: {symbol}")
            print(f"  时间: {created_at}")
            print(f"  最终分数: {final_score:.1f}")
            print(f"  四维分数: 结构={structure_score:.1f} 波动={volatility_score:.1f} 情绪={sentiment_score:.1f} 操控={manipulation_score:.1f}")
            print(f"  阶段: {phase}")
            print(f"  决策: {'✅ 允许交易' if should_trade else '❌ 拦截'} {('(' + block_reason + ')') if block_reason else ''}")
    else:
        print("  无数据")
    
    print()
    
except Exception as e:
    print(f"[ERROR] 查询失败: {e}")
    import traceback
    traceback.print_exc()

# 4. 诊断建议
print("4️⃣ 诊断建议")
print("-" * 60)

if recent_count == 0:
    print("⚠️  最近 1 小时没有新数据")
    print("   建议: 检查采集器是否正在运行")
elif recent_count < 10:
    print("⚠️  最近 1 小时数据量较少 (< 10 条)")
    print("   建议: 检查是否有异动币种，或降低异动阈值")
else:
    print("✅ 数据采集正常")

if total_count > 0:
    scores_response = supabase.table("trade_scores_v43").select("final_score").limit(1000).execute()
    if scores_response.data:
        scores = [float(r.get("final_score", 0) or 0) for r in scores_response.data]
        zero_scores = len([s for s in scores if s == 0])
        if zero_scores > len(scores) * 0.5:
            print("⚠️  超过 50% 的记录分数为 0")
            print("   可能原因:")
            print("   1. 所有币种都是 P1_NO_WHALE 阶段（不允许交易）")
            print("   2. 特征提取失败（四维分数都是 0）")
            print("   3. 硬过滤器拦截（但应该保留分数）")
            print("   建议: 检查采集器日志，查看具体拦截原因")

print()
print("=" * 60)
print("检查完成")
print("=" * 60)

