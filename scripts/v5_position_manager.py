"""V5 LIVE 持仓管理 — 走 Broker(Binance/OKX)真实下单。

fail-closed:主仓开成功 + SL/TP 失败 → 立刻市价平回滚。
"""
import os
import sqlite3
from datetime import datetime, timezone, timedelta


SOFT_TARGET_MINUTES = 15
SL_TP_FAIL_OPEN = os.environ.get("SL_TP_FAIL_OPEN", "false").lower() in ("1", "true")


def _utcnow():
    return datetime.now(timezone.utc)


class V5PositionManager:
    def __init__(self, broker, db_path: str = "data/rabbit_hunter.db"):
        self.broker = broker
        self.db_path = db_path

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def open_position(self, *, symbol: str, side: str, entry_price: float,
                      sl_price: float, tp_price: float, size_usdt: float,
                      leverage: int) -> int:
        """LIVE 开仓:主仓 → SL → TP。任一失败按 fail-closed 处理。"""
        main = self.broker.create_order(
            symbol=symbol, side="sell" if side == "SHORT" else "buy",
            type="market", amount=size_usdt / entry_price,
        )
        position_size_coins = size_usdt / entry_price

        try:
            self.broker.create_order(
                symbol=symbol, side="buy" if side == "SHORT" else "sell",
                type="stop_market", amount=position_size_coins,
                params={"stopPrice": sl_price, "reduceOnly": True},
            )
        except Exception as e:
            if not SL_TP_FAIL_OPEN:
                self.broker.close_position(symbol)
                raise Exception(f"SL 下单失败,主仓已回滚: {e}")
            else:
                print(f"[V5PositionManager] SL 失败但 SL_TP_FAIL_OPEN=true,保留主仓: {e}")

        try:
            self.broker.create_order(
                symbol=symbol, side="buy" if side == "SHORT" else "sell",
                type="take_profit_market", amount=position_size_coins,
                params={"stopPrice": tp_price, "reduceOnly": True},
            )
        except Exception as e:
            if not SL_TP_FAIL_OPEN:
                self.broker.close_position(symbol)
                raise Exception(f"TP 下单失败,主仓已回滚: {e}")

        entry_time = _utcnow()
        target_close_at = entry_time + timedelta(minutes=SOFT_TARGET_MINUTES)
        conn = self._conn()
        try:
            cur = conn.execute("""
                INSERT INTO positions_v5 (
                    symbol, side, status, entry_price, entry_time,
                    sl_price, tp_price, size_usdt, leverage, position_size_coins,
                    target_close_at, extension_count, created_at, updated_at
                ) VALUES (?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """, (symbol, side, entry_price, entry_time.isoformat(),
                  sl_price, tp_price, size_usdt, leverage, position_size_coins,
                  target_close_at.isoformat(), entry_time.isoformat(), entry_time.isoformat()))
            pid = cur.lastrowid
            conn.commit()
            return pid
        finally:
            conn.close()

    def get_open_positions(self) -> list:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, symbol, side, entry_price, sl_price as stop_loss, "
                "tp_price as take_profit, target_close_at, extension_count, entry_time "
                "FROM positions_v5 WHERE status='OPEN'")
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            conn.close()

    def extend_position(self, position_id: int, extra_minutes: int = 15) -> None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT target_close_at, extension_count FROM positions_v5 WHERE id=?",
                (position_id,)).fetchone()
            if not row:
                return
            current_target = datetime.fromisoformat(row[0])
            new_target = current_target + timedelta(minutes=extra_minutes)
            conn.execute(
                "UPDATE positions_v5 SET target_close_at=?, extension_count=?, updated_at=? "
                "WHERE id=?",
                (new_target.isoformat(), (row[1] or 0) + 1, _utcnow().isoformat(), position_id))
            conn.commit()
        finally:
            conn.close()

    def close_position(self, position_id: int, *, exit_price: float, exit_reason: str) -> None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT symbol, side, entry_price, size_usdt, leverage, entry_time "
                "FROM positions_v5 WHERE id=?", (position_id,)).fetchone()
            if not row:
                return
            symbol, side, entry_price, size_usdt, leverage, entry_time_str = row

            try:
                self.broker.close_position(symbol)
            except Exception as e:
                print(f"[V5PositionManager] 平仓 broker 失败: {e}")

            entry_time = datetime.fromisoformat(entry_time_str)
            exit_time = _utcnow()
            holding_minutes = (exit_time - entry_time).total_seconds() / 60
            notional = (size_usdt or 0) * (leverage or 1)
            if side == "LONG":
                pnl_pct = (exit_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - exit_price) / entry_price
            pnl_usdt = notional * pnl_pct

            conn.execute("""
                UPDATE positions_v5 SET status='CLOSED', exit_price=?, exit_time=?,
                  exit_reason=?, pnl_usdt=?, pnl_pct=?, holding_minutes=?, updated_at=?
                WHERE id=?
            """, (exit_price, exit_time.isoformat(), exit_reason,
                  pnl_usdt, pnl_pct * 100, holding_minutes, exit_time.isoformat(), position_id))
            conn.commit()
        finally:
            conn.close()
