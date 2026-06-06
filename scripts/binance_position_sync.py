"""
币安持仓同步模块（V4.5 + v45 blip 保护）

功能：
- 定期从币安 API 同步持仓
- 更新 positions_v43 表
- 处理数据不一致 — 但在不一致来自 API blip 时**不**误关 DB 持仓

v45 关键修复（防止"API blip 把所有 OPEN 仓位标 CLOSED → 下轮重开 → 持仓翻倍"）：
  1) 异常分类：ccxt RateLimit/NetworkError 直接 return TRANSIENT，不触碰 DB
  2) Bulk-blip 检测：DB 有 ≥2 OPEN 仓位 but broker 返回 0 → 极大概率是 blip，跳过 close phase
  3) 年龄宽限期：positions 创建时间 < 60s 的不参与 close（broker 端可能还在落定）
  4) 连续缺失计数：单个仓位需要连续 N 次 sync 都 missing 才标 CLOSED（默认 N=2）
  5) close 时用 db.current_price 算 exit_price/pnl，不留空
"""

import os
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

try:
    import ccxt
    _CCXT_TRANSIENT = (
        ccxt.NetworkError,
        ccxt.RequestTimeout,
        ccxt.DDoSProtection,
        ccxt.RateLimitExceeded,
        ccxt.ExchangeNotAvailable,
    )
except ImportError:
    ccxt = None
    _CCXT_TRANSIENT = ()

try:
    from binance_trader import BinanceTrader
except ImportError:
    BinanceTrader = None

from binance_config_manager import get_config_manager


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """安全解析 ISO 时间串；返回带 tz 的 UTC datetime 或 None。"""
    if not ts or not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None
    # 如果 created_at 是 naive（旧数据），假定为 UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class BinancePositionSync:
    """
    币安持仓同步器

    在 sync_positions() 中维护一个 per-position miss counter，
    所有"判定 broker 端无此仓位"的决策都经过 grace period + consecutive miss 检查。
    """

    def __init__(self, supabase_client=None, trader=None):
        self.supabase = supabase_client
        self.trader = trader
        self.last_sync_time: Optional[datetime] = None

        # v45 防 blip 状态 — 跨多次 sync_positions() 调用持久化
        # key: db_pos["id"]（或 fallback symbol），value: 连续 missing 次数
        self._miss_counts: Dict[str, int] = {}
        self._required_misses_to_close: int = int(
            os.environ.get("BINANCE_SYNC_REQUIRED_MISSES", "2")
        )
        self._grace_period_seconds: int = int(
            os.environ.get("BINANCE_SYNC_GRACE_SECONDS", "60")
        )
        # 当 DB 有 ≥ 这个数的 OPEN 仓位、broker 返回 0 → 判定为 blip
        self._blip_min_db_positions: int = int(
            os.environ.get("BINANCE_SYNC_BLIP_MIN_POSITIONS", "2")
        )

    def _get_trader(self):
        """获取交易器实例"""
        if self.trader:
            return self.trader

        config_manager = get_config_manager(self.supabase)
        config = config_manager.get_config()
        if not config:
            return None

        try:
            if BinanceTrader is None:
                from binance_trader import BinanceTrader as _BT
            else:
                _BT = BinanceTrader
            return _BT(
                api_key=config["api_key"],
                api_secret=config["api_secret"],
                testnet=config["testnet"],
                leverage=config.get("leverage", 10),
            )
        except Exception as e:
            print(f"[ERROR] 创建交易器失败: {e}")
            return None

    # ── broker 端拉取 ────────────────────────────────────────────────

    def _fetch_broker_positions(self, trader) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        返回 (positions_list, error_kind)。
          - 成功 → ([...], None)
          - 瞬时错误 → (None, "TRANSIENT")
          - 永久错误 → (None, "PERMANENT")
        """
        try:
            positions = trader.exchange.fapiPrivate_get_positionrisk()
            # 兜底：broker 偶尔返回 None / 非 list — 视为瞬时（可能是中间网关）
            if not isinstance(positions, list):
                return None, "TRANSIENT"
            return positions, None
        except _CCXT_TRANSIENT as e:
            print(f"[WARNING] broker positionRisk 瞬时错误: {type(e).__name__}: {e}")
            return None, "TRANSIENT"
        except Exception as e:
            # 区分 -1003（IP 限速）/ -2008（Invalid Api-Key）等
            msg = str(e)
            if any(code in msg for code in ("-1003", "-1015", "-1021")):
                print(f"[WARNING] broker 限速 / 时间戳错误（视为瞬时）: {e}")
                return None, "TRANSIENT"
            print(f"[ERROR] broker positionRisk 永久错误: {e}")
            return None, "PERMANENT"

    # ── 主同步流程 ───────────────────────────────────────────────────

    def sync_positions(self) -> Dict[str, Any]:
        """
        同步持仓。返回结果字典；当瞬时错误时 success=False、closed_count=0、
        miss_counts 保持不变（不会因 blip 误判持仓已平）。
        """
        trader = self._get_trader()
        if not trader:
            return {"success": False, "error": "交易器未配置", "synced_count": 0}
        if not self.supabase:
            return {"success": False, "error": "Supabase 未配置", "synced_count": 0}

        # 1) 拉 broker 持仓 — 失败时不触碰 DB
        binance_positions, fetch_err = self._fetch_broker_positions(trader)
        if binance_positions is None:
            return {
                "success": False,
                "error": f"broker 端拉取失败（{fetch_err}）— 跳过本轮 sync，miss 计数器保持",
                "error_kind": fetch_err,
                "synced_count": 0,
                "closed_count": 0,
            }

        # 2) 拉 DB OPEN 持仓
        try:
            db_response = self.supabase.table("positions_v43")\
                .select("*").eq("status", "OPEN").execute()
            db_positions: Dict[str, Dict[str, Any]] = {
                pos["symbol"]: pos for pos in (db_response.data or [])
            }
        except Exception as e:
            print(f"[ERROR] DB 拉 OPEN 持仓失败: {e}")
            return {
                "success": False,
                "error": f"DB 查询失败: {e}",
                "error_kind": "DB_ERROR",
                "synced_count": 0,
            }

        synced_count = 0
        created_count = 0
        updated_count = 0
        closed_count = 0
        skipped_blip = 0
        errors: List[str] = []
        broker_symbols: set = set()

        # 3) 同步 broker → DB（创建 / 更新）
        for binance_pos in binance_positions:
            symbol_binance = binance_pos.get("symbol", "")
            try:
                position_amt = float(binance_pos.get("positionAmt", 0) or 0)
            except (TypeError, ValueError):
                continue
            if abs(position_amt) < 0.0001:
                continue

            symbol_ccxt = self._binance_to_ccxt_symbol(symbol_binance)
            broker_symbols.add(symbol_ccxt)

            side = "LONG" if position_amt > 0 else "SHORT"
            try:
                entry_price = float(binance_pos.get("entryPrice", 0) or 0)
                current_price = float(binance_pos.get("markPrice", entry_price) or entry_price)
                leverage = float(binance_pos.get("leverage", 10) or 10)
                unrealized_pnl = float(binance_pos.get("unRealizedProfit", 0) or 0)
            except (TypeError, ValueError) as e:
                errors.append(f"解析 {symbol_ccxt} 价格字段失败: {e}")
                continue

            if symbol_ccxt in db_positions:
                # update 路径
                db_pos = db_positions[symbol_ccxt]
                update_data = {
                    "current_price": current_price,
                    "position_size": abs(position_amt),
                    "leverage": leverage,
                    "unrealized_pnl": unrealized_pnl,
                    "updated_at": _now_utc().isoformat(),
                }
                try:
                    self.supabase.table("positions_v43")\
                        .update(update_data).eq("id", db_pos["id"]).execute()
                    updated_count += 1
                except Exception as e:
                    errors.append(f"更新 {symbol_ccxt} 失败: {e}")
                # 仓位回归 → 重置 miss 计数
                self._miss_counts.pop(self._miss_key(db_pos), None)
            else:
                # broker 端有 / DB 端无 → 外部开仓，create 路径
                new_position = {
                    "symbol": symbol_ccxt,
                    "side": side,
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "position_size": abs(position_amt),
                    "leverage": leverage,
                    "status": "OPEN",
                    "created_at": _now_utc().isoformat(),
                    "updated_at": _now_utc().isoformat(),
                    "source": "BINANCE_SYNC",
                    "highest_price": current_price if side == "LONG" else None,
                    "lowest_price": current_price if side == "SHORT" else None,
                }
                try:
                    self.supabase.table("positions_v43").insert(new_position).execute()
                    created_count += 1
                except Exception as e:
                    errors.append(f"创建 {symbol_ccxt} 失败: {e}")

            synced_count += 1

        # 4) close phase — 仅当不是 bulk blip 时才执行
        bulk_blip = (
            len(db_positions) >= self._blip_min_db_positions
            and len(broker_symbols) == 0
        )
        if bulk_blip:
            print(
                f"[ALERT] bulk-blip 检测：DB 有 {len(db_positions)} 个 OPEN 仓位但 "
                f"broker 返回 0 — 跳过 close phase，miss 计数器不动"
            )
            skipped_blip = len(db_positions)
        else:
            now = _now_utc()
            for symbol_ccxt, db_pos in db_positions.items():
                if symbol_ccxt in broker_symbols:
                    continue  # 还在 broker，已经在上面 update 时 reset 过 miss

                # 4a) 年龄宽限期 — broker 端可能还在落定
                created_at = _parse_iso(db_pos.get("created_at"))
                if created_at is not None:
                    age_sec = (now - created_at).total_seconds()
                    if age_sec < self._grace_period_seconds:
                        print(
                            f"[INFO] {symbol_ccxt} 仓位仅 {age_sec:.0f}s "
                            f"(< {self._grace_period_seconds}s 宽限期) — 跳过 close 判定"
                        )
                        continue

                # 4b) miss 计数 — 需连续 N 次才 close
                key = self._miss_key(db_pos)
                self._miss_counts[key] = self._miss_counts.get(key, 0) + 1
                misses = self._miss_counts[key]
                if misses < self._required_misses_to_close:
                    print(
                        f"[INFO] {symbol_ccxt} broker 端无此仓位 (miss {misses}/"
                        f"{self._required_misses_to_close}) — 等待下一轮确认"
                    )
                    continue

                # 4c) 达到阈值 → 真正关闭，用 db.current_price 算 exit_price/pnl
                exit_price = float(
                    db_pos.get("current_price")
                    or db_pos.get("entry_price")
                    or 0
                )
                entry_price = float(db_pos.get("entry_price") or 0)
                position_size = float(db_pos.get("position_size") or 0)
                side = (db_pos.get("side") or "LONG").upper()
                if entry_price and position_size:
                    if side == "LONG":
                        pnl = (exit_price - entry_price) * position_size
                        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                    else:
                        pnl = (entry_price - exit_price) * position_size
                        pnl_pct = ((entry_price - exit_price) / entry_price) * 100
                else:
                    pnl = None
                    pnl_pct = None

                update_payload = {
                    "status": "CLOSED",
                    "closed_at": now.isoformat(),
                    "exit_reason": "BINANCE_SYNC_CONFIRMED_MISSING",
                    "current_price": exit_price,
                    "pnl": pnl,
                    "pnl_percent": pnl_pct,
                    "updated_at": now.isoformat(),
                }
                try:
                    self.supabase.table("positions_v43")\
                        .update(update_payload).eq("id", db_pos["id"]).execute()
                    closed_count += 1
                    self._miss_counts.pop(key, None)
                    print(
                        f"[V4.3 SYNC CLOSE] {symbol_ccxt} side={side} "
                        f"entry={entry_price:.4f} exit={exit_price:.4f} "
                        f"pnl={pnl if pnl is not None else 'N/A'}"
                    )
                except Exception as e:
                    errors.append(f"关闭 {symbol_ccxt} 失败: {e}")

        self.last_sync_time = _now_utc()

        result = {
            "success": True,
            "synced_count": synced_count,
            "created_count": created_count,
            "updated_count": updated_count,
            "closed_count": closed_count,
            "skipped_blip": skipped_blip,
            "active_miss_counts": dict(self._miss_counts),
            "errors": errors,
            "sync_time": self.last_sync_time.isoformat(),
        }

        if errors:
            print(f"[WARNING] 持仓同步完成，但有 {len(errors)} 个错误")
        else:
            print(
                f"[INFO] ✅ 持仓同步完成: 同步 {synced_count}，创建 {created_count}，"
                f"更新 {updated_count}，关闭 {closed_count}"
                + (f"，跳过 {skipped_blip}（blip）" if skipped_blip else "")
            )

        return result

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _miss_key(db_pos: Dict[str, Any]) -> str:
        """构造 miss counter 的 key — 优先用 id，fallback 用 symbol。"""
        if "id" in db_pos and db_pos["id"] is not None:
            return f"id:{db_pos['id']}"
        return f"sym:{db_pos.get('symbol', 'UNKNOWN')}"

    def _binance_to_ccxt_symbol(self, binance_symbol: str) -> str:
        """TRBUSDT -> TRB/USDT"""
        if binance_symbol.endswith("USDT"):
            return f"{binance_symbol[:-4]}/USDT"
        return binance_symbol

    def get_sync_status(self) -> Dict[str, Any]:
        return {
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "trader_configured": self._get_trader() is not None,
            "supabase_configured": self.supabase is not None,
            "miss_counts": dict(self._miss_counts),
            "required_misses_to_close": self._required_misses_to_close,
            "grace_period_seconds": self._grace_period_seconds,
        }


# 全局同步器实例
_position_sync: Optional[BinancePositionSync] = None


def get_position_sync(supabase_client=None, trader=None) -> BinancePositionSync:
    """获取持仓同步器实例（单例）"""
    global _position_sync
    if _position_sync is None:
        _position_sync = BinancePositionSync(supabase_client=supabase_client, trader=trader)
    elif supabase_client and _position_sync.supabase != supabase_client:
        _position_sync.supabase = supabase_client
    elif trader and _position_sync.trader != trader:
        _position_sync.trader = trader
    return _position_sync


__all__ = ["BinancePositionSync", "get_position_sync"]
