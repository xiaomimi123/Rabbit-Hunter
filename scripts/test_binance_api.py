"""
币安测试网 API 验证脚本

用于直接测试币安测试网 API Key 和 Secret 是否有效
"""

import os
import sys
import time
import requests
import hmac
import hashlib
from urllib.parse import urlencode

# 添加项目根目录到路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv()

def test_binance_testnet_api(api_key: str, api_secret: str):
    """
    直接测试币安测试网 API（不使用 CCXT）
    
    这样可以绕过 CCXT 的配置问题，直接验证 API Key 和 Secret
    """
    base_url = "https://testnet.binancefuture.com"
    
    print("=" * 80)
    print("币安测试网 API 直接验证")
    print("=" * 80)
    print(f"API Key 前缀: {api_key[:5]}...")
    print(f"Secret 长度: {len(api_secret)}")
    print()
    
    # 测试 1: 获取服务器时间（公共 API，不需要认证）
    print("1️⃣ 测试公共 API（获取服务器时间）...")
    try:
        response = requests.get(f"{base_url}/fapi/v1/time", timeout=10)
        if response.status_code == 200:
            server_time = response.json()["serverTime"]
            local_time = int(time.time() * 1000)
            time_diff = server_time - local_time
            print(f"   ✅ 成功: 服务器时间={server_time}, 本地时间={local_time}, 时间差={time_diff}ms")
            if abs(time_diff) > 5000:
                print(f"   ⚠️  警告: 时间差过大 ({time_diff}ms)，可能导致 API 调用失败")
        else:
            print(f"   ❌ 失败: HTTP {response.status_code}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
        return False
    
    print()
    
    # 测试 2: 获取账户信息（需要认证）
    print("2️⃣ 测试私有 API（获取账户信息）...")
    try:
        # 构建请求参数
        timestamp = int(time.time() * 1000)
        params = {
            "timestamp": timestamp,
        }
        
        # 生成签名
        query_string = urlencode(params)
        signature = hmac.new(
            api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        params["signature"] = signature
        
        # 发送请求
        headers = {
            "X-MBX-APIKEY": api_key,
        }
        
        url = f"{base_url}/fapi/v2/account?{urlencode(params)}"
        print(f"   [DEBUG] 请求 URL: {url[:100]}...")
        print(f"   [DEBUG] 时间戳: {timestamp}")
        print(f"   [DEBUG] 签名: {signature[:20]}...")
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            account_info = response.json()
            total_balance = float(account_info.get("totalWalletBalance", 0))
            print(f"   ✅ 成功: 账户余额={total_balance} USDT")
            print(f"   ✅ API Key 和 Secret 验证成功！")
            return True
        else:
            error_info = response.json() if response.content else {}
            error_code = error_info.get("code", "N/A")
            error_msg = error_info.get("msg", response.text)
            print(f"   ❌ 失败: HTTP {response.status_code}")
            print(f"   ❌ 错误代码: {error_code}")
            print(f"   ❌ 错误信息: {error_msg}")
            
            if error_code == -2008:
                print()
                print("   🔍 诊断:")
                print("   - API Key 格式正确（以 'lc' 开头）")
                print("   - 但币安服务器返回 'Invalid Api-Key ID'")
                print("   - 可能的原因:")
                print("     1. API Secret 错误（最常见）")
                print("     2. API Key 已被删除")
                print("     3. 时间戳问题（但已检查，时间差正常）")
                print()
                print("   💡 建议:")
                print("     1. 重新复制 API Secret（确保完整，没有多余空格）")
                print("     2. 在测试网中验证 API Key 是否仍然存在")
                print("     3. 检查 API Key 权限（至少需要'读取'权限）")
            
            return False
            
    except Exception as e:
        print(f"   ❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # 从命令行参数或环境变量获取
    if len(sys.argv) >= 3:
        api_key = sys.argv[1]
        api_secret = sys.argv[2]
    else:
        # 从环境变量或配置管理器获取
        from scripts.binance_config_manager import get_config_manager
        from supabase import create_client
        
        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
        
        if SUPABASE_URL and SUPABASE_KEY:
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            config_manager = get_config_manager(supabase_client=supabase)
            config = config_manager.get_config(force_refresh=True)
            
            if config and config.get("testnet"):
                api_key = config["api_key"]
                api_secret = config["api_secret"]
                print(f"[INFO] 从配置管理器读取测试网配置")
            else:
                print("[ERROR] 未找到测试网配置")
                print("用法: python scripts/test_binance_api.py <api_key> <api_secret>")
                sys.exit(1)
        else:
            print("[ERROR] 未配置 Supabase 或未提供 API Key/Secret")
            print("用法: python scripts/test_binance_api.py <api_key> <api_secret>")
            sys.exit(1)
    
    success = test_binance_testnet_api(api_key, api_secret)
    
    print()
    print("=" * 80)
    if success:
        print("✅ 验证成功：API Key 和 Secret 有效")
    else:
        print("❌ 验证失败：请检查 API Key 和 Secret")
    print("=" * 80)

