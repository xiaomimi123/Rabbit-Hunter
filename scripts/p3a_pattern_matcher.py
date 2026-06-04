"""
历史 P3a 模式匹配（Rabbit Hunter 4.0）

目标：
- 用历史“成功的 P3a（P3A_PUMP_START）”样本构建一个轻量 profile（均值/方差）。
- 运行时对当前样本打分 p3a_match_score (0-1)，用于 AI 裁决的先验输入与动态阈值调节。

说明：
- 这是 MVP：不做强化学习，只做“相似度打分”。
- 标签（success）采用与 train_ai_judge.py 相同的最小版本：未来 horizon_minutes 的收益 >= target_return。
- 为了降低查询成本：对 future_price 查询做简单缓存（按 symbol + t_future）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from supabase import Client


def _safe_float(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        return float(x)
    except Exception:  # noqa: BLE001
        return 0.0


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


@dataclass(frozen=True)
class PatternConfig:
    days: int = 14
    horizon_minutes: int = 30
    target_return: float = 0.005  # 0.5%
    max_rows: int = 5000
    min_success_samples: int = 50


@dataclass
class PatternProfile:
    # 选择和 V4 语义最相关且稳定产出的字段
    feature_keys: Tuple[str, ...]
    mean: List[float]
    std: List[float]
    n: int

    def score(self, row: Dict[str, Any]) -> float:
        """
        计算相似度分数（0-1，越高越像历史成功 P3a）。

        这里用标准化欧氏距离，并用 exp(-dist) 压到 0-1：
        - dist 越小（越接近）-> 分数越接近 1
        """
        if self.n <= 0:
            return 0.5
        xs = [_safe_float(row.get(k)) for k in self.feature_keys]
        z2 = 0.0
        for i, x in enumerate(xs):
            s = self.std[i] if self.std[i] > 1e-9 else 1.0
            z = (x - self.mean[i]) / s
            z2 += z * z
        dist = math.sqrt(z2)
        # dist=0 -> 1.0；dist≈3 -> ~0.05
        val = math.exp(-dist)
        return float(max(0.0, min(1.0, val)))


class P3APatternMatcher:
    """
    启动时：从 Supabase 构建成功 P3a 的统计画像（Profile）
    运行时：对当前样本打分
    """

    DEFAULT_FEATURE_KEYS: Tuple[str, ...] = (
        "funding_rate",
        "long_short_ratio",
        "oi_change_1h",
        "price_change_1h",
        "cvd_15m",
        "cvd_1h",
        "exit_clarity_score",
        "confidence_level",
        "price_breakout",
    )

    def __init__(self, supabase: Client, cfg: PatternConfig | None = None) -> None:
        self.supabase = supabase
        self.cfg = cfg or PatternConfig()
        self.profile: Optional[PatternProfile] = None
        self._future_cache: dict[tuple[str, str], float | None] = {}

    def is_ready(self) -> bool:
        return self.profile is not None and (self.profile.n >= self.cfg.min_success_samples)

    def score(self, row: Dict[str, Any]) -> float:
        if not self.profile:
            return 0.5
        # price_breakout 可能是 bool，转为 0/1
        if "price_breakout" in row:
            row = dict(row)
            row["price_breakout"] = 1.0 if bool(row.get("price_breakout")) else 0.0
        return self.profile.score(row)

    def fit(self) -> PatternProfile | None:
        rows = self._fetch_candidate_rows()
        if not rows:
            return None
        success_rows = self._filter_success_rows(rows)
        if len(success_rows) < self.cfg.min_success_samples:
            return None
        prof = self._build_profile(success_rows, self.DEFAULT_FEATURE_KEYS)
        self.profile = prof
        return prof

    # -----------------------------
    # internal
    # -----------------------------
    def _fetch_candidate_rows(self) -> List[Dict[str, Any]]:
        start_time = _iso(datetime.now(timezone.utc) - timedelta(days=self.cfg.days))
        resp = (
            self.supabase.table("ai_training_data")
            .select(
                "created_at, symbol, price,"
                "funding_rate, long_short_ratio, oi_change_1h, price_change_1h,"
                "cvd_15m, cvd_1h, exit_clarity_score, confidence_level, price_breakout,"
                "market_phase"
            )
            .eq("market_phase", "P3A_PUMP_START")
            .gte("created_at", start_time)
            .order("created_at", desc=False)
            .limit(self.cfg.max_rows)
            .execute()
        )
        return list(resp.data or [])

    def _future_price(self, symbol: str, t0_iso: str) -> float | None:
        t0 = _parse_iso(t0_iso)
        t_future = _iso(t0 + timedelta(minutes=self.cfg.horizon_minutes))
        key = (symbol, t_future)
        if key in self._future_cache:
            return self._future_cache[key]

        resp = (
            self.supabase.table("ai_training_data")
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
        self._future_cache[key] = price
        return price

    def _filter_success_rows(self, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in rows:
            p0 = r.get("price")
            if p0 is None:
                continue
            p0f = float(p0)
            if p0f <= 0:
                continue
            p1 = self._future_price(r["symbol"], r["created_at"])
            if p1 is None or p1 <= 0:
                continue
            ret = (p1 - p0f) / p0f
            if ret >= self.cfg.target_return:
                out.append(r)
        return out

    @staticmethod
    def _build_profile(rows: List[Dict[str, Any]], keys: Tuple[str, ...]) -> PatternProfile:
        # 计算均值/方差（std 做最小夹逼，避免除零）
        xs: List[List[float]] = []
        for r in rows:
            row_vals: List[float] = []
            for k in keys:
                if k == "price_breakout":
                    row_vals.append(1.0 if bool(r.get(k)) else 0.0)
                else:
                    row_vals.append(_safe_float(r.get(k)))
            xs.append(row_vals)

        n = len(xs)
        dim = len(keys)
        mean = [0.0] * dim
        for v in xs:
            for i in range(dim):
                mean[i] += v[i]
        mean = [m / n for m in mean]

        var = [0.0] * dim
        for v in xs:
            for i in range(dim):
                d = v[i] - mean[i]
                var[i] += d * d
        var = [vv / max(1, (n - 1)) for vv in var]
        std = [math.sqrt(vv) if vv > 1e-12 else 1.0 for vv in var]

        return PatternProfile(feature_keys=keys, mean=mean, std=std, n=n)


__all__ = ["PatternConfig", "PatternProfile", "P3APatternMatcher"]


