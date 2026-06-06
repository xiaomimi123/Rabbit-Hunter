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
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime

import ccxt
from dotenv import load_dotenv


# ccxt exception classes that are safe to retry (truly transient).
# Anything else (ExchangeError, BadSymbol, InsufficientFunds, ValueError, ...) is deterministic
# and will not succeed on retry — those bubble up immediately.
_RETRYABLE_EXC = (
    ccxt.NetworkError,
    ccxt.RequestTimeout,
    ccxt.DDoSProtection,
    ccxt.ExchangeNotAvailable,
)


# Substrings in error messages that indicate "this clientOrderId was already accepted" — Binance
# returns these when a previous network-timed-out request actually went through. Treat as success.
_DUPLICATE_ORDER_HINTS = (
    "-2010",  # NEW_ORDER_REJECTED
    "-2011",  # CANCEL_REJECTED
    "-4015",  # Client order id is not valid
    "-5022",  # Due to the order could not be filled immediately
    "duplicate clientOrderId",
    "Order already exists",
    "DUPLICATE_ORDER",
)

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

        # 10s hard timeout on every ccxt HTTP call — without this, a hung TCP connection
        # blocks the calling thread indefinitely.
        self.exchange.timeout = 10000  # milliseconds

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

        仅在调用 raw fapi/sapi 端点时使用。所有 ccxt 统一方法（create_*_order,
        fetch_ticker, fetch_order 等）应该传 unified symbol "BTC/USDT"。
        """
        return symbol.replace("/", "")

    @staticmethod
    def _is_duplicate_order_error(err: Exception) -> bool:
        """Binance 在 clientOrderId 已存在 / 之前重试已成功时返回的错误."""
        msg = str(err)
        return any(hint in msg for hint in _DUPLICATE_ORDER_HINTS)

    @staticmethod
    def make_client_order_tag(prefix: str = "rh") -> str:
        """
        生成 ccxt newClientOrderId 用的稳定字符串。
        调用方应在 "一次逻辑下单" 的开头生成一次，整个 retry 链路复用同一个 tag —
        这样网络超时后重试不会被 broker 视为新订单。
        Binance 上限 36 字符，允许 [A-Za-z0-9.-_]。
        """
        return f"{prefix}-{uuid.uuid4().hex[:12]}"

    def _safe_create_order(
        self,
        symbol: str,                    # unified, e.g. "BTC/USDT"
        side: str,                      # "buy" or "sell"
        order_type: str,                # "MARKET" / "LIMIT" / "STOP_MARKET" / "TAKE_PROFIT_MARKET"
        amount: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        reduce_only: bool = False,
        client_order_tag: Optional[str] = None,
        max_attempts: int = 3,
    ) -> Dict[str, Any]:
        """
        所有下单的唯一入口。修四个长期 bug：
          1) ccxt 接收 unified symbol（不是拼接的 BTCUSDT）
          2) amount/price/stopPrice 走 exchange.*_to_precision，避免 stepSize/tickSize 拒单
          3) 校验 market.limits.amount.min / cost.min，提前拒绝
          4) newClientOrderId 幂等键 — 网络超时重试不会重复成交
          5) retry 只针对 NetworkError/RequestTimeout/DDoSProtection；其它异常立刻 fail
          6) 重试时若 broker 回 "duplicate clientOrderId" → 视为之前重试已成功

        Returns:
            {
                "success": bool,
                "order_id": str | None,
                "client_order_id": str,
                "filled": float,           # 仅成功
                "price": float | None,     # 仅成功
                "raw": dict,               # ccxt 返回原文（成功时）
                "error": str,              # 仅失败
                "error_kind": "TRANSIENT" | "PERMANENT" | "DUPLICATE",
            }
        """
        # ── 0. 校验 / 解析 market ─────────────────────────────────────
        try:
            market = self.exchange.market(symbol)
        except Exception as e:
            return {
                "success": False,
                "error": f"unknown symbol {symbol}: {e}",
                "error_kind": "PERMANENT",
            }
        if not market or not market.get("active", True):
            return {
                "success": False,
                "error": f"symbol {symbol} inactive or unavailable",
                "error_kind": "PERMANENT",
            }

        # ── 1. precision 规整 ─────────────────────────────────────────
        try:
            amount_str = self.exchange.amount_to_precision(symbol, amount)
            amount_f = float(amount_str)
        except Exception as e:
            return {
                "success": False,
                "error": f"amount_to_precision({amount}) failed: {e}",
                "error_kind": "PERMANENT",
            }

        price_f: Optional[float] = None
        if price is not None:
            try:
                price_f = float(self.exchange.price_to_precision(symbol, price))
            except Exception as e:
                return {
                    "success": False,
                    "error": f"price_to_precision({price}) failed: {e}",
                    "error_kind": "PERMANENT",
                }

        stop_price_f: Optional[float] = None
        if stop_price is not None:
            try:
                stop_price_f = float(self.exchange.price_to_precision(symbol, stop_price))
            except Exception as e:
                return {
                    "success": False,
                    "error": f"price_to_precision(stop={stop_price}) failed: {e}",
                    "error_kind": "PERMANENT",
                }

        # ── 2. limits 校验 ────────────────────────────────────────────
        limits = market.get("limits", {}) or {}
        amount_min = (limits.get("amount") or {}).get("min")
        cost_min = (limits.get("cost") or {}).get("min")
        if amount_min and amount_f < float(amount_min):
            return {
                "success": False,
                "error": f"amount {amount_f} below min {amount_min}",
                "error_kind": "PERMANENT",
            }
        # 估算 notional 用的参考价：
        #   LIMIT → price_f
        #   STOP_MARKET / TAKE_PROFIT_MARKET → stop_price_f（触发价 ≈ 成交价）
        #   MARKET → fetch_ticker last
        ref_price = price_f or stop_price_f
        if ref_price is None and cost_min:
            try:
                ticker = self.exchange.fetch_ticker(symbol) or {}
                last = ticker.get("last")
                if last is not None:
                    ref_price = float(last) or None
            except Exception:
                ref_price = None
        if cost_min and ref_price:
            notional = amount_f * ref_price
            if notional < float(cost_min):
                return {
                    "success": False,
                    "error": f"notional {notional:.4f} below min cost {cost_min}",
                    "error_kind": "PERMANENT",
                }

        # ── 3. 幂等键 ─────────────────────────────────────────────────
        client_order_id = client_order_tag or self.make_client_order_tag()

        # ── 4. 组装 params ────────────────────────────────────────────
        params: Dict[str, Any] = {"newClientOrderId": client_order_id}
        if reduce_only:
            params["reduceOnly"] = True
        if stop_price_f is not None:
            params["stopPrice"] = stop_price_f

        order_type_upper = order_type.upper()

        # ── 5. 实际下单 + 受控 retry ──────────────────────────────────
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                if order_type_upper == "MARKET":
                    order = self.exchange.create_market_order(
                        symbol=symbol, side=side, amount=amount_f, params=params,
                    )
                elif order_type_upper == "LIMIT":
                    if price_f is None:
                        return {
                            "success": False,
                            "error": "LIMIT order requires price",
                            "error_kind": "PERMANENT",
                            "client_order_id": client_order_id,
                        }
                    order = self.exchange.create_limit_order(
                        symbol=symbol, side=side, amount=amount_f, price=price_f, params=params,
                    )
                else:
                    # STOP_MARKET / TAKE_PROFIT_MARKET — 通过 create_order
                    order = self.exchange.create_order(
                        symbol=symbol,
                        type=order_type_upper,
                        side=side,
                        amount=amount_f,
                        params=params,
                    )

                return {
                    "success": True,
                    "order_id": str(order.get("id")) if order.get("id") else None,
                    "client_order_id": client_order_id,
                    "filled": float(order.get("filled") or amount_f),
                    "price": order.get("price") or order.get("average"),
                    "raw": order,
                }

            except _RETRYABLE_EXC as e:
                last_exc = e
                if attempt < max_attempts:
                    sleep_s = min(2 ** attempt, 8)
                    print(
                        f"[TRADE] {symbol} {order_type_upper} 瞬时错误 (尝试 {attempt}/{max_attempts}): "
                        f"{e} — {sleep_s}s 后重试"
                    )
                    time.sleep(sleep_s)
                    continue
                # 出 retry → 报 TRANSIENT，调用方决定下一轮是否重试
                return {
                    "success": False,
                    "error": str(e),
                    "error_kind": "TRANSIENT",
                    "client_order_id": client_order_id,
                }

            except Exception as e:
                # 同一 clientOrderId 已经成交 — 之前重试其实成功了
                if self._is_duplicate_order_error(e):
                    print(
                        f"[TRADE] {symbol} {order_type_upper} clientOrderId={client_order_id} "
                        f"已存在 — 视为之前重试已成功"
                    )
                    return {
                        "success": True,
                        "order_id": None,
                        "client_order_id": client_order_id,
                        "filled": amount_f,
                        "price": None,
                        "error_kind": "DUPLICATE",
                        "error": str(e),
                    }
                # 其它异常都是确定性的（坏 symbol / 余额不足 / 参数错），不重试
                return {
                    "success": False,
                    "error": str(e),
                    "error_kind": "PERMANENT",
                    "client_order_id": client_order_id,
                }

        # 理论上不会走到（循环里要么 return 要么 continue），兜底
        return {
            "success": False,
            "error": str(last_exc) if last_exc else "unknown",
            "error_kind": "TRANSIENT",
            "client_order_id": client_order_id,
        }
    
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
        开仓 — 走 _safe_create_order（带精度规整 + 幂等键 + 受控重试）

        Args:
            symbol: 交易对符号（CCXT 统一格式，如 "TRB/USDT"）
            side: 方向（'LONG' 或 'SHORT'）
            quantity: 数量（币数 — 实际下单前会被 amount_to_precision 规整）
            order_type: 'MARKET' 或 'LIMIT'
            price: 限价单价格
            stop_loss: 止损价格（可选 — 内部调 set_stop_loss）
            take_profit: 止盈价格（可选 — 内部调 set_take_profit）

        Returns:
            {success, order_id, symbol, side, quantity, price, order_type, status,
             stop_loss?, stop_loss_error?, take_profit?, take_profit_error?, timestamp}

        注意：本函数本身**不**带 @retry — retry 已经被 _safe_create_order 接管，
        而且它有 clientOrderId 幂等保护，网络超时重试不会双倍成交。
        """
        # 校验方向
        if side.upper() == "LONG":
            side_ccxt = "buy"
        elif side.upper() == "SHORT":
            side_ccxt = "sell"
        else:
            return {
                "success": False,
                "error": f"无效的方向: {side}，必须是 'LONG' 或 'SHORT'",
                "error_kind": "PERMANENT",
                "symbol": symbol,
                "timestamp": datetime.now().isoformat(),
            }

        # 杠杆设置（best-effort，失败不阻塞）
        try:
            self.set_leverage(symbol, self.leverage)
        except Exception as e:
            print(f"[WARNING] 设置杠杆失败（继续开仓）: {e}")

        # 主下单 — 唯一入口
        order_result = self._safe_create_order(
            symbol=symbol,
            side=side_ccxt,
            order_type=order_type,
            amount=quantity,
            price=price,
            reduce_only=False,
        )

        if not order_result.get("success"):
            error_msg = order_result.get("error", "未知错误")
            kind = order_result.get("error_kind", "UNKNOWN")
            print(f"[ERROR] 开仓失败 [{kind}]: {symbol} {side} - {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "error_kind": kind,
                "symbol": symbol,
                "side": side,
                "timestamp": datetime.now().isoformat(),
            }

        order_id = order_result.get("order_id")
        filled_quantity = order_result.get("filled") or quantity
        filled_price = order_result.get("price")

        result: Dict[str, Any] = {
            "success": True,
            "order_id": order_id,
            "client_order_id": order_result.get("client_order_id"),
            "symbol": symbol,
            "side": side,
            "quantity": filled_quantity,
            "price": filled_price,
            "order_type": order_type,
            "status": (order_result.get("raw") or {}).get("status", "unknown"),
            "timestamp": datetime.now().isoformat(),
        }
        if order_result.get("error_kind") == "DUPLICATE":
            result["was_duplicate"] = True

        # 等持仓在 broker 端落定后再挂保护单（异步阻塞 — 此函数应在 to_thread 中调用）
        time.sleep(0.5)

        if stop_loss:
            sl_result = self._place_protective_stop(
                symbol=symbol,
                stop_price=stop_loss,
                side=side,
                kind="STOP_LOSS",
                quantity=filled_quantity,
            )
            if sl_result.get("success"):
                result["stop_loss"] = stop_loss
                print(f"[TRADE] ✅ 止损设置成功: {symbol} @ {stop_loss}")
            else:
                err = sl_result.get("error", "未知错误")
                print(f"[WARNING] 设置止损失败: {symbol} - {err}")
                result["stop_loss_error"] = err

        if take_profit:
            tp_result = self._place_protective_stop(
                symbol=symbol,
                stop_price=take_profit,
                side=side,
                kind="TAKE_PROFIT",
                quantity=filled_quantity,
            )
            if tp_result.get("success"):
                result["take_profit"] = take_profit
                print(f"[TRADE] ✅ 止盈设置成功: {symbol} @ {take_profit}")
            else:
                err = tp_result.get("error", "未知错误")
                print(f"[WARNING] 设置止盈失败: {symbol} - {err}")
                result["take_profit_error"] = err

        print(
            f"[TRADE] ✅ 开仓成功: {symbol} {side} "
            f"{float(filled_quantity):.4f} @ {filled_price}"
        )
        return result
    
    def close_position(
        self,
        symbol: str,
        quantity: Optional[float] = None,  # None = 全部平仓
        order_type: str = 'MARKET',
    ) -> Dict[str, Any]:
        """
        平仓 — 走 _safe_create_order，reduce_only=True 防止意外反向开仓

        Args:
            symbol: 交易对符号（unified, 如 "BTC/USDT"）
            quantity: 平仓数量（None = 全部平仓）
            order_type: 'MARKET' 或 'LIMIT'

        Returns:
            订单结果字典

        注意：本函数本身**不**带 @retry — retry 由 _safe_create_order 内部控制。
        """
        binance_symbol = self._symbol_to_binance(symbol)

        # 查询当前持仓 — 这是 reduce_only 单需要的数量来源
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
                "error_kind": "PERMANENT",
                "symbol": symbol,
            }

        # 反向单
        close_side = "sell" if current_position["side"] == "LONG" else "buy"
        close_quantity = quantity or abs(current_position["size"])

        # 限价单需要参考价
        ref_price: Optional[float] = None
        if order_type.upper() == "LIMIT":
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                ref_price = ticker.get("last")
            except Exception as e:
                return {
                    "success": False,
                    "error": f"无法获取参考价: {e}",
                    "error_kind": "TRANSIENT",
                    "symbol": symbol,
                }
            if ref_price is None:
                return {
                    "success": False,
                    "error": "ticker last 为空",
                    "error_kind": "TRANSIENT",
                    "symbol": symbol,
                }

        order_result = self._safe_create_order(
            symbol=symbol,
            side=close_side,
            order_type=order_type,
            amount=close_quantity,
            price=ref_price,
            reduce_only=True,  # 关键：防止意外反向开仓
        )

        if not order_result.get("success"):
            error_msg = order_result.get("error", "未知错误")
            kind = order_result.get("error_kind", "UNKNOWN")
            print(f"[ERROR] 平仓失败 [{kind}]: {symbol} - {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "error_kind": kind,
                "symbol": symbol,
                "timestamp": datetime.now().isoformat(),
            }

        filled_quantity = order_result.get("filled") or close_quantity
        filled_price = order_result.get("price")
        print(
            f"[TRADE] ✅ 平仓成功: {symbol} "
            f"{float(filled_quantity):.4f} @ {filled_price}"
        )
        return {
            "success": True,
            "order_id": order_result.get("order_id"),
            "client_order_id": order_result.get("client_order_id"),
            "symbol": symbol,
            "quantity": filled_quantity,
            "price": filled_price,
            "order_type": order_type,
            "status": (order_result.get("raw") or {}).get("status", "unknown"),
            "timestamp": datetime.now().isoformat(),
        }

    def _place_protective_stop(
        self,
        symbol: str,
        stop_price: float,
        side: str,             # 持仓方向 'LONG' / 'SHORT'
        kind: str,             # 'STOP_LOSS' / 'TAKE_PROFIT'
        quantity: Optional[float] = None,  # 数量；None 时查询 broker
        max_wait_attempts: int = 4,
        wait_seconds: float = 0.5,
    ) -> Dict[str, Any]:
        """
        统一的保护单挂单逻辑。**关键修复**：
          - 用 reduceOnly + 明确 amount，**不再**用 closePosition=True + amount
            （这两个参数在 Binance 是互斥的，组合会被 -1106 拒绝 → 保护单永远挂不上）
          - 走 _safe_create_order，享受 precision 规整 + idempotency + retry 分类
          - 内置 "等持仓在 broker 端落定" 的轮询（首次 broker 仓位查询可能为空）
        """
        if side.upper() == "LONG":
            # 多头止损/止盈方向都是 SELL
            stop_side = "sell"
        elif side.upper() == "SHORT":
            stop_side = "buy"
        else:
            return {"success": False, "error": f"无效方向: {side}", "error_kind": "PERMANENT"}

        if kind.upper() == "STOP_LOSS":
            order_type = "STOP_MARKET"
        elif kind.upper() == "TAKE_PROFIT":
            order_type = "TAKE_PROFIT_MARKET"
        else:
            return {"success": False, "error": f"无效保护单类型: {kind}", "error_kind": "PERMANENT"}

        binance_symbol = self._symbol_to_binance(symbol)

        # 等持仓落定 / 查询数量
        position_amt: float = abs(quantity) if quantity else 0.0
        if not position_amt:
            for attempt in range(max_wait_attempts):
                positions = self._get_positions(symbol)
                for pos in positions:
                    if pos.get("symbol") == binance_symbol:
                        position_amt = abs(float(pos.get("positionAmt", 0) or 0))
                        if position_amt:
                            break
                if position_amt:
                    break
                if attempt < max_wait_attempts - 1:
                    time.sleep(wait_seconds)
            if not position_amt:
                return {
                    "success": False,
                    "error": f"{symbol} broker 端无持仓（等待 {max_wait_attempts*wait_seconds:.1f}s 仍未出现）",
                    "error_kind": "TRANSIENT",
                }

        return self._safe_create_order(
            symbol=symbol,
            side=stop_side,
            order_type=order_type,
            amount=position_amt,
            stop_price=stop_price,
            reduce_only=True,  # 关键 — 替代了之前错误的 closePosition=True
        )

    def set_stop_loss(
        self,
        symbol: str,
        stop_price: float,
        side: str,
    ) -> Dict[str, Any]:
        """挂止损单（薄封装 → _place_protective_stop）"""
        return self._place_protective_stop(
            symbol=symbol, stop_price=stop_price, side=side, kind="STOP_LOSS",
        )

    def set_take_profit(
        self,
        symbol: str,
        take_profit_price: float,
        side: str,
    ) -> Dict[str, Any]:
        """挂止盈单（薄封装 → _place_protective_stop）"""
        return self._place_protective_stop(
            symbol=symbol, stop_price=take_profit_price, side=side, kind="TAKE_PROFIT",
        )
    
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

