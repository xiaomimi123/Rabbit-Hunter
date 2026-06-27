"""V5 持仓监控 — 每 30s 轮询活仓,决定是否平仓。

check_exit_triggers 是纯函数,易测;30s 轮询循环放 run() 协程里。
"""
import asyncio
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


from scripts.v5_params import get_param


def _enqueue_ws(db_path: str, payload: dict) -> None:
    """跨进程 WS 消息总线:写 ws_event_queue,api 进程 poll 后广播。"""
    import json, sqlite3
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "INSERT INTO ws_event_queue (payload_json) VALUES (?)",
                (json.dumps(payload, ensure_ascii=False),),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[V5PositionMonitor] WS enqueue 失败: {e}")


def _max_extensions() -> int:
    # 2026-06-27 应用 max-hold-scan 实验最优档:
    #   v5_max_extensions=15 → soft_target(15min) × (1+15) = 240min 窗口 (4h)
    #   PF=1.51 + R/小时峰值 + maxDD 比 480 还小,见 docs/max-hold-scan-experiment.md
    return int(get_param("v5_max_extensions", 15, int))


def _signal_reverse_min_minutes() -> int:
    """SIGNAL_REVERSE 最短持仓门槛 (分钟)。
    历史 28 笔 SR 全部在 30min 内触发 (max 11.5min),平均 2.4min。
    设 30 → 在 240min 窗口的前 30min 屏蔽 SR 抢跑,30min 后仍允许真趋势反转兜底。
    设 0 → 旧行为 (SR 立即生效)。
    见 docs/applied-optimal-exit-config.md
    """
    return int(get_param("v5_signal_reverse_min_minutes", 30, int))


def _rsi_reverse_short() -> float:
    return float(get_param("v5_rsi_reverse_short", 65.0, float))


def _rsi_reverse_long() -> float:
    return float(get_param("v5_rsi_reverse_long", 35.0, float))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sl_hit(side: str, current_price: float, sl_price: float) -> bool:
    if side == "LONG":
        return current_price <= sl_price
    return current_price >= sl_price


def _tp_hit(side: str, current_price: float, tp_price: float) -> bool:
    if side == "LONG":
        return current_price >= tp_price
    return current_price <= tp_price


def _signal_reversed(side: str, rsi: float, hist: float, hist_prev: float) -> bool:
    """SIGNAL_REVERSE 判定:
    - SHORT:RSI 跌破 65,或 MACD 由死叉(hist<0)重新金叉(hist>0)
    - LONG: RSI 涨过 35,或 MACD 由金叉(hist>0)重新死叉(hist<0)
    """
    if side == "SHORT":
        if rsi < _rsi_reverse_short():
            return True
        if hist_prev < 0 and hist > 0:
            return True
    else:
        if rsi > _rsi_reverse_long():
            return True
        if hist_prev > 0 and hist < 0:
            return True
    return False


def check_exit_triggers(position: dict, market: dict) -> Optional[dict]:
    """检查所有退出条件。返回 CloseIntent dict 或 None(不平)。

    优先级:SL(含 trailing) → TP → soft target → 指标反转。
    """
    from scripts.chandelier import effective_sl_price

    side = position["side"]
    current_price = market["price"]
    static_sl = position["stop_loss"]
    tp_price = position["take_profit"]

    # M5 Chandelier:trailing_sl 比 static 更近时,用 trailing。
    sl_price = effective_sl_price(
        side=side,
        static_sl=static_sl,
        trailing_sl=position.get("trailing_sl"),
    )

    if _sl_hit(side, current_price, sl_price):
        exit_reason = "TRAILING_SL_HIT" if (
            position.get("trailing_sl") is not None and sl_price != static_sl
        ) else "SL_HIT"
        return {"position_id": position["id"], "exit_price": current_price,
                "exit_reason": exit_reason}

    if _tp_hit(side, current_price, tp_price):
        return {"position_id": position["id"], "exit_price": current_price,
                "exit_reason": "TP_HIT"}

    target_str = position.get("target_close_at")
    if target_str:
        target = datetime.fromisoformat(target_str)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        if _utcnow() >= target:
            if (position.get("extension_count") or 0) >= _max_extensions():
                return {"position_id": position["id"], "exit_price": current_price,
                        "exit_reason": "AI_EXTEND_MAX"}
            return {"position_id": position["id"], "exit_price": current_price,
                    "exit_reason": "SOFT_TARGET_REACHED"}

    # SIGNAL_REVERSE 只对 auto 策略生效:手动单是用户主观决定,
    # 不应该被规则引擎"反悔"。SL/TP/SOFT_TARGET 仍然适用。
    # 加最短持仓门槛 (_signal_reverse_min_minutes,默认 30):防止 SR 在 240min 窗口
    # 前 30min 抢跑赢单。30min 后仍允许真趋势反转 SR 兜底。
    if position.get("strategy_id") != "v5_manual":
        entry_time_str = position.get("entry_time")
        elapsed_min = 9999.0   # 默认通过 (兼容无 entry_time 的旧数据)
        if entry_time_str:
            try:
                et = datetime.fromisoformat(entry_time_str)
                if et.tzinfo is None:
                    et = et.replace(tzinfo=timezone.utc)
                elapsed_min = (_utcnow() - et).total_seconds() / 60
            except (ValueError, TypeError):
                pass
        if elapsed_min >= _signal_reverse_min_minutes():
            if _signal_reversed(side, market["rsi_15m"],
                                market["macd_hist_15m"], market["macd_hist_prev_15m"]):
                return {"position_id": position["id"], "exit_price": current_price,
                        "exit_reason": "SIGNAL_REVERSE"}

    return None


class V5PositionMonitor:
    """每 30s 轮询活仓的协程。"""

    def __init__(self, paper_pm, live_pm, ai_assistant, indicator_fetcher,
                 mode_resolver, poll_interval_s: int = 30,
                 db_path: str = "data/rabbit_hunter.db"):
        self.paper_pm = paper_pm
        self.live_pm = live_pm
        self.ai = ai_assistant
        self.fetch_indicators = indicator_fetcher
        self.resolve_mode = mode_resolver
        self.poll_interval_s = poll_interval_s
        self.db_path = db_path

    async def run(self):
        print(f"[V5PositionMonitor] 启动,轮询间隔 {self.poll_interval_s}s")
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                print("[V5PositionMonitor] 收到取消信号,退出")
                return
            except Exception as e:
                print(f"[V5PositionMonitor] tick 异常: {type(e).__name__}: {e}")
            await asyncio.sleep(self.poll_interval_s)

    async def _tick(self):
        mode = self.resolve_mode()
        pm = self.paper_pm if mode == "SHADOW" else self.live_pm
        if not pm:
            return
        for position in pm.get_open_positions():
            try:
                market = await self.fetch_indicators(position["symbol"])
            except Exception as e:
                print(f"[V5PositionMonitor] {position['symbol']} 拉指标失败: {e}")
                continue

            # M5 Chandelier:每 tick 更新 highest/lowest/trailing,只收紧不放宽。
            try:
                from scripts.chandelier import update_chandelier
                from scripts.v5_params import get_param
                k = float(get_param("v5_sl_atr_mult", 1.5, float))
                new_high, new_low, new_trail = update_chandelier(
                    side=position["side"],
                    current_price=float(market["price"]),
                    entry_atr=float(position.get("entry_atr_15m") or 0),
                    highest_seen=position.get("highest_seen"),
                    lowest_seen=position.get("lowest_seen"),
                    trailing_sl=position.get("trailing_sl"),
                    k=k,
                )
                if hasattr(pm, "update_trailing_state"):
                    pm.update_trailing_state(
                        position["id"], highest_seen=new_high,
                        lowest_seen=new_low, trailing_sl=new_trail,
                    )
                # 注入到当前 position dict 让本轮的 check_exit_triggers 看到最新值
                position["highest_seen"] = new_high
                position["lowest_seen"] = new_low
                position["trailing_sl"] = new_trail
            except Exception as e:
                print(f"[V5PositionMonitor] {position['symbol']} chandelier 更新失败: {e}")

            intent = check_exit_triggers(position, market)
            if not intent:
                continue

            reason = intent["exit_reason"]
            if reason == "SOFT_TARGET_REACHED":
                ai_decision = await self._ask_ai_extend(position, market)
                if ai_decision == "EXTEND":
                    pm.extend_position(position["id"], extra_minutes=15)
                    print(f"[V5PositionMonitor] {position['symbol']} AI 续仓 "
                          f"(extension {position['extension_count'] + 1}/{_max_extensions()})")
                    _enqueue_ws(self.db_path, {
                        "type": "position_extended",
                        "position_id": position["id"],
                        "symbol": position["symbol"],
                        "extension_count": (position.get("extension_count") or 0) + 1,
                    })
                    continue
                pm.close_position(position["id"], exit_price=intent["exit_price"],
                                  exit_reason="AI_TIMEBOX")
                print(f"[V5PositionMonitor] {position['symbol']} CLOSE reason=AI_TIMEBOX")
                _enqueue_ws(self.db_path, {
                    "type": "position_closed",
                    "position_id": position["id"],
                    "symbol": position["symbol"],
                    "exit_price": intent["exit_price"],
                    "exit_reason": "AI_TIMEBOX",
                })
                # B-Phase-1: 触发 reflection 入队 (best-effort, don't block monitor)
                try:
                    from scripts.local_db import enqueue_reflection
                    enqueue_reflection(position["id"], db_path=self.db_path)
                except Exception as e:
                    print(f"[V5PositionMonitor] reflection enqueue failed: {e}")
            else:
                pm.close_position(position["id"], exit_price=intent["exit_price"],
                                  exit_reason=reason)
                print(f"[V5PositionMonitor] {position['symbol']} CLOSE reason={reason}")
                _enqueue_ws(self.db_path, {
                    "type": "position_closed",
                    "position_id": position["id"],
                    "symbol": position["symbol"],
                    "exit_price": intent["exit_price"],
                    "exit_reason": reason,
                })
                # B-Phase-1: 触发 reflection 入队 (best-effort, don't block monitor)
                try:
                    from scripts.local_db import enqueue_reflection
                    enqueue_reflection(position["id"], db_path=self.db_path)
                except Exception as e:
                    print(f"[V5PositionMonitor] reflection enqueue failed: {e}")

    async def _ask_ai_extend(self, position: dict, market: dict) -> str:
        try:
            from scripts.ai.prompt import V5_SYSTEM_PROMPT
            msg = (
                f"Position {position['symbol']} {position['side']} entry={position['entry_price']} "
                f"current={market['price']} rsi_15m={market['rsi_15m']:.1f} "
                f"hist={market['macd_hist_15m']:+.4f} (prev {market['macd_hist_prev_15m']:+.4f}). "
                f"Soft target reached (ext {position['extension_count']}/{_max_extensions()}). "
                "Reply with single word: EXTEND or CLOSE."
            )
            resp = await asyncio.wait_for(
                self.ai.quick_yes_no(V5_SYSTEM_PROMPT, msg),
                timeout=15.0,
            )
            return "EXTEND" if "EXTEND" in (resp or "").upper() else "CLOSE"
        except Exception as e:
            print(f"[V5PositionMonitor] AI 续仓决策异常 → 默认平: {e}")
            return "CLOSE"
