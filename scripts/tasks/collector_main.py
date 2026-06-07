"""
collector_main.py - New async entry point for the Rabbit Hunter collector.

Replaces the monolithic scripts/collector.py with four independent tasks
coordinated via asyncio.Queue:

    MarketScanner  ──movers_queue──►  DeepCollector
                                            │
                                    enriched_queue
                                            │
                                            ▼
                                    StrategyScorer ──write_queue──► DatabaseWriter

Usage:
    python -m scripts.tasks.collector_main
    # or
    python scripts/tasks/collector_main.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path (needed when run as a script)
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_SCRIPTS = Path(__file__).parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from dotenv import load_dotenv

load_dotenv(dotenv_path=_ROOT / ".env")

from scripts.config import get_config
from scripts.local_db import get_local_db, prune_old_data
from scripts.tasks.scanner import MarketScanner
from scripts.tasks.deep_collector import DeepCollector
from scripts.tasks.scorer import StrategyScorer
from scripts.tasks.writer import DatabaseWriter


async def _init_openai_assistant():
    """Initialize TradingAssistant if OPENAI_API_KEY is set. Returns None if disabled."""
    if not os.getenv("OPENAI_API_KEY"):
        return None
    if os.getenv("OPENAI_AI_ENABLED", "false").lower() not in ("1", "true"):
        return None
    try:
        from scripts.ai.trading_assistant import TradingAssistant
        assistant = TradingAssistant()
        await assistant.initialize()
        return assistant
    except Exception as e:
        print(f"[WARNING] OpenAI Assistant 初始化失败，将跳过 AI 层: {e}")
        return None


async def main() -> None:
    cfg = get_config()

    # Validate required config
    issues = cfg.validate()
    if issues:
        for issue in issues:
            print(f"[WARNING] 配置问题: {issue}")

    # Initialize OpenAI Assistant (optional)
    openai_assistant = await _init_openai_assistant()
    ai_status = "ON" if openai_assistant else "OFF"

    print("[INFO] Rabbit Hunter Collector 启动中...")
    # v0.5.6: AI provider 状态走 DB > env，反映 SettingsPage 真实保存的配置
    try:
        try:
            from ai_config_manager import resolve_active_ai  # type: ignore[import-not-found]
        except ImportError:
            from scripts.ai_config_manager import resolve_active_ai  # type: ignore[import-not-found]
        _deepseek_cfg = resolve_active_ai(expected_provider="deepseek")
        _openai_cfg   = resolve_active_ai(expected_provider="openai")
        _deepseek_on  = bool(_deepseek_cfg.get("enabled") and _deepseek_cfg.get("api_key"))
        _openai_on    = bool(_openai_cfg.get("enabled") and _openai_cfg.get("api_key"))
    except Exception:
        _deepseek_on = cfg.deepseek_enabled
        _openai_on   = bool(openai_assistant)
    print(f"[INFO] V4.3={'ON' if cfg.v43_enabled else 'OFF'} | "
          f"V4.4={'ON' if cfg.v44_enabled else 'OFF'} | "
          f"AutoTrade={'ON' if cfg.enable_auto_trading else 'OFF'} | "
          f"DeepSeek={'ON' if _deepseek_on else 'OFF'} | "
          f"OpenAI={'ON' if _openai_on else 'OFF'}")

    # 初始化本地 SQLite 数据库
    db = get_local_db()
    print("[INFO] 本地 SQLite 数据库已就绪")

    # 启动时清理一次过期数据
    try:
        prune_old_data()
    except Exception as e:
        print(f"[WARNING] 数据清理失败: {e}")

    # ── Shared queues ──────────────────────────────────────────────────────────
    movers_queue: asyncio.Queue = asyncio.Queue(maxsize=2)
    enriched_queue: asyncio.Queue = asyncio.Queue(maxsize=50)

    # ── Task instances ──────────────────────────────────────────────────────────
    writer = DatabaseWriter(
        queue_maxsize=cfg.write_queue_maxsize,
        num_workers=cfg.write_workers,
    )
    write_queue = writer.queue

    scanner = MarketScanner(
        movers_queue=movers_queue,
        scan_interval=cfg.scan_interval,
        top_movers_count=cfg.store_top_count,
        supabase=db,
    )

    deep_collector = DeepCollector(
        movers_queue=movers_queue,
        enriched_queue=enriched_queue,
        deep_scan_interval=cfg.deep_scan_interval_seconds,
    )

    scorer = StrategyScorer(
        enriched_queue=enriched_queue,
        write_queue=write_queue,
        supabase=db,
        v43_enabled=cfg.v43_enabled,
        v44_enabled=cfg.v44_enabled,
        store_top_count=cfg.store_top_count,
        deepseek_cache_secs=60,
        openai_assistant=openai_assistant,
    )

    # v0.5.4: paper trading 监视器 — SHADOW 模式下虚拟仓位的实时 SL/TP 触发
    try:
        from tasks.paper_monitor import PaperMonitor  # type: ignore[import-not-found]
    except ImportError:
        from scripts.tasks.paper_monitor import PaperMonitor  # type: ignore[import-not-found]
    paper_monitor = PaperMonitor(
        supabase=db,
        interval_seconds=int(os.environ.get("PAPER_MONITOR_INTERVAL_SECONDS", "30")),
    )

    # v0.5.6: Vector Store 自动上传 — 周期把 trade_log 推到 OpenAI，带 24h 冷却窗口
    # 防 lookahead leak（刚平的单不会立刻进 vector store 影响下一笔决策）
    memory_uploader = None
    try:
        try:
            from ai.memory_uploader import MemoryAutoUploader  # type: ignore[import-not-found]
        except ImportError:
            from scripts.ai.memory_uploader import MemoryAutoUploader  # type: ignore[import-not-found]
        memory_uploader = MemoryAutoUploader()
    except Exception as e:
        print(f"[WARNING] MemoryAutoUploader 初始化失败，本次启动不跑自动上传: {e}")

    # ── Run all tasks ──────────────────────────────────────────────────────────
    writer.start()
    print("[INFO] DatabaseWriter 已启动")

    coroutines = [scanner.run(), deep_collector.run(), scorer.run(), paper_monitor.run()]
    if memory_uploader is not None:
        coroutines.append(memory_uploader.run())

    print("[INFO] 所有任务已启动，按 Ctrl+C 停止")
    try:
        await asyncio.gather(*coroutines)
    except asyncio.CancelledError:
        print("[INFO] Collector 收到取消信号")
    finally:
        await writer.stop()
        print("[INFO] Rabbit Hunter Collector 已停止")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断，退出")
