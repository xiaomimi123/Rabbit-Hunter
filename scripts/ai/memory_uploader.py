"""Trade memory management for Rabbit Hunter AI.

Two responsibilities:
1. log_trade_result()   — called after each trade closes, appends to local JSONL
2. upload_trade_history() — called periodically (daily/weekly) to push latest
                            trades into the OpenAI Vector Store so the Assistant
                            can retrieve them as few-shot examples.

Usage (periodic cron or manual):
    python -m scripts.ai.memory_uploader --upload
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import openai

TRADE_LOG_PATH = Path(os.getenv("AI_TRADE_LOG_PATH", "data/ai_trade_log.jsonl"))
MAX_TRADES_IN_UPLOAD = int(os.getenv("AI_MEMORY_MAX_TRADES", "300"))


# ---------------------------------------------------------------------------
# Log a completed trade (call this from position manager on close)
# ---------------------------------------------------------------------------


def log_trade_result(
    *,
    symbol: str,
    side: str,
    entry_price: float,
    exit_price: float,
    pnl_usdt: float,
    pnl_pct: float,
    exit_reason: str,
    features: dict,
    ai_decision: Optional[dict] = None,
) -> None:
    """Append one completed trade to the local JSONL log.

    Call this from V5 PositionMonitor / PaperPositionManager close_position()
    after the trade closes.
    """
    TRADE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "side": side,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "pnl_usdt": round(pnl_usdt, 4),
        "pnl_pct": round(pnl_pct * 100, 4),
        "outcome": "WIN" if pnl_usdt > 0 else "LOSS",
        "exit_reason": exit_reason,
        "ai": ai_decision or {},
        "features": {
            k: features.get(k)
            for k in [
                "phase",
                "market_phase",
                "funding_rate",
                "oi_change_1h",
                "price_change_1h",
                "long_short_ratio",
                "kill_zone_signal",
                "structure_score",
                "volatility_score",
                "sentiment_score",
                "manipulation_score",
                "atr",
                "atr_1h",
            ]
            if features.get(k) is not None
        },
    }

    with open(TRADE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Upload to OpenAI Vector Store
# ---------------------------------------------------------------------------


async def upload_trade_history(
    vector_store_id: Optional[str] = None,
    last_n: int = MAX_TRADES_IN_UPLOAD,
    min_age_hours: float = 0.0,
) -> dict:
    """Compile recent trades into a readable file and upload to Vector Store.

    The Assistant will be able to retrieve this file during future decisions.
    Old uploads are replaced so the vector store doesn't grow unboundedly.

    v0.5.6: 新增 min_age_hours — 只上传交易时间 ≥ N 小时前的记录。
    防止 lookahead leak: 刚平的虚拟/真实交易立刻进 Vector Store →
    下次 decide() 命中自己刚做的决定 → 模型自我验证。
    默认 0（向后兼容手动 CLI）。后台自动任务建议 24h。

    Returns: {"uploaded": int, "skipped_too_recent": int, "win_rate": float} 或
             {"skipped": "reason"} 当啥也没上传时。
    """
    vs_id = vector_store_id or os.getenv("OPENAI_VECTOR_STORE_ID")
    if not vs_id:
        print("[Memory] OPENAI_VECTOR_STORE_ID not set, skipping upload")
        return {"skipped": "no_vector_store_id"}

    if not TRADE_LOG_PATH.exists():
        print("[Memory] No trade log found at", TRADE_LOG_PATH)
        return {"skipped": "no_log_file"}

    raw_lines = TRADE_LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    raw_lines = [l for l in raw_lines if l.strip()]
    recent = raw_lines[-last_n:]
    trades = []
    for line in recent:
        try:
            trades.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    # v0.5.6: 冷却窗口 — 过滤掉太新的记录
    skipped_recent = 0
    if min_age_hours > 0:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
        filtered = []
        for t in trades:
            ts_str = t.get("timestamp") or ""
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts <= cutoff:
                    filtered.append(t)
                else:
                    skipped_recent += 1
            except Exception:
                # 解析不出来的时间戳保守跳过（避免 leak）
                skipped_recent += 1
        trades = filtered
        if skipped_recent:
            print(f"[Memory] 冷却窗口 {min_age_hours}h: 跳过 {skipped_recent} 笔太新的交易（防 lookahead leak）")

    if not trades:
        print("[Memory] No valid trades to upload (after cooldown filter)")
        return {"skipped": "no_trades_after_filter", "skipped_too_recent": skipped_recent}

    wins = [t for t in trades if t.get("outcome") == "WIN"]
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0

    # Build human-readable text for the vector store
    lines = [
        "# Rabbit Hunter Trade History",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Total trades: {len(trades)} | Win rate: {win_rate:.1f}% | Wins: {len(wins)} | Losses: {len(trades)-len(wins)}",
        "",
    ]

    for t in trades:
        ai = t.get("ai", {})
        feat = t.get("features", {})
        lines.append("---")
        lines.append(
            f"Symbol: {t['symbol']} | {t['side']} | {t.get('timestamp', '')[:10]} | {t.get('outcome', '?')}"
        )
        lines.append(
            f"Entry: {t['entry_price']} → Exit: {t['exit_price']} | "
            f"PnL: {t['pnl_usdt']:+.2f} USDT ({t['pnl_pct']:+.3f}%)"
        )
        lines.append(
            f"Phase: {feat.get('phase') or feat.get('market_phase', '?')} | "
            f"OI: {feat.get('oi_change_1h', 0):+.2f}% | "
            f"Price: {feat.get('price_change_1h', 0):+.2f}% | "
            f"Funding: {float(feat.get('funding_rate', 0))*100:+.4f}%"
        )
        lines.append(
            f"Scores — structure: {float(feat.get('structure_score', 0))*100:.0f} "
            f"sentiment: {float(feat.get('sentiment_score', 0))*100:.0f} "
            f"volatility: {float(feat.get('volatility_score', 0))*100:.0f}"
        )
        lines.append(f"Exit reason: {t.get('exit_reason', '?')}")
        if ai:
            lines.append(
                f"AI: SL={ai.get('sl_multiplier', '?')}x ATR | "
                f"TP={ai.get('tp_multiplier', '?')}x ATR | "
                f"size={ai.get('size_multiplier', '?')}x | "
                f"conf={ai.get('confidence', '?')} | {ai.get('reasoning', '')}"
            )
        lines.append("")

    content_bytes = "\n".join(lines).encode("utf-8")
    filename = f"trade_history_{datetime.now(timezone.utc).strftime('%Y%m%d')}.txt"

    client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Delete existing trade history files to avoid duplication
    existing = await client.beta.vector_stores.files.list(vector_store_id=vs_id)
    for vf in existing.data:
        try:
            await client.beta.vector_stores.files.delete(
                vector_store_id=vs_id, file_id=vf.id
            )
            await client.files.delete(vf.id)
        except Exception as e:
            print(f"[Memory] Warning: could not delete old file {vf.id}: {e}")

    # Upload new file
    file_obj = await client.files.create(
        file=(filename, content_bytes, "text/plain"),
        purpose="assistants",
    )
    await client.beta.vector_stores.files.create(
        vector_store_id=vs_id,
        file_id=file_obj.id,
    )

    print(
        f"[Memory] Uploaded {len(trades)} trades to Vector Store {vs_id} | "
        f"win rate {win_rate:.1f}% | file={filename}"
    )
    return {
        "uploaded":           len(trades),
        "skipped_too_recent": skipped_recent,
        "win_rate":           round(win_rate, 2),
        "file":               filename,
    }


# ---------------------------------------------------------------------------
# 自动后台任务（v0.5.6）— 进 collector_main 跑
# ---------------------------------------------------------------------------


class MemoryAutoUploader:
    """异步任务：周期性把 trade_log.jsonl 推到 Vector Store。

    冷却窗口：默认 24h — 只上传 entry_time ≥ 24h 前的交易。
    用 entry_time 而不是 exit_time，避免一个长持仓 close 后立刻被自己引用。

    所有参数走 env，可以热改但需重启容器（轮询循环里读固定字段）。

    Env:
      VECTOR_STORE_UPLOAD_INTERVAL_HOURS  默认 6   两次上传间隔
      VECTOR_STORE_UPLOAD_LAG_HOURS       默认 24  冷却窗口，防 lookahead leak
      VECTOR_STORE_UPLOAD_LAST_N          默认 300 单次最多上传几笔
    """

    def __init__(self):
        self.interval_h = float(os.environ.get("VECTOR_STORE_UPLOAD_INTERVAL_HOURS", "6"))
        self.lag_h     = float(os.environ.get("VECTOR_STORE_UPLOAD_LAG_HOURS", "24"))
        self.last_n    = int(os.environ.get("VECTOR_STORE_UPLOAD_LAST_N", "300"))
        self._stop = False

    async def run(self):
        # 启动时先睡一段（不抢启动期 CPU）；后续按 interval
        startup_delay = 60  # 60s 后第一次跑
        print(
            f"[MemoryAutoUploader] 启动 — interval={self.interval_h}h lag={self.lag_h}h "
            f"last_n={self.last_n} (启动后 {startup_delay}s 第一次上传)"
        )
        await asyncio.sleep(startup_delay)

        while not self._stop:
            try:
                await self._tick()
            except asyncio.CancelledError:
                return
            except Exception as e:
                print(f"[MemoryAutoUploader] tick 出错: {type(e).__name__}: {e}")
            try:
                await asyncio.sleep(self.interval_h * 3600)
            except asyncio.CancelledError:
                return

    async def _tick(self):
        """单次上传：先检查 OpenAI provider + vector_store_id，再上传。"""
        # 检查 OpenAI 已启用（DB 或 env）
        try:
            try:
                from ai_config_manager import resolve_active_ai  # type: ignore[import-not-found]
            except ImportError:
                from scripts.ai_config_manager import resolve_active_ai  # type: ignore[import-not-found]
            cfg = resolve_active_ai(expected_provider="openai")
            openai_enabled = bool(cfg.get("enabled") and cfg.get("api_key"))
        except Exception:
            openai_enabled = bool(os.environ.get("OPENAI_API_KEY"))

        if not openai_enabled:
            print("[MemoryAutoUploader] OpenAI 未启用，跳过本轮上传")
            return

        if not os.environ.get("OPENAI_VECTOR_STORE_ID"):
            print("[MemoryAutoUploader] OPENAI_VECTOR_STORE_ID 未设，跳过本轮上传")
            return

        result = await upload_trade_history(
            last_n=self.last_n,
            min_age_hours=self.lag_h,
        )
        if result.get("uploaded"):
            print(
                f"[MemoryAutoUploader] 完成: 上传 {result['uploaded']} 笔 | "
                f"跳过 {result.get('skipped_too_recent', 0)} 笔太新 | "
                f"胜率 {result.get('win_rate', 0):.1f}%"
            )

    def stop(self):
        self._stop = True


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Rabbit Hunter AI Memory Uploader")
    parser.add_argument("--upload", action="store_true", help="Upload trade history to Vector Store")
    parser.add_argument("--last-n", type=int, default=MAX_TRADES_IN_UPLOAD)
    parser.add_argument("--min-age-hours", type=float, default=0.0,
                        help="Only upload trades older than this many hours (防 lookahead leak)")
    args = parser.parse_args()

    if args.upload:
        await upload_trade_history(last_n=args.last_n, min_age_hours=args.min_age_hours)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(_main())
