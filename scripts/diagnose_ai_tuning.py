"""
AI 调优诊断脚本

用于诊断 AI 调优脚本可能遇到的问题
"""

import os
import sys
from dotenv import load_dotenv

# 添加 scripts 目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_environment():
    """检查环境变量"""
    print("=" * 60)
    print("1. 检查环境变量")
    print("=" * 60)
    
    load_dotenv()
    
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY")
    deepseek_enabled = os.environ.get("DEEPSEEK_ENABLED", "0")
    
    print(f"SUPABASE_URL: {'✅ 已设置' if supabase_url else '❌ 未设置'}")
    if supabase_url:
        print(f"  值: {supabase_url[:30]}...")
    
    print(f"SUPABASE_KEY: {'✅ 已设置' if supabase_key else '❌ 未设置'}")
    if supabase_key:
        print(f"  值: {supabase_key[:20]}...")
    
    print(f"DEEPSEEK_API_KEY: {'✅ 已设置' if deepseek_api_key else '❌ 未设置'}")
    if deepseek_api_key:
        print(f"  值: {deepseek_api_key[:20]}...")
    
    print(f"DEEPSEEK_ENABLED: {deepseek_enabled}")
    
    return supabase_url and supabase_key


def check_imports():
    """检查必要的导入"""
    print("\n" + "=" * 60)
    print("2. 检查 Python 模块导入")
    print("=" * 60)
    
    errors = []
    
    # 检查基础模块
    try:
        import json
        print("✅ json")
    except ImportError as e:
        errors.append(f"json: {e}")
        print(f"❌ json: {e}")
    
    try:
        import requests
        print("✅ requests")
    except ImportError as e:
        errors.append(f"requests: {e}")
        print(f"❌ requests: {e}")
        print("   提示: 运行 pip install requests")
    
    try:
        from supabase import create_client
        print("✅ supabase")
    except ImportError as e:
        errors.append(f"supabase: {e}")
        print(f"❌ supabase: {e}")
        print("   提示: 运行 pip install supabase")
    
    # 检查项目模块
    try:
        from scripts.ai_tuner import load_strategy_config, prepare_tuning_data
        print("✅ scripts.ai_tuner")
    except ImportError as e:
        errors.append(f"scripts.ai_tuner: {e}")
        print(f"❌ scripts.ai_tuner: {e}")
        print(f"   错误详情: {e}")
    
    try:
        from scripts.time_machine import replay_history, SimulationConfig
        print("✅ scripts.time_machine")
    except ImportError as e:
        errors.append(f"scripts.time_machine: {e}")
        print(f"❌ scripts.time_machine: {e}")
        print(f"   错误详情: {e}")
        import traceback
        traceback.print_exc()
    
    return len(errors) == 0


def check_config_file():
    """检查配置文件"""
    print("\n" + "=" * 60)
    print("3. 检查配置文件")
    print("=" * 60)
    
    config_path = "strategy_config.json"
    
    if not os.path.exists(config_path):
        print(f"❌ 配置文件不存在: {config_path}")
        print("   提示: 正在创建默认配置文件...")
        try:
            from scripts.ai_tuner import DEFAULT_CONFIG, save_strategy_config
            save_strategy_config(DEFAULT_CONFIG, config_path)
            print(f"   ✅ 已创建默认配置文件: {config_path}")
        except Exception as e:
            print(f"   ❌ 创建配置文件失败: {e}")
            print("   提示: 请手动创建 strategy_config.json 文件")
            return False
    
    print(f"✅ 配置文件存在: {config_path}")
    
    try:
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        print(f"✅ 配置文件格式正确")
        print(f"   参数数量: {len(config)}")
        
        required_params = [
            "atr_multiplier_p2",
            "atr_multiplier_p3a_early",
            "atr_multiplier_p3a_normal",
            "atr_multiplier_p3b",
            "structure_gap_threshold",
            "phase_age_max_candles",
        ]
        
        missing = []
        for param in required_params:
            if param not in config:
                missing.append(param)
            else:
                print(f"   ✅ {param} = {config[param]}")
        
        if missing:
            print(f"   ❌ 缺少参数: {', '.join(missing)}")
            return False
        
        return True
    except json.JSONDecodeError as e:
        print(f"❌ 配置文件 JSON 格式错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 读取配置文件失败: {e}")
        return False


def check_supabase_connection():
    """检查 Supabase 连接"""
    print("\n" + "=" * 60)
    print("4. 检查 Supabase 连接")
    print("=" * 60)
    
    try:
        from supabase import create_client
        load_dotenv()
        
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            print("❌ Supabase 配置缺失")
            return False
        
        supabase = create_client(supabase_url, supabase_key)
        
        # 测试连接
        response = supabase.table("ai_evolution_logs").select("id").limit(1).execute()
        print("✅ Supabase 连接成功")
        
        # 检查表是否存在
        tables_to_check = ["ai_evolution_logs", "ai_training_data"]
        for table in tables_to_check:
            try:
                supabase.table(table).select("id").limit(1).execute()
                print(f"   ✅ 表 {table} 存在")
            except Exception as e:
                print(f"   ❌ 表 {table} 不存在或无法访问: {e}")
                return False
        
        return True
    except Exception as e:
        print(f"❌ Supabase 连接失败: {e}")
        print(f"   错误类型: {type(e).__name__}")
        import traceback
        print(f"   详细错误:\n{traceback.format_exc()}")
        return False


def check_data_availability():
    """检查数据可用性"""
    print("\n" + "=" * 60)
    print("5. 检查数据可用性")
    print("=" * 60)
    
    try:
        from supabase import create_client
        from scripts.ai_tuner import prepare_tuning_data
        load_dotenv()
        
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            print("❌ Supabase 配置缺失")
            return False
        
        supabase = create_client(supabase_url, supabase_key)
        
        print("正在准备调优数据（可能需要几秒钟）...")
        tuning_data = prepare_tuning_data(supabase, days=7)
        
        data_points = tuning_data.get("data_points", 0)
        print(f"✅ 数据准备完成")
        print(f"   数据点数量: {data_points}")
        
        if data_points < 100:
            print(f"   ⚠️  数据点不足（需要至少 100 个）")
            return False
        
        print(f"   ✅ 数据点充足")
        return True
    except Exception as e:
        print(f"❌ 数据准备失败: {e}")
        print(f"   错误类型: {type(e).__name__}")
        import traceback
        print(f"   详细错误:\n{traceback.format_exc()}")
        return False


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("AI 调优诊断工具")
    print("=" * 60)
    print()
    
    results = []
    
    # 1. 环境变量
    results.append(("环境变量", check_environment()))
    
    # 2. 模块导入
    results.append(("模块导入", check_imports()))
    
    # 3. 配置文件
    results.append(("配置文件", check_config_file()))
    
    # 4. Supabase 连接
    results.append(("Supabase 连接", check_supabase_connection()))
    
    # 5. 数据可用性
    results.append(("数据可用性", check_data_availability()))
    
    # 总结
    print("\n" + "=" * 60)
    print("诊断总结")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("✅ 所有检查通过！可以运行 python scripts/run_ai_tuning.py")
    else:
        print("❌ 部分检查失败，请根据上述提示修复问题")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())

