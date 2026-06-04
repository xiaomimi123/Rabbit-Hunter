"""
V4.2 AI 参数调优执行脚本

用法：
    python scripts/run_ai_tuning.py

功能：
- 执行一次完整的 AI 参数调优流程
- 使用 Time Machine 评估当前配置和新配置
- 如果新配置更好，自动应用
- 记录调优历史到数据库
"""

import os
import sys
import traceback
from dotenv import load_dotenv

# 添加 scripts 目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def main():
    """主函数"""
    try:
        # 检查环境变量
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            print("❌ 未配置 Supabase URL 或 Key")
            print("   提示: 请检查 .env 文件中的 SUPABASE_URL 和 SUPABASE_KEY")
            return 1
        
        # 导入 Supabase
        try:
            from supabase import create_client
        except ImportError as e:
            print(f"❌ 无法导入 supabase 模块: {e}")
            print("   提示: 运行 pip install supabase")
            return 1
        
        # 创建 Supabase 客户端
        try:
            supabase = create_client(supabase_url, supabase_key)
        except Exception as e:
            print(f"❌ 创建 Supabase 客户端失败: {e}")
            print(f"   错误类型: {type(e).__name__}")
            traceback.print_exc()
            return 1
        
        # 导入调优模块
        try:
            from scripts.ai_tuner import apply_tuning
        except ImportError as e:
            print(f"❌ 无法导入 ai_tuner 模块: {e}")
            print(f"   详细错误:")
            traceback.print_exc()
            return 1
        
        print("🚀 开始 AI 参数调优...")
        print("=" * 50)
        
        # 执行调优
        try:
            result = apply_tuning(supabase)
        except Exception as e:
            print(f"❌ 调优过程发生异常: {e}")
            print(f"   错误类型: {type(e).__name__}")
            print(f"   详细错误:")
            traceback.print_exc()
            return 1
        
        if not result.get("success"):
            print(f"❌ 调优失败: {result.get('reason', '未知错误')}")
            if "errors" in result:
                print("   错误列表:")
                for error in result["errors"]:
                    print(f"     - {error}")
            return 1
        
        print("✅ 调优完成！")
        print("=" * 50)
        print(f"当前配置 WCS 分数: {result.get('current_score', 'N/A')}")
        print(f"新配置 WCS 分数: {result.get('new_score', 'N/A')}")
        
        improvement = result.get("improvement")
        if improvement is not None:
            if improvement > 0:
                print(f"📈 改进: +{improvement:.2f} (新配置更好)")
            elif improvement < 0:
                print(f"📉 变化: {improvement:.2f} (新配置较差)")
            else:
                print("➡️  变化: 0.00 (无变化)")
        
        print(f"应用状态: {'✅ 已应用' if result.get('is_applied') else '❌ 未应用（新配置未优于当前配置）'}")
        print("=" * 50)
        
        if result.get("is_applied"):
            print("📝 新配置已保存到 strategy_config.json")
            print("⚠️  请重启采集器以应用新配置")
        
        return 0
    
    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 发生未预期的错误: {e}")
        print(f"   错误类型: {type(e).__name__}")
        print(f"   详细错误:")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())

