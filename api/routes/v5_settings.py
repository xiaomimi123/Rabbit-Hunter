"""/api/v5/settings GET/PATCH。

读 system_settings 表;敏感字段(API key)在返回时掩码 "sk-****xxxx"。
PATCH 显式 "" 表示清空。
"""
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter

from api.schemas.v5_settings import (
    SettingsResponse, SettingsPatchRequest,
    TestAIRequest, TestAIResponse,
)


router = APIRouter(prefix="/api/v5", tags=["settings"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def _read_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute(
        "SELECT value FROM system_settings WHERE key=? ORDER BY rowid DESC LIMIT 1",
        (key,),
    ).fetchone()
    if row is None:
        return default
    return row[0] or default


def _write_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO system_settings (key, value, created_at) VALUES (?, ?, datetime('now'))",
        (key, value),
    )


def _mask(key: str) -> str:
    """sk-abcdefghijklmnop → sk-****mnop。"""
    if not key:
        return ""
    if len(key) < 8:
        return "****"
    prefix = key[:3] if key.startswith("sk-") else key[:3]
    suffix = key[-4:]
    return f"{prefix}****{suffix}"


@router.get("/settings", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    db = _db()
    conn = sqlite3.connect(db)
    try:
        # API keys: DB-only for masked display. Env keys are not shown in the
        # UI (they were never saved via SettingsPage, so masking them would be
        # misleading and breaks tests that delete env vars after import).
        openai_key = _read_setting(conn, "openai_api_key")
        deepseek_key = _read_setting(conn, "deepseek_api_key")
        # For active_provider resolution we still honour env fallback.
        openai_key_eff = openai_key or os.environ.get("OPENAI_API_KEY", "")
        deepseek_key_eff = deepseek_key or os.environ.get("DEEPSEEK_API_KEY", "")

        exchange_raw = _read_setting(conn, "exchange") or os.environ.get("EXCHANGE", "okx")
        exchange = "binance" if exchange_raw.lower() == "binance" else "okx"

        system_mode_raw = _read_setting(conn, "system_state").upper()
        system_mode = "LIVE" if system_mode_raw == "LIVE" else "SHADOW"

        deepseek_enabled = (_read_setting(conn, "deepseek_enabled") or
                            os.environ.get("DEEPSEEK_ENABLED", "false")).lower() in ("1", "true")
        enable_auto_trading = (_read_setting(conn, "enable_auto_trading") or
                               os.environ.get("ENABLE_AUTO_TRADING", "false")).lower() in ("1", "true")
        ai_fail_open = (_read_setting(conn, "ai_fail_open") or
                        os.environ.get("AI_FAIL_OPEN", "false")).lower() in ("1", "true")
        sl_tp_fail_open = (_read_setting(conn, "sl_tp_fail_open") or
                           os.environ.get("SL_TP_FAIL_OPEN", "false")).lower() in ("1", "true")

        if deepseek_enabled and deepseek_key_eff:
            active_provider, active_model = "deepseek", os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        elif openai_key_eff:
            active_provider, active_model = "openai", os.environ.get("OPENAI_TRADING_MODEL", "gpt-4o")
        else:
            active_provider, active_model = None, None

        assistant_id = _read_setting(conn, "openai_assistant_id") or os.environ.get("OPENAI_ASSISTANT_ID") or None
        vector_store_id = _read_setting(conn, "openai_vector_store_id") or os.environ.get("OPENAI_VECTOR_STORE_ID") or None
    finally:
        conn.close()

    return SettingsResponse(
        exchange=exchange,
        openai_api_key_masked=_mask(openai_key),
        openai_assistant_id=assistant_id,
        openai_vector_store_id=vector_store_id,
        deepseek_api_key_masked=_mask(deepseek_key),
        deepseek_enabled=deepseek_enabled,
        active_ai_provider=active_provider,
        active_chat_model=active_model,
        system_mode=system_mode,
        enable_auto_trading=enable_auto_trading,
        ai_fail_open=ai_fail_open,
        sl_tp_fail_open=sl_tp_fail_open,
    )


@router.post("/settings/test-ai", response_model=TestAIResponse)
async def test_ai(req: TestAIRequest) -> TestAIResponse:
    """测试 AI 连接是否可用 — 发一次最小推理调用,返回延时 + 错误诊断。

    优先级:request 里的 candidate key > DB > env。
    """
    import time
    db = _db()
    conn = sqlite3.connect(db)
    try:
        # 决定用哪个 provider + 哪个 key
        candidate_deepseek = (req.deepseek_api_key or "").strip()
        candidate_openai = (req.openai_api_key or "").strip()

        if req.provider:
            provider = req.provider
        elif candidate_deepseek:
            provider = "deepseek"
        elif candidate_openai:
            provider = "openai"
        else:
            # 从 DB 决定
            deepseek_enabled = (_read_setting(conn, "deepseek_enabled") or
                                os.environ.get("DEEPSEEK_ENABLED", "false")).lower() in ("1", "true")
            deepseek_db = _read_setting(conn, "deepseek_api_key")
            openai_db = _read_setting(conn, "openai_api_key")
            if deepseek_enabled and (deepseek_db or os.environ.get("DEEPSEEK_API_KEY")):
                provider = "deepseek"
            elif openai_db or os.environ.get("OPENAI_API_KEY"):
                provider = "openai"
            else:
                return TestAIResponse(
                    ok=False,
                    error_type="no_key_configured",
                    message="没有配置 API key — DeepSeek 和 OpenAI 都为空",
                )

        # 获取实际要用的 key
        if provider == "deepseek":
            api_key = candidate_deepseek or _read_setting(conn, "deepseek_api_key") or os.environ.get("DEEPSEEK_API_KEY", "")
            model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
            base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        else:
            api_key = candidate_openai or _read_setting(conn, "openai_api_key") or os.environ.get("OPENAI_API_KEY", "")
            model = os.environ.get("OPENAI_TRADING_MODEL", "gpt-4o-mini")
            base_url = None
    finally:
        conn.close()

    if not api_key:
        return TestAIResponse(
            ok=False, provider=provider, model=model,
            error_type="no_key_configured",
            message=f"{provider} 的 API key 为空",
        )

    # 调最小推理:1 个 token,问"Say ok"
    try:
        import openai as _openai
    except ImportError:
        return TestAIResponse(
            ok=False, provider=provider, model=model,
            error_type="unknown",
            message="openai SDK 未安装(容器内应有,可能镜像有问题)",
        )

    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = _openai.AsyncOpenAI(**kwargs)

    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say ok"}],
            max_tokens=4,
            temperature=0.0,
        )
        latency_ms = int((time.time() - t0) * 1000)
        text = (resp.choices[0].message.content or "").strip() if resp.choices else ""
        return TestAIResponse(
            ok=True, provider=provider, model=model,
            latency_ms=latency_ms, response_text=text,
            message=f"连接正常 · 延时 {latency_ms}ms",
        )
    except _openai.AuthenticationError as e:
        return TestAIResponse(
            ok=False, provider=provider, model=model,
            latency_ms=int((time.time() - t0) * 1000),
            error_type="auth_failed",
            message=f"API key 鉴权失败:key 无效或已删除",
        )
    except _openai.RateLimitError as e:
        return TestAIResponse(
            ok=False, provider=provider, model=model,
            latency_ms=int((time.time() - t0) * 1000),
            error_type="rate_limit",
            message="请求频率过高(rate limit),稍等再试",
        )
    except _openai.APIStatusError as e:
        # 包括 402 余额不足
        code = getattr(e, "status_code", None) or 0
        err_type = "insufficient_balance" if code == 402 else "unknown"
        if "insufficient" in str(e).lower() or "balance" in str(e).lower():
            err_type = "insufficient_balance"
        msg_short = f"账户余额不足(HTTP 402)— 去 {provider} dashboard 充值" if err_type == "insufficient_balance" else f"API HTTP {code}: {str(e)[:200]}"
        return TestAIResponse(
            ok=False, provider=provider, model=model,
            latency_ms=int((time.time() - t0) * 1000),
            error_type=err_type,
            message=msg_short,
        )
    except Exception as e:
        return TestAIResponse(
            ok=False, provider=provider, model=model,
            latency_ms=int((time.time() - t0) * 1000),
            error_type="network",
            message=f"{type(e).__name__}: {str(e)[:200]}",
        )


@router.patch("/settings", response_model=SettingsResponse)
async def patch_settings(req: SettingsPatchRequest) -> SettingsResponse:
    db = _db()
    conn = sqlite3.connect(db)
    try:
        if req.exchange is not None:
            _write_setting(conn, "exchange", req.exchange)
        if req.openai_api_key is not None:
            _write_setting(conn, "openai_api_key", req.openai_api_key)
        if req.openai_assistant_id is not None:
            _write_setting(conn, "openai_assistant_id", req.openai_assistant_id)
        if req.deepseek_api_key is not None:
            _write_setting(conn, "deepseek_api_key", req.deepseek_api_key)
        if req.deepseek_enabled is not None:
            _write_setting(conn, "deepseek_enabled", "true" if req.deepseek_enabled else "false")
        if req.system_mode is not None:
            _write_setting(conn, "system_state", req.system_mode)
        if req.enable_auto_trading is not None:
            _write_setting(conn, "enable_auto_trading",
                           "true" if req.enable_auto_trading else "false")
        if req.ai_fail_open is not None:
            _write_setting(conn, "ai_fail_open", "true" if req.ai_fail_open else "false")
        if req.sl_tp_fail_open is not None:
            _write_setting(conn, "sl_tp_fail_open", "true" if req.sl_tp_fail_open else "false")
        conn.commit()
    finally:
        conn.close()
    return await get_settings()
