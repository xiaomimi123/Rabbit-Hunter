"""V5 Collector 主入口。

四任务管道:Scanner → DeepCollector → V5Scorer → Writer
+ V5PositionMonitor 30s 轮询活仓
+ MemoryAutoUploader 周期上传 AI 学习

替换 V4.3 monolithic collector,使用 v5_* 模块组合。
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

# Ensure project root + scripts/ are on sys.path
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_SCRIPTS = Path(__file__).parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_ROOT / ".env")
except Exception:
    pass


def _resolve_mode_db() -> str:
    """从 system_settings 读 system_state,SHADOW 默认。"""
    import sqlite3
    db = os.environ.get("DB_PATH", "data/rabbit_hunter.db")
    try:
        conn = sqlite3.connect(db)
        try:
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key='system_state'"
            ).fetchone()
            if row and (row[0] or "").upper() in ("SHADOW", "LIVE"):
                return row[0].upper()
        finally:
            conn.close()
    except Exception:
        pass
    return "SHADOW"


def _get_live_trader():
    """获取 active exchange 的 trader 实例(用于 LIVE balance + V5PositionManager)。

    返回 None 表示拉取失败/没配置,调用方应回退到 SHADOW 路径。
    """
    try:
        from scripts.exchange_factory import get_trader
        return get_trader()
    except Exception as e:
        print(f"[collector_main] get_trader 失败: {e}")
        return None


def _fetch_balance() -> float:
    """先尝试从交易所拉余额,失败回退 env PAPER_INITIAL_BALANCE_USDT。"""
    try:
        trader = _get_live_trader()
        if trader is not None:
            bal = trader.fetch_balance()
            # ccxt 风格 / 自定义 trader 风格兼容
            usdt = None
            if isinstance(bal, dict):
                if "USDT" in bal and isinstance(bal["USDT"], dict):
                    usdt = bal["USDT"].get("free") or bal["USDT"].get("available")
                elif "free" in bal:
                    usdt = bal["free"]
                elif "available" in bal:
                    usdt = bal["available"]
            if usdt is not None and float(usdt) > 0:
                return float(usdt)
    except Exception as e:
        print(f"[collector_main] 余额拉取失败,用 PAPER_INITIAL_BALANCE_USDT: {e}")
    return float(os.environ.get("PAPER_INITIAL_BALANCE_USDT", "1000"))


async def _build_indicator_fetcher():
    """给 V5PositionMonitor 用的 indicator fetcher。

    返回 async fn(symbol) -> {price, rsi_15m, macd_hist_15m, macd_hist_prev_15m}。
    """
    from scripts.tasks.exchange_endpoints import fetch_klines  # type: ignore[import-not-found]
    from v5_indicator_engine import calculate_rsi, calculate_macd

    async def fetch(symbol: str) -> dict:
        klines = await asyncio.to_thread(fetch_klines, symbol, "15m", 50)
        price = float(klines[-1][4])
        rsi = calculate_rsi(klines)
        _, _, hist, hist_prev = calculate_macd(klines)
        return {
            "price": price,
            "rsi_15m": rsi,
            "macd_hist_15m": hist,
            "macd_hist_prev_15m": hist_prev,
        }
    return fetch


async def _init_ai():
    """初始化 TradingAssistant — 失败返回 None,SHADOW 仍能跑(scorer 处理 None)。"""
    try:
        from scripts.ai.trading_assistant import TradingAssistant
        ai = TradingAssistant()
        if hasattr(ai, "initialize"):
            try:
                await ai.initialize()
            except Exception as e:
                print(f"[collector_main] TradingAssistant.initialize() 失败: {e}")
        return ai
    except Exception as e:
        print(f"[collector_main] TradingAssistant 初始化失败: {e}")
        return None


async def main() -> None:
    from scripts.config import get_config
    from scripts.local_db import get_local_db
    from scripts.tasks.scanner import MarketScanner
    from scripts.tasks.deep_collector import DeepCollector
    from scripts.tasks.scorer import V5Scorer
    from scripts.tasks.writer import DatabaseWriter
    from scripts.paper_position_manager import PaperPositionManager
    from scripts.v5_position_monitor import V5PositionMonitor

    cfg = get_config()
    db_path = os.environ.get("DB_PATH", "data/rabbit_hunter.db")

    # 初始化本地 SQLite(创建表 + 迁移)
    _ = get_local_db()
    print("[collector_main] 本地 SQLite 数据库已就绪")

    ai = await _init_ai()

    paper_pm = PaperPositionManager(db_path=db_path)
    live_pm = None
    if cfg.enable_auto_trading:
        try:
            from scripts.v5_position_manager import V5PositionManager
            trader = _get_live_trader()
            if trader is not None:
                live_pm = V5PositionManager(broker=trader, db_path=db_path)
            else:
                print("[collector_main] V5PositionManager 跳过:get_trader 返回 None")
        except Exception as e:
            print(f"[collector_main] V5PositionManager 初始化失败: {e}")

    movers_queue: asyncio.Queue = asyncio.Queue(maxsize=2)
    enriched_queue: asyncio.Queue = asyncio.Queue(maxsize=50)

    writer = DatabaseWriter(
        queue_maxsize=cfg.write_queue_maxsize,
        num_workers=cfg.write_workers,
    )

    scanner = MarketScanner(
        movers_queue=movers_queue,
        scan_interval=cfg.scan_interval,
        top_movers_count=cfg.store_top_count,
        min_volume_24h=cfg.min_volume_24h_usdt,
        supabase=None,
    )
    deep_collector = DeepCollector(
        movers_queue=movers_queue,
        enriched_queue=enriched_queue,
        deep_scan_interval=cfg.deep_scan_interval_seconds,
    )
    scorer = V5Scorer(
        enriched_queue=enriched_queue,
        ai=ai,
        paper_pm=paper_pm,
        live_pm=live_pm,
        mode_resolver=_resolve_mode_db,
        balance_fetcher=_fetch_balance,
        db_path=db_path,
    )

    indicator_fetcher = await _build_indicator_fetcher()
    monitor = V5PositionMonitor(
        paper_pm=paper_pm,
        live_pm=live_pm,
        ai_assistant=ai,
        indicator_fetcher=indicator_fetcher,
        mode_resolver=_resolve_mode_db,
        poll_interval_s=int(os.environ.get("V5_MONITOR_INTERVAL_S", "30")),
    )

    # v0.5.6: Vector Store 自动上传 — 周期把 trade_log 推到 OpenAI(可选)
    memory_uploader = None
    try:
        from scripts.ai.memory_uploader import MemoryAutoUploader
        memory_uploader = MemoryAutoUploader()
    except Exception as e:
        print(f"[collector_main] MemoryAutoUploader 初始化失败,本次启动不跑自动上传: {e}")

    mode = _resolve_mode_db()
    print(f"[collector_main] V5 启动 — mode={mode} db={db_path} "
          f"auto_trading={'ON' if cfg.enable_auto_trading else 'OFF'} "
          f"ai={'ON' if ai else 'OFF'}")

    # writer 用旧风格:start() 启动 worker,scorer 把 trade_score 直接写 DB,
    # 这里保留 writer.run() 占位以兼容其他任务/未来扩展。
    writer.start()
    print("[collector_main] DatabaseWriter 已启动")

    coroutines = [
        scanner.run(),
        deep_collector.run(),
        scorer.run(),
        monitor.run(),
    ]
    if memory_uploader is not None:
        coroutines.append(memory_uploader.run())

    try:
        await asyncio.gather(*coroutines, return_exceptions=False)
    except asyncio.CancelledError:
        print("[collector_main] 收到取消信号")
    finally:
        try:
            await writer.stop()
        except Exception:
            pass
        print("[collector_main] V5 Collector 已停止")


def _setup_shutdown() -> None:
    """注册 SIGTERM/SIGINT — Docker stop 时优雅退出。"""
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: loop.stop())
        except (NotImplementedError, RuntimeError):
            # Windows / 已注册 — 忽略
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[collector_main] 用户中断,退出")
