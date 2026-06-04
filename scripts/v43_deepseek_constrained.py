"""
V4.3 带约束的 DeepSeek AI 模块

定位：
- AI 只能调整权重，不能修改规则
- 所有决策必须可解释
- ⚠️ AI 最高禁令：不允许为了提升短期指标，降低系统可解释性

功能：
- 权重调整（带约束）
- 每日自省报告
- 可解释性检查
- AI 决策验证
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, date

import requests

# 确保 scripts 目录在路径中
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

try:
    from scripts.v43_weight_manager import (
        load_weights,
        save_weights,
        validate_weights,
        get_next_version,
        WEIGHT_CONSTRAINTS,
        DEFAULT_WEIGHTS,
    )
except ImportError:
    # 备用导入路径
    from v43_weight_manager import (  # type: ignore
        load_weights,
        save_weights,
        validate_weights,
        get_next_version,
        WEIGHT_CONSTRAINTS,
        DEFAULT_WEIGHTS,
    )


@dataclass
class WeightAdjustment:
    """权重调整结果"""
    new_weights: Dict[str, float]
    reasoning: str
    explainability_check: bool
    opportunity_density_impact: Optional[str] = None  # "quality" or "density"
    version: str = "v4.3.0"


@dataclass
class DailyReport:
    """每日自省报告"""
    report_date: date
    report_content: Dict[str, Any]
    opportunity_density_analysis: Dict[str, Any]
    weight_adjustments: Optional[WeightAdjustment] = None
    explainability_check: bool = True
    applied: bool = False


class DeepSeekConstrained:
    """
    V4.3 带约束的 DeepSeek AI
    
    核心原则：
    1. AI 只能调整权重，不能修改规则
    2. 所有决策必须可解释
    3. ⚠️ AI 最高禁令：不允许为了提升短期指标，降低系统可解释性
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat",
        timeout_seconds: float = 30.0,
        max_tokens: int = 1000,
        debug: bool = False,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.base_url = (base_url or os.environ.get("DEEPSEEK_API_BASE") or "https://api.deepseek.com").rstrip("/")
        self.model = os.environ.get("DEEPSEEK_MODEL") or model
        self.timeout_seconds = float(os.environ.get("DEEPSEEK_TIMEOUT", timeout_seconds))
        self.max_tokens = int(os.environ.get("DEEPSEEK_MAX_TOKENS", str(max_tokens)))
        self.debug = debug or os.environ.get("DEEPSEEK_DEBUG", "0") in ("1", "true", "True")
    
    def is_ready(self) -> bool:
        """检查是否已配置 API Key"""
        return bool(self.api_key)
    
    def _endpoint(self) -> str:
        """获取 API 端点"""
        return f"{self.base_url}/chat/completions"
    
    def generate_anatomy_explanation(
        self,
        symbol: str,
        score: float,
        reason: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        为指定币种生成深度解剖台用的 AI 文本解释。

        返回一段简短的中文说明，用于前端 “神经脉冲 (AI 心声)” 区域。
        """
        if not self.is_ready():
            return None

        system_prompt = (
            "你是 Rabbit Hunter V4.3 系统内嵌的 DeepSeek 交易分析助手。"
            "请用简短的中文（不超过 80 字）解释当前币种的交易形态，"
            "语气要像一位冷静的战术顾问，避免啰嗦。"
            "可以提到 P 阶段、ATR 吃趋势、黄金影线等概念，但不要给出具体下单指令。"
        )

        # 组合额外上下文：ATR、止损/止盈、盈亏比、阶段等
        atr = None
        stop_loss = None
        take_profit = None
        reward_risk_ratio = None
        phase = None
        if context:
            atr = context.get("atr")
            stop_loss = context.get("stop_loss")
            take_profit = context.get("take_profit")
            reward_risk_ratio = context.get("reward_risk_ratio")
            phase = context.get("phase")

        extra_lines: list[str] = []
        if phase:
            extra_lines.append(f"阶段: {phase}")
        if atr is not None:
            extra_lines.append(f"ATR: {float(atr):.6f}")
        if stop_loss is not None and take_profit is not None:
            extra_lines.append(f"止损: {float(stop_loss):.6f} / 止盈: {float(take_profit):.6f}")
        if reward_risk_ratio is not None:
            try:
                rr = float(reward_risk_ratio)
                extra_lines.append(f"盈亏比: 1:{rr:.2f}")
            except Exception:
                pass

        context_text = ""
        if extra_lines:
            context_text = "\n".join(extra_lines) + "\n"

        user_prompt = (
            f"币种: {symbol}\n"
            f"AI 评分: {score:.1f}/100\n"
            f"检测到的理由: {reason or '系统未提供详细原因'}\n"
            f"{context_text}\n"
            "请结合这些信息，总结当前机会的大致形态、主要风险点和观察要点。"
        )

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "max_tokens": min(self.max_tokens, 512),
            "temperature": 0.7,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            r = requests.post(self._endpoint(), headers=headers, json=body, timeout=self.timeout_seconds)
            if r.status_code >= 400:
                if self.debug:
                    msg = (r.text or "")[:300].replace("\n", " ")
                    print(f"[DEEPSEEK][HTTP {r.status_code}][anatomy] {msg}")
                return None

            data = r.json()
            content = data["choices"][0]["message"]["content"]
            return (content or "").strip()
        except Exception as e:  # noqa: BLE001
            if self.debug:
                print(f"[DEEPSEEK][ERROR][anatomy_explain] {type(e).__name__}: {e}")
            return None
    
    def _get_system_prompt(self) -> str:
        """
        获取系统提示词（含硬约束声明）
        
        这是 V4.3 的核心：明确限制 AI 的角色和权限
        """
        return """You are a trading optimization AI embedded inside a live trading system.

Your role is strictly LIMITED to:
1. Adjusting factor weights within allowed ranges
2. Analyzing past decisions and missed opportunities
3. Explaining your reasoning clearly in daily reports

You are STRICTLY FORBIDDEN from:
- Modifying hard trading rules
- Suggesting removal of stop-loss logic
- Optimizing for win-rate alone
- Hiding or omitting explanations

Hard constraints you MUST respect:
- Expected Return per trade >= 2%
- Risk per trade <= 1.5%
- Structure weight >= 0.25 (min) and <= 0.50 (max)
- Volatility weight >= 0.15 (min) and <= 0.35 (max)
- Sentiment weight >= 0.15 (min) and <= 0.35 (max)
- Manipulation weight >= 0.10 (min) and <= 0.25 (max)
- You may NOT set any weight to zero
- All weights must sum to 1.0

Your objective function is:
Maximize long-term expectancy (E), NOT short-term win-rate.

Every weight change must be justified.
If you cannot explain a change, do NOT make it.

⚠️ HIGHEST PROHIBITION:
AI is NOT allowed to reduce system explainability to improve short-term metrics.
If reasoning cannot be explained in plain language, the adjustment is invalid.

If market conditions are unclear, you must recommend inactivity.

You must generate a DAILY SELF-REFLECTION REPORT.

When adjusting weights, you MUST answer:
"Is this adjustment improving single trade quality, or opportunity density?"
You cannot optimize for one without considering the other."""
    
    def adjust_weights(
        self,
        current_weights: Dict[str, float],
        performance_metrics: Dict[str, Any],
        opportunity_density_score: float,
        recent_trades: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[WeightAdjustment]:
        """
        调整权重（带约束）
        
        Args:
            current_weights: 当前权重
            performance_metrics: 性能指标
                - win_rate: 胜率
                - profit_factor: 盈亏比
                - max_drawdown: 最大回撤
                - total_trades: 总交易次数
            opportunity_density_score: 机会密度分数
            recent_trades: 最近交易列表（可选）
        
        Returns:
            WeightAdjustment 或 None（如果调整失败）
        """
        if not self.is_ready():
            return None
        
        # 验证当前权重
        valid, reason = validate_weights(current_weights)
        if not valid:
            if self.debug:
                print(f"[DEEPSEEK][WARNING] 当前权重无效: {reason}")
            return None
        
        # 构建用户提示词
        user_prompt = {
            "current_weights": current_weights,
            "performance_metrics": performance_metrics,
            "opportunity_density_score": opportunity_density_score,
            "constraints": WEIGHT_CONSTRAINTS,
        }
        
        # 添加额外提示
        additional_instructions = """You must output a JSON object with:
{
  "new_weights": {
    "structure": 0.35,
    "volatility": 0.25,
    "sentiment": 0.25,
    "manipulation": 0.15
  },
  "reasoning": "Clear explanation in plain language",
  "opportunity_density_impact": "quality" or "density"
}

⚠️ CRITICAL:
- All weights must be within constraints
- Weights must sum to 1.0
- Reasoning must be explainable in plain language
- You MUST answer: "Is this improving quality or density?"
- If you cannot explain, return current weights unchanged."""
        
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False) + "\n\n" + additional_instructions},
            ],
            "stream": False,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "temperature": 0.2,  # 较低温度，更保守
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        try:
            r = requests.post(self._endpoint(), headers=headers, json=body, timeout=self.timeout_seconds)
            if r.status_code >= 400:
                if self.debug:
                    msg = (r.text or "")[:300].replace("\n", " ")
                    print(f"[DEEPSEEK][HTTP {r.status_code}] {msg}")
                return None
            
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            obj = json.loads(content)
            
            # 提取新权重
            new_weights = obj.get("new_weights", current_weights)
            reasoning = obj.get("reasoning", "")
            ods_impact = obj.get("opportunity_density_impact", "unknown")
            
            # 验证新权重
            valid, reason = validate_weights(new_weights)
            if not valid:
                if self.debug:
                    print(f"[DEEPSEEK][WARNING] AI 建议的权重无效: {reason}")
                return None
            
            # 检查可解释性
            explainability_check = self.check_explainability(reasoning)
            
            # 生成版本号
            current_version = current_weights.get("version", "v4.3.0")
            new_version = get_next_version(current_version)
            new_weights["version"] = new_version
            
            return WeightAdjustment(
                new_weights=new_weights,
                reasoning=reasoning,
                explainability_check=explainability_check,
                opportunity_density_impact=ods_impact,
                version=new_version,
            )
        except Exception as e:
            if self.debug:
                print(f"[DEEPSEEK][ERROR] {type(e).__name__}: {e}")
            return None
    
    def check_explainability(self, reasoning: str) -> bool:
        """
        检查可解释性
        
        ⚠️ AI 最高禁令：不允许为了提升短期指标，降低系统可解释性
        
        Args:
            reasoning: AI 的推理过程
        
        Returns:
            True: 可解释
            False: 不可解释
        """
        if not reasoning or len(reasoning.strip()) < 10:
            return False
        
        # 检查是否包含"黑盒"词汇
        blackbox_keywords = [
            "complex combination",
            "black box",
            "unclear",
            "cannot explain",
            "mysterious",
            "unexplainable",
        ]
        
        reasoning_lower = reasoning.lower()
        for keyword in blackbox_keywords:
            if keyword in reasoning_lower:
                if self.debug:
                    print(f"[DEEPSEEK][WARNING] 检测到不可解释的推理: {keyword}")
                return False
        
        # 检查是否包含具体解释
        explanation_keywords = [
            "because",
            "due to",
            "reason",
            "based on",
            "according to",
            "improve",
            "increase",
            "decrease",
        ]
        
        has_explanation = any(keyword in reasoning_lower for keyword in explanation_keywords)
        
        return has_explanation
    
    def generate_daily_report(
        self,
        report_date: date,
        performance_metrics: Dict[str, Any],
        opportunity_density_score: float,
        recent_trades: Optional[List[Dict[str, Any]]] = None,
        current_weights: Optional[Dict[str, float]] = None,
    ) -> Optional[DailyReport]:
        """
        生成每日自省报告
        
        Args:
            report_date: 报告日期
            performance_metrics: 性能指标
            opportunity_density_score: 机会密度分数
            recent_trades: 最近交易列表（可选）
            current_weights: 当前权重（可选）
        
        Returns:
            DailyReport 或 None
        """
        if not self.is_ready():
            return None
        
        # 加载当前权重（如果未提供）
        if current_weights is None:
            current_weights = load_weights()
        
        # 构建用户提示词
        user_prompt = {
            "report_date": report_date.isoformat(),
            "performance_metrics": performance_metrics,
            "opportunity_density_score": opportunity_density_score,
            "current_weights": current_weights,
            "task": "Generate a daily self-reflection report",
        }
        
        additional_instructions = """You must output a JSON object with:
{
  "report_content": {
    "summary": "Overall performance summary",
    "strengths": ["What worked well"],
    "weaknesses": ["What needs improvement"],
    "missed_opportunities": ["Opportunities we missed"],
    "recommendations": ["Action items"]
  },
  "opportunity_density_analysis": {
    "current_ods": 0.65,
    "trend": "increasing" or "decreasing" or "stable",
    "interpretation": "What this means"
  },
  "weight_adjustments": {
    "new_weights": {...},
    "reasoning": "...",
    "opportunity_density_impact": "quality" or "density"
  },
  "explainability_check": true
}

⚠️ CRITICAL:
- All reasoning must be explainable in plain language
- If you cannot explain, set explainability_check to false
- Weight adjustments must respect constraints"""
        
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False) + "\n\n" + additional_instructions},
            ],
            "stream": False,
            "max_tokens": self.max_tokens * 2,  # 报告需要更多 token
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        try:
            r = requests.post(self._endpoint(), headers=headers, json=body, timeout=self.timeout_seconds * 2)
            if r.status_code >= 400:
                if self.debug:
                    msg = (r.text or "")[:300].replace("\n", " ")
                    print(f"[DEEPSEEK][HTTP {r.status_code}] {msg}")
                return None
            
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            obj = json.loads(content)
            
            # 提取报告内容
            report_content = obj.get("report_content", {})
            ods_analysis = obj.get("opportunity_density_analysis", {})
            weight_adjustments_data = obj.get("weight_adjustments", {})
            explainability_check = obj.get("explainability_check", False)
            
            # 处理权重调整
            weight_adjustment = None
            if weight_adjustments_data:
                new_weights = weight_adjustments_data.get("new_weights", {})
                reasoning = weight_adjustments_data.get("reasoning", "")
                ods_impact = weight_adjustments_data.get("opportunity_density_impact", "unknown")
                
                # 验证权重
                valid, reason = validate_weights(new_weights)
                if valid:
                    # 检查可解释性
                    exp_check = self.check_explainability(reasoning)
                    
                    # 生成版本号
                    current_version = current_weights.get("version", "v4.3.0")
                    new_version = get_next_version(current_version)
                    new_weights["version"] = new_version
                    
                    weight_adjustment = WeightAdjustment(
                        new_weights=new_weights,
                        reasoning=reasoning,
                        explainability_check=exp_check,
                        opportunity_density_impact=ods_impact,
                        version=new_version,
                    )
                else:
                    if self.debug:
                        print(f"[DEEPSEEK][WARNING] 报告中的权重调整无效: {reason}")
            
            return DailyReport(
                report_date=report_date,
                report_content=report_content,
                opportunity_density_analysis=ods_analysis,
                weight_adjustments=weight_adjustment,
                explainability_check=explainability_check,
                applied=False,
            )
        except Exception as e:
            if self.debug:
                print(f"[DEEPSEEK][ERROR] {type(e).__name__}: {e}")
            return None
    
    def validate_ai_decision(
        self,
        decision: WeightAdjustment,
    ) -> Tuple[bool, str]:
        """
        验证 AI 决策
        
        Args:
            decision: AI 的权重调整决策
        
        Returns:
            (valid, reason)
            - valid=True: 决策有效
            - valid=False: 决策无效，reason 说明原因
        """
        # 1. 验证权重
        valid, reason = validate_weights(decision.new_weights)
        if not valid:
            return (False, f"权重验证失败: {reason}")
        
        # 2. 检查可解释性
        if not decision.explainability_check:
            return (False, "可解释性检查失败：推理过程不可解释")
        
        # 3. 检查推理是否为空
        if not decision.reasoning or len(decision.reasoning.strip()) < 10:
            return (False, "推理过程为空或过短")
        
        # 4. 检查是否回答了 ODS 问题
        if not decision.opportunity_density_impact or decision.opportunity_density_impact == "unknown":
            return (False, "未回答机会密度影响问题")
        
        return (True, "")


__all__ = [
    "DeepSeekConstrained",
    "WeightAdjustment",
    "DailyReport",
]

