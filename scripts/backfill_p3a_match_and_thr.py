"""
回填历史字段：p3a_match_score / ai_effective_threshold（Rabbit Hunter 4.0）

用途：
- 让历史 ai_training_data 也具备可回测/可筛选字段（p3a_match_score、ai_effective_threshold）
- 不依赖当前 collector 是否在跑

策略（MVP）：
1) 启动时构建 P3a 成功样本 profile（同 p3a_pattern_matcher 的 fit 思路）
2) 分批拉取 ai_training_data 中 p3a_match_score 或 ai_effective_threshold 为空的行
3) 计算并 update 回写

说明：
- p3a_match_score：使用 profile 相似度；若 profile 不可用则默认 0.5
- ai_effective_threshold：按当前规则重算（基于 confidence_level + p3a_match_score）

用法：
  py -3 scripts/backfill_p3a_match_and_thr.py

环境：
  .env 需要 SUPABASE_URL / SUPABASE_KEY
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from supabase import Client, create_client

from p3a_pattern_matcher import P3APatternMatcher, PatternConfig


@dataclass(frozen=True)
class BackfillConfig:
    days_for_profile: int = 14
    min_success_samples: int = 50
    batch_size: int = 200
    max_batches: int = 200  # 防止无限跑；需要更大就改
    base_threshold: float = 0.65
    max_boost: float = 0.20
    match_bonus_thr_cut: float = 0.05
    match_bonus_gate: float = 0.75


def init_supabase() -> Client:
    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(dotenv_path=base_dir / ".env")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("缺少 SUPABASE_URL / SUPABASE_KEY")
    return create_client(url, key)


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:  # noqa: BLE001
        return default


def compute_effective_threshold(cfg: BackfillConfig, confidence_level: Any, p3a_match_score: float) -> float:
    cl = _safe_float(confidence_level, 0.0)
    dyn_thr = cfg.base_threshold + (cl / 100.0) * cfg.max_boost
    dyn_thr = max(0.05, min(0.95, dyn_thr))
    eff_thr = dyn_thr
    if p3a_match_score >= cfg.match_bonus_gate:
        eff_thr = max(0.05, dyn_thr - cfg.match_bonus_thr_cut)
    return float(eff_thr)


def fetch_need_backfill(supabase: Client, limit: int) -> List[Dict[str, Any]]:
    # 只取必须的字段，减少传输
    resp = (
        supabase.table("ai_training_data")
        .select(
            "id, symbol, funding_rate, long_short_ratio, oi_change_1h, price_change_1h, "
            "cvd_15m, cvd_1h, exit_clarity_score, confidence_level, price_breakout, market_phase"
        )
        .or_("p3a_match_score.is.null,ai_effective_threshold.is.null")
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return list(resp.data or [])


def main() -> None:
    cfg = BackfillConfig(
        days_for_profile=int(os.environ.get("P3A_MATCH_DAYS", "14")),
        min_success_samples=int(os.environ.get("P3A_MATCH_MIN_SAMPLES", "50")),
        batch_size=int(os.environ.get("BACKFILL_BATCH_SIZE", "200")),
        max_batches=int(os.environ.get("BACKFILL_MAX_BATCHES", "200")),
        base_threshold=float(os.environ.get("AI_JUDGE_THRESHOLD", "0.65")),
        max_boost=float(os.environ.get("AI_DYNAMIC_THRESHOLD_MAX_BOOST", "0.20")),
    )

    supabase = init_supabase()

    matcher = P3APatternMatcher(
        supabase,
        PatternConfig(days=cfg.days_for_profile, min_success_samples=cfg.min_success_samples),
    )
    prof = matcher.fit()
    if prof is None or not matcher.is_ready():
        print("[BACKFILL] P3a profile 不可用/样本不足：p3a_match_score 将使用默认 0.5")
        matcher = None  # type: ignore[assignment]
    else:
        print(f"[BACKFILL] P3a profile ready: success_samples={prof.n} days={cfg.days_for_profile}")

    updated = 0
    for bi in range(cfg.max_batches):
        rows = fetch_need_backfill(supabase, cfg.batch_size)
        if not rows:
            print("[BACKFILL] done (no more rows).")
            break

        patch_rows: List[Dict[str, Any]] = []
        for r in rows:
            p3a = 0.5
            if matcher is not None:
                try:
                    p3a = float(matcher.score(r))
                except Exception:
                    p3a = 0.5

            eff_thr = compute_effective_threshold(cfg, r.get("confidence_level"), p3a)

            patch_rows.append(
                {
                    "id": r["id"],
                    # supabase upsert 需要带上非空字段，否则会因 NOT NULL 约束失败
                    "symbol": r.get("symbol"),
                    "p3a_match_score": p3a,
                    "ai_effective_threshold": eff_thr,
                }
            )

        # upsert by id（只更新两列）
        supabase.table("ai_training_data").upsert(patch_rows, on_conflict="id").execute()
        updated += len(patch_rows)
        print(f"[BACKFILL] batch {bi+1}: updated {len(patch_rows)} (total {updated})")

    print(f"[BACKFILL] finished. total_updated={updated}")


if __name__ == "__main__":
    main()


