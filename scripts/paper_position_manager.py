"""
Paper Position Manager (v5.0) — 在线影子交易（paper trading）

V5 新签名：
  open_position(*, enriched, indicators, decision, risk, ai) -> int  (返回 paper_trades.id)
  extend_position(position_id, extra_minutes=15) -> None
  close_position(position_id, *, exit_price, exit_reason) -> None
  get_open_positions() -> list[dict]

同时保留 V4.3 兼容方法供尚未迁移的调用方使用：
  load_open_positions / get_position / get_position_api_safe /
  check_exit_triggers / update_current_price / sync_positions

SHADOW 模式下 scorer 检测到信号 → 调本 manager → 写虚拟仓位 →
paper_monitor 异步任务 tick 当前价 → 触 SL/TP → 自动结算 PnL。

数据流：
  scorer → PaperPositionManager.open_position → paper_trades (status=OPEN)
  paper_monitor → fetch 当前价 → 触发判定 → close_position → 更新行
  前端 PaperTradesPage → 查 paper_trades → 展示 + 聚合 KPI
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List, Tuple

# V5: chandelier_stop 已废弃。V5 通过 v5_risk_calculator.plan() 直接计算 SL/TP，
# 调用方在 open_position 里传入 risk(RiskPlan) + ai(AIResult)。
# 此处保留 None stub 以避免下游代码（若有）做存在性判断时崩。
initialize_position = None  # type: ignore[assignment]


SOFT_TARGET_MINUTES = 15


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


class ConcurrencyLimitExceeded(Exception):
    """开仓时检测到当前 OPEN 数已达 max_concurrent 上限(TOCTOU 二次校验)。

    Finding 11: IMMEDIATE 事务内二次 count 双表(paper_trades + positions_v5),
    上层 catch 后应写 block_reason=MAX_CONCURRENT_POSITIONS_RACE,不重试。
    """


class PaperPositionManager:
    """V5 虚拟仓位管理器。

    构造函数接受 db_path（SQLite 直写，测试用）或 supabase_client（云端写入）。
    两者可以共存：优先用 db_path，其次用 supabase。
    """

    def __init__(
        self,
        supabase_client=None,
        db_path: Optional[str] = None,
    ):
        self.supabase = supabase_client
        self.db_path = db_path or "data/rabbit_hunter.db"
        # V4.3 compat cache
        self.positions_cache: Dict[str, Dict[str, Any]] = {}
        self.last_sync_time = _utcnow()

    # ─────────────────────────────────────────────────────────────────
    # 内部 SQLite helpers
    # ─────────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ─── v0.5.5: leverage 从 active exchange 配置拉（DB > env > 10）─────────────

    def _resolve_leverage(self) -> int:
        """读 active exchange 的 leverage（DB > env > default 10）。"""
        try:
            try:
                from exchange_config_manager import get_exchange_config_manager  # type: ignore[import-not-found]
            except ImportError:
                from scripts.exchange_config_manager import get_exchange_config_manager  # type: ignore[import-not-found]
            mgr = get_exchange_config_manager(self.supabase)
            active = mgr.get_active_exchange()
            cfg = mgr.get_config(active) or {}
            lev = cfg.get("leverage")
            if lev:
                return int(lev)
        except Exception:
            pass

        env_active = (os.environ.get("EXCHANGE", "okx") or "okx").lower()
        env_key = "OKX_LEVERAGE" if env_active == "okx" else "BINANCE_LEVERAGE"
        env_val = (os.environ.get(env_key) or "").strip()
        if env_val:
            try:
                return int(env_val)
            except ValueError:
                pass
        return 10

    # ─────────────────────────────────────────────────────────────────
    # V5 核心接口
    # ─────────────────────────────────────────────────────────────────

    def open_position(self, *, enriched, indicators, decision, risk, ai,
                      max_concurrent: Optional[int] = None) -> int:
        """SHADOW 开仓 — 返回 paper_trades.id。

        参数均为 v5_types 数据类：
          enriched:   EnrichedItem
          indicators: Indicators
          decision:   Decision
          risk:       RiskPlan
          ai:         AIResult
        """
        sl_dist = abs(risk.entry_price - risk.sl_price) * ai.sl_multiplier
        tp_dist = abs(risk.tp_price - risk.entry_price) * ai.tp_multiplier
        if decision.side == "LONG":
            sl_price = risk.entry_price - sl_dist
            tp_price = risk.entry_price + tp_dist
        else:
            sl_price = risk.entry_price + sl_dist
            tp_price = risk.entry_price - tp_dist
        size_usdt = max(1.0, risk.size_usdt * ai.size_multiplier)

        entry_time = _utcnow()
        target_close_at = entry_time + timedelta(minutes=SOFT_TARGET_MINUTES)

        conn = self._conn()
        try:
            if max_concurrent is not None:
                # Finding 11: 加 IMMEDIATE 锁 + 二次 count paper + live
                conn.execute("BEGIN IMMEDIATE")
                n_paper = conn.execute(
                    "SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'"
                ).fetchone()[0]
                try:
                    n_live = conn.execute(
                        "SELECT COUNT(*) FROM positions_v5 WHERE status='OPEN'"
                    ).fetchone()[0]
                except sqlite3.OperationalError:
                    n_live = 0  # positions_v5 表可能未 mig,视为 0
                if n_paper + n_live >= max_concurrent:
                    conn.rollback()
                    raise ConcurrencyLimitExceeded(
                        f"open_position 并发上限已达:{n_paper}(paper)+{n_live}(live)"
                        f">={max_concurrent},拒绝开仓"
                    )
            cur = conn.execute("""
                INSERT INTO paper_trades (
                    symbol, side, entry_price, status, strategy_id,
                    created_at, entry_time, target_close_at, extension_count,
                    current_price, stop_loss, take_profit, position_size_usdt,
                    leverage, ai_confidence, ai_sl_multiplier, ai_tp_multiplier,
                    ai_reason, entry_rsi_15m, entry_macd_hist_15m, entry_rsi_4h,
                    entry_atr_15m, signal_score
                ) VALUES (?, ?, ?, 'OPEN', 'v5_rsi_macd',
                          ?, ?, ?, 0,
                          ?, ?, ?, ?,
                          ?, ?, ?, ?,
                          ?, ?, ?, ?,
                          ?, ?)
            """, (
                enriched.symbol, decision.side, risk.entry_price,
                entry_time.isoformat(), entry_time.isoformat(), target_close_at.isoformat(),
                risk.entry_price, sl_price, tp_price, size_usdt,
                risk.leverage, ai.confidence, ai.sl_multiplier, ai.tp_multiplier,
                ai.reasoning, indicators.rsi_15m, indicators.macd_hist_15m,
                indicators.rsi_4h, indicators.atr_15m,
                risk.expected_rr,
            ))
            pid = cur.lastrowid
            conn.commit()
            return pid
        finally:
            conn.close()

    def extend_position(self, position_id: int, extra_minutes: int = 15) -> None:
        """AI 决定延期持仓：target_close_at += extra_minutes，extension_count++。"""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT target_close_at, extension_count FROM paper_trades WHERE id=?",
                (position_id,)).fetchone()
            if not row:
                return
            current_target = datetime.fromisoformat(row[0])
            new_target = current_target + timedelta(minutes=extra_minutes)
            new_count = (row[1] or 0) + 1
            conn.execute(
                "UPDATE paper_trades SET target_close_at=?, extension_count=?, "
                "updated_at=? WHERE id=?",
                (new_target.isoformat(), new_count, _utcnow().isoformat(), position_id))
            conn.commit()
        finally:
            conn.close()

    def close_position(
        self,
        position_id: Optional[int] = None,
        *,
        exit_price: float,
        exit_reason: str,
        # V4.3 compat kwargs — ignored when position_id is provided
        symbol: Optional[str] = None,
        write_queue=None,
    ) -> Optional[Dict[str, Any]]:
        """결仓。

        V5 签名：close_position(position_id, *, exit_price, exit_reason)
        V4.3 compat：close_position(symbol=..., exit_price=..., exit_reason=...)
        """
        # ── V4.3 compat path (symbol-based, supabase) ──────────────────────
        if position_id is None:
            if symbol is None:
                return None
            return self._close_position_v43(
                symbol=symbol, exit_price=exit_price,
                exit_reason=exit_reason, write_queue=write_queue,
            )

        # ── V5 path (id-based, SQLite) ──────────────────────────────────────
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT side, entry_price, position_size_usdt, leverage, entry_time "
                "FROM paper_trades WHERE id=?", (position_id,)).fetchone()
            if not row:
                return None
            side, entry_price, size_usdt, leverage, entry_time_str = row

            entry_time = datetime.fromisoformat(entry_time_str)
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)
            exit_time = _utcnow()
            holding_minutes = (exit_time - entry_time).total_seconds() / 60.0
            notional = (size_usdt or 0) * (leverage or 1)
            if side == "LONG":
                pnl_pct = (exit_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - exit_price) / entry_price
            pnl_usdt = notional * pnl_pct

            conn.execute(
                "UPDATE paper_trades SET status='CLOSED', exit_price=?, exit_time=?, "
                "exit_reason=?, pnl=?, pnl_percent=?, holding_hours=?, updated_at=? "
                "WHERE id=?",
                (exit_price, exit_time.isoformat(), exit_reason,
                 pnl_usdt, pnl_pct * 100, holding_minutes / 60.0,
                 exit_time.isoformat(), position_id))
            conn.commit()
            return {"id": position_id, "pnl": pnl_usdt}
        finally:
            conn.close()

    def get_open_positions(self) -> list:
        """返回所有 OPEN 状态的虚拟仓位（SQLite，V5 path）。"""
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, symbol, side, entry_price, target_close_at, "
                "extension_count, entry_time, stop_loss, take_profit, strategy_id, "
                "entry_atr_15m, highest_seen, lowest_seen, trailing_sl "
                "FROM paper_trades WHERE status='OPEN'")
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            conn.close()

    def update_trailing_state(
        self, position_id: int, *,
        highest_seen: float, lowest_seen: float, trailing_sl: float,
    ) -> None:
        """M5 Chandelier:更新 trailing 三件套。仅 SQLite,best-effort。"""
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE paper_trades SET highest_seen=?, lowest_seen=?, trailing_sl=?, "
                "updated_at=? WHERE id=?",
                (highest_seen, lowest_seen, trailing_sl,
                 _utcnow().isoformat(), position_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────
    # V4.3 兼容方法（供未迁移调用方使用）
    # ─────────────────────────────────────────────────────────────────

    def load_open_positions(self) -> Dict[str, Dict[str, Any]]:
        """加载所有 OPEN 状态的虚拟持仓（supabase path）。"""
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
            if self.supabase and pid is not None:
                try:
                    self.supabase.table("paper_trades").update(
                        {"current_price": current_price, "updated_at": _utcnow_iso()},
                    ).eq("id", pid).execute()
                except Exception:
                    pass
            position["current_price"] = current_price
            return None

        exit_reason, exit_price = trigger
        return self._close_position_v43(
            symbol=symbol, exit_price=exit_price, exit_reason=exit_reason,
        )

    def _close_position_v43(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str,
        write_queue=None,
    ) -> Optional[Dict[str, Any]]:
        """V4.3 symbol-based close (supabase path)。"""
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

        if side == "LONG":
            pnl_percent = (exit_price - entry_price) / entry_price * 100.0
        else:
            pnl_percent = (entry_price - exit_price) / entry_price * 100.0
        pnl = position_size_usdt * leverage * (pnl_percent / 100.0)

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
