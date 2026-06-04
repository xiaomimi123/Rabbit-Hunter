"""
币安持仓查询工具

从币安 API 获取实际持仓信息
"""

import os
from typing import Optional

import ccxt
import requests
from dotenv import load_dotenv

# 载入环境变量
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET")


def init_exchange() -> Optional[ccxt.binanceusdm]:
    """
    初始化币安 USDT 永续合约交易所实例（用于查询持仓）
    
    注意：查询持仓需要有效的 API Key
    """
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        return None

    config: dict = {
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",  # 使用合约市场
        },
        "apiKey": BINANCE_API_KEY,
        "secret": BINANCE_API_SECRET,
    }

    exchange = ccxt.binanceusdm(config)
    return exchange


def fetch_positions_via_api() -> list[dict]:
    """
    使用币安 API 直接获取持仓（需要 API Key）
    
    返回格式：
    [
        {
            "symbol": "TRB/USDT",
            "size": 10.0,           # 持仓数量（正数=多单，负数=空单）
            "entry_price": 120.5,   # 开仓价格
            "mark_price": 125.0,    # 标记价格
            "unrealized_pnl": 45.0, # 未实现盈亏
            "margin_type": "isolated", # 保证金类型
            "leverage": 10,         # 杠杆倍数
            "liquidation_price": 100.0, # 强平价格
        }
    ]
    """
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        raise Exception("需要配置 BINANCE_API_KEY 和 BINANCE_API_SECRET 才能查询持仓")

    base_url = "https://fapi.binance.com"
    
    # 币安 API 需要签名认证
    # 这里使用 ccxt 来处理签名，或者直接使用 requests + hmac
    
    try:
        # 方法1: 使用 ccxt（推荐，自动处理签名）
        exchange = init_exchange()
        if exchange is None:
            raise Exception("无法初始化交易所实例")
        
        # 获取持仓信息
        positions = exchange.fapiPrivate_get_positionrisk()
        
        # 过滤出有持仓的（positionAmt != 0）
        active_positions = []
        for pos in positions:
            position_amt = float(pos.get("positionAmt", 0))
            if abs(position_amt) > 0:  # 有持仓
                entry_price = float(pos.get("entryPrice", 0))
                mark_price = float(pos.get("markPrice", 0))
                unrealized_pnl = float(pos.get("unRealizedProfit", 0))
                
                # 转换币安 symbol 为 ccxt 格式
                binance_symbol = pos.get("symbol", "")
                symbol = binance_symbol_to_ccxt(binance_symbol)
                
                active_positions.append({
                    "symbol": symbol,
                    "size": position_amt,  # 正数=多单，负数=空单
                    "entry_price": entry_price,
                    "mark_price": mark_price,
                    "current_price": mark_price,  # 标记价格作为当前价格
                    "unrealized_pnl": unrealized_pnl,
                    "pnl": unrealized_pnl,  # 兼容字段
                    "margin_type": pos.get("marginType", "unknown"),
                    "leverage": int(pos.get("leverage", 1)),
                    "liquidation_price": float(pos.get("liquidationPrice", 0)),
                    "notional": float(pos.get("notional", 0)),  # 持仓名义价值
                })
        
        return active_positions
        
    except Exception as e:  # noqa: BLE001
        raise Exception(f"获取币安持仓失败: {e}")


def binance_symbol_to_ccxt(binance_symbol: str) -> str:
    """
    将币安合约格式转换为 ccxt 格式
    例如：TRBUSDT -> TRB/USDT
    """
    # 币安 USDT 永续合约格式：BASEUSDT
    # 需要找到 USDT 的位置
    if binance_symbol.endswith("USDT"):
        base = binance_symbol[:-4]  # 去掉 USDT
        return f"{base}/USDT"
    # 如果格式不对，返回原样
    return binance_symbol


def get_positions() -> list[dict]:
    """
    获取当前持仓（对外接口）
    
    返回格式与 PositionResponse 模型兼容
    """
    try:
        positions = fetch_positions_via_api()
        return positions
    except Exception as e:  # noqa: BLE001
        # 如果查询失败，返回空列表
        print(f"[WARNING] 查询持仓失败: {e}")
        return []


if __name__ == "__main__":
    # 测试代码
    print("测试持仓查询...")
    try:
        positions = get_positions()
        if positions:
            print(f"当前持仓数量: {len(positions)}")
            for pos in positions:
                print(f"  {pos['symbol']}: {pos['size']:.4f} @ {pos['entry_price']:.4f} | PnL: {pos['pnl']:.2f} USDT")
        else:
            print("当前无持仓")
    except Exception as e:  # noqa: BLE001
        print(f"错误: {e}")

