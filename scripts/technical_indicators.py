"""
技术指标计算模块

实现常用的技术指标：
- RSI (相对强弱指标)
- MACD (移动平均收敛散度)
- 布林带 (Bollinger Bands)
- 均线系统 (MA5, MA10, MA20, MA50)
"""

from typing import Optional
import numpy as np


def calculate_rsi(prices: list[float], period: int = 14) -> Optional[float]:
    """
    计算 RSI (相对强弱指标)
    
    Args:
        prices: 价格列表（从旧到新）
        period: 计算周期，默认 14
    
    Returns:
        RSI 值 (0-100)，如果数据不足返回 None
    """
    if len(prices) < period + 1:
        return None
    
    prices = np.array(prices[-period-1:])
    deltas = np.diff(prices)
    
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return float(rsi)


def calculate_macd(
    prices: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Optional[dict]:
    """
    计算 MACD (移动平均收敛散度)
    
    Args:
        prices: 价格列表（从旧到新）
        fast_period: 快线周期，默认 12
        slow_period: 慢线周期，默认 26
        signal_period: 信号线周期，默认 9
    
    Returns:
        {
            'macd': float,      # MACD 线
            'signal': float,    # 信号线
            'histogram': float  # 柱状图（MACD - Signal）
        }
        如果数据不足返回 None
    """
    if len(prices) < slow_period + signal_period:
        return None
    
    prices = np.array(prices)
    
    # 计算 EMA
    def ema(data: np.ndarray, period: int) -> np.ndarray:
        ema_values = np.zeros_like(data)
        multiplier = 2 / (period + 1)
        
        ema_values[0] = data[0]
        for i in range(1, len(data)):
            ema_values[i] = (data[i] * multiplier) + (ema_values[i-1] * (1 - multiplier))
        
        return ema_values
    
    # 计算快线和慢线 EMA
    fast_ema = ema(prices, fast_period)
    slow_ema = ema(prices, slow_period)
    
    # MACD 线 = 快线 - 慢线
    macd_line = fast_ema - slow_ema
    
    # 信号线 = MACD 线的 EMA
    signal_line = ema(macd_line, signal_period)
    
    # 柱状图 = MACD - Signal
    histogram = macd_line - signal_line
    
    return {
        'macd': float(macd_line[-1]),
        'signal': float(signal_line[-1]),
        'histogram': float(histogram[-1])
    }


def calculate_bollinger_bands(
    prices: list[float],
    period: int = 20,
    std_dev: float = 2.0
) -> Optional[dict]:
    """
    计算布林带 (Bollinger Bands)
    
    Args:
        prices: 价格列表（从旧到新）
        period: 计算周期，默认 20
        std_dev: 标准差倍数，默认 2.0
    
    Returns:
        {
            'upper': float,  # 上轨
            'middle': float, # 中轨（MA）
            'lower': float   # 下轨
        }
        如果数据不足返回 None
    """
    if len(prices) < period:
        return None
    
    prices = np.array(prices[-period:])
    
    # 中轨 = 移动平均
    middle = np.mean(prices)
    
    # 标准差
    std = np.std(prices)
    
    # 上轨和下轨
    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)
    
    return {
        'upper': float(upper),
        'middle': float(middle),
        'lower': float(lower)
    }


def calculate_moving_averages(prices: list[float]) -> dict:
    """
    计算多条均线
    
    Args:
        prices: 价格列表（从旧到新）
    
    Returns:
        {
            'ma5': float | None,
            'ma10': float | None,
            'ma20': float | None,
            'ma50': float | None
        }
    """
    result = {
        'ma5': None,
        'ma10': None,
        'ma20': None,
        'ma50': None
    }
    
    prices = np.array(prices)
    
    if len(prices) >= 5:
        result['ma5'] = float(np.mean(prices[-5:]))
    
    if len(prices) >= 10:
        result['ma10'] = float(np.mean(prices[-10:]))
    
    if len(prices) >= 20:
        result['ma20'] = float(np.mean(prices[-20:]))
    
    if len(prices) >= 50:
        result['ma50'] = float(np.mean(prices[-50:]))
    
    return result


def get_all_indicators(prices: list[float]) -> dict:
    """
    计算所有技术指标
    
    Args:
        prices: 价格列表（从旧到新），建议至少 50 个数据点
    
    Returns:
        {
            'rsi': float | None,
            'macd': dict | None,
            'bollinger': dict | None,
            'moving_averages': dict
        }
    """
    return {
        'rsi': calculate_rsi(prices),
        'macd': calculate_macd(prices),
        'bollinger': calculate_bollinger_bands(prices),
        'moving_averages': calculate_moving_averages(prices)
    }

