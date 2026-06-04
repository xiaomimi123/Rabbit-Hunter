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
            strategy_id = record.get("strategy_id", "")
            side = record.get("side", "LONG")
            strategy_score = float(record.get("strategy_score", 0) or 0)
            final_score = float(record.get("final_score", 0) or 0)
            
            # 检查策略特定门槛（使用新的配置）
            if self.config.use_strategy_specific_thresholds:
                # 如果 strategy_id 存在，使用策略特定门槛；否则使用默认门槛
                if strategy_id and strategy_id != "WAIT":
                    min_score = get_strategy_threshold(strategy_id)
                    passed, threshold_msg = check_strategy_threshold(strategy_id, strategy_score)
                    if not passed:
                        # 分数不够，跳过这笔交易
                        return None
                else:
                    # 如果没有 strategy_id，使用默认门槛（向后兼容）
                    if strategy_score < self.config.min_strategy_score:
                        return None
            else:
                # 使用统一门槛（旧逻辑）
                if strategy_score < self.config.min_strategy_score:
                    return None
            
            # 提取决策信息
            decision_policy = record.get("decision_policy", {})
            if isinstance(decision_policy, str):
                import json
                try:
                    decision_policy = json.loads(decision_policy)
                except:
                    decision_policy = {}
            
            # 检查是否允许交易
            should_trade = decision_policy.get("should_trade", False)
            if not should_trade:
                return None
            
            # 提取特征
            features = record.get("features", {})
            if isinstance(features, str):
                import json
                try:
                    features = json.loads(features)
                except:
                    features = {}
            
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
            
            # 计算退出时间窗口
            horizon_end = entry_time + timedelta(hours=self.config.horizon_hours)
            
            # 在价格历史中查找退出点
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
                holding_hours=holding_hours
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

