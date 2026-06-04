"""
离线训练：AI Judge（Rabbit Hunter 4.0）

目标：
- 训练一个“继续参与概率”模型（不预测方向）。
- 输出：ai_score (0-1) / ai_allowed (bool)

标签构造（最小版本）：
- 对每条样本，找同一 symbol 在未来 horizon_minutes 附近的 price（>= 未来时间点的第一条）
- label = 1 当 future_return >= target_return（默认 0.5%）

用法：
  py -3 scripts/train_ai_judge.py
环境：
  需要 .env 中 SUPABASE_URL / SUPABASE_KEY
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from dotenv import load_dotenv
from supabase import create_client, Client

from ai_judge_model import DEFAULT_AI_VERSION, build_feature_vector


@dataclass(frozen=True)
class TrainConfig:
    days: int = 7
    horizon_minutes: int = 30
    target_return: float = 0.005  # 0.5%
    min_rows: int = 200
    allowed_threshold: float = 0.65
    model_path: str = "models/ai_judge_lr_v1.npz"


def init_supabase() -> Client:
    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(dotenv_path=base_dir / ".env")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("缺少 SUPABASE_URL / SUPABASE_KEY")
    return create_client(url, key)


def fetch_training_rows(supabase: Client, cfg: TrainConfig) -> List[Dict[str, Any]]:
    """
    拉取近 N 天的训练数据（原始特征），用于构造标签与训练。
    注意：这里不分页的话可能数据量较大；先用 limit 控制。
    """
    from datetime import datetime, timedelta, timezone

    start_time = (datetime.now(timezone.utc) - timedelta(days=cfg.days)).isoformat()
    resp = (
        supabase.table("ai_training_data")
        .select(
            "created_at, symbol, price, funding_rate, long_short_ratio, oi_change_1h, price_change_1h,"
            "cvd_15m, cvd_1h, cvd_value, market_phase, kill_zone_signal, exit_clarity_score, confidence_level, price_breakout"
        )
        .gte("created_at", start_time)
        .order("created_at", desc=False)
        .limit(5000)
        .execute()
    )
    return list(resp.data or [])


def fetch_future_price(
    supabase: Client, symbol: str, t0_iso: str, horizon_minutes: int
) -> float | None:
    """
    找未来时间点附近的第一条记录价格。
    """
    from datetime import datetime, timedelta, timezone

    t0 = datetime.fromisoformat(t0_iso.replace("Z", "+00:00"))
    t_future = (t0 + timedelta(minutes=horizon_minutes)).isoformat()

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


def build_dataset(
    supabase: Client, rows: List[Dict[str, Any]], cfg: TrainConfig
) -> Tuple[np.ndarray, np.ndarray]:
    X: List[List[float]] = []
    y: List[int] = []

    for r in rows:
        price = r.get("price")
        if price is None:
            continue
        p0 = float(price)
        if p0 <= 0:
            continue

        future_price = fetch_future_price(supabase, r["symbol"], r["created_at"], cfg.horizon_minutes)
        if future_price is None or future_price <= 0:
            continue

        ret = (future_price - p0) / p0
        label = 1 if ret >= cfg.target_return else 0

        X.append(build_feature_vector(r))
        y.append(label)

    if not X:
        return np.zeros((0, 1)), np.zeros((0,))
    return np.array(X, dtype=np.float64), np.array(y, dtype=np.int64)


def train_logistic_regression(X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
    """
    用 sklearn 训练一个可控的 LR。保存权重/偏置到 npz，推理不依赖 sklearn。
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    clf = LogisticRegression(max_iter=500, n_jobs=None)
    clf.fit(X, y)

    proba = clf.predict_proba(X)[:, 1]
    try:
        auc = float(roc_auc_score(y, proba))
    except Exception:
        auc = 0.0

    return {
        "w": clf.coef_.reshape(-1).astype(np.float64),
        "b": float(clf.intercept_.reshape(-1)[0]),
        "auc": auc,
    }


def save_model_npz(model: Dict[str, Any], cfg: TrainConfig) -> None:
    path = Path(cfg.model_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        w=model["w"],
        b=np.array([model["b"]], dtype=np.float64),
        auc=np.array([model.get("auc", 0.0)], dtype=np.float64),
        version=np.array([DEFAULT_AI_VERSION]),
    )


def main() -> None:
    cfg = TrainConfig()
    supabase = init_supabase()

    rows = fetch_training_rows(supabase, cfg)
    print(f"[AI TRAIN] rows fetched: {len(rows)}")

    X, y = build_dataset(supabase, rows, cfg)
    print(f"[AI TRAIN] dataset: X={X.shape}, y={y.shape}, pos_rate={(y.mean() if y.size else 0):.3f}")

    if X.shape[0] < cfg.min_rows:
        print(f"[AI TRAIN] 数据不足（{X.shape[0]} < {cfg.min_rows}），先不训练。")
        return

    model = train_logistic_regression(X, y)
    print(f"[AI TRAIN] trained: auc={model.get('auc', 0.0):.3f}")

    save_model_npz(model, cfg)
    print(f"[AI TRAIN] model saved: {cfg.model_path} (version={DEFAULT_AI_VERSION})")


if __name__ == "__main__":
    main()


