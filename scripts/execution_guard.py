"""
Execution Guard (Rabbit Hunter 4.0)

包含：
- Anti-Confidence Engine（反身性压制）：当系统“最想加仓”时踩刹车

说明：
- 本模块不直接下单，只输出“自信度等级/仓位系数建议”
- consecutive_wins / daily_profit 目前从 system_settings 读取（若无则视为 0）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

try:
    from supabase import Client
except Exception:  # noqa: BLE001
    Client = object  # type: ignore


@dataclass(frozen=True)
class AntiConfidenceConfig:
    win_streak_threshold: int = 2
    daily_profit_threshold: float = 100.0
    penalty_step: int = 15  # 触发一次加多少“自信度压力”
    max_level: int = 100


class AntiConfidenceEngine:
    def __init__(self, supabase: Optional[Client] = None, config: Optional[AntiConfidenceConfig] = None) -> None:
        self.supabase = supabase
        self.config = config or AntiConfidenceConfig()

    def _read_setting(self, key: str) -> Optional[str]:
        if self.supabase is None:
            return None
        try:
            resp = self.supabase.table("system_settings").select("value").eq("key", key).limit(1).execute()
            if resp.data:
                return resp.data[0].get("value")
            return None
        except Exception:  # noqa: BLE001
            return None

    def get_state(self) -> Tuple[int, float]:
        """
        返回 (consecutive_wins, daily_profit)
        说明：
        - 这两个值目前假设由外部系统/人工写入 system_settings
        """
        wins_raw = self._read_setting("anti_confidence_consecutive_wins")
        profit_raw = self._read_setting("anti_confidence_daily_profit")

        try:
            wins = int(wins_raw) if wins_raw is not None else 0
        except Exception:  # noqa: BLE001
            wins = 0

        try:
            profit = float(profit_raw) if profit_raw is not None else 0.0
        except Exception:  # noqa: BLE001
            profit = 0.0

        return wins, profit

    def compute_confidence_level(self, base_level: int) -> int:
        """
        输出 confidence_level（0-100，越高越要降低仓位）。

        base_level 通常来自策略置信度（0-100）。
        """
        base = max(0, min(self.config.max_level, int(base_level)))
        wins, profit = self.get_state()

        extra = 0
        if wins >= self.config.win_streak_threshold:
            extra += self.config.penalty_step
        if profit >= self.config.daily_profit_threshold:
            extra += self.config.penalty_step

        return max(0, min(self.config.max_level, base + extra))

    @staticmethod
    def position_scale_from_confidence(confidence_level: int) -> float:
        """
        将 confidence_level 映射为仓位系数（0.3 ~ 1.0）
        - 低自信度：允许正常仓位
        - 高自信度（“过自信压力”高）：强制降仓
        """
        c = max(0, min(100, int(confidence_level)))
        # 0 -> 1.0, 100 -> 0.3（线性）
        return 1.0 - 0.7 * (c / 100.0)


__all__ = ["AntiConfidenceEngine", "AntiConfidenceConfig"]


