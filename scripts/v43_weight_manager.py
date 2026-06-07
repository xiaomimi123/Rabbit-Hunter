"""
V4.3 权重管理模块

管理 AI 可调整的权重：
- 权重加载/保存
- 权重验证（确保在约束范围内）
- 权重历史记录（文件 + 数据库）
"""

import json
import os
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path


# 默认权重
DEFAULT_WEIGHTS = {
    "structure": 0.35,
    "volatility": 0.25,
    "sentiment": 0.25,
    "manipulation": 0.15,
    "version": "v4.3.0",
}

# 硬约束：AI 不能修改的权重范围
WEIGHT_CONSTRAINTS = {
    "structure": (0.25, 0.50),      # 结构权重 >= 25%
    "volatility": (0.15, 0.35),     # 波动率权重 >= 15%
    "sentiment": (0.15, 0.35),      # 情绪权重 >= 15%
    "manipulation": (0.10, 0.25),   # 操控权重 >= 10%
}


def load_weights(config_path: Optional[str] = None) -> Dict[str, float]:
    """
    加载权重配置
    
    Args:
        config_path: 配置文件路径（默认：strategy_config.json）
    
    Returns:
        weights: 权重字典
    """
    if config_path is None:
        config_path = "strategy_config.json"
    
    # 如果文件不存在，返回默认权重
    if not os.path.exists(config_path):
        return DEFAULT_WEIGHTS.copy()
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # 从配置中提取 V4.3 权重
        v43_weights = config.get("v43_weights", {})
        
        # 合并默认权重
        weights = DEFAULT_WEIGHTS.copy()
        weights.update(v43_weights)
        
        return weights
    except Exception as e:
        print(f"[WARNING] 加载权重配置失败: {e}，使用默认权重")
        return DEFAULT_WEIGHTS.copy()


def save_weights(
    weights: Dict[str, float], 
    config_path: Optional[str] = None,
    save_to_database: bool = False,
    supabase_client: Optional[Any] = None,
    performance_metrics: Optional[Dict[str, Any]] = None,
    opportunity_density_score: Optional[float] = None,
    ai_reason: Optional[str] = None,
    applied: bool = False,
) -> bool:
    """
    保存权重配置（文件 + 可选数据库）
    
    Args:
        weights: 权重字典
        config_path: 配置文件路径（默认：strategy_config.json）
        save_to_database: 是否同时保存到数据库
        supabase_client: Supabase 客户端（如果 save_to_database=True 则必需）
        performance_metrics: 性能指标（可选，用于数据库记录）
        opportunity_density_score: 机会密度分数（可选，用于数据库记录）
        ai_reason: AI 调整理由（可选，用于数据库记录）
        applied: 是否已应用（用于数据库记录）
    
    Returns:
        success: 是否成功
    """
    if config_path is None:
        config_path = "strategy_config.json"
    
    # 1. 保存到文件
    file_success = False
    try:
        # 读取现有配置（如果存在）
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        else:
            config = {}
        
        # 更新 V4.3 权重
        config["v43_weights"] = weights
        
        # 保存配置
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        file_success = True
    except Exception as e:
        print(f"[ERROR] 保存权重配置到文件失败: {e}")
    
    # 2. 保存到数据库（如果启用）
    db_success = True
    if save_to_database:
        db_success = save_weights_to_database(
            weights=weights,
            weights_version=weights.get("version", "v4.3.0"),
            performance_metrics=performance_metrics,
            opportunity_density_score=opportunity_density_score,
            ai_reason=ai_reason,
            applied=applied,
            supabase=supabase_client,
        )
    
    return file_success and db_success


def save_weights_to_database(
    weights: Dict[str, float],
    weights_version: str,
    performance_metrics: Optional[Dict[str, Any]] = None,
    opportunity_density_score: Optional[float] = None,
    ai_reason: Optional[str] = None,
    applied: bool = False,
    supabase: Optional[Any] = None,
) -> bool:
    """
    保存权重到数据库（ai_weights_v43 表）
    
    Args:
        weights: 权重字典
        weights_version: 权重版本号
        performance_metrics: 性能指标（可选）
        opportunity_density_score: 机会密度分数（可选）
        ai_reason: AI 调整理由（可选）
        applied: 是否已应用
        supabase: Supabase 客户端（如果为 None，则尝试从环境变量初始化）
    
    Returns:
        success: 是否成功
    """
    # 尝试获取 Supabase 客户端
    if supabase is None:
        try:
            import os
            from supabase import create_client
            SUPABASE_URL = os.environ.get("SUPABASE_URL")
            SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
            if not SUPABASE_URL or not SUPABASE_KEY:
                print("[WARNING] Supabase 未配置，无法保存权重到数据库")
                return False
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        except ImportError:
            print("[WARNING] 无法导入 supabase 模块，无法保存权重到数据库")
            return False
        except Exception as e:
            print(f"[WARNING] 初始化 Supabase 客户端失败: {e}")
            return False
    
    try:
        # 构建数据库行
        row = {
            "weights": weights,
            "weights_version": weights_version,
            "performance_metrics": performance_metrics or {},
            "opportunity_density_score": opportunity_density_score,
            "ai_reason": ai_reason,
            "applied": applied,
        }
        
        # 插入数据库
        response = supabase.table("ai_weights_v43").insert(row).execute()
        
        if response.data:
            print(f"[INFO] ✅ 权重已保存到数据库: {weights_version}")
            return True
        else:
            print(f"[WARNING] 权重保存到数据库返回空响应")
            return False
            
    except Exception as e:
        print(f"[ERROR] 保存权重到数据库失败: {e}")
        return False


def validate_weights(weights: Dict[str, float]) -> tuple[bool, str]:
    """
    验证权重是否在约束范围内
    
    Args:
        weights: 权重字典
    
    Returns:
        (valid, reason)
        - valid=True: 权重有效
        - valid=False: 权重无效，reason 说明原因
    """
    # 检查必需字段
    required_fields = ["structure", "volatility", "sentiment", "manipulation"]
    for field in required_fields:
        if field not in weights:
            return (False, f"缺少必需字段: {field}")
    
    # 检查权重范围
    for field, (min_val, max_val) in WEIGHT_CONSTRAINTS.items():
        value = weights.get(field, 0.0)
        if value < min_val or value > max_val:
            return (False, f"{field} 权重 {value} 超出范围 [{min_val}, {max_val}]")
    
    # 检查权重总和（应该接近 1.0，允许一定误差）
    total = sum(weights.get(field, 0.0) for field in required_fields)
    if abs(total - 1.0) > 0.01:
        return (False, f"权重总和 {total} 不等于 1.0")
    
    return (True, "")


def get_next_version(current_version: str = "v4.3.0") -> str:
    """
    获取下一个版本号
    
    Args:
        current_version: 当前版本号（例如 "v4.3.0"）
    
    Returns:
        next_version: 下一个版本号（例如 "v4.3.1"）
    """
    try:
        # 解析版本号
        parts = current_version.replace("v", "").split(".")
        if len(parts) >= 3:
            patch = int(parts[2])
            return f"v{parts[0]}.{parts[1]}.{patch + 1}"
    except Exception:
        pass
    
    # 如果解析失败，返回默认递增版本
    return "v4.3.1"


# v0.5.1 兼容 wrapper：旧代码 import `get_current_weights`，本模块实际只导出
# `load_weights`。Review 期间这条 import 在 5 个位置 ImportError，把
# AnatomyPanel / EntryValidator / KillQueueManager 全砸了。提供 alias 接通：
def get_current_weights() -> Dict[str, float]:
    """Compat alias — equivalent to load_weights() with default config path.

    Provided so that pre-existing callers (anatomy / entry_validator / kill_queue)
    keep working without per-site rewrites. Prefer load_weights() in new code.
    """
    return load_weights()


__all__ = [
    "load_weights",
    "save_weights",
    "save_weights_to_database",
    "validate_weights",
    "get_next_version",
    "get_current_weights",
    "DEFAULT_WEIGHTS",
    "WEIGHT_CONSTRAINTS",
]

