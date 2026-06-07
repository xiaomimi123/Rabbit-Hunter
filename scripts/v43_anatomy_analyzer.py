"""
V4.3 币种深度解剖分析器

功能：
- 结构性缺口识别
- 蜡烛图形态分析
- 权重分布计算
- 推荐止损/盈利比
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List
from datetime import datetime
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# 确保 scripts 目录在路径中
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

try:
    from supabase import create_client, Client
    from scripts.v43_feature_extractor import extract_features
    from scripts.v43_score_calculator import calculate_scores
    from scripts.v43_weight_manager import get_current_weights
    import ccxt
except ImportError as e:
    print(f"[WARNING] V4.3 AnatomyAnalyzer 导入失败: {e}")
    # 尝试备用导入路径
    try:
        from v43_feature_extractor import extract_features  # type: ignore
        from v43_score_calculator import calculate_scores  # type: ignore
        from v43_weight_manager import get_current_weights  # type: ignore
    except ImportError:
        pass


class AnatomyAnalyzer:
    """
    币种深度解剖分析器
    
    提供：
    1. 结构性缺口分析
    2. 蜡烛图形态识别
    3. AI 权重分布
    4. 止损/盈利比推荐
    """
    
    def __init__(self, supabase_client: Optional[Client] = None, exchange: Optional[ccxt.Exchange] = None, trader=None):
        """
        初始化分析器
        
        Args:
            supabase_client: Supabase 客户端
            exchange: CCXT 交易所实例（已废弃，使用 public_exchange）
            trader: BinanceTrader 实例（可选，如果提供且已初始化，会使用其 exchange）
        """
        self.supabase = supabase_client
        self.trader = trader
        # 保留 self.exchange 用于向后兼容，但优先使用 self.public_exchange
        self.exchange = exchange
        self.public_exchange = None
        self._init_clients()
    
    def _init_clients(self):
        """初始化客户端"""
        # Supabase
        if not self.supabase:
            try:
                SUPABASE_URL = os.environ.get("SUPABASE_URL")
                SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
                if SUPABASE_URL and SUPABASE_KEY:
                    self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            except Exception as e:
                print(f"[WARNING] AnatomyAnalyzer: Supabase 初始化失败: {e}")
        
        # Exchange（公共 API，不需要 API Key，用于获取 K 线等公共数据）
        # 优先使用 trader 的 exchange（如果已初始化），否则创建新的公共 exchange
        if self.trader and hasattr(self.trader, 'exchange') and self.trader.exchange:
            self.public_exchange = self.trader.exchange
        elif self.exchange:
            self.public_exchange = self.exchange
        else:
            # 创建新的公共 exchange（不需要 API Key）
            try:
                self.public_exchange = ccxt.binanceusdm({
                    "enableRateLimit": True,
                    "options": {
                        "defaultType": "future",
                        "adjustForTimeDifference": True,  # 自动调整时间差
                    }
                })
                # 测试连接
                self.public_exchange.load_markets()
                # 向后兼容：同时设置 self.exchange
                self.exchange = self.public_exchange
            except Exception as e:
                print(f"[WARNING] AnatomyAnalyzer: Exchange 初始化失败: {e}")
                self.public_exchange = None
                self.exchange = None  # 确保设置为 None，避免后续错误
    
    def analyze_symbol(
        self,
        symbol: str,
        timeframe: str = "15m"
    ) -> Dict[str, Any]:
        """
        执行深度分析
        
        Args:
            symbol: 交易对（如 'BTC/USDT'）
            timeframe: 时间周期（如 '15m', '1h', '4h'）
        
        Returns:
            分析结果字典（包含前端需要的 ATR 止损位 / 盈亏比等字段）
        """
        try:
            # 1. 获取 K 线数据（用于 ATR 计算 + 可视化）
            candles = self._get_candles(symbol, timeframe, limit=100)
            
            # 2. 估算当前价格（优先使用最新 K 线的收盘价）
            price = 0.0
            if candles:
                price = float(candles[-1]["close"])
            elif self.public_exchange or self.exchange:
                # 退而求其次：使用 ticker 价格
                exchange_to_use = self.public_exchange or self.exchange
                try:
                    ticker = exchange_to_use.fetch_ticker(symbol)
                    price = float(ticker.get("last") or ticker.get("close") or ticker.get("ask") or ticker.get("bid") or 0.0)
                except Exception as e:  # noqa: BLE001
                    print(f"[WARNING] AnatomyAnalyzer: 获取 {symbol} ticker 失败: {e}")
            
            # 3. 粗略计算 ATR（用于止损/止盈建议）
            atr_value = 0.0
            if candles and len(candles) >= 2:
                trs = []
                prev_close = float(candles[0]["close"])
                for c in candles[1:]:
                    high = float(c["high"])
                    low = float(c["low"])
                    close = float(c["close"])
                    tr = max(
                        high - low,
                        abs(high - prev_close),
                        abs(low - prev_close),
                    )
                    trs.append(tr)
                    prev_close = close
                if trs:
                    atr_value = sum(trs) / len(trs)
            
            # 4. 提取特征（使用与主策略一致的特征提取函数）
            features = extract_features(
                symbol=symbol,
                price=price,
                funding_rate=None,
                long_short_ratio=None,
                oi_value=None,
                oi_change_1h=None,
                price_change_1h=None,
                cvd_data=None,
                oi_series=None,
                prices=None,
                highs_1h=None,
                closes_1h=None,
                phase_4h=None,
                phase_1h=None,
                phase_age_candles=None,
                atr_value=atr_value,
                ohlcv_15m=None,
            )
            
            # 5. 计算分数
            scores = calculate_scores(features)
            
            # 6. 获取当前权重
            weights = get_current_weights()
            
            # 7. 计算最终分数（0-1）
            final_score = (
                scores["structure_score"] * weights.get("structure", 0.25) +
                scores["volatility_score"] * weights.get("volatility", 0.25) +
                scores["sentiment_score"] * weights.get("sentiment", 0.25) +
                scores["manipulation_score"] * weights.get("manipulation", 0.25)
            )
            
            # 8. 分析结构缺口
            structural_gap = self._analyze_structural_gap(features, candles)
            
            # 9. 分析蜡烛图形态
            candlestick_analysis = self._analyze_candlestick_patterns(candles)
            
            # 10. 计算推荐止损/盈利比
            stop_loss, take_profit = self._calculate_stop_loss_take_profit(features, scores)
            
            price_for_rr = features.get("price", price or 0.0)
            reward_risk_ratio = 0.0
            try:
                if stop_loss < price_for_rr and price_for_rr > 0:
                    reward = take_profit - price_for_rr
                    risk = price_for_rr - stop_loss
                    if risk > 0:
                        reward_risk_ratio = round(reward / risk, 2)
            except Exception:
                reward_risk_ratio = 0.0
            
            # 11. 组装返回结构（兼容前端 AnatomyPanel 的字段）
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp": datetime.now().isoformat(),
                "features": features,
                "scores": {
                    "structure": round(scores["structure_score"] * 100, 1),
                    "volatility": round(scores["volatility_score"] * 100, 1),
                    "sentiment": round(scores["sentiment_score"] * 100, 1),
                    "manipulation": round(scores["manipulation_score"] * 100, 1),
                    "final": round(final_score * 100, 1),
                },
                "weights": weights,
                # 结构化分析（供前端显示 Gap 百分比等）
                "structuralAnalysis": {
                    "gap": {
                        "percentage": structural_gap.get("size", 0.0),
                        "type": structural_gap.get("type", "UNKNOWN"),
                        "direction": structural_gap.get("direction", "NONE"),
                    }
                },
                # 蜡烛图形态分析
                "candlestickAnalysis": candlestick_analysis,
                # 技术分析信息（ATR 等）
                "technicalAnalysis": {
                    "atr": round(float(features.get("atr", atr_value or 0.0)), 6),
                },
                # 推荐执行参数（前端 AnatomyPanel 使用）
                "recommendedExecution": {
                    "stopLoss": float(stop_loss) if stop_loss is not None else None,
                    "takeProfit": float(take_profit) if take_profit is not None else None,
                    "rewardRiskRatio": reward_risk_ratio,
                    # 杠杆先给一个保守默认值，后续可接入决策策略
                    "suggestedLeverage": 1,
                },
                # 兼容旧字段
                "structuralGap": structural_gap,
                "recommendations": {
                    "stopLoss": stop_loss,
                    "takeProfit": take_profit,
                    "riskRewardRatio": reward_risk_ratio,
                },
                "currentPrice": price_for_rr,
                "phase": features.get("phase", "UNKNOWN"),
                "phaseAge": features.get("phase_age", 0),
            }
        except Exception as e:
            print(f"[ERROR] AnatomyAnalyzer.analyze_symbol 失败: {e}")
            return {
                "symbol": symbol,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    def _get_candles(self, symbol: str, timeframe: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取 K 线数据（使用公共 API，不需要 API Key）"""
        # 使用 public_exchange（公共 API，不需要 API Key）
        exchange_to_use = self.public_exchange or self.exchange
        
        if not exchange_to_use:
            print(f"[ERROR] AnatomyAnalyzer._get_candles: Exchange 未初始化，无法获取 {symbol} 的 K 线数据")
            return []
        
        try:
            print(f"[INFO] AnatomyAnalyzer._get_candles: 开始获取 {symbol} {timeframe} K 线数据，limit={limit}")
            ohlcv = exchange_to_use.fetch_ohlcv(symbol, timeframe, limit=limit)
            print(f"[INFO] AnatomyAnalyzer._get_candles: 成功获取 {len(ohlcv)} 根 K 线")
            
            result = [
                {
                    "time": candle[0],
                    "open": candle[1],
                    "high": candle[2],
                    "low": candle[3],
                    "close": candle[4],
                    "volume": candle[5],
                }
                for candle in ohlcv
            ]
            return result
        except Exception as e:
            print(f"[ERROR] AnatomyAnalyzer._get_candles 失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _analyze_structural_gap(self, features: Dict[str, Any], candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析结构缺口（v0.5.1：修复签名 — 之前传 symbol 字符串当 current_price，恒返回 0）"""
        try:
            from v41_structure_analyzer import calculate_structure_gap  # type: ignore[import-not-found]

            # 从 features / candles 提取真实输入
            current_price = float(features.get("price") or 0.0)
            highs_1h = [float(c.get("high", 0)) for c in candles if c.get("high") is not None]
            lows_1h  = [float(c.get("low", 0))  for c in candles if c.get("low")  is not None]
            closes_1h = [float(c.get("close", 0)) for c in candles if c.get("close") is not None]

            if current_price <= 0 or not highs_1h:
                return {"size": 0.0, "type": "UNKNOWN", "direction": "UNKNOWN"}

            gap_size, gap_type = calculate_structure_gap(
                current_price=current_price,
                highs_1h=highs_1h,
                lows_1h=lows_1h,
                closes_1h=closes_1h,
            )

            return {
                "size": round(float(gap_size or 0.0) * 100, 2),
                "type": gap_type or "UNKNOWN",
                "direction": "UP" if (gap_size or 0.0) > 0 else "DOWN",
            }
        except:
            return {
                "size": 0.0,
                "type": "UNKNOWN",
                "direction": "NONE",
            }
    
    def _analyze_candlestick_patterns(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析蜡烛图形态"""
        if len(candles) < 2:
            return {"patterns": [], "signals": []}
        
        patterns = []
        signals = []
        
        # 检查最近几根 K 线
        recent = candles[-7:] if len(candles) >= 7 else candles
        
        # 黄金影线检测
        for i, candle in enumerate(recent):
            body = abs(candle["close"] - candle["open"])
            lower_wick = min(candle["open"], candle["close"]) - candle["low"]
            upper_wick = candle["high"] - max(candle["open"], candle["close"])
            
            if lower_wick > body * 2 and candle["close"] > candle["open"]:
                patterns.append("golden_wick")
                signals.append("看涨信号：黄金影线")
                break
        
        # 吞没形态检测
        if len(recent) >= 2:
            prev = recent[-2]
            curr = recent[-1]
            
            if prev["close"] < prev["open"] and curr["close"] > curr["open"]:
                if curr["open"] < prev["close"] and curr["close"] > prev["open"]:
                    patterns.append("bullish_engulfing")
                    signals.append("看涨信号：看涨吞没")
        
        return {
            "patterns": patterns,
            "signals": signals,
            "recentCandles": len(recent),
        }
    
    def _calculate_stop_loss_take_profit(
        self,
        features: Dict[str, Any],
        scores: Dict[str, Any]
    ) -> tuple[float, float]:
        """计算推荐止损和止盈"""
        price = features.get("price", 0.0)
        atr = features.get("atr", 0.0)
        phase = features.get("phase", "P1_NO_WHALE")
        
        if price == 0 or atr == 0:
            return price * 0.98, price * 1.02  # 默认 2% 止损，2% 止盈
        
        # 根据阶段调整 ATR 倍数
        if phase == "P3A_PUMP_START":
            k = 2.5
        elif phase == "P3B_PUMP_LATE":
            k = 2.0
        else:
            k = 1.5
        
        stop_loss = price - (atr * k)
        take_profit = price + (atr * k * 2)  # 盈亏比 1:2
        
        return round(stop_loss, 2), round(take_profit, 2)
    
    def get_chart_data(
        self,
        symbol: str,
        timeframe: str = "15m",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取图表数据（TradingView 格式）
        
        Args:
            symbol: 交易对
            timeframe: 时间周期
            limit: K 线数量
        
        Returns:
            TradingView 格式的 K 线数据
        """
        candles = self._get_candles(symbol, timeframe, limit)
        
        if not candles:
            print(f"[WARNING] AnatomyAnalyzer.get_chart_data: {symbol} 未获取到 K 线数据")
            return []
        
        result = []
        for candle in candles:
            # CCXT 返回的时间戳是毫秒级，TradingView 需要秒级
            timestamp = candle["time"]
            if timestamp > 1e10:  # 如果是毫秒级（> 10^10），转换为秒级
                timestamp = timestamp // 1000
            
            result.append({
                "time": int(timestamp),  # Unix 时间戳（秒）
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
            })
        
        print(f"[INFO] AnatomyAnalyzer.get_chart_data: {symbol} 返回 {len(result)} 根 K 线")
        return result


# 全局单例
_anatomy_analyzer: Optional[AnatomyAnalyzer] = None


def get_anatomy_analyzer() -> AnatomyAnalyzer:
    """获取全局 AnatomyAnalyzer 实例"""
    global _anatomy_analyzer
    if _anatomy_analyzer is None:
        _anatomy_analyzer = AnatomyAnalyzer()
    return _anatomy_analyzer

