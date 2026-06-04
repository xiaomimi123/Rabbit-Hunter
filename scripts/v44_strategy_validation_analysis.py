"""
V4.4 策略验证分析脚本

分析 Sniffer 和 Vulture 策略的历史表现
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

print("=" * 80)
print("V4.4 策略验证分析")
print("=" * 80)
print()

# 1. Sniffer 策略分析
print("1️⃣ Sniffer 策略分析（P2 + 异动信号）")
print("-" * 80)

try:
    # 查询 P2 阶段的币种
    p2_response = supabase.table("trade_scores_v43").select(
        "symbol, created_at, features, sentiment_score, structure_score, final_score"
    ).eq("features->>phase", "P2_ACCUMULATION").gte("created_at", (datetime.now() - timedelta(days=3)).isoformat()).limit(1000).execute()
    
    if p2_response.data:
        p2_records = p2_response.data
        print(f"P2 阶段总记录数: {len(p2_records)}")
        
        # 分析异动信号
        sniffer_candidates = []
        for record in p2_records:
            features = record.get("features", {})
            if isinstance(features, dict):
                oi_change = features.get("oi_change", 0) or 0
                volume_spike = features.get("volume_spike", 0) or 0
                
                # Sniffer 条件：OI 上升 > 2% 或 爆量 > 3x
                if oi_change > 0.02 or volume_spike > 3.0:
                    sniffer_candidates.append({
                        "symbol": record.get("symbol"),
                        "created_at": record.get("created_at"),
                        "oi_change": oi_change,
                        "volume_spike": volume_spike,
                        "sentiment_score": record.get("sentiment_score", 0),
                        "final_score": record.get("final_score", 0),
                    })
        
        print(f"符合 Sniffer 条件的记录: {len(sniffer_candidates)}")
        
        if sniffer_candidates:
            unique_symbols = set([c["symbol"] for c in sniffer_candidates])
            print(f"唯一币种数: {len(unique_symbols)}")
            print(f"\nTop 10 Sniffer 候选币:")
            for i, candidate in enumerate(sorted(sniffer_candidates, key=lambda x: x["final_score"], reverse=True)[:10], 1):
                print(f"  {i}. {candidate['symbol']:15s} | OI变化: {candidate['oi_change']:6.2%} | 爆量: {candidate['volume_spike']:.1f}x | 分数: {candidate['final_score']:.1f}")
        else:
            print("  ⚠️  未找到符合 Sniffer 条件的记录")
            print("  建议: 放宽条件（OI 上升 > 1% 或 爆量 > 2x）")
    else:
        print("  ⚠️  未找到 P2 阶段记录")
    
    print()
    
except Exception as e:
    print(f"[ERROR] Sniffer 分析失败: {e}")
    import traceback
    traceback.print_exc()

# 2. Vulture 策略分析
print("2️⃣ Vulture 策略分析（P3B/P4 + 被拒 + OI 下降）")
print("-" * 80)

try:
    # 查询 P3B/P4 阶段的币种
    vulture_response = supabase.table("trade_scores_v43").select(
        "symbol, created_at, features, decision_policy, structure_score, final_score"
    ).in_("features->>phase", ["P3B_PUMP_LATE", "P4_DISTRIBUTION"]).gte("created_at", (datetime.now() - timedelta(days=3)).isoformat()).limit(1000).execute()
    
    if vulture_response.data:
        vulture_records = vulture_response.data
        print(f"P3B/P4 阶段总记录数: {len(vulture_records)}")
        
        # 分析 Vulture 候选币
        vulture_candidates = []
        for record in vulture_records:
            features = record.get("features", {})
            decision_policy = record.get("decision_policy", {})
            
            if isinstance(features, dict) and isinstance(decision_policy, dict):
                block_reason = decision_policy.get("block_reason", "")
                oi_change = features.get("oi_change", 0) or 0
                
                # Vulture 条件：被 LOW_EXPECTED_RETURN 拦截 + OI 下降 > 5%
                if "LOW_EXPECTED" in block_reason.upper() and oi_change < -0.05:
                    vulture_candidates.append({
                        "symbol": record.get("symbol"),
                        "created_at": record.get("created_at"),
                        "phase": features.get("phase", "UNKNOWN"),
                        "oi_change": oi_change,
                        "structure_score": record.get("structure_score", 0),
                        "final_score": record.get("final_score", 0),
                    })
        
        print(f"符合 Vulture 条件的记录: {len(vulture_candidates)}")
        
        if vulture_candidates:
            unique_symbols = set([c["symbol"] for c in vulture_candidates])
            print(f"唯一币种数: {len(unique_symbols)}")
            print(f"\nTop 10 Vulture 候选币:")
            for i, candidate in enumerate(sorted(vulture_candidates, key=lambda x: abs(x["oi_change"]), reverse=True)[:10], 1):
                print(f"  {i}. {candidate['symbol']:15s} | 阶段: {candidate['phase']:15s} | OI变化: {candidate['oi_change']:7.2%} | 分数: {candidate['final_score']:.1f}")
        else:
            print("  ⚠️  未找到符合 Vulture 条件的记录")
    else:
        print("  ⚠️  未找到 P3B/P4 阶段记录")
    
    print()
    
except Exception as e:
    print(f"[ERROR] Vulture 分析失败: {e}")
    import traceback
    traceback.print_exc()

# 3. 阶段分布统计
print("3️⃣ 阶段分布统计（过去 3 天）")
print("-" * 80)

try:
    phase_response = supabase.table("trade_scores_v43").select("features, final_score").gte("created_at", (datetime.now() - timedelta(days=3)).isoformat()).limit(5000).execute()
    
    if phase_response.data:
        phase_stats = {}
        for record in phase_response.data:
            features = record.get("features", {})
            if isinstance(features, dict):
                phase = features.get("phase", "UNKNOWN")
                if phase not in phase_stats:
                    phase_stats[phase] = {"count": 0, "scores": []}
                phase_stats[phase]["count"] += 1
                phase_stats[phase]["scores"].append(float(record.get("final_score", 0) or 0))
        
        print(f"{'阶段':<20} {'记录数':<10} {'平均分数':<12} {'占比':<10}")
        print("-" * 60)
        total = sum([s["count"] for s in phase_stats.values()])
        for phase, stats in sorted(phase_stats.items(), key=lambda x: x[1]["count"], reverse=True):
            avg_score = sum(stats["scores"]) / len(stats["scores"]) if stats["scores"] else 0
            percentage = stats["count"] / total * 100 if total > 0 else 0
            print(f"{phase:<20} {stats['count']:<10} {avg_score:<12.2f} {percentage:<10.1f}%")
    
    print()
    
except Exception as e:
    print(f"[ERROR] 阶段分布统计失败: {e}")

print("=" * 80)
print("分析完成")
print("=" * 80)

