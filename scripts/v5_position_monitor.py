"""V5 持仓监控 — 每 30s 轮询活仓,决定是否平仓。

check_exit_triggers 是纯函数,易测;30s 轮询循环放 run() 协程里。
"""
import asyncio
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


MAX_EXTENSIONS = int(os.environ.get("V5_MAX_EXTENSIONS", "3"))
RSI_REVERSE_SHORT = float(os.environ.get("V5_RSI_REVERSE_SHORT", "65"))
RSI_REVERSE_LONG = float(os.environ.get("V5_RSI_REVERSE_LONG", "35"))


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
        if rsi < RSI_REVERSE_SHORT:
            return True
        if hist_prev < 0 and hist > 0:
            return True
    else:
        if rsi > RSI_REVERSE_LONG:
            return True
        if hist_prev > 0 and hist < 0:
            return True
    return False


def check_exit_triggers(position: dict, market: dict) -> Optional[dict]:
    """检查所有退出条件。返回 CloseIntent dict 或 None(不平)。

    优先级:SL → TP → soft target → 指标反转。
    """
    side = position["side"]
    current_price = market["price"]
    sl_price = position["stop_loss"]
    tp_price = position["take_profit"]

    if _sl_hit(side, current_price, sl_price):
        return {"position_id": position["id"], "exit_price": current_price,
                "exit_reason": "SL_HIT"}

    if _tp_hit(side, current_price, tp_price):
        return {"position_id": position["id"], "exit_price": current_price,
                "exit_reason": "TP_HIT"}

    target_str = position.get("target_close_at")
    if target_str:
        target = datetime.fromisoformat(target_str)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        if _utcnow() >= target:
            if (position.get("extension_count") or 0) >= MAX_EXTENSIONS:
                return {"position_id": position["id"], "exit_price": current_price,
                        "exit_reason": "AI_EXTEND_MAX"}
            return {"position_id": position["id"], "exit_price": current_price,
                    "exit_reason": "SOFT_TARGET_REACHED"}

    if _signal_reversed(side, market["rsi_15m"],
                        market["macd_hist_15m"], market["macd_hist_prev_15m"]):
        return {"position_id": position["id"], "exit_price": current_price,
                "exit_reason": "SIGNAL_REVERSE"}

    return None


class V5PositionMonitor:
    """每 30s 轮询活仓的协程。"""

    def __init__(self, paper_pm, live_pm, ai_assistant, indicator_fetcher,
                 mode_resolver, poll_interval_s: int = 30):
        self.paper_pm = paper_pm
        self.live_pm = live_pm
        self.ai = ai_assistant
        self.fetch_indicators = indicator_fetcher
        self.resolve_mode = mode_resolver
        self.poll_interval_s = poll_interval_s

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

            intent = check_exit_triggers(position, market)
            if not intent:
                continue

            reason = intent["exit_reason"]
            if reason == "SOFT_TARGET_REACHED":
                ai_decision = await self._ask_ai_extend(position, market)
                if ai_decision == "EXTEND":
                    pm.extend_position(position["id"], extra_minutes=15)
                    print(f"[V5PositionMonitor] {position['symbol']} AI 续仓 "
                          f"(extension {position['extension_count'] + 1}/{MAX_EXTENSIONS})")
                    continue
                pm.close_position(position["id"], exit_price=intent["exit_price"],
                                  exit_reason="AI_TIMEBOX")
                print(f"[V5PositionMonitor] {position['symbol']} CLOSE reason=AI_TIMEBOX")
            else:
                pm.close_position(position["id"], exit_price=intent["exit_price"],
                                  exit_reason=reason)
                print(f"[V5PositionMonitor] {position['symbol']} CLOSE reason={reason}")

    async def _ask_ai_extend(self, position: dict, market: dict) -> str:
        try:
            from scripts.ai.prompt import V5_SYSTEM_PROMPT
            msg = (
                f"Position {position['symbol']} {position['side']} entry={position['entry_price']} "
                f"current={market['price']} rsi_15m={market['rsi_15m']:.1f} "
                f"hist={market['macd_hist_15m']:+.4f} (prev {market['macd_hist_prev_15m']:+.4f}). "
                f"Soft target reached (ext {position['extension_count']}/{MAX_EXTENSIONS}). "
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
