"""
统一配置管理模块

所有环境变量读取集中在此处，提供全局单例 get_config()。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TradingConfig:
    # ── Supabase ─────────────────────────────────────────────
    supabase_url: str = ""
    supabase_key: str = ""

    # ── Binance ──────────────────────────────────────────────
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = False
    binance_leverage: int = 10

    # ── V4.3 策略 ─────────────────────────────────────────────
    v43_enabled: bool = True
    v43_trade_threshold: float = 0.6
    v43_risk_per_trade: float = 0.01

    # ── V4.4 策略路由 ─────────────────────────────────────────
    v44_enabled: bool = False
    v44_position_size_multiplier: float = 1.0

    # ── AI 判断 ──────────────────────────────────────────────
    deepseek_enabled: bool = False
    ai_judge_enabled: bool = False

    # ── 自动交易 ─────────────────────────────────────────────
    enable_auto_trading: bool = False

    # ── 失败安全（fail-closed by default） ───────────────────
    # AI 决策层不可用/超时/异常时，是否仍然放行交易（默认 False = 拒绝）
    ai_fail_open: bool = False
    # SL/TP 下单失败时，是否仍然保留刚开的仓位（默认 False = 立即平仓回滚）
    sl_tp_fail_open: bool = False

    # ── SHORT 路径暂停（v45 临时止血） ────────────────────────
    # 默认禁用 SHORT 入场。VULTURE 策略 + chandelier_stop 的 SHORT 数学和
    # positions_v43 的 lowest_price 字段尚未端到端打通，强行交易会得到错误的
    # 止损位（实际等于没有止损）。系统性重写完成后再开启。
    # 开关只影响**新的** SHORT 入场；已有 OPEN SHORT 仓位继续按旧逻辑管理。
    enable_short_trading: bool = False

    # ── 采集参数 ─────────────────────────────────────────────
    scan_interval: float = 1.0
    write_queue_maxsize: int = 500
    write_workers: int = 2
    deep_scan_interval_seconds: int = 60
    store_top_count: int = 20
    # MarketScanner 最低 24h 成交额(USDT)。过低会让微价 meme 币霸榜,
    # 过高会漏掉新上线的中小盘。30M 是平衡点。
    min_volume_24h_usdt: float = 30_000_000.0

    def validate(self) -> List[str]:
        """返回配置问题列表（空列表表示配置无误）"""
        issues: List[str] = []
        if not self.supabase_url:
            issues.append("SUPABASE_URL 未设置")
        if not self.supabase_key:
            issues.append("SUPABASE_KEY 未设置")
        if self.enable_auto_trading:
            if not self.binance_api_key:
                issues.append("enable_auto_trading=True 但 BINANCE_API_KEY 未设置")
            if not self.binance_api_secret:
                issues.append("enable_auto_trading=True 但 BINANCE_API_SECRET 未设置")
        if self.v43_risk_per_trade <= 0 or self.v43_risk_per_trade > 0.1:
            issues.append(f"V43_RISK_PER_TRADE={self.v43_risk_per_trade} 超出合理范围 (0, 0.1]")
        return issues


def _load_from_env() -> TradingConfig:
    """从环境变量构建 TradingConfig"""
    return TradingConfig(
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_key=os.environ.get("SUPABASE_KEY", "") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        binance_api_key=os.environ.get("BINANCE_API_KEY", ""),
        binance_api_secret=os.environ.get("BINANCE_API_SECRET", ""),
        binance_testnet=os.environ.get("BINANCE_TESTNET", "false").lower() in ("1", "true"),
        binance_leverage=int(os.environ.get("BINANCE_LEVERAGE", "10")),
        v43_enabled=os.environ.get("V43_ENABLED", "1") in ("1", "true", "True"),
        v43_trade_threshold=float(os.environ.get("V43_TRADE_THRESHOLD", "0.6")),
        v43_risk_per_trade=float(os.environ.get("V43_RISK_PER_TRADE", "0.01")),
        v44_enabled=os.environ.get("V44_ENABLED", "0") in ("1", "true", "True"),
        v44_position_size_multiplier=float(os.environ.get("V44_POSITION_SIZE_MULTIPLIER", "1.0")),
        deepseek_enabled=os.environ.get("DEEPSEEK_ENABLED", "0") in ("1", "true", "True"),
        ai_judge_enabled=os.environ.get("AI_JUDGE_ENABLED", "0") in ("1", "true", "True"),
        enable_auto_trading=os.environ.get("ENABLE_AUTO_TRADING", "false").lower() in ("1", "true"),
        ai_fail_open=os.environ.get("AI_FAIL_OPEN", "false").lower() in ("1", "true"),
        sl_tp_fail_open=os.environ.get("SL_TP_FAIL_OPEN", "false").lower() in ("1", "true"),
        enable_short_trading=os.environ.get("ENABLE_SHORT_TRADING", "false").lower() in ("1", "true"),
        scan_interval=float(os.environ.get("SCAN_INTERVAL", "1.0")),
        write_queue_maxsize=int(os.environ.get("WRITE_QUEUE_MAXSIZE", "500")),
        write_workers=int(os.environ.get("WRITE_WORKERS", "2")),
        deep_scan_interval_seconds=int(os.environ.get("DEEP_SCAN_INTERVAL_SECONDS", "60")),
        store_top_count=int(os.environ.get("STORE_TOP_COUNT", "20")),
        min_volume_24h_usdt=float(os.environ.get("MIN_VOLUME_24H_USDT", "30000000")),
    )


_config_instance: Optional[TradingConfig] = None


def get_config(reload: bool = False) -> TradingConfig:
    """
    返回全局单例 TradingConfig。

    Args:
        reload: 为 True 时强制从环境变量重新加载（用于热加载场景）
    """
    global _config_instance
    if _config_instance is None or reload:
        _config_instance = _load_from_env()
    return _config_instance
