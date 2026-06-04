"""
CVD (Cumulative Volume Delta，累计成交量差) 分析模块

核心目标：
- 计算整体多空差：主动买入量 - 主动卖出量
- 计算买方优势比：主动买入量 / 总成交量
- 计算庄家多空差（Whale CVD）：大额主动成交的多空差

注意事项（工程级约束）：
- `fetch_trades` 是高权重接口，严禁对所有币种高频轮询。
- 建议只对通过第一层漏斗筛选出来的 Top N 候选币种计算 CVD。
- 调用频率建议控制在 15s - 60s 一次。
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_fixed


class CVDAnalyzer:
    """
    CVD 分析器

    参数:
    - exchange: ccxt 交易所实例（推荐 async 版本，需实现 fetch_trades）
    """

    def __init__(self, exchange: Any) -> None:
        self.exchange = exchange

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def fetch_recent_trades(self, symbol: str, limit: int = 1000) -> list[dict]:
        """
        获取最近的逐笔成交数据。

        注意：
        - 这是一个高权重接口，不要每秒都调，建议 15s-60s 调一次。
        - fetch_trades 获取的是公共成交历史。
        """
        # 一些 ccxt 版本是同步接口，这里做一次兼容处理
        try:
            if asyncio.iscoroutinefunction(self.exchange.fetch_trades):
                trades = await self.exchange.fetch_trades(symbol, limit=limit)
            else:
                # 在异步环境中执行同步方法
                loop = asyncio.get_running_loop()
                trades = await loop.run_in_executor(
                    None, lambda: self.exchange.fetch_trades(symbol, limit=limit)
                )
            return trades or []
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] 获取成交数据失败 {symbol}: {e}")
            return []

    async def calculate_cvd_metrics(
        self,
        symbol: str,
        limit: int = 1000,
        whale_value_threshold: Optional[float] = None,
    ) -> Optional[Dict[str, float]]:
        """
        计算 CVD 核心指标。

        返回:
        - cvd_15m / cvd_1h: 按时间窗口聚合的净成交量
        - buy_ratio_15m / buy_ratio_1h: 时间窗口内主动买入占比
        - whale_cvd_15m / whale_cvd_1h: 时间窗口内大单多空差
        - cvd_volume / buy_ratio / whale_cvd: 为兼容旧逻辑，默认映射到 15m 窗口
        - total_volume: 当前抓取样本总成交量（非窗口）
        - whale_threshold: 判定大单的金额阈值
        """
        try:
            trades = await self.fetch_recent_trades(symbol, limit)

            if not trades:
                return None

            df = pd.DataFrame(trades)

            # 确保必要字段存在
            if (
                "side" not in df.columns
                or "amount" not in df.columns
                or "price" not in df.columns
                or "timestamp" not in df.columns
            ):
                print(f"[WARN] 逐笔成交数据缺少必要字段，无法计算 CVD: {symbol}")
                return None

            # 统一类型
            df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
            df = df.dropna(subset=["timestamp"])
            if df.empty:
                return None

            # --- 核心算法：判断主动方向 ---
            # ccxt 统一了 'side' 字段：
            # side='buy'  -> Taker Buy (主动买入，庄家吃货)
            # side='sell' -> Taker Sell (主动卖出，庄家砸盘)

            # (进阶) 大单过滤
            # 默认阈值：price * 1000 ≈ 1000 个币的价值（粗略动态阈值）
            df["value"] = df["price"] * df["amount"]

            if whale_value_threshold is None:
                # 使用最近成交价格近似当前价
                try:
                    current_price = float(df["price"].iloc[-1])
                except Exception:  # noqa: BLE001
                    current_price = 0.0
                whale_threshold = current_price * 1000 if current_price > 0 else 10_000.0
            else:
                whale_threshold = float(whale_value_threshold)

            def _calc_window(window_df: pd.DataFrame) -> tuple[float, float, float]:
                """返回 (cvd, buy_ratio, whale_cvd)"""
                if window_df.empty:
                    return 0.0, 0.5, 0.0

                buy_trades = window_df[window_df["side"] == "buy"]
                sell_trades = window_df[window_df["side"] == "sell"]

                buy_vol = float(buy_trades["amount"].sum())
                sell_vol = float(sell_trades["amount"].sum())
                total_vol = buy_vol + sell_vol

                cvd = buy_vol - sell_vol
                ratio = buy_vol / total_vol if total_vol > 0 else 0.5

                whale_df = window_df[window_df["value"] > whale_threshold]
                whale_buy_vol = float(whale_df[whale_df["side"] == "buy"]["amount"].sum())
                whale_sell_vol = float(whale_df[whale_df["side"] == "sell"]["amount"].sum())
                whale_cvd = whale_buy_vol - whale_sell_vol

                return cvd, ratio, whale_cvd

            end_ts = float(df["timestamp"].max())
            ts_15m = end_ts - 15 * 60 * 1000
            ts_1h = end_ts - 60 * 60 * 1000

            df_15m = df[df["timestamp"] >= ts_15m]
            df_1h = df[df["timestamp"] >= ts_1h]

            cvd_15m, buy_ratio_15m, whale_cvd_15m = _calc_window(df_15m)
            cvd_1h, buy_ratio_1h, whale_cvd_1h = _calc_window(df_1h)

            # 样本总量（非窗口）
            all_buy = float(df[df["side"] == "buy"]["amount"].sum())
            all_sell = float(df[df["side"] == "sell"]["amount"].sum())
            total_vol_all = float(all_buy + all_sell)

            # 兼容旧逻辑：默认使用 15m 作为“当前”cvd
            return {
                "symbol": symbol,
                # v4: windowed
                "cvd_15m": float(cvd_15m),
                "cvd_1h": float(cvd_1h),
                "buy_ratio_15m": float(buy_ratio_15m),
                "buy_ratio_1h": float(buy_ratio_1h),
                "whale_cvd_15m": float(whale_cvd_15m),
                "whale_cvd_1h": float(whale_cvd_1h),
                # legacy-compatible
                "cvd_volume": float(cvd_15m),
                "buy_ratio": float(buy_ratio_15m),
                "whale_cvd": float(whale_cvd_15m),
                # meta
                "total_volume": float(total_vol_all),
                "whale_threshold": float(whale_threshold),
                "end_ts": float(end_ts),
            }

        except Exception as e:  # noqa: BLE001
            print(f"❌ [CVD] 计算失败 {symbol}: {e}")
            return None

    def analyze_cvd_intent(self, price_trend: float, cvd_data: Optional[Dict[str, float]]) -> str:
        """
        解读 CVD 与价格的关系 (4.0 核心)

        返回:
        - 'ACCUMULATION'  吸筹 (P2)
        - 'DISTRIBUTION'  派发 (P4)
        - 'PUMP_CONFIRMED' 真拉盘 (P3a)
        - 'NORMAL'         正常
        - 'UNKNOWN'        数据不足
        """
        if not cvd_data:
            return "UNKNOWN"

        cvd = cvd_data.get("cvd_volume", 0.0)
        whale_cvd = cvd_data.get("whale_cvd", 0.0)

        # 🎯 场景一：吸筹 (Accumulation) - P2 阶段
        # 价格横盘/微跌 + 庄家大单在买 (Whale CVD > 0)
        if abs(price_trend) < 0.005 and whale_cvd > 50_000:
            return "ACCUMULATION"

        # 🎯 场景二：出货 (Distribution) - P4 阶段
        # 价格在涨/横盘 + 庄家大单在卖 (Whale CVD < 0)
        if price_trend > 0 and whale_cvd < -50_000:
            return "DISTRIBUTION"

        # 🎯 场景三：真拉盘 (Real Pump) - P3a 阶段
        # 价格涨 + 散户和庄家都在买 (CVD 全正)
        if price_trend > 0.01 and cvd > 0 and whale_cvd > 0:
            return "PUMP_CONFIRMED"

        return "NORMAL"


__all__ = ["CVDAnalyzer"]


