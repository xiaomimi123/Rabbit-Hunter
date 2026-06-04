"""
权重管理路由

端点:
  GET  /api/v43/weights
  GET  /api/v43/weight-history
  POST /api/v43/weights/adjust
  POST /api/v43/weights/apply/{weight_id}
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import get_supabase
from api.schemas.weights import V43WeightsResponse, V43WeightHistoryResponse

router = APIRouter(prefix="/api/v43", tags=["weights"])

# 权重约束常量
WEIGHT_CONSTRAINTS = {
    "structure": [0.25, 0.50],
    "volatility": [0.15, 0.35],
    "sentiment": [0.15, 0.35],
    "manipulation": [0.10, 0.25],
}

DEFAULT_WEIGHTS = {
    "structure": 0.35,
    "volatility": 0.25,
    "sentiment": 0.25,
    "manipulation": 0.15,
}


def _parse_weights(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}
    return value or {}


@router.get("/weights", response_model=V43WeightsResponse)
async def get_v43_current_weights(supabase=Depends(get_supabase)):
    """
    获取当前 V4.3 权重配置

    返回最新的权重配置和约束范围。
    """
    try:
        response = (
            supabase.table("ai_weights_v43")
            .select("*")
            .eq("applied", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not response.data or len(response.data) == 0:
            return {
                "weights": DEFAULT_WEIGHTS,
                "weights_version": "v4.3.0",
                "constraints": WEIGHT_CONSTRAINTS,
                "applied": False,
                "created_at": None,
            }

        record = response.data[0]
        weights = _parse_weights(record.get("weights", {}))

        return {
            "weights": weights,
            "weights_version": record.get("weights_version", "v4.3.0"),
            "constraints": WEIGHT_CONSTRAINTS,
            "applied": record.get("applied", False),
            "created_at": record.get("created_at"),
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取权重配置失败: {str(e)}",
        )


@router.get("/weight-history", response_model=List[V43WeightHistoryResponse])
async def get_v43_weight_history(
    limit: int = Query(50, description="返回的记录数，最多 100", ge=1, le=100),
    offset: int = Query(0, description="偏移量", ge=0),
    supabase=Depends(get_supabase),
):
    """
    获取 V4.3 权重历史列表

    返回权重调整历史，包括性能指标对比。
    """
    try:
        response = (
            supabase.table("ai_weights_v43")
            .select("*")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .limit(limit)
            .execute()
        )

        result = []
        for record in response.data or []:
            performance_metrics = record.get("performance_metrics")
            if isinstance(performance_metrics, str):
                try:
                    performance_metrics = json.loads(performance_metrics)
                except Exception:
                    performance_metrics = {}
            elif performance_metrics is None:
                performance_metrics = {}

            weights = _parse_weights(record.get("weights", {}))

            result.append({
                "id": record.get("id"),
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
                "weights": weights,
                "weights_version": record.get("weights_version"),
                "performance_metrics": performance_metrics,
                "opportunity_density_score": (
                    float(record.get("opportunity_density_score", 0))
                    if record.get("opportunity_density_score") is not None
                    else None
                ),
                "ai_reason": record.get("ai_reason"),
                "applied": record.get("applied", False),
            })

        return result
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取权重历史失败: {str(e)}",
        )


@router.post("/weights/adjust")
async def trigger_weight_adjustment(
    force: bool = Query(False, description="是否强制运行（即使最近已调整过）"),
    supabase=Depends(get_supabase),
):
    """
    触发 AI 权重调整

    手动触发 AI 进行权重调整，并保存到数据库。
    """
    try:
        scripts_path = Path(__file__).parent.parent.parent / "scripts"
        sys.path.insert(0, str(scripts_path))

        from v43_weight_manager import load_weights  # type: ignore[import-not-found]
        from v43_deepseek_constrained import DeepSeekConstrained  # type: ignore[import-not-found]
        from v43_weight_history_helper import save_weight_adjustment_to_database  # type: ignore[import-not-found]
        from v43_opportunity_density import (  # type: ignore[import-not-found]
            calculate_opportunity_density_score,
            calculate_trades_per_week,
            calculate_average_expectancy,
        )

        # 检查是否最近已调整过
        if not force:
            recent_response = (
                supabase.table("ai_weights_v43")
                .select("created_at")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            if recent_response.data:
                last_adjustment = recent_response.data[0].get("created_at")
                if last_adjustment:
                    last_time = datetime.fromisoformat(last_adjustment.replace("Z", "+00:00"))
                    hours_since = (datetime.now(last_time.tzinfo) - last_time).total_seconds() / 3600

                    if hours_since < 6:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"最近 {hours_since:.1f} 小时前已调整过，请稍后再试或使用 force=true",
                        )

        # 加载当前权重
        current_weights = load_weights()

        # 计算性能指标
        cutoff_date = (datetime.now() - timedelta(days=7)).isoformat()
        try:
            trades_response = (
                supabase.table("paper_trades")
                .select("entry_time, pnl_usdt, ret, status")
                .gte("entry_time", cutoff_date)
                .eq("status", "CLOSED")
                .execute()
            )
            trades = trades_response.data or []
        except Exception:
            trades = []

        if not trades:
            performance_metrics = {
                "win_rate": 0.5,
                "avg_profit": 0.0,
                "total_trades": 0,
                "profit_factor": 1.0,
                "max_drawdown": 0.0,
            }
        else:
            wins = [t for t in trades if (t.get("pnl_usdt") or t.get("ret") or 0) > 0]
            win_rate = len(wins) / len(trades) if trades else 0.0
            profits = [float(t.get("pnl_usdt") or t.get("ret") or 0) for t in trades if t.get("pnl_usdt") or t.get("ret")]
            avg_profit = sum(profits) / len(profits) if profits else 0.0
            winning_profits = [p for p in profits if p > 0]
            losing_profits = [abs(p) for p in profits if p < 0]
            profit_factor = (
                sum(winning_profits) / sum(losing_profits)
                if losing_profits and sum(losing_profits) > 0
                else 1.0
            )
            performance_metrics = {
                "win_rate": win_rate,
                "avg_profit": avg_profit,
                "total_trades": len(trades),
                "profit_factor": profit_factor,
                "max_drawdown": 0.0,
            }

        # 计算机会密度分数
        trades_per_week = calculate_trades_per_week(trades, days=7)
        average_expectancy = calculate_average_expectancy(trades)
        opportunity_density_score = calculate_opportunity_density_score(
            trades_per_week=trades_per_week,
            average_expectancy=average_expectancy,
            recent_performance={
                "win_rate": performance_metrics["win_rate"],
                "profit_factor": performance_metrics["profit_factor"],
            },
        )

        # AI 调整权重
        ai = DeepSeekConstrained(debug=False)
        if not ai.is_ready():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="DeepSeek API Key 未配置",
            )

        adjustment = ai.adjust_weights(
            current_weights=current_weights,
            performance_metrics=performance_metrics,
            opportunity_density_score=opportunity_density_score,
        )

        if not adjustment:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI 权重调整失败",
            )

        # 保存到数据库
        success = save_weight_adjustment_to_database(
            adjustment=adjustment,
            performance_metrics=performance_metrics,
            opportunity_density_score=opportunity_density_score,
            applied=False,
            supabase=supabase,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="保存权重调整失败",
            )

        return {
            "status": "success",
            "message": "权重调整已触发并保存",
            "data": {
                "weights_version": adjustment.version,
                "new_weights": adjustment.new_weights,
                "reasoning": adjustment.reasoning,
                "performance_metrics": performance_metrics,
                "opportunity_density_score": opportunity_density_score,
            },
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"触发权重调整失败: {str(e)}",
        )


@router.post("/weights/apply/{weight_id}")
async def apply_weight_configuration(
    weight_id: int,
    supabase=Depends(get_supabase),
):
    """
    应用权重配置

    将指定的权重配置标记为已应用，并更新当前使用的权重。
    """
    try:
        response = (
            supabase.table("ai_weights_v43")
            .select("*")
            .eq("id", weight_id)
            .single()
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"权重配置 {weight_id} 不存在",
            )

        weight_record = response.data
        weights = _parse_weights(weight_record.get("weights", {}))

        # 将所有其他权重配置标记为未应用
        supabase.table("ai_weights_v43").update({"applied": False}).neq("id", weight_id).execute()

        # 将当前权重配置标记为已应用
        supabase.table("ai_weights_v43").update({"applied": True}).eq("id", weight_id).execute()

        # 保存到配置文件（可选）
        try:
            from v43_weight_manager import save_weights  # type: ignore[import-not-found]
            save_weights(weights, save_to_database=False)
        except Exception as e:
            print(f"[WARNING] 保存权重到配置文件失败: {e}")

        return {
            "status": "success",
            "message": f"权重配置 {weight_record.get('weights_version')} 已应用",
            "data": {
                "id": weight_id,
                "weights_version": weight_record.get("weights_version"),
                "weights": weights,
            },
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"应用权重配置失败: {str(e)}",
        )
