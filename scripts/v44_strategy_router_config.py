"""
V4.4/V4.5 策略路由动态配置模块

将策略路由中的硬编码参数改为动态配置，支持从配置文件或数据库读取
"""

from typing import Dict, Any, Optional
import os
import json
from datetime import datetime, timezone

# 默认配置（硬编码的原始值）
DEFAULT_ROUTER_CONFIG = {
    # SNIPER 策略配置
    "SNIPER": {
        "min_structure_score": 60.0,  # 最低结构分要求
        "min_confidence": 0.8,  # 最低置信度
        "position_size": 1.0,  # 标准仓位
        "stop_loss_atr_multiplier": 2.0,  # 标准止损
    },
    
    # SNIFFER 策略配置（观察模式）
    "SNIFFER": {
        "enabled": False,  # 是否启用交易（V4.5 已禁用）
        "min_oi_growth": 0.05,  # OI 增长 > 5%
        "min_volume_spike": 3.0,  # 爆量 > 3x
        "min_whale_activity": 0.7,  # 庄家活动强度 > 0.7
        "position_size": 0.5,  # 轻仓试错
        "stop_loss_atr_multiplier": 3.0,  # 宽止损，防洗盘
    },
    
    # VULTURE 策略配置
    "VULTURE": {
        "min_oi_drop": -0.03,  # OI 下降 > 3%（放宽版）
        "min_score_boost": 60.0,  # 如果接近 60，自动提升到 60
        "min_score_boost_threshold": 50.0,  # 触发提升的阈值
        "position_size": 0.5,  # 轻仓（做空风险大）
        "stop_loss_atr_multiplier": 1.5,  # 极窄止损，破前高即跑
        "confidence_high_oi_drop": 0.7,  # OI 下降 > 10% 时的置信度
        "confidence_normal": 0.6,  # 正常置信度
        "high_oi_drop_threshold": 0.10,  # 高 OI 下降阈值
    },
    
    # 庄家活动强度计算权重
    "WHALE_ACTIVITY_WEIGHTS": {
        "oi_score": 0.4,  # OI 变化权重
        "volume_score": 0.3,  # 成交量权重
        "funding_score": 0.2,  # 资金费率权重
        "ls_score": 0.1,  # 多空比权重
    },
    
    # 庄家活动强度阈值
    "WHALE_ACTIVITY_THRESHOLDS": {
        "oi_max": 0.10,  # OI 上升 > 10% = 满分
        "volume_max": 3.0,  # 爆量 > 3x = 满分
        "funding_max": 0.001,  # 负费率绝对值 > 0.001 = 满分
        "ls_max": 2.0,  # LS > 2.0 = 满分
    },
    
    # Vulture 分数计算配置
    "VULTURE_SCORE": {
        "oi_contribution_max": 0.10,  # OI 下降 10% = 100分
        "structure_weight": 0.5,  # 结构分数权重（如果有）
        "oi_weight": 0.5,  # OI 贡献权重
    },
}

# 配置文件路径
CONFIG_FILE = "strategy_router_config.json"


def load_router_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载策略路由配置
    
    Args:
        config_path: 配置文件路径（默认：strategy_router_config.json）
        
    Returns:
        config: 配置字典
    """
    if config_path is None:
        config_path = CONFIG_FILE
    
    # 1. 尝试从文件加载
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = json.load(f)
                # 合并默认配置和文件配置
                config = _merge_config(DEFAULT_ROUTER_CONFIG.copy(), file_config)
                return config
        except Exception as e:
            print(f"[WARNING] 加载策略路由配置失败: {e}，使用默认配置")
    
    # 2. 尝试从环境变量加载（如果配置了）
    env_config = _load_from_env()
    if env_config:
        config = _merge_config(DEFAULT_ROUTER_CONFIG.copy(), env_config)
        return config
    
    # 3. 使用默认配置
    return DEFAULT_ROUTER_CONFIG.copy()


def save_router_config(
    config: Dict[str, Any],
    config_path: Optional[str] = None,
) -> bool:
    """
    保存策略路由配置到文件
    
    Args:
        config: 配置字典
        config_path: 配置文件路径（默认：strategy_router_config.json）
        
    Returns:
        success: 是否成功
    """
    if config_path is None:
        config_path = CONFIG_FILE
    
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERROR] 保存策略路由配置失败: {e}")
        return False


def _merge_config(default: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并配置字典"""
    result = default.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_config(result[key], value)
        else:
            result[key] = value
    return result


def _load_from_env() -> Optional[Dict[str, Any]]:
    """从环境变量加载配置"""
    config = {}
    
    # SNIPER 配置
    if os.environ.get("V44_SNIPER_MIN_STRUCTURE_SCORE"):
        try:
            if "SNIPER" not in config:
                config["SNIPER"] = {}
            config["SNIPER"]["min_structure_score"] = float(os.environ.get("V44_SNIPER_MIN_STRUCTURE_SCORE"))
        except ValueError:
            pass
    
    # VULTURE 配置
    if os.environ.get("V44_VULTURE_MIN_OI_DROP"):
        try:
            if "VULTURE" not in config:
                config["VULTURE"] = {}
            config["VULTURE"]["min_oi_drop"] = float(os.environ.get("V44_VULTURE_MIN_OI_DROP"))
        except ValueError:
            pass
    
    # SNIFFER 配置
    if os.environ.get("V44_SNIFFER_ENABLED"):
        if "SNIFFER" not in config:
            config["SNIFFER"] = {}
        config["SNIFFER"]["enabled"] = os.environ.get("V44_SNIFFER_ENABLED").lower() in ("true", "1")
    
    return config if config else None


def get_router_config() -> Dict[str, Any]:
    """
    获取策略路由配置（带缓存）
    
    Returns:
        config: 配置字典
    """
    # 使用模块级缓存
    if not hasattr(get_router_config, "_cache") or get_router_config._cache_time is None:
        get_router_config._cache = load_router_config()
        get_router_config._cache_time = datetime.now(timezone.utc)
    else:
        # 检查缓存是否过期（5分钟）
        cache_age = (datetime.now(timezone.utc) - get_router_config._cache_time).total_seconds()
        if cache_age > 300:  # 5分钟
            get_router_config._cache = load_router_config()
            get_router_config._cache_time = datetime.now(timezone.utc)
    
    return get_router_config._cache


# 初始化缓存
get_router_config._cache = None
get_router_config._cache_time = None


def clear_router_config_cache():
    """清空配置缓存（用于测试或手动刷新）"""
    get_router_config._cache = None
    get_router_config._cache_time = None


__all__ = [
    "load_router_config",
    "save_router_config",
    "get_router_config",
    "clear_router_config_cache",
    "DEFAULT_ROUTER_CONFIG",
]

