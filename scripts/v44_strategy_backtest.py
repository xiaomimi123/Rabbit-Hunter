"""
V4.4 策略回测系统

功能：
- 从 trade_scores_v43 读取 V4.4 策略数据（strategy_id 不为 null）
- 模拟交易执行（基于策略评分、side、position_size_multiplier）
- 使用历史价格数据计算盈亏
- 生成回测报告（胜率、盈亏比、最大回撤等）

用法：
  python scripts/v44_strategy_backtest.py

环境变量：
  V44_BACKTEST_DAYS=7          # 回测天数（默认 7 天）
  V44_BACKTEST_HORIZON_HOURS=24 # 持仓时间窗口（默认 24 小时）
  V44_BACKTEST_INITIAL_BALANCE=10000  # 初始余额（默认 10000 USDT）
  V44_BACKTEST_RISK_PER_TRADE=0.02    # 单笔风险百分比（默认 2%）
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal

from dotenv import load_dotenv
from supabase import Client, create_client

# 添加项目根目录到路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

load_dotenv()

# 导入策略配置（用于策略特定门槛）
try:
    from v44_strategy_config import get_strategy_threshold, check_strategy_threshold
except ImportError:
    # 如果导入失败，使用默认函数
    def get_strategy_threshold(strategy_id: str) -> float:
        return 60.0

    def check_strategy_threshold(strategy_id: str, score: float) -> tuple[bool, str]:
        min_score = get_strategy_threshold(strategy_id)
        if score >= min_score:
            return True, f"Score {score:.1f} >= {min_score:.1f} (Pass)"
        else:
            return False, f"Score {score:.1f} < {min_score:.1f} (Fail)"

# v45: 导入活的 router — 让 backtest 重新执行 route_strategy()，而不是 replay
# trade_scores_v43 里写好的 strategy_id/strategy_score（那是写入当时的 router 决定，
# 改 router/weights/threshold 在 backtest 里看不到效果）。
try:
    from v44_strategy_router import route_strategy, StrategyResult  # type: ignore
    _LIVE_ROUTER_AVAILABLE = True
except ImportError:
    route_strategy = None  # type: ignore
    StrategyResult = None  # type: ignore
    _LIVE_ROUTER_AVAILABLE = False


@dataclass
class BacktestConfig:
    """回测配置"""
    days: int = 7
    horizon_hours: int = 24
    initial_balance: float = 10000.0
    risk_per_trade: float = 0.02  # 2% 风险
    min_strategy_score: float = 60.0  # 最低策略分数（仅用于没有 strategy_id 的情况，有 strategy_id 时使用策略特定门槛）
    commission_rate: float = 0.0004  # 手续费率（0.04%）
    use_strategy_specific_thresholds: bool = True  # 是否使用策略特定门槛
    # v45：在历史 features 上**重新执行**当前 route_strategy()，让代码改动直接反映到回测。
    # False 时退回旧 "replay" 行为 — 仅当你想复现历史决策时用（例如对比 router 改动前后）。
    use_live_router: bool = True
    # v45：用 Binance 15m OHLC bar.high/low 检查 stop/TP 触发，消除"两次 snapshot 之间
    # 的 3% wick 被漏掉"的 winner bias。False 时退回旧 snapshot 路径。
    use_ohlc_for_exits: bool = True
    ohlc_interval: str = "15m"


@dataclass
class SimulatedTrade:
    """模拟交易记录"""
    symbol: str
    strategy_id: str
    side: str  # LONG or SHORT
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime]
    exit_price: Optional[float]
    quantity: float
    position_size_usdt: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    strategy_score: float
    final_score: float
    pnl_usdt: float
    pnl_percent: float
    exit_reason: str
    holding_hours: float
    # v45: 退出路径来源 ("ohlc_bar" / "snapshot" / "timeout") — 用于审计
    exit_source: str = "snapshot"


# v45: OHLC 抓取 — 用 Binance fapi/v1/klines 直接抓历史 bar，
# 替代旧的 market_snapshot 稀疏采样。bar.high/low 能捕获到 snapshot 之间的 wick。

_INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}


def _ccxt_to_binance_symbol(ccxt_symbol: str) -> str:
    """BTC/USDT → BTCUSDT。"""
    return ccxt_symbol.replace("/", "").upper()


def _active_exchange() -> str:
    """v0.5.5: 与 exchange_endpoints 一致的 active exchange 决议 — DB > env > 'okx'。"""
    try:
        try:
            from exchange_factory import get_active_exchange  # type: ignore[import-not-found]
        except ImportError:
            from scripts.exchange_factory import get_active_exchange  # type: ignore[import-not-found]
        return (get_active_exchange() or "okx").lower()
    except Exception:
        return (os.environ.get("EXCHANGE", "okx") or "okx").lower()


def _fetch_klines_range(
    binance_symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
) -> List[Dict[str, Any]]:
    """
    抓取 [start_ms, end_ms] 区间的 OHLC bars，按 active exchange 分发。
    v0.5.5：OKX 模式不再硬编码 fapi.binance.com。

    返回 [{open_time, open, high, low, close, volume}, ...]，
    失败返回 []（调用方应回退到 snapshot 模式）。
    """
    if _active_exchange() == "okx":
        return _fetch_klines_range_okx(binance_symbol, interval, start_ms, end_ms)
    return _fetch_klines_range_binance(binance_symbol, interval, start_ms, end_ms)


def _fetch_klines_range_binance(
    binance_symbol: str, interval: str, start_ms: int, end_ms: int,
) -> List[Dict[str, Any]]:
    import requests
    bars: List[Dict[str, Any]] = []
    cursor = start_ms
    bar_ms = _INTERVAL_MS.get(interval, 900_000)
    safety_loops = 0

    while cursor < end_ms and safety_loops < 20:
        safety_loops += 1
        try:
            resp = requests.get(
                "https://fapi.binance.com/fapi/v1/klines",
                params={
                    "symbol": binance_symbol, "interval": interval,
                    "startTime": cursor, "endTime": end_ms, "limit": 1500,
                },
                timeout=10,
            )
            resp.raise_for_status()
            page = resp.json()
        except Exception as e:
            print(f"  [BACKTEST] OHLC 抓取失败 (binance) {binance_symbol} {interval}: {e}")
            return []
        if not page:
            break
        for row in page:
            bars.append({
                "open_time": int(row[0]),
                "open": float(row[1]), "high": float(row[2]),
                "low":  float(row[3]), "close": float(row[4]),
                "volume": float(row[5]),
            })
        last_open = int(page[-1][0])
        next_cursor = last_open + bar_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(page) < 1500:
            break
    return bars


def _fetch_klines_range_okx(
    binance_symbol: str, interval: str, start_ms: int, end_ms: int,
) -> List[Dict[str, Any]]:
    """OKX history-candles API：按 [start, end] 拉，OKX 单次 100，需要分页。"""
    import requests
    # 复用 exchange_endpoints 的 symbol/interval mapping
    try:
        from tasks.exchange_endpoints import binance_symbol_to_okx_inst, to_okx_interval  # type: ignore[import-not-found]
    except ImportError:
        from scripts.tasks.exchange_endpoints import binance_symbol_to_okx_inst, to_okx_interval  # type: ignore[import-not-found]

    inst_id = binance_symbol_to_okx_inst(binance_symbol)
    okx_bar = to_okx_interval(interval)
    bar_ms = _INTERVAL_MS.get(interval, 900_000)

    bars: List[Dict[str, Any]] = []
    # OKX history-candles 是 "before/after" 分页 — after = 比某个 ts 之后的（更老）
    # 简单做法：往回拉一页一页直到 cursor < start_ms
    cursor_end = end_ms
    safety_loops = 0
    while cursor_end > start_ms and safety_loops < 30:
        safety_loops += 1
        try:
            resp = requests.get(
                "https://www.okx.com/api/v5/market/history-candles",
                params={
                    "instId": inst_id, "bar": okx_bar,
                    "before": str(start_ms), "after": str(cursor_end),
                    "limit": "100",
                },
                timeout=10,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != "0":
                print(f"  [BACKTEST] OKX K 线返回 code={payload.get('code')} msg={payload.get('msg')}")
                return bars
            page = payload.get("data") or []
        except Exception as e:
            print(f"  [BACKTEST] OHLC 抓取失败 (okx) {binance_symbol} {interval}: {e}")
            return bars
        if not page:
            break

        # OKX 返回最新在前；插到 bars 头部（保持 oldest→newest）
        for row in page:
            ts = int(row[0])
            if ts < start_ms:
                continue
            bars.append({
                "open_time": ts,
                "open": float(row[1]), "high": float(row[2]),
                "low":  float(row[3]), "close": float(row[4]),
                "volume": float(row[5]),
            })

        oldest_ts = int(page[-1][0])
        if oldest_ts <= cursor_end - bar_ms:
            cursor_end = oldest_ts
        else:
            break  # 防卡死
        if len(page) < 100:
            break

    # 排序成 oldest→newest
    bars.sort(key=lambda b: b["open_time"])
    return bars


def _bar_hits_exit_long(
    bar: Dict[str, Any], stop_loss: Optional[float], take_profit: Optional[float]
) -> Optional[Tuple[float, str]]:
    """LONG 持仓：bar.low 触 SL → 止损；bar.high 触 TP → 止盈。
    同一 bar 内两边都触发时，悲观假设：先触 SL（这是 backtest 的标准谨慎做法 — 真实
    分钟内顺序不可知）。"""
    if stop_loss is not None and bar["low"] <= stop_loss:
        return stop_loss, "止损"
    if take_profit is not None and bar["high"] >= take_profit:
        return take_profit, "止盈"
    return None


def _bar_hits_exit_short(
    bar: Dict[str, Any], stop_loss: Optional[float], take_profit: Optional[float]
) -> Optional[Tuple[float, str]]:
    """SHORT 持仓：bar.high 触 SL；bar.low 触 TP。同 bar 双触发时悲观假设先触 SL。"""
    if stop_loss is not None and bar["high"] >= stop_loss:
        return stop_loss, "止损"
    if take_profit is not None and bar["low"] <= take_profit:
        return take_profit, "止盈"
    return None


@dataclass
class BacktestResult:
    """回测结果"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_profit: float
    total_loss: float
    avg_profit: float
    avg_loss: float
    profit_factor: float  # 总盈利 / 总亏损
    max_profit: float
    max_loss: float
    max_drawdown: float
    sharpe_ratio: float
    final_balance: float
    total_return: float
    
    # 按策略分类
    sniffer_trades: int
    sniper_trades: int
    vulture_trades: int
    sniffer_profit: float
    sniper_profit: float
    vulture_profit: float


class V44StrategyBacktester:
    """V4.4 策略回测器"""
    
    def __init__(self, supabase: Client, config: BacktestConfig):
        self.supabase = supabase
        self.config = config
        self.trades: List[SimulatedTrade] = []
        self.account_balance = config.initial_balance
        self.peak_balance = config.initial_balance
    
    def fetch_strategy_data(self) -> List[Dict[str, Any]]:
        """从数据库获取 V4.4 策略数据"""
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=self.config.days)).isoformat()
        
        print(f"[回测] 获取最近 {self.config.days} 天的 V4.4 策略数据...")
        
        response = self.supabase.table("trade_scores_v43").select(
            "symbol, strategy_id, side, strategy_score, final_score, "
            "features, decision_policy, created_at"
        ).not_.is_("strategy_id", "null").gte("created_at", cutoff_date).order("created_at", desc=False).execute()
        
        records = response.data or []
        print(f"[回测] 获取到 {len(records)} 条策略记录")
        
        return records
    
    def get_price_history(self, symbol: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """获取价格历史数据（从多个数据源）"""
        price_history = []
        
        # 方法 1: 尝试从 market_snapshot 表获取（使用 updated_at）
        try:
            response = self.supabase.table("market_snapshot").select(
                "price, updated_at"
            ).eq("symbol", symbol).gte("updated_at", start_time.isoformat()).lte("updated_at", end_time.isoformat()).order("updated_at", desc=False).execute()
            
            if response.data:
                # 将 updated_at 映射为 created_at 以保持兼容性
                for record in response.data:
                    price_history.append({
                        "price": record.get("price"),
                        "created_at": record.get("updated_at"),  # 使用 updated_at 作为时间戳
                    })
        except Exception as e:
            pass  # 如果失败，继续尝试其他数据源
        
        # 方法 2: 如果 market_snapshot 数据不足，尝试从 ai_training_data 表获取
        if len(price_history) < 5:  # 如果数据点少于 5 个，尝试其他数据源
            try:
                response = self.supabase.table("ai_training_data").select(
                    "price, created_at"
                ).eq("symbol", symbol).gte("created_at", start_time.isoformat()).lte("created_at", end_time.isoformat()).order("created_at", desc=False).limit(100).execute()
                
                if response.data:
                    for record in response.data:
                        price_history.append({
                            "price": record.get("price"),
                            "created_at": record.get("created_at"),
                        })
            except Exception as e:
                pass  # 如果失败，继续
        
        # 去重并排序（按时间）
        if price_history:
            # 按时间排序
            price_history.sort(key=lambda x: x.get("created_at", ""))
            # 去重（相同时间的只保留一个）
            seen_times = set()
            unique_history = []
            for record in price_history:
                time_key = record.get("created_at", "")
                if time_key and time_key not in seen_times:
                    seen_times.add(time_key)
                    unique_history.append(record)
            price_history = unique_history
        
        return price_history
    
    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        position_size_multiplier: float = 1.0
    ) -> Tuple[float, float]:
        """
        计算仓位大小
        
        Returns:
            (quantity, position_size_usdt)
        """
        # 基础风险金额
        risk_amount = account_balance * self.config.risk_per_trade
        
        # 应用策略的仓位倍数
        risk_amount *= position_size_multiplier
        
        # 计算止损距离（百分比）
        stop_loss_distance = abs(entry_price - stop_loss) / entry_price
        
        # 计算仓位大小（基于风险金额和止损距离）
        position_size_usdt = risk_amount / stop_loss_distance if stop_loss_distance > 0 else 0
        
        # 限制最大仓位（不超过账户余额的 20%）
        max_position = account_balance * 0.20
        position_size_usdt = min(position_size_usdt, max_position)
        
        # 计算数量
        quantity = position_size_usdt / entry_price if entry_price > 0 else 0
        
        return quantity, position_size_usdt
    
    def simulate_trade(
        self,
        record: Dict[str, Any],
        price_history: List[Dict[str, Any]]
    ) -> Optional[SimulatedTrade]:
        """模拟单笔交易"""
        try:
            # 提取基本信息
            symbol = record.get("symbol", "")
            final_score = float(record.get("final_score", 0) or 0)

            # ── 提取 features / decision_policy（双格式：dict 或 JSON 字符串）──
            decision_policy = record.get("decision_policy", {})
            if isinstance(decision_policy, str):
                import json
                try:
                    decision_policy = json.loads(decision_policy)
                except Exception:
                    decision_policy = {}

            features = record.get("features", {})
            if isinstance(features, str):
                import json
                try:
                    features = json.loads(features)
                except Exception:
                    features = {}

            # ── v45: 重新执行 router on historical features，而不是 replay 数据库行 ──
            # 让 router/weights/threshold 改动**直接**反映到回测；之前的 replay 模式
            # 让 "改一行 router 看不到任何效果" 成为常态。
            use_live = self.config.use_live_router and _LIVE_ROUTER_AVAILABLE
            if use_live:
                # 用 trade_scores_v43 行里能拿到的字段重建 score_result
                score_result = {
                    "final_score":       record.get("final_score", 0) or 0,
                    "structure_score":   record.get("structure_score", 0) or 0,
                    "volatility_score":  record.get("volatility_score", 0) or 0,
                    "sentiment_score":   record.get("sentiment_score", 0) or 0,
                    "manipulation_score":record.get("manipulation_score", 0) or 0,
                    "block_reason":      record.get("block_reason"),
                }
                try:
                    strategy_result = route_strategy(features, score_result)  # type: ignore[misc]
                except Exception as e:
                    # router 异常 — 当作 WAIT 处理（跳过这笔）
                    print(f"  [BACKTEST] route_strategy 异常 {symbol}: {e}")
                    return None
                strategy_id = strategy_result.id
                strategy_score = float(strategy_result.score or 0)
                side = strategy_result.side
                # router 标记 WAIT/不可交易 → 跳过
                if strategy_id == "WAIT" or side == "NONE":
                    return None
            else:
                # 旧 replay 行为 — 仅在 use_live_router=False 时
                strategy_id = record.get("strategy_id", "")
                side = record.get("side", "LONG")
                strategy_score = float(record.get("strategy_score", 0) or 0)

            # ── 检查策略特定门槛 ──
            if self.config.use_strategy_specific_thresholds:
                if strategy_id and strategy_id != "WAIT":
                    passed, _ = check_strategy_threshold(strategy_id, strategy_score)
                    if not passed:
                        return None
                else:
                    if strategy_score < self.config.min_strategy_score:
                        return None
            else:
                if strategy_score < self.config.min_strategy_score:
                    return None

            # ── should_trade 检查（仅 replay 模式有意义；live router 已经隐含通过）──
            if not use_live:
                should_trade = decision_policy.get("should_trade", False)
                if not should_trade:
                    return None
            
            # 获取入场时间和价格
            created_at_str = record.get("created_at", "")
            if not created_at_str:
                return None
            
            try:
                if isinstance(created_at_str, str):
                    if created_at_str.endswith("Z"):
                        created_at_str = created_at_str[:-1] + "+00:00"
                    entry_time = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                else:
                    return None
            except Exception:
                return None
            
            # 获取入场价格（从 price_history 或 features）
            entry_price = None
            if price_history:
                # 找到最接近 entry_time 的价格
                for price_record in price_history:
                    price_time_str = price_record.get("created_at", "")
                    if price_time_str:
                        try:
                            if price_time_str.endswith("Z"):
                                price_time_str = price_time_str[:-1] + "+00:00"
                            price_time = datetime.fromisoformat(price_time_str.replace("Z", "+00:00"))
                            if price_time >= entry_time:
                                entry_price = float(price_record.get("price", 0))
                                break
                        except:
                            continue
            
            # 如果价格历史中没有，尝试从 features 获取
            if entry_price is None or entry_price <= 0:
                entry_price = features.get("current_price") or features.get("price")
                if entry_price:
                    entry_price = float(entry_price)
            
            if entry_price is None or entry_price <= 0:
                return None
            
            # 计算止损（基于 ATR 或固定百分比）
            atr = features.get("atr") or features.get("atr_1h")
            stop_loss_atr_multiplier = decision_policy.get("stop_loss_atr_multiplier", 2.0)
            
            if atr and stop_loss_atr_multiplier:
                atr_value = float(atr)
                stop_loss_distance = atr_value * float(stop_loss_atr_multiplier)
                
                if side == "LONG":
                    stop_loss = entry_price - stop_loss_distance
                else:  # SHORT
                    stop_loss = entry_price + stop_loss_distance
            else:
                # 默认止损：LONG 2%，SHORT 2%
                if side == "LONG":
                    stop_loss = entry_price * 0.98
                else:
                    stop_loss = entry_price * 1.02
            
            # 计算仓位大小
            position_size_multiplier = float(decision_policy.get("position_size_multiplier", 1.0))
            quantity, position_size_usdt = self.calculate_position_size(
                self.account_balance,
                entry_price,
                stop_loss,
                position_size_multiplier
            )
            
            if quantity <= 0:
                return None
            
            # 计算止盈（基于预期收益或固定比例）
            take_profit = None
            range_left = features.get("range_left")
            if range_left:
                range_left_value = float(range_left)
                if side == "LONG":
                    take_profit = entry_price * (1 + range_left_value)
                else:
                    take_profit = entry_price * (1 - range_left_value)
            
            # 模拟持仓和退出
            exit_time = None
            exit_price = None
            exit_reason = "未退出"
            exit_source = "snapshot"

            # 计算退出时间窗口
            horizon_end = entry_time + timedelta(hours=self.config.horizon_hours)

            # ── v45 路径 A：用 OHLC bar.high/low 精确检测触发 ────────
            # 解决旧 snapshot 路径的 winner bias：两次 snapshot 之间的 wick 会被漏掉。
            use_ohlc = self.config.use_ohlc_for_exits and (stop_loss is not None or take_profit is not None)
            if use_ohlc:
                start_ms = int(entry_time.timestamp() * 1000)
                end_ms   = int(horizon_end.timestamp() * 1000)
                bars = _fetch_klines_range(
                    _ccxt_to_binance_symbol(symbol),
                    self.config.ohlc_interval,
                    start_ms, end_ms,
                )
                for bar in bars:
                    bar_open_ts = bar["open_time"]
                    if bar_open_ts < start_ms:
                        continue  # 入场前的 bar 跳过
                    hit = (
                        _bar_hits_exit_long(bar, stop_loss, take_profit)
                        if side == "LONG"
                        else _bar_hits_exit_short(bar, stop_loss, take_profit)
                    )
                    if hit is not None:
                        exit_price, exit_reason = hit
                        # bar.open_time 是该 bar 起点；保守地把退出时间标在 bar 中点
                        exit_time = datetime.fromtimestamp(bar_open_ts / 1000, tz=timezone.utc)
                        exit_source = "ohlc_bar"
                        break
                # bars 为空 → 抓取失败 → 退回 snapshot 路径
                if not bars:
                    use_ohlc = False
                    print(f"  [BACKTEST] {symbol} OHLC 抓取为空，退回 snapshot 路径")

            # ── 路径 B：snapshot 兜底（旧逻辑）────────────────────
            if not use_ohlc and exit_time is None:
                for price_record in price_history:
                    price_time_str = price_record.get("created_at", "")
                    if not price_time_str:
                        continue

                    try:
                        if price_time_str.endswith("Z"):
                            price_time_str = price_time_str[:-1] + "+00:00"
                        price_time = datetime.fromisoformat(price_time_str.replace("Z", "+00:00"))

                        if price_time <= entry_time:
                            continue

                        if price_time > horizon_end:
                            break

                        current_price = float(price_record.get("price", 0))
                        if current_price <= 0:
                            continue

                        # 检查止损
                        if side == "LONG":
                            if current_price <= stop_loss:
                                exit_time = price_time
                                exit_price = stop_loss
                                exit_reason = "止损"
                                break
                            if take_profit and current_price >= take_profit:
                                exit_time = price_time
                                exit_price = take_profit
                                exit_reason = "止盈"
                                break
                        else:  # SHORT
                            if current_price >= stop_loss:
                                exit_time = price_time
                                exit_price = stop_loss
                                exit_reason = "止损"
                                break
                            if take_profit and current_price <= take_profit:
                                exit_time = price_time
                                exit_price = take_profit
                                exit_reason = "止盈"
                                break
                    except Exception:
                        continue
                exit_source = "snapshot"
            
            # 如果未退出，使用时间窗口结束时的价格
            if exit_time is None:
                # 找到最接近 horizon_end 的价格
                for price_record in reversed(price_history):
                    price_time_str = price_record.get("created_at", "")
                    if not price_time_str:
                        continue
                    
                    try:
                        if price_time_str.endswith("Z"):
                            price_time_str = price_time_str[:-1] + "+00:00"
                        price_time = datetime.fromisoformat(price_time_str.replace("Z", "+00:00"))
                        
                        if price_time <= horizon_end:
                            exit_time = price_time
                            exit_price = float(price_record.get("price", entry_price))
                            exit_reason = "时间窗口结束"
                            break
                    except Exception:
                        continue
            
            # 如果还是没有退出价格，使用入场价格（无盈亏）
            if exit_price is None:
                exit_price = entry_price
                exit_time = horizon_end
                exit_reason = "无价格数据"
            
            # 计算盈亏
            if side == "LONG":
                pnl_percent = (exit_price - entry_price) / entry_price
            else:  # SHORT
                pnl_percent = (entry_price - exit_price) / entry_price
            
            # 扣除手续费
            pnl_percent -= self.config.commission_rate * 2  # 开仓和平仓各一次
            
            pnl_usdt = position_size_usdt * pnl_percent
            
            # 计算持仓时间
            holding_hours = (exit_time - entry_time).total_seconds() / 3600.0 if exit_time else 0
            
            # 超时（snapshot 都没找到）→ 用 entry 价兜底，并标 timeout
            if exit_time is not None and exit_source == "snapshot" and exit_reason == "时间窗口结束":
                exit_source = "timeout"
            elif exit_price == entry_price and exit_reason == "无价格数据":
                exit_source = "timeout"

            return SimulatedTrade(
                symbol=symbol,
                strategy_id=strategy_id,
                side=side,
                entry_time=entry_time,
                entry_price=entry_price,
                exit_time=exit_time,
                exit_price=exit_price,
                quantity=quantity,
                position_size_usdt=position_size_usdt,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy_score=strategy_score,
                final_score=final_score,
                pnl_usdt=pnl_usdt,
                pnl_percent=pnl_percent,
                exit_reason=exit_reason,
                holding_hours=holding_hours,
                exit_source=exit_source,
            )
            
        except Exception as e:
            print(f"[ERROR] 模拟交易失败 ({record.get('symbol', 'UNKNOWN')}): {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def run_backtest(self) -> BacktestResult:
        """运行回测"""
        print("=" * 80)
        print("V4.4 策略回测系统")
        print("=" * 80)
        print(f"配置:")
        print(f"  - 回测天数: {self.config.days} 天")
        print(f"  - 持仓时间窗口: {self.config.horizon_hours} 小时")
        print(f"  - 初始余额: {self.config.initial_balance} USDT")
        print(f"  - 单笔风险: {self.config.risk_per_trade * 100}%")
        if self.config.use_strategy_specific_thresholds:
            print(f"  - 策略特定门槛: SNIFFER=30, SNIPER=60, VULTURE=75")
        else:
            print(f"  - 最低策略分数: {self.config.min_strategy_score}")
        print("=" * 80)
        print()
        
        # 获取策略数据
        records = self.fetch_strategy_data()
        
        if not records:
            print("[WARNING] 没有找到策略数据")
            return self._empty_result()
        
        # 按时间排序
        sorted_records = sorted(records, key=lambda x: x.get("created_at", ""))
        
        # 模拟每笔交易
        print(f"[回测] 开始模拟 {len(sorted_records)} 笔交易...")
        
        for i, record in enumerate(sorted_records):
            if (i + 1) % 10 == 0:
                print(f"[回测] 进度: {i + 1}/{len(sorted_records)}")
            
            symbol = record.get("symbol", "")
            created_at_str = record.get("created_at", "")
            
            if not created_at_str:
                continue
            
            try:
                if isinstance(created_at_str, str):
                    if created_at_str.endswith("Z"):
                        created_at_str = created_at_str[:-1] + "+00:00"
                    entry_time = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                else:
                    continue
            except Exception:
                continue
            
            # 获取价格历史
            end_time = entry_time + timedelta(hours=self.config.horizon_hours + 1)
            price_history = self.get_price_history(symbol, entry_time, end_time)
            
            # 模拟交易
            trade = self.simulate_trade(record, price_history)
            
            if trade:
                self.trades.append(trade)
                
                # 更新账户余额
                self.account_balance += trade.pnl_usdt
                
                # 更新峰值余额（用于计算最大回撤）
                if self.account_balance > self.peak_balance:
                    self.peak_balance = self.account_balance
        
        print(f"[回测] 完成！共模拟 {len(self.trades)} 笔交易")
        print()
        
        # 计算回测结果
        return self._calculate_results()
    
    def _calculate_results(self) -> BacktestResult:
        """计算回测结果"""
        if not self.trades:
            return self._empty_result()
        
        # 分类交易
        winning_trades = [t for t in self.trades if t.pnl_usdt > 0]
        losing_trades = [t for t in self.trades if t.pnl_usdt <= 0]
        
        # 按策略分类
        sniffer_trades = [t for t in self.trades if t.strategy_id == "SNIFFER"]
        sniper_trades = [t for t in self.trades if t.strategy_id == "SNIPER"]
        vulture_trades = [t for t in self.trades if t.strategy_id == "VULTURE"]
        
        # 计算统计指标
        total_profit = sum(t.pnl_usdt for t in winning_trades)
        total_loss = abs(sum(t.pnl_usdt for t in losing_trades))
        
        avg_profit = total_profit / len(winning_trades) if winning_trades else 0.0
        avg_loss = total_loss / len(losing_trades) if losing_trades else 0.0
        
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        max_profit = max(t.pnl_usdt for t in self.trades) if self.trades else 0.0
        max_loss = min(t.pnl_usdt for t in self.trades) if self.trades else 0.0
        
        # 计算最大回撤
        max_drawdown = 0.0
        running_balance = self.config.initial_balance
        peak = running_balance
        
        for trade in sorted(self.trades, key=lambda t: t.entry_time):
            running_balance += trade.pnl_usdt
            if running_balance > peak:
                peak = running_balance
            drawdown = (peak - running_balance) / peak if peak > 0 else 0.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # 计算夏普比率（简化版）
        returns = [t.pnl_percent for t in self.trades]
        if returns:
            avg_return = sum(returns) / len(returns)
            variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
            std_dev = variance ** 0.5
            sharpe_ratio = (avg_return / std_dev) * (252 ** 0.5) if std_dev > 0 else 0.0  # 年化
        else:
            sharpe_ratio = 0.0
        
        # 计算策略收益
        sniffer_profit = sum(t.pnl_usdt for t in sniffer_trades)
        sniper_profit = sum(t.pnl_usdt for t in sniper_trades)
        vulture_profit = sum(t.pnl_usdt for t in vulture_trades)
        
        total_return = (self.account_balance - self.config.initial_balance) / self.config.initial_balance
        
        return BacktestResult(
            total_trades=len(self.trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=len(winning_trades) / len(self.trades) if self.trades else 0.0,
            total_profit=total_profit,
            total_loss=total_loss,
            avg_profit=avg_profit,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_profit=max_profit,
            max_loss=max_loss,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            final_balance=self.account_balance,
            total_return=total_return,
            sniffer_trades=len(sniffer_trades),
            sniper_trades=len(sniper_trades),
            vulture_trades=len(vulture_trades),
            sniffer_profit=sniffer_profit,
            sniper_profit=sniper_profit,
            vulture_profit=vulture_profit,
        )
    
    def _empty_result(self) -> BacktestResult:
        """返回空结果"""
        return BacktestResult(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            total_profit=0.0,
            total_loss=0.0,
            avg_profit=0.0,
            avg_loss=0.0,
            profit_factor=0.0,
            max_profit=0.0,
            max_loss=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            final_balance=self.config.initial_balance,
            total_return=0.0,
            sniffer_trades=0,
            sniper_trades=0,
            vulture_trades=0,
            sniffer_profit=0.0,
            sniper_profit=0.0,
            vulture_profit=0.0,
        )
    
    def print_report(self, result: BacktestResult):
        """打印回测报告"""
        print("=" * 80)
        print("V4.4 策略回测报告")
        print("=" * 80)
        print()
        
        print("📊 总体表现")
        print("-" * 80)
        print(f"  总交易数: {result.total_trades}")
        print(f"  盈利交易: {result.winning_trades} ({result.win_rate * 100:.1f}%)")
        print(f"  亏损交易: {result.losing_trades} ({100 - result.win_rate * 100:.1f}%)")
        print(f"  初始余额: {self.config.initial_balance:,.2f} USDT")
        print(f"  最终余额: {result.final_balance:,.2f} USDT")
        print(f"  总收益率: {result.total_return * 100:.2f}%")
        print()
        
        print("💰 盈亏统计")
        print("-" * 80)
        print(f"  总盈利: {result.total_profit:,.2f} USDT")
        print(f"  总亏损: {result.total_loss:,.2f} USDT")
        print(f"  平均盈利: {result.avg_profit:,.2f} USDT")
        print(f"  平均亏损: {result.avg_loss:,.2f} USDT")
        print(f"  盈亏比: {result.profit_factor:.2f}")
        print(f"  最大盈利: {result.max_profit:,.2f} USDT")
        print(f"  最大亏损: {result.max_loss:,.2f} USDT")
        print()
        
        print("📉 风险指标")
        print("-" * 80)
        print(f"  最大回撤: {result.max_drawdown * 100:.2f}%")
        print(f"  夏普比率: {result.sharpe_ratio:.2f}")
        print()
        
        print("🎯 策略表现")
        print("-" * 80)
        print(f"  SNIFFER (P2 潜伏):")
        print(f"    交易数: {result.sniffer_trades}")
        print(f"    总收益: {result.sniffer_profit:,.2f} USDT")
        if result.sniffer_trades > 0:
            print(f"    平均收益: {result.sniffer_profit / result.sniffer_trades:,.2f} USDT/笔")
        print()
        print(f"  SNIPER (P3A 狙击):")
        print(f"    交易数: {result.sniper_trades}")
        print(f"    总收益: {result.sniper_profit:,.2f} USDT")
        if result.sniper_trades > 0:
            print(f"    平均收益: {result.sniper_profit / result.sniper_trades:,.2f} USDT/笔")
        print()
        print(f"  VULTURE (P3B/P4 做空):")
        print(f"    交易数: {result.vulture_trades}")
        print(f"    总收益: {result.vulture_profit:,.2f} USDT")
        if result.vulture_trades > 0:
            print(f"    平均收益: {result.vulture_profit / result.vulture_trades:,.2f} USDT/笔")
        print()
        
        print("=" * 80)


def main():
    """主函数"""
    try:
        # 初始化 Supabase
        SUPABASE_URL = os.environ.get("SUPABASE_URL")
        SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
        
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("[ERROR] Please configure SUPABASE_URL and SUPABASE_KEY in .env file")
            print("[ERROR] Missing SUPABASE_URL or SUPABASE_KEY")
            sys.exit(1)
    
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # 读取配置
        use_strategy_thresholds = os.environ.get("V44_BACKTEST_USE_STRATEGY_THRESHOLDS", "1") in ("1", "true", "True")
        config = BacktestConfig(
            days=int(os.environ.get("V44_BACKTEST_DAYS", "7")),
            horizon_hours=int(os.environ.get("V44_BACKTEST_HORIZON_HOURS", "24")),
            initial_balance=float(os.environ.get("V44_BACKTEST_INITIAL_BALANCE", "10000")),
            risk_per_trade=float(os.environ.get("V44_BACKTEST_RISK_PER_TRADE", "0.02")),
            min_strategy_score=float(os.environ.get("V44_BACKTEST_MIN_SCORE", "60")),
            use_strategy_specific_thresholds=use_strategy_thresholds,
        )
        
        # 创建回测器
        backtester = V44StrategyBacktester(supabase, config)
        
        # 运行回测
        result = backtester.run_backtest()
        
        # 打印报告
        backtester.print_report(result)
    except KeyboardInterrupt:
        print("\n[INFO] Backtest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] Backtest failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

