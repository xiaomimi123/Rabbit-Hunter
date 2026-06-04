"""
币安交易执行器（V4.3）

功能：
- 开仓（LONG/SHORT）
- 平仓
- 止损/止盈设置
- 订单管理
- 错误处理和重试
"""

import os
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

import ccxt
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

# 用于直接 API 调用（测试网备用方案）
try:
    import requests
    import hmac
    import hashlib
    from urllib.parse import urlencode
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# 载入环境变量
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET")
BINANCE_TESTNET = os.environ.get("BINANCE_TESTNET", "false").lower() in ("true", "1")


class BinanceTrader:
    """
    币安交易执行器
    
    使用 CCXT 库执行币安合约交易
    """
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, testnet: bool = False, leverage: int = 10):
        """
        初始化交易器
        
        Args:
            api_key: 币安 API Key（如果为 None，从环境变量读取）
            api_secret: 币安 API Secret（如果为 None，从环境变量读取）
            testnet: 是否使用测试网
            leverage: 杠杆倍数（默认 10）
        """
        self.api_key = api_key or BINANCE_API_KEY
        self.api_secret = api_secret or BINANCE_API_SECRET
        self.testnet = testnet or BINANCE_TESTNET
        self.leverage = leverage or int(os.environ.get("BINANCE_LEVERAGE", "10"))
        
        if not self.api_key or not self.api_secret:
            raise ValueError("需要配置 BINANCE_API_KEY 和 BINANCE_API_SECRET")
        
        # 初始化交易所配置
        exchange_config = {
            "apiKey": self.api_key.strip() if self.api_key else None,  # 去除首尾空格
            "secret": self.api_secret.strip() if self.api_secret else None,  # 去除首尾空格
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",  # 告诉 CCXT 我们要做合约
                "adjustForTimeDifference": True,  # 自动调整时间差
            }
        }
        
        self.exchange = ccxt.binanceusdm(exchange_config)
        
        if self.testnet:
            # 1. 劫持 URL (补全所有缺少的路标)
            testnet_url = "https://testnet.binancefuture.com/fapi/v1"
            self.exchange.urls["api"] = {
                "fapiPublic": testnet_url,
                "fapiPrivate": testnet_url,
                "fapiPrivateV2": testnet_url,
                "fapiPrivateV3": testnet_url,
                "public": testnet_url,
                "private": testnet_url,
                "sapi": testnet_url,  # 🔥 新增：把现货接口也指向合约测试网
            }
            
            # 2. 🔥 核心修复：禁用 fetchCurrencies 🔥
            # 告诉 ccxt："别去查现货币种信息了，测试网没这个功能"
            # 这能直接跳过报错的 sapiGetCapitalConfigGetall 调用
            self.exchange.has["fetchCurrencies"] = False
            
            print(f"[INIT] 🟢 强制锁定: Binance Futures Testnet (已禁用 sapi)")
        else:
            print("[INFO] 使用币安实盘（⚠️ 注意风险）")
        
        # 同步服务器时间（解决时间戳错误）
        # 注意：由于 adjustForTimeDifference=True，CCXT 会自动处理时间差
        try:
            self.exchange.load_markets()
            # 获取服务器时间并计算时间差
            server_time = self.exchange.fetch_time()
            local_time = int(time.time() * 1000)  # 毫秒
            time_diff = server_time - local_time
            if abs(time_diff) > 1000:  # 如果时间差超过 1 秒
                print(f"[INFO] 检测到时间差: {time_diff}ms，CCXT 将自动调整")
        except Exception as e:
            # 如果 API Key 验证失败，这是正常的（可能在初始化时还未完全配置）
            # 由于 adjustForTimeDifference=True，CCXT 会在实际交易时自动处理时间差
            error_str = str(e)
            if "-2008" in error_str or "Invalid Api-Key" in error_str:
                # API Key 验证失败，但不影响后续交易（会在实际交易时验证）
                pass  # 静默处理，不显示警告
            else:
                print(f"[INFO] 时间同步检查跳过: {error_str}（CCXT 将自动处理时间差）")
        
        # 设置默认杠杆（全局）
        # 注意：币安可能不支持全局杠杆设置，杠杆会在开仓时按交易对设置
        try:
            self.set_leverage_all(self.leverage)
        except Exception as e:
            # 全局杠杆设置失败不影响功能（杠杆会在开仓时设置）
            error_str = str(e)
            if "fapiPrivate_post_leverage" in error_str or "has no attribute" in error_str:
                # CCXT 方法不存在，这是正常的（杠杆会在开仓时设置）
                pass  # 静默处理，不显示警告
            else:
                print(f"[INFO] 全局杠杆设置跳过（将在开仓时按交易对设置）")
    
    def _symbol_to_binance(self, symbol: str) -> str:
        """
        将 CCXT 格式转换为币安格式
        例如：TRB/USDT -> TRBUSDT
        """
        return symbol.replace("/", "")
    
    def _get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取持仓信息（兼容测试网和实盘）
        
        Args:
            symbol: 交易对符号（可选，如果提供则只返回该交易对的持仓）
        
        Returns:
            持仓列表
        """
        binance_symbol = self._symbol_to_binance(symbol) if symbol else None
        
        try:
            # 方法 1: 尝试使用 CCXT 标准方法
            if hasattr(self.exchange, 'fetch_positions'):
                positions = self.exchange.fetch_positions([symbol] if symbol else None)
                # CCXT 返回的格式可能不同，需要转换
                result = []
                for pos in positions:
                    if pos.get('contracts', 0) != 0:  # 有持仓
                        pos_symbol = pos.get('symbol', '').replace('/', '')
                        if not binance_symbol or pos_symbol == binance_symbol:
                            result.append({
                                "symbol": pos_symbol,
                                "positionAmt": pos.get('contracts', 0),
                                "entryPrice": pos.get('entryPrice', 0),
                                "markPrice": pos.get('markPrice', 0),
                                "leverage": pos.get('leverage', 1),
                                "unRealizedProfit": pos.get('unrealizedPnl', 0),
                            })
                return result
        except Exception as e:
            # CCXT 方法失败，尝试直接 API 调用
            pass
        
        # 方法 2: 使用直接 API 调用（测试网和实盘都支持）
        if not REQUESTS_AVAILABLE:
            raise Exception("需要 requests 库来获取持仓信息")
        
        try:
            import time
            import hmac
            import hashlib
            from urllib.parse import urlencode
            
            base_url = "https://testnet.binancefuture.com" if self.testnet else "https://fapi.binance.com"
            timestamp = int(time.time() * 1000)
            
            params = {"timestamp": timestamp}
            if binance_symbol:
                params["symbol"] = binance_symbol
            
            query_string = urlencode(params)
            signature = hmac.new(
                self.api_secret.encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            params["signature"] = signature
            headers = {"X-MBX-APIKEY": self.api_key}
            url = f"{base_url}/fapi/v2/positionRisk?{urlencode(params)}"
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                positions = response.json()
                # 过滤掉无持仓的
                return [pos for pos in positions if abs(float(pos.get("positionAmt", 0))) > 0.0001]
            else:
                error_info = response.json() if response.content else {}
                error_msg = error_info.get("msg", response.text)
                raise Exception(f"获取持仓失败: HTTP {response.status_code}, {error_msg}")
                
        except Exception as e:
            raise Exception(f"获取持仓失败: {e}")
    
    def fetch_balance(self) -> Dict[str, Any]:
        """
        获取账户余额
        
        在测试网环境下，使用直接 API 调用绕过 CCXT 的限制
        在实盘环境下，使用 CCXT 的标准方法
        
        Returns:
            余额字典，格式与 CCXT 兼容
        """
        if self.testnet and REQUESTS_AVAILABLE:
            # 测试网：使用直接 API 调用（绕过 CCXT 的限制）
            try:
                base_url = "https://testnet.binancefuture.com"
                endpoint = "/fapi/v2/account"
                
                timestamp = int(time.time() * 1000)
                params = {
                    "timestamp": timestamp,
                    "recvWindow": 10000
                }
                
                query_string = urlencode(params)
                signature = hmac.new(
                    self.api_secret.encode("utf-8"),
                    query_string.encode("utf-8"),
                    hashlib.sha256
                ).hexdigest()
                
                params["signature"] = signature
                headers = {"X-MBX-APIKEY": self.api_key}
                
                url = f"{base_url}{endpoint}?{urlencode(params)}"
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    account = response.json()
                    total_balance = float(account.get("totalWalletBalance", 0))
                    available_balance = float(account.get("availableBalance", 0))
                    
                    # 转换为 CCXT 格式
                    return {
                        "USDT": {
                            "free": available_balance,
                            "used": total_balance - available_balance,
                            "total": total_balance,
                        },
                        "total": {
                            "USDT": total_balance,
                        },
                        "free": {
                            "USDT": available_balance,
                        },
                        "used": {
                            "USDT": total_balance - available_balance,
                        },
                        "info": account,  # 保留原始信息
                    }
                else:
                    error = response.json() if response.content else {}
                    raise Exception(f"API 调用失败: HTTP {response.status_code}, {error.get('msg', response.text)}")
            except Exception as e:
                # 如果直接 API 调用失败，尝试使用 CCXT（可能会失败，但至少尝试了）
                print(f"[WARNING] 直接 API 调用失败，尝试 CCXT: {e}")
                return self.exchange.fetch_balance()
        else:
            # 实盘：使用 CCXT 标准方法
            return self.exchange.fetch_balance()
    
    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        设置单个交易对的杠杆
        
        Args:
            symbol: 交易对符号（CCXT 格式）
            leverage: 杠杆倍数（1-125）
            
        Returns:
            设置结果字典
        """
        # 验证杠杆范围
        if leverage < 1 or leverage > 125:
            raise ValueError(f"杠杆倍数必须在 1-125 之间，当前: {leverage}")
        
        try:
            # ✅ 使用 CCXT 标准方法（通用且安全）
            # 注意：币安要求先加载市场结构，确保 symbol 格式正确
            market = self.exchange.market(symbol)
            
            # 设置杠杆
            self.exchange.set_leverage(leverage, symbol)
            
            # 顺便设置逐仓 (ISOLATED)，防止测试网爆仓太快
            try:
                self.exchange.set_margin_mode("ISOLATED", symbol)
            except:
                pass  # 有些币种默认就是逐仓，忽略错误
            
            print(f"[RISK] {symbol} 杠杆已设置为 {leverage}x")
            return {
                "success": True,
                "symbol": symbol,
                "leverage": leverage,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] 设置杠杆失败: {symbol} - {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "symbol": symbol,
            }
    
    def set_leverage_all(self, leverage: int) -> Dict[str, Any]:
        """
        设置所有交易对的杠杆（全局设置）
        
        注意：币安不支持真正的全局杠杆设置，这里使用 BTC/USDT 作为代表
        
        Args:
            leverage: 杠杆倍数（1-125）
            
        Returns:
            设置结果字典
        """
        # 验证杠杆范围
        if leverage < 1 or leverage > 125:
            raise ValueError(f"杠杆倍数必须在 1-125 之间，当前: {leverage}")
        
        try:
            # ✅ 使用 CCXT 标准方法（使用 BTC/USDT 作为代表）
            # 注意：币安不支持真正的全局杠杆，这里只是设置一个代表交易对
            self.exchange.set_leverage(leverage, "BTC/USDT")
            
            # 更新实例杠杆
            self.leverage = leverage
            
            print(f"[TRADE] ✅ 杠杆设置成功（BTC/USDT 代表）: {leverage}x")
            print(f"[INFO] 注意：币安不支持全局杠杆，其他交易对将在开仓时单独设置")
            return {
                "success": True,
                "leverage": leverage,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            error_msg = str(e)
            print(f"[WARNING] 设置全局杠杆失败: {error_msg}（将在开仓时按交易对设置）")
            # 仍然更新实例杠杆，在开仓时会使用
            self.leverage = leverage
            return {
                "success": False,
                "error": error_msg,
                "leverage": leverage,
            }
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def open_position(
        self,
        symbol: str,
        side: str,  # 'LONG' or 'SHORT'
        quantity: float,
        order_type: str = 'MARKET',  # 'MARKET' or 'LIMIT'
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        开仓
        
        Args:
            symbol: 交易对符号（CCXT 格式，如 "TRB/USDT"）
            side: 方向（'LONG' 或 'SHORT'）
            quantity: 数量（币数）
            order_type: 订单类型（'MARKET' 或 'LIMIT'）
            price: 限价单价格（限价单必需）
            stop_loss: 止损价格（可选）
            take_profit: 止盈价格（可选）
        
        Returns:
            订单信息字典
        """
        binance_symbol = self._symbol_to_binance(symbol)
        
        # 验证交易对是否有效（在测试网可能不支持某些交易对）
        try:
            # 尝试加载市场信息，如果失败则说明交易对无效
            market = self.exchange.market(symbol)
            if not market or not market.get("active", True):
                raise ValueError(f"交易对 {symbol} 不可用或已停用")
        except Exception as e:
            error_msg = str(e)
            # 检查是否是 "Invalid symbol" 错误
            if "-1121" in error_msg or "Invalid symbol" in error_msg or "symbol" in error_msg.lower():
                raise ValueError(f"交易对 {symbol} 在币安测试网不支持或无效（错误: {error_msg}）")
            # 其他错误也抛出，但保留原始错误信息
            raise
        
        # 确定方向
        if side.upper() == "LONG":
            side_ccxt = "buy"
        elif side.upper() == "SHORT":
            side_ccxt = "sell"
        else:
            raise ValueError(f"无效的方向: {side}，必须是 'LONG' 或 'SHORT'")
        
        # 创建订单
        try:
            # 设置杠杆（在开仓前）
            try:
                self.set_leverage(symbol, self.leverage)
            except Exception as e:
                print(f"[WARNING] 设置杠杆失败（继续开仓）: {e}")
            
            if order_type.upper() == "MARKET":
                order = self.exchange.create_market_order(
                    symbol=binance_symbol,
                    side=side_ccxt,
                    amount=quantity,
                )
            elif order_type.upper() == "LIMIT":
                if price is None:
                    raise ValueError("限价单需要指定价格")
                order = self.exchange.create_limit_order(
                    symbol=binance_symbol,
                    side=side_ccxt,
                    amount=quantity,
                    price=price,
                )
            else:
                raise ValueError(f"不支持的订单类型: {order_type}")
            
            order_id = order.get("id")
            filled_price = order.get("price") or order.get("average")
            filled_quantity = order.get("filled", quantity)
            
            result = {
                "success": True,
                "order_id": str(order_id),
                "symbol": symbol,
                "side": side,
                "quantity": filled_quantity,
                "price": filled_price,
                "order_type": order_type,
                "status": order.get("status", "unknown"),
                "timestamp": datetime.now().isoformat(),
            }
            
            # 设置止损/止盈（如果提供）
            # 注意：需要等待持仓建立后再设置止损/止盈
            import time
            time.sleep(0.5)  # 等待 0.5 秒，确保持仓已建立
            
            if stop_loss:
                try:
                    # 重试机制：最多重试 3 次，每次间隔 0.5 秒
                    max_retries = 3
                    stop_loss_success = False
                    for attempt in range(max_retries):
                        try:
                            stop_result = self.set_stop_loss(symbol, stop_loss, side)
                            if stop_result.get("success"):
                                result["stop_loss"] = stop_loss
                                stop_loss_success = True
                                print(f"[TRADE] ✅ 止损设置成功: {symbol} @ {stop_loss}")
                                break
                            else:
                                error_msg = stop_result.get("error", "未知错误")
                                if "无持仓" in error_msg and attempt < max_retries - 1:
                                    # 持仓可能还没建立，等待后重试
                                    time.sleep(0.5)
                                    continue
                                else:
                                    raise Exception(error_msg)
                        except ValueError as e:
                            if "无持仓" in str(e) and attempt < max_retries - 1:
                                # 持仓可能还没建立，等待后重试
                                time.sleep(0.5)
                                continue
                            else:
                                raise
                    if not stop_loss_success:
                        raise Exception("止损设置失败：重试次数用尽")
                except Exception as e:
                    print(f"[WARNING] 设置止损失败: {symbol} - {e}")
                    result["stop_loss_error"] = str(e)
            
            if take_profit:
                try:
                    # 重试机制：最多重试 3 次，每次间隔 0.5 秒
                    max_retries = 3
                    take_profit_success = False
                    for attempt in range(max_retries):
                        try:
                            tp_result = self.set_take_profit(symbol, take_profit, side)
                            if tp_result.get("success"):
                                result["take_profit"] = take_profit
                                take_profit_success = True
                                print(f"[TRADE] ✅ 止盈设置成功: {symbol} @ {take_profit}")
                                break
                            else:
                                error_msg = tp_result.get("error", "未知错误")
                                if "无持仓" in error_msg and attempt < max_retries - 1:
                                    # 持仓可能还没建立，等待后重试
                                    time.sleep(0.5)
                                    continue
                                else:
                                    raise Exception(error_msg)
                        except ValueError as e:
                            if "无持仓" in str(e) and attempt < max_retries - 1:
                                # 持仓可能还没建立，等待后重试
                                time.sleep(0.5)
                                continue
                            else:
                                raise
                    if not take_profit_success:
                        raise Exception("止盈设置失败：重试次数用尽")
                except Exception as e:
                    print(f"[WARNING] 设置止盈失败: {symbol} - {e}")
                    result["take_profit_error"] = str(e)
            
            print(f"[TRADE] ✅ 开仓成功: {symbol} {side} {filled_quantity:.4f} @ {filled_price}")
            return result
            
        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] 开仓失败: {symbol} {side} - {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "symbol": symbol,
                "side": side,
                "timestamp": datetime.now().isoformat(),
            }
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def close_position(
        self,
        symbol: str,
        quantity: Optional[float] = None,  # None = 全部平仓
        order_type: str = 'MARKET',
    ) -> Dict[str, Any]:
        """
        平仓
        
        Args:
            symbol: 交易对符号
            quantity: 平仓数量（None = 全部平仓）
            order_type: 订单类型（'MARKET' 或 'LIMIT'）
        
        Returns:
            订单信息字典
        """
        binance_symbol = self._symbol_to_binance(symbol)
        
        # 获取当前持仓（使用新的兼容方法）
        positions = self._get_positions(symbol)
        current_position = None
        for pos in positions:
            pos_symbol = pos.get("symbol", "")
            if pos_symbol == binance_symbol:
                position_amt = float(pos.get("positionAmt", 0))
                if abs(position_amt) > 0:
                    current_position = {
                        "size": position_amt,
                        "side": "LONG" if position_amt > 0 else "SHORT",
                    }
                    break
        
        if not current_position:
            return {
                "success": False,
                "error": f"{symbol} 无持仓",
                "symbol": symbol,
            }
        
        # 确定平仓方向（与持仓相反）
        close_side = "sell" if current_position["side"] == "LONG" else "buy"
        close_quantity = quantity or abs(current_position["size"])
        
        try:
            if order_type.upper() == "MARKET":
                order = self.exchange.create_market_order(
                    symbol=binance_symbol,
                    side=close_side,
                    amount=close_quantity,
                )
            elif order_type.upper() == "LIMIT":
                # 限价平仓需要获取当前价格
                ticker = self.exchange.fetch_ticker(binance_symbol)
                price = ticker.get("last")
                if price is None:
                    raise ValueError("无法获取当前价格")
                order = self.exchange.create_limit_order(
                    symbol=binance_symbol,
                    side=close_side,
                    amount=close_quantity,
                    price=price,
                )
            else:
                raise ValueError(f"不支持的订单类型: {order_type}")
            
            order_id = order.get("id")
            filled_price = order.get("price") or order.get("average")
            filled_quantity = order.get("filled", close_quantity)
            
            print(f"[TRADE] ✅ 平仓成功: {symbol} {filled_quantity:.4f} @ {filled_price}")
            return {
                "success": True,
                "order_id": str(order_id),
                "symbol": symbol,
                "quantity": filled_quantity,
                "price": filled_price,
                "order_type": order_type,
                "status": order.get("status", "unknown"),
                "timestamp": datetime.now().isoformat(),
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] 平仓失败: {symbol} - {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "symbol": symbol,
                "timestamp": datetime.now().isoformat(),
            }
    
    def set_stop_loss(
        self,
        symbol: str,
        stop_price: float,
        side: str,  # 'LONG' or 'SHORT'
    ) -> Dict[str, Any]:
        """
        设置止损单（STOP_MARKET）
        
        Args:
            symbol: 交易对符号
            stop_price: 止损价格
            side: 方向（'LONG' 或 'SHORT'）
        
        Returns:
            订单信息字典
        """
        binance_symbol = self._symbol_to_binance(symbol)
        
        # 确定止损方向
        if side.upper() == "LONG":
            # 做多止损：价格下跌触发，卖出
            stop_side = "SELL"
        elif side.upper() == "SHORT":
            # 做空止损：价格上涨触发，买入
            stop_side = "BUY"
        else:
            raise ValueError(f"无效的方向: {side}")
        
        try:
            # 币安止损单（STOP_MARKET）
            # 注意：币安 API 需要先获取当前持仓数量
            positions = self._get_positions(symbol)
            position_amt = 0.0
            for pos in positions:
                pos_symbol = pos.get("symbol", "")
                if pos_symbol == binance_symbol:
                    position_amt = abs(float(pos.get("positionAmt", 0)))
                    break
            
            if position_amt == 0:
                raise ValueError(f"{symbol} 无持仓，无法设置止损")
            
            # 创建止损单
            order = self.exchange.create_order(
                symbol=binance_symbol,
                type="STOP_MARKET",
                side=stop_side.lower(),
                amount=position_amt,
                params={
                    "stopPrice": stop_price,
                    "closePosition": True,  # 平仓所有持仓
                }
            )
            
            # 注意：成功日志已在 open_position 中打印，这里不再重复
            return {
                "success": True,
                "order_id": str(order.get("id")),
                "symbol": symbol,
                "stop_price": stop_price,
                "timestamp": datetime.now().isoformat(),
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] 设置止损失败: {symbol} - {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "symbol": symbol,
            }
    
    def set_take_profit(
        self,
        symbol: str,
        take_profit_price: float,
        side: str,  # 'LONG' or 'SHORT'
    ) -> Dict[str, Any]:
        """
        设置止盈单（TAKE_PROFIT_MARKET）
        
        Args:
            symbol: 交易对符号
            take_profit_price: 止盈价格
            side: 方向（'LONG' 或 'SHORT'）
        
        Returns:
            订单信息字典
        """
        binance_symbol = self._symbol_to_binance(symbol)
        
        # 确定止盈方向
        if side.upper() == "LONG":
            # 做多止盈：价格上涨触发，卖出
            tp_side = "SELL"
        elif side.upper() == "SHORT":
            # 做空止盈：价格下跌触发，买入
            tp_side = "BUY"
        else:
            raise ValueError(f"无效的方向: {side}")
        
        try:
            # 获取当前持仓数量（使用新的兼容方法）
            positions = self._get_positions(symbol)
            position_amt = 0.0
            for pos in positions:
                pos_symbol = pos.get("symbol", "")
                if pos_symbol == binance_symbol:
                    position_amt = abs(float(pos.get("positionAmt", 0)))
                    break
            
            if position_amt == 0:
                raise ValueError(f"{symbol} 无持仓，无法设置止盈")
            
            # 创建止盈单
            order = self.exchange.create_order(
                symbol=binance_symbol,
                type="TAKE_PROFIT_MARKET",
                side=tp_side.lower(),
                amount=position_amt,
                params={
                    "stopPrice": take_profit_price,
                    "closePosition": True,  # 平仓所有持仓
                }
            )
            
            # 注意：成功日志已在 open_position 中打印，这里不再重复
            return {
                "success": True,
                "order_id": str(order.get("id")),
                "symbol": symbol,
                "take_profit_price": take_profit_price,
                "timestamp": datetime.now().isoformat(),
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] 设置止盈失败: {symbol} - {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "symbol": symbol,
            }
    
    def get_order_status(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """
        查询订单状态
        
        Args:
            symbol: 交易对符号
            order_id: 订单 ID
        
        Returns:
            订单信息字典
        """
        binance_symbol = self._symbol_to_binance(symbol)
        
        try:
            order = self.exchange.fetch_order(order_id, binance_symbol)
            return {
                "success": True,
                "order_id": order_id,
                "symbol": symbol,
                "status": order.get("status"),
                "filled": order.get("filled"),
                "remaining": order.get("remaining"),
                "price": order.get("price"),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "order_id": order_id,
                "symbol": symbol,
            }
    
    def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """
        取消订单
        
        Args:
            symbol: 交易对符号
            order_id: 订单 ID
        
        Returns:
            取消结果字典
        """
        binance_symbol = self._symbol_to_binance(symbol)
        
        try:
            result = self.exchange.cancel_order(order_id, binance_symbol)
            return {
                "success": True,
                "order_id": order_id,
                "symbol": symbol,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "order_id": order_id,
                "symbol": symbol,
            }


__all__ = ["BinanceTrader"]

