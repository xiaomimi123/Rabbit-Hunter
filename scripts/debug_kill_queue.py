#!/usr/bin/env python3
"""
调试工具：检查 kill queue 数据
用于排查为什么前端没有显示数据
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

try:
    from supabase import create_client
except ImportError:
    print("[ERROR] 请安装 supabase: pip install supabase")
    sys.exit(1)

def main():
    """主函数"""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        print("[ERROR] 请设置 SUPABASE_URL 和 SUPABASE_KEY 环境变量")
        sys.exit(1)
    
    print("=" * 60)
    print("V4.3 Kill Queue 数据调试工具")
    print("=" * 60)
    print()
    
    supabase = create_client(supabase_url, supabase_key)
    
    # 1. 检查数据总数
    print("📊 数据统计:")
    print("-" * 60)
    try:
        count_response = supabase.table("trade_scores_v43").select("id", count="exact").execute()
        total_count = count_response.count if hasattr(count_response, 'count') else 0
        print(f"  总记录数: {total_count}")
    except Exception as e:
        print(f"  ❌ 查询失败: {e}")
        return
    
    if total_count == 0:
        print("\n⚠️  数据库中没有数据！")
        print("   可能原因：")
        print("   1. 数据采集器未运行")
        print("   2. V4.3 模块未启用")
        print("   3. 数据未满足存储条件")
        return
    
    # 2. 检查最近的数据（详细分析）
    print("\n📋 最近 10 条记录（详细分析）:")
    print("-" * 60)
    try:
        recent = supabase.table("trade_scores_v43")\
            .select("*")\
            .order("created_at", desc=True)\
            .limit(10)\
            .execute()
        
        if not recent.data:
            print("  ⚠️  没有数据")
        else:
            for i, record in enumerate(recent.data, 1):
                final_score = record.get("final_score", 0.0)
                symbol = record.get("symbol", "N/A")
                created_at = record.get("created_at", "N/A")
                executed = record.get("executed", False)
                
                # 解析 decision_policy
                decision_policy = record.get("decision_policy", {})
                if isinstance(decision_policy, dict):
                    should_trade = decision_policy.get("should_trade", False)
                    decision_reason = decision_policy.get("reason", "N/A")
                else:
                    should_trade = False
                    decision_reason = "N/A"
                
                # 解析 score_result (从 decision_policy 或直接获取)
                structure_score = record.get("structure_score", 0.0)
                volatility_score = record.get("volatility_score", 0.0)
                sentiment_score = record.get("sentiment_score", 0.0)
                manipulation_score = record.get("manipulation_score", 0.0)
                
                # 检查 block_reason（可能在 decision_policy 中）
                block_reason = None
                if isinstance(decision_policy, dict):
                    block_reason = decision_policy.get("block_reason") or decision_reason
                
                score_display = final_score * 100 if final_score else 0.0
                status = "✅ TRADE" if should_trade or executed else "❌ NO"
                
                print(f"  {i:2d}. {symbol:12s} | score={score_display:5.1f} | {status:8s} | {created_at[:19]}")
                
                # 显示详细分数（如果分数为 0，显示原因）
                if final_score == 0.0:
                    print(f"      结构={structure_score*100:.1f} 波动={volatility_score*100:.1f} 情绪={sentiment_score*100:.1f} 操控={manipulation_score*100:.1f}")
                    if block_reason or (decision_reason and "拦截" in decision_reason):
                        reason = block_reason or decision_reason
                        print(f"      ⚠️  拦截原因: {reason[:80]}")
    except Exception as e:
        print(f"  ❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 3. 检查分数分布
    print("\n📈 分数分布:")
    print("-" * 60)
    thresholds = [
        (0.0, "所有数据"),
        (0.4, ">= 40"),
        (0.5, ">= 50"),
        (0.6, ">= 60 (默认阈值)"),
        (0.7, ">= 70"),
        (0.8, ">= 80"),
    ]
    
    for threshold, label in thresholds:
        try:
            count_response = supabase.table("trade_scores_v43")\
                .select("id", count="exact")\
                .gte("final_score", threshold)\
                .execute()
            count = count_response.count if hasattr(count_response, 'count') else 0
            percentage = (count / total_count * 100) if total_count > 0 else 0
            print(f"  {label:20s}: {count:4d} 条 ({percentage:5.1f}%)")
        except Exception as e:
            print(f"  {label:20s}: ❌ 查询失败: {e}")
    
    # 4. 检查最近 1 小时的数据
    print("\n⏰ 最近 1 小时的数据:")
    print("-" * 60)
    try:
        one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
        recent_1h = supabase.table("trade_scores_v43")\
            .select("id", count="exact")\
            .gte("created_at", one_hour_ago)\
            .execute()
        count_1h = recent_1h.count if hasattr(recent_1h, 'count') else 0
        print(f"  最近 1 小时: {count_1h} 条记录")
        
        if count_1h == 0:
            print("  ⚠️  最近 1 小时没有新数据")
            print("     可能原因：")
            print("     1. 数据采集器未运行")
            print("     2. 市场没有异动币种")
            print("     3. 数据写入被去重逻辑过滤")
    except Exception as e:
        print(f"  ❌ 查询失败: {e}")
    
    # 5. 检查满足前端条件的记录
    print("\n🎯 满足前端显示条件的记录 (score >= 60):")
    print("-" * 60)
    try:
        qualified = supabase.table("trade_scores_v43")\
            .select("*")\
            .gte("final_score", 0.6)\
            .order("final_score", desc=True)\
            .limit(5)\
            .execute()
        
        if not qualified.data:
            print("  ⚠️  没有满足条件的记录")
            print("     建议：降低 minScore 阈值（例如改为 40）")
        else:
            print(f"  ✅ 找到 {len(qualified.data)} 条记录:")
            for i, record in enumerate(qualified.data, 1):
                final_score = record.get("final_score", 0.0)
                symbol = record.get("symbol", "N/A")
                score_display = final_score * 100 if final_score else 0.0
                print(f"     {i}. {symbol:12s} | score={score_display:.1f}")
    except Exception as e:
        print(f"  ❌ 查询失败: {e}")
    
    # 6. 检查 features 字段（关键诊断）
    print("\n🔍 关键诊断：检查 features 字段是否有数据")
    print("-" * 60)
    try:
        sample_features = supabase.table("trade_scores_v43")\
            .select("symbol, final_score, features, created_at")\
            .order("created_at", desc=True)\
            .limit(3)\
            .execute()
        
        if sample_features.data:
            for idx, record in enumerate(sample_features.data, 1):
                symbol = record.get("symbol", "N/A")
                final_score = record.get("final_score", 0.0)
                features = record.get("features", {})
                created_at = record.get("created_at", "N/A")
                
                print(f"\n  记录 #{idx} ({symbol}):")
                print(f"    Final Score: {final_score}")
                print(f"    Features 类型: {type(features).__name__}")
                
                if features is None:
                    print(f"    ❌ CRITICAL: features 是 NULL！采集器没有写入数据！")
                elif isinstance(features, dict):
                    if len(features) == 0:
                        print(f"    ❌ CRITICAL: features 是空字典 {{}}！")
                    else:
                        # 检查关键字段
                        phase = features.get("phase") or features.get("market_phase", "N/A")
                        phase_age = features.get("phase_age", "N/A")
                        range_left = features.get("range_left", "N/A")
                        atr = features.get("atr", "N/A")
                        
                        print(f"    ✅ Features 有数据 ({len(features)} 个字段)")
                        print(f"       关键字段: phase={phase}, phase_age={phase_age}, range_left={range_left}, atr={atr}")
                        
                        # 检查是否全是 0
                        numeric_values = [v for v in features.values() if isinstance(v, (int, float))]
                        if numeric_values and all(v == 0.0 for v in numeric_values):
                            print(f"    ⚠️  警告: features 中所有数值都是 0.0！")
                else:
                    print(f"    ⚠️  警告: features 类型异常: {type(features)}")
        else:
            print("  ⚠️  没有数据可检查")
    except Exception as e:
        print(f"  ❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 7. 分析为什么所有分数都是 0.0
    print("\n🔍 深度分析：为什么所有分数都是 0.0？")
    print("-" * 60)
    try:
        # 检查最近 3 条记录的详细信息
        samples = supabase.table("trade_scores_v43")\
            .select("*")\
            .order("created_at", desc=True)\
            .limit(3)\
            .execute()
        
        if samples.data:
            for idx, record in enumerate(samples.data, 1):
                print(f"\n  记录 #{idx} ({record.get('symbol', 'N/A')}):")
                decision_policy = record.get("decision_policy", {})
                features = record.get("features", {})
                
                # 分数信息
                final_score = record.get("final_score", 0.0)
                structure_score = record.get("structure_score", 0.0)
                volatility_score = record.get("volatility_score", 0.0)
                sentiment_score = record.get("sentiment_score", 0.0)
                manipulation_score = record.get("manipulation_score", 0.0)
                
                print(f"    最终分数: {final_score*100:.1f}")
                print(f"    各维度分数: 结构={structure_score*100:.1f} 波动={volatility_score*100:.1f} 情绪={sentiment_score*100:.1f} 操控={manipulation_score*100:.1f}")
                
                # 检查特征
                if isinstance(features, dict):
                    phase = features.get("phase") or features.get("market_phase", "N/A")
                    phase_age = features.get("phase_age", "N/A")
                    range_left = features.get("range_left", "N/A")
                    
                    print(f"    特征: phase={phase}, phase_age={phase_age}, range_left={range_left}")
                    
                    # 检查硬约束拦截原因
                    if phase in ["P1_NO_WHALE", "P4_DISTRIBUTION", "P1", "P4"]:
                        print(f"    ⚠️  硬约束拦截: 阶段 {phase} 禁止交易（P1/P4）")
                    if isinstance(phase_age, (int, float)) and phase_age > 100:
                        print(f"    ⚠️  硬约束拦截: 阶段年龄 {phase_age} > 100")
                    if isinstance(range_left, (int, float)) and range_left < 0.02:
                        print(f"    ⚠️  硬约束拦截: 预期收益 {range_left*100:.2f}% < 2%")
                
                # 检查决策原因
                if isinstance(decision_policy, dict):
                    should_trade = decision_policy.get("should_trade", False)
                    reason = decision_policy.get("reason", "")
                    block_reason = decision_policy.get("block_reason", "")
                    
                    print(f"    决策: should_trade={should_trade}")
                    if block_reason:
                        print(f"    ⚠️  拦截原因: {block_reason}")
                    if reason and reason != "N/A":
                        print(f"    决策原因: {reason[:120]}")
        else:
            print("  ⚠️  没有数据可分析")
    except Exception as e:
        print(f"  ❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 7. 建议
    print("\n💡 建议:")
    print("-" * 60)
    if total_count == 0:
        print("  1. 确认数据采集器正在运行")
        print("  2. 检查环境变量 V43_ENABLED=1")
        print("  3. 查看采集器日志")
    else:
        try:
            count_60 = supabase.table("trade_scores_v43")\
                .select("id", count="exact")\
                .gte("final_score", 0.6)\
                .execute()
            count_60_val = count_60.count if hasattr(count_60, 'count') else 0
            
            if count_60_val == 0:
                print("  ⚠️  所有记录的分数都是 0.0，可能原因：")
                print("     1. 硬约束拦截了所有交易（P1/P4 阶段、年龄>100、预期收益<2%）")
                print("     2. 结构分数计算为 0（市场阶段不匹配）")
                print("     3. 特征提取有问题")
                print("")
                print("  🔧 解决方案：")
                print("     1. 检查采集器日志，查看是否有 [V4.3] 错误信息")
                print("     2. 检查硬约束逻辑（v43_hard_filters.py）")
                print("     3. 检查特征提取逻辑（v43_feature_extractor.py）")
                print("     4. 临时降低前端阈值到 0，查看是否有任何非零分数")
            else:
                print("  1. 数据正常，检查前端 API 调用")
                print("  2. 打开浏览器控制台查看 Network 请求")
        except:
            pass
    
    print("\n" + "=" * 60)
    print("调试完成")
    print("=" * 60)
    print("\n提示: 窗口将保持打开，方便您复制结果。")
    print("按 Ctrl+C 或关闭窗口以退出。")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[用户中断] 调试已取消")
    except Exception as e:
        print(f"\n\n[错误] 调试过程中发生异常: {e}")
        import traceback
        traceback.print_exc()

