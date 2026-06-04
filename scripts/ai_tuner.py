"""
V4.2 DeepSeek Tuner (AI 参数调优模块)

功能：
- 使用 DeepSeek AI 调优策略参数
- 分析过去 7 天的行情数据和模拟交易日志
- 输出参数建议（ATR 倍数、阈值等）
- 验证参数在安全区间内
- 保存配置到 strategy_config.json
- 记录调优历史到 ai_evolution_logs 表
"""

import os
import json
from typing import Optional, Dict, Any
from datetime import datetime, date, timezone
from pathlib import Path
from dotenv import load_dotenv

# 尝试导入 DeepSeek AI 客户端
try:
    from scripts.deepseek_ai import DeepSeekJudge
    DEEPSEEK_AVAILABLE = True
except ImportError:
    try:
        from deepseek_ai import DeepSeekJudge
        DEEPSEEK_AVAILABLE = True
    except ImportError:
        DEEPSEEK_AVAILABLE = False
        DeepSeekJudge = None

# 尝试导入 Time Machine
try:
    from scripts.time_machine import replay_history, SimulationConfig, SimulationResult
    TIME_MACHINE_AVAILABLE = True
except ImportError:
    TIME_MACHINE_AVAILABLE = False


# 默认策略配置
DEFAULT_CONFIG = {
    "atr_multiplier_p2": 2.5,
    "atr_multiplier_p3a_early": 2.5,
    "atr_multiplier_p3a_normal": 2.0,
    "atr_multiplier_p3b": 1.5,
    "structure_gap_threshold": 0.02,  # 2%
    "phase_age_max_candles": 100,
    "context_gate_required": True,
    "golden_wick_bypass_structure": True,
    "risk_per_trade": 0.015,  # 1.5%
    "ai_judge_threshold": 0.65,
}

# 参数安全区间
PARAM_SAFE_RANGES = {
    "atr_multiplier_p2": (1.5, 3.5),
    "atr_multiplier_p3a_early": (1.5, 3.5),
    "atr_multiplier_p3a_normal": (1.0, 3.0),
    "atr_multiplier_p3b": (1.0, 2.5),
    "structure_gap_threshold": (0.01, 0.05),  # 1% - 5%
    "phase_age_max_candles": (50, 150),
    "risk_per_trade": (0.01, 0.03),  # 1% - 3%
    "ai_judge_threshold": (0.5, 0.8),
}


def load_strategy_config(config_path: str = "strategy_config.json") -> Dict[str, Any]:
    """
    加载策略配置
    
    Args:
        config_path: 配置文件路径
    
    Returns:
        策略配置字典
    """
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    
    return DEFAULT_CONFIG.copy()


def save_strategy_config(config: Dict[str, Any], config_path: str = "strategy_config.json"):
    """
    保存策略配置
    
    Args:
        config: 策略配置字典
        config_path: 配置文件路径
    """
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def validate_param_change(old_value: float, new_value: float, param_name: str, auto_clamp: bool = True) -> tuple[bool, str, float]:
    """
    验证参数变化是否在安全范围内
    
    规则：
    1. 变化幅度 < 10%（如果超过，自动限制在 10% 以内）
    2. 新值必须在安全区间内
    
    Args:
        old_value: 旧值
        new_value: 新值
        param_name: 参数名称
        auto_clamp: 如果变化超过 10%，是否自动限制在 10% 以内
    
    Returns:
        (is_valid, reason, clamped_value)
        - is_valid: 是否有效
        - reason: 原因（如果有警告或错误）
        - clamped_value: 限制后的值（如果 auto_clamp=True）
    """
    clamped_value = new_value
    
    # 检查变化幅度
    if old_value == 0:
        change_pct = abs(new_value) * 100
    else:
        change_pct = abs((new_value - old_value) / old_value) * 100
    
    if change_pct > 10:
        if auto_clamp:
            # 自动限制在 10% 以内
            if new_value > old_value:
                clamped_value = old_value * 1.1
            else:
                clamped_value = old_value * 0.9
            reason = f"参数 {param_name} 变化幅度 {change_pct:.2f}% 超过 10% 限制，已自动限制为 10%"
        else:
            return False, f"参数 {param_name} 变化幅度 {change_pct:.2f}% 超过 10% 限制", new_value
    else:
        reason = ""
    
    # 使用限制后的值检查安全区间
    value_to_check = clamped_value
    
    # 检查安全区间
    if param_name in PARAM_SAFE_RANGES:
        min_val, max_val = PARAM_SAFE_RANGES[param_name]
        if value_to_check < min_val:
            clamped_value = min_val
            if reason:
                reason += f"；新值低于安全区间最小值 {min_val}，已自动调整为 {min_val}"
            else:
                reason = f"参数 {param_name} 新值 {value_to_check:.4f} 低于安全区间最小值 {min_val}，已自动调整为 {min_val}"
        elif value_to_check > max_val:
            clamped_value = max_val
            if reason:
                reason += f"；新值超过安全区间最大值 {max_val}，已自动调整为 {max_val}"
            else:
                reason = f"参数 {param_name} 新值 {value_to_check:.4f} 超过安全区间最大值 {max_val}，已自动调整为 {max_val}"
    
    return True, reason, clamped_value


def prepare_tuning_data(
    supabase,
    days: int = 7
) -> Dict[str, Any]:
    """
    准备调优数据（过去 N 天的行情数据和模拟交易日志）
    
    Args:
        supabase: Supabase 客户端
        days: 数据天数
    
    Returns:
        调优数据字典
    """
    from datetime import timedelta
    
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # 获取过去 N 天的训练数据（移除 Supabase 默认的 1000 条限制）
    # 注意：Supabase 默认限制是 1000 条，需要显式设置更大的 limit 或使用分页
    training_data = []
    page_size = 1000
    offset = 0
    
    while True:
        training_response = (
            supabase.table("ai_training_data")
            .select("*")
            .gte("created_at", start_date)
            .order("created_at", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        
        page_data = training_response.data or []
        if not page_data:
            break
        
        training_data.extend(page_data)
        
        # 如果返回的数据少于 page_size，说明已经是最后一页
        if len(page_data) < page_size:
            break
        
        offset += page_size
    
    # 获取模拟交易数据（如果有，也使用分页）
    paper_trades = []
    offset = 0
    
    while True:
        paper_response = (
            supabase.table("paper_trades")
            .select("*")
            .gte("created_at", start_date)
            .order("created_at", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        
        page_data = paper_response.data or []
        if not page_data:
            break
        
        paper_trades.extend(page_data)
        
        # 如果返回的数据少于 page_size，说明已经是最后一页
        if len(page_data) < page_size:
            break
        
        offset += page_size
    
    return {
        "training_data": training_data,
        "paper_trades": paper_trades,
        "data_points": len(training_data),
        "trade_count": len(paper_trades),
    }


def call_deepseek_tuner(
    tuning_data: Dict[str, Any],
    current_config: Dict[str, Any],
    simulation_report: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    调用 DeepSeek AI 进行参数调优（使用 V4.2 专业提示词）
    
    Args:
        tuning_data: 调优数据（包含数据点、交易统计等）
        current_config: 当前策略配置
        simulation_report: 模拟报告（包含性能指标和失败分析）
    
    Returns:
        AI 建议的新配置字典，或 None
    """
    if not DEEPSEEK_AVAILABLE:
        print("[WARNING] DeepSeek AI 不可用，跳过参数调优")
        return None
    
    try:
        # V4.2 专业 System Prompt（Rabbit Hunter V4.2 - AI 调优官专属提示词）
        system_prompt = """# Role
You are the "Optimization Engine" for a proprietary crypto trading system named "Rabbit Hunter V4.2". 
Your goal is to maximize the "Whale Capture Score (WCS)" while strictly adhering to risk management protocols.
You DO NOT trade. You only adjust strategy parameters based on simulation logs.

# The Strategy Logic
The system captures "P3A" (Whale Pump) phases using ATR Trailing Stops.
- If Win Rate is low but Risk:Reward is high: This is acceptable.
- If Drawdown is high: This is unacceptable.
- If P3A trend is missed: This is unacceptable.

# Input Data
You will receive a JSON containing:
1. `current_config`: The parameters used in the last 24h simulation.
2. `simulation_report`: Key metrics (Win Rate, Max Drawdown, Avg PnL, WCS Score).
3. `failure_analysis`: A summary of why trades failed (e.g., "Stopped out by noise", "Missed entry").

# Your Action Space (Hard Constraints)
You are allowed to tune ONLY the following parameters within these bounds. DO NOT exceed them:

| Parameter | Min | Max | Description |
| :--- | :--- | :--- | :--- |
| `atr_multiplier_p3a_normal` | 1.5 | 3.5 | Stop loss width. Higher = looser stop. |
| `risk_per_trade` | 0.005 | 0.02 | 0.5% to 2.0% equity risk per trade. |
| `structure_gap_threshold` | 0.015 | 0.04 | Minimum distance to resistance required. |
| `ai_judge_threshold` | 0.5 | 0.8 | Sensitivity to whale anomalies. |

# Tuning Logic (Chain of Thought)
1. **Analyze Drawdown First**: If Max Drawdown > 5% in simulation, immediately reduce `risk_per_trade` and tighten `atr_multiplier_p3a_normal`.
2. **Analyze Whipsaws**: If many trades were stopped out but price later went up (Noise), increase `atr_multiplier_p3a_normal` (widen stop) slightly.
3. **Analyze Missed Opportunity**: If `ai_judge_threshold` is high and trade count is 0 despite market movement, lower `ai_judge_threshold`.
4. **Gradient Clipping**: Do not change any parameter by more than 10% per iteration compared to `current_config`.

# Output Format
You must output ONLY a valid JSON object containing the new configuration and a short reasoning string.
NO markdown code blocks. NO conversational text.

Example Output:
{
  "new_config": {
    "atr_multiplier_p3a_normal": 2.2,
    "risk_per_trade": 0.012,
    "structure_gap_threshold": 0.02,
    "ai_judge_threshold": 0.65
  },
  "reasoning": "Drawdown was low (1%), but missed 2 valid P3A trends due to tight ATR. Increased ATR multiplier by 10% to capture noise."
}"""
        
        # 构建 User Prompt（包含性能指标和失败分析）
        from datetime import date
        
        # 提取性能指标
        win_rate = simulation_report.get("win_rate", 0.0) if simulation_report else 0.0
        max_drawdown = simulation_report.get("max_drawdown", 0.0) if simulation_report else 0.0
        total_trades = simulation_report.get("total_trades", 0) if simulation_report else tuning_data.get("trade_count", 0)
        wcs_score = simulation_report.get("wcs_score", 0.0) if simulation_report else 0.0
        avg_pnl_ratio = simulation_report.get("avg_pnl_ratio", "1:1") if simulation_report else "1:1"
        
        # 分析失败模式
        failure_patterns = []
        if simulation_report:
            if max_drawdown > 0.05:  # 5%
                failure_patterns.append(f"Max Drawdown {max_drawdown*100:.1f}% exceeds 5% limit (Drawdown issue).")
            if total_trades == 0 and tuning_data.get("data_points", 0) > 100:
                failure_patterns.append("No trades executed despite market movement (Missed opportunity).")
            if win_rate < 0.3 and total_trades > 0:
                failure_patterns.append(f"Low win rate {win_rate*100:.1f}% suggests many trades stopped out by noise (Whipsaw issue).")
        
        failure_analysis = "\n".join(failure_patterns) if failure_patterns else "No significant failure patterns detected."
        
        user_prompt = f"""Here is the simulation report for {date.today().isoformat()}:

[Current Config]
{json.dumps(current_config, indent=2, ensure_ascii=False)}

[Performance Metrics]
- Win Rate: {win_rate*100:.1f}%
- Max Drawdown: {max_drawdown*100:.1f}% {"(WARNING: Close to limit)" if max_drawdown > 0.04 else ""}
- Total Trades: {total_trades}
- WCS Score: {wcs_score:.2f} {"(Low)" if wcs_score < 50 else ""}
- Avg PnL Ratio: {avg_pnl_ratio}
- Data Points: {tuning_data.get("data_points", 0)}

[Failure Patterns]
{failure_analysis}

Based on the above, optimize the configuration for tomorrow."""
        
        # 调用 DeepSeek AI
        import requests
        
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        base_url = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/")
        model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        
        if not api_key:
            return None
        
        endpoint = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "max_tokens": 800,
            "response_format": {"type": "json_object"},
            "temperature": 0.1,  # 低温保证输出稳定
        }
        
        try:
            r = requests.post(endpoint, headers=headers, json=body, timeout=60)
            if r.status_code >= 400:
                print(f"[ERROR] DeepSeek API 返回错误: {r.status_code} - {r.text}")
                return None
            
            data = r.json()
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "")
                if content:
                    # 尝试解析 JSON
                    try:
                        response_data = json.loads(content)
                        
                        # 提取 new_config 和 reasoning
                        if "new_config" in response_data:
                            suggested_config = response_data["new_config"]
                            reasoning = response_data.get("reasoning", "")
                            if reasoning:
                                print(f"[AI Reasoning] {reasoning}")
                            return suggested_config
                        else:
                            # 如果没有 new_config，假设整个响应就是配置
                            return response_data
                    except json.JSONDecodeError as e:
                        print(f"[ERROR] JSON 解析失败: {e}")
                        print(f"[DEBUG] 响应内容: {content[:200]}")
                        # 如果直接解析失败，尝试提取 JSON
                        import re
                        json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
                        if json_match:
                            try:
                                response_data = json.loads(json_match.group())
                                if "new_config" in response_data:
                                    return response_data["new_config"]
                                return response_data
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            print(f"[ERROR] DeepSeek API 调用失败: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    except Exception as e:
        print(f"[ERROR] DeepSeek AI 调优失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def apply_tuning(
    supabase,
    config_path: str = "strategy_config.json"
) -> Dict[str, Any]:
    """
    执行参数调优
    
    Args:
        supabase: Supabase 客户端
        config_path: 配置文件路径
    
    Returns:
        调优结果字典
    """
    # 1. 加载当前配置
    current_config = load_strategy_config(config_path)
    
    # 2. 准备调优数据
    tuning_data = prepare_tuning_data(supabase, days=7)
    
    if tuning_data.get("data_points", 0) < 100:
        return {
            "success": False,
            "reason": f"数据点不足（需要至少 100 个，当前 {tuning_data.get('data_points', 0)} 个）"
        }
    
    # 3. 使用 Time Machine 评估当前配置并生成模拟报告
    current_score = None
    simulation_report = None
    if TIME_MACHINE_AVAILABLE:
        try:
            sim_config = SimulationConfig(
                atr_multiplier_p2=current_config.get("atr_multiplier_p2", 2.5),
                atr_multiplier_p3a_early=current_config.get("atr_multiplier_p3a_early", 2.5),
                atr_multiplier_p3a_normal=current_config.get("atr_multiplier_p3a_normal", 2.0),
                atr_multiplier_p3b=current_config.get("atr_multiplier_p3b", 1.5),
                structure_gap_threshold=current_config.get("structure_gap_threshold", 0.02),
                phase_age_max_candles=current_config.get("phase_age_max_candles", 100),
            )
            result = replay_history(tuning_data["training_data"], sim_config)
            current_score = result.wcs_score
            
            # 计算平均盈亏比
            if result.winning_trades > 0 and result.losing_trades > 0:
                avg_win = result.total_profit / result.winning_trades
                avg_loss = abs(result.total_loss) / result.losing_trades
                avg_pnl_ratio = f"1:{avg_win/avg_loss:.2f}" if avg_loss > 0 else "1:0"
            else:
                avg_pnl_ratio = "1:1"
            
            # 生成模拟报告（用于 AI 调优）
            simulation_report = {
                "win_rate": result.win_rate,
                "max_drawdown": result.max_drawdown,
                "total_trades": result.total_trades,
                "wcs_score": result.wcs_score,
                "avg_pnl_ratio": avg_pnl_ratio,
                "winning_trades": result.winning_trades,
                "losing_trades": result.losing_trades,
                "missed_p3a": result.missed_p3a,
            }
        except Exception as e:
            print(f"[WARNING] Time Machine 评估失败: {e}")
    
    # 4. 调用 DeepSeek AI 获取参数建议（传入模拟报告）
    suggested_config = call_deepseek_tuner(tuning_data, current_config, simulation_report)
    
    if not suggested_config:
        return {
            "success": False,
            "reason": "DeepSeek AI 未返回参数建议"
        }
    
    # 6. 验证并合并参数（自动限制变化幅度在 10% 以内）
    new_config = current_config.copy()
    validation_warnings = []
    validation_errors = []
    
    for param_name, new_value in suggested_config.items():
        if param_name not in current_config:
            validation_errors.append(f"未知参数: {param_name}")
            continue
        
        old_value = current_config[param_name]
        is_valid, reason, clamped_value = validate_param_change(old_value, new_value, param_name, auto_clamp=True)
        
        if not is_valid:
            validation_errors.append(reason)
        else:
            # 使用限制后的值
            new_config[param_name] = clamped_value
            if reason:  # 如果有警告（如自动限制），记录下来
                validation_warnings.append(reason)
    
    if validation_errors:
        return {
            "success": False,
            "reason": "参数验证失败",
            "errors": validation_errors
        }
    
    # 如果有警告，记录到结果中（但不阻止调优）
    if validation_warnings:
        print(f"[WARNING] 参数调整警告: {validation_warnings}")
    
    # 6. 使用 Time Machine 评估新配置
    new_score = None
    if TIME_MACHINE_AVAILABLE:
        try:
            sim_config = SimulationConfig(
                atr_multiplier_p2=new_config.get("atr_multiplier_p2", 2.5),
                atr_multiplier_p3a_early=new_config.get("atr_multiplier_p3a_early", 2.5),
                atr_multiplier_p3a_normal=new_config.get("atr_multiplier_p3a_normal", 2.0),
                atr_multiplier_p3b=new_config.get("atr_multiplier_p3b", 1.5),
                structure_gap_threshold=new_config.get("structure_gap_threshold", 0.02),
                phase_age_max_candles=new_config.get("phase_age_max_candles", 100),
            )
            result = replay_history(tuning_data["training_data"], sim_config)
            new_score = result.wcs_score
        except Exception as e:
            print(f"[WARNING] Time Machine 评估新配置失败: {e}")
    
    # 7. 保存配置（如果新配置更好）
    is_applied = False
    if new_score is not None and current_score is not None:
        if new_score > current_score:
            save_strategy_config(new_config, config_path)
            is_applied = True
    else:
        # 如果无法评估，默认不应用
        is_applied = False
    
    # 8. 记录到数据库
    if supabase:
        try:
            supabase.table("ai_evolution_logs").insert({
                "train_date": date.today().isoformat(),
                "old_config": json.dumps(current_config),
                "new_config": json.dumps(new_config),
                "simulation_score": new_score if new_score is not None else current_score,
                "is_applied": is_applied,
            }).execute()
        except Exception as e:
            print(f"[WARNING] 记录调优历史失败: {e}")
    
    return {
        "success": True,
        "current_config": current_config,
        "new_config": new_config,
        "current_score": current_score,
        "new_score": new_score,
        "is_applied": is_applied,
        "improvement": (new_score - current_score) if (new_score and current_score) else None,
    }


__all__ = [
    "load_strategy_config",
    "save_strategy_config",
    "validate_param_change",
    "prepare_tuning_data",
    "call_deepseek_tuner",
    "apply_tuning",
]

