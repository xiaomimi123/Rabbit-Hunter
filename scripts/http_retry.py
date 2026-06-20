"""HTTP 重试 helper — 共享给 funding_okx_client / exchange_endpoints 等模块。

Docker Desktop on macOS 跟 OKX/Binance 的 TLS 会偶发性 SSL EOF /
handshake timeout(分钟级故障)。urllib3 的 Retry 不覆盖这层(它的
status_forcelist 只看 HTTP code),所以这些错误直接抛出来,导致 fetch
函数返回 [] / None,下游 Scorer / FundingCollector 收不到数据。

这个 helper 实现一个**显式重试循环**:
- 5 次尝试
- 指数退避 0.5 / 1 / 2 / 4 / 8 秒
- 只对网络层错误(URLError / SSLError / socket.timeout / ConnectionError)重试
- 其他错误(如 ValueError / RuntimeError)直接抛出
- 全部失败后抛 RuntimeError 包装最后一个异常
"""
from __future__ import annotations

import socket
import ssl
import time
from typing import Callable, TypeVar
from urllib.error import URLError

T = TypeVar("T")

# 跟 backtest/kline_fetcher 同口径
_DEFAULT_BACKOFFS = (0.5, 1.0, 2.0, 4.0, 8.0)


def with_retries(
    fn: Callable[[], T],
    *,
    description: str = "http call",
    max_attempts: int = 5,
    backoffs: tuple = _DEFAULT_BACKOFFS,
    catch_requests_errors: bool = True,
) -> T:
    """Call fn() with retries on network-level errors.

    Args:
        fn: zero-arg callable performing one HTTP request.
        description: short label for the call (used in error message).
        max_attempts: total attempts including first.
        backoffs: sleep seconds before each retry. Must be >= max_attempts-1.
        catch_requests_errors: also catch requests.exceptions.RequestException
            (ConnectionError, Timeout, etc.) — set False if caller doesn't use requests.

    Raises:
        RuntimeError wrapping the last underlying exception if all attempts fail.
        Re-raises any non-network exception immediately (no retry).
    """
    # Build the set of exception types to retry on
    network_excs: list = [URLError, ssl.SSLError, socket.timeout, TimeoutError]
    if catch_requests_errors:
        try:
            import requests
            network_excs.append(requests.exceptions.RequestException)
        except ImportError:
            pass
    network_tuple = tuple(network_excs)

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except network_tuple as e:
            last_exc = e
            if attempt < max_attempts - 1:
                time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
                continue
        # Non-network exceptions bubble immediately
        # (we don't reach here; this comment is just for documentation)

    raise RuntimeError(
        f"{description} failed after {max_attempts} attempts: "
        f"{type(last_exc).__name__}: {last_exc}"
    ) from last_exc


__all__ = ["with_retries"]
