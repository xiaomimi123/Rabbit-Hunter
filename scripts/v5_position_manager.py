"""V5 LIVE 持仓管理 — 走 Broker(Binance/OKX)真实下单。

fail-closed: 主仓成功 + SL/TP 失败 → 立即市价平回滚。
fail-open  : 运行时 sl_tp_fail_open=true 时保留主仓,但带 sl_attached=False 标记。

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
from typing import Optional


SOFT_TARGET_MINUTES = 15


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
          阶段 2 SL   → 失败按 sl_tp_fail_open 选 fail-closed/fail-open
                        fail-closed 时再次失败 → 写库 ERROR_RECONCILE_NEEDED
          阶段 3 TP   → 同上
        """
        from scripts.settings_db import read_sl_tp_fail_open
        sl_tp_fail_open = read_sl_tp_fail_open(self.db_path)

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
            if not sl_tp_fail_open:
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
            # sl_tp_fail_open=true: 保留主仓继续,sl_attached=False
            print(f"[V5PositionManager] ⚠️  SL 失败但 sl_tp_fail_open=true 保留主仓: {e_sl}")

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
            if not sl_tp_fail_open:
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
            print(f"[V5PositionManager] ⚠️  TP 失败但 sl_tp_fail_open=true 保留主仓: {e_tp}")

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

    def _update_closed(
        self, conn: sqlite3.Connection, position_id: int, side: str,
        entry_price: float, size_usdt: float, leverage: int,
        entry_time_str: str, exit_price: float, exit_reason: str,
        existing_ctx_json: Optional[str],
        exit_price_source: str = "monitor_tick",
    ) -> None:
        """成功平仓 or PERMANENT 补记账 —— 计算 PnL 并写 CLOSED。

        若 error_context 里有 close_error（前次 RETRYABLE 遗留），清掉。
        F14: 加 exit_price_source 到 error_context 让审计可见 fill 来源。
        """
        entry_time = datetime.fromisoformat(entry_time_str)
        exit_time = _utcnow()
        holding_minutes = (exit_time - entry_time).total_seconds() / 60
        notional = (size_usdt or 0) * (leverage or 1)
        if side == "LONG":
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - exit_price) / entry_price
        pnl_usdt = notional * pnl_pct

        # 清掉前次失败的 close_error（若有）,保留其他键（如 open_error）
        ctx = self._parse_error_context(existing_ctx_json)
        ctx.pop("close_error", None)
        ctx["exit_price_source"] = exit_price_source  # F14: audit trail
        ctx_json = json.dumps(ctx)  # ctx 至少含 source, 不再判空

        conn.execute("""
            UPDATE positions_v5 SET status='CLOSED', exit_price=?, exit_time=?,
              exit_reason=?, pnl_usdt=?, pnl_pct=?, holding_minutes=?,
              error_context=?, updated_at=?
            WHERE id=?
        """, (
            exit_price, exit_time.isoformat(), exit_reason,
            pnl_usdt, pnl_pct * 100, holding_minutes, ctx_json, exit_time.isoformat(),
            position_id,
        ))

    def _append_close_error(
        self, conn: sqlite3.Connection, position_id: int, kind: str,
        msg: str, existing_ctx_json: Optional[str],
    ) -> None:
        """RETRYABLE:保持 status,合并 close_error 到 error_context。"""
        ctx = self._parse_error_context(existing_ctx_json)
        now = _utcnow().isoformat()
        ctx["close_error"] = {"kind": kind, "msg": msg, "at": now}
        conn.execute(
            "UPDATE positions_v5 SET error_context=?, updated_at=? WHERE id=?",
            (json.dumps(ctx), now, position_id),
        )

    def _mark_reconcile_needed(
        self, conn: sqlite3.Connection, position_id: int, msg: str,
        existing_ctx_json: Optional[str],
    ) -> None:
        """UNKNOWN:标 ERROR_RECONCILE_NEEDED,合并 close_error。"""
        ctx = self._parse_error_context(existing_ctx_json)
        now = _utcnow().isoformat()
        ctx["close_error"] = {"kind": "UNKNOWN", "msg": msg, "at": now}
        conn.execute(
            "UPDATE positions_v5 SET status='ERROR_RECONCILE_NEEDED', "
            "error_context=?, updated_at=? WHERE id=?",
            (json.dumps(ctx), now, position_id),
        )

    @staticmethod
    def _parse_error_context(existing: Optional[str]) -> dict:
        """把已有 error_context JSON 反序列化 or 空 dict。"""
        if not existing:
            return {}
        try:
            v = json.loads(existing)
            return v if isinstance(v, dict) else {}
        except json.JSONDecodeError:
            return {}

    def close_position(self, position_id: int, *, exit_price: float, exit_reason: str) -> None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT symbol, side, entry_price, size_usdt, leverage, entry_time, error_context "
                "FROM positions_v5 WHERE id=?", (position_id,)).fetchone()
            if not row:
                return
            symbol, side, entry_price, size_usdt, leverage, entry_time_str, existing_ctx_json = row

            # ── broker.close_position 结果分类 ──────────────
            broker_error_kind: Optional[str] = None
            broker_error_msg: Optional[str] = None
            try:
                rb_result = self.broker.close_position(symbol)
                if isinstance(rb_result, dict) and not rb_result.get("success"):
                    broker_error_kind = rb_result.get("error_kind", "UNKNOWN")
                    broker_error_msg = rb_result.get("error", "unknown")
            except Exception as e:
                broker_error_kind = "UNKNOWN"
                broker_error_msg = f"{type(e).__name__}: {e}"

            # ── 决策分支 ────────────────────────────────
            if broker_error_kind is None:
                # F14: broker 成功成交时优先用 fill price;无 price 字段 → fallback caller
                broker_price: Optional[float] = None
                if isinstance(rb_result, dict):
                    raw = rb_result.get("price")
                    if raw is not None:
                        try:
                            broker_price = float(raw)
                        except (TypeError, ValueError):
                            broker_price = None
                actual_exit = broker_price if broker_price is not None else exit_price
                source = "broker_fill" if broker_price is not None else "monitor_tick"
                self._update_closed(
                    conn, position_id, side, entry_price, size_usdt, leverage,
                    entry_time_str, actual_exit, exit_reason, existing_ctx_json,
                    exit_price_source=source,
                )
            elif broker_error_kind == "PERMANENT":
                # 交易所已平 → DB 补记账
                print(
                    f"[V5PositionManager] close broker PERMANENT: {broker_error_msg}; "
                    f"position {position_id} 交易所已平,DB 补记 CLOSED"
                )
                # F14: 无 fill data → 保留 caller monitor tick 价 + 标 source
                self._update_closed(
                    conn, position_id, side, entry_price, size_usdt, leverage,
                    entry_time_str, exit_price,
                    f"{exit_reason}|broker_permanent:{broker_error_msg}",
                    existing_ctx_json,
                    exit_price_source="monitor_tick_permanent",
                )
            elif broker_error_kind == "RETRYABLE":
                # 保持 OPEN + error_context, monitor 下 tick 重试
                print(
                    f"[V5PositionManager] close broker RETRYABLE: {broker_error_msg}; "
                    f"position {position_id} 保持 OPEN 待重试"
                )
                self._append_close_error(
                    conn, position_id, "RETRYABLE", broker_error_msg, existing_ctx_json,
                )
            else:
                # UNKNOWN → 保守 → 人工对账
                print(
                    f"[V5PositionManager] close broker UNKNOWN error: {broker_error_msg}; "
                    f"position {position_id} → ERROR_RECONCILE_NEEDED"
                )
                self._mark_reconcile_needed(
                    conn, position_id, broker_error_msg, existing_ctx_json,
                )

            conn.commit()
        finally:
            conn.close()
