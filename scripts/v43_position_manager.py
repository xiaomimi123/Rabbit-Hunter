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
        # SHORT 路径暂停（v45 临时止血）
        # chandelier_stop 的 SHORT 数学和 funding 符号尚未端到端修复，强行 SHORT 等于裸奔
        # 设 ENABLE_SHORT_TRADING=true 可恢复（不推荐，等系统性修复后再开）
        if side.upper() == "SHORT":
            enable_short = os.environ.get("ENABLE_SHORT_TRADING", "false").lower() in ("1", "true")
            if not enable_short:
                print(
                    f"[V4.3 SKIP] {symbol} SHORT 入场被 kill switch 拦截 "
                    f"(ENABLE_SHORT_TRADING=false) — 设 true 可恢复"
                )
                return None

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
            # V4.3 原有逻辑：使用 initialize_position（v45：side-aware）
            position_init = initialize_position(
                features=features,
                price=entry_price,
                atr=atr_value,
                side=side,
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
            # 对称初始化 — 已 ALTER TABLE 加上 lowest_price 列（v45 迁移）
            "highest_price": entry_price if side == "LONG" else None,
            "lowest_price": entry_price if side == "SHORT" else None,
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

                # 进场成功 — 但 SL/TP 可能在 trader 内部静默失败（只记 WARNING）。
                # 默认 fail-closed：如果保护单未挂上，立刻平掉刚开的仓位，不写入 DB。
                # 设 SL_TP_FAIL_OPEN=true 可恢复旧的"裸奔"行为。
                sl_tp_fail_open = os.environ.get("SL_TP_FAIL_OPEN", "false").lower() in ("1", "true")
                sl_err = trade_result.get("stop_loss_error")
                tp_err = trade_result.get("take_profit_error")
                if (sl_err or tp_err) and not sl_tp_fail_open:
                    print(
                        f"[CRITICAL] {symbol} 保护单未挂上 "
                        f"(sl_error={sl_err!r}, tp_error={tp_err!r}) — 立刻回滚平仓"
                    )
                    try:
                        rollback = self.trader.close_position(
                            symbol=symbol, quantity=None, order_type="MARKET"
                        )
                        if rollback.get("success"):
                            print(f"[V4.3] ↩ 回滚平仓成功: order_id={rollback.get('order_id')}")
                        else:
                            # 回滚失败 = 真正的紧急情况：broker 端有裸仓，需人工介入。
                            print(
                                f"[ALERT] {symbol} 回滚平仓失败: {rollback.get('error')} "
                                f"— 请立即手动检查 broker 持仓"
                            )
                    except Exception as rb_exc:
                        print(
                            f"[ALERT] {symbol} 回滚平仓异常: {rb_exc} "
                            f"— 请立即手动检查 broker 持仓"
                        )
                    return None

                if sl_err or tp_err:
                    # fail-open 路径：警告但继续写 DB
                    print(
                        f"[WARNING] {symbol} 保护单失败但 SL_TP_FAIL_OPEN=true，"
                        f"仓位以裸奔状态记录 (sl_error={sl_err!r}, tp_error={tp_err!r})"
                    )

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
        
        # v45：update_chandelier_stop 现在自己处理 side 感知的极值跟踪
        # （根据 position["side"] 自动选 highest 或 lowest），这里不再需要做镜像处理。

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

        # 更新止损 — side-aware（v45）
        updated_position = update_chandelier_stop(
            position=position,
            current_price=current_price,
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

        顺序：broker 先 → DB 后。
        broker 平仓失败时保持 DB status=OPEN，返回 None，让下一轮 scan 重试；
        避免出现 "DB 写 CLOSED 但 broker 实际还有持仓" 的幽灵仓位。

        Args:
            symbol: 交易对符号
            exit_price: 平仓价格（broker 调用成功时会被实际成交价覆盖）
            exit_reason: 平仓原因
            write_queue: 异步写入队列（可选）

        Returns:
            平仓后的持仓字典（包含 PnL），平仓不存在或 broker 失败返回 None
        """
        position = self.get_position(symbol)
        if not position:
            return None

        entry_price = position["entry_price"]
        position_size = position["position_size"]
        side = position["side"]

        # Step 1 — 先调 broker（如果配置了）。broker 失败就 DB 不动，让重试覆盖。
        broker_fill_price: Optional[float] = None
        if self.trader:
            try:
                trade_result = self.trader.close_position(
                    symbol=symbol,
                    quantity=None,  # 全部平仓
                    order_type="MARKET",
                )
            except Exception as e:
                print(
                    f"[ALERT] {symbol} broker 平仓异常: {e} — "
                    f"DB 保持 OPEN，下一轮 scan 会重试"
                )
                return None

            if not trade_result.get("success"):
                print(
                    f"[ALERT] {symbol} broker 平仓失败: {trade_result.get('error', '未知错误')} — "
                    f"DB 保持 OPEN，下一轮 scan 会重试"
                )
                return None

            # broker 成交价优先（更准确）
            broker_fill_price = trade_result.get("price") or trade_result.get("filled_price")
            print(f"[V4.3] ✅ 币安平仓成功: order_id={trade_result.get('order_id')}")
        else:
            print(f"[INFO] 未配置交易器，仅记录平仓到数据库（模拟交易）")

        # Step 2 — broker 成功（或模拟）后，用真实成交价计算 PnL 并写 DB。
        final_exit_price = float(broker_fill_price) if broker_fill_price else exit_price
        if side == "LONG":
            pnl = (final_exit_price - entry_price) * position_size
            pnl_percent = ((final_exit_price - entry_price) / entry_price) * 100
        else:  # SHORT
            pnl = (entry_price - final_exit_price) * position_size
            pnl_percent = ((entry_price - final_exit_price) / entry_price) * 100

        now_iso = datetime.now().isoformat()
        position["status"] = "CLOSED"
        position["current_price"] = final_exit_price
        position["closed_at"] = now_iso
        position["exit_reason"] = exit_reason
        position["pnl"] = pnl
        position["pnl_percent"] = pnl_percent
        position["updated_at"] = now_iso

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
                # broker 已平，DB 没写上 — 出现 broker/DB 不一致。
                # 记录关键告警，由 reconciler 后台修复。
                print(
                    f"[ALERT] {symbol} broker 已平仓但 DB 更新失败: {e} — "
                    f"position_id={position.get('id')} 需要 reconciler 修复"
                )

        # 从缓存移除
        if symbol in self.positions_cache:
            del self.positions_cache[symbol]

        print(
            f"[V4.3 CLOSE] {symbol:12s} | "
            f"side={side} | "
            f"entry={entry_price:.4f} | "
            f"exit={final_exit_price:.4f} | "
            f"pnl={pnl:.2f} ({pnl_percent:+.2f}%) | "
            f"reason={exit_reason}"
        )

        # v45：写入 AI 学习日志（JSONL），喂给 memory_uploader 的 Vector Store 上传。
        # 之前 log_trade_result 没有任何调用方，Vector Store 永远是空的 → AI 的"搜索历史
        # 案例"prompt 形同虚设。这里把闭环接通。任何写日志的失败都不能影响交易主线。
        try:
            self._log_trade_to_ai_memory(
                position=position,
                entry_price=entry_price,
                exit_price=final_exit_price,
                pnl=pnl,
                pnl_percent=pnl_percent,
                exit_reason=exit_reason,
            )
        except Exception as log_exc:
            print(f"[WARNING] AI 学习日志写入失败（不影响交易）: {log_exc}")

        return position

    @staticmethod
    def _log_trade_to_ai_memory(
        *,
        position: Dict[str, Any],
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_percent: float,   # 百分比形式（5.0 = 5%）
        exit_reason: str,
    ) -> None:
        """把刚关闭的交易 append 到 data/ai_trade_log.jsonl。

        memory_uploader.log_trade_result 期望 pnl_pct **小数形式**（0.05 = 5%），
        它内部会 *100 转回百分比存储。所以这里把百分比 / 100。

        从 position 上提取可用的 features / ai_decision 子集。完整的 features 需要
        从 trade_scores_v43 / ai_training_data 关联查询，下一步再做。
        """
        # 懒加载：避免 import 时连锁副作用（openai 客户端等）
        from scripts.ai.memory_uploader import log_trade_result

        features = {
            "phase": position.get("phase"),
            "phase_age": position.get("phase_age"),
            # 后续可在 open_position 时把完整 features 序列化进 position["entry_features"]
            # 然后这里直接读出来，给 AI 学习"开仓时的市场状态 → 结果"的映射。
        }
        ai_decision = {
            "confidence": position.get("ai_confidence"),
            "sl_multiplier": position.get("ai_sl_multiplier"),
            "tp_multiplier": position.get("ai_tp_multiplier"),
            "strategy_id": position.get("strategy_id"),
        }

        log_trade_result(
            symbol=position.get("symbol", "UNKNOWN"),
            side=position.get("side", "UNKNOWN"),
            entry_price=float(entry_price),
            exit_price=float(exit_price),
            pnl_usdt=float(pnl),
            pnl_pct=float(pnl_percent) / 100.0,   # 转回小数形式
            exit_reason=exit_reason,
            features={k: v for k, v in features.items() if v is not None},
            ai_decision={k: v for k, v in ai_decision.items() if v is not None} or None,
        )
    
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

