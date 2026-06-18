"""Tests for backtest kline cache + OKX fetch."""
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.backtest.kline_fetcher import (
    cache_path_for,
    load_cached_klines,
    save_klines_to_cache,
    fetch_klines_with_cache,
)


def test_cache_path_for_includes_range_info(tmp_path):
    p = cache_path_for(str(tmp_path), "BTCUSDT", "15m",
                       "2026-05-01T00:00:00+00:00",
                       "2026-06-01T00:00:00+00:00")
    s = str(p)
    assert "BTCUSDT" in s
    assert "15m" in s
    assert "20260501" in s
    assert "20260601" in s
    assert s.endswith(".json")


def test_save_then_load_round_trip(tmp_path):
    klines = [
        [1716076800000, 65000.0, 65100.0, 64900.0, 65050.0, 100.0],
        [1716077700000, 65050.0, 65200.0, 65000.0, 65150.0, 120.0],
    ]
    save_klines_to_cache(str(tmp_path), "BTCUSDT", "15m",
                         "2026-05-19T00:00:00+00:00",
                         "2026-05-19T01:00:00+00:00", klines)
    loaded = load_cached_klines(str(tmp_path), "BTCUSDT", "15m",
                                "2026-05-19T00:00:00+00:00",
                                "2026-05-19T01:00:00+00:00")
    assert loaded == klines


def test_load_returns_none_when_no_cache_file(tmp_path):
    out = load_cached_klines(str(tmp_path), "ETHUSDT", "15m",
                             "2026-05-19T00:00:00+00:00",
                             "2026-05-19T01:00:00+00:00")
    assert out is None


@patch("scripts.backtest.kline_fetcher._fetch_okx_history")
def test_fetch_with_cache_hits_cache_on_second_call(mock_fetch, tmp_path):
    mock_fetch.return_value = [
        [1716076800000, 65000.0, 65100.0, 64900.0, 65050.0, 100.0],
    ]
    out1 = fetch_klines_with_cache(str(tmp_path), "BTCUSDT", "15m",
                                   "2026-05-19T00:00:00+00:00",
                                   "2026-05-19T01:00:00+00:00")
    assert mock_fetch.call_count == 1
    out2 = fetch_klines_with_cache(str(tmp_path), "BTCUSDT", "15m",
                                   "2026-05-19T00:00:00+00:00",
                                   "2026-05-19T01:00:00+00:00")
    assert mock_fetch.call_count == 1   # cache hit, no extra OKX call
    assert out1 == out2


@patch("scripts.backtest.kline_fetcher._fetch_okx_history")
def test_fetch_writes_to_cache_file_on_miss(mock_fetch, tmp_path):
    mock_fetch.return_value = [
        [1716076800000, 65000.0, 65100.0, 64900.0, 65050.0, 100.0],
    ]
    out = fetch_klines_with_cache(str(tmp_path), "BTCUSDT", "15m",
                                  "2026-05-19T00:00:00+00:00",
                                  "2026-05-19T01:00:00+00:00")
    p = cache_path_for(str(tmp_path), "BTCUSDT", "15m",
                       "2026-05-19T00:00:00+00:00",
                       "2026-05-19T01:00:00+00:00")
    assert p.exists()
    assert out == mock_fetch.return_value


def test_unsupported_interval_raises():
    from scripts.backtest.kline_fetcher import _interval_to_okx_bar
    with pytest.raises(ValueError):
        _interval_to_okx_bar("30m")
