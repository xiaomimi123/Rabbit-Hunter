"""
币安持仓同步模块（V4.5）

功能：
- 定期从币安 API 同步持仓
- 更新 positions_v43 表
- 处理数据不一致的情况
"""

import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

try:
    from binance_trader import BinanceTrader
except ImportError:
    BinanceTrader = None

from binance_config_manager import get_config_manager


class BinancePositionSync:
    """
    币安持仓同步器
    
    功能：
    - 从币安 API 同步持仓到数据库
    - 处理数据不一致
    - 更新持仓状态
    """
    
    def __init__(self, supabase_client=None, trader=None):
        """
        初始化持仓同步器
        
        Args:
            supabase_client: Supabase 客户端
            trader: BinanceTrader 实例（如果为 None，会尝试创建）
        """
        self.supabase = supabase_client
        self.trader = trader
        self.last_sync_time: Optional[datetime] = None
    
    def _get_trader(self):
        """获取交易器实例"""
        if self.trader:
            return self.trader
        
        # 尝试从配置管理器获取配置
        config_manager = get_config_manager(self.supabase)
        config = config_manager.get_config()
        
        if not config:
            return None
        
        try:
            if BinanceTrader is None:
                from binance_trader import BinanceTrader
            return BinanceTrader(
                api_key=config["api_key"],
                api_secret=config["api_secret"],
                testnet=config["testnet"],
                leverage=config.get("leverage", 10),
            )
        except Exception as e:
            print(f"[ERROR] 创建交易器失败: {e}")
            return None
    
    def sync_positions(self) -> Dict[str, Any]:
        """
        同步持仓
        
        从币安 API 获取持仓，更新 positions_v43 表
        
        Returns:
            同步结果字典
        """
        trader = self._get_trader()
        if not trader:
            return {
                "success": False,
                "error": "交易器未配置",
                "synced_count": 0,
            }
        
        if not self.supabase:
            return {
                "success": False,
                "error": "Supabase 未配置",
                "synced_count": 0,
            }
        
        try:
            # 1. 从币安获取持仓
            binance_positions = trader.exchange.fapiPrivate_get_positionrisk()
            
            # 2. 从数据库获取持仓
            db_positions_response = self.supabase.table("positions_v43").select("*").eq("status", "OPEN").execute()
            db_positions = {pos["symbol"]: pos for pos in (db_positions_response.data or [])}
            
            synced_count = 0
            created_count = 0
            updated_count = 0
            closed_count = 0
            errors = []
            
            # 3. 处理币安持仓
            for binance_pos in binance_positions:
                symbol_binance = binance_pos.get("symbol", "")
                position_amt = float(binance_pos.get("positionAmt", 0))
                
                # 跳过无持仓的币种
                if abs(position_amt) < 0.0001:
                    continue
                
                # 转换为 CCXT 格式
                symbol_ccxt = self._binance_to_ccxt_symbol(symbol_binance)
                
                # 确定方向
                side = "LONG" if position_amt > 0 else "SHORT"
                entry_price = float(binance_pos.get("entryPrice", 0))
                current_price = float(binance_pos.get("markPrice", entry_price))
                leverage = float(binance_pos.get("leverage", 10))
                unrealized_pnl = float(binance_pos.get("unRealizedProfit", 0))
                
                # 检查数据库是否有该持仓
                if symbol_ccxt in db_positions:
                    # 更新现有持仓
                    db_pos = db_positions[symbol_ccxt]
                    update_data = {
                        "current_price": current_price,
                        "position_size": abs(position_amt),
                        "leverage": leverage,
                        "unrealized_pnl": unrealized_pnl,
                        "updated_at": datetime.now().isoformat(),
                    }
                    
                    try:
                        self.supabase.table("positions_v43").update(update_data).eq("id", db_pos["id"]).execute()
                        updated_count += 1
                    except Exception as e:
                        errors.append(f"更新 {symbol_ccxt} 失败: {e}")
                else:
                    # 创建新持仓记录（可能是外部开仓）
                    new_position = {
                        "symbol": symbol_ccxt,
                        "side": side,
                        "entry_price": entry_price,
                        "current_price": current_price,
                        "position_size": abs(position_amt),
                        "leverage": leverage,
                        "status": "OPEN",
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat(),
                        "source": "BINANCE_SYNC",  # 标记为同步创建
                    }
                    
                    try:
                        self.supabase.table("positions_v43").insert(new_position).execute()
                        created_count += 1
                    except Exception as e:
                        errors.append(f"创建 {symbol_ccxt} 失败: {e}")
                
                synced_count += 1
            
            # 4. 检查数据库中的持仓是否在币安还存在
            binance_symbols = {self._binance_to_ccxt_symbol(pos.get("symbol", "")) for pos in binance_positions if abs(float(pos.get("positionAmt", 0))) >= 0.0001}
            
            for symbol_ccxt, db_pos in db_positions.items():
                if symbol_ccxt not in binance_symbols:
                    # 币安已无持仓，但数据库显示 OPEN，标记为 CLOSED
                    try:
                        self.supabase.table("positions_v43").update({
                            "status": "CLOSED",
                            "closed_at": datetime.now().isoformat(),
                            "close_reason": "BINANCE_SYNC_CLOSED",
                            "updated_at": datetime.now().isoformat(),
                        }).eq("id", db_pos["id"]).execute()
                        closed_count += 1
                    except Exception as e:
                        errors.append(f"关闭 {symbol_ccxt} 失败: {e}")
            
            self.last_sync_time = datetime.now()
            
            result = {
                "success": True,
                "synced_count": synced_count,
                "created_count": created_count,
                "updated_count": updated_count,
                "closed_count": closed_count,
                "errors": errors,
                "sync_time": self.last_sync_time.isoformat(),
            }
            
            if errors:
                print(f"[WARNING] 持仓同步完成，但有 {len(errors)} 个错误")
            else:
                print(f"[INFO] ✅ 持仓同步完成: 同步 {synced_count} 个，创建 {created_count} 个，更新 {updated_count} 个，关闭 {closed_count} 个")
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] 持仓同步失败: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "synced_count": 0,
            }
    
    def _binance_to_ccxt_symbol(self, binance_symbol: str) -> str:
        """
        将币安格式转换为 CCXT 格式
        例如：TRBUSDT -> TRB/USDT
        """
        if binance_symbol.endswith("USDT"):
            base = binance_symbol[:-4]
            return f"{base}/USDT"
        return binance_symbol
    
    def get_sync_status(self) -> Dict[str, Any]:
        """获取同步状态"""
        return {
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "trader_configured": self._get_trader() is not None,
            "supabase_configured": self.supabase is not None,
        }


# 全局同步器实例
_position_sync: Optional[BinancePositionSync] = None


def get_position_sync(supabase_client=None, trader=None) -> BinancePositionSync:
    """
    获取持仓同步器实例（单例）
    
    Args:
        supabase_client: Supabase 客户端
        trader: BinanceTrader 实例
        
    Returns:
        持仓同步器实例
    """
    global _position_sync
    
    if _position_sync is None:
        _position_sync = BinancePositionSync(supabase_client=supabase_client, trader=trader)
    elif supabase_client and _position_sync.supabase != supabase_client:
        _position_sync.supabase = supabase_client
    elif trader and _position_sync.trader != trader:
        _position_sync.trader = trader
    
    return _position_sync


__all__ = ["BinancePositionSync", "get_position_sync"]

