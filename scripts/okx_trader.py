"""
OKX 永续合约交易器（v0.5.2）

与 scripts/binance_trader.py 同接口（v43_position_manager 在不知情下调用任意一边）：
  - open_position(symbol, side, quantity, order_type, stop_loss, take_profit)
  - close_position(symbol, quantity, order_type)
  - set_stop_loss(symbol, stop_price, side)
  - set_take_profit(symbol, take_profit_price, side)
  - set_leverage(symbol, leverage)
  - get_account_balance() / fetch_balance()
  - exchange  (ccxt 实例，给 position_sync 用)

OKX vs Binance 的关键差异：
  - 鉴权多一个 passphrase
  - SWAP symbol 在 ccxt 是 BTC/USDT:USDT（带 settle 后缀）
  - Demo trading 走 set_sandbox_mode(True)
  - 持仓默认 net 模式（与 Binance one-way 对齐，不用 hedge mode）
  - 杠杆设置必须带 mgnMode + posSide
  - fetch_positions 返回 ccxt unified format（'contracts' 字段，不是 'positionAmt'）

调用方应该用 binance flat symbol 风格（BTCUSDT），本模块内部转 OKX unified（BTC/USDT:USDT）。
"""

import os
import time
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

import ccxt
from dotenv import load_dotenv


# fail-closed 默认: SL/TP 挂失败时抛异常,让 v5_position_manager 的回滚逻辑生效。
# fail-open (true) 仅应在已知 OKX 接口不稳定的应急时段开启;那时主仓会成功但保护单可能缺失。
_SL_TP_FAIL_OPEN = os.environ.get("SL_TP_FAIL_OPEN", "false").lower() in ("1", "true", "yes")


# ── 凭据 ─────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

OKX_API_KEY    = os.environ.get("OKX_API_KEY")
OKX_API_SECRET = os.environ.get("OKX_API_SECRET")
OKX_PASSPHRASE = os.environ.get("OKX_API_PASSPHRASE")
OKX_TESTNET    = os.environ.get("OKX_TESTNET", "false").lower() in ("true", "1")


# 与 BinanceTrader 用同一套常量，方便共享 _safe_create_order 的语义
_RETRYABLE_EXC = (
    ccxt.NetworkError,
    ccxt.RequestTimeout,
    ccxt.DDoSProtection,
    ccxt.ExchangeNotAvailable,
)

# OKX 的 "duplicate clientOrderId" 错误标志（其 error code 与 Binance 不同）
_DUPLICATE_ORDER_HINTS = (
    "51000",  # Parameter error
    "51020",  # The order has been canceled
    "Client order id",
    "clOrdId",
    "Duplicate",
    "already exists",
)


class OkxTrader:
    """OKX 永续合约交易器 — 与 BinanceTrader 同 surface。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        testnet: bool = False,
        leverage: int = 10,
    ):
        self.api_key    = api_key or OKX_API_KEY
        self.api_secret = api_secret or OKX_API_SECRET
        self.passphrase = passphrase or OKX_PASSPHRASE
        self.testnet    = testnet or OKX_TESTNET
        self.leverage   = leverage or int(os.environ.get("OKX_LEVERAGE", "10"))

        # 公开行情可以无 key 跑；私有调用前会被 ccxt 拒绝
        if not self.api_key:
            print("[OKX] 未配置 OKX_API_KEY — 仅支持公开行情，私有调用（下单/查仓）会失败")

        exchange_config: Dict[str, Any] = {
            "apiKey":          (self.api_key or "").strip(),
            "secret":          (self.api_secret or "").strip(),
            "password":        (self.passphrase or "").strip(),
            "enableRateLimit": True,
            "options": {
                "defaultType":              "swap",     # 永续合约
                "marginMode":               "isolated", # 默认逐仓
                "adjustForTimeDifference":  True,
            },
        }

        self.exchange = ccxt.okx(exchange_config)
        self.exchange.timeout = 10000  # ms

        if self.testnet:
            # OKX 的 demo trading：ccxt 通过 set_sandbox_mode 自动加 x-simulated-trading 头
            try:
                self.exchange.set_sandbox_mode(True)
                print("[INIT] 🟢 OKX Demo Trading 已启用（x-simulated-trading=1）")
            except Exception as e:
                print(f"[WARNING] OKX set_sandbox_mode 失败: {e}")
        else:
            print("[INFO] 使用 OKX 实盘（⚠️ 注意风险）")

        # 加载 markets — 必要：amount_to_precision / price_to_precision 都依赖
        # Docker Desktop on macOS 跟 www.okx.com 偶尔 SSL EOF / timeout；重试 3 次
        for attempt in range(1, 4):
            try:
                self.exchange.load_markets()
                if attempt > 1:
                    print(f"[OKX] load_markets 成功（第 {attempt} 次）")
                break
            except Exception as e:
                error_str = str(e)
                if any(s in error_str for s in ("Invalid OK_ACCESS_KEY", "401", "Unauthorized")):
                    # 公开 endpoint 不需要 auth；这种 401 不影响 markets
                    print(f"[INFO] OKX load_markets: API key 鉴权失败但 markets 仍会加载: {error_str[:80]}")
                    break
                if attempt == 3:
                    print(f"[WARNING] OKX load_markets 三次都失败: {error_str[:120]}")
                else:
                    print(f"[INFO] OKX load_markets 尝试 {attempt}/3 失败，2s 后重试: {error_str[:80]}")
                    time.sleep(2)

    # ──────────────────────────────────────────────────────────────────
    # symbol 转换
    # ──────────────────────────────────────────────────────────────────

    @classmethod
    def to_ccxt_symbol(cls, symbol: str) -> str:
        """与 BinanceTrader.to_ccxt_symbol 同接口，方便 routes 解耦。
        OKX 永续：unified 是 'BTC/USDT:USDT'。"""
        return cls._binance_flat_to_okx_unified(symbol)

    @staticmethod
    def _binance_flat_to_okx_unified(binance_symbol: str) -> str:
        """BTCUSDT → BTC/USDT:USDT（OKX SWAP ccxt unified 格式）。"""
        if "/" in binance_symbol:
            # 已经是 ccxt unified，转 OKX swap
            if ":" in binance_symbol:
                return binance_symbol
            base, quote = binance_symbol.split("/")
            return f"{base}/{quote}:{quote}"
        # 假定 USDT-margined
        if binance_symbol.endswith("USDT"):
            base = binance_symbol[:-4]
            return f"{base}/USDT:USDT"
        return binance_symbol

    @staticmethod
    def _is_duplicate_order_error(err: Exception) -> bool:
        msg = str(err)
        return any(hint in msg for hint in _DUPLICATE_ORDER_HINTS)

    @staticmethod
    def make_client_order_tag(prefix: str = "rh") -> str:
        """OKX 的 clOrdId 上限 32 字符，[A-Za-z0-9-_]。"""
        return f"{prefix}{uuid.uuid4().hex[:12]}"

    # ──────────────────────────────────────────────────────────────────
    # _safe_create_order — 与 BinanceTrader 同语义，使用 ccxt unified
    # ──────────────────────────────────────────────────────────────────

    def _safe_create_order(
        self,
        symbol: str,            # 接受 binance flat (BTCUSDT) 或 ccxt unified
        side: str,              # "buy" or "sell"
        order_type: str,        # "MARKET" / "LIMIT" / "STOP_MARKET" / "TAKE_PROFIT_MARKET"
        amount: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        reduce_only: bool = False,
        client_order_tag: Optional[str] = None,
        max_attempts: int = 3,
    ) -> Dict[str, Any]:
        """OKX 下单唯一入口 — 接口与 BinanceTrader._safe_create_order 一致。

        实现差异：
          - symbol 自动转 OKX unified (BTC/USDT:USDT)
          - OKX 用 clOrdId 而非 newClientOrderId
          - STOP 类型走 OKX 的 trigger order 路径（params['ordType']='trigger'）
        """
        okx_symbol = self._binance_flat_to_okx_unified(symbol)

        # 0. market
        try:
            market = self.exchange.market(okx_symbol)
        except Exception as e:
            return {
                "success": False,
                "error":   f"unknown symbol {okx_symbol}: {e}",
                "error_kind": "PERMANENT",
            }
        if not market or not market.get("active", True):
            return {
                "success": False,
                "error":   f"symbol {okx_symbol} inactive or unavailable",
                "error_kind": "PERMANENT",
            }

        # 1. precision
        try:
            amount_str = self.exchange.amount_to_precision(okx_symbol, amount)
            amount_f   = float(amount_str)
        except Exception as e:
            return {
                "success": False,
                "error":   f"amount_to_precision({amount}) failed: {e}",
                "error_kind": "PERMANENT",
            }

        price_f: Optional[float] = None
        if price is not None:
            try:
                price_f = float(self.exchange.price_to_precision(okx_symbol, price))
            except Exception as e:
                return {
                    "success": False,
                    "error":   f"price_to_precision({price}) failed: {e}",
                    "error_kind": "PERMANENT",
                }

        stop_price_f: Optional[float] = None
        if stop_price is not None:
            try:
                stop_price_f = float(self.exchange.price_to_precision(okx_symbol, stop_price))
            except Exception as e:
                return {
                    "success": False,
                    "error":   f"price_to_precision(stop={stop_price}) failed: {e}",
                    "error_kind": "PERMANENT",
                }

        # 2. limits（OKX 也有 amount.min / cost.min）
        limits = market.get("limits", {}) or {}
        amount_min = (limits.get("amount") or {}).get("min")
        cost_min   = (limits.get("cost") or {}).get("min")
        if amount_min and amount_f < float(amount_min):
            return {
                "success": False,
                "error":   f"amount {amount_f} below min {amount_min}",
                "error_kind": "PERMANENT",
            }
        ref_price = price_f or stop_price_f
        if ref_price is None and cost_min:
            try:
                ticker = self.exchange.fetch_ticker(okx_symbol) or {}
                last   = ticker.get("last")
                if last is not None:
                    ref_price = float(last) or None
            except Exception:
                ref_price = None
        if cost_min and ref_price:
            notional = amount_f * ref_price
            if notional < float(cost_min):
                return {
                    "success": False,
                    "error":   f"notional {notional:.4f} below min cost {cost_min}",
                    "error_kind": "PERMANENT",
                }

        # 3. 幂等键 — OKX 用 clOrdId，限制 32 字符
        client_order_id = client_order_tag or self.make_client_order_tag()
        if len(client_order_id) > 32:
            client_order_id = client_order_id[:32]

        # 4. params 组装
        params: Dict[str, Any] = {"clOrdId": client_order_id}
        if reduce_only:
            params["reduceOnly"] = True
        # OKX 的 net 模式（一向持仓，对齐 Binance one-way）
        params["posSide"] = "net"
        # OKX 永续默认逐仓
        params["mgnMode"] = "isolated"
        if stop_price_f is not None:
            # OKX trigger order 用 triggerPrice
            params["triggerPrice"]    = stop_price_f
            params["stopLossPrice"]   = stop_price_f if "STOP_MARKET" in order_type.upper() else None
            params["takeProfitPrice"] = stop_price_f if "TAKE_PROFIT" in order_type.upper() else None
            # 清掉 None
            params = {k: v for k, v in params.items() if v is not None}

        order_type_upper = order_type.upper()

        # 5. 实际下单 + 受控 retry
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                if order_type_upper == "MARKET":
                    order = self.exchange.create_market_order(
                        symbol=okx_symbol, side=side, amount=amount_f, params=params,
                    )
                elif order_type_upper == "LIMIT":
                    if price_f is None:
                        return {
                            "success": False,
                            "error":   "LIMIT order requires price",
                            "error_kind": "PERMANENT",
                            "client_order_id": client_order_id,
                        }
                    order = self.exchange.create_limit_order(
                        symbol=okx_symbol, side=side, amount=amount_f, price=price_f, params=params,
                    )
                else:
                    # STOP / TP — OKX trigger order
                    # ccxt 抽象：create_order(type='market', side, amount, params={'stopLossPrice':...})
                    order = self.exchange.create_order(
                        symbol=okx_symbol,
                        type="market",   # trigger 触发后用市价单
                        side=side,
                        amount=amount_f,
                        params=params,
                    )

                return {
                    "success":          True,
                    "order_id":         str(order.get("id")) if order.get("id") else None,
                    "client_order_id":  client_order_id,
                    "filled":           float(order.get("filled") or amount_f),
                    "price":            order.get("price") or order.get("average"),
                    "raw":              order,
                }

            except _RETRYABLE_EXC as e:
                last_exc = e
                if attempt < max_attempts:
                    sleep_s = min(2 ** attempt, 8)
                    print(
                        f"[OKX] {okx_symbol} {order_type_upper} 瞬时错误 "
                        f"(尝试 {attempt}/{max_attempts}): {e} — {sleep_s}s 后重试"
                    )
                    time.sleep(sleep_s)
                    continue
                return {
                    "success": False,
                    "error":   str(e),
                    "error_kind": "TRANSIENT",
                    "client_order_id": client_order_id,
                }

            except Exception as e:
                if self._is_duplicate_order_error(e):
                    print(
                        f"[OKX] {okx_symbol} {order_type_upper} clOrdId={client_order_id} "
                        f"已存在 — 视为之前重试已成功"
                    )
                    return {
                        "success":          True,
                        "order_id":         None,
                        "client_order_id":  client_order_id,
                        "filled":           amount_f,
                        "price":            None,
                        "error_kind":       "DUPLICATE",
                        "error":            str(e),
                    }
                return {
                    "success":         False,
                    "error":           str(e),
                    "error_kind":      "PERMANENT",
                    "client_order_id": client_order_id,
                }

        return {
            "success":          False,
            "error":            str(last_exc) if last_exc else "unknown",
            "error_kind":       "TRANSIENT",
            "client_order_id":  client_order_id,
        }

    # ──────────────────────────────────────────────────────────────────
    # 持仓查询 — 返回与 BinanceTrader._get_positions 兼容的 shape
    # ──────────────────────────────────────────────────────────────────

    def _get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """返回 [{symbol: 'BTCUSDT', positionAmt: '+0.1' / '-0.1', ...}, ...]

        binance_position_sync 期望 Binance-style 字段 (positionAmt, entryPrice, markPrice...)，
        这里把 ccxt unified 反向映射回去，让 sync 模块无需感知 exchange。"""
        try:
            okx_symbol = self._binance_flat_to_okx_unified(symbol) if symbol else None
            positions = self.exchange.fetch_positions([okx_symbol] if okx_symbol else None)
        except Exception as e:
            print(f"[OKX] _get_positions 失败: {e}")
            return []

        result: List[Dict[str, Any]] = []
        for p in positions:
            contracts = p.get("contracts") or 0
            if not contracts:
                continue
            side = (p.get("side") or "").lower()  # 'long' / 'short'
            # 正负号约定与 Binance positionAmt 一致：long 正 / short 负
            position_amt = float(contracts) * (1 if side == "long" else -1)

            # OKX ccxt symbol 例如 'BTC/USDT:USDT' → binance flat 'BTCUSDT'
            ccxt_symbol = p.get("symbol") or ""
            binance_flat = ccxt_symbol.split(":")[0].replace("/", "") if ccxt_symbol else ""

            result.append({
                "symbol":           binance_flat,
                "positionAmt":      str(position_amt),
                "entryPrice":       str(p.get("entryPrice") or 0),
                "markPrice":        str(p.get("markPrice")  or 0),
                "leverage":         str(p.get("leverage")   or self.leverage),
                "unRealizedProfit": str(p.get("unrealizedPnl") or 0),
                "_source":          "okx",
                "_okx_raw":         p,
            })
        return result

    # ──────────────────────────────────────────────────────────────────
    # 杠杆 + 余额（与 BinanceTrader 同名）
    # ──────────────────────────────────────────────────────────────────

    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """OKX 需要 mgnMode + posSide 参数。"""
        okx_symbol = self._binance_flat_to_okx_unified(symbol)
        try:
            self.exchange.set_leverage(
                int(leverage), okx_symbol,
                params={"mgnMode": "isolated", "posSide": "net"},
            )
            return {"success": True, "symbol": symbol, "leverage": leverage}
        except Exception as e:
            error_str = str(e)
            # OKX 51022 = leverage already at this value
            if "51022" in error_str or "already" in error_str.lower():
                return {"success": True, "symbol": symbol, "leverage": leverage}
            print(f"[OKX] set_leverage {symbol}={leverage} 失败: {e}")
            return {"success": False, "error": error_str, "symbol": symbol}

    def set_leverage_all(self, leverage: int) -> Dict[str, Any]:
        # OKX 没有全局杠杆 — 静默 noop
        return {"success": True, "leverage": leverage, "note": "OKX 杠杆按合约设置"}

    def fetch_balance(self) -> Dict[str, Any]:
        try:
            bal = self.exchange.fetch_balance({"type": "swap"})
            # 提取 USDT
            usdt = bal.get("USDT", {})
            return {
                "balance":         float(usdt.get("total") or 0),
                "availableBalance":float(usdt.get("free")  or 0),
                "asset":           "USDT",
                "testnet":         self.testnet,
                "info":            bal,
            }
        except Exception as e:
            print(f"[OKX] fetch_balance 失败: {e}")
            return {"balance": 0.0, "availableBalance": 0.0, "asset": "USDT", "testnet": self.testnet, "error": str(e)}

    # ──────────────────────────────────────────────────────────────────
    # 高层 trade 方法 — open / close / SL / TP
    # ──────────────────────────────────────────────────────────────────

    def open_position(
        self,
        symbol: str,
        side: str,                          # 'LONG' / 'SHORT'
        quantity: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Dict[str, Any]:
        """OKX 开仓 — 与 BinanceTrader.open_position 同 surface 同语义。"""
        if side.upper() == "LONG":
            side_ccxt = "buy"
        elif side.upper() == "SHORT":
            side_ccxt = "sell"
        else:
            return {
                "success":    False,
                "error":      f"无效方向: {side}",
                "error_kind": "PERMANENT",
                "symbol":     symbol,
                "timestamp":  datetime.now().isoformat(),
            }

        # 杠杆 best-effort
        try:
            self.set_leverage(symbol, self.leverage)
        except Exception as e:
            print(f"[OKX WARNING] 设置杠杆失败（继续开仓）: {e}")

        # 主下单
        order_result = self._safe_create_order(
            symbol=symbol, side=side_ccxt, order_type=order_type,
            amount=quantity, price=price, reduce_only=False,
        )

        if not order_result.get("success"):
            print(f"[OKX ERROR] 开仓失败 [{order_result.get('error_kind')}]: {symbol} {side} - {order_result.get('error')}")
            return {
                "success":    False,
                "error":      order_result.get("error"),
                "error_kind": order_result.get("error_kind"),
                "symbol":     symbol,
                "side":       side,
                "timestamp":  datetime.now().isoformat(),
            }

        result: Dict[str, Any] = {
            "success":           True,
            "order_id":          order_result.get("order_id"),
            "client_order_id":   order_result.get("client_order_id"),
            "symbol":            symbol,
            "side":              side,
            "quantity":          order_result.get("filled") or quantity,
            "price":             order_result.get("price"),
            "order_type":        order_type,
            "status":            (order_result.get("raw") or {}).get("status", "unknown"),
            "timestamp":         datetime.now().isoformat(),
        }
        if order_result.get("error_kind") == "DUPLICATE":
            result["was_duplicate"] = True

        # 等持仓落地后挂保护单
        time.sleep(0.5)

        filled_qty = order_result.get("filled") or quantity

        # SL/TP 失败 fail-closed: 默认抛异常,让 v5_position_manager 的 try/except 回滚主仓。
        # fail-open 仅在 SL_TP_FAIL_OPEN=true 时保留主仓 + 在 result 里塞 error 字段。
        result["sl_attached"] = True
        result["tp_attached"] = True

        if stop_loss:
            sl_result = self._place_protective_stop(
                symbol=symbol, stop_price=stop_loss, side=side,
                kind="STOP_LOSS", quantity=filled_qty,
            )
            if sl_result.get("success"):
                result["stop_loss"] = stop_loss
                print(f"[OKX TRADE] ✅ 止损设置成功: {symbol} @ {stop_loss}")
            else:
                err = sl_result.get("error", "未知错误")
                print(f"[OKX WARNING] 设置止损失败: {symbol} - {err}")
                result["stop_loss_error"] = err
                result["sl_attached"] = False
                if not _SL_TP_FAIL_OPEN:
                    raise Exception(f"OKX SL 挂单失败: {err}")

        if take_profit:
            tp_result = self._place_protective_stop(
                symbol=symbol, stop_price=take_profit, side=side,
                kind="TAKE_PROFIT", quantity=filled_qty,
            )
            if tp_result.get("success"):
                result["take_profit"] = take_profit
                print(f"[OKX TRADE] ✅ 止盈设置成功: {symbol} @ {take_profit}")
            else:
                err = tp_result.get("error", "未知错误")
                print(f"[OKX WARNING] 设置止盈失败: {symbol} - {err}")
                result["take_profit_error"] = err
                result["tp_attached"] = False
                if not _SL_TP_FAIL_OPEN:
                    raise Exception(f"OKX TP 挂单失败: {err}")

        print(f"[OKX TRADE] ✅ 开仓成功: {symbol} {side} {float(filled_qty):.4f} @ {result['price']}")
        return result

    def close_position(
        self,
        symbol: str,
        quantity: Optional[float] = None,   # None = 全部平
        order_type: str = "MARKET",
    ) -> Dict[str, Any]:
        """OKX 平仓 — reduce_only=True 保护。"""
        positions = self._get_positions(symbol)
        current = next(
            (p for p in positions if p.get("symbol") == self._symbol_to_binance_flat(symbol)),
            None,
        )
        if not current:
            return {
                "success":    False,
                "error":      f"{symbol} 无持仓",
                "error_kind": "PERMANENT",
                "symbol":     symbol,
            }

        position_amt = float(current.get("positionAmt", 0))
        if abs(position_amt) < 1e-9:
            return {
                "success":    False,
                "error":      f"{symbol} 持仓为 0",
                "error_kind": "PERMANENT",
                "symbol":     symbol,
            }

        # 反向单
        close_side = "sell" if position_amt > 0 else "buy"
        close_qty  = quantity or abs(position_amt)

        ref_price: Optional[float] = None
        if order_type.upper() == "LIMIT":
            try:
                okx_symbol = self._binance_flat_to_okx_unified(symbol)
                ticker = self.exchange.fetch_ticker(okx_symbol)
                ref_price = ticker.get("last")
            except Exception as e:
                return {
                    "success":    False,
                    "error":      f"无法获取参考价: {e}",
                    "error_kind": "TRANSIENT",
                    "symbol":     symbol,
                }
            if ref_price is None:
                return {
                    "success":    False,
                    "error":      "ticker last 为空",
                    "error_kind": "TRANSIENT",
                    "symbol":     symbol,
                }

        order_result = self._safe_create_order(
            symbol=symbol, side=close_side, order_type=order_type,
            amount=close_qty, price=ref_price, reduce_only=True,
        )

        if not order_result.get("success"):
            print(f"[OKX ERROR] 平仓失败 [{order_result.get('error_kind')}]: {symbol} - {order_result.get('error')}")
            return {
                "success":    False,
                "error":      order_result.get("error"),
                "error_kind": order_result.get("error_kind"),
                "symbol":     symbol,
                "timestamp":  datetime.now().isoformat(),
            }

        filled_qty = order_result.get("filled") or close_qty
        filled_px  = order_result.get("price")
        print(f"[OKX TRADE] ✅ 平仓成功: {symbol} {float(filled_qty):.4f} @ {filled_px}")
        return {
            "success":          True,
            "order_id":         order_result.get("order_id"),
            "client_order_id":  order_result.get("client_order_id"),
            "symbol":           symbol,
            "quantity":         filled_qty,
            "price":            filled_px,
            "order_type":       order_type,
            "status":           (order_result.get("raw") or {}).get("status", "unknown"),
            "timestamp":        datetime.now().isoformat(),
        }

    def _place_protective_stop(
        self,
        symbol: str,
        stop_price: float,
        side: str,                              # 持仓方向 LONG/SHORT
        kind: str,                              # STOP_LOSS / TAKE_PROFIT
        quantity: Optional[float] = None,
        max_wait_attempts: int = 4,
        wait_seconds: float = 0.5,
    ) -> Dict[str, Any]:
        """OKX 保护单 — 用 ccxt 的 stopLossPrice/takeProfitPrice 包装。
        与 Binance 一样不用 closePosition+amount 互斥参数。"""
        if side.upper() == "LONG":
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

        position_amt = abs(quantity) if quantity else 0.0
        if not position_amt:
            # 等持仓落定
            target_flat = self._symbol_to_binance_flat(symbol)
            for attempt in range(max_wait_attempts):
                for p in self._get_positions(symbol):
                    if p.get("symbol") == target_flat:
                        position_amt = abs(float(p.get("positionAmt") or 0))
                        if position_amt:
                            break
                if position_amt:
                    break
                if attempt < max_wait_attempts - 1:
                    time.sleep(wait_seconds)
            if not position_amt:
                return {
                    "success":    False,
                    "error":      f"{symbol} broker 端无持仓",
                    "error_kind": "TRANSIENT",
                }

        return self._safe_create_order(
            symbol=symbol, side=stop_side, order_type=order_type,
            amount=position_amt, stop_price=stop_price, reduce_only=True,
        )

    def set_stop_loss(self, symbol: str, stop_price: float, side: str) -> Dict[str, Any]:
        return self._place_protective_stop(symbol=symbol, stop_price=stop_price, side=side, kind="STOP_LOSS")

    def set_take_profit(self, symbol: str, take_profit_price: float, side: str) -> Dict[str, Any]:
        return self._place_protective_stop(symbol=symbol, stop_price=take_profit_price, side=side, kind="TAKE_PROFIT")

    # ──────────────────────────────────────────────────────────────────
    # 工具
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _symbol_to_binance_flat(symbol: str) -> str:
        """统一返回 binance flat 风格 (BTCUSDT)，用于 _get_positions 的 dict key 对比。"""
        if "/" in symbol:
            return symbol.split(":")[0].replace("/", "")
        return symbol


__all__ = ["OkxTrader"]
