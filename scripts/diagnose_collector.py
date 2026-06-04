"""
采集器诊断脚本

用于诊断采集器无法运行的原因
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

print("=" * 60)
print("Rabbit Hunter 采集器诊断工具")
print("=" * 60)
print()

# 1. 检查环境变量
print("[1/6] 检查环境变量...")
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
binance_api_key = os.environ.get("BINANCE_API_KEY")
binance_api_secret = os.environ.get("BINANCE_API_SECRET")

print(f"  SUPABASE_URL: {'✅ 已配置' if supabase_url else '❌ 未配置'}")
print(f"  SUPABASE_KEY: {'✅ 已配置' if supabase_key else '❌ 未配置'}")
print(f"  BINANCE_API_KEY: {'✅ 已配置' if binance_api_key else '⚠️  未配置（可选）'}")
print(f"  BINANCE_API_SECRET: {'✅ 已配置' if binance_api_secret else '⚠️  未配置（可选）'}")
print()

# 2. 检查 Supabase 连接
print("[2/6] 检查 Supabase 连接...")
if supabase_url and supabase_key:
    try:
        from supabase import create_client
        import requests
        
        # 健康检查
        health_url = supabase_url.rstrip("/") + "/auth/v1/health"
        try:
            r = requests.get(health_url, timeout=10)
            if r.status_code in (200, 401, 403):
                print(f"  ✅ Supabase URL 可达 (状态码: {r.status_code})")
            else:
                print(f"  ❌ Supabase URL 不可达 (状态码: {r.status_code})")
        except Exception as e:
            print(f"  ❌ Supabase URL 健康检查失败: {e}")
        
        # 尝试创建客户端
        try:
            client = create_client(supabase_url, supabase_key)
            # 测试查询
            test_response = client.table("ai_training_data").select("id").limit(1).execute()
            print("  ✅ Supabase 连接成功，可以查询数据")
        except Exception as e:
            print(f"  ❌ Supabase 连接失败: {e}")
            if "404" in str(e) or "JSON could not be generated" in str(e):
                print("    可能原因：SUPABASE_URL 不正确")
            elif "401" in str(e) or "403" in str(e) or "permission" in str(e).lower():
                print("    可能原因：API key 无效或权限不足")
    except ImportError:
        print("  ❌ 无法导入 supabase 库，请运行: pip install supabase")
    except Exception as e:
        print(f"  ❌ 检查失败: {e}")
else:
    print("  ⚠️  跳过（环境变量未配置）")
print()

# 3. 检查依赖包
print("[3/6] 检查 Python 依赖包...")
required_packages = {
    "ccxt": "ccxt",
    "supabase": "supabase",
    "dotenv": "python-dotenv",
    "requests": "requests",
}

missing_packages = []
for module_name, package_name in required_packages.items():
    try:
        __import__(module_name)
        print(f"  ✅ {package_name}")
    except ImportError:
        print(f"  ❌ {package_name} (缺失)")
        missing_packages.append(package_name)

if missing_packages:
    print(f"\n  请安装缺失的包: pip install {' '.join(missing_packages)}")
print()

# 4. 检查 V4.3 模块
print("[4/6] 检查 V4.3 模块...")
v43_modules = [
    "v43_feature_extractor",
    "v43_score_calculator",
    "v43_hard_filters",
    "v43_decision_policy",
    "v43_weight_manager",
    "v43_chandelier_stop",
    "v43_position_manager",
]

scripts_dir = Path(__file__).parent
missing_modules = []
for module_name in v43_modules:
    module_path = scripts_dir / f"{module_name}.py"
    if module_path.exists():
        print(f"  ✅ {module_name}.py")
    else:
        print(f"  ❌ {module_name}.py (缺失)")
        missing_modules.append(module_name)

if missing_modules:
    print(f"\n  ⚠️  缺失的 V4.3 模块: {', '.join(missing_modules)}")
    print("  采集器将使用占位函数，部分功能可能不可用")
print()

# 5. 检查币安连接
print("[5/6] 检查币安连接...")
try:
    import ccxt
    
    # 测试公共 API（不需要 API Key）
    exchange_config = {
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
        },
    }
    exchange = ccxt.binanceusdm(exchange_config)
    
    try:
        # 尝试获取一个 ticker
        ticker = exchange.fetch_ticker("BTC/USDT")
        print(f"  ✅ 币安公共 API 连接成功 (BTC/USDT: ${ticker['last']:.2f})")
    except Exception as e:
        print(f"  ❌ 币安公共 API 连接失败: {e}")
        print("    可能原因：网络问题、VPN 未连接、或币安 API 限制")
except ImportError:
    print("  ❌ 无法导入 ccxt 库，请运行: pip install ccxt")
except Exception as e:
    print(f"  ❌ 检查失败: {e}")
print()

# 6. 检查文件权限和路径
print("[6/6] 检查文件权限和路径...")
collector_path = scripts_dir / "collector.py"
if collector_path.exists():
    print(f"  ✅ collector.py 存在: {collector_path}")
    if os.access(collector_path, os.R_OK):
        print("  ✅ collector.py 可读")
    else:
        print("  ❌ collector.py 不可读（权限问题）")
else:
    print(f"  ❌ collector.py 不存在: {collector_path}")

env_path = BASE_DIR / ".env"
if env_path.exists():
    print(f"  ✅ .env 文件存在: {env_path}")
    if os.access(env_path, os.R_OK):
        print("  ✅ .env 文件可读")
    else:
        print("  ❌ .env 文件不可读（权限问题）")
else:
    print(f"  ⚠️  .env 文件不存在: {env_path}")
    print("    请创建 .env 文件并配置环境变量")
print()

# 总结
print("=" * 60)
print("诊断总结")
print("=" * 60)

issues = []
if not supabase_url or not supabase_key:
    issues.append("❌ Supabase 环境变量未配置")
if missing_packages:
    issues.append(f"❌ 缺失 Python 包: {', '.join(missing_packages)}")
if missing_modules:
    issues.append(f"⚠️  缺失 V4.3 模块: {', '.join(missing_modules)}")

if issues:
    print("\n发现以下问题：")
    for issue in issues:
        print(f"  {issue}")
    print("\n建议：")
    if not supabase_url or not supabase_key:
        print("  1. 检查 .env 文件中的 SUPABASE_URL 和 SUPABASE_KEY")
    if missing_packages:
        print(f"  2. 安装缺失的包: pip install {' '.join(missing_packages)}")
    if missing_modules:
        print("  3. 确保所有 V4.3 模块文件存在于 scripts/ 目录")
else:
    print("\n✅ 所有检查通过！采集器应该可以正常运行。")
    print("\n如果采集器仍然无法运行，请：")
    print("  1. 查看采集器启动时的错误信息")
    print("  2. 检查网络连接（特别是币安 API）")
    print("  3. 检查 Supabase 数据库表是否已创建")

print()

