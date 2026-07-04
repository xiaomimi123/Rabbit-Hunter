"""V5 collector_main._fetch_balance 分支测试 (F3)."""
import sys
from unittest.mock import MagicMock


def _stub_ccxt():
    """ccxt 在测试环境未装,先 stub 避免 collector_main import 时崩。"""
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = MagicMock()


def test_fetch_balance_shadow_returns_paper(monkeypatch):
    """SHADOW → 返 _PAPER_BALANCE。"""
    _stub_ccxt()
    from scripts.tasks import collector_main

    monkeypatch.setattr(collector_main, "_resolve_mode_db", lambda: "SHADOW")
    monkeypatch.setattr(collector_main, "_PAPER_BALANCE", 1000.0)

    result = collector_main._fetch_balance()
    assert result == 1000.0


def test_fetch_balance_live_success_returns_real(monkeypatch):
    """LIVE + trader.fetch_balance 返可 parse 的 USDT free → 返真实值。"""
    _stub_ccxt()
    from scripts.tasks import collector_main

    monkeypatch.setattr(collector_main, "_resolve_mode_db", lambda: "LIVE")

    fake_trader = MagicMock()
    fake_trader.fetch_balance.return_value = {"USDT": {"free": 500.5, "available": 500.5}}
    monkeypatch.setattr(collector_main, "_get_live_trader", lambda: fake_trader)

    result = collector_main._fetch_balance()
    assert result == 500.5


def test_fetch_balance_live_failure_returns_none(monkeypatch):
    """LIVE + trader.fetch_balance 抛 → 返 None(不再 fallback 到 1000)。"""
    _stub_ccxt()
    from scripts.tasks import collector_main

    monkeypatch.setattr(collector_main, "_resolve_mode_db", lambda: "LIVE")

    fake_trader = MagicMock()
    fake_trader.fetch_balance.side_effect = RuntimeError("network error")
    monkeypatch.setattr(collector_main, "_get_live_trader", lambda: fake_trader)

    result = collector_main._fetch_balance()
    assert result is None
