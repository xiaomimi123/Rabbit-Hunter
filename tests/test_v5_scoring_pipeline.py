"""V5 scoring pipeline 集成测试。Mock OKX 拉 K 线 + AI,验证端到端流。"""
import asyncio
import sqlite3
import tempfile
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from tests.conftest import _build_klines


@pytest.fixture
def fresh_db():
    from scripts.local_db import init_local_db
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    init_local_db(tmp.name)
    return tmp.name


@pytest.mark.asyncio
async def test_strong_signal_writes_trade_scores_v5_and_paper_trade(fresh_db, monkeypatch):
    """构造一个必然触发 SHORT 的输入 → 验证 paper_trades + trade_scores_v5 各写一行。"""
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "60")
    monkeypatch.setenv("DB_PATH", fresh_db)
    monkeypatch.setenv("V5_USE_SYMBOL_WHITELIST", "false")  # 测试用的 TEST/USDT 不在白名单

    rising_then_drop = [100 + i * 2 for i in range(40)] + [180, 178, 176]
    klines_15m = _build_klines(rising_then_drop)
    klines_4h = _build_klines([100 + i * 1.5 for i in range(40)])

    from v5_types import AIResult
    fake_ai = MagicMock()
    fake_ai.decide = AsyncMock(return_value=AIResult(
        execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
        size_multiplier=1.0, confidence=0.7, reasoning="test"
    ))

    monkeypatch.setenv("PAPER_INITIAL_BALANCE_USDT", "100000")

    from scripts.tasks.scorer import process_enriched_v5
    from v5_types import EnrichedItem
    enriched = EnrichedItem(
        symbol="TEST/USDT", current_price=176.0, delta_15m_pct=-0.034,
        volume_24h_usdt=50_000_000, klines_15m=klines_15m, klines_4h=klines_4h,
    )

    from scripts.paper_position_manager import PaperPositionManager
    paper_pm = PaperPositionManager(db_path=fresh_db)

    # 用 100k 本金:1% = 1000 USDT 风险预算,足够吸收测试 fixture 的极端 ATR。
    await process_enriched_v5(
        enriched=enriched, ai=fake_ai, paper_pm=paper_pm, live_pm=None,
        mode="SHADOW", db_path=fresh_db, balance_usdt=100_000.0,
    )

    conn = sqlite3.connect(fresh_db)
    scores = conn.execute(
        "SELECT symbol, should_trade, side, executed FROM trade_scores_v5"
    ).fetchall()
    trades = conn.execute(
        "SELECT symbol, side, status FROM paper_trades"
    ).fetchall()
    conn.close()

    assert len(scores) == 1
    assert scores[0][0] == "TEST/USDT"
    assert scores[0][1] == 1
    assert scores[0][2] == "SHORT"
    assert scores[0][3] == 1
    assert len(trades) == 1
    assert trades[0] == ("TEST/USDT", "SHORT", "OPEN")


def test_process_enriched_v5_injects_funding_zscore(monkeypatch):
    """funding_zscore_cache 有数据时,trade_scores 应当含 funding_z_score。"""
    import asyncio
    import sqlite3
    import tempfile
    from unittest.mock import MagicMock

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    monkeypatch.setenv("V5_USE_SYMBOL_WHITELIST", "false")
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")

    from scripts.local_db import init_local_db
    init_local_db(tmp.name)

    # 注入 funding cache for BTCUSDT
    conn = sqlite3.connect(tmp.name)
    conn.execute("""
        INSERT INTO funding_zscore_cache (symbol, current_funding_rate,
            zscore_30d, sample_size_30d, is_extreme, extreme_direction)
        VALUES ('BTCUSDT', 0.0008, 2.5, 30, 1, 'long_crowded')
    """)
    conn.commit()
    conn.close()

    from v5_types import EnrichedItem
    from scripts.tasks.scorer import process_enriched_v5
    from tests.conftest import _build_klines

    # 给足 K 线让 indicators 算得出
    klines_15m = _build_klines([100 + i for i in range(50)])
    klines_4h = _build_klines([100 + i * 2 for i in range(50)])

    enriched = EnrichedItem(
        symbol="BTCUSDT", current_price=150.0,
        delta_15m_pct=0.005, volume_24h_usdt=5e7,
        klines_15m=klines_15m, klines_4h=klines_4h,
    )

    asyncio.run(process_enriched_v5(
        enriched=enriched, ai=None,
        paper_pm=MagicMock(), live_pm=MagicMock(),
        mode="SHADOW", db_path=tmp.name, balance_usdt=1000.0,
    ))

    conn = sqlite3.connect(tmp.name)
    row = conn.execute(
        "SELECT funding_z_score, funding_rate_8h FROM trade_scores_v5 "
        "WHERE symbol='BTCUSDT' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 2.5
    assert row[1] == 0.0008


def test_disabled_auto_trading_writes_block_reason_no_paper_trade(monkeypatch):
    """enable_auto_trading=false → trade_scores 写一行 'AUTO_TRADING_DISABLED',无开仓。"""
    import asyncio
    import sqlite3
    import tempfile
    from unittest.mock import MagicMock, AsyncMock

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "60")
    monkeypatch.setenv("DB_PATH", tmp.name)
    monkeypatch.setenv("V5_USE_SYMBOL_WHITELIST", "false")

    from scripts.local_db import init_local_db
    init_local_db(tmp.name)

    # 关掉自动交易开关
    conn = sqlite3.connect(tmp.name)
    conn.execute(
        "INSERT INTO system_settings(key, value) VALUES (?, ?)",
        ("enable_auto_trading", "false"),
    )
    conn.commit()
    conn.close()

    rising_then_drop = [100 + i * 2 for i in range(40)] + [180, 178, 176]
    klines_15m = _build_klines(rising_then_drop)
    klines_4h = _build_klines([100 + i * 1.5 for i in range(40)])

    from v5_types import AIResult, EnrichedItem
    fake_ai = MagicMock()
    fake_ai.decide = AsyncMock(return_value=AIResult(
        execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
        size_multiplier=1.0, confidence=0.7, reasoning="test"
    ))

    from scripts.tasks.scorer import process_enriched_v5
    from scripts.paper_position_manager import PaperPositionManager
    paper_pm = PaperPositionManager(db_path=tmp.name)

    enriched = EnrichedItem(
        symbol="TEST/USDT", current_price=176.0, delta_15m_pct=-0.034,
        volume_24h_usdt=50_000_000, klines_15m=klines_15m, klines_4h=klines_4h,
    )

    asyncio.run(process_enriched_v5(
        enriched=enriched, ai=fake_ai, paper_pm=paper_pm, live_pm=None,
        mode="SHADOW", db_path=tmp.name, balance_usdt=100_000.0,
    ))

    conn = sqlite3.connect(tmp.name)
    scores = conn.execute(
        "SELECT block_reason, executed FROM trade_scores_v5"
    ).fetchall()
    trades = conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()
    conn.close()

    assert len(scores) == 1
    assert scores[0][0] == "AUTO_TRADING_DISABLED"
    assert scores[0][1] == 0     # executed = 0
    assert trades[0] == 0         # 无开仓


def test_process_enriched_v5_funding_null_when_cache_miss(monkeypatch):
    """cache 没数据时,funding_z_score 写 NULL,不阻塞。"""
    import asyncio
    import sqlite3
    import tempfile
    from unittest.mock import MagicMock

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    monkeypatch.setenv("V5_USE_SYMBOL_WHITELIST", "false")
    monkeypatch.setenv("V5_STRATEGY_MODE", "and_strict")

    from scripts.local_db import init_local_db
    init_local_db(tmp.name)

    from v5_types import EnrichedItem
    from scripts.tasks.scorer import process_enriched_v5
    from tests.conftest import _build_klines

    klines_15m = _build_klines([100 + i for i in range(50)])
    klines_4h = _build_klines([100 + i * 2 for i in range(50)])

    enriched = EnrichedItem(
        symbol="UNKNOWN_NOT_IN_CACHE_USDT", current_price=150.0,
        delta_15m_pct=0.005, volume_24h_usdt=5e7,
        klines_15m=klines_15m, klines_4h=klines_4h,
    )

    asyncio.run(process_enriched_v5(
        enriched=enriched, ai=None,
        paper_pm=MagicMock(), live_pm=MagicMock(),
        mode="SHADOW", db_path=tmp.name, balance_usdt=1000.0,
    ))

    conn = sqlite3.connect(tmp.name)
    row = conn.execute(
        "SELECT funding_z_score FROM trade_scores_v5 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] is None    # NULL = cache miss
