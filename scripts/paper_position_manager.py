"""
Paper Position Manager (v0.5.4) — 在线影子交易（paper trading）

与 V43PositionManager **同 surface**（open_position / update_position /
close_position / get_position / load_open_positions），但**所有操作只写
paper_trades 表，不调用 trader / broker**。

SHADOW 模式下 scorer 检测到信号 → 调本 manager → 写虚拟仓位 →
paper_monitor 异步任务 tick 当前价 → 触 SL/TP → 自动结算 PnL。

数据流：
  scorer → PaperPositionManager.open_position → paper_trades (status=OPEN)
  paper_monitor → fetch 当前价 → 触发判定 → close_position → 更新行
  前端 PaperTradesPage → 查 paper_trades → 展示 + 聚合 KPI
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List, Tuple

# 与 V43PositionManager 同样的 chandelier 工具（计算 SL/TP）
try:
    from v43_chandelier_stop import initialize_position
except ImportError:
    from scripts.v43_chandelier_stop import initialize_position  # type: ignore[import-not-found]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


class PaperPositionManager:
    """与 V43PositionManager 同 surface 的虚拟仓位管理器。"""

    def __init__(self, supabase_client=None):
        self.supabase = supabase_client
        # 与 V43PositionManager 不一样的是：不需要 trader，不需要 exchange
        self.positions_cache: Dict[str, Dict[str, Any]] = {}
        self.last_sync_time = _utcnow()

    # ─────────────────────────────────────────────────────────────────
    # 读
    # ─────────────────────────────────────────────────────────────────

    def load_open_positions(self) -> Dict[str, Dict[str, Any]]:
        """加载所有 OPEN 状态的虚拟持仓。"""
        if not self.supabase:
            return {}
        try:
            r = (
                self.supabase.table("paper_trades")
                .select("*").eq("status", "OPEN").execute()
            )
            positions: Dict[str, Dict[str, Any]] = {}
            for row in (r.data or []):
                sym = row.get("symbol")
                if sym:
                    positions[sym] = row
            self.positions_cache = positions
            self.last_sync_time = _utcnow()
            return positions
        except Exception as e:
            print(f"[PaperPM] load_open_positions 失败: {e}")
            return {}

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        if symbol in self.positions_cache:
            return self.positions_cache[symbol]
        if (_utcnow() - self.last_sync_time).total_seconds() > 5:
            self.load_open_positions()
        return self.positions_cache.get(symbol)

    def get_position_api_safe(self, symbol: str) -> Optional[Dict[str, Any]]:
        """直接查 DB，绕开缓存（幂等保护用）。"""
        if not self.supabase:
            return None
        try:
            r = (
                self.supabase.table("paper_trades")
                .select("*")
                .eq("symbol", symbol).eq("status", "OPEN")
                .execute()
            )
            if r.data:
                return r.data[0]
            return None
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────────
    # 开仓
    # ─────────────────────────────────────────────────────────────────

    def open_position(
        self,
        symbol: str,
        side: str,                       # LONG / SHORT
        entry_price: float,
        features: Dict[str, Any],
        decision_result: Dict[str, Any],
        account_balance: float,
        atr_value: float,
        write_queue=None,
        signal_score: Optional[float] = None,
        source_score_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """开虚拟仓位 — 与 V43PositionManager.open_position 接口一致。
        不调 broker，只写 paper_trades。"""

        # 幂等保护：同 symbol 不能有重叠 OPEN 虚拟仓位
        existing = self.get_position_api_safe(symbol)
        if existing:
            print(f"[PaperPM] {symbol} 已有虚拟仓位（OPEN），跳过 (id={existing.get('id')})")
            return None

        # SHORT kill switch 仍然遵守（与 V43PositionManager 同步逻辑）
        if side.upper() == "SHORT":
            enable_short = os.environ.get("ENABLE_SHORT_TRADING", "false").lower() in ("1", "true")
            if not enable_short:
                print(f"[PaperPM SKIP] {symbol} SHORT 被 kill switch 拦截")
                return None

        # ATR 校验
        if not atr_value or atr_value <= 0:
            fallback = features.get("atr") or features.get("atr_1h")
            if fallback and float(fallback) > 0:
                atr_value = float(fallback)
            else:
                print(f"[PaperPM] {symbol} ATR 无效，跳过")
                return None

        # 计算 SL/TP（重用 V43 的 chandelier 数学）
        strategy_id = decision_result.get("strategy_id")
        stop_loss_atr_multiplier = decision_result.get("stop_loss_atr_multiplier")
        take_profit_atr_multiplier = decision_result.get("take_profit_atr_multiplier")

        if stop_loss_atr_multiplier:
            if side == "LONG":
                stop_price = entry_price - (atr_value * stop_loss_atr_multiplier)
            else:
                stop_price = entry_price + (atr_value * stop_loss_atr_multiplier)
            atr_k = stop_loss_atr_multiplier
        else:
            init = initialize_position(features=features, price=entry_price, atr=atr_value, side=side)
            stop_price = init.get("stop_price")
            atr_k = init.get("atr_k") or init.get("k")

        if stop_price is None:
            print(f"[PaperPM] {symbol} stop_price 计算失败")
            return None

        # TP 计算
        take_profit = None
        if take_profit_atr_multiplier and atr_value > 0:
            if side == "LONG":
                take_profit = entry_price + (atr_value * float(take_profit_atr_multiplier))
            else:
                take_profit = entry_price - (atr_value * float(take_profit_atr_multiplier))
        else:
            # 默认 3x ATR
            if side == "LONG":
                take_profit = entry_price + (atr_value * 3.0)
            else:
                take_profit = entry_price - (atr_value * 3.0)

        # 仓位价值（USDT，受 v44 grayscale 影响）
        position_multiplier = decision_result.get("position_size_multiplier", 1.0)
        v44_grayscale = float(os.environ.get("V44_POSITION_SIZE_MULTIPLIER", "1.0"))
        effective_multiplier = position_multiplier * v44_grayscale
        risk_per_trade = float(os.environ.get("V43_RISK_PER_TRADE", "0.015"))
        effective_risk = risk_per_trade * effective_multiplier
        position_size_usdt = account_balance * effective_risk

        leverage = int(os.environ.get("BINANCE_LEVERAGE",
                       os.environ.get("OKX_LEVERAGE", "10")))
        horizon_hours = int(os.environ.get("PAPER_HORIZON_HOURS", "24"))

        now = _utcnow_iso()
        row = {
            "symbol":             symbol,
            "side":               side,
            "entry_price":        entry_price,
            "entry_time":         now,
            "current_price":      entry_price,
            "stop_loss":          stop_price,
            "take_profit":        take_profit,
            "atr_k":              atr_k,
            "position_size_usdt": position_size_usdt,
            "leverage":           leverage,
            "horizon_hours":      horizon_hours,
            "status":             "OPEN",
            "strategy_id":        strategy_id,
            "signal_score":       signal_score,
            "source_score_id":    source_score_id,
            "ai_confidence":      decision_result.get("ai_confidence"),
            "ai_sl_multiplier":   stop_loss_atr_multiplier,
            "ai_tp_multiplier":   take_profit_atr_multiplier,
            "ai_reason":          decision_result.get("ai_reasoning"),
            "reason":             decision_result.get("reason"),
            "created_at":         now,
            "updated_at":         now,
        }

        # 写 DB
        if write_queue:
            write_queue.put_nowait({"op": "insert", "table": "paper_trades", "row": row})
        elif self.supabase:
            try:
                self.supabase.table("paper_trades").insert(row).execute()
            except Exception as e:
                print(f"[PaperPM] 写 paper_trades 失败: {e}")
                return None

        self.positions_cache[symbol] = row
        print(
            f"[PaperPM OPEN] {symbol:12s} | "
            f"strategy={strategy_id} | side={side} | "
            f"entry={entry_price:.6g} | stop={stop_price:.6g} | tp={take_profit:.6g} | "
            f"size={position_size_usdt:.2f} USDT  (虚拟，影子模式)"
        )
        return row

    # ─────────────────────────────────────────────────────────────────
    # update + close — 给 paper_monitor 调用
    # ─────────────────────────────────────────────────────────────────

    def check_exit_triggers(
        self, position: Dict[str, Any], current_price: float,
    ) -> Optional[Tuple[str, float]]:
        """返回 (exit_reason, exit_price) 或 None。"""
        side = (position.get("side") or "LONG").upper()
        sl = position.get("stop_loss")
        tp = position.get("take_profit")

        if side == "LONG":
            if sl is not None and current_price <= float(sl):
                return ("SL_HIT", float(sl))
            if tp is not None and current_price >= float(tp):
                return ("TP_HIT", float(tp))
        else:  # SHORT
            if sl is not None and current_price >= float(sl):
                return ("SL_HIT", float(sl))
            if tp is not None and current_price <= float(tp):
                return ("TP_HIT", float(tp))

        # horizon timeout
        entry_time = position.get("entry_time")
        horizon_hours = position.get("horizon_hours") or 24
        if entry_time:
            try:
                ts = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_h = (_utcnow() - ts).total_seconds() / 3600
                if age_h >= float(horizon_hours):
                    return ("HORIZON_TIMEOUT", current_price)
            except Exception:
                pass
        return None

    def update_current_price(self, symbol: str, current_price: float) -> Optional[Dict[str, Any]]:
        """paper_monitor 每个 tick 调一次 — 更新 current_price + 检查触发。"""
        position = self.get_position(symbol)
        if not position:
            return None

        pid = position.get("id")
        trigger = self.check_exit_triggers(position, current_price)

        if trigger is None:
            # 只更新 current_price，不触发
            if self.supabase and pid is not None:
                try:
                    self.supabase.table("paper_trades").update(
                        {"current_price": current_price, "updated_at": _utcnow_iso()},
                    ).eq("id", pid).execute()
                except Exception:
                    pass
            position["current_price"] = current_price
            return None

        # 触发了 — 结算
        exit_reason, exit_price = trigger
        return self.close_position(symbol=symbol, exit_price=exit_price, exit_reason=exit_reason)

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str,
        write_queue=None,
    ) -> Optional[Dict[str, Any]]:
        position = self.get_position(symbol)
        if not position:
            return None

        side = (position.get("side") or "LONG").upper()
        entry_price = float(position.get("entry_price") or 0)
        position_size_usdt = float(position.get("position_size_usdt") or 0)
        leverage = float(position.get("leverage") or 10)
        if entry_price <= 0 or position_size_usdt <= 0:
            print(f"[PaperPM] {symbol} 关闭失败：entry_price 或 size 为 0")
            return None

        # 虚拟 PnL — 含杠杆
        if side == "LONG":
            pnl_percent = (exit_price - entry_price) / entry_price * 100.0
        else:
            pnl_percent = (entry_price - exit_price) / entry_price * 100.0
        pnl = position_size_usdt * leverage * (pnl_percent / 100.0)

        # 持仓时长
        entry_ts = position.get("entry_time")
        holding_hours = 0.0
        try:
            ts = datetime.fromisoformat(str(entry_ts).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            holding_hours = (_utcnow() - ts).total_seconds() / 3600.0
        except Exception:
            pass

        now = _utcnow_iso()
        update = {
            "status":         "CLOSED",
            "exit_price":     exit_price,
            "exit_time":      now,
            "exit_reason":    exit_reason,
            "current_price":  exit_price,
            "pnl":            round(pnl, 6),
            "pnl_percent":    round(pnl_percent, 6),
            "holding_hours":  round(holding_hours, 3),
            "updated_at":     now,
        }

        pid = position.get("id")
        if pid is not None and self.supabase:
            try:
                self.supabase.table("paper_trades").update(update).eq("id", pid).execute()
            except Exception as e:
                print(f"[PaperPM] close 更新失败: {e}")
                return None

        self.positions_cache.pop(symbol, None)
        position.update(update)
        outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "FLAT"
        print(
            f"[PaperPM CLOSE] {symbol:12s} | side={side} | "
            f"entry={entry_price:.6g} → exit={exit_price:.6g} | "
            f"pnl={pnl:+.2f} ({pnl_percent:+.2f}%) | "
            f"reason={exit_reason} | hold={holding_hours:.1f}h | {outcome}"
        )
        return position

    def sync_positions(self, write_queue=None):
        self.load_open_positions()


__all__ = ["PaperPositionManager"]
