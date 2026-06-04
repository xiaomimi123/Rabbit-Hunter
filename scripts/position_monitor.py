"""
持仓监控模块

功能：
1. 记录持仓历史
2. 监控持仓风险（结合市场状态）
3. 生成风险警报
"""

import os
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client, Client

# 导入持仓查询模块
from scripts.binance_positions import get_positions

# 载入环境变量
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def init_supabase() -> Optional[Client]:
    """初始化 Supabase 客户端。"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[WARNING] 未配置 Supabase，无法记录持仓历史")
        return None

    try:
        client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return client
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] Supabase 初始化失败: {e}")
        return None


def get_market_risk(supabase: Client, symbol: str) -> dict:
    """
    从 market_snapshot 表获取币种的市场风险信息
    
    返回: {
        "risk_score": int,
        "risk_level": str,
        "regime": str
    }
    """
    try:
        response = (
            supabase.table("market_snapshot")
            .select("risk_score, risk_level, regime")
            .eq("symbol", symbol)
            .execute()
        )

        if response.data and len(response.data) > 0:
            data = response.data[0]
            return {
                "risk_score": data.get("risk_score", 0),
                "risk_level": data.get("risk_level", "UNKNOWN"),
                "regime": data.get("regime", "UNKNOWN"),
            }
        return {
            "risk_score": 0,
            "risk_level": "UNKNOWN",
            "regime": "UNKNOWN",
        }
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] 获取 {symbol} 市场风险失败: {e}")
        return {
            "risk_score": 0,
            "risk_level": "UNKNOWN",
            "regime": "UNKNOWN",
        }


def calculate_liquidation_distance(
    entry_price: float, liquidation_price: float, size: float
) -> Optional[float]:
    """
    计算距离强平价格的距离（百分比）
    
    返回: 距离百分比（正数=安全，负数=危险）
    """
    if liquidation_price == 0 or entry_price == 0:
        return None

    if size > 0:  # 多单
        # 多单：价格下跌到强平价格
        distance = ((entry_price - liquidation_price) / entry_price) * 100
    else:  # 空单
        # 空单：价格上涨到强平价格
        distance = ((liquidation_price - entry_price) / entry_price) * 100

    return distance


def record_position_history(supabase: Client, positions: list[dict]) -> None:
    """
    记录持仓历史到数据库
    
    Args:
        supabase: Supabase 客户端
        positions: 持仓列表（从 binance_positions.get_positions() 获取）
    """
    if not positions:
        return

    now = datetime.now(timezone.utc).isoformat()

    for pos in positions:
        symbol = pos.get("symbol", "")
        if not symbol:
            continue

        # 获取市场风险信息
        market_risk = get_market_risk(supabase, symbol)

        # 计算距离强平价格的距离
        entry_price = pos.get("entry_price", 0)
        liquidation_price = pos.get("liquidation_price", 0)
        size = pos.get("size", 0)
        liquidation_distance = calculate_liquidation_distance(
            entry_price, liquidation_price, size
        )

        # 构建风险原因数组
        risk_reasons = []
        if market_risk["risk_level"] == "DANGER":
            risk_reasons.append("MARKET_DANGER")
        if market_risk["regime"] in ["SQUEEZE", "MANIPULATED"]:
            risk_reasons.append(f"REGIME_{market_risk['regime']}")
        if liquidation_distance is not None and liquidation_distance < 10:
            risk_reasons.append("NEAR_LIQUIDATION")

        # 准备记录数据
        history_record = {
            "created_at": now,
            "symbol": symbol,
            "size": size,
            "entry_price": entry_price,
            "mark_price": pos.get("mark_price", pos.get("current_price", 0)),
            "liquidation_price": liquidation_price,
            "unrealized_pnl": pos.get("unrealized_pnl", pos.get("pnl", 0)),
            "notional": pos.get("notional", 0),
            "market_risk_score": market_risk["risk_score"],
            "market_risk_level": market_risk["risk_level"],
            "market_regime": market_risk["regime"],
            "risk_reasons": risk_reasons if risk_reasons else None,
            "margin_type": pos.get("margin_type", "unknown"),
            "leverage": pos.get("leverage", 1),
        }

        try:
            supabase.table("position_history").insert(history_record).execute()
            print(f"[INFO] 已记录持仓历史: {symbol}")
        except Exception as e:  # noqa: BLE001
            print(f"[WARNING] 记录 {symbol} 持仓历史失败: {e}")


def check_position_risks(supabase: Client, positions: list[dict]) -> None:
    """
    检查持仓风险并生成警报
    
    Args:
        supabase: Supabase 客户端
        positions: 持仓列表
    """
    if not positions:
        return

    now = datetime.now(timezone.utc).isoformat()

    for pos in positions:
        symbol = pos.get("symbol", "")
        if not symbol:
            continue

        # 获取市场风险信息
        market_risk = get_market_risk(supabase, symbol)

        # 计算距离强平价格的距离
        entry_price = pos.get("entry_price", 0)
        liquidation_price = pos.get("liquidation_price", 0)
        size = pos.get("size", 0)
        liquidation_distance = calculate_liquidation_distance(
            entry_price, liquidation_price, size
        )

        alerts = []

        # 检查1: 市场风险等级为 DANGER
        if market_risk["risk_level"] == "DANGER":
            alerts.append({
                "alert_type": "MARKET_DANGER",
                "alert_level": "CRITICAL",
                "message": f"{symbol} 市场状态为高危（{market_risk['regime']}），建议考虑平仓",
                "market_risk_score": market_risk["risk_score"],
                "market_risk_level": market_risk["risk_level"],
                "market_regime": market_risk["regime"],
            })

        # 检查2: 市场风险评分 >= 80
        if market_risk["risk_score"] >= 80:
            alerts.append({
                "alert_type": "HIGH_RISK",
                "alert_level": "WARNING",
                "message": f"{symbol} 市场风险评分 {market_risk['risk_score']}，风险较高",
                "market_risk_score": market_risk["risk_score"],
                "market_risk_level": market_risk["risk_level"],
                "market_regime": market_risk["regime"],
            })

        # 检查3: 距离强平价格过近
        if liquidation_distance is not None and liquidation_distance < 5:
            alerts.append({
                "alert_type": "LIQUIDATION_WARNING",
                "alert_level": "CRITICAL",
                "message": f"{symbol} 距离强平价格仅 {liquidation_distance:.2f}%，风险极高！",
                "distance_to_liquidation": liquidation_distance,
            })

        # 检查4: 时间止损（4.0）
        # 逻辑：持仓“存在时间”过久但盈利没有延展 -> 发出 TIME_STOP_LOSS 警报
        try:
            max_minutes = 15
            min_profit_ratio = 0.001  # 0.1%（名义价值口径）

            notional = float(pos.get("notional", 0) or 0)
            pnl = float(pos.get("unrealized_pnl", pos.get("pnl", 0)) or 0)
            profit_ratio = (pnl / notional) if notional > 0 else 0.0

            # 查询首次记录时间（近似为开仓开始被监控的时间）
            first_ts = None
            resp = (
                supabase.table("position_history")
                .select("created_at")
                .eq("symbol", symbol)
                .order("created_at", desc=False)
                .limit(1)
                .execute()
            )
            if resp.data:
                first_ts = resp.data[0].get("created_at")

            if first_ts:
                opened_at = datetime.fromisoformat(str(first_ts).replace("Z", "+00:00"))
                age_minutes = (datetime.now(timezone.utc) - opened_at).total_seconds() / 60.0

                if age_minutes >= max_minutes and profit_ratio < min_profit_ratio:
                    alerts.append({
                        "alert_type": "TIME_STOP_LOSS",
                        "alert_level": "WARNING",
                        "message": f"{symbol} 持仓已超过 {max_minutes} 分钟但盈利未延展（≈{profit_ratio*100:.2f}%），建议按 4.0 时间止损退出",
                        "market_risk_score": market_risk["risk_score"],
                        "market_risk_level": market_risk["risk_level"],
                        "market_regime": market_risk["regime"],
                        "distance_to_liquidation": liquidation_distance,
                    })
        except Exception as e:  # noqa: BLE001
            print(f"[WARNING] 时间止损检查失败 {symbol}: {e}")

        # 写入警报
        for alert in alerts:
            alert_record = {
                "created_at": now,
                "symbol": symbol,
                "alert_type": alert["alert_type"],
                "alert_level": alert["alert_level"],
                "message": alert["message"],
                "market_risk_score": alert.get("market_risk_score"),
                "market_risk_level": alert.get("market_risk_level"),
                "market_regime": alert.get("market_regime"),
                "distance_to_liquidation": alert.get("distance_to_liquidation"),
            }

            try:
                supabase.table("position_risk_alerts").insert(alert_record).execute()
                print(f"[ALERT] {alert['alert_level']}: {alert['message']}")
            except Exception as e:  # noqa: BLE001
                print(f"[WARNING] 记录 {symbol} 风险警报失败: {e}")


def monitor_positions() -> None:
    """
    主函数：监控持仓并记录历史
    
    定期调用此函数来：
    1. 获取当前持仓
    2. 记录持仓历史
    3. 检查持仓风险
    """
    supabase = init_supabase()
    if supabase is None:
        print("[ERROR] 无法初始化 Supabase，跳过持仓监控")
        return

    try:
        # 获取当前持仓
        positions = get_positions()

        if not positions:
            print("[INFO] 当前无持仓")
            return

        print(f"[INFO] 发现 {len(positions)} 个持仓，开始监控...")

        # 记录持仓历史
        record_position_history(supabase, positions)

        # 检查持仓风险
        check_position_risks(supabase, positions)

        print("[INFO] 持仓监控完成")

    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] 持仓监控失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 测试代码
    print("测试持仓监控...")
    monitor_positions()

