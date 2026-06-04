"""
诊断数据流脚本

检查：
1. collector.py 是否在写入 market_snapshot
2. Supabase 中是否有数据
3. Realtime 是否已启用
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import datetime, timezone

# 载入环境变量
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def main():
    print("=" * 60)
    print("Rabbit Hunter 数据流诊断")
    print("=" * 60)
    
    # 1. 检查环境变量
    print("\n[1] 检查环境变量...")
    if not SUPABASE_URL:
        print("  ❌ SUPABASE_URL 未设置")
        return
    else:
        print(f"  ✅ SUPABASE_URL: {SUPABASE_URL[:30]}...")
    
    if not SUPABASE_KEY:
        print("  ❌ SUPABASE_KEY 未设置")
        return
    else:
        print(f"  ✅ SUPABASE_KEY: {SUPABASE_KEY[:20]}...")
    
    # 2. 连接 Supabase
    print("\n[2] 连接 Supabase...")
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("  ✅ Supabase 连接成功")
    except Exception as e:
        print(f"  ❌ Supabase 连接失败: {e}")
        return
    
    # 3. 检查 market_snapshot 表数据
    print("\n[3] 检查 market_snapshot 表...")
    try:
        response = supabase.table("market_snapshot").select("symbol, updated_at, price, risk_score").limit(10).execute()
        count = len(response.data) if response.data else 0
        print(f"  ✅ market_snapshot 表中有 {count} 条记录")
        
        if count > 0:
            print("\n  最近 5 条记录：")
            for i, row in enumerate(response.data[:5], 1):
                symbol = row.get("symbol", "N/A")
                updated_at = row.get("updated_at", "N/A")
                price = row.get("price", "N/A")
                risk_score = row.get("risk_score", "N/A")
                print(f"    {i}. {symbol:15s} | price={price:10s} | risk={risk_score:3s} | updated={updated_at}")
        else:
            print("  ⚠️  表中没有数据，请确保 collector.py 正在运行")
    except Exception as e:
        print(f"  ❌ 查询失败: {e}")
    
    # 4. 检查 ai_training_data 表数据
    print("\n[4] 检查 ai_training_data 表...")
    try:
        response = supabase.table("ai_training_data").select("symbol, created_at, market_phase, kill_zone_signal").order("created_at", desc=True).limit(5).execute()
        count = len(response.data) if response.data else 0
        print(f"  ✅ ai_training_data 表中有数据（最近 5 条）")
        
        if count > 0:
            print("\n  最近 5 条记录：")
            for i, row in enumerate(response.data[:5], 1):
                symbol = row.get("symbol", "N/A")
                created_at = row.get("created_at", "N/A")
                phase = row.get("market_phase", "N/A")
                kz = row.get("kill_zone_signal", "N/A")
                print(f"    {i}. {symbol:15s} | phase={phase:20s} | kz={kz:15s} | created={created_at}")
        else:
            print("  ⚠️  表中没有数据")
    except Exception as e:
        print(f"  ❌ 查询失败: {e}")
    
    # 5. 检查 V4.1 字段
    print("\n[5] 检查 V4.1 字段...")
    try:
        response = supabase.table("ai_training_data").select("symbol, atr_value, structure_gap, chandelier_stop_price").not_.is_("atr_value", "null").limit(5).execute()
        count = len(response.data) if response.data else 0
        if count > 0:
            print(f"  ✅ 找到 {count} 条包含 V4.1 字段的记录")
            for i, row in enumerate(response.data[:3], 1):
                symbol = row.get("symbol", "N/A")
                atr = row.get("atr_value", "N/A")
                gap = row.get("structure_gap", "N/A")
                stop = row.get("chandelier_stop_price", "N/A")
                print(f"    {i}. {symbol:15s} | ATR={atr} | gap={gap} | stop={stop}")
        else:
            print("  ⚠️  还没有包含 V4.1 字段的记录（可能 collector.py 刚启动，等待数据写入）")
    except Exception as e:
        print(f"  ⚠️  查询 V4.1 字段失败（可能字段还未创建）: {e}")
    
    # 6. 检查 Realtime 是否启用
    print("\n[6] 检查 Realtime 配置...")
    try:
        # 查询 pg_publication 表（需要管理员权限，这里只做提示）
        print("  ℹ️  Realtime 配置检查需要数据库管理员权限")
        print("  ℹ️  如果前端无法接收实时更新，请检查：")
        print("     1. Supabase Dashboard → Database → Replication")
        print("     2. 确认 market_snapshot 表已启用 Realtime")
    except Exception as e:
        print(f"  ⚠️  无法检查 Realtime 配置: {e}")
    
    # 7. 建议
    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)
    print("\n建议：")
    print("1. 如果 market_snapshot 表为空，请确保 collector.py 正在运行")
    print("2. 如果前端无法接收更新，请检查：")
    print("   - frontend/.env.local 中的 NEXT_PUBLIC_SUPABASE_URL 和 NEXT_PUBLIC_SUPABASE_ANON_KEY")
    print("   - Supabase Dashboard → Database → Replication → 确认 market_snapshot 已启用")
    print("3. 如果 V4.1 字段为空，请等待 collector.py 运行一段时间（至少 1 分钟）")

if __name__ == "__main__":
    main()

