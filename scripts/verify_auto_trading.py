"""
自动交易功能验证脚本

用于快速检查自动交易功能的配置和状态
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

load_dotenv(dotenv_path=BASE_DIR / ".env")

def check_env_variable():
    """检查环境变量"""
    print("=" * 80)
    print("1️⃣ 检查环境变量")
    print("=" * 80)
    
    enable_auto_trading = os.environ.get("ENABLE_AUTO_TRADING", "false").lower()
    
    if enable_auto_trading in ("true", "1"):
        print("✅ ENABLE_AUTO_TRADING=true")
        return True
    else:
        print("❌ ENABLE_AUTO_TRADING=false 或未设置")
        print("   需要设置: ENABLE_AUTO_TRADING=true")
        return False

def check_binance_config():
    """检查币安配置"""
    print("\n" + "=" * 80)
    print("2️⃣ 检查币安 API 配置")
    print("=" * 80)
    
    try:
        from supabase import create_client
        from scripts.binance_config_manager import get_config_manager
        
        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
        
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("❌ 未配置 SUPABASE_URL 或 SUPABASE_KEY")
            return False
        
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        config_manager = get_config_manager(supabase_client=supabase)
        config = config_manager.get_config(force_refresh=True)
        
        if not config:
            print("❌ 未找到币安 API 配置")
            print("   请在前端'系统设置'页面配置币安 API")
            return False
        
        api_key = config.get("api_key", "")
        testnet = config.get("testnet", False)
        leverage = config.get("leverage", 10)
        
        print(f"✅ API Key: {api_key[:10]}...{api_key[-5:] if len(api_key) > 15 else ''}")
        print(f"✅ 测试网模式: {'是' if testnet else '否'}")
        print(f"✅ 杠杆: {leverage}x")
        
        return True
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        return False

def test_binance_connection():
    """测试币安 API 连接"""
    print("\n" + "=" * 80)
    print("3️⃣ 测试币安 API 连接")
    print("=" * 80)
    
    try:
        from supabase import create_client
        from scripts.binance_config_manager import get_config_manager
        from scripts.binance_trader import BinanceTrader
        
        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
        
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("❌ 未配置 Supabase")
            return False
        
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        config_manager = get_config_manager(supabase_client=supabase)
        config = config_manager.get_config(force_refresh=True)
        
        if not config:
            print("❌ 未找到币安配置")
            return False
        
        trader = BinanceTrader(
            api_key=config["api_key"],
            api_secret=config["api_secret"],
            testnet=config["testnet"],
            leverage=config.get("leverage", 10),
        )
        
        # 测试获取余额（使用直接 API 调用，绕过 CCXT 的问题）
        try:
            if config["testnet"]:
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
                    config["api_secret"].encode('utf-8'),
                    query_string.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                
                params["signature"] = signature
                headers = {"X-MBX-APIKEY": config["api_key"]}
                url = f"{base_url}/fapi/v2/account?{urlencode(params)}"
                
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    account_info = response.json()
                    total_balance = float(account_info.get("totalWalletBalance", 0.0) or 0.0)
                    available_balance = float(account_info.get("availableBalance", 0.0) or 0.0)
                    
                    print(f"✅ API 连接成功（测试网）")
                    print(f"   总资产: {total_balance:.2f} USDT")
                    print(f"   可用余额: {available_balance:.2f} USDT")
                    
                    if total_balance < 100:
                        print("⚠️  警告: 账户余额较低，可能影响开仓")
                    
                    return True
                else:
                    error_info = response.json() if response.content else {}
                    error_code = error_info.get("code", "N/A")
                    error_msg = error_info.get("msg", response.text)
                    print(f"❌ API 连接失败: HTTP {response.status_code}")
                    print(f"   错误代码: {error_code}")
                    print(f"   错误信息: {error_msg}")
                    
                    if error_code == -2008:
                        print("\n💡 提示:")
                        print("   - 检查 API Key 是否正确")
                        print("   - 确认已勾选'测试网'选项")
                        print("   - 测试网 API Key 通常以 'lc' 开头")
                        print("   - 可以运行 test_api_key.py 验证 API Key")
                    
                    return False
            else:
                # 实盘：使用 CCXT
                balance = trader.exchange.fetch_balance()
                usdt_info = balance.get("USDT") or balance.get("USDT:USDT") or {}
                total_balance = float(usdt_info.get("total", 0.0))
                available_balance = float(usdt_info.get("free", 0.0))
                
                print(f"✅ API 连接成功（实盘）")
                print(f"   总资产: {total_balance:.2f} USDT")
                print(f"   可用余额: {available_balance:.2f} USDT")
                
                if total_balance < 100:
                    print("⚠️  警告: 账户余额较低，可能影响开仓")
                
                return True
        except Exception as e:
            print(f"❌ API 连接失败: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_recent_positions():
    """检查最近的持仓记录"""
    print("\n" + "=" * 80)
    print("4️⃣ 检查最近的持仓记录")
    print("=" * 80)
    
    try:
        from supabase import create_client
        
        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
        
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("❌ 未配置 Supabase")
            return False
        
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # 查询最近的持仓（不包含 trade_status，因为可能不存在）
        try:
            response = supabase.table("positions_v43")\
                .select("symbol, side, entry_price, position_size, stop_price, strategy_id, created_at")\
                .eq("status", "OPEN")\
                .order("created_at", desc=True)\
                .limit(5)\
                .execute()
        except Exception as e:
            # 如果查询失败，尝试不包含可能不存在的字段
            print(f"⚠️  查询时遇到问题，尝试简化查询: {e}")
            response = supabase.table("positions_v43")\
                .select("symbol, side, entry_price, strategy_id, created_at")\
                .eq("status", "OPEN")\
                .order("created_at", desc=True)\
                .limit(5)\
                .execute()
        
        positions = response.data or []
        
        if positions:
            print(f"✅ 找到 {len(positions)} 个持仓:")
            for pos in positions:
                symbol = pos.get("symbol", "N/A")
                side = pos.get("side", "N/A")
                strategy = pos.get("strategy_id", "N/A")
                entry_price = pos.get("entry_price", 0)
                created = pos.get("created_at", "N/A")
                
                created_str = created[:19] if created and len(created) > 19 else str(created)
                print(f"   - {symbol} | {side} | {strategy} | 价格: {entry_price} | {created_str}")
        else:
            print("ℹ️  暂无持仓记录（这是正常的，如果系统刚启动）")
        
        return True
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_recent_trade_scores():
    """检查最近的交易评分记录"""
    print("\n" + "=" * 80)
    print("5️⃣ 检查最近的交易评分记录")
    print("=" * 80)
    
    try:
        from supabase import create_client
        
        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
        
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("❌ 未配置 Supabase")
            return False
        
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # 查询最近的交易评分
        response = supabase.table("trade_scores_v43")\
            .select("symbol, strategy_id, side, strategy_score, final_score, decision_policy, created_at")\
            .not_.is_("strategy_id", "null")\
            .order("created_at", desc=True)\
            .limit(5)\
            .execute()
        
        scores = response.data or []
        
        if scores:
            print(f"✅ 找到 {len(scores)} 条策略记录:")
            for score in scores:
                symbol = score.get("symbol", "N/A")
                strategy = score.get("strategy_id", "N/A")
                side = score.get("side", "N/A")
                strategy_score = score.get("strategy_score")
                
                # 处理 None 值
                if strategy_score is None:
                    strategy_score = score.get("final_score", 0)
                    if strategy_score is None:
                        strategy_score = 0
                
                try:
                    strategy_score_float = float(strategy_score) if strategy_score is not None else 0.0
                except (ValueError, TypeError):
                    strategy_score_float = 0.0
                
                decision = score.get("decision_policy", {})
                if isinstance(decision, str):
                    try:
                        import json
                        decision = json.loads(decision)
                    except:
                        decision = {}
                
                should_trade = decision.get("should_trade", False) if isinstance(decision, dict) else False
                created = score.get("created_at", "N/A")
                
                trade_status = "✅ TRADE" if should_trade else "⏸️ SKIP"
                created_str = created[:19] if created and len(str(created)) > 19 else str(created)
                print(f"   - {symbol} | {strategy} | {side} | Score: {strategy_score_float:.1f} | {trade_status} | {created_str}")
        else:
            print("ℹ️  暂无策略记录（这是正常的，如果系统刚启动）")
        
        return True
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def generate_report(results):
    """生成验证报告"""
    print("\n" + "=" * 80)
    print("📊 验证报告")
    print("=" * 80)
    
    total = len(results)
    passed = sum(1 for r in results if r)
    
    print(f"\n总计: {total} 项检查")
    print(f"通过: {passed} 项")
    print(f"失败: {total - passed} 项")
    
    if passed == total:
        print("\n✅ 所有检查通过！系统已准备好进行自动交易。")
        print("\n下一步:")
        print("1. 启动采集器: run_collector.bat")
        print("2. 观察日志，等待交易信号")
        print("3. 验证自动开仓功能")
    else:
        print("\n⚠️  部分检查未通过，请根据上述提示修复问题。")
        print("\n常见问题:")
        print("1. ENABLE_AUTO_TRADING 未设置: 运行 add_auto_trading.bat")
        print("2. 币安 API 未配置: 在前端'系统设置'页面配置")
        print("3. API 连接失败: 检查 API Key 和 Secret 是否正确")

def main():
    """主函数"""
    try:
        print("\n" + "=" * 80)
        print("Rabbit Hunter V4.5 自动交易功能验证")
        print("=" * 80)
        print()
        
        results = []
        
        # 检查环境变量
        try:
            results.append(check_env_variable())
        except Exception as e:
            print(f"[ERROR] 环境变量检查失败: {e}")
            results.append(False)
        
        # 检查币安配置
        try:
            results.append(check_binance_config())
        except Exception as e:
            print(f"[ERROR] 币安配置检查失败: {e}")
            results.append(False)
        
        # 测试币安连接
        try:
            results.append(test_binance_connection())
        except Exception as e:
            print(f"[ERROR] 币安连接测试失败: {e}")
            results.append(False)
        
        # 检查持仓记录
        try:
            results.append(check_recent_positions())
        except Exception as e:
            print(f"[ERROR] 持仓记录检查失败: {e}")
            results.append(False)
        
        # 检查交易评分
        try:
            results.append(check_recent_trade_scores())
        except Exception as e:
            print(f"[ERROR] 交易评分检查失败: {e}")
            results.append(False)
        
        # 生成报告
        generate_report(results)
        
        print("\n" + "=" * 80)
    except Exception as e:
        print(f"\n[ERROR] 验证过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] 验证已中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] 验证失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

