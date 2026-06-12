"""V5 manual-order preview + execute 测试。fetch_klines + AI 都 mock。"""
import sqlite3
import sys
import tempfile
import types
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_db(monkeypatch):
    from scripts.local_db import init_local_db
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    monkeypatch.setenv("PAPER_INITIAL_BALANCE_USDT", "1000")
    init_local_db(tmp.name)
    from api.main import app
    return TestClient(app), tmp.name


def _fake_klines():
    """构造能让 RSI 高 + MACD 死叉拐点的 prices。"""
    from tests.conftest import _build_klines
    rising_then_drop = [100 + i * 2 for i in range(40)] + [180, 178, 176]
    klines_15m = _build_klines(rising_then_drop)
    klines_4h = _build_klines([100 + i * 1.5 for i in range(50)])
    return klines_15m, klines_4h


def _inject_fake_exchange(monkeypatch, klines_15m, klines_4h):
    """注入伪造的 exchange_endpoints 模块,避免依赖 requests。"""
    def _fake_fetch(symbol, interval, limit):
        return klines_15m if interval == "15m" else klines_4h

    fake_mod = types.ModuleType("scripts.tasks.exchange_endpoints")
    fake_mod.fetch_klines = _fake_fetch
    monkeypatch.setitem(sys.modules, "scripts.tasks.exchange_endpoints", fake_mod)


def test_preview_returns_full_snapshot(app_with_db, monkeypatch):
    klines_15m, klines_4h = _fake_klines()
    _inject_fake_exchange(monkeypatch, klines_15m, klines_4h)
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "60")

    from v5_types import AIResult
    with patch("scripts.ai.trading_assistant.TradingAssistant") as mock_ta_cls:
        mock_ta = mock_ta_cls.return_value
        mock_ta.client = object()
        mock_ta.provider = "deepseek"
        mock_ta.assistant_id = None
        mock_ta.decide = AsyncMock(return_value=AIResult(
            execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
            size_multiplier=1.0, confidence=0.7, reasoning="ok"))

        client, _ = app_with_db
        r = client.post("/api/v5/manual-order/preview", json={
            "symbol": "TEST/USDT", "side": "SHORT", "size_usdt": 15.0,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["symbol"] == "TEST/USDT"
        assert data["side"] == "SHORT"
        assert "indicators" in data
        assert "decision" in data and "risk_plan" in data and "ai_result" in data
        assert "rag_cases" in data


def test_execute_writes_paper_trade(app_with_db, monkeypatch):
    klines_15m, klines_4h = _fake_klines()
    _inject_fake_exchange(monkeypatch, klines_15m, klines_4h)
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "60")

    from v5_types import AIResult
    with patch("scripts.ai.trading_assistant.TradingAssistant") as mock_ta_cls:
        mock_ta = mock_ta_cls.return_value
        mock_ta.client = object()
        mock_ta.provider = "deepseek"
        mock_ta.assistant_id = None
        mock_ta.decide = AsyncMock(return_value=AIResult(
            execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
            size_multiplier=1.0, confidence=0.7, reasoning="ok"))

        client, db = app_with_db
        r = client.post("/api/v5/manual-order/execute", json={
            "symbol": "TEST/USDT", "side": "SHORT", "size_usdt": 15.0,
            "sl_multiplier": 1.0, "tp_multiplier": 1.0, "size_multiplier": 1.0,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["strategy_id"] == "v5_manual"
        assert data["side"] == "SHORT"
        assert data["position_id"] > 0

        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT symbol, side, status, strategy_id FROM paper_trades "
            "WHERE id=?", (data["position_id"],)).fetchone()
        conn.close()
        assert row == ("TEST/USDT", "SHORT", "OPEN", "v5_manual")
