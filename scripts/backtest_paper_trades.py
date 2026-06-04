"""
离线模拟交易/回测闭环（Rabbit Hunter 4.0 / MVP）

做什么：
- 从 ai_training_data 读取历史信号
- 满足条件的样本生成一笔“模拟交易（paper trade）”
- 用未来 horizon_minutes 的价格结算收益（不下单）
- 写入 public.paper_trades（幂等：unique(symbol, source_row_id)）

最小开仓规则（MVP，可按你的 V4 规则再加强）：
- technical_signal in ('LONG','SHORT')
- is_trade_allowed = true （V4 允许跟庄）
- ai_allowed = true （AI 允许继续参与）

结算：
- LONG: ret = (future_price - entry_price) / entry_price
- SHORT: ret = (entry_price - future_price) / entry_price

用法：
  py -3 scripts/backtest_paper_trades.py

PowerShell 环境变量提示：
- PowerShell 里不要用 `set XXX=1`（那是 cmd 的语法），请用：
  $env:PAPER_BACKTEST_DAYS="1"
  $env:PAPER_BACKTEST_HORIZON_MINUTES="10"
  py -3 scripts/backtest_paper_trades.py

环境：
  .env 需要 SUPABASE_URL / SUPABASE_KEY
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from supabase import Client, create_client
from bisect import bisect_left


@dataclass(frozen=True)
class BacktestConfig:
    # 真实策略回测默认：更贴近“近期真实可执行样本”
    days: int = 30
    limit: int = 8000
    # 默认 30m 结算，更贴近短线/波段的快速验证；可用环境变量调整
    horizon_minutes: int = 30
    notional_usdt: float = 100.0
    allowed_signal: tuple[str, ...] = ("LONG", "SHORT")
    require_trade_allowed: bool = True
    require_ai_allowed: bool = True
    # 真实策略回测默认：不允许“推断方向”，只回测策略真实给出的 LONG/SHORT
    infer_side_when_missing: bool = False
    infer_normal_side: str = ""  # 真实策略回测默认禁用；仅用于短数据期“先产样本”调试


def normalize_signal(x: Any) -> str:
    """
    将策略信号标准化为 LONG/SHORT/""。
    兼容 BUY/SELL 等历史/实验字段。
    """
    s = str(x or "").strip().upper()
    if s in ("LONG", "BUY", "BULL", "UP"):
        return "LONG"
    if s in ("SHORT", "SELL", "BEAR", "DOWN"):
        return "SHORT"
    return ""


def infer_side_from_v4(cfg: BacktestConfig, r: Dict[str, Any]) -> str:
    """
    当 technical_signal 缺失时，基于 V4 语义做一个保守推断（用于“先产样本回测/看收益”）。
    规则可后续按你的白皮书再细化。
    """
    kz = str(r.get("kill_zone_signal") or "").upper()
    phase = str(r.get("market_phase") or "").upper()
    regime = str(r.get("market_regime") or "").upper()

    # Kill Zone 直觉：逼空/吸筹/洗盘更偏 LONG（先产样本）
    if kz in ("SQUEEZE", "ACCUMULATION", "SHAKEOUT"):
        return "LONG"

    # P4 派发偏 SHORT（如果未来你允许在 P4 做对冲）
    if phase == "P4_DISTRIBUTION":
        return "SHORT"

    # 兼容：用 market_regime 兜底推断（采集器一般更稳定写入这个字段）
    if any(k in regime for k in ("SQUEEZE", "ACCUMULATION", "SHAKEOUT", "P3A", "P2")):
        return "LONG"
    if any(k in regime for k in ("P4", "BEAR")):
        return "SHORT"

    # 短数据期兜底：允许把 NORMAL/UNKNOWN 临时映射成固定方向以“先产样本”
    if cfg.infer_normal_side in ("LONG", "SHORT") and (regime in ("NORMAL", "UNKNOWN", "")):
        return cfg.infer_normal_side

    # 其他不推断
    return ""


def init_supabase() -> Client:
    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(dotenv_path=base_dir / ".env")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("缺少 SUPABASE_URL / SUPABASE_KEY")
    return create_client(url, key)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _safe_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:  # noqa: BLE001
        return None


def fetch_rows(supabase: Client, cfg: BacktestConfig) -> List[Dict[str, Any]]:
    start_time = _iso(datetime.now(timezone.utc) - timedelta(days=cfg.days))
    resp = (
        supabase.table("ai_training_data")
        .select(
            "id, created_at, symbol, price, technical_signal, is_trade_allowed, "
            "market_regime, "
            "market_phase, kill_zone_signal, exit_clarity_score, confidence_level, "
            "p3a_match_score, ai_effective_threshold, ai_version, ai_score, ai_allowed"
        )
        .gte("created_at", start_time)
        .order("created_at", desc=False)
        .limit(cfg.limit)
        .execute()
    )
    return list(resp.data or [])


def fetch_future_price(supabase: Client, symbol: str, t0_iso: str, horizon_minutes: int) -> float | None:
    t0 = _parse_iso(t0_iso)
    t_future = _iso(t0 + timedelta(minutes=horizon_minutes))
    resp = (
        supabase.table("ai_training_data")
        .select("price, created_at")
        .eq("symbol", symbol)
        .gte("created_at", t_future)
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    if resp.data:
        p = resp.data[0].get("price")
        return float(p) if p is not None else None
    return None


def build_future_index(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    为每个 symbol 建立时间序列索引，用于本地快速查找 horizon 后的未来价格。
    这样避免每条样本都打一次 Supabase 查询（极大加速短期回测）。
    """
    idx: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        sym = r.get("symbol")
        if not sym:
            continue
        p = _safe_float(r.get("price"))
        if p is None or p <= 0:
            continue
        try:
            ts = _parse_iso(str(r.get("created_at"))).timestamp()
        except Exception:  # noqa: BLE001
            continue
        if sym not in idx:
            idx[sym] = {"t": [], "p": []}
        idx[sym]["t"].append(ts)
        idx[sym]["p"].append(float(p))
    return idx


def fetch_future_price_local(
    future_idx: Dict[str, Dict[str, Any]],
    symbol: str,
    t0_iso: str,
    horizon_minutes: int,
) -> float | None:
    seq = future_idx.get(symbol)
    if not seq:
        return None
    try:
        t0 = _parse_iso(t0_iso).timestamp()
    except Exception:  # noqa: BLE001
        return None
    target = t0 + horizon_minutes * 60
    times: List[float] = seq["t"]
    i = bisect_left(times, target)
    if i < 0 or i >= len(times):
        return None
    return float(seq["p"][i])


def build_trade_row(cfg: BacktestConfig, r: Dict[str, Any], future_price: float) -> Dict[str, Any]:
    entry_price = float(r["price"])
    side = str(r.get("technical_signal") or "").upper()
    
    # V4.1: 使用 ATR 止损替代固定 TP/SL
    exit_reason = "paper_backtest_horizon_exit"
    exit_price = float(future_price)
    atr_stop_triggered = False
    
    try:
        from v41_risk_manager import calculate_chandelier_stop
        
        # 获取 V4.1 字段
        atr_value = r.get("atr_value")
        atr_multiplier = r.get("atr_multiplier")
        chandelier_stop_price = r.get("chandelier_stop_price")
        
        # 如果 ATR 止损价格存在，检查是否触发止损
        if chandelier_stop_price is not None and atr_value is not None and atr_multiplier is not None:
            stop_price = float(chandelier_stop_price)
            is_long = (side == "LONG")
            
            # 检查是否触发止损
            if is_long and future_price < stop_price:
                exit_price = stop_price
                exit_reason = "v41_atr_stop_loss"
                atr_stop_triggered = True
            elif not is_long and future_price > stop_price:
                exit_price = stop_price
                exit_reason = "v41_atr_stop_loss"
                atr_stop_triggered = True
    except ImportError:
        pass  # V4.1 模块未安装，使用默认逻辑
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] V4.1 ATR 止损计算失败: {e}")
    
    # 计算收益（使用实际退出价格）
    if side == "SHORT":
        ret = (entry_price - exit_price) / entry_price
    else:
        ret = (exit_price - entry_price) / entry_price
    
    # V4.1: 使用动态仓位计算（如果存在）
    position_size_coin = r.get("position_size_coin")
    if position_size_coin is not None:
        # 使用动态仓位计算 PnL
        pnl_usdt = float(position_size_coin) * float(exit_price - entry_price) if side == "LONG" else float(position_size_coin) * float(entry_price - exit_price)
    else:
        # 回退到固定名义价值
        pnl_usdt = float(cfg.notional_usdt) * float(ret)
    
    entry_time = r.get("created_at")
    exit_time = _iso(_parse_iso(entry_time) + timedelta(minutes=cfg.horizon_minutes))

    return {
        "symbol": r["symbol"],
        "source_row_id": r["id"],
        "entry_time": entry_time,
        "exit_time": exit_time,
        "side": side,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "horizon_minutes": int(cfg.horizon_minutes),
        "ret": float(ret),
        "pnl_usdt": float(pnl_usdt),
        "status": "CLOSED",
        "reason": exit_reason,
        "market_phase": r.get("market_phase"),
        "kill_zone_signal": r.get("kill_zone_signal"),
        "exit_clarity_score": r.get("exit_clarity_score"),
        "confidence_level": r.get("confidence_level"),
        "p3a_match_score": r.get("p3a_match_score"),
        "ai_effective_threshold": r.get("ai_effective_threshold"),
        "ai_version": r.get("ai_version"),
        "ai_score": r.get("ai_score"),
        "ai_allowed": r.get("ai_allowed"),
        # V4.1 新增字段
        "atr_value": r.get("atr_value"),
        "atr_multiplier": r.get("atr_multiplier"),
        "structure_gap": r.get("structure_gap"),
        "structure_gap_method": r.get("structure_gap_method"),
        "phase_age_candles": r.get("phase_age_candles"),
        "phase_age_percent": r.get("phase_age_percent"),
        "v41_block_reason": r.get("v41_block_reason"),
        "chandelier_stop_price": r.get("chandelier_stop_price"),
        "position_size_coin": position_size_coin,
        "atr_stop_triggered": atr_stop_triggered,
        "phase_4h": r.get("phase_4h"),
        "phase_1h": r.get("phase_1h"),
    }


def main() -> None:
    cfg = BacktestConfig(
        days=int(os.environ.get("PAPER_BACKTEST_DAYS", "30")),
        limit=int(os.environ.get("PAPER_BACKTEST_LIMIT", "8000")),
        horizon_minutes=int(os.environ.get("PAPER_BACKTEST_HORIZON_MINUTES", "30")),
        notional_usdt=float(os.environ.get("PAPER_BACKTEST_NOTIONAL", "100")),
        require_trade_allowed=os.environ.get("PAPER_BACKTEST_REQUIRE_TRADE_ALLOWED", "1") != "0",
        require_ai_allowed=os.environ.get("PAPER_BACKTEST_REQUIRE_AI_ALLOWED", "1") != "0",
        infer_side_when_missing=os.environ.get("PAPER_BACKTEST_INFER_SIDE", "0") != "0",
        infer_normal_side=str(os.environ.get("PAPER_BACKTEST_INFER_NORMAL_SIDE", "") or "").strip().upper(),
    )
    print(
        "[PAPER] cfg=",
        {
            "days": cfg.days,
            "limit": cfg.limit,
            "horizon_minutes": cfg.horizon_minutes,
            "require_trade_allowed": cfg.require_trade_allowed,
            "require_ai_allowed": cfg.require_ai_allowed,
            "infer_side_when_missing": cfg.infer_side_when_missing,
            "infer_normal_side": cfg.infer_normal_side,
        },
    )
    supabase = init_supabase()

    rows = fetch_rows(supabase, cfg)
    print(f"[PAPER] rows fetched: {len(rows)}")
    future_idx = build_future_index(rows)
    print(f"[PAPER] future_index_symbols={len(future_idx)}")
    if rows:
        non_empty = {
            "technical_signal": 0,
            "market_regime": 0,
            "market_phase": 0,
            "kill_zone_signal": 0,
        }
        for rr in rows:
            if str(rr.get("technical_signal") or "").strip():
                non_empty["technical_signal"] += 1
            if str(rr.get("market_regime") or "").strip():
                non_empty["market_regime"] += 1
            if str(rr.get("market_phase") or "").strip():
                non_empty["market_phase"] += 1
            if str(rr.get("kill_zone_signal") or "").strip():
                non_empty["kill_zone_signal"] += 1
        print(f"[PAPER] non_empty_counts={non_empty}")
        print(
            "[PAPER] sample_row=",
            {
                "symbol": rows[0].get("symbol"),
                "technical_signal": rows[0].get("technical_signal"),
                "market_regime": rows[0].get("market_regime"),
                "market_phase": rows[0].get("market_phase"),
                "kill_zone_signal": rows[0].get("kill_zone_signal"),
                "is_trade_allowed": rows[0].get("is_trade_allowed"),
                "ai_allowed": rows[0].get("ai_allowed"),
                "price": rows[0].get("price"),
                "created_at": rows[0].get("created_at"),
            },
        )

    inserted = 0
    skipped = 0
    skip_reason: dict[str, int] = {
        "signal_not_long_short": 0,
        "signal_missing_inferred": 0,
        "signal_missing_not_inferred": 0,
        "is_trade_allowed_false": 0,
        "ai_allowed_false": 0,
        "bad_price": 0,
        "no_future_price": 0,
    }

    for r in rows:
        processed += 1
        raw_signal = r.get("technical_signal")
        side = normalize_signal(raw_signal)
        if side not in cfg.allowed_signal:
            # 如果信号缺失，允许用 V4 语义推断一把（用于短数据期快速产样本）
            if side == "" and cfg.infer_side_when_missing:
                inferred = infer_side_from_v4(cfg, r)
                if inferred in cfg.allowed_signal:
                    side = inferred
                    skip_reason["signal_missing_inferred"] += 1
                else:
                    skipped += 1
                    skip_reason["signal_missing_not_inferred"] += 1
                    continue
            else:
                skipped += 1
                skip_reason["signal_not_long_short"] += 1
                continue

        # 覆盖回 row，保证写入 paper_trades 里的 side 与推断一致
        r = dict(r)
        r["technical_signal"] = side
        if cfg.require_trade_allowed and (r.get("is_trade_allowed") is not True):
            skipped += 1
            skip_reason["is_trade_allowed_false"] += 1
            continue
        if cfg.require_ai_allowed and (r.get("ai_allowed") is not True):
            skipped += 1
            skip_reason["ai_allowed_false"] += 1
            continue
        price = _safe_float(r.get("price"))
        if price is None or price <= 0:
            skipped += 1
            skip_reason["bad_price"] += 1
            continue

        # 优先本地索引查未来价格（快），找不到再走远程（可选，默认不走）
        fp = fetch_future_price_local(future_idx, r["symbol"], r["created_at"], cfg.horizon_minutes)
        if fp is None and os.environ.get("PAPER_BACKTEST_FUTURE_FALLBACK_REMOTE", "0") == "1":
            fp = fetch_future_price(supabase, r["symbol"], r["created_at"], cfg.horizon_minutes)
        if fp is None or fp <= 0:
            skipped += 1
            skip_reason["no_future_price"] += 1
            continue

        trade_row = build_trade_row(cfg, r, fp)
        # 幂等：unique(symbol, source_row_id)
        supabase.table("paper_trades").upsert(trade_row, on_conflict="symbol,source_row_id").execute()
        inserted += 1

        if inserted % 200 == 0:
            print(f"[PAPER] progress processed={processed} inserted={inserted} skipped={skipped}")
        elif processed % 500 == 0:
            print(f"[PAPER] progress processed={processed} inserted={inserted} skipped={skipped}")

    print(f"[PAPER] done. inserted={inserted} skipped={skipped}")
    print(f"[PAPER] skip_breakdown={skip_reason}")


if __name__ == "__main__":
    main()


