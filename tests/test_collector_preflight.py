"""collector_main 启动自检测试。"""
import pytest


def test_preflight_missing_okx_key_raises_when_auto_trading():
    """开启 auto_trading 但没 broker key → 自检失败。"""
    from scripts.tasks.collector_main import preflight_check

    issues = preflight_check(
        enable_auto_trading=True,
        binance_api_key="", okx_api_key="",
        openai_key="sk-xxx", ai_enabled=True,
    )
    assert any("API key" in i for i in issues)


def test_preflight_passes_in_shadow_no_key_needed():
    from scripts.tasks.collector_main import preflight_check
    issues = preflight_check(
        enable_auto_trading=False,
        binance_api_key="", okx_api_key="",
        openai_key="sk-xxx", ai_enabled=True,
    )
    assert issues == []


def test_preflight_warns_ai_enabled_no_key():
    from scripts.tasks.collector_main import preflight_check
    issues = preflight_check(
        enable_auto_trading=False,
        binance_api_key="", okx_api_key="",
        openai_key="", ai_enabled=True,
    )
    assert any("OPENAI" in i for i in issues)
