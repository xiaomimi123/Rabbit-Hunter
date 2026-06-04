"""
Reward 计算（Rabbit Hunter 4.0 / MVP）

目的：
- 为后续“强化学习 / 反事实裁决 / 动态阈值策略学习”准备可用的 reward 数据。
- 先不回写数据库（避免 schema 扩展），输出到 reports/rewards.csv 供分析。

Reward（最小版本）：
- 针对 ai_training_data 每条样本，计算未来 horizon_minutes 的收益率 r
- reward = clip(r / reward_scale, -1, +1)
- 同时输出 label（是否 >= target_return），方便做离线评估

用法：
  py -3 scripts/compute_rewards.py

环境：
  .env 需要 SUPABASE_URL / SUPABASE_KEY
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from supabase import Client, create_client


@dataclass(frozen=True)
class RewardConfig:
    days: int = 7
    horizon_minutes: int = 30
    target_return: float = 0.005
    reward_scale: float = 0.02  # 2% 对应 reward=1
    limit: int = 5000
    out_csv: str = "reports/rewards.csv"


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def init_supabase() -> Client:
    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(dotenv_path=base_dir / ".env")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("缺少 SUPABASE_URL / SUPABASE_KEY")
    return create_client(url, key)


def fetch_rows(supabase: Client, cfg: RewardConfig) -> List[Dict[str, Any]]:
    start_time = _iso(datetime.now(timezone.utc) - timedelta(days=cfg.days))
    resp = (
        supabase.table("ai_training_data")
        .select("created_at, symbol, price, market_phase, kill_zone_signal, exit_clarity_score, ai_version, ai_score, ai_allowed")
        .gte("created_at", start_time)
        .order("created_at", desc=False)
        .limit(cfg.limit)
        .execute()
    )
    return list(resp.data or [])


def fetch_future_price(
    supabase: Client, symbol: str, t0_iso: str, horizon_minutes: int, cache: dict[tuple[str, str], float | None]
) -> float | None:
    t0 = _parse_iso(t0_iso)
    t_future = _iso(t0 + timedelta(minutes=horizon_minutes))
    key = (symbol, t_future)
    if key in cache:
        return cache[key]
    resp = (
        supabase.table("ai_training_data")
        .select("price, created_at")
        .eq("symbol", symbol)
        .gte("created_at", t_future)
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    price = None
    if resp.data:
        p = resp.data[0].get("price")
        price = float(p) if p is not None else None
    cache[key] = price
    return price


def clip(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


def main() -> None:
    cfg = RewardConfig()
    supabase = init_supabase()
    rows = fetch_rows(supabase, cfg)
    print(f"[REWARD] rows fetched: {len(rows)}")

    out_path = Path(cfg.out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cache: dict[tuple[str, str], float | None] = {}
    written = 0
    pos = 0

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "created_at",
                "symbol",
                "price",
                "future_price",
                "ret",
                "label",
                "reward",
                "market_phase",
                "kill_zone_signal",
                "exit_clarity_score",
                "ai_version",
                "ai_score",
                "ai_allowed",
            ]
        )

        for r in rows:
            p0 = r.get("price")
            if p0 is None:
                continue
            p0f = float(p0)
            if p0f <= 0:
                continue
            p1 = fetch_future_price(supabase, r["symbol"], r["created_at"], cfg.horizon_minutes, cache)
            if p1 is None or p1 <= 0:
                continue
            ret = (p1 - p0f) / p0f
            label = 1 if ret >= cfg.target_return else 0
            reward = clip(ret / cfg.reward_scale, -1.0, 1.0)

            written += 1
            pos += label
            w.writerow(
                [
                    r.get("created_at"),
                    r.get("symbol"),
                    p0f,
                    p1,
                    round(ret, 6),
                    label,
                    round(reward, 6),
                    r.get("market_phase"),
                    r.get("kill_zone_signal"),
                    r.get("exit_clarity_score"),
                    r.get("ai_version"),
                    r.get("ai_score"),
                    r.get("ai_allowed"),
                ]
            )

    print(f"[REWARD] written={written} pos_rate={(pos / written if written else 0):.3f}")
    print(f"[REWARD] saved: {cfg.out_csv}")


if __name__ == "__main__":
    main()


