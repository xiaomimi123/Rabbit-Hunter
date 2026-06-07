"""
DeepSeek AI 裁决与学习（Rabbit Hunter V4.2）

定位：
- 使用 deepseek-chat（默认）对"是否继续参与/是否放行"做裁决
- V4.2 升级：具备学习能力，从历史数据中学习并改进决策
- 不预测方向，只输出 ai_score(0-1) / ai_allowed / ai_reason / ai_version

接口（OpenAI 兼容）：
- POST {base_url}/chat/completions
- base_url 默认：https://api.deepseek.com
参考文档：https://api-docs.deepseek.com/zh-cn/
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

# 尝试导入学习器（支持相对导入和绝对导入）
try:
    # 先尝试相对导入（如果 deepseek_ai.py 在 scripts/ 目录下）
    from deepseek_ai_learner import DeepSeekLearner
    LEARNER_AVAILABLE = True
except ImportError:
    try:
        # 再尝试绝对导入
        from scripts.deepseek_ai_learner import DeepSeekLearner
        LEARNER_AVAILABLE = True
    except ImportError:
        LEARNER_AVAILABLE = False
        DeepSeekLearner = None


@dataclass(frozen=True)
class DeepSeekDecision:
    ai_score: float
    ai_allowed: bool
    ai_reason: str
    ai_version: str


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:  # noqa: BLE001
        return default


class DeepSeekJudge:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat",
        timeout_seconds: float = 12.0,
        max_tokens: int = 200,
        enable_learning: bool = True,
        supabase: Optional[Any] = None,
    ) -> None:
        # v0.5.6: DB > env > None。DB 里 provider=deepseek+enabled=true 才用 DB key。
        if api_key:
            self.api_key = api_key
            _db_model = None
        else:
            self.api_key, _db_model = self._resolve_from_db_or_env()
        self.base_url = (base_url or os.environ.get("DEEPSEEK_API_BASE") or "https://api.deepseek.com").rstrip("/")
        self.model = os.environ.get("DEEPSEEK_MODEL") or _db_model or model
        self.timeout_seconds = float(os.environ.get("DEEPSEEK_TIMEOUT", timeout_seconds))
        self.max_tokens = int(os.environ.get("DEEPSEEK_MAX_TOKENS", str(max_tokens)))
        self.debug = os.environ.get("DEEPSEEK_DEBUG", "0") in ("1", "true", "True")
        
        # V4.2 学习功能
        self.enable_learning = enable_learning and os.environ.get("DEEPSEEK_LEARNING_ENABLED", "1") in ("1", "true", "True")
        self.learner = None
        if self.enable_learning and LEARNER_AVAILABLE and DeepSeekLearner is not None:
            try:
                self.learner = DeepSeekLearner(supabase=supabase)
            except Exception:
                self.learner = None

    def is_ready(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _resolve_from_db_or_env():
        """v0.5.6: SettingsPage 保存到 DB 的 ai_config 优先，没存才回 DEEPSEEK_API_KEY env。"""
        try:
            try:
                from ai_config_manager import resolve_active_ai  # type: ignore[import-not-found]
            except ImportError:
                from scripts.ai_config_manager import resolve_active_ai  # type: ignore[import-not-found]
            cfg = resolve_active_ai(expected_provider="deepseek")
            if cfg.get("enabled") and cfg.get("api_key"):
                return cfg["api_key"], cfg.get("model") or None
        except Exception:
            pass
        return os.environ.get("DEEPSEEK_API_KEY"), None

    def _endpoint(self) -> str:
        # DeepSeek 文档：base_url 可设为 https://api.deepseek.com 或 https://api.deepseek.com/v1
        # 为兼容两种情况，这里直接拼 /chat/completions
        return f"{self.base_url}/chat/completions"

    def judge(self, features: Dict[str, Any]) -> Optional[DeepSeekDecision]:
        """
        输入：ai_training_data 行（或其子集）
        输出：DeepSeekDecision（失败返回 None）
        
        V4.2 升级：如果启用学习功能，会自动从历史数据中学习并增强特征
        """
        if not self.is_ready():
            return None
        
        # V4.2 学习功能：用历史数据丰富特征
        if self.learner:
            try:
                features = self.learner.enrich_features_with_history(features, days=7)
            except Exception:
                # 如果学习功能失败，继续使用原始特征
                pass

        # V4.2 增强系统提示词：加入历史学习能力
        if self.learner and features.get("historical_context"):
            hist_ctx = features.get("historical_context", {})
            hist_win_rate = hist_ctx.get("win_rate", 0.0)
            hist_avg_return = hist_ctx.get("avg_return", 0.0)
            phase_stats = hist_ctx.get("phase_specific_stats", {})
            
            learning_context = ""
            if hist_ctx.get("paper_trades_count", 0) > 0:
                learning_context = f"\n历史学习数据（最近7天）：\n"
                learning_context += f"- 该币种历史胜率: {hist_win_rate:.1%}\n"
                learning_context += f"- 该币种平均收益: {hist_avg_return:.2%}\n"
                if phase_stats:
                    learning_context += f"- 当前阶段({features.get('market_phase')})历史平均分数: {phase_stats.get('avg_score', 0.0):.2f}\n"
                learning_context += "- 基于历史表现调整决策：如果历史胜率高，可以适当放宽标准；如果历史表现差，应该更严格。\n"
            
            # 使用纯字符串拼接，不使用元组（因为需要插入 learning_context）
            system_prompt = "你是 Rabbit Hunter V4.2 的智能交易裁决器（具备学习能力）。\n"
            system_prompt += "你必须严格输出 JSON，不要输出任何多余文字。\n"
            system_prompt += "输出字段：ai_allowed(boolean)、ai_score(number 0-1)、ai_reason(string 简短原因)。\n"
            system_prompt += learning_context
            system_prompt += "裁决原则：\n"
            system_prompt += "- P3A 且 kill_zone 明确且 exit_clarity_score 高：倾向允许\n"
            system_prompt += "- P1/P4 或 exit_clarity_score 低 或 confidence_level 过高（反身性刹车）：倾向拒绝\n"
            system_prompt += "- 结合历史表现：如果该币种历史胜率高，可以适当提高分数；如果历史表现差，应该降低分数\n"
            system_prompt += "- 不要预测涨跌方向，只判断\"继续参与概率\"。"
        else:
            system_prompt = (
                "你是 Rabbit Hunter V4.2 的交易裁决器（不预测方向，只裁决是否继续参与/是否放行）。\n"
                "你必须严格输出 JSON，不要输出任何多余文字。\n"
                "输出字段：ai_allowed(boolean)、ai_score(number 0-1)、ai_reason(string 简短原因)。\n"
                "裁决原则：\n"
                "- P3A 且 kill_zone 明确且 exit_clarity_score 高：倾向允许\n"
                "- P1/P4 或 exit_clarity_score 低 或 confidence_level 过高（反身性刹车）：倾向拒绝\n"
                "- 不要预测涨跌方向，只判断\"继续参与概率\"。"
            )

        user_payload = {
            # 只给关键特征，控制 token
            "symbol": features.get("symbol"),
            "funding_rate": features.get("funding_rate"),
            "long_short_ratio": features.get("long_short_ratio"),
            "oi_change_1h": features.get("oi_change_1h"),
            "price_change_1h": features.get("price_change_1h"),
            "cvd_15m": features.get("cvd_15m"),
            "cvd_1h": features.get("cvd_1h"),
            "cvd_value": features.get("cvd_value"),
            "market_phase": features.get("market_phase"),
            "kill_zone_signal": features.get("kill_zone_signal"),
            "exit_clarity_score": features.get("exit_clarity_score"),
            "confidence_level": features.get("confidence_level"),
            "price_breakout": features.get("price_breakout"),
        }

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "stream": False,
            "max_tokens": self.max_tokens,
            # OpenAI 兼容 JSON output（DeepSeek 文档有 JSON Output 指南）
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            r = requests.post(self._endpoint(), headers=headers, json=body, timeout=self.timeout_seconds)
            if r.status_code >= 400:
                if self.debug:
                    # 不打印任何敏感信息；仅输出状态码与简短错误
                    msg = (r.text or "")[:300].replace("\n", " ")
                    print(f"[DEEPSEEK][HTTP {r.status_code}] {msg}")
                return None
            data = r.json()
            content = data["choices"][0]["message"]["content"]

            # content 应该是 JSON 字符串
            obj = json.loads(content)
            ai_allowed = bool(obj.get("ai_allowed"))
            ai_score = max(0.0, min(1.0, _safe_float(obj.get("ai_score"), 0.0)))
            ai_reason = str(obj.get("ai_reason") or "").strip()[:240]

            if not ai_reason:
                ai_reason = f"deepseek({self.model}) score={ai_score:.3f}"

            return DeepSeekDecision(
                ai_allowed=ai_allowed,
                ai_score=ai_score,
                ai_reason=ai_reason,
                ai_version=self.model,
            )
        except Exception as e:  # noqa: BLE001
            if self.debug:
                print(f"[DEEPSEEK][ERROR] {type(e).__name__}: {e}")
            return None


__all__ = ["DeepSeekJudge", "DeepSeekDecision"]
