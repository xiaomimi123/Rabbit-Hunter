"""
在线推理：AI Judge（Rabbit Hunter 4.0）

输入：ai_training_data 的一行特征（dict）
输出：ai_score/ai_allowed/ai_reason/ai_version

特性：
- 如果模型文件不存在：返回 None（collector 会写空，不影响运行）
- 推理不依赖 sklearn（读取 npz 的 w/b）
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from ai_judge_model import AIJudgeResult, DEFAULT_AI_VERSION, build_feature_vector


class AIJudge:
    def __init__(self, model_path: str | None = None, allowed_threshold: float = 0.65) -> None:
        self.model_path = model_path or os.environ.get("AI_JUDGE_MODEL_PATH") or "models/ai_judge_lr_v1.npz"
        self.allowed_threshold = float(allowed_threshold)
        self._loaded = False
        self._w: Optional[np.ndarray] = None
        self._b: float = 0.0
        self._version: str = DEFAULT_AI_VERSION
        self._auc: float = 0.0

    def is_ready(self) -> bool:
        return self._loaded and self._w is not None

    def load(self) -> bool:
        path = Path(self.model_path)
        if not path.exists():
            return False
        data = np.load(path, allow_pickle=True)
        self._w = np.array(data["w"], dtype=np.float64)
        self._b = float(np.array(data["b"], dtype=np.float64).reshape(-1)[0])
        try:
            self._auc = float(np.array(data.get("auc", [0.0]), dtype=np.float64).reshape(-1)[0])
        except Exception:
            self._auc = 0.0
        try:
            self._version = str(np.array(data.get("version", [DEFAULT_AI_VERSION])).reshape(-1)[0])
        except Exception:
            self._version = DEFAULT_AI_VERSION
        self._loaded = True
        return True

    @staticmethod
    def _sigmoid(z: float) -> float:
        # 数值稳定
        if z >= 0:
            ez = math.exp(-z)
            return 1.0 / (1.0 + ez)
        ez = math.exp(z)
        return ez / (1.0 + ez)

    def predict(self, row: Dict[str, Any]) -> Optional[AIJudgeResult]:
        if not self.is_ready():
            if not self.load():
                return None
        assert self._w is not None

        x = np.array(build_feature_vector(row), dtype=np.float64)
        if x.shape[0] != self._w.shape[0]:
            return None

        z = float(np.dot(self._w, x) + self._b)
        score = self._sigmoid(z)
        allowed = bool(score >= self.allowed_threshold)

        reason = f"AIJudge={self._version} score={score:.3f} thr={self.allowed_threshold:.2f} auc≈{self._auc:.3f}"
        return AIJudgeResult(ai_score=float(score), ai_allowed=allowed, ai_reason=reason, ai_version=self._version)


__all__ = ["AIJudge"]


