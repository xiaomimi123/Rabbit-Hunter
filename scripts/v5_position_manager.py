"""V5 LIVE 持仓管理 — 走 Broker(Binance/OKX)真实下单。

fail-closed: 主仓成功 + SL/TP 失败 → 立即市价平回滚。
fail-open  : SL_TP_FAIL_OPEN=true 时保留主仓,但带 sl_attached=False 标记。

HIGH-1+2 修复 (docs/code-audit-report.md):
  - 回滚 broker.close_position() 失败时仍 INSERT positions_v5,
    带 status='ERROR_RECONCILE_NEEDED' + error_context JSON,
    让人工/外部 reconciler 平账,而不是孤立持仓。
  - SL/TP 部分失败 (fail-open) 时 sl_attached/tp_attached 落库,
    监控/前端可识别"主仓有但保护单缺"的高风险状态。
"""
import json
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

    def _insert_position(
        self, *, symbol, side, status, entry_price, entry_time,
        sl_price, tp_price, size_usdt, leverage, position_size_coins,
        target_close_at, sl_attached, tp_attached, error_context,
    ) -> int:
        """统一 INSERT 路径,所有阶段(happy / fail-open / error-reconcile)共用。"""
        conn = self._conn()
        try:
            cur = conn.execute("""
                INSERT INTO positions_v5 (
                    symbol, side, status, entry_price, entry_time,
                    sl_price, tp_price, sl_attached, tp_attached, error_context,
                    size_usdt, leverage, position_size_coins,
                    target_close_at, extension_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """, (
                symbol, side, status, entry_price, entry_time.isoformat(),
                sl_price, tp_price,
                1 if sl_attached else 0, 1 if tp_attached else 0,
                json.dumps(error_context) if error_context else None,
                size_usdt, leverage, position_size_coins,
                target_close_at.isoformat(),
                entry_time.isoformat(), entry_time.isoformat(),
            ))
            pid = cur.lastrowid
            conn.commit()
            return pid
        finally:
            conn.close()

    def open_position(self, *, symbol: str, side: str, entry_price: float,
                      sl_price: float, tp_price: float, size_usdt: float,
                      leverage: int) -> int:
        """LIVE 开仓三阶段状态机:
          阶段 1 主仓 → 失败直接抛(无需写库,无真持仓)
          阶段 2 SL   → 失败按 SL_TP_FAIL_OPEN 选 fail-closed/fail-open
                        fail-closed 时再次失败 → 写库 ERROR_RECONCILE_NEEDED
          阶段 3 TP   → 同上
        """
        position_size_coins = size_usdt / entry_price
        entry_time = _utcnow()
        target_close_at = entry_time + timedelta(minutes=SOFT_TARGET_MINUTES)

        # ── 阶段 1: 主仓 ─────────────────────────────────────────────
        try:
            result = self.broker.open_position(
                symbol=symbol, side=side, quantity=position_size_coins,
            )
            if not result.get("success"):
                raise Exception(
                    f"主仓下单失败: {result.get('error_kind', 'PERMANENT')}: {result.get('error', 'unknown')}"
                )
        except Exception as e:
            if str(e).startswith("主仓下单失败:"):
                raise
            raise Exception(f"主仓下单失败: {type(e).__name__}: {e}")

        sl_attached = True
        tp_attached = True
        error_context: dict = {}

        # ── 阶段 2: SL 挂单 ──────────────────────────────────────────
        try:
            result = self.broker.set_stop_loss(
                symbol=symbol, stop_price=sl_price, side=side,
            )
            if not result.get("success"):
                raise Exception(
                    f"{result.get('error_kind', 'PERMANENT')}: {result.get('error', 'unknown')}"
                )
        except Exception as e_sl:
            sl_attached = False
            error_context["sl_error"] = f"{type(e_sl).__name__}: {e_sl}"
            if not SL_TP_FAIL_OPEN:
                # fail-closed: 回滚主仓
                try:
                    rb_result = self.broker.close_position(symbol)
                    if isinstance(rb_result, dict) and not rb_result.get("success"):
                        raise Exception(
                            f"{rb_result.get('error_kind', 'PERMANENT')}: {rb_result.get('error', 'unknown')}"
                        )
                    raise Exception(f"SL 下单失败,主仓已回滚: {e_sl}")
                except Exception as e_rb:
                    if "已回滚" in str(e_rb):
                        # 回滚成功后我们自己抛的友好消息 → 透传
                        raise
                    # 真·回滚失败:交易所有持仓 + 我们也没 SL → 必须写库标 ERROR
                    error_context["rollback_error"] = f"{type(e_rb).__name__}: {e_rb}"
                    pid = self._insert_position(
                        symbol=symbol, side=side,
                        status="ERROR_RECONCILE_NEEDED",
                        entry_price=entry_price, entry_time=entry_time,
                        sl_price=sl_price, tp_price=tp_price,
                        size_usdt=size_usdt, leverage=leverage,
                        position_size_coins=position_size_coins,
                        target_close_at=target_close_at,
                        sl_attached=False, tp_attached=False,
                        error_context=error_context,
                    )
                    print(f"[V5PositionManager] ⚠️  position {pid} 进 ERROR_RECONCILE_NEEDED: "
                          f"SL 失败 + 回滚失败,交易所可能有孤立持仓")
                    raise Exception(
                        f"SL 失败且回滚失败 (position {pid} 待 reconcile): "
                        f"sl={e_sl}; rollback={e_rb}"
                    )
            # SL_TP_FAIL_OPEN=true: 保留主仓继续,sl_attached=False
            print(f"[V5PositionManager] ⚠️  SL 失败但 SL_TP_FAIL_OPEN=true 保留主仓: {e_sl}")

        # ── 阶段 3: TP 挂单 ──────────────────────────────────────────
        try:
            result = self.broker.set_take_profit(
                symbol=symbol, take_profit_price=tp_price, side=side,
            )
            if not result.get("success"):
                raise Exception(
                    f"{result.get('error_kind', 'PERMANENT')}: {result.get('error', 'unknown')}"
                )
        except Exception as e_tp:
            tp_attached = False
            error_context["tp_error"] = f"{type(e_tp).__name__}: {e_tp}"
            if not SL_TP_FAIL_OPEN:
                try:
                    rb_result = self.broker.close_position(symbol)
                    if isinstance(rb_result, dict) and not rb_result.get("success"):
                        raise Exception(
                            f"{rb_result.get('error_kind', 'PERMANENT')}: {rb_result.get('error', 'unknown')}"
                        )
                    raise Exception(f"TP 下单失败,主仓已回滚: {e_tp}")
                except Exception as e_rb:
                    if "已回滚" in str(e_rb):
                        raise
                    error_context["rollback_error"] = f"{type(e_rb).__name__}: {e_rb}"
                    pid = self._insert_position(
                        symbol=symbol, side=side,
                        status="ERROR_RECONCILE_NEEDED",
                        entry_price=entry_price, entry_time=entry_time,
                        sl_price=sl_price, tp_price=tp_price,
                        size_usdt=size_usdt, leverage=leverage,
                        position_size_coins=position_size_coins,
                        target_close_at=target_close_at,
                        sl_attached=sl_attached, tp_attached=False,
                        error_context=error_context,
                    )
                    print(f"[V5PositionManager] ⚠️  position {pid} 进 ERROR_RECONCILE_NEEDED: "
                          f"TP 失败 + 回滚失败")
                    raise Exception(
                        f"TP 失败且回滚失败 (position {pid} 待 reconcile): "
                        f"tp={e_tp}; rollback={e_rb}"
                    )
            print(f"[V5PositionManager] ⚠️  TP 失败但 SL_TP_FAIL_OPEN=true 保留主仓: {e_tp}")

        # ── 全部 OK (或 fail-open 状态) — 写库 ──────────────────────
        # status: 全 attached → OPEN; 任一缺 (fail-open) → OPEN_DEGRADED
        status = "OPEN" if (sl_attached and tp_attached) else "OPEN_DEGRADED"
        return self._insert_position(
            symbol=symbol, side=side, status=status,
            entry_price=entry_price, entry_time=entry_time,
            sl_price=sl_price, tp_price=tp_price,
            size_usdt=size_usdt, leverage=leverage,
            position_size_coins=position_size_coins,
            target_close_at=target_close_at,
            sl_attached=sl_attached, tp_attached=tp_attached,
            error_context=error_context if error_context else None,
        )

    def get_open_positions(self) -> list:
        conn = self._conn()
        try:
            # 把 OPEN_DEGRADED 也算开仓中(还在跑,只是缺保护)
            cur = conn.execute(
                "SELECT id, symbol, side, entry_price, sl_price as stop_loss, "
                "tp_price as take_profit, target_close_at, extension_count, entry_time, "
                "status, sl_attached, tp_attached, error_context "
                "FROM positions_v5 WHERE status IN ('OPEN', 'OPEN_DEGRADED')")
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
