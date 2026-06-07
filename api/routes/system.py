"""
系统路由

端点:
  GET    /health
  GET    /
  GET    /api/v43/binance-config
  POST   /api/v43/binance-config
  DELETE /api/v43/binance-config
  GET    /api/v43/account/balance
  GET    /api/v43/ai-evolution
  GET    /api/v43/accuracy-heatmap
  POST   /api/v43/validate-entry
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from api.dependencies import get_supabase, get_supabase_optional
from api.services.market_service import build_ccxt_config

router = APIRouter(tags=["system"])


# ============================================
# Pydantic 模型（系统路由专用）
# ============================================


class BinanceConfigRequest(BaseModel):
    api_key: str
    api_secret: str
    testnet: bool = False
    leverage: int = 10


class BinanceConfigResponse(BaseModel):
    status: str
    code: int
    message: str
    configured: bool
    testnet: bool
    api_key_masked: Optional[str] = None
    leverage: Optional[int] = None


class EntryValidationRequest(BaseModel):
    symbol: str
    leverage: int = 10
    risk: float = 2.0


class EntryValidationResponse(BaseModel):
    status: str
    code: int
    data: dict


# ============================================
# 健康检查 & 根端点
# ============================================


@router.get("/health")
async def health_check(supabase=Depends(get_supabase_optional)):
    """健康检查端点"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "supabase_connected": supabase is not None,
    }


@router.get("/")
async def root():
    """根端点"""
    return {
        "message": "Rabbit Hunter API",
        "version": "4.3.0",
        "docs": "/docs",
    }


# ============================================
# 当前 active exchange（v0.5.2）
# ============================================


# ============================================
# Paper Trades 查询 (v0.5.4) — SHADOW 模式虚拟仓位
# ============================================


@router.get("/api/v43/paper-trades")
async def get_paper_trades(
    status_filter: str = Query("all", alias="status"),
    limit: int = Query(200, ge=1, le=1000),
    supabase=Depends(get_supabase_optional),
) -> dict:
    """所有虚拟仓位 + KPI 聚合。status=open|closed|all。"""
    try:
        q = supabase.table("paper_trades").select("*").order("created_at", desc=True).limit(int(limit))
        if status_filter.lower() == "open":
            q = q.eq("status", "OPEN")
        elif status_filter.lower() == "closed":
            q = q.eq("status", "CLOSED")
        r = q.execute()
        rows = r.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读 paper_trades 失败: {e}")

    # 聚合 — 仅基于 CLOSED 算胜率 / PnL
    closed = [x for x in rows if (x.get("status") or "").upper() == "CLOSED"]
    open_rows = [x for x in rows if (x.get("status") or "").upper() == "OPEN"]
    wins = [x for x in closed if (x.get("pnl") or 0) > 0]
    losses = [x for x in closed if (x.get("pnl") or 0) < 0]

    total_pnl = sum(float(x.get("pnl") or 0) for x in closed)
    win_rate = (len(wins) / len(closed) * 100) if closed else 0.0
    avg_hold = (
        sum(float(x.get("holding_hours") or 0) for x in closed) / len(closed)
    ) if closed else 0.0

    return {
        "status": "success",
        "data": rows,
        "kpi": {
            "total_closed":      len(closed),
            "total_open":        len(open_rows),
            "wins":              len(wins),
            "losses":            len(losses),
            "win_rate_pct":      round(win_rate, 2),
            "total_pnl_usdt":    round(total_pnl, 4),
            "avg_holding_hours": round(avg_hold, 2),
        },
    }


@router.get("/api/v43/system-state")
async def get_system_state(supabase=Depends(get_supabase_optional)) -> dict:
    """前端 sidebar StatusRow 用：collector_running / api_online / testnet。

    collector 是否在跑用 market_snapshot 最近写入时间推断（≤120s = 在跑）。
    """
    api_online = True  # 能进到这里就说明 api 在响应
    collector_running = False
    last_collector_write = None
    try:
        from datetime import datetime, timezone, timedelta
        r = (
            supabase.table("market_snapshot")
            .select("updated_at")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if r.data:
            last_str = r.data[0].get("updated_at") or ""
            try:
                last_dt = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - last_dt).total_seconds()
                collector_running = age <= 120  # 2 分钟内有写就算活
                last_collector_write = last_str
            except Exception:
                pass
    except Exception:
        pass

    # 当前 active exchange 的 testnet 状态
    is_testnet = False
    try:
        from scripts.exchange_config_manager import get_exchange_config_manager
        mgr = get_exchange_config_manager(supabase)
        cfg = mgr.get_config(mgr.get_active_exchange())
        if cfg:
            is_testnet = bool(cfg.get("testnet", False))
    except Exception:
        pass

    return {
        "api_online":           api_online,
        "collector_running":    collector_running,
        "last_collector_write": last_collector_write,
        "testnet":              is_testnet,
    }


# ============================================
# SHADOW / LIVE 模式（v0.5.4）— 真持久化的系统状态
# ============================================
#
# 之前 SHADOW/LIVE 只是前端 useUIStore 的 localStorage 字段，后端完全不认。
# 这里把 system_state 行写进 system_settings 表，让 scorer / API trade 路由
# 都能读到 → 真正实现"影子模式不下真单"。


@router.get("/api/v43/system/mode")
async def get_system_mode(supabase=Depends(get_supabase_optional)) -> dict:
    """读当前 SHADOW/LIVE 模式（DB 持久化，默认 SHADOW = 安全姿态）。"""
    state = "SHADOW"
    try:
        r = (
            supabase.table("system_settings")
            .select("value")
            .eq("key", "system_state")
            .execute()
        )
        if r.data:
            v = (r.data[0].get("value") or "").strip().upper()
            if v in ("SHADOW", "LIVE"):
                state = v
    except Exception:
        pass
    return {"mode": state, "is_live": state == "LIVE", "is_shadow": state == "SHADOW"}


class SystemModeRequest(BaseModel):
    mode: str   # "SHADOW" | "LIVE"


@router.post("/api/v43/system/mode")
async def set_system_mode(
    body: SystemModeRequest,
    supabase=Depends(get_supabase_optional),
) -> dict:
    """切换 SHADOW/LIVE。切到 LIVE 要求当前 active exchange 已经鉴权可用。"""
    target = body.mode.strip().upper()
    if target not in ("SHADOW", "LIVE"):
        raise HTTPException(status_code=400, detail=f"mode 必须是 SHADOW 或 LIVE，收到 {body.mode!r}")

    # 切到 LIVE 时检查交易器鉴权 — 防止 OKX passphrase 错的情况下用户切实盘
    if target == "LIVE":
        try:
            from scripts.exchange_factory import get_trader
            trader = get_trader()
            bal = trader.fetch_balance() if hasattr(trader, "fetch_balance") else {}
            if bal.get("error"):
                raise HTTPException(
                    status_code=422,
                    detail=f"无法切换到 LIVE：交易器鉴权失败 — {bal['error'][:120]}",
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"无法切换到 LIVE：{e}")

    try:
        supabase.table("system_settings").upsert(
            {"key": "system_state", "value": target}, on_conflict="key",
        ).execute()
        return {"mode": target, "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"切换失败: {e}")


@router.get("/api/v43/system/exchange")
async def get_active_exchange_endpoint(supabase=Depends(get_supabase_optional)) -> dict:
    """返回当前 active exchange（OKX / Binance）。前端顶栏徽章用。
    v0.5.3：DB > env，让 SettingsPage 改的值立刻反映。"""
    try:
        from scripts.exchange_factory import get_active_exchange  # type: ignore[import-not-found]
        name = get_active_exchange()
    except Exception:
        import os as _os
        name = (_os.environ.get("EXCHANGE", "okx") or "okx").lower()

    # testnet 从该 exchange 的配置里读，DB > env
    is_testnet = False
    try:
        from scripts.exchange_config_manager import get_exchange_config_manager  # type: ignore[import-not-found]
        cfg = get_exchange_config_manager(supabase).get_config(name)
        if cfg:
            is_testnet = bool(cfg.get("testnet", False))
    except Exception:
        import os as _os
        is_testnet = _os.environ.get(
            "OKX_TESTNET" if name == "okx" else "BINANCE_TESTNET", "false"
        ).lower() in ("1", "true")

    return {
        "exchange": name,
        "label":    name.upper(),
        "testnet":  is_testnet,
    }


# ============================================
# 交易所配置（多 exchange — v0.5.3）
# ============================================


class ExchangeConfigRequest(BaseModel):
    api_key:        str
    api_secret:     str
    api_passphrase: str = ""
    testnet:        bool = False
    leverage:       int  = 10


@router.get("/api/v43/exchange-config/status")
async def get_all_exchange_status(supabase=Depends(get_supabase_optional)) -> dict:
    """SettingsPage 一次拉所有 exchange 配置状态 + active。"""
    try:
        from scripts.exchange_config_manager import get_exchange_config_manager
        mgr = get_exchange_config_manager(supabase)
        return {"status": "success", "data": mgr.get_status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取 exchange 状态失败: {e}")


class ActiveExchangeRequest(BaseModel):
    exchange: str


# 注意：FastAPI 路由按声明顺序匹配 — `/active` 必须放在 `/{exchange}` 之前，
# 否则 'active' 会被当成 exchange 路径参数。


@router.post("/api/v43/exchange-config/active")
async def set_active_exchange_endpoint(
    body: ActiveExchangeRequest,
    supabase=Depends(get_supabase_optional),
) -> dict:
    """SettingsPage 上 OKX/Binance segmented 切换 — 把选择落地到 DB。"""
    from scripts.exchange_config_manager import get_exchange_config_manager
    result = get_exchange_config_manager(supabase).set_active_exchange(body.exchange.lower())
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "切换失败"))
    return {"status": "success", "data": result}


@router.post("/api/v43/exchange-config/{exchange}")
async def save_exchange_config(
    exchange: str,
    body: ExchangeConfigRequest,
    supabase=Depends(get_supabase_optional),
) -> dict:
    """保存 OKX 或 Binance 的配置。passphrase 仅 OKX 需要，Binance 传空字符串。"""
    from scripts.exchange_config_manager import get_exchange_config_manager, SUPPORTED_EXCHANGES
    if exchange.lower() not in SUPPORTED_EXCHANGES:
        raise HTTPException(status_code=400, detail=f"不支持的 exchange: {exchange}")
    if not body.api_key.strip() or not body.api_secret.strip():
        raise HTTPException(status_code=400, detail="api_key / api_secret 必填")
    if exchange.lower() == "okx" and not body.api_passphrase.strip():
        raise HTTPException(status_code=400, detail="OKX 需要 api_passphrase")
    mgr = get_exchange_config_manager(supabase)
    result = mgr.save_config(
        exchange=exchange.lower(),
        api_key=body.api_key, api_secret=body.api_secret,
        api_passphrase=body.api_passphrase, testnet=body.testnet, leverage=body.leverage,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "保存失败"))
    return {"status": "success", "data": result}


@router.delete("/api/v43/exchange-config/{exchange}")
async def delete_exchange_config(exchange: str, supabase=Depends(get_supabase_optional)) -> dict:
    from scripts.exchange_config_manager import get_exchange_config_manager
    result = get_exchange_config_manager(supabase).delete_config(exchange.lower())
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "删除失败"))
    return {"status": "success", "data": result}


# ============================================
# AI 大模型配置 — v0.5.3
# ============================================


class AIConfigRequest(BaseModel):
    provider: str             # 'openai' | 'deepseek' | 'anthropic' | 'disabled'
    api_key:  str = ""
    model:    str = ""
    enabled:  bool = True


@router.get("/api/v43/ai-config")
async def get_ai_config(supabase=Depends(get_supabase_optional)) -> dict:
    from scripts.ai_config_manager import get_ai_config_manager
    return {"status": "success", "data": get_ai_config_manager(supabase).get_status()}


@router.post("/api/v43/ai-config")
async def save_ai_config(body: AIConfigRequest, supabase=Depends(get_supabase_optional)) -> dict:
    from scripts.ai_config_manager import get_ai_config_manager, SUPPORTED_PROVIDERS
    if body.provider.lower() not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"未知 provider: {body.provider}")
    result = get_ai_config_manager(supabase).save_config(
        provider=body.provider.lower(), api_key=body.api_key,
        model=body.model, enabled=body.enabled,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "保存失败"))
    return {"status": "success", "data": result}


@router.delete("/api/v43/ai-config")
async def delete_ai_config(supabase=Depends(get_supabase_optional)) -> dict:
    from scripts.ai_config_manager import get_ai_config_manager
    result = get_ai_config_manager(supabase).delete_config()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "删除失败"))
    return {"status": "success", "data": result}


# ============================================
# 币安配置端点
# ============================================


@router.get("/api/v43/binance-config", response_model=BinanceConfigResponse)
async def get_binance_config(supabase=Depends(get_supabase)):
    """
    获取币安 API 配置状态

    返回配置状态（不返回实际的 Secret）。
    V4.5: 使用配置管理器（支持缓存和热加载）。
    """
    try:
        from scripts.binance_config_manager import get_config_manager  # type: ignore[import-not-found]

        config_manager = get_config_manager(supabase_client=supabase)
        config = config_manager.get_config()

        if config:
            api_key = config.get("api_key", "")
            api_key_masked = None
            if api_key and len(api_key) > 10:
                api_key_masked = f"{api_key[:5]}...{api_key[-5:]}"
            elif api_key:
                api_key_masked = f"{api_key[:3]}..."

            return BinanceConfigResponse(
                status="success",
                code=200,
                message="配置状态获取成功",
                configured=True,
                testnet=config.get("testnet", False),
                api_key_masked=api_key_masked,
                leverage=config.get("leverage", 10),
            )
        else:
            env_api_key = os.environ.get("BINANCE_API_KEY")
            env_api_secret = os.environ.get("BINANCE_API_SECRET")

            return BinanceConfigResponse(
                status="success",
                code=200,
                message="配置状态获取成功",
                configured=bool(env_api_key and env_api_secret),
                testnet=os.environ.get("BINANCE_TESTNET", "false").lower() in ("true", "1"),
            )
    except Exception:
        env_api_key = os.environ.get("BINANCE_API_KEY")
        env_api_secret = os.environ.get("BINANCE_API_SECRET")

        return BinanceConfigResponse(
            status="success",
            code=200,
            message="从环境变量读取配置",
            configured=bool(env_api_key and env_api_secret),
            testnet=os.environ.get("BINANCE_TESTNET", "false").lower() in ("true", "1"),
        )


@router.post("/api/v43/binance-config", response_model=BinanceConfigResponse)
async def save_binance_config(
    request: BinanceConfigRequest,
    supabase=Depends(get_supabase),
):
    """
    保存币安 API 配置

    将配置保存到 system_settings 表（加密存储 Secret）。
    V4.5: 使用配置管理器加密存储 Secret，支持热加载。
    """
    try:
        if not request.api_key or len(request.api_key) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API Key 格式无效",
            )

        if not request.api_secret or len(request.api_secret) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API Secret 格式无效",
            )

        api_key_trimmed = request.api_key.strip()
        api_key_lower = api_key_trimmed.lower()
        is_testnet_key = api_key_lower.startswith("lc")

        # 日志不打印 API Key 的任何前缀 — 即使 5 字符也会落入 stdout / 监控聚合系统
        print(f"[DEBUG] API Key 验证: testnet={request.testnet}, is_testnet_key={is_testnet_key}")

        if request.testnet and not is_testnet_key:
            print(f"[INFO] 测试网模式已启用，API Key 不以 'lc' 开头（这是正常的，某些测试网 Key 格式不同）")

        if not request.testnet and is_testnet_key:
            print(f"[WARNING] 实盘模式已启用，但 API Key 是测试网格式（以 lc 开头）")

        # 验证 API Key（尝试连接）
        try:
            import ccxt  # type: ignore[import-not-found]

            test_config = build_ccxt_config(
                testnet=request.testnet,
                api_key=request.api_key.strip(),
                api_secret=request.api_secret.strip(),
            )

            secret_has_whitespace = request.api_secret != request.api_secret.strip()
            if secret_has_whitespace:
                print(f"[WARNING] API Secret 包含首尾空格，已自动去除")

            test_exchange = ccxt.binanceusdm(test_config)

            if request.testnet:
                print(f"[DEBUG] 测试网验证: 使用直接 API 调用验证...")
                try:
                    import requests as req_lib
                    import hmac as hmac_lib
                    import hashlib
                    from urllib.parse import urlencode

                    timestamp = int(time.time() * 1000)
                    params = {"timestamp": timestamp}
                    query_string = urlencode(params)
                    signature = hmac_lib.new(
                        request.api_secret.strip().encode("utf-8"),
                        query_string.encode("utf-8"),
                        hashlib.sha256,
                    ).hexdigest()
                    params["signature"] = signature

                    headers = {"X-MBX-APIKEY": request.api_key.strip()}
                    url = f"https://testnet.binancefuture.com/fapi/v2/account?{urlencode(params)}"
                    response = req_lib.get(url, headers=headers, timeout=10)

                    if response.status_code == 200:
                        account = response.json()
                        balance = float(account.get("totalWalletBalance", 0))
                        print(f"[DEBUG] 测试网 API 验证成功！账户余额: {balance} USDT")
                    else:
                        error = response.json() if response.content else {}
                        error_code = error.get("code", "N/A")
                        error_msg = error.get("msg", response.text)
                        print(f"[DEBUG] 测试网 API 验证失败: HTTP {response.status_code}")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=(
                                f"测试网 API 验证失败：\n\n"
                                f"错误代码: {error_code}\n"
                                f"错误信息: {error_msg}\n\n"
                                f"请检查：\n"
                                f"   1. API Key 和 Secret 是否正确\n"
                                f"   2. 是否从 https://testnet.binancefuture.com/ 获取的测试网 API Key\n"
                                f"   3. API Key 权限是否足够（至少需要读取权限）"
                            ),
                        )
                except HTTPException:
                    raise
                except Exception as direct_error:
                    print(f"[DEBUG] 直接 API 调用失败: {direct_error}，尝试 CCXT...")
                    try:
                        test_exchange.load_markets()
                        test_exchange.fetch_balance()
                        print(f"[DEBUG] CCXT 验证成功")
                    except Exception as ccxt_error:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=(
                                f"API 验证失败：\n\n"
                                f"直接 API 调用错误: {str(direct_error)}\n"
                                f"CCXT 验证错误: {str(ccxt_error)}\n\n"
                                f"请检查 API Key 和 Secret 是否正确"
                            ),
                        )
            else:
                # 实盘使用 CCXT 验证
                try:
                    test_exchange.load_markets()
                    server_time = test_exchange.fetch_time()
                    local_time = int(time.time() * 1000)
                    time_diff = server_time - local_time
                    if abs(time_diff) > 1000:
                        print(f"[WARNING] 检测到时间差: {time_diff}ms，CCXT 将自动调整")
                except Exception as e:
                    print(f"[WARNING] 时间同步失败: {e}，继续验证...")

                try:
                    test_exchange.fetch_balance()
                    print(f"[DEBUG] 实盘 API 验证成功")
                except Exception as balance_error:
                    print(f"[DEBUG] 实盘 API 验证失败: {balance_error}")
                    raise balance_error

        except ccxt.NetworkError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"网络错误: {str(e)}（请检查网络连接）",
            )
        except ccxt.ExchangeError as e:
            error_msg = str(e)
            error_code = None
            try:
                if "{" in error_msg:
                    error_json = json.loads(error_msg.split("{")[1].split("}")[0] + "}")
                    error_code = error_json.get("code")
            except Exception:
                pass

            if "timestamp" in error_msg.lower() or "time" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"时间戳错误: {error_msg}（请同步系统时间或检查网络延迟）",
                )

            if error_code == -2008 or "Invalid Api-Key" in error_msg or "invalid api-key" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"API Key 验证失败 (错误代码: {error_code or 'N/A'}): {error_msg}",
                )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"API Key/Secret 验证失败: {error_msg}",
            )
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"API Key/Secret 验证失败: {str(e)}",
            )

        # 保存配置
        from scripts.binance_config_manager import get_config_manager  # type: ignore[import-not-found]

        config_manager = get_config_manager(supabase_client=supabase)
        leverage = getattr(request, "leverage", 10)

        success = config_manager.save_config(
            api_key=request.api_key,
            api_secret=request.api_secret,
            testnet=request.testnet,
            leverage=leverage,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="保存配置失败",
            )

        return BinanceConfigResponse(
            status="success",
            code=200,
            message="币安 API 配置已保存并验证成功（Secret 已加密）",
            configured=True,
            testnet=request.testnet,
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存配置失败: {str(e)}",
        )


@router.delete("/api/v43/binance-config")
async def delete_binance_config(supabase=Depends(get_supabase)):
    """
    删除币安 API 配置

    从 system_settings 表删除配置。
    V4.5: 使用配置管理器删除。
    """
    try:
        from scripts.binance_config_manager import get_config_manager  # type: ignore[import-not-found]

        config_manager = get_config_manager(supabase_client=supabase)
        success = config_manager.delete_config()

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="删除配置失败",
            )

        return {
            "status": "success",
            "code": 200,
            "message": "币安 API 配置已删除",
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除配置失败: {str(e)}",
        )


# ============================================
# 账户余额端点
# ============================================


@router.get("/api/v43/account/balance")
async def get_account_balance(supabase=Depends(get_supabase_optional)):
    """
    获取币安账户资金信息（简单版本）

    - V4.5: 优先从数据库读取配置（支持前端配置的 API Key）
    - 若数据库未配置，回退到环境变量
    - 若都未配置，返回模拟余额
    - 仅读取 USDT 合约账户的总权益与可用余额
    """
    api_key = None
    api_secret = None
    testnet = False

    try:
        from scripts.binance_config_manager import get_config_manager  # type: ignore[import-not-found]

        config_manager = get_config_manager(supabase_client=supabase)
        config = config_manager.get_config(force_refresh=True)

        if config:
            api_key = config.get("api_key")
            api_secret = config.get("api_secret")
            testnet = config.get("testnet", False)

            print(f"[DEBUG] /api/v43/account/balance: 从数据库读取配置")
            print(f"[DEBUG]   - testnet: {testnet}")
            print(f"[DEBUG]   - api_key 长度: {len(api_key) if api_key else 0}")
        else:
            print(f"[DEBUG] /api/v43/account/balance: 数据库未找到配置，回退到环境变量")
    except Exception as e:
        print(f"[WARNING] /api/v43/account/balance: 配置管理器读取失败: {e}")
        import traceback
        traceback.print_exc()

    # 回退到环境变量
    if not api_key or not api_secret:
        api_key = os.environ.get("BINANCE_API_KEY")
        api_secret = os.environ.get("BINANCE_API_SECRET")
        testnet = os.environ.get("BINANCE_TESTNET", "false").lower() in ("true", "1")
        if api_key:
            print(f"[DEBUG] /api/v43/account/balance: 从环境变量读取配置 - testnet={testnet}")

    if not api_key or not api_secret:
        return {
            "balance": 10000.0,
            "freeMargin": 10000.0,
            "availableBalance": 10000.0,
            "asset": "USDT",
            "testnet": False,
            "mode": "SIMULATION",
        }

    try:
        import ccxt  # type: ignore[import-not-found]

        api_key_clean = api_key.strip() if api_key else None
        api_secret_clean = api_secret.strip() if api_secret else None

        ccxt_config = build_ccxt_config(testnet, api_key_clean, api_secret_clean)

        if testnet:
            print(f"[DEBUG] /api/v43/account/balance: 使用直接 API 调用（测试网）")
            try:
                import requests as req_lib
                import hmac as hmac_lib
                import hashlib
                from urllib.parse import urlencode

                timestamp = int(time.time() * 1000)
                params = {"timestamp": timestamp}
                query_string = urlencode(params)
                signature = hmac_lib.new(
                    api_secret_clean.encode("utf-8"),
                    query_string.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                params["signature"] = signature

                headers = {"X-MBX-APIKEY": api_key_clean}
                url = f"https://testnet.binancefuture.com/fapi/v2/account?{urlencode(params)}"
                response = req_lib.get(url, headers=headers, timeout=10)

                if response.status_code == 200:
                    account_info = response.json()
                    total_balance = float(account_info.get("totalWalletBalance", 0.0) or 0.0)
                    available_balance = float(account_info.get("availableBalance", 0.0) or 0.0)

                    print(f"[DEBUG] 测试网 API 调用成功: 余额={total_balance} USDT")
                    return {
                        "balance": total_balance,
                        "freeMargin": available_balance,
                        "availableBalance": available_balance,
                        "asset": "USDT",
                        "testnet": testnet,
                    }
                else:
                    error_info = response.json() if response.content else {}
                    error_code = error_info.get("code", "N/A")
                    error_msg = error_info.get("msg", response.text)
                    print(f"[ERROR] 测试网 API 调用失败: HTTP {response.status_code}, code={error_code}, msg={error_msg}")
                    raise Exception(f"测试网 API 错误 (代码: {error_code}): {error_msg}")

            except Exception as direct_error:
                print(f"[ERROR] 直接 API 调用失败: {direct_error}，尝试 CCXT...")
                import traceback
                traceback.print_exc()
                exchange = ccxt.binanceusdm(ccxt_config)
                balance = exchange.fetch_balance()
                usdt_info = balance.get("USDT") or balance.get("USDT:USDT") or {}
                total_balance = float(usdt_info.get("total", 0.0) or 0.0)
                free_balance = float(usdt_info.get("free", 0.0) or 0.0)
                return {
                    "balance": total_balance,
                    "freeMargin": free_balance,
                    "availableBalance": free_balance,
                    "asset": "USDT",
                    "testnet": testnet,
                }
        else:
            # 实盘使用 CCXT
            exchange = ccxt.binanceusdm(ccxt_config)

            try:
                exchange.load_markets()
                server_time = exchange.fetch_time()
                local_time = int(time.time() * 1000)
                time_diff = server_time - local_time
                if abs(time_diff) > 1000:
                    print(f"[WARNING] 检测到时间差: {time_diff}ms，CCXT 将自动调整")
            except Exception:
                pass

            balance = exchange.fetch_balance()
            usdt_info = balance.get("USDT") or balance.get("USDT:USDT") or {}
            total_balance = float(usdt_info.get("total", 0.0) or 0.0)
            free_balance = float(usdt_info.get("free", 0.0) or 0.0)

            return {
                "balance": total_balance,
                "freeMargin": free_balance,
                "availableBalance": free_balance,
                "asset": "USDT",
                "testnet": testnet,
            }
    except HTTPException:
        raise
    except ccxt.NetworkError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"网络错误: {str(e)}（请检查网络连接）",
        )
    except ccxt.ExchangeError as e:
        error_msg = str(e)
        import re
        error_code = None
        try:
            json_match = re.search(r'\{[^}]+\}', error_msg)
            if json_match:
                error_json = json.loads(json_match.group())
                error_code = error_json.get("code")
        except Exception:
            pass

        if error_code is None:
            code_match = re.search(r'"code":\s*(-?\d+)', error_msg)
            if code_match:
                error_code = int(code_match.group(1))

        if error_code == -2008 or "-2008" in error_msg or "Invalid Api-Key" in error_msg or "invalid api-key" in error_msg.lower():
            print(f"[ERROR] API Key 无效 (错误代码: {error_code or 'N/A'}): {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"API Key 无效（错误代码: {error_code or 'N/A'}）: {error_msg}",
            )

        if "timestamp" in error_msg.lower() or "time" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"时间戳错误: {error_msg}（请同步系统时间或检查网络延迟）",
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"币安 API 错误: {error_msg}",
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取账户余额失败: {str(e)}",
        )


# ============================================
# OpenAI 状态端点
# ============================================


@router.get("/api/v43/openai-status")
async def get_openai_status():
    """返回 OpenAI AI 层的状态和统计信息。"""
    import json as _json
    from pathlib import Path as _Path

    enabled = os.getenv("OPENAI_AI_ENABLED", "false").lower() in ("1", "true")
    assistant_id = os.getenv("OPENAI_ASSISTANT_ID", "")
    vector_store_id = os.getenv("OPENAI_VECTOR_STORE_ID", "")
    model = os.getenv("OPENAI_TRADING_MODEL", "gpt-4o")
    has_key = bool(os.getenv("OPENAI_API_KEY"))

    # 读取交易日志统计
    log_path = _Path(os.getenv("AI_TRADE_LOG_PATH", "data/ai_trade_log.jsonl"))
    trade_count = 0
    win_count = 0
    last_upload_date: Optional[str] = None

    if log_path.exists():
        try:
            lines = [l for l in log_path.read_text(encoding="utf-8").strip().splitlines() if l.strip()]
            for line in lines:
                try:
                    rec = _json.loads(line)
                    trade_count += 1
                    if rec.get("outcome") == "WIN":
                        win_count += 1
                except Exception:
                    pass
            # Last modified = approximate last upload indicator
            import time as _time
            mtime = log_path.stat().st_mtime
            last_upload_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

    win_rate = round(win_count / trade_count * 100, 1) if trade_count > 0 else 0.0

    return {
        "status": "success",
        "code": 200,
        "data": {
            "enabled": enabled,
            "configured": bool(assistant_id and has_key),
            "has_api_key": has_key,
            "model": model,
            "assistant_id_masked": f"{assistant_id[:8]}..." if assistant_id else None,
            "vector_store_id_masked": f"{vector_store_id[:8]}..." if vector_store_id else None,
            "trade_log": {
                "total": trade_count,
                "wins": win_count,
                "losses": trade_count - win_count,
                "win_rate": win_rate,
                "last_updated": last_upload_date,
            },
        },
    }


@router.post("/api/v43/openai-memory/upload")
async def trigger_memory_upload():
    """手动触发将交易记录上传到 OpenAI Vector Store。"""
    vector_store_id = os.getenv("OPENAI_VECTOR_STORE_ID")
    if not vector_store_id:
        raise HTTPException(status_code=400, detail="OPENAI_VECTOR_STORE_ID 未配置")
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY 未配置")

    try:
        import asyncio as _asyncio
        from scripts.ai.memory_uploader import upload_trade_history  # type: ignore[import-not-found]
        await upload_trade_history(vector_store_id=vector_store_id)
        return {"status": "success", "code": 200, "message": "交易记忆上传完成"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


# ============================================
# AI 进化 & 准确率热力图端点
# ============================================


@router.get("/api/v43/ai-evolution")
async def get_ai_evolution(
    days: int = Query(30, description="返回最近 N 天的记录", ge=1, le=365),
    eventType: Optional[str] = Query(None, description="事件类型过滤", regex="^(WIN|LOSS|ADJUSTMENT|all)$"),
    supabase=Depends(get_supabase),
):
    """
    获取 AI 进化日志

    从权重历史中提取 AI 决策和性能变化。
    """
    try:
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        response = (
            supabase.table("ai_weights_v43")
            .select("*")
            .gte("created_at", cutoff_date)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )

        events = []
        wins = 0
        losses = 0

        for record in response.data or []:
            performance_metrics = record.get("performance_metrics", {})
            if isinstance(performance_metrics, str):
                try:
                    performance_metrics = json.loads(performance_metrics)
                except Exception:
                    performance_metrics = {}

            event_type = "ADJUSTMENT"
            profit_change = None

            if performance_metrics:
                profit_change_val = performance_metrics.get("profit_change") or performance_metrics.get("pnl_change")
                if profit_change_val:
                    profit_change_val = float(profit_change_val)
                    if profit_change_val > 0:
                        event_type = "WIN"
                        wins += 1
                        profit_change = f"+{profit_change_val * 100:.1f}%"
                    elif profit_change_val < 0:
                        event_type = "LOSS"
                        losses += 1
                        profit_change = f"{profit_change_val * 100:.1f}%"

            weights = record.get("weights", {})
            if isinstance(weights, str):
                try:
                    weights = json.loads(weights)
                except Exception:
                    weights = {}

            atr_k = None
            if performance_metrics:
                atr_k = performance_metrics.get("atr_k") or performance_metrics.get("atr_multiplier")

            ai_reason = record.get("ai_reason", "权重调整")
            decision_text = ai_reason or "AI 参数优化"

            mode = "Sniper"
            if weights:
                structure_weight = weights.get("structure", 0.35)
                if structure_weight < 0.3:
                    mode = "Scavenger"

            created_at = record.get("created_at", datetime.now().isoformat())
            if isinstance(created_at, str):
                try:
                    date_obj = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    date_str = date_obj.strftime("%Y-%m-%d")
                except Exception:
                    date_str = created_at[:10] if len(created_at) >= 10 else datetime.now().strftime("%Y-%m-%d")
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")

            if eventType and eventType != "all" and event_type != eventType:
                continue

            events.append({
                "date": date_str,
                "type": event_type,
                "mode": mode,
                "decision": decision_text,
                "atrK": float(atr_k) if atr_k else None,
                "profitChange": profit_change,
                "confidence": float(performance_metrics.get("confidence", 0.7)) if performance_metrics else None,
                "impact": {
                    "tradeQuality": performance_metrics.get("trade_quality_change", "+0%") if performance_metrics else "+0%",
                    "winRate": performance_metrics.get("win_rate_change", "+0%") if performance_metrics else "+0%",
                } if performance_metrics else None,
            })

        total_events = len(events)
        win_rate = wins / total_events if total_events > 0 else 0.0

        return {
            "status": "success",
            "code": 200,
            "data": events,
            "stats": {
                "totalEvents": total_events,
                "wins": wins,
                "losses": losses,
                "winRate": win_rate,
                "avgProfitPerWin": 0.124,
                "avgLossPerLoss": -0.052,
            },
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取 AI 进化日志失败: {str(e)}",
        )


@router.get("/api/v43/accuracy-heatmap")
async def get_accuracy_heatmap(
    days: int = Query(28, description="返回最近 N 天的数据", ge=1, le=365),
    supabase=Depends(get_supabase),
):
    """获取准确率热力图数据"""
    try:
        heatmap_data = []
        for i in range(days):
            heatmap_data.append({
                "day": i,
                "accuracy": 60 + (i % 20),
                "trades": 10 + (i % 10),
            })

        return {
            "status": "success",
            "code": 200,
            "data": {
                "heatmap": heatmap_data,
                "avgAccuracy": 70.0,
                "totalTrades": sum(d["trades"] for d in heatmap_data),
            },
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取准确率热力图失败: {str(e)}",
        )


# ============================================
# 进场验证端点
# ============================================


@router.post("/api/v43/validate-entry", response_model=EntryValidationResponse)
async def validate_entry(request: EntryValidationRequest):
    """
    验证交易进场条件

    返回 4D 评分、状态判定、AI 建议。
    """
    try:
        from scripts.v43_entry_validator import get_entry_validator  # type: ignore[import-not-found]

        validator = get_entry_validator()
        result = validator.validate_entry(
            request.symbol,
            request.leverage,
            request.risk,
        )

        return EntryValidationResponse(
            status="success",
            code=200,
            data=result,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"验证进场条件失败: {str(e)}",
        )
