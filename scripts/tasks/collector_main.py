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
from typing import Optional

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


_PAPER_BALANCE = float(os.environ.get("PAPER_INITIAL_BALANCE_USDT", "1000"))


def _fetch_balance() -> Optional[float]:
    """SHADOW 模式直接返回 PAPER_INITIAL_BALANCE_USDT
    (避免每次 scoring 都打一堆 fetch_balance / load_markets 失败的日志)。
    LIVE 模式才真正去拉真实余额。LIVE 失败返 None (由 scorer 端写
    BALANCE_UNAVAILABLE block 记录,不伪造成 1000 USDT 假余额,防止风险
    计算被误导 —— F3)."""
    if _resolve_mode_db() != "LIVE":
        return _PAPER_BALANCE
    try:
        trader = _get_live_trader()
        if trader is not None:
            bal = trader.fetch_balance()
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
        print(f"[collector_main] LIVE 余额拉取失败,scorer 侧将写 BALANCE_UNAVAILABLE: {e}")
    return None


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


def preflight_check(*, enable_auto_trading: bool,
                    binance_api_key: str, okx_api_key: str,
                    openai_key: str, ai_enabled: bool,
                    deepseek_key: str = "", deepseek_enabled: bool = False) -> list:
    """返回问题列表(空 = OK)。

    AI 需求只要 OpenAI 或 DeepSeek 任一 provider 配齐就放行;两个都没配
    且 ai_enabled=True(OPENAI_AI_ENABLED 真值)→ 报错。如果用户两个都关
    (ai_enabled=False 且 deepseek_enabled=False)就允许启动跑纯规则引擎。
    """
    issues = []
    if enable_auto_trading and not binance_api_key and not okx_api_key:
        issues.append("ENABLE_AUTO_TRADING=true 但 broker API key 都未设置")

    deepseek_ready = deepseek_enabled and bool(deepseek_key)
    openai_ready = ai_enabled and bool(openai_key)
    if ai_enabled and not openai_ready and not deepseek_ready:
        issues.append(
            "OPENAI_AI_ENABLED=true 但既没 OPENAI_API_KEY,也没 "
            "DEEPSEEK_ENABLED=true + DEEPSEEK_API_KEY,AI 层无法工作"
        )
    return issues


async def _healthcheck_loop(db_path: str, interval_s: int = 60):
    """每分钟自检,有问题打 WARN/ERROR 日志。"""
    import sqlite3
    while True:
        await asyncio.sleep(interval_s)
        try:
            conn = sqlite3.connect(db_path)
            try:
                # 5min 无信号 → WARN
                n_recent = conn.execute(
                    "SELECT COUNT(*) FROM trade_scores_v5 "
                    "WHERE created_at >= datetime('now', '-5 minute')"
                ).fetchone()[0]
                if n_recent == 0:
                    print("[WARN][health] 过去 5 分钟无 trade_scores_v5 写入,评分流可能停滞")

                # 1h 无入场但 should_trade>=10 → AI 阈值过严
                n_rejected = conn.execute(
                    "SELECT COUNT(*) FROM trade_scores_v5 "
                    "WHERE created_at >= datetime('now', '-1 hour') "
                    "  AND should_trade=1 AND block_reason='AI_REJECTED'"
                ).fetchone()[0]
                n_executed = conn.execute(
                    "SELECT COUNT(*) FROM trade_scores_v5 "
                    "WHERE created_at >= datetime('now', '-1 hour') "
                    "  AND executed=1"
                ).fetchone()[0]
                if n_rejected >= 10 and n_executed == 0:
                    print(f"[WARN][health] 过去 1h AI 拒了 {n_rejected} 个但 0 入场,"
                          "AI 阈值可能过严")
            finally:
                conn.close()
        except Exception as e:
            print(f"[health] healthcheck 异常: {e}")


async def main() -> None:
    from scripts.config import get_config
    from scripts.local_db import get_local_db, init_local_db
    from scripts.tasks.scanner import MarketScanner
    from scripts.tasks.deep_collector import DeepCollector
    from scripts.tasks.scorer import V5Scorer
    from scripts.tasks.writer import DatabaseWriter
    from scripts.paper_position_manager import PaperPositionManager
    from scripts.v5_position_monitor import V5PositionMonitor

    cfg = get_config()

    issues = preflight_check(
        enable_auto_trading=cfg.enable_auto_trading,
        binance_api_key=os.environ.get("BINANCE_API_KEY", ""),
        okx_api_key=os.environ.get("OKX_API_KEY", ""),
        openai_key=os.environ.get("OPENAI_API_KEY", ""),
        ai_enabled=os.environ.get("OPENAI_AI_ENABLED", "false").lower() in ("1", "true"),
        deepseek_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        deepseek_enabled=os.environ.get("DEEPSEEK_ENABLED", "false").lower() in ("1", "true"),
    )
    if issues:
        for issue in issues:
            print(f"[FATAL] preflight: {issue}")
        sys.exit(1)

    db_path = os.environ.get("DB_PATH", "data/rabbit_hunter.db")

    # 初始化本地 SQLite(创建表 + 迁移)
    _ = get_local_db()
    # V5 schema 升级:DROP V43/V44 + CREATE V5 表 + ALTER paper_trades 加 V5 列
    init_local_db(db_path)
    print("[collector_main] 本地 SQLite 数据库已就绪(V5 schema 已迁移)")

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

    # Reflection worker (阶段 1)
    from scripts.tasks.v5_reflection_worker import V5ReflectionWorker

    async def _reflection_ai_call(prompt: str) -> str:
        """用 trading_assistant 已有的 LLM 客户端做轻量 chat 调用。
        失败时上层 worker 会落 error + retry。"""
        if ai is None or ai.client is None:
            raise RuntimeError("AI client not configured for reflection")
        resp = await ai.client.chat.completions.create(
            model=ai.chat_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""

    reflection_worker = V5ReflectionWorker(
        db_path=db_path,
        ai_call=_reflection_ai_call,
        ai_provider=(ai.provider if ai else None),
        ai_model=(ai.chat_model if ai else None),
        taxonomy_keys=[
            "late_entry_signal_decay", "macd_false_cross",
            "against_4h_trend_no_funding_filter", "sl_too_tight_in_high_atr",
            "tp_too_far_in_low_atr", "news_event_30min_blackout",
            "chase_after_3pct_move", "repeat_failure_same_symbol_24h",
        ],
    )

    mode = _resolve_mode_db()
    print(f"[collector_main] V5 启动 — mode={mode} db={db_path} "
          f"auto_trading={'ON' if cfg.enable_auto_trading else 'OFF'} "
          f"ai={'ON' if ai else 'OFF'}")

    # writer 用旧风格:start() 启动 worker,scorer 把 trade_score 直接写 DB,
    # 这里保留 writer.run() 占位以兼容其他任务/未来扩展。
    writer.start()
    print("[collector_main] DatabaseWriter 已启动")

    # Funding rate collector (V6)
    from scripts.tasks.v5_funding_collector import V5FundingCollector
    from scripts.v5_symbol_whitelist import V5_TOP20_WHITELIST

    funding_collector = V5FundingCollector(
        db_path=db_path,
        symbols=sorted(V5_TOP20_WHITELIST),
    )

    coroutines = [
        scanner.run(),
        deep_collector.run(),
        scorer.run(),
        monitor.run(),
        _healthcheck_loop(db_path),
        reflection_worker.run(),
        funding_collector.run(),
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
