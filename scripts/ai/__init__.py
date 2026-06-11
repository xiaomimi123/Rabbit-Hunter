"""OpenAI-powered trading decision layer for Rabbit Hunter."""
from .trading_assistant import TradingAssistant, AIDecision
from .guardrails import clamp_ai_result

try:
    from .memory_uploader import log_trade_result, upload_trade_history
    __all__ = ["TradingAssistant", "AIDecision", "clamp_ai_result",
               "log_trade_result", "upload_trade_history"]
except ImportError:
    __all__ = ["TradingAssistant", "AIDecision", "clamp_ai_result"]
