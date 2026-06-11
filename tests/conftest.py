"""Pytest fixtures for V5 tests."""
import sys
from pathlib import Path

# 把 scripts/ 加入 import path,让测试能 import scripts/v5_*
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))


def _build_klines(prices, base_volume=1000.0, interval_seconds=900):
    """构造 OHLCV 数据,长度 = len(prices),用于模拟 K 线。

    返回 List[Tuple[ts, open, high, low, close, volume]]。
    interval_seconds=900 = 15min;3600=1h;14400=4h。
    """
    import time as _time
    result = []
    base_ts = int(_time.time() * 1000) - len(prices) * interval_seconds * 1000
    for i, close in enumerate(prices):
        prev_close = prices[i - 1] if i > 0 else close
        open_ = prev_close
        high = max(open_, close) * 1.005
        low = min(open_, close) * 0.995
        ts = base_ts + i * interval_seconds * 1000
        result.append((ts, open_, high, low, close, base_volume))
    return result


def pytest_collection_modifyitems(config, items):
    """没用上,占位让 pytest 知道 conftest 在被加载。"""
    pass
