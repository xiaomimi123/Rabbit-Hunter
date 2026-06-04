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

    Call this from v43_position_manager.close_position() after the trade closes.
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
) -> None:
    """Compile recent trades into a readable file and upload to Vector Store.

    The Assistant will be able to retrieve this file during future decisions.
    Old uploads are replaced so the vector store doesn't grow unboundedly.
    """
    vs_id = vector_store_id or os.getenv("OPENAI_VECTOR_STORE_ID")
    if not vs_id:
        print("[Memory] OPENAI_VECTOR_STORE_ID not set, skipping upload")
        return

    if not TRADE_LOG_PATH.exists():
        print("[Memory] No trade log found at", TRADE_LOG_PATH)
        return

    raw_lines = TRADE_LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    raw_lines = [l for l in raw_lines if l.strip()]
    recent = raw_lines[-last_n:]
    trades = []
    for line in recent:
        try:
            trades.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not trades:
        print("[Memory] No valid trades to upload")
        return

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


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Rabbit Hunter AI Memory Uploader")
    parser.add_argument("--upload", action="store_true", help="Upload trade history to Vector Store")
    parser.add_argument("--last-n", type=int, default=MAX_TRADES_IN_UPLOAD)
    args = parser.parse_args()

    if args.upload:
        await upload_trade_history(last_n=args.last_n)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(_main())
