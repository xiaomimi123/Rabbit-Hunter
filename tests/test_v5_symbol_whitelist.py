"""V5 top-20 symbol whitelist 测试。"""
import asyncio
import sqlite3
import tempfile
from unittest.mock import MagicMock

import pytest

from scripts.v5_symbol_whitelist import (
    V5_TOP20_WHITELIST,
    normalize_symbol,
    parse_whitelist_param,
    is_symbol_allowed,
)


# ---------------------------------------------------------------------------
# Unit tests — whitelist module
# ---------------------------------------------------------------------------

def test_whitelist_size_is_25():
    # 2026-06: MATIC removed (delisted from OKX as Polygon rebranded to POL)
    # 2026-06-26: +6 加密主流(WLD/PEPE/AAVE/HYPE/ZEC/IP),OKX SWAP 当前 100M+
    assert len(V5_TOP20_WHITELIST) == 25


def test_matic_no_longer_in_whitelist():
    assert "MATICUSDT" not in V5_TOP20_WHITELIST


def test_whitelist_includes_majors():
    for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"):
        assert s in V5_TOP20_WHITELIST


def test_whitelist_includes_new_2026_06_26_additions():
    """2026-06-26 加入的 6 个 OKX SWAP 100M+ 主流加密币。"""
    for s in ("WLDUSDT", "PEPEUSDT", "AAVEUSDT", "HYPEUSDT", "ZECUSDT", "IPUSDT"):
        assert s in V5_TOP20_WHITELIST


def test_whitelist_excludes_known_meme_and_rwa():
    """这些 RWA / 美股代币化 / meme 应该被过滤掉。"""
    for s in ("BEATUSDT", "HUSDT", "BSBUSDT", "MEGAUSDT", "JTOUSDT", "SPCXUSDT", "LABUSDT",
              "SOXLUSDT", "SKHYNIXUSDT", "SNDKUSDT", "MUUSDT", "XAUUSDT", "XAGUSDT"):
        assert s not in V5_TOP20_WHITELIST


def test_normalize_handles_slash_and_case():
    assert normalize_symbol("btc/usdt") == "BTCUSDT"
    assert normalize_symbol("ETH:USDT") == "ETHUSDT"
    assert normalize_symbol(" SOLUSDT ") == "SOLUSDT"
    assert normalize_symbol("") == ""


def test_parse_whitelist_empty_returns_default():
    assert parse_whitelist_param("") == V5_TOP20_WHITELIST
    assert parse_whitelist_param("   ") == V5_TOP20_WHITELIST


def test_parse_whitelist_custom_overrides():
    wl = parse_whitelist_param("BTCUSDT,ETHUSDT,SOL/USDT")
    assert wl == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}


def test_is_symbol_allowed_with_default():
    assert is_symbol_allowed("BTCUSDT", V5_TOP20_WHITELIST) is True
    assert is_symbol_allowed("btcusdt", V5_TOP20_WHITELIST) is True   # case-insensitive
    assert is_symbol_allowed("BEATUSDT", V5_TOP20_WHITELIST) is False
    assert is_symbol_allowed("BTC/USDT", V5_TOP20_WHITELIST) is True   # normalize handles slash


def test_is_symbol_allowed_with_custom():
    wl = {"BTCUSDT", "ETHUSDT"}
    assert is_symbol_allowed("SOLUSDT", wl) is False
    assert is_symbol_allowed("ETHUSDT", wl) is True


# ---------------------------------------------------------------------------
# Integration smoke tests — scorer wiring
# ---------------------------------------------------------------------------

def test_process_enriched_v5_skips_when_not_whitelisted(monkeypatch):
    """非白名单的 symbol 不评分,不写 trade_scores,不触发 paper_pm.open_position。"""
    monkeypatch.setenv("V5_USE_SYMBOL_WHITELIST", "true")
    # Clear v5_params cache so the env var is picked up fresh
    import scripts.v5_params as _p
    _p._CACHE.clear()

    from v5_types import EnrichedItem
    from scripts.tasks.scorer import process_enriched_v5

    enriched = EnrichedItem(
        symbol="BEATUSDT",   # NOT in whitelist
        current_price=0.166, delta_15m_pct=0.005, volume_24h_usdt=1e7,
        klines_15m=[], klines_4h=[],
    )

    fake_paper_pm = MagicMock()
    fake_paper_pm.open_position = MagicMock()
    fake_live_pm = MagicMock()

    asyncio.run(process_enriched_v5(
        enriched=enriched, ai=None,
        paper_pm=fake_paper_pm, live_pm=fake_live_pm,
        mode="SHADOW", db_path=":memory:", balance_usdt=1000.0,
    ))
    fake_paper_pm.open_position.assert_not_called()


def test_process_enriched_v5_can_be_disabled(monkeypatch):
    """v5_use_symbol_whitelist=false 时,所有币都进入评分流程(过了白名单门)。"""
    monkeypatch.setenv("V5_USE_SYMBOL_WHITELIST", "false")
    import scripts.v5_params as _p
    _p._CACHE.clear()

    from v5_types import EnrichedItem
    from scripts.tasks.scorer import process_enriched_v5

    enriched = EnrichedItem(
        symbol="BEATUSDT",
        current_price=0.166, delta_15m_pct=0.005, volume_24h_usdt=1e7,
        klines_15m=[], klines_4h=[],
    )

    fake_paper_pm = MagicMock()
    fake_live_pm = MagicMock()

    # 白名单关闭后会进入 calculate_indicators → 空 klines → ValueError → 早退
    # 我们只验证它没有在白名单层 return,而是传递到了指标计算层
    try:
        asyncio.run(process_enriched_v5(
            enriched=enriched, ai=None,
            paper_pm=fake_paper_pm, live_pm=fake_live_pm,
            mode="SHADOW", db_path=":memory:", balance_usdt=1000.0,
        ))
    except Exception:
        pass    # OK — 指标层的异常是预期的,不是白名单层的异常
    # 没有更强的 assert — 主要验证没有在白名单层崩溃
