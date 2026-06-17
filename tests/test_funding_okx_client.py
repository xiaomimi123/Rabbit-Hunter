"""OKX 公开 funding API 客户端测试。HTTP 用 mock,纯数据校验。"""
from unittest.mock import patch, MagicMock

import pytest

from scripts.funding_okx_client import (
    symbol_to_okx_instid,
    okx_instid_to_symbol,
    parse_funding_response,
    fetch_funding_history,
)


def test_symbol_to_okx_instid_basic():
    assert symbol_to_okx_instid("BTCUSDT") == "BTC-USDT-SWAP"
    assert symbol_to_okx_instid("ETHUSDT") == "ETH-USDT-SWAP"
    assert symbol_to_okx_instid("DOGEUSDT") == "DOGE-USDT-SWAP"


def test_symbol_to_okx_instid_already_swap():
    """如果已经是 OKX 格式,直接返回。"""
    assert symbol_to_okx_instid("BTC-USDT-SWAP") == "BTC-USDT-SWAP"


def test_okx_instid_to_symbol():
    assert okx_instid_to_symbol("BTC-USDT-SWAP") == "BTCUSDT"
    assert okx_instid_to_symbol("ETH-USDT-SWAP") == "ETHUSDT"
    assert okx_instid_to_symbol("BTCUSDT") == "BTCUSDT"   # 已经是 V5 格式


def test_parse_funding_response_success():
    raw = {
        "code": "0",
        "data": [
            {
                "fundingRate": "-0.000024895073548",
                "fundingTime": "1781683200000",
                "instId": "BTC-USDT-SWAP",
                "realizedRate": "-0.000020",
            },
            {
                "fundingRate": "0.0000359942934559",
                "fundingTime": "1781654400000",
                "instId": "BTC-USDT-SWAP",
                "realizedRate": "0.0000360",
            },
        ],
        "msg": "",
    }
    out = parse_funding_response(raw)
    assert len(out) == 2
    first = out[0]
    assert first["symbol"] == "BTCUSDT"
    assert first["instrument_id"] == "BTC-USDT-SWAP"
    assert first["funding_rate"] == -0.000024895073548
    assert first["funding_time"].endswith("+00:00")
    # annualized = funding_rate * 365 * 3 (8h periods/day)
    assert abs(first["annualized_rate"] - (-0.000024895073548 * 365 * 3)) < 1e-12
    assert first["settled_rate"] == -0.000020


def test_parse_funding_response_okx_error():
    raw = {"code": "50001", "data": [], "msg": "API frequency limit exceeded"}
    with pytest.raises(ValueError, match="50001"):
        parse_funding_response(raw)


def test_parse_funding_response_empty_data():
    """code=0 但 data 空(币种不存在) → 返回 []."""
    raw = {"code": "0", "data": [], "msg": ""}
    assert parse_funding_response(raw) == []


def test_fetch_funding_history_uses_urllib_no_external_deps(monkeypatch):
    """mock urllib.request 验证 URL + 参数构造。"""
    captured_urls = []

    class FakeResponse:
        def read(self):
            return b'{"code":"0","data":[],"msg":""}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=10):
        captured_urls.append(req.full_url if hasattr(req, "full_url") else req)
        return FakeResponse()

    import scripts.funding_okx_client as mod
    monkeypatch.setattr(mod, "urlopen", fake_urlopen)

    out = fetch_funding_history("BTCUSDT", limit=5)
    assert out == []
    assert "funding-rate-history" in captured_urls[0]
    assert "instId=BTC-USDT-SWAP" in captured_urls[0]
    assert "limit=5" in captured_urls[0]
