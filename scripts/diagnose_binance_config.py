"""
币安配置诊断脚本

用于检查币安配置是否正确保存到数据库，以及是否能正确读取
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

load_dotenv(dotenv_path=BASE_DIR / ".env")

def check_database_config():
    """检查数据库中的配置"""
    print("=" * 80)
    print("1️⃣ 检查数据库中的配置")
    print("=" * 80)
    
    try:
        from supabase import create_client
        
        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
        
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("❌ 未配置 SUPABASE_URL 或 SUPABASE_KEY")
            return False
        
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # 查询 system_settings 表中的币安配置
        try:
            response = supabase.table("system_settings")\
                .select("key, value, updated_at")\
                .in_("key", ["binance_api_key", "binance_api_secret", "binance_testnet", "binance_leverage"])\
                .execute()
        except Exception as e:
            print(f"❌ 查询 system_settings 表失败: {e}")
            print("   💡 可能的原因:")
            print("      1. system_settings 表不存在")
            print("      2. 数据库连接失败")
            print("      3. 权限不足")
            return None
        
        settings = response.data or []
        
        if not settings:
            print("❌ 数据库中没有找到币安配置")
            print("   💡 请在前端'系统设置'页面保存配置")
            print("   💡 保存后，配置会存储到 system_settings 表")
            return None
        
        print(f"✅ 找到 {len(settings)} 条配置记录:")
        config_dict = {}
        for setting in settings:
            key = setting.get("key", "")
            value = setting.get("value", "")
            updated = setting.get("updated_at", "N/A")
            
            # 安全显示：API Key 显示部分，Secret 显示长度
            if key == "binance_api_key":
                if value and len(value) > 10:
                    display_value = f"{value[:5]}...{value[-5:]}"
                else:
                    display_value = value[:3] + "..." if value else "N/A"
                config_dict["api_key"] = value
            elif key == "binance_api_secret":
                secret_len = len(value) if value else 0
                # 判断是加密还是明文
                if secret_len == 64:
                    display_value = f"[明文] 长度: {secret_len} 字符（未加密）"
                elif secret_len > 100:
                    display_value = f"[加密] 长度: {secret_len} 字符（已加密）"
                else:
                    display_value = f"[异常] 长度: {secret_len} 字符"
                config_dict["api_secret"] = value
            else:
                display_value = value
                if key == "binance_testnet":
                    config_dict["testnet"] = value.lower() in ("true", "1")
                elif key == "binance_leverage":
                    config_dict["leverage"] = int(value) if value else 10
            
            print(f"   - {key}: {display_value} (更新于: {updated[:19] if updated else 'N/A'})")
        
        return config_dict
        
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def check_config_manager():
    """检查配置管理器能否正确读取配置"""
    print("\n" + "=" * 80)
    print("2️⃣ 检查配置管理器读取")
    print("=" * 80)
    
    try:
        from supabase import create_client
        from scripts.binance_config_manager import get_config_manager
        
        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
        
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("❌ 未配置 Supabase")
            return False
        
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        config_manager = get_config_manager(supabase_client=supabase)
        
        # 强制刷新配置
        config = config_manager.get_config(force_refresh=True)
        
        if not config:
            print("❌ 配置管理器无法读取配置")
            return False
        
        api_key = config.get("api_key", "")
        api_secret = config.get("api_secret", "")
        testnet = config.get("testnet", False)
        leverage = config.get("leverage", 10)
        
        print(f"✅ 配置管理器读取成功:")
        print(f"   - API Key: {api_key[:5]}...{api_key[-5:] if len(api_key) > 10 else ''}")
        print(f"   - API Secret: {'已解密' if api_secret else '未解密'} (长度: {len(api_secret) if api_secret else 0})")
        print(f"   - 测试网: {testnet}")
        print(f"   - 杠杆: {leverage}x")
        
        # 检查 Secret 是否正确解密
        if api_secret:
            # Secret 应该是 64 字符（币安 Secret 的标准长度）
            if len(api_secret) == 64:
                print("   ✅ Secret 长度正确（64 字符）")
            else:
                print(f"   ⚠️  Secret 长度异常: {len(api_secret)} 字符（预期 64）")
                print("   ⚠️  可能是解密失败，Secret 仍然是加密状态")
        
        return config
        
    except Exception as e:
        print(f"❌ 配置管理器读取失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_api_with_config(config):
    """使用配置测试 API"""
    print("\n" + "=" * 80)
    print("3️⃣ 使用配置测试币安 API")
    print("=" * 80)
    
    if not config:
        print("❌ 没有配置可测试")
        return False
    
    api_key = config.get("api_key", "")
    api_secret = config.get("api_secret", "")
    testnet = config.get("testnet", False)
    
    if not api_key or not api_secret:
        print("❌ API Key 或 Secret 为空")
        return False
    
    try:
        if testnet:
            # 测试网：使用直接 API 调用
            import requests
            import time
            import hmac
            import hashlib
            from urllib.parse import urlencode
            
            base_url = "https://testnet.binancefuture.com"
            timestamp = int(time.time() * 1000)
            params = {"timestamp": timestamp}
            
            query_string = urlencode(params)
            signature = hmac.new(
                api_secret.encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            params["signature"] = signature
            headers = {"X-MBX-APIKEY": api_key}
            url = f"{base_url}/fapi/v2/account?{urlencode(params)}"
            
            print(f"   测试网 API Key: {api_key[:5]}...{api_key[-5:]}")
            print(f"   Secret 长度: {len(api_secret)} 字符")
            print(f"   正在测试连接...")
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                account_info = response.json()
                total_balance = float(account_info.get("totalWalletBalance", 0.0) or 0.0)
                print(f"   ✅ API 连接成功！账户余额: {total_balance:.2f} USDT")
                return True
            else:
                error_info = response.json() if response.content else {}
                error_code = error_info.get("code", "N/A")
                error_msg = error_info.get("msg", response.text)
                print(f"   ❌ API 连接失败: HTTP {response.status_code}")
                print(f"   错误代码: {error_code}")
                print(f"   错误信息: {error_msg}")
                
                if error_code == -2008:
                    print("\n   🔍 诊断:")
                    print("   - 错误代码 -2008 表示 'Invalid Api-Key ID'")
                    print("   - 可能的原因:")
                    print("     1. API Secret 解密失败（Secret 仍然是加密状态）")
                    print("     2. API Key 或 Secret 在保存时被修改")
                    print("     3. 数据库中的 Secret 加密/解密密钥不匹配")
                    print("\n   💡 建议:")
                    print("     1. 在前端重新保存一次配置")
                    print("     2. 检查后端日志，查看是否有解密错误")
                    print("     3. 如果问题持续，可以尝试删除配置后重新保存")
                
                return False
        else:
            print("   ⚠️  实盘模式，跳过测试（安全考虑）")
            return True
            
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("币安配置诊断工具")
    print("=" * 80)
    print()
    
    # 1. 检查数据库配置
    db_config = check_database_config()
    
    # 2. 检查配置管理器
    manager_config = check_config_manager()
    
    # 3. 测试 API
    if manager_config:
        test_api_with_config(manager_config)
    
    # 4. 对比分析
    print("\n" + "=" * 80)
    print("4️⃣ 对比分析")
    print("=" * 80)
    
    if db_config and manager_config:
        db_api_key = db_config.get("api_key", "")
        mgr_api_key = manager_config.get("api_key", "")
        
        if db_api_key == mgr_api_key:
            print("✅ 数据库配置和配置管理器读取的配置一致")
        else:
            print("❌ 配置不一致！")
            print(f"   数据库 API Key: {db_api_key[:10]}...")
            print(f"   管理器 API Key: {mgr_api_key[:10]}...")
            print("   ⚠️  可能是缓存问题，尝试清除缓存")
        
        db_secret_len = len(db_config.get("api_secret", ""))
        mgr_secret_len = len(manager_config.get("api_secret", ""))
        
        print(f"\n   Secret 长度对比:")
        print(f"   数据库: {db_secret_len} 字符（加密后）")
        print(f"   管理器: {mgr_secret_len} 字符（解密后）")
        
        if mgr_secret_len == 64:
            print("   ✅ Secret 解密成功（64 字符是币安 Secret 的标准长度）")
        elif mgr_secret_len > 100:
            print("   ⚠️  Secret 可能仍然是加密状态（长度 > 100）")
            print("   ⚠️  解密可能失败，Secret 没有被正确解密")
        else:
            print(f"   ⚠️  Secret 长度异常: {mgr_secret_len} 字符")
    
    print("\n" + "=" * 80)
    print("诊断完成")
    print("=" * 80)
    print("\n💡 如果配置读取失败，请：")
    print("   1. 检查后端日志，查看是否有错误")
    print("   2. 在前端重新保存一次配置")
    print("   3. 确认 system_settings 表存在且有数据")
    print("   4. 检查 .binance_key 文件是否存在（用于 Secret 加密/解密）")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] 诊断已中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] 诊断失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

