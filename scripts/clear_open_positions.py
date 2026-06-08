"""
清理数据库中的 OPEN 持仓记录

用途：
- 当币安测试网已全部平仓，但数据库中仍有 OPEN 状态的持仓时
- 将这些持仓更新为 CLOSED 状态，以便重新测试

用法：
  python scripts/clear_open_positions.py
"""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timezone

# 添加项目根目录到路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

load_dotenv()

def clear_open_positions():
    """清理所有 OPEN 状态的持仓"""
    print("=" * 80)
    print("清理数据库中的 OPEN 持仓记录")
    print("=" * 80)
    print()
    
    # 初始化 Supabase
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ERROR] 请配置 SUPABASE_URL 和 SUPABASE_KEY 在 .env 文件中")
        sys.exit(1)
    
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # 1. 查询所有 OPEN 状态的持仓
        print("📊 查询 OPEN 状态的持仓...")
        response = supabase.table("positions_v43").select(
            "id, symbol, side, entry_price, position_size, strategy_id, created_at"
        ).eq("status", "OPEN").execute()
        
        open_positions = response.data or []
        
        if not open_positions:
            print("✅ 没有找到 OPEN 状态的持仓，数据库已清理")
            return
        
        print(f"📋 找到 {len(open_positions)} 个 OPEN 状态的持仓：")
        print()
        for i, pos in enumerate(open_positions, 1):
            symbol = pos.get("symbol", "UNKNOWN")
            side = pos.get("side", "UNKNOWN")
            entry_price = pos.get("entry_price", 0)
            position_size = pos.get("position_size", 0)
            strategy_id = pos.get("strategy_id", "N/A")
            created_at = pos.get("created_at", "N/A")
            print(f"  {i}. {symbol:15s} | {side:5s} | 价格: {entry_price:.8f} | 数量: {position_size:.4f} | 策略: {strategy_id} | 创建: {created_at}")
        
        print()
        print("⚠️  警告：这将把所有 OPEN 状态的持仓更新为 CLOSED 状态")
        print("⚠️  请确认币安测试网已全部平仓！")
        print()
        
        # 2. 确认操作
        confirm = input("是否继续？(yes/no): ").strip().lower()
        if confirm not in ["yes", "y", "是"]:
            print("❌ 操作已取消")
            return
        
        # 3. 更新所有 OPEN 持仓为 CLOSED
        print()
        print("🔄 正在更新持仓状态...")
        
        now_iso = datetime.now(timezone.utc).isoformat()
        update_data = {
            "status": "CLOSED",
            "updated_at": now_iso,
            "exit_reason": "手动清理（币安测试网已平仓）",
        }
        
        # 批量更新
        updated_count = 0
        errors = []
        
        for pos in open_positions:
            pos_id = pos.get("id")
            symbol = pos.get("symbol", "UNKNOWN")
            
            if not pos_id:
                errors.append(f"{symbol}: 缺少 ID")
                continue
            
            try:
                supabase.table("positions_v43").update(update_data).eq("id", pos_id).execute()
                updated_count += 1
                print(f"  ✅ {symbol} 已更新为 CLOSED")
            except Exception as e:
                error_msg = f"{symbol}: {str(e)}"
                errors.append(error_msg)
                print(f"  ❌ {error_msg}")
        
        print()
        print("=" * 80)
        print("清理完成")
        print("=" * 80)
        print(f"✅ 成功更新: {updated_count} 个持仓")
        if errors:
            print(f"❌ 失败: {len(errors)} 个持仓")
            for error in errors:
                print(f"   - {error}")
        print()
        print("💡 提示：现在可以重新启动采集器进行测试")
        
    except Exception as e:
        print(f"[ERROR] 清理失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    try:
        clear_open_positions()
    except KeyboardInterrupt:
        print("\n[INFO] 操作已中断")
        sys.exit(0)

