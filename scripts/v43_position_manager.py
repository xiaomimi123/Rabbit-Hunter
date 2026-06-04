"""
V4.3 持仓管理模块

负责：
1. 开仓（根据 V4.3 决策）
2. 平仓（根据 ATR Chandelier Stop 或阶段转换）
3. 止损更新（动态调整）
4. 持仓状态同步到数据库
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import os

from v43_chandelier_stop import (
    initialize_position,
    update_chandelier_stop,
    should_exit_position,
    dynamic_k_by_phase,
)
from v43_decision_policy import decision_policy, detect_market_regime, get_account_stage
from scripts.core.risk_calculator import calculate_position_size


class V43PositionManager:
    """
    V4.3 持仓管理器
    
    职责：
    - 管理所有 V4.3 持仓（开仓、平仓、止损更新）
    - 与数据库同步（positions_v43 表）
    - 执行交易决策
    """
    
    def __init__(self, supabase_client=None, exchange=None, trader=None):
        """
        初始化持仓管理器
        
        Args:
            supabase_client: Supabase 客户端（用于数据库操作）
            exchange: 交易所客户端（用于实际交易，可选）
            trader: BinanceTrader 实例（用于执行交易，可选）
        """
        self.supabase = supabase_client
        self.exchange = exchange
        self.trader = trader  # BinanceTrader 实例
        self.positions_cache: Dict[str, Dict[str, Any]] = {}  # symbol -> position
        self.last_sync_time = datetime.now()
        
    def load_open_positions(self) -> Dict[str, Dict[str, Any]]:
        """
        从数据库加载所有未平仓的持仓
        
        Returns:
            {symbol: position_dict}
        """
        if not self.supabase:
            return {}
        
        try:
            result = self.supabase.table("positions_v43")\
                .select("*")\
                .eq("status", "OPEN")\
                .execute()
            
            positions = {}
            for row in result.data:
                symbol = row.get("symbol")
                if symbol:
                    positions[symbol] = row
            
            self.positions_cache = positions
            self.last_sync_time = datetime.now()
            return positions
        except Exception as e:
            print(f"[WARNING] 加载持仓失败: {e}")
            return {}
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取指定交易对的持仓信息
        
        Args:
            symbol: 交易对符号（如 "BTC/USDT"）
        
        Returns:
            持仓字典，如果不存在返回 None
        """
        # 先从缓存获取
        if symbol in self.positions_cache:
            return self.positions_cache[symbol]
        
        # 如果缓存过期（超过 5 秒），重新加载
        if (datetime.now() - self.last_sync_time).total_seconds() > 5:
            self.load_open_positions()
        
        return self.positions_cache.get(symbol)

    def get_position_api_safe(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        永远从 DB 查询持仓，不依赖内存缓存（用于幂等保护）

        Args:
            symbol: 交易对符号

        Returns:
            持仓字典，如果不存在返回 None
        """
        if not self.supabase:
            return None
        try:
            result = self.supabase.table("positions_v43")\
                .select("*")\
                .eq("symbol", symbol)\
                .eq("status", "OPEN")\
                .execute()
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            print(f"[WARNING] get_position_api_safe {symbol} 查询失败: {e}")
            return None

    def _resolve_atr(
        self,
        atr_value: Optional[float],
        entry_price: float,
        features: Dict[str, Any],
        symbol: str,
    ) -> float:
        """
        解析并验证 ATR 值，ATR 无效时拒绝开仓（抛出异常）

        Args:
            atr_value: 传入的 ATR 值
            entry_price: 开仓价格（仅用于错误日志）
            features: 特征字典，尝试从中提取备用 ATR
            symbol: 交易对符号（用于错误日志）

        Returns:
            有效的 ATR 值（float > 0）

        Raises:
            ValueError: ATR 无效时抛出，调用方必须中止开仓
        """
        if atr_value and atr_value > 0:
            return float(atr_value)

        # 尝试从 features 获取备用 ATR
        fallback = features.get("atr") or features.get("atr_1h")
        if fallback and float(fallback) > 0:
            print(f"[INFO] {symbol} 使用 features ATR 备用值: {fallback}")
            return float(fallback)

        raise ValueError(f"ATR 无效，拒绝开仓: {symbol}")

    def open_position(
        self,
        symbol: str,
        side: str,  # "LONG" or "SHORT"
        entry_price: float,
        features: Dict[str, Any],
        decision_result: Dict[str, Any],
        account_balance: float,
        atr_value: float,
        write_queue=None,  # 异步写入队列
    ) -> Optional[Dict[str, Any]]:
        """
        开仓
        
        Args:
            symbol: 交易对符号
            side: 方向（"LONG" 或 "SHORT"）
            entry_price: 开仓价格
            features: 特征字典
            decision_result: 决策结果（包含 position_size_multiplier, strategy_id, stop_loss_atr_multiplier）
            account_balance: 账户余额
            atr_value: ATR 值
            write_queue: 异步写入队列（可选）
        
        Returns:
            持仓字典，如果开仓失败返回 None
        """
        # 幂等保护：永远从 DB 查询，不依赖内存缓存
        existing = self.get_position_api_safe(symbol)
        if existing:
            print(f"[WARNING] {symbol} 已有持仓（DB 确认），跳过开仓（持仓ID: {existing.get('id', 'N/A')}）")
            return None

        # 确保 ATR 值有效
        atr_value = self._resolve_atr(atr_value, entry_price, features, symbol)
        
        # V4.4 策略路由：使用策略特定的止损倍数
        strategy_id = decision_result.get("strategy_id")
        stop_loss_atr_multiplier = decision_result.get("stop_loss_atr_multiplier")
        
        if stop_loss_atr_multiplier:
            # 使用策略特定的 ATR 倍数
            if side == "LONG":
                stop_price = entry_price - (atr_value * stop_loss_atr_multiplier)
            else:  # SHORT
                stop_price = entry_price + (atr_value * stop_loss_atr_multiplier)
            atr_k = stop_loss_atr_multiplier
        else:
            # V4.3 原有逻辑：使用 initialize_position
            position_init = initialize_position(
                features=features,
                price=entry_price,
                atr=atr_value,
            )
            stop_price = position_init.get("stop_price")
            atr_k = position_init.get("atr_k")
        
        if stop_price is None:
            print(f"[WARNING] {symbol} 止损价格计算失败，跳过开仓")
            return None
        
        # 计算止盈价格（AI multiplier → range_left → ATR 默认值）
        take_profit = None
        range_left = features.get("range_left")
        ai_tp_multiplier = decision_result.get("take_profit_atr_multiplier")
        if ai_tp_multiplier and atr_value and atr_value > 0:
            if side == "LONG":
                take_profit = entry_price + (atr_value * float(ai_tp_multiplier))
            else:  # SHORT
                take_profit = entry_price - (atr_value * float(ai_tp_multiplier))
        elif range_left and float(range_left) > 0:
            range_left_value = float(range_left)
            if side == "LONG":
                take_profit = entry_price * (1 + range_left_value)
            else:  # SHORT
                take_profit = entry_price * (1 - range_left_value)
        else:
            # 如果没有 AI multiplier 也没有 range_left，使用 ATR 的 3 倍作为止盈（保守估计）
            if atr_value and atr_value > 0:
                if side == "LONG":
                    take_profit = entry_price + (atr_value * 3.0)
                else:  # SHORT
                    take_profit = entry_price - (atr_value * 3.0)
        
        # V4.4 策略路由：使用策略特定的仓位倍数 + 灰度发布倍数
        position_multiplier = decision_result.get("position_size_multiplier", 1.0)
        v44_grayscale_multiplier = float(os.environ.get("V44_POSITION_SIZE_MULTIPLIER", "1.0"))  # 默认 1.0（100%）
        effective_position_multiplier = position_multiplier * v44_grayscale_multiplier
        
        risk_per_trade = float(os.environ.get("V43_RISK_PER_TRADE", "0.015"))  # 默认 1.5%
        effective_risk = risk_per_trade * effective_position_multiplier
        
        position_size = calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss_price=stop_price,
            risk_per_trade=effective_risk,
            is_short=(side == "SHORT"),
        )
        
        if position_size <= 0:
            print(f"[WARNING] {symbol} 仓位大小计算为 0，跳过开仓")
            return None
        
        # 构建持仓记录
        now_iso = datetime.now().isoformat()
        position = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "current_price": entry_price,
            "position_size": position_size,
            "stop_price": stop_price,
            "take_profit": take_profit,  # 添加止盈价格（如果数据库支持）
            "atr_k": atr_k,
            "atr_shock_detected": False,
            "atr_shock_freeze_until": None,
            "highest_price": entry_price if side == "LONG" else None,
            # 注意：数据库表中没有 lowest_price 字段，已移除
            "phase": features.get("phase"),
            "phase_age": features.get("phase_age"),
            "status": "OPEN",
            "created_at": now_iso,
            "updated_at": now_iso,
            # V4.4 策略路由字段
            "strategy_id": strategy_id,
        }
        
        # 如果配置了交易器，执行实际交易
        binance_order_success = True  # 默认成功（如果没有交易器，视为模拟交易成功）
        if self.trader:
            try:
                trade_result = self.trader.open_position(
                    symbol=symbol,
                    side=side,
                    quantity=position_size,
                    order_type="MARKET",
                    stop_loss=stop_price,
                    take_profit=take_profit,  # 添加止盈价格
                )
                
                if not trade_result.get("success"):
                    error_msg = trade_result.get('error', '未知错误')
                    print(f"[ERROR] 币安开仓失败: {error_msg}")
                    
                    # 检查是否是交易对状态错误（测试网可能不支持某些交易对）
                    if "-4140" in str(error_msg) or "Invalid symbol status" in str(error_msg):
                        print(f"[WARNING] {symbol} 在币安测试网不支持或状态异常，跳过此交易对")
                        print(f"[INFO] 这是正常现象，测试网可能不支持所有交易对")
                    
                    # 如果币安订单失败，不写入数据库，直接返回 None
                    # 这样可以避免记录虚假的持仓
                    return None
                else:
                    # 注意：数据库表中没有 binance_order_id 字段，已移除
                    # 订单 ID 已通过日志输出
                    print(f"[V4.3] ✅ 币安开仓成功: order_id={trade_result.get('order_id')}")
                    binance_order_success = True
            except Exception as e:
                print(f"[ERROR] 币安开仓异常: {e}")
                # 如果币安订单异常，不写入数据库，直接返回 None
                return None
        else:
            print(f"[INFO] 未配置交易器，仅记录持仓到数据库（模拟交易）")
            # 注意：数据库表中没有 trade_status 字段，已移除
        
        # 写入数据库（只有币安订单成功或没有交易器时才写入）
        if write_queue:
            write_queue.put_nowait({
                "op": "insert",
                "table": "positions_v43",
                "row": position
            })
        elif self.supabase:
            try:
                self.supabase.table("positions_v43").insert(position).execute()
            except Exception as e:
                print(f"[WARNING] 写入持仓失败: {e}")
                return None
        
        # 更新缓存
        self.positions_cache[symbol] = position
        
        # 日志输出（包含策略信息和止盈价格）
        strategy_info = f"strategy={strategy_id} | " if strategy_id else ""
        take_profit_info = f" | tp={take_profit:.4f}" if take_profit else " | tp=None"
        print(
            f"[V4.3 OPEN] {symbol:12s} | "
            f"{strategy_info}"
            f"side={side} | "
            f"size={position_size:.4f} | "
            f"entry={entry_price:.4f} | "
            f"stop={stop_price:.4f}{take_profit_info} | "
            f"risk={effective_risk*100:.2f}% | "
            f"multiplier={effective_position_multiplier:.2f}x"
        )
        
        return position
    
    def update_position(
        self,
        symbol: str,
        current_price: float,
        current_atr: float,
        current_phase: str,
        current_phase_age: int,
        ohlcv_15m: List[Dict[str, Any]],
        write_queue=None,
    ) -> Optional[Dict[str, Any]]:
        """
        更新持仓（止损、价格等）
        
        Args:
            symbol: 交易对符号
            current_price: 当前价格
            current_atr: 当前 ATR 值
            current_phase: 当前市场阶段
            current_phase_age: 当前阶段年龄
            ohlcv_15m: 15分钟 K 线数据（用于 ATR Shock Guard）
            write_queue: 异步写入队列（可选）
        
        Returns:
            更新后的持仓字典，如果持仓不存在返回 None
        """
        position = self.get_position(symbol)
        if not position:
            return None
        
        # 更新当前价格
        position["current_price"] = current_price
        position["updated_at"] = datetime.now().isoformat()
        
        # 更新最高价（LONG 持仓使用）
        if position["side"] == "LONG":
            if position.get("highest_price") is None or current_price > position["highest_price"]:
                position["highest_price"] = current_price
        
        # 注意：数据库表中没有 lowest_price 字段，SHORT 持仓直接使用 current_price
        # 更新 Chandelier Stop
        current_high = position.get("highest_price") if position["side"] == "LONG" else current_price
        current_low = current_price  # SHORT 持仓直接使用当前价格（数据库中没有 lowest_price 字段）
        
        # 计算 ATR 历史（用于 ATR Shock Guard）
        atr_history = None
        if ohlcv_15m and len(ohlcv_15m) >= 20:
            try:
                from scripts.core.risk_calculator import calculate_atr
                highs = [c["high"] for c in ohlcv_15m[-20:]]
                lows = [c["low"] for c in ohlcv_15m[-20:]]
                closes = [c["close"] for c in ohlcv_15m[-20:]]
                atr_history = [calculate_atr(highs[:i+1], lows[:i+1], closes[:i+1]) for i in range(14, len(highs))]
            except Exception:
                pass
        
        # 更新止损
        updated_position = update_chandelier_stop(
            position=position,
            current_high=current_high if position["side"] == "LONG" else current_low,
            atr=current_atr,
            atr_history=atr_history,
            bars_since_entry=self._calculate_bars_since_entry(position),
        )
        
        # 检查是否应该平仓
        should_exit, exit_reason = should_exit_position(
            position=updated_position,
            current_price=current_price,
            current_phase=current_phase,
        )
        
        if should_exit:
            return self.close_position(
                symbol=symbol,
                exit_price=current_price,
                exit_reason=exit_reason,
                write_queue=write_queue,
            )
        
        # 更新数据库
        if write_queue:
            write_queue.put_nowait({
                "op": "upsert",
                "table": "positions_v43",
                "row": updated_position,
                "on_conflict": "symbol",
            })
        elif self.supabase:
            try:
                self.supabase.table("positions_v43")\
                    .update(updated_position)\
                    .eq("symbol", symbol)\
                    .eq("status", "OPEN")\
                    .execute()
            except Exception as e:
                print(f"[WARNING] 更新持仓失败: {e}")
        
        # 更新缓存
        self.positions_cache[symbol] = updated_position
        
        return updated_position
    
    def close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str,
        write_queue=None,
    ) -> Optional[Dict[str, Any]]:
        """
        平仓
        
        Args:
            symbol: 交易对符号
            exit_price: 平仓价格
            exit_reason: 平仓原因
            write_queue: 异步写入队列（可选）
        
        Returns:
            平仓后的持仓字典（包含 PnL），如果持仓不存在返回 None
        """
        position = self.get_position(symbol)
        if not position:
            return None
        
        entry_price = position["entry_price"]
        position_size = position["position_size"]
        side = position["side"]
        
        # 计算盈亏
        if side == "LONG":
            pnl = (exit_price - entry_price) * position_size
            pnl_percent = ((exit_price - entry_price) / entry_price) * 100
        else:  # SHORT
            pnl = (entry_price - exit_price) * position_size
            pnl_percent = ((entry_price - exit_price) / entry_price) * 100
        
        # 更新持仓记录
        position["status"] = "CLOSED"
        position["current_price"] = exit_price
        position["closed_at"] = datetime.now().isoformat()
        position["exit_reason"] = exit_reason
        position["pnl"] = pnl
        position["pnl_percent"] = pnl_percent
        position["updated_at"] = datetime.now().isoformat()
        
        # 更新数据库
        if write_queue:
            write_queue.put_nowait({
                "op": "upsert",
                "table": "positions_v43",
                "row": position,
                "on_conflict": "symbol",
            })
        elif self.supabase:
            try:
                self.supabase.table("positions_v43")\
                    .update(position)\
                    .eq("symbol", symbol)\
                    .eq("status", "OPEN")\
                    .execute()
            except Exception as e:
                print(f"[WARNING] 平仓更新失败: {e}")
        
        # 如果配置了交易器，执行实际平仓
        if self.trader:
            try:
                trade_result = self.trader.close_position(
                    symbol=symbol,
                    quantity=None,  # 全部平仓
                    order_type="MARKET",
                )
                
                if not trade_result.get("success"):
                    print(f"[WARNING] 币安平仓失败: {trade_result.get('error', '未知错误')}")
                    # 注意：数据库表中没有 trade_status 和 trade_error 字段，已移除
                    # 错误信息已通过日志输出
                else:
                    # 注意：数据库表中没有 binance_order_id 字段，已移除
                    # 订单 ID 已通过日志输出
                    print(f"[V4.3] ✅ 币安平仓成功: order_id={trade_result.get('order_id')}")
            except Exception as e:
                print(f"[WARNING] 币安平仓异常: {e}")
                # 注意：数据库表中没有 trade_status 和 trade_error 字段，已移除
                # 错误信息已通过日志输出
        else:
            print(f"[INFO] 未配置交易器，仅记录平仓到数据库（模拟交易）")
            # 注意：数据库表中没有 trade_status 字段，已移除
        
        # 从缓存移除
        if symbol in self.positions_cache:
            del self.positions_cache[symbol]
        
        print(
            f"[V4.3 CLOSE] {symbol:12s} | "
            f"side={side} | "
            f"entry={entry_price:.4f} | "
            f"exit={exit_price:.4f} | "
            f"pnl={pnl:.2f} ({pnl_percent:+.2f}%) | "
            f"reason={exit_reason}"
        )
        
        return position
    
    def _calculate_bars_since_entry(self, position: Dict[str, Any]) -> int:
        """
        计算自开仓以来的 K 线数量
        
        Args:
            position: 持仓字典
        
        Returns:
            K 线数量（15分钟）
        """
        try:
            created_at = position.get("created_at")
            if not created_at:
                return 0
            
            if isinstance(created_at, str):
                entry_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            else:
                entry_time = created_at
            
            now = datetime.now(entry_time.tzinfo) if entry_time.tzinfo else datetime.now()
            diff_minutes = (now - entry_time).total_seconds() / 60
            return int(diff_minutes / 15)  # 15分钟 K 线
        except Exception:
            return 0
    
    def sync_positions(self, write_queue=None):
        """
        同步所有持仓状态（定期调用）
        
        Args:
            write_queue: 异步写入队列（可选）
        """
        positions = self.load_open_positions()
        print(f"[INFO] 当前持仓数量: {len(positions)}")
        return positions


__all__ = ["V43PositionManager"]

