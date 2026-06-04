"""
持仓业务逻辑服务

包含 PnL 计算、持仓格式化等逻辑（从 routes/positions.py 提取）。
"""

from typing import Optional, Dict, Any, List


def calculate_pnl(
    current_price: Optional[float],
    entry_price: Optional[float],
    position_size: Optional[float],
    side: Optional[str],
) -> tuple[Optional[float], Optional[float]]:
    """
    计算持仓盈亏（绝对值和百分比）。

    :return: (pnl, pnl_percent) — 任何输入为 None 时均返回 (None, None)
    """
    if current_price and entry_price and position_size:
        if side == "LONG":
            pnl = (current_price - entry_price) * position_size
            pnl_percent = ((current_price - entry_price) / entry_price) * 100
        elif side == "SHORT":
            pnl = (entry_price - current_price) * position_size
            pnl_percent = ((entry_price - current_price) / entry_price) * 100
        else:
            return None, None
        return pnl, pnl_percent
    return None, None


def estimate_stop_price(
    record: Dict[str, Any],
    current_price: Optional[float],
) -> Optional[float]:
    """
    若记录中没有明确的止损价格，则根据 ATR 参数估算止损价。
    """
    stop_price = record.get("stop_price")
    if not stop_price and record.get("atr_k") and current_price:
        atr_k = float(record.get("atr_k", 2.0))
        estimated_atr = current_price * 0.02
        side = record.get("side")
        if side == "LONG":
            stop_price = current_price - (estimated_atr * atr_k)
        else:
            stop_price = current_price + (estimated_atr * atr_k)
    return stop_price


def calculate_take_profit(
    entry_price: Optional[float],
    stop_price: Optional[float],
    side: Optional[str],
    rr_ratio: float = 2.0,
) -> Optional[float]:
    """
    根据风险收益比计算止盈价（默认 2:1）。
    """
    if entry_price and stop_price:
        if side == "LONG":
            risk = entry_price - stop_price
            return entry_price + (risk * rr_ratio)
        elif side == "SHORT":
            risk = stop_price - entry_price
            return entry_price - (risk * rr_ratio)
    return None


def determine_position_status(
    current_price: Optional[float],
    stop_price: Optional[float],
    side: Optional[str],
    danger_threshold: float = 1.05,
) -> str:
    """
    确定持仓风险状态（"SAFE" 或 "DANGER"）。

    距离止损 5% 以内视为 DANGER。
    """
    if stop_price and current_price:
        if side == "LONG" and current_price <= stop_price * danger_threshold:
            return "DANGER"
        if side == "SHORT" and current_price >= stop_price * danger_threshold:
            return "DANGER"
    return "SAFE"


def format_position(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    将数据库原始记录格式化为前端期望的持仓格式。
    """
    current_price = record.get("current_price")
    entry_price = record.get("entry_price")
    side = record.get("side")
    position_size = record.get("position_size")

    pnl, pnl_percent = calculate_pnl(current_price, entry_price, position_size, side)

    stop_price = estimate_stop_price(record, current_price)

    take_profit = calculate_take_profit(entry_price, stop_price, side)

    status_str = determine_position_status(current_price, stop_price, side)

    return {
        # 前端期望的字段名（驼峰命名）
        "symbol": record.get("symbol", ""),
        "entryPrice": float(record.get("entry_price", 0)),
        "currentPrice": float(current_price) if current_price else float(record.get("entry_price", 0)),
        "atrStop": float(stop_price) if stop_price else float(record.get("entry_price", 0) * 0.95),
        "takeProfit": float(take_profit) if take_profit else None,
        "leverage": float(record.get("leverage", 1)) if record.get("leverage") else 1.0,
        "size": float(record.get("position_size", 0)),
        "pnl": float(pnl) if pnl is not None else 0.0,
        "pnlPercent": float(pnl_percent) if pnl_percent is not None else 0.0,
        "status": status_str,
        "side": record.get("side", "LONG"),
        # 保留原始字段供兼容
        "id": record.get("id"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "entry_price": float(record.get("entry_price", 0)),
        "current_price": float(current_price) if current_price else None,
        "position_size": float(record.get("position_size", 0)),
        "stop_price": float(stop_price) if stop_price else None,
        "atr_k": float(record.get("atr_k")) if record.get("atr_k") else None,
        "phase": record.get("phase"),
        "phase_age": record.get("phase_age"),
    }


def format_positions(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """批量格式化持仓记录。"""
    return [format_position(r) for r in records]
