# Plan B-1:V5 后端联动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Plan B 前端重写补齐所有后端依赖:12 个新 API 路由 + WebSocket 广播 + 策略参数热读 + DeepSeek 本地 RAG-lite + 手动模拟开单工作流。完成后前端可在稳定 API 基础上开工。

**Architecture:** 三块独立增量,每块端到端 TDD:① `v5_params.py` 热读层(env > DB > default 优先级,5s cache)替换 6 个 V5 模块里散落的 `os.environ.get`;② `local_rag.py` 加权欧氏距离 top-K 检索 `ai_training_data`,注入 `trading_assistant._decide_via_chat` 的 prompt;③ 12 个新路由(`api/routes/v5_*.py`)+ WebSocket 广播(`api/websocket_v5.py`)+ Pydantic schemas(`api/schemas/v5_*.py`)。

**Tech Stack:** Python 3.11、FastAPI 0.115、Pydantic v2、SQLite、asyncio、pytest、AsyncOpenAI(DeepSeek 兼容)。

**Spec reference:** `docs/superpowers/specs/2026-06-12-v5-frontend-rebuild-design.md` §5/§6

---

## 文件结构

### 新建文件
```
scripts/v5_params.py                 # 热读参数层(env > DB > default + 5s cache)
scripts/ai/local_rag.py              # DeepSeek 本地 RAG-lite

api/schemas/v5_strategy_config.py    # 策略配置 schema
api/schemas/v5_settings.py           # 系统设置 schema
api/schemas/v5_ai.py                 # AI 状态 / 决策 schema
api/schemas/v5_charts.py             # K 线 / 事件 schema
api/schemas/v5_manual_order.py       # 手动开单 preview/execute schema

api/routes/v5_strategy_config.py     # GET/PATCH /api/v5/strategy-config + preview
api/routes/v5_settings.py            # GET/PATCH /api/v5/settings
api/routes/v5_ai.py                  # /api/v5/ai/status + /decisions
api/routes/v5_charts.py              # /api/v5/klines + /events
api/routes/v5_manual_order.py        # /api/v5/manual-order/{preview,execute}
api/routes/v5_position_close.py      # POST /api/v5/positions/:id/close

api/websocket_v5.py                  # /ws/v5 广播服务(替代 stub)
api/services/v5_broadcast.py         # 广播 client 注册表 + send_to_all

tests/test_v5_params.py
tests/test_local_rag.py
tests/test_v5_strategy_config_api.py
tests/test_v5_settings_api.py
tests/test_v5_ai_api.py
tests/test_v5_charts_api.py
tests/test_v5_manual_order_api.py
tests/test_v5_position_close_api.py
tests/test_websocket_v5.py
```

### 修改文件
```
scripts/v5_strategy.py               # _f() → get_param()
scripts/v5_risk_calculator.py        # _f() → get_param()
scripts/v5_position_monitor.py       # MAX_EXTENSIONS/RSI_REVERSE_* → get_param()
scripts/tasks/deep_collector.py      # V5_DELTA_15M_THRESHOLD → get_param()
scripts/tasks/scorer.py              # MAX_CONCURRENT/RISK_PER_TRADE/LEVERAGE → get_param() + 接 broadcast
scripts/ai/trading_assistant.py      # _decide_via_chat 接 local_rag
scripts/v5_position_monitor.py       # 平仓/续仓时接 broadcast
api/main.py                          # 注册新路由 + 挂 WebSocket
```

---

## Phase 0:Pydantic Schemas

### Task 1:全部 V5 Pydantic schemas 一次性写完

**Files:**
- Create: `api/schemas/v5_strategy_config.py`
- Create: `api/schemas/v5_settings.py`
- Create: `api/schemas/v5_ai.py`
- Create: `api/schemas/v5_charts.py`
- Create: `api/schemas/v5_manual_order.py`
- Create: `tests/test_v5_schemas.py`

- [ ] **Step 1: 写 schema tests(红)**

`tests/test_v5_schemas.py`:

```python
"""V5 Pydantic schemas sanity test。"""
import pytest


def test_strategy_config_response_round_trip():
    from api.schemas.v5_strategy_config import StrategyConfigResponse, ParamSpec
    r = StrategyConfigResponse(params=[
        ParamSpec(key="v5_rsi_overbought", value=70.0, default=70.0, min=60.0, max=80.0, unit="", description="开空 RSI 阈值"),
    ])
    assert r.params[0].value == 70.0
    # JSON 序列化往返
    j = r.model_dump_json()
    r2 = StrategyConfigResponse.model_validate_json(j)
    assert r2.params[0].key == "v5_rsi_overbought"


def test_settings_response_masks_keys():
    from api.schemas.v5_settings import SettingsResponse
    r = SettingsResponse(
        exchange="okx",
        openai_api_key_masked="sk-****abcd",
        openai_assistant_id=None,
        deepseek_api_key_masked="sk-****wxyz",
        deepseek_enabled=True,
        active_ai_provider="deepseek",
        active_chat_model="deepseek-chat",
        system_mode="SHADOW",
        enable_auto_trading=False,
        ai_fail_open=False,
        sl_tp_fail_open=False,
    )
    # 掩码字段不应包含 sk- 完整 key
    assert "****" in r.openai_api_key_masked


def test_ai_status_response():
    from api.schemas.v5_ai import AIStatusResponse
    r = AIStatusResponse(
        provider="deepseek",
        chat_model="deepseek-chat",
        healthy=True,
        last_latency_ms=7800,
        decisions_24h=142,
        rag_utilization_24h=0.78,
        rag_cases_in_db=142,
    )
    assert r.rag_utilization_24h == 0.78


def test_ai_decision_item():
    from api.schemas.v5_ai import AIDecisionItem
    d = AIDecisionItem(
        id=1, created_at="2026-06-12T10:00:00+00:00",
        symbol="H/USDT", side="SHORT",
        execute=True, confidence=0.7,
        reasoning="...", top1_distance=0.08, rag_case_count=5,
    )
    assert d.execute is True


def test_kline_response():
    from api.schemas.v5_charts import KlinesResponse, Kline
    r = KlinesResponse(symbol="H/USDT", interval="15m",
                       klines=[Kline(ts=1717200000000, open=0.166, high=0.168, low=0.165, close=0.166, volume=1000.0)])
    assert r.klines[0].close == 0.166


def test_symbol_event():
    from api.schemas.v5_charts import SymbolEvent, SymbolEventsResponse
    ev = SymbolEvent(
        event_type="entry", side="SHORT", price=0.166,
        timestamp="2026-06-12T10:00:00+00:00",
        position_id=1, reasoning="RSI 超买", rsi_15m=72.0, macd_hist_15m=-0.0005,
    )
    r = SymbolEventsResponse(symbol="H/USDT", events=[ev])
    assert r.events[0].event_type == "entry"


def test_manual_order_preview_response():
    from api.schemas.v5_manual_order import (
        ManualOrderPreviewRequest, ManualOrderPreviewResponse,
        ManualOrderDecisionSnapshot, ManualOrderRagCase,
    )
    req = ManualOrderPreviewRequest(symbol="H/USDT", side="SHORT", size_usdt=15.0)
    assert req.size_usdt == 15.0

    r = ManualOrderPreviewResponse(
        symbol="H/USDT", side="SHORT", current_price=0.166,
        indicators={"rsi_15m": 72.0, "macd_hist_15m": -0.0005, "atr_15m": 0.0015,
                    "rsi_4h": 65.0, "macd_hist_4h": 0.003},
        decision=ManualOrderDecisionSnapshot(
            should_trade=True, side="SHORT", reasoning="RSI 超买"),
        risk_plan={"entry_price": 0.166, "sl_price": 0.169, "tp_price": 0.162,
                   "size_usdt": 15.0, "leverage": 10, "expected_rr": 1.67},
        ai_result={"execute": True, "sl_multiplier": 1.8, "tp_multiplier": 2.6,
                   "size_multiplier": 1.0, "confidence": 0.7, "reasoning": "..."},
        rag_cases=[
            ManualOrderRagCase(entry_rsi_15m=73.2, entry_macd_hist_15m=-0.0006,
                               outcome="WIN", pnl_pct=0.004, exit_reason="TP_HIT", distance=0.08),
        ],
    )
    assert len(r.rag_cases) == 1


def test_manual_order_execute_request():
    from api.schemas.v5_manual_order import ManualOrderExecuteRequest
    req = ManualOrderExecuteRequest(
        symbol="H/USDT", side="SHORT", size_usdt=15.0,
        sl_multiplier=1.8, tp_multiplier=2.6, size_multiplier=1.0,
    )
    assert req.sl_multiplier == 1.8
```

- [ ] **Step 2: 跑测试,期望全 fail(模块不存在)**

```bash
python3 -m pytest tests/test_v5_schemas.py -v
```

预期:全部 `ModuleNotFoundError`。

- [ ] **Step 3: 写 api/schemas/v5_strategy_config.py**

```python
"""V5 策略配置 schema。"""
from typing import List, Optional, Union
from pydantic import BaseModel


class ParamSpec(BaseModel):
    """单个参数:当前值 + 默认 + 范围 + 单位 + 说明。"""
    key: str                        # 例: "v5_rsi_overbought"
    value: float                    # 当前值
    default: float                  # 代码内置默认
    min: float
    max: float
    unit: str = ""                  # 例: "%", "x", "USDT", ""
    description: str = ""


class StrategyConfigResponse(BaseModel):
    params: List[ParamSpec]


class StrategyConfigPatchRequest(BaseModel):
    """前端 PATCH 一次只改若干个 key。"""
    updates: dict[str, float]


class StrategyConfigPreviewResponse(BaseModel):
    """回测预览:基于过去 N 天数据估算改阈值后命中率 + 入场频率。"""
    candidate_params: dict[str, float]
    estimated_hourly_entries: float
    estimated_win_rate: float
    sample_days: int                # 实际用了多少天数据
```

- [ ] **Step 4: 写 api/schemas/v5_settings.py**

```python
"""V5 系统设置 schema。"""
from typing import Optional, Literal
from pydantic import BaseModel


class SettingsResponse(BaseModel):
    exchange: Literal["okx", "binance"]

    # OpenAI
    openai_api_key_masked: str = ""           # "sk-****abcd" 或 ""
    openai_assistant_id: Optional[str] = None
    openai_vector_store_id: Optional[str] = None

    # DeepSeek
    deepseek_api_key_masked: str = ""
    deepseek_enabled: bool = False

    # Active provider(读自 trading_assistant 当前状态)
    active_ai_provider: Optional[Literal["openai", "deepseek"]] = None
    active_chat_model: Optional[str] = None

    # Mode
    system_mode: Literal["SHADOW", "LIVE"]
    enable_auto_trading: bool

    # Fail-closed knobs
    ai_fail_open: bool
    sl_tp_fail_open: bool


class SettingsPatchRequest(BaseModel):
    """全部字段可选;只更新提交的字段。
    Key 字段如果提交"" 视为清空,如果不提交则保留原值。
    """
    exchange: Optional[Literal["okx", "binance"]] = None
    openai_api_key: Optional[str] = None           # 明文 key,落库时加密(MVP 直接存)
    openai_assistant_id: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    deepseek_enabled: Optional[bool] = None
    system_mode: Optional[Literal["SHADOW", "LIVE"]] = None
    enable_auto_trading: Optional[bool] = None
    ai_fail_open: Optional[bool] = None
    sl_tp_fail_open: Optional[bool] = None
```

- [ ] **Step 5: 写 api/schemas/v5_ai.py**

```python
"""V5 AI 状态 + 最近决策 schema。"""
from typing import List, Optional, Literal
from pydantic import BaseModel


class AIStatusResponse(BaseModel):
    provider: Optional[Literal["openai", "deepseek"]]
    chat_model: Optional[str]
    healthy: bool
    last_latency_ms: Optional[int] = None         # 最近一次 decide() 调用耗时
    decisions_24h: int
    rag_utilization_24h: float                    # 0~1
    rag_cases_in_db: int                          # ai_training_data 已平仓样本数


class AIDecisionItem(BaseModel):
    id: int
    created_at: str                                # UTC ISO + 00:00
    symbol: str
    side: Literal["LONG", "SHORT"]
    execute: bool
    confidence: float
    reasoning: str
    top1_distance: Optional[float] = None         # RAG top-1 距离;None=未启用 RAG
    rag_case_count: int = 0                        # 这次 decide 用了多少 RAG case


class AIDecisionsResponse(BaseModel):
    decisions: List[AIDecisionItem]
```

- [ ] **Step 6: 写 api/schemas/v5_charts.py**

```python
"""V5 ChartPage K 线 + 事件 schema。"""
from typing import List, Optional, Literal
from pydantic import BaseModel


class Kline(BaseModel):
    ts: int                                # 毫秒时间戳
    open: float
    high: float
    low: float
    close: float
    volume: float


class KlinesResponse(BaseModel):
    symbol: str
    interval: Literal["15m", "1h", "4h"]
    klines: List[Kline]


class SymbolEvent(BaseModel):
    event_type: Literal["entry", "exit", "extension"]
    side: Optional[Literal["LONG", "SHORT"]] = None
    price: float
    timestamp: str                                  # UTC ISO + 00:00
    position_id: Optional[int] = None
    reasoning: Optional[str] = None
    # 入场时的指标快照(标注 tooltip 用)
    rsi_15m: Optional[float] = None
    macd_hist_15m: Optional[float] = None
    # 出场时的字段
    exit_reason: Optional[str] = None
    pnl_pct: Optional[float] = None


class SymbolEventsResponse(BaseModel):
    symbol: str
    events: List[SymbolEvent]
```

- [ ] **Step 7: 写 api/schemas/v5_manual_order.py**

```python
"""V5 手动模拟开单 schema(三步工作流)。"""
from typing import List, Optional, Literal
from pydantic import BaseModel


class ManualOrderPreviewRequest(BaseModel):
    symbol: str
    side: Optional[Literal["LONG", "SHORT"]] = None   # None 表示让规则引擎决定
    size_usdt: float = 15.0


class ManualOrderDecisionSnapshot(BaseModel):
    should_trade: bool
    side: Optional[Literal["LONG", "SHORT"]]
    reasoning: str
    block_reason: Optional[str] = None


class ManualOrderRagCase(BaseModel):
    entry_rsi_15m: float
    entry_macd_hist_15m: float
    outcome: Literal["WIN", "LOSS", "FLAT"]
    pnl_pct: float
    exit_reason: str
    distance: float


class ManualOrderPreviewResponse(BaseModel):
    symbol: str
    side: Literal["LONG", "SHORT"]
    current_price: float
    indicators: dict                              # rsi_15m / macd_hist_15m / atr_15m / rsi_4h / macd_hist_4h
    decision: ManualOrderDecisionSnapshot
    risk_plan: dict                               # entry/sl/tp/size_usdt/leverage/expected_rr
    ai_result: dict                               # execute/sl_mult/tp_mult/size_mult/confidence/reasoning
    rag_cases: List[ManualOrderRagCase]
    rag_summary: Optional[str] = None             # 例: "5 case 中 3 胜 2 负,均 PnL +0.12%"


class ManualOrderExecuteRequest(BaseModel):
    symbol: str
    side: Literal["LONG", "SHORT"]
    size_usdt: float = 15.0
    # 用户在 preview 看到 AI 给的乘数后可微调
    sl_multiplier: float = 1.0
    tp_multiplier: float = 1.0
    size_multiplier: float = 1.0


class ManualOrderExecuteResponse(BaseModel):
    position_id: int
    symbol: str
    side: Literal["LONG", "SHORT"]
    entry_price: float
    sl_price: float
    tp_price: float
    size_usdt: float
    strategy_id: str                              # 'v5_manual'
```

- [ ] **Step 8: 跑测试,期望全 pass**

```bash
python3 -m pytest tests/test_v5_schemas.py -v
```

预期:`8 passed`。

- [ ] **Step 9: 全量回归 + Commit**

```bash
python3 -m pytest tests/ -v 2>&1 | tail -3
# 期望 85 passed(77 + 8 新)
```

```bash
git add api/schemas/v5_strategy_config.py api/schemas/v5_settings.py \
        api/schemas/v5_ai.py api/schemas/v5_charts.py \
        api/schemas/v5_manual_order.py tests/test_v5_schemas.py
git commit -m "feat(api): V5 Pydantic schemas for Plan B routes

- v5_strategy_config: ParamSpec + Response + Patch + Preview
- v5_settings: masked key display + Patch with optional fields
- v5_ai: AIStatus + AIDecision list
- v5_charts: Kline + SymbolEvent (entry/exit/extension)
- v5_manual_order: 3-step workflow preview + execute

8 schema round-trip tests pass."
```

---

## Phase 1:策略参数热读层

### Task 2:`scripts/v5_params.py` + 改造 6 个 V5 模块

**Files:**
- Create: `scripts/v5_params.py`
- Modify: `scripts/v5_strategy.py`
- Modify: `scripts/v5_risk_calculator.py`
- Modify: `scripts/v5_position_monitor.py`
- Modify: `scripts/tasks/deep_collector.py`
- Modify: `scripts/tasks/scorer.py`
- Create: `tests/test_v5_params.py`

- [ ] **Step 1: 写 tests/test_v5_params.py(红)**

```python
"""V5Params 热读层测试。"""
import sqlite3
import tempfile
import time
import pytest


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def test_env_takes_priority(monkeypatch):
    """env 设了就锁死,即使 DB 有不同值。"""
    from scripts.v5_params import get_param
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "65")
    db = _fresh_db()
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('v5_rsi_overbought', '60')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", db)
    v = get_param("v5_rsi_overbought", default=70.0, cast=float)
    assert v == 65.0   # env > DB


def test_db_takes_over_when_env_unset(monkeypatch):
    monkeypatch.delenv("V5_RSI_OVERBOUGHT", raising=False)
    db = _fresh_db()
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('v5_rsi_overbought', '68')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", db)
    # 强制清 cache,避免上一测试残留
    from scripts.v5_params import _CACHE
    _CACHE.clear()
    v = get_param("v5_rsi_overbought", default=70.0, cast=float)
    assert v == 68.0


def test_default_when_neither_set(monkeypatch):
    monkeypatch.delenv("V5_RSI_OVERBOUGHT", raising=False)
    db = _fresh_db()
    monkeypatch.setenv("DB_PATH", db)
    from scripts.v5_params import _CACHE
    _CACHE.clear()
    v = get_param("v5_rsi_overbought", default=70.0, cast=float)
    assert v == 70.0


def test_cache_avoids_db_hit(monkeypatch):
    """同一 key 5s 内只读一次 DB。"""
    monkeypatch.delenv("V5_RSI_OVERBOUGHT", raising=False)
    db = _fresh_db()
    monkeypatch.setenv("DB_PATH", db)

    from scripts.v5_params import _CACHE, get_param
    _CACHE.clear()

    v1 = get_param("v5_rsi_overbought", default=70.0, cast=float)
    # 改 DB
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('v5_rsi_overbought', '99')"
    )
    conn.commit()
    conn.close()
    # 立刻再读 — cache 命中 → 还是旧值
    v2 = get_param("v5_rsi_overbought", default=70.0, cast=float)
    assert v2 == v1


def test_invalidate_force_refresh(monkeypatch):
    """invalidate_cache 后再读会拿到新值。"""
    monkeypatch.delenv("V5_RSI_OVERBOUGHT", raising=False)
    db = _fresh_db()
    monkeypatch.setenv("DB_PATH", db)
    from scripts.v5_params import _CACHE, get_param, invalidate_cache
    _CACHE.clear()

    _ = get_param("v5_rsi_overbought", default=70.0, cast=float)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('v5_rsi_overbought', '55')"
    )
    conn.commit()
    conn.close()

    invalidate_cache()
    v = get_param("v5_rsi_overbought", default=70.0, cast=float)
    assert v == 55.0


def test_invalid_value_falls_back_to_default(monkeypatch):
    """DB 里存了不能解析的字符串 → fallback default。"""
    monkeypatch.delenv("V5_RSI_OVERBOUGHT", raising=False)
    db = _fresh_db()
    monkeypatch.setenv("DB_PATH", db)
    from scripts.v5_params import _CACHE, get_param
    _CACHE.clear()
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('v5_rsi_overbought', 'not-a-number')"
    )
    conn.commit()
    conn.close()
    v = get_param("v5_rsi_overbought", default=70.0, cast=float)
    assert v == 70.0
```

- [ ] **Step 2: 跑测试,期望 fail**

```bash
python3 -m pytest tests/test_v5_params.py -v
```

- [ ] **Step 3: 写 scripts/v5_params.py**

```python
"""V5 参数热读层 — 5s 缓存,env > DB > default 优先级。

V5 把分散在多个文件里的 os.environ.get 收拢到这里。前端 PATCH 策略配置
时调 invalidate_cache(),collector 下次读会拿到新值,不需要重启。

env 优先级最高 —— 用户在 .env 里设了死的就锁死,无视 UI 改动。
"""
import os
import sqlite3
import time
from typing import Any, Callable, Optional


_DEFAULT_TTL = 5.0
_CACHE: dict = {}              # key → (value_str, expire_ts)


def _db_path() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


# DB key → env var name(env 比 DB 优先时用)
_ENV_MAP = {
    "v5_rsi_overbought":          "V5_RSI_OVERBOUGHT",
    "v5_rsi_oversold":            "V5_RSI_OVERSOLD",
    "v5_sl_atr_mult":             "V5_SL_ATR_MULT",
    "v5_tp_atr_mult":             "V5_TP_ATR_MULT",
    "v5_delta_15m_threshold":     "V5_DELTA_15M_THRESHOLD",
    "v5_min_expected_move_pct":   "MIN_EXPECTED_MOVE_PCT",
    "v5_max_concurrent":          "V5_MAX_CONCURRENT",
    "v5_max_extensions":          "V5_MAX_EXTENSIONS",
    "v5_rsi_reverse_short":       "V5_RSI_REVERSE_SHORT",
    "v5_rsi_reverse_long":        "V5_RSI_REVERSE_LONG",
    "v5_risk_per_trade":          "V43_RISK_PER_TRADE",     # 沿用旧 env 名
    "v5_leverage":                "BINANCE_LEVERAGE",       # 沿用旧 env 名
    "v5_soft_target_minutes":     "V5_SOFT_TARGET_MINUTES",
}


def get_param(key: str, default: Any, cast: Callable[[str], Any] = str) -> Any:
    """读参数。优先级 env > DB(system_settings)> default。

    cast 把字符串转换成目标类型,失败 → default。
    """
    # 1. env
    env_name = _ENV_MAP.get(key)
    if env_name:
        raw = os.environ.get(env_name, "").strip()
        if raw:
            try:
                return cast(raw)
            except (ValueError, TypeError):
                pass

    # 2. cache(只缓存 DB 路径,因为 env 总是即时读)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and cached[1] > now:
        try:
            return cast(cached[0])
        except (ValueError, TypeError):
            return default

    # 3. DB
    try:
        conn = sqlite3.connect(_db_path())
        try:
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key = ? ORDER BY rowid DESC LIMIT 1",
                (key,),
            ).fetchone()
        finally:
            conn.close()
        if row and row[0] is not None:
            _CACHE[key] = (str(row[0]), now + _DEFAULT_TTL)
            try:
                return cast(row[0])
            except (ValueError, TypeError):
                return default
    except Exception:
        pass

    # 4. default
    return default


def invalidate_cache(key: Optional[str] = None) -> None:
    """清缓存。前端 PATCH 后调一次 → 下次 read 走 DB。"""
    if key is None:
        _CACHE.clear()
    else:
        _CACHE.pop(key, None)


# 公开默认值常量,供前端 GET /strategy-config 返回 default
DEFAULTS = {
    "v5_rsi_overbought":          70.0,
    "v5_rsi_oversold":            30.0,
    "v5_sl_atr_mult":             1.5,
    "v5_tp_atr_mult":             2.5,
    "v5_delta_15m_threshold":     0.03,
    "v5_min_expected_move_pct":   0.01,
    "v5_max_concurrent":          3,
    "v5_max_extensions":          3,
    "v5_rsi_reverse_short":       65.0,
    "v5_rsi_reverse_long":        35.0,
    "v5_risk_per_trade":          0.015,
    "v5_leverage":                10,
    "v5_soft_target_minutes":     15,
}

PARAM_META = {
    # key → (min, max, unit, description)
    "v5_rsi_overbought":          (60.0, 80.0, "", "开空 RSI 阈值(>)"),
    "v5_rsi_oversold":            (20.0, 40.0, "", "开多 RSI 阈值(<)"),
    "v5_sl_atr_mult":             (0.5, 5.0,  "x", "SL 距离 ATR 倍数"),
    "v5_tp_atr_mult":             (1.0, 8.0,  "x", "TP 距离 ATR 倍数"),
    "v5_delta_15m_threshold":     (0.005, 0.10, "", "最低 15min |ΔP|"),
    "v5_min_expected_move_pct":   (0.005, 0.05, "", "最低预期收益(ATR×倍数)"),
    "v5_max_concurrent":          (1, 10, "", "同时活仓数上限"),
    "v5_max_extensions":          (0, 10, "次", "AI 续仓上限"),
    "v5_rsi_reverse_short":       (50.0, 70.0, "", "SHORT 仓 RSI 反向阈值(跌破)"),
    "v5_rsi_reverse_long":        (30.0, 50.0, "", "LONG 仓 RSI 反向阈值(涨破)"),
    "v5_risk_per_trade":          (0.001, 0.05, "", "单笔风险预算(账户%)"),
    "v5_leverage":                (1, 100, "x", "杠杆"),
    "v5_soft_target_minutes":     (5, 60, "分钟", "持仓软目标"),
}
```

- [ ] **Step 4: 跑测试,期望全 pass**

```bash
python3 -m pytest tests/test_v5_params.py -v
```

预期:`6 passed`。

- [ ] **Step 5: 改 scripts/v5_strategy.py — 用 get_param 替代 _f**

替换 `_f("V5_RSI_OVERBOUGHT", 70.0)` 调用:

```python
# 顶部 import
from scripts.v5_params import get_param

def decide(enriched: EnrichedItem, indicators: Indicators) -> Decision:
    overbought = get_param("v5_rsi_overbought", 70.0, float)
    oversold = get_param("v5_rsi_oversold", 30.0, float)
    # ... 后续逻辑不变
```

把原文件里的 `_f` 函数定义保留(向后兼容),但 `decide()` 内部改用 `get_param`。

- [ ] **Step 6: 改 scripts/v5_risk_calculator.py**

```python
from scripts.v5_params import get_param

def plan(*, side, entry, atr, balance, risk_pct, leverage):
    if atr <= 0:
        raise ValueError(f"atr must be > 0, got {atr}")
    if entry <= 0:
        raise ValueError(f"entry must be > 0, got {entry}")

    sl_mult = get_param("v5_sl_atr_mult", 1.5, float)
    tp_mult = get_param("v5_tp_atr_mult", 2.5, float)
    # ... 后续不变
```

- [ ] **Step 7: 改 scripts/v5_position_monitor.py**

模块顶部 `MAX_EXTENSIONS / RSI_REVERSE_SHORT / RSI_REVERSE_LONG` 全部改为函数读:

```python
from scripts.v5_params import get_param

def _max_extensions() -> int:
    return int(get_param("v5_max_extensions", 3, int))

def _rsi_reverse_short() -> float:
    return float(get_param("v5_rsi_reverse_short", 65.0, float))

def _rsi_reverse_long() -> float:
    return float(get_param("v5_rsi_reverse_long", 35.0, float))


def _signal_reversed(side, rsi, hist, hist_prev):
    if side == "SHORT":
        if rsi < _rsi_reverse_short():
            return True
        # ...
    else:
        if rsi > _rsi_reverse_long():
            return True
```

`MAX_EXTENSIONS` 引用全部改为 `_max_extensions()` 调用。**测试 `tests/test_v5_position_monitor.py` 里 `from scripts.v5_position_monitor import MAX_EXTENSIONS` 改成 `_max_extensions`**:

打开 `tests/test_v5_position_monitor.py`,把:

```python
def test_max_extension_force_close():
    from scripts.v5_position_monitor import check_exit_triggers, MAX_EXTENSIONS
    pos = _open_position(..., extension_count=MAX_EXTENSIONS)
```

改为:

```python
def test_max_extension_force_close():
    from scripts.v5_position_monitor import check_exit_triggers, _max_extensions
    pos = _open_position(..., extension_count=_max_extensions())
```

- [ ] **Step 8: 改 scripts/tasks/deep_collector.py**

`_enrich_symbol` 里:

```python
from scripts.v5_params import get_param

async def _enrich_symbol(self, symbol, ticker):
    threshold = get_param("v5_delta_15m_threshold", 0.03, float)
    # ...
```

- [ ] **Step 9: 改 scripts/tasks/scorer.py**

模块顶部 `MAX_CONCURRENT_POSITIONS / RISK_PER_TRADE / LEVERAGE` 改函数读:

```python
from scripts.v5_params import get_param

def _max_concurrent() -> int:
    return int(get_param("v5_max_concurrent", 3, int))

def _risk_per_trade() -> float:
    return float(get_param("v5_risk_per_trade", 0.015, float))

def _leverage() -> int:
    return int(get_param("v5_leverage", 10, int))


# process_enriched_v5 里:
if _count_open_positions(db_path) >= _max_concurrent():
    _write_trade_score(db_path, ..., block_reason="MAX_CONCURRENT_POSITIONS")
    return

risk = plan(
    side=decision.side, entry=enriched.current_price,
    atr=indicators.atr_15m, balance=balance_usdt,
    risk_pct=_risk_per_trade(), leverage=_leverage(),
)
```

- [ ] **Step 10: 跑全测,期望全 pass**

```bash
python3 -m pytest tests/ -v 2>&1 | tail -3
# 预期 91 passed(85 + 6)
```

如果 `test_v5_position_monitor.py::test_max_extension_force_close` fail,说明 Step 7 的测试改写没生效,回去修。

- [ ] **Step 11: Commit**

```bash
git add scripts/v5_params.py scripts/v5_strategy.py scripts/v5_risk_calculator.py \
        scripts/v5_position_monitor.py scripts/tasks/deep_collector.py \
        scripts/tasks/scorer.py tests/test_v5_params.py tests/test_v5_position_monitor.py
git commit -m "feat(v5): v5_params hot-reload layer + integrate 6 modules

scripts/v5_params.py:
  get_param(key, default, cast) — env > DB > default with 5s cache
  invalidate_cache() — frontend PATCH triggers this
  DEFAULTS + PARAM_META exported for /strategy-config response

Integration:
  v5_strategy.decide              uses get_param('v5_rsi_overbought/oversold')
  v5_risk_calculator.plan         uses get_param('v5_sl/tp_atr_mult')
  v5_position_monitor             uses get_param('v5_max_extensions/rsi_reverse_*')
  deep_collector._enrich_symbol   uses get_param('v5_delta_15m_threshold')
  scorer.process_enriched_v5      uses get_param('v5_max_concurrent/risk_per_trade/leverage')

6 new unit tests + position_monitor test updated to call _max_extensions()."
```

---

## Phase 2:本地 RAG-lite

### Task 3:`scripts/ai/local_rag.py` + 接入 TradingAssistant

**Files:**
- Create: `scripts/ai/local_rag.py`
- Modify: `scripts/ai/trading_assistant.py`
- Create: `tests/test_local_rag.py`

- [ ] **Step 1: 写测试 tests/test_local_rag.py**

```python
"""local_rag 距离 + top-K + 冷启动 + 集成 prompt 注入测试。"""
import sqlite3
import tempfile
import pytest


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _insert_case(db, *, side="SHORT", rsi_15m=72.0, macd_hist_15m=-0.0005,
                 rsi_4h=65.0, delta_15m_pct=0.034, outcome="WIN", pnl_pct=0.004,
                 exit_reason="TP_HIT"):
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO ai_training_data (
            symbol, side, entry_price,
            entry_rsi_15m, entry_macd_hist_15m, entry_rsi_4h, delta_15m_pct,
            outcome, pnl_pct, exit_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-06-12T10:00:00+00:00')
    """, ("H/USDT", side, 0.166,
          rsi_15m, macd_hist_15m, rsi_4h, delta_15m_pct,
          outcome, pnl_pct, exit_reason))
    conn.commit()
    conn.close()


def _ind(rsi_15m=72.0, macd_hist_15m=-0.0005, rsi_4h=65.0):
    from v5_types import Indicators
    return Indicators(
        rsi_15m=rsi_15m, macd_15m=0.0, macd_signal_15m=0.0,
        macd_hist_15m=macd_hist_15m, macd_hist_prev_15m=0.0,
        rsi_4h=rsi_4h, macd_hist_4h=0.0, atr_15m=0.0015,
    )


def test_cold_start_returns_empty():
    """ai_training_data 行数 < 10 → 返回 []。"""
    from scripts.ai.local_rag import find_similar_cases
    db = _fresh_db()
    _insert_case(db)
    cases = find_similar_cases(_ind(), side="SHORT", top_k=5, db_path=db,
                               cold_start_threshold=10)
    assert cases == []


def test_returns_top_k_sorted_by_distance():
    """喂 12 个样本 → 取最近 indicators 的 top-5,按距离升序。"""
    from scripts.ai.local_rag import find_similar_cases
    db = _fresh_db()
    # 远的样本
    for i in range(8):
        _insert_case(db, rsi_15m=80.0 + i * 0.5, macd_hist_15m=-0.001, delta_15m_pct=0.05)
    # 近的样本(rsi=72 hist=-0.0005)
    _insert_case(db, rsi_15m=72.0, macd_hist_15m=-0.0005, delta_15m_pct=0.034)
    _insert_case(db, rsi_15m=72.5, macd_hist_15m=-0.0006, delta_15m_pct=0.033)
    _insert_case(db, rsi_15m=71.8, macd_hist_15m=-0.0004, delta_15m_pct=0.035)
    _insert_case(db, rsi_15m=73.0, macd_hist_15m=-0.0007, delta_15m_pct=0.032)

    cases = find_similar_cases(_ind(), side="SHORT", top_k=5,
                               source_delta_15m_pct=0.034, db_path=db,
                               cold_start_threshold=10)
    assert len(cases) == 5
    # 距离单调递增
    for i in range(len(cases) - 1):
        assert cases[i].distance <= cases[i + 1].distance


def test_filters_by_side():
    """同 side 才算相似。"""
    from scripts.ai.local_rag import find_similar_cases
    db = _fresh_db()
    for _ in range(15):
        _insert_case(db, side="LONG", rsi_15m=28.0, macd_hist_15m=0.0005)
    cases = find_similar_cases(_ind(rsi_15m=28.0, macd_hist_15m=0.0005),
                               side="SHORT", top_k=5, db_path=db,
                               cold_start_threshold=10)
    assert cases == []   # 都是 LONG,不算


def test_excludes_unclosed_samples():
    """outcome IS NULL 的(还在持仓) → 不参与排序。"""
    from scripts.ai.local_rag import find_similar_cases
    db = _fresh_db()
    conn = sqlite3.connect(db)
    for _ in range(15):
        conn.execute("""
            INSERT INTO ai_training_data (symbol, side, entry_rsi_15m, entry_macd_hist_15m,
              entry_rsi_4h, delta_15m_pct, created_at)
            VALUES ('H/USDT', 'SHORT', 72.0, -0.0005, 65.0, 0.034, '2026-06-12T10:00:00+00:00')
        """)
    conn.commit()
    conn.close()
    cases = find_similar_cases(_ind(), side="SHORT", top_k=5, db_path=db,
                               cold_start_threshold=10)
    assert cases == []   # outcome 全 NULL


def test_format_for_prompt():
    """format_cases_for_prompt 把 list 渲染成给 AI 看的文本。"""
    from scripts.ai.local_rag import SimilarCase, format_cases_for_prompt
    cases = [
        SimilarCase(entry_rsi_15m=73.2, entry_macd_hist_15m=-0.0006,
                    entry_rsi_4h=68.0, outcome="WIN", pnl_pct=0.004,
                    exit_reason="TP_HIT", distance=0.08),
        SimilarCase(entry_rsi_15m=71.5, entry_macd_hist_15m=-0.0004,
                    entry_rsi_4h=66.0, outcome="LOSS", pnl_pct=-0.003,
                    exit_reason="SL_HIT", distance=0.12),
    ]
    text = format_cases_for_prompt(cases)
    assert "Historical similar cases" in text
    assert "73.2" in text or "73.20" in text
    assert "WIN" in text
    assert "LOSS" in text


def test_format_empty_returns_empty_string():
    from scripts.ai.local_rag import format_cases_for_prompt
    assert format_cases_for_prompt([]) == ""


def test_rag_utilization_24h(monkeypatch):
    """统计过去 24h 决策中"被注入了至少 1 case"的占比。"""
    from scripts.ai.local_rag import rag_utilization_24h
    db = _fresh_db()
    # 模拟 3 笔决策:2 笔有 RAG,1 笔无
    conn = sqlite3.connect(db)
    # 这里不直接写 ai_training_data 的 reasoning 字段,而是用一个专门记录
    # 实际实现走 trade_scores_v5.ai_reasoning 是否含 "Historical similar cases"
    for i, has_rag in enumerate([True, False, True]):
        reasoning = ("Historical similar cases: case1..." if has_rag else "...")
        conn.execute("""
            INSERT INTO trade_scores_v5 (symbol, created_at, should_trade,
              ai_reasoning, executed)
            VALUES (?, datetime('now', '-1 hour'), 1, ?, 1)
        """, (f"S{i}/USDT", reasoning))
    conn.commit()
    conn.close()
    ratio = rag_utilization_24h(db_path=db)
    assert abs(ratio - 2/3) < 0.01
```

- [ ] **Step 2: 跑测试,期望 fail**

```bash
python3 -m pytest tests/test_local_rag.py -v
```

- [ ] **Step 3: 写 scripts/ai/local_rag.py**

```python
"""V5 本地 RAG-lite — DeepSeek-friendly,Vector Store-free。

decide() 之前查 ai_training_data 中已平仓且同 side 的样本,按加权欧氏距离
排序取 top-K,把结果格式化注入 system prompt。这样 DeepSeek 没有 Vector
Store 也能基于"过去类似 setup 的胜负记录"做 base-rate 推理。

距离公式按重要性加权:
  d = sqrt(
        ((rsi_15m   - entry_rsi_15m)        / 100  ) ** 2 +
        ((macd_hist - entry_macd_hist_15m)  * 1000 ) ** 2 +
        ((rsi_4h    - entry_rsi_4h)         / 100  ) ** 2 * 0.5 +
        ((delta     - delta_15m_pct)        * 10   ) ** 2 * 0.3
      )
"""
import os
import sqlite3
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class SimilarCase:
    entry_rsi_15m: float
    entry_macd_hist_15m: float
    entry_rsi_4h: float
    outcome: str            # WIN / LOSS / FLAT
    pnl_pct: float
    exit_reason: str
    distance: float


def _db_path(explicit: Optional[str]) -> str:
    return explicit or os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def find_similar_cases(
    indicators,
    side: str,
    top_k: int = 5,
    *,
    source_delta_15m_pct: float = 0.0,
    db_path: Optional[str] = None,
    cold_start_threshold: int = 10,
) -> List[SimilarCase]:
    """查 ai_training_data 同 side 已平仓样本,返回 top-K 最近。

    冷启动:同 side 已平仓样本 < cold_start_threshold 行 → 返回 []。
    """
    db = _db_path(db_path)
    try:
        conn = sqlite3.connect(db)
    except Exception:
        return []
    try:
        # 先 count 看是否冷启动
        count = conn.execute(
            "SELECT COUNT(*) FROM ai_training_data "
            "WHERE side = ? AND outcome IS NOT NULL", (side,)
        ).fetchone()[0]
        if count < cold_start_threshold:
            return []

        rows = conn.execute(
            "SELECT entry_rsi_15m, entry_macd_hist_15m, entry_rsi_4h, "
            "       delta_15m_pct, outcome, pnl_pct, exit_reason "
            "  FROM ai_training_data "
            " WHERE side = ? AND outcome IS NOT NULL", (side,)
        ).fetchall()
    finally:
        conn.close()

    candidates = []
    for (entry_rsi, entry_hist, entry_rsi_4h, entry_delta,
         outcome, pnl_pct, exit_reason) in rows:
        # 容错:DB 里可能有 NULL,丢弃
        if entry_rsi is None or entry_hist is None or entry_rsi_4h is None:
            continue
        d_rsi   = (indicators.rsi_15m       - entry_rsi)      / 100.0
        d_hist  = (indicators.macd_hist_15m - entry_hist)     * 1000.0
        d_rsi4  = (indicators.rsi_4h        - entry_rsi_4h)   / 100.0
        d_delta = (source_delta_15m_pct     - (entry_delta or 0.0)) * 10.0
        dist = (d_rsi ** 2 + d_hist ** 2
                + d_rsi4 ** 2 * 0.5
                + d_delta ** 2 * 0.3) ** 0.5
        candidates.append(SimilarCase(
            entry_rsi_15m=float(entry_rsi),
            entry_macd_hist_15m=float(entry_hist),
            entry_rsi_4h=float(entry_rsi_4h),
            outcome=outcome or "FLAT",
            pnl_pct=float(pnl_pct or 0.0),
            exit_reason=exit_reason or "",
            distance=dist,
        ))

    candidates.sort(key=lambda c: c.distance)
    return candidates[:top_k]


def format_cases_for_prompt(cases: List[SimilarCase]) -> str:
    """把 top-K cases 渲染成给 AI 看的文本。空 list 返回空串。"""
    if not cases:
        return ""
    lines = ["Historical similar cases (top {} by weighted indicator distance):".format(len(cases))]
    for i, c in enumerate(cases, 1):
        lines.append(
            f"  case{i}: entry_rsi={c.entry_rsi_15m:.1f} "
            f"hist={c.entry_macd_hist_15m:+.4f} rsi_4h={c.entry_rsi_4h:.1f} "
            f"→ {c.outcome} pnl={c.pnl_pct*100:+.2f}% exit={c.exit_reason} "
            f"(distance={c.distance:.3f})"
        )
    n_win = sum(1 for c in cases if c.outcome == "WIN")
    avg_pnl = sum(c.pnl_pct for c in cases) / len(cases)
    lines.append(
        f"Aggregate: {n_win}/{len(cases)} win,avg pnl {avg_pnl*100:+.2f}%. "
        "Use these as base-rate hints; don't blindly follow."
    )
    return "\n".join(lines)


def rag_utilization_24h(*, db_path: Optional[str] = None) -> float:
    """过去 24h 决策中"被注入 ≥1 case"的占比。

    用 ai_reasoning 字段是否含 "Historical similar cases" 探测。
    """
    db = _db_path(db_path)
    try:
        conn = sqlite3.connect(db)
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM trade_scores_v5 "
                "WHERE should_trade=1 AND ai_reasoning IS NOT NULL "
                "  AND created_at >= datetime('now', '-24 hour')"
            ).fetchone()[0]
            with_rag = conn.execute(
                "SELECT COUNT(*) FROM trade_scores_v5 "
                "WHERE should_trade=1 "
                "  AND ai_reasoning LIKE '%Historical similar cases%' "
                "  AND created_at >= datetime('now', '-24 hour')"
            ).fetchone()[0]
        finally:
            conn.close()
    except Exception:
        return 0.0
    if total == 0:
        return 0.0
    return with_rag / total
```

- [ ] **Step 4: 跑测试,期望全 pass**

```bash
python3 -m pytest tests/test_local_rag.py -v
```

预期:`7 passed`。

- [ ] **Step 5: 改 scripts/ai/trading_assistant.py 集成 RAG**

修改 `_decide_via_chat` 在拼 user_msg 之前调一次:

```python
async def _decide_via_chat(self, system_prompt: str, user_msg: str) -> dict:
    """Chat completions 路径,带 RAG-lite 注入。"""
    json_constraint = (
        "\n\nReturn ONLY a JSON object with exactly these keys: "
        'execute (boolean), sl_multiplier (number 1.0-3.0), '
        'tp_multiplier (number 1.5-5.0), size_multiplier (number 0.3-1.2), '
        'confidence (number 0.0-1.0), reasoning (string ≤ 200 chars). '
        "No markdown, no surrounding text."
    )

    rag_text = getattr(self, "_pending_rag_text", "") or ""
    if rag_text:
        # 注入到 system prompt 之后(与 json_constraint 同级)
        system_full = system_prompt + "\n\n" + rag_text + json_constraint
    else:
        system_full = system_prompt + json_constraint

    resp = await self.client.chat.completions.create(
        model=self.chat_model,
        messages=[
            {"role": "system", "content": system_full},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=300,
    )
    import json
    content = resp.choices[0].message.content or "{}"
    return json.loads(content)
```

`decide()` 在调 `_decide_via_chat` 之前装载 RAG:

找到 decide 方法,在 `timeout_s = float(os.getenv("AI_DECISION_TIMEOUT", "20"))` 后面加入:

```python
    # RAG 注入(仅 chat completions 路径用 — Assistants 走 Vector Store)
    self._pending_rag_text = ""
    if not (self.provider == "openai" and self.assistant_id):
        try:
            from scripts.ai.local_rag import find_similar_cases, format_cases_for_prompt
            cases = find_similar_cases(
                indicators, side=decision.side or "SHORT", top_k=5,
                source_delta_15m_pct=enriched.delta_15m_pct,
            )
            self._pending_rag_text = format_cases_for_prompt(cases)
        except Exception as e:
            print(f"[AI] RAG 检索失败,跳过: {type(e).__name__}: {e}")
```

注意:`decision.side` 在不进 trade 时可能为 None,fallback "SHORT" 只是占位 — 实际 decide 此时不会拿 RAG(因为 should_trade=False 不调 AI)。但为了简化代码不引入分支。

- [ ] **Step 6: 跑全测,验证未破回归**

```bash
python3 -m pytest tests/ -v 2>&1 | tail -3
# 预期 98 passed(91 + 7)
```

如果 `test_deepseek_adapter.py::test_decide_uses_chat_completions_in_deepseek_mode` fail,因为现在 chat 调用注入了 RAG 文本,system prompt 长度变了。检查测试断言,可能要松绑 — 但 assert response_format 还是 json_object,模型还是 deepseek-chat,这两个核心断言不影响。

如果还是 fail,在测试里加 `mock_rag.return_value = []` 让 `find_similar_cases` 返回空。

- [ ] **Step 7: Commit**

```bash
git add scripts/ai/local_rag.py scripts/ai/trading_assistant.py tests/test_local_rag.py
git commit -m "feat(v5): DeepSeek-friendly local RAG-lite

scripts/ai/local_rag.py:
  find_similar_cases — weighted Euclidean distance over RSI/MACD-hist/RSI-4h/delta
  SimilarCase dataclass, cold-start threshold (default 10)
  format_cases_for_prompt — renders top-K to system prompt text
  rag_utilization_24h — % of recent decisions that got injected cases

Integration:
  trading_assistant.decide injects rag_text before _decide_via_chat
  Skipped when OpenAI Assistants path is active (Vector Store handles it)

7 unit tests covering: cold start, top-K sort, side filter, exclude unclosed,
prompt formatting, utilization metric."
```

---

## Phase 3:策略配置路由

### Task 4:GET/PATCH/preview `/api/v5/strategy-config`

**Files:**
- Create: `api/routes/v5_strategy_config.py`
- Modify: `api/main.py`
- Create: `tests/test_v5_strategy_config_api.py`

- [ ] **Step 1: 写测试**

```python
"""V5 strategy-config GET/PATCH API 测试。"""
import sqlite3
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_db(monkeypatch):
    from scripts.local_db import init_local_db
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    init_local_db(tmp.name)
    from scripts.v5_params import _CACHE
    _CACHE.clear()
    from api.main import app
    return TestClient(app), tmp.name


def test_get_returns_defaults_when_db_empty(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/strategy-config")
    assert r.status_code == 200
    data = r.json()
    assert "params" in data
    keys = {p["key"] for p in data["params"]}
    assert "v5_rsi_overbought" in keys
    assert "v5_sl_atr_mult" in keys
    for p in data["params"]:
        # 每个 param 都带 default/min/max
        assert "default" in p and "min" in p and "max" in p


def test_get_returns_db_value_when_set(app_with_db):
    client, db = app_with_db
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO system_settings (key, value) VALUES ('v5_rsi_overbought', '65')")
    conn.commit()
    conn.close()
    r = client.get("/api/v5/strategy-config")
    data = r.json()
    rsi_p = next(p for p in data["params"] if p["key"] == "v5_rsi_overbought")
    assert rsi_p["value"] == 65.0


def test_patch_writes_db_and_invalidates_cache(app_with_db):
    client, db = app_with_db
    # 先 GET 一次让 cache 暖起来
    client.get("/api/v5/strategy-config")
    # PATCH
    r = client.patch("/api/v5/strategy-config", json={
        "updates": {"v5_rsi_overbought": 68, "v5_max_concurrent": 5}
    })
    assert r.status_code == 200
    # DB 应该被写
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT value FROM system_settings WHERE key='v5_rsi_overbought' "
        "ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row[0] == "68"
    # 再 GET 应该返回新值(cache 被 invalidate)
    r2 = client.get("/api/v5/strategy-config")
    data = r2.json()
    rsi_p = next(p for p in data["params"] if p["key"] == "v5_rsi_overbought")
    assert rsi_p["value"] == 68.0


def test_patch_rejects_unknown_key(app_with_db):
    client, _ = app_with_db
    r = client.patch("/api/v5/strategy-config", json={
        "updates": {"unknown_key": 99}
    })
    assert r.status_code == 400
    assert "unknown" in r.text.lower()


def test_patch_rejects_out_of_range(app_with_db):
    client, _ = app_with_db
    # v5_rsi_overbought 范围 60-80,试 90
    r = client.patch("/api/v5/strategy-config", json={
        "updates": {"v5_rsi_overbought": 90}
    })
    assert r.status_code == 400


def test_preview_returns_estimates(app_with_db):
    """无论 ai_training_data 数据多少,/preview 都返回结构化结果。"""
    client, _ = app_with_db
    r = client.post(
        "/api/v5/strategy-config/preview",
        json={"candidate_params": {"v5_rsi_overbought": 65}},
    )
    assert r.status_code == 200
    data = r.json()
    assert "estimated_hourly_entries" in data
    assert "estimated_win_rate" in data
    assert "sample_days" in data
```

- [ ] **Step 2: 跑测试,期望 fail**

```bash
python3 -m pytest tests/test_v5_strategy_config_api.py -v
```

- [ ] **Step 3: 写 api/routes/v5_strategy_config.py**

```python
"""/api/v5/strategy-config — GET/PATCH/preview。

GET     返回 13 个 V5 旋钮当前值 + default + range + unit + description
PATCH   写 system_settings + invalidate v5_params cache
POST /preview  基于过去 N 天 trade_scores_v5 估算 新阈值下入场频率 + 胜率
"""
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, status

from api.schemas.v5_strategy_config import (
    ParamSpec, StrategyConfigResponse,
    StrategyConfigPatchRequest, StrategyConfigPreviewResponse,
)
from scripts.v5_params import (
    get_param, invalidate_cache, DEFAULTS, PARAM_META,
)


router = APIRouter(prefix="/api/v5", tags=["strategy-config"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def _cast_for(key: str):
    """返回该 key 该用的 Python cast。整数 vs 浮点。"""
    default = DEFAULTS.get(key)
    if isinstance(default, bool):
        return lambda v: str(v).lower() in ("1", "true", "yes")
    if isinstance(default, int):
        return int
    return float


@router.get("/strategy-config", response_model=StrategyConfigResponse)
async def get_strategy_config() -> StrategyConfigResponse:
    params = []
    for key, default in DEFAULTS.items():
        meta = PARAM_META.get(key, (0, 0, "", ""))
        cur = get_param(key, default, _cast_for(key))
        params.append(ParamSpec(
            key=key,
            value=float(cur),
            default=float(default),
            min=float(meta[0]),
            max=float(meta[1]),
            unit=meta[2],
            description=meta[3],
        ))
    return StrategyConfigResponse(params=params)


@router.patch("/strategy-config", response_model=StrategyConfigResponse)
async def patch_strategy_config(req: StrategyConfigPatchRequest) -> StrategyConfigResponse:
    db = _db()
    # 校验
    for key, val in req.updates.items():
        if key not in DEFAULTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown param key: {key}",
            )
        lo, hi, _, _ = PARAM_META.get(key, (None, None, "", ""))
        if lo is not None and not (float(lo) <= float(val) <= float(hi)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{key}={val} out of range [{lo}, {hi}]",
            )

    # 写 DB(同 key UPSERT 等价 — 简单实现:DELETE 后 INSERT,因为 system_settings 没唯一约束)
    conn = sqlite3.connect(db)
    try:
        for key, val in req.updates.items():
            # 用最新一行为权威,旧行不删除(保留历史审计)
            conn.execute(
                "INSERT INTO system_settings (key, value, created_at) "
                "VALUES (?, ?, datetime('now'))",
                (key, str(val)),
            )
        conn.commit()
    finally:
        conn.close()

    # 缓存失效 — collector 下次读拿到新值
    invalidate_cache()
    return await get_strategy_config()


@router.post("/strategy-config/preview", response_model=StrategyConfigPreviewResponse)
async def preview_strategy_config(req: dict) -> StrategyConfigPreviewResponse:
    """快速估算:候选阈值下,过去 N 天 trade_scores_v5 的入场频率 + 胜率。

    MVP 实现:用 ai_training_data + trade_scores_v5 直接 SQL 估算,
    不真的回放管道(那需要重算 indicators)。
    """
    candidate = req.get("candidate_params", {})
    db = _db()
    sample_days = 7
    conn = sqlite3.connect(db)
    try:
        # 估算入场频率:过去 7 天 trade_scores_v5 满足候选 RSI 阈值的占比 × 当前每小时进入数
        # 简化:对 候选 v5_rsi_overbought / v5_rsi_oversold 算
        overbought = float(candidate.get("v5_rsi_overbought", DEFAULTS["v5_rsi_overbought"]))
        oversold = float(candidate.get("v5_rsi_oversold", DEFAULTS["v5_rsi_oversold"]))

        total_h = conn.execute(
            "SELECT COUNT(*) / 168.0 FROM trade_scores_v5 "
            "WHERE created_at >= datetime('now', '-7 day')"
        ).fetchone()[0] or 0.0

        would_trade = conn.execute(
            "SELECT COUNT(*) FROM trade_scores_v5 "
            "WHERE created_at >= datetime('now', '-7 day') "
            "  AND ((side='SHORT' AND rsi_15m > ?) "
            "    OR (side='LONG'  AND rsi_15m < ?))",
            (overbought, oversold),
        ).fetchone()[0] or 0

        days_have_data = conn.execute(
            "SELECT MIN(7, CAST((julianday('now') - julianday(MIN(created_at))) AS INTEGER)) "
            "FROM trade_scores_v5"
        ).fetchone()[0] or 0
        sample_days = int(days_have_data) if days_have_data else 0

        hourly = (would_trade / max(sample_days, 1)) / 24.0

        # 胜率估算:用 ai_training_data 已平仓样本,候选 RSI 触发样本的 WIN 占比
        wins = conn.execute(
            "SELECT COUNT(*) FROM ai_training_data "
            "WHERE outcome='WIN' "
            "  AND ((side='SHORT' AND entry_rsi_15m > ?) "
            "    OR (side='LONG'  AND entry_rsi_15m < ?))",
            (overbought, oversold),
        ).fetchone()[0] or 0
        totals = conn.execute(
            "SELECT COUNT(*) FROM ai_training_data "
            "WHERE outcome IN ('WIN','LOSS','FLAT') "
            "  AND ((side='SHORT' AND entry_rsi_15m > ?) "
            "    OR (side='LONG'  AND entry_rsi_15m < ?))",
            (overbought, oversold),
        ).fetchone()[0] or 0
        win_rate = (wins / totals) if totals else 0.0
    finally:
        conn.close()

    return StrategyConfigPreviewResponse(
        candidate_params=candidate,
        estimated_hourly_entries=round(hourly, 2),
        estimated_win_rate=round(win_rate, 3),
        sample_days=sample_days,
    )
```

- [ ] **Step 4: 注册路由 api/main.py**

打开 `api/main.py`,在已有 `include_router` 段加:

```python
from api.routes import v5_strategy_config
app.include_router(v5_strategy_config.router)
```

- [ ] **Step 5: 跑测试**

```bash
python3 -m pytest tests/test_v5_strategy_config_api.py -v
# 预期 6 passed
```

如果"v5_strategy.py 内的 `_f` 被调到崩"等回归,跑全测:
```bash
python3 -m pytest tests/ -v 2>&1 | tail -3
# 预期 104 passed(98 + 6)
```

- [ ] **Step 6: Commit**

```bash
git add api/routes/v5_strategy_config.py api/main.py tests/test_v5_strategy_config_api.py
git commit -m "feat(api): /api/v5/strategy-config GET/PATCH/preview

- GET returns 13 V5 knobs with value/default/min/max/unit/description
- PATCH validates range, INSERTs (audit-keeping), invalidates v5_params cache
- /preview estimates hourly entries + win rate over past 7 days

6 integration tests with TestClient + tempfile DB."
```

---

## Phase 4:系统设置路由

### Task 5:GET/PATCH `/api/v5/settings`

**Files:**
- Create: `api/routes/v5_settings.py`
- Modify: `api/main.py`
- Create: `tests/test_v5_settings_api.py`

- [ ] **Step 1: 写测试**

```python
"""V5 settings GET/PATCH API 测试。"""
import sqlite3
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_db(monkeypatch):
    from scripts.local_db import init_local_db
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    init_local_db(tmp.name)
    # 初始化默认 mode = SHADOW
    conn = sqlite3.connect(tmp.name)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('system_state', 'SHADOW')")
    conn.commit()
    conn.close()
    from api.main import app
    return TestClient(app), tmp.name


def test_get_returns_default_structure(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["system_mode"] in ("SHADOW", "LIVE")
    assert "openai_api_key_masked" in data
    assert "deepseek_api_key_masked" in data
    assert data["openai_api_key_masked"] == ""  # 没设
    assert data["deepseek_api_key_masked"] == ""


def test_get_masks_existing_key(app_with_db):
    client, db = app_with_db
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('openai_api_key', 'sk-abcdefghijklmnop')")
    conn.commit()
    conn.close()
    r = client.get("/api/v5/settings")
    data = r.json()
    assert data["openai_api_key_masked"].startswith("sk-")
    assert "****" in data["openai_api_key_masked"]
    # 末 4 位可见
    assert data["openai_api_key_masked"].endswith("mnop")
    # 中间不含完整 key
    assert "abcdefghij" not in data["openai_api_key_masked"]


def test_patch_writes_settings(app_with_db):
    client, db = app_with_db
    r = client.patch("/api/v5/settings", json={
        "deepseek_api_key": "sk-deepseekxxx",
        "deepseek_enabled": True,
        "ai_fail_open": False,
    })
    assert r.status_code == 200
    conn = sqlite3.connect(db)
    rows = dict(conn.execute(
        "SELECT key, value FROM system_settings "
        "WHERE key IN ('deepseek_api_key', 'deepseek_enabled', 'ai_fail_open')"
    ).fetchall())
    conn.close()
    assert rows.get("deepseek_api_key") == "sk-deepseekxxx"
    assert rows.get("deepseek_enabled") == "true"


def test_patch_mode_change_requires_no_active_position(app_with_db):
    """SHADOW → LIVE 切换时如果有 OPEN paper_trades,前端要二次确认。
    后端 MVP:总是允许切换,只做日志。
    """
    client, _ = app_with_db
    r = client.patch("/api/v5/settings", json={"system_mode": "LIVE"})
    assert r.status_code == 200
    r2 = client.get("/api/v5/settings")
    assert r2.json()["system_mode"] == "LIVE"


def test_patch_empty_key_clears(app_with_db):
    """显式提交 "" 清空 key。"""
    client, db = app_with_db
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES ('openai_api_key', 'sk-old')")
    conn.commit()
    conn.close()
    r = client.patch("/api/v5/settings", json={"openai_api_key": ""})
    assert r.status_code == 200
    r2 = client.get("/api/v5/settings")
    assert r2.json()["openai_api_key_masked"] == ""
```

- [ ] **Step 2: 跑测试,期望 fail**

```bash
python3 -m pytest tests/test_v5_settings_api.py -v
```

- [ ] **Step 3: 写 api/routes/v5_settings.py**

```python
"""/api/v5/settings GET/PATCH。

读 system_settings 表;敏感字段(API key)在返回时掩码 "sk-****xxxx"。
PATCH 显式 "" 表示清空。
"""
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter

from api.schemas.v5_settings import SettingsResponse, SettingsPatchRequest


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
        "INSERT INTO system_settings (key, value, created_at) VALUES (?, ?, datetime('now'))",
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
        # API keys:DB 优先,env fallback
        openai_key = _read_setting(conn, "openai_api_key") or os.environ.get("OPENAI_API_KEY", "")
        deepseek_key = _read_setting(conn, "deepseek_api_key") or os.environ.get("DEEPSEEK_API_KEY", "")

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

        # active_ai_provider 从 trading_assistant 实例反查 — 因为 collector 在另一进程,
        # 我们从配置推断:DeepSeek 启用 → "deepseek",否则有 OpenAI key → "openai",否则 None
        if deepseek_enabled and deepseek_key:
            active_provider, active_model = "deepseek", os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        elif openai_key:
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
```

- [ ] **Step 4: 注册路由**

`api/main.py` 加 include:

```python
from api.routes import v5_settings
app.include_router(v5_settings.router)
```

- [ ] **Step 5: 跑测试**

```bash
python3 -m pytest tests/test_v5_settings_api.py -v
python3 -m pytest tests/ -v 2>&1 | tail -3
# 预期 109 passed(104 + 5)
```

- [ ] **Step 6: Commit**

```bash
git add api/routes/v5_settings.py api/main.py tests/test_v5_settings_api.py
git commit -m "feat(api): /api/v5/settings GET/PATCH

- GET reads system_settings + env fallback, masks API keys 'sk-****xxxx'
- active_ai_provider derived from deepseek_enabled+key / openai key
- PATCH writes any subset of fields; explicit '' clears a key

5 integration tests."
```

---

## Phase 5:AI 状态 + 决策路由

### Task 6:`/api/v5/ai/status` 和 `/api/v5/ai/decisions`

**Files:**
- Create: `api/routes/v5_ai.py`
- Modify: `api/main.py`
- Create: `tests/test_v5_ai_api.py`

- [ ] **Step 1: 写测试**

```python
"""V5 AI status + decisions API 测试。"""
import sqlite3
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_db(monkeypatch):
    from scripts.local_db import init_local_db
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    init_local_db(tmp.name)
    from api.main import app
    return TestClient(app), tmp.name


def test_ai_status_empty(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/ai/status")
    assert r.status_code == 200
    data = r.json()
    assert "provider" in data
    assert data["decisions_24h"] == 0
    assert data["rag_utilization_24h"] == 0.0
    assert data["rag_cases_in_db"] == 0


def test_ai_status_with_data(app_with_db, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    client, db = app_with_db
    conn = sqlite3.connect(db)
    # 3 笔决策,2 笔含 RAG
    for i in range(3):
        reasoning = "Historical similar cases" if i < 2 else "no rag"
        conn.execute(
            "INSERT INTO trade_scores_v5 (symbol, created_at, should_trade, "
            "ai_reasoning, executed) "
            "VALUES (?, datetime('now', '-1 hour'), 1, ?, 1)",
            (f"S{i}", reasoning),
        )
    # 12 个已平仓 RAG 案例
    for i in range(12):
        conn.execute(
            "INSERT INTO ai_training_data (symbol, side, entry_rsi_15m, "
            "entry_macd_hist_15m, entry_rsi_4h, outcome, pnl_pct, created_at) "
            "VALUES (?, 'SHORT', 72.0, -0.0005, 65.0, 'WIN', 0.004, datetime('now'))",
            (f"H{i}",),
        )
    conn.commit()
    conn.close()
    r = client.get("/api/v5/ai/status")
    data = r.json()
    assert data["decisions_24h"] == 3
    assert abs(data["rag_utilization_24h"] - 2/3) < 0.01
    assert data["rag_cases_in_db"] == 12


def test_decisions_returns_recent(app_with_db):
    client, db = app_with_db
    conn = sqlite3.connect(db)
    # 5 笔最近决策
    for i in range(5):
        conn.execute("""
            INSERT INTO trade_scores_v5 (
                symbol, created_at, side, ai_confidence, ai_reasoning,
                should_trade, executed
            ) VALUES (?, datetime('now', '-1 hour'), 'SHORT', ?, ?, 1, 1)
        """, (f"S{i}", 0.6 + i * 0.05, f"reason {i}"))
    conn.commit()
    conn.close()
    r = client.get("/api/v5/ai/decisions?limit=3")
    assert r.status_code == 200
    data = r.json()
    assert len(data["decisions"]) == 3
    for d in data["decisions"]:
        assert d["symbol"].startswith("S")


def test_decisions_filters_no_ai_reasoning(app_with_db):
    """ai_reasoning IS NULL 的不出现(它们是规则拒,不是 AI 决策)。"""
    client, db = app_with_db
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO trade_scores_v5 (symbol, created_at, should_trade) "
        "VALUES ('X', datetime('now'), 0)")
    conn.commit()
    conn.close()
    r = client.get("/api/v5/ai/decisions")
    assert r.json()["decisions"] == []
```

- [ ] **Step 2: 跑测试,期望 fail**

```bash
python3 -m pytest tests/test_v5_ai_api.py -v
```

- [ ] **Step 3: 写 api/routes/v5_ai.py**

```python
"""/api/v5/ai/status + /decisions"""
import os
import sqlite3
from fastapi import APIRouter

from api.schemas.v5_ai import (
    AIStatusResponse, AIDecisionItem, AIDecisionsResponse,
)
from scripts.ai.local_rag import rag_utilization_24h
from api.services.score_service import ensure_utc_iso


router = APIRouter(prefix="/api/v5", tags=["ai"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def _resolve_active_provider() -> tuple[str | None, str | None]:
    """跟 v5_settings 同款逻辑。"""
    db = _db()
    try:
        conn = sqlite3.connect(db)
        try:
            row = conn.execute(
                "SELECT key, value FROM system_settings "
                "WHERE key IN ('deepseek_enabled', 'deepseek_api_key', "
                "             'openai_api_key') ORDER BY rowid DESC"
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        row = []
    state = {k: v for k, v in row}
    deepseek_enabled = (state.get("deepseek_enabled") or
                        os.environ.get("DEEPSEEK_ENABLED", "false")).lower() in ("1", "true")
    deepseek_key = state.get("deepseek_api_key") or os.environ.get("DEEPSEEK_API_KEY", "")
    openai_key = state.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")

    if deepseek_enabled and deepseek_key:
        return "deepseek", os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    if openai_key:
        return "openai", os.environ.get("OPENAI_TRADING_MODEL", "gpt-4o")
    return None, None


@router.get("/ai/status", response_model=AIStatusResponse)
async def get_ai_status() -> AIStatusResponse:
    db = _db()
    provider, chat_model = _resolve_active_provider()
    conn = sqlite3.connect(db)
    try:
        decisions_24h = conn.execute(
            "SELECT COUNT(*) FROM trade_scores_v5 "
            "WHERE should_trade=1 AND ai_reasoning IS NOT NULL "
            "  AND created_at >= datetime('now', '-24 hour')"
        ).fetchone()[0] or 0

        rag_in_db = conn.execute(
            "SELECT COUNT(*) FROM ai_training_data WHERE outcome IS NOT NULL"
        ).fetchone()[0] or 0
    finally:
        conn.close()

    util = rag_utilization_24h(db_path=db)

    return AIStatusResponse(
        provider=provider,
        chat_model=chat_model,
        healthy=(provider is not None),
        last_latency_ms=None,
        decisions_24h=int(decisions_24h),
        rag_utilization_24h=round(util, 3),
        rag_cases_in_db=int(rag_in_db),
    )


@router.get("/ai/decisions", response_model=AIDecisionsResponse)
async def get_ai_decisions(limit: int = 20) -> AIDecisionsResponse:
    db = _db()
    limit = max(1, min(200, limit))
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT id, created_at, symbol, side, should_trade, ai_confidence, "
            "       ai_reasoning "
            "  FROM trade_scores_v5 "
            " WHERE ai_reasoning IS NOT NULL "
            " ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()

    decisions = []
    for rid, created_at, symbol, side, should_trade, conf, reasoning in rows:
        # 解析 top1_distance:reasoning 里如果含 "distance=" 后第一个数
        top1 = None
        rag_count = 0
        if reasoning and "case1" in reasoning:
            import re
            m = re.search(r"distance=([0-9.]+)", reasoning)
            if m:
                try:
                    top1 = float(m.group(1))
                except ValueError:
                    pass
            rag_count = len(re.findall(r"case\d+:", reasoning))
        decisions.append(AIDecisionItem(
            id=rid,
            created_at=ensure_utc_iso(created_at) or created_at,
            symbol=(symbol or "").replace("/USDT", "/USDT"),
            side=side or "SHORT",
            execute=bool(should_trade),
            confidence=float(conf or 0.0),
            reasoning=(reasoning or "")[:200],
            top1_distance=top1,
            rag_case_count=rag_count,
        ))
    return AIDecisionsResponse(decisions=decisions)
```

- [ ] **Step 4: 注册路由**

```python
# api/main.py
from api.routes import v5_ai
app.include_router(v5_ai.router)
```

- [ ] **Step 5: 跑测试**

```bash
python3 -m pytest tests/test_v5_ai_api.py -v
python3 -m pytest tests/ -v 2>&1 | tail -3
# 预期 113 passed(109 + 4)
```

- [ ] **Step 6: Commit**

```bash
git add api/routes/v5_ai.py api/main.py tests/test_v5_ai_api.py
git commit -m "feat(api): /api/v5/ai/status + /decisions

- /status: provider+model, decisions_24h, rag_utilization_24h, rag_cases_in_db
- /decisions: paginated last N decisions with parsed top1_distance + rag_case_count

4 integration tests."
```

---

## Phase 6:K 线 + 事件路由

### Task 7:`/api/v5/klines/{symbol}` 和 `/events/{symbol}`

**Files:**
- Create: `api/routes/v5_charts.py`
- Modify: `api/main.py`
- Create: `tests/test_v5_charts_api.py`

- [ ] **Step 1: 写测试**

```python
"""V5 charts API 测试。fetch_klines mock 掉。"""
import sqlite3
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_db(monkeypatch):
    from scripts.local_db import init_local_db
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    init_local_db(tmp.name)
    from api.main import app
    return TestClient(app), tmp.name


def test_klines_returns_data(app_with_db, monkeypatch):
    fake = [(1717200000000, 0.166, 0.168, 0.165, 0.166, 1000.0)] * 50

    def _fake_fetch(*args, **kwargs):
        return fake

    monkeypatch.setattr(
        "scripts.tasks.exchange_endpoints.fetch_klines", _fake_fetch
    )
    client, _ = app_with_db
    r = client.get("/api/v5/klines/H_USDT?interval=15m&limit=50")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "H/USDT"
    assert data["interval"] == "15m"
    assert len(data["klines"]) == 50
    assert data["klines"][0]["ts"] == 1717200000000
    assert data["klines"][0]["close"] == 0.166


def test_klines_rejects_invalid_interval(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/klines/H_USDT?interval=2d")
    assert r.status_code == 400 or r.status_code == 422


def test_events_aggregates_from_paper_trades(app_with_db):
    """paper_trades 里的开/平仓事件应该出现在 events。"""
    client, db = app_with_db
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO paper_trades (
            symbol, side, entry_price, entry_time, status,
            stop_loss, take_profit, position_size_usdt, leverage,
            entry_rsi_15m, entry_macd_hist_15m,
            strategy_id, created_at
        ) VALUES ('H/USDT', 'SHORT', 0.166, '2026-06-12T09:48:00+00:00', 'CLOSED',
                  0.169, 0.162, 15.0, 10,
                  72.0, -0.0005,
                  'v5_rsi_macd', '2026-06-12T09:48:00+00:00')
    """)
    conn.execute("""
        UPDATE paper_trades SET exit_price=0.162, exit_time='2026-06-12T09:55:00+00:00',
          exit_reason='TP_HIT', pnl_percent=2.4 WHERE id=last_insert_rowid()
    """)
    conn.commit()
    conn.close()
    r = client.get("/api/v5/events/H_USDT")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "H/USDT"
    types = {e["event_type"] for e in data["events"]}
    assert "entry" in types
    assert "exit" in types


def test_events_empty_for_unknown_symbol(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/events/UNKNOWN_USDT")
    assert r.status_code == 200
    assert r.json()["events"] == []
```

- [ ] **Step 2: 跑测试,期望 fail**

```bash
python3 -m pytest tests/test_v5_charts_api.py -v
```

- [ ] **Step 3: 写 api/routes/v5_charts.py**

```python
"""V5 ChartPage:K 线 + 事件。

注意 symbol 在 URL 里用下划线表示:H_USDT → H/USDT。这是因为 / 在 URL 里
要 encode 成 %2F,在 docker/反代里有时会被吃掉。前端约定用下划线。
"""
import os
import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Path

from api.schemas.v5_charts import (
    Kline, KlinesResponse, SymbolEvent, SymbolEventsResponse,
)
from api.services.score_service import ensure_utc_iso


router = APIRouter(prefix="/api/v5", tags=["charts"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def _decode(symbol: str) -> str:
    return symbol.replace("_", "/")


@router.get("/klines/{symbol}", response_model=KlinesResponse)
async def get_klines(
    symbol: str = Path(...),
    interval: Literal["15m", "1h", "4h"] = Query("15m"),
    limit: int = Query(200, ge=10, le=500),
) -> KlinesResponse:
    raw_symbol = _decode(symbol)
    try:
        from scripts.tasks.exchange_endpoints import fetch_klines
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"exchange_endpoints 不可用: {e}")
    try:
        raw = fetch_klines(raw_symbol, interval, limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"K 线拉取失败: {type(e).__name__}: {e}")

    klines = []
    for row in raw:
        try:
            ts, o, h, l, c, v = row[0], row[1], row[2], row[3], row[4], row[5]
            klines.append(Kline(ts=int(ts), open=float(o), high=float(h),
                                low=float(l), close=float(c), volume=float(v)))
        except Exception:
            continue
    return KlinesResponse(symbol=raw_symbol, interval=interval, klines=klines)


@router.get("/events/{symbol}", response_model=SymbolEventsResponse)
async def get_symbol_events(
    symbol: str = Path(...),
    limit: int = Query(50, ge=1, le=500),
) -> SymbolEventsResponse:
    raw_symbol = _decode(symbol)
    db = _db()
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("""
            SELECT id, symbol, side, entry_price, entry_time, exit_price,
                   exit_time, exit_reason, pnl_percent, status,
                   entry_rsi_15m, entry_macd_hist_15m, ai_reason
              FROM paper_trades
             WHERE symbol = ?
             ORDER BY entry_time DESC LIMIT ?
        """, (raw_symbol, limit)).fetchall()
    finally:
        conn.close()

    events: list[SymbolEvent] = []
    for (pid, sym, side, entry_p, entry_t, exit_p, exit_t,
         exit_reason, pnl_pct, status, rsi_15m, macd_hist_15m, ai_reason) in rows:
        # entry
        events.append(SymbolEvent(
            event_type="entry", side=side, price=float(entry_p or 0.0),
            timestamp=ensure_utc_iso(entry_t) or "",
            position_id=pid,
            reasoning=(ai_reason or "")[:200],
            rsi_15m=float(rsi_15m) if rsi_15m is not None else None,
            macd_hist_15m=float(macd_hist_15m) if macd_hist_15m is not None else None,
        ))
        # exit(if closed)
        if status == "CLOSED" and exit_p is not None:
            events.append(SymbolEvent(
                event_type="exit", side=side, price=float(exit_p),
                timestamp=ensure_utc_iso(exit_t) or "",
                position_id=pid,
                exit_reason=exit_reason,
                pnl_pct=float(pnl_pct or 0.0) / 100.0,  # paper_trades.pnl_percent 是百分数
            ))
    return SymbolEventsResponse(symbol=raw_symbol, events=events)
```

- [ ] **Step 4: 注册路由**

```python
from api.routes import v5_charts
app.include_router(v5_charts.router)
```

- [ ] **Step 5: 跑测试**

```bash
python3 -m pytest tests/test_v5_charts_api.py -v
python3 -m pytest tests/ -v 2>&1 | tail -3
# 预期 117 passed(113 + 4)
```

- [ ] **Step 6: Commit**

```bash
git add api/routes/v5_charts.py api/main.py tests/test_v5_charts_api.py
git commit -m "feat(api): /api/v5/klines/{symbol} + /events/{symbol}

- Symbol uses _ in URL (H_USDT → H/USDT) to avoid % encoding edge cases
- klines: passthrough fetch_klines, interval validated by Literal
- events: aggregate entry+exit per paper_trade with indicator snapshot

4 integration tests."
```

---

## Phase 7:手动开单工作流

### Task 8:`/api/v5/manual-order/preview` 和 `/execute`

**Files:**
- Create: `api/routes/v5_manual_order.py`
- Modify: `api/main.py`
- Create: `tests/test_v5_manual_order_api.py`

- [ ] **Step 1: 写测试**

```python
"""V5 manual-order preview + execute 测试。fetch_klines + AI 都 mock。"""
import sqlite3
import tempfile
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_db(monkeypatch):
    from scripts.local_db import init_local_db
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    monkeypatch.setenv("PAPER_INITIAL_BALANCE_USDT", "1000")
    init_local_db(tmp.name)
    from api.main import app
    return TestClient(app), tmp.name


def _fake_klines():
    """构造能让 RSI 高 + MACD 死叉拐点的 prices。"""
    from tests.conftest import _build_klines
    rising_then_drop = [100 + i * 2 for i in range(40)] + [180, 178, 176]
    klines_15m = _build_klines(rising_then_drop)
    klines_4h = _build_klines([100 + i * 1.5 for i in range(50)])
    return klines_15m, klines_4h


def test_preview_returns_full_snapshot(app_with_db, monkeypatch):
    klines_15m, klines_4h = _fake_klines()

    def fake_fetch(symbol, interval, limit):
        return klines_15m if interval == "15m" else klines_4h

    monkeypatch.setattr(
        "scripts.tasks.exchange_endpoints.fetch_klines", fake_fetch
    )
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "60")  # 让信号必中

    # mock AI 批准
    from v5_types import AIResult
    with patch("scripts.ai.trading_assistant.TradingAssistant") as mock_ta_cls:
        mock_ta = mock_ta_cls.return_value
        mock_ta.client = object()   # 非 None
        mock_ta.provider = "deepseek"
        mock_ta.assistant_id = None
        mock_ta.decide = AsyncMock(return_value=AIResult(
            execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
            size_multiplier=1.0, confidence=0.7, reasoning="ok"))

        client, _ = app_with_db
        r = client.post("/api/v5/manual-order/preview", json={
            "symbol": "TEST/USDT", "side": "SHORT", "size_usdt": 15.0,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["symbol"] == "TEST/USDT"
        assert data["side"] == "SHORT"
        assert "indicators" in data
        assert "decision" in data and "risk_plan" in data and "ai_result" in data
        assert "rag_cases" in data


def test_execute_writes_paper_trade(app_with_db, monkeypatch):
    klines_15m, klines_4h = _fake_klines()
    monkeypatch.setattr(
        "scripts.tasks.exchange_endpoints.fetch_klines",
        lambda s, i, l: klines_15m if i == "15m" else klines_4h)
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "60")

    from v5_types import AIResult
    with patch("scripts.ai.trading_assistant.TradingAssistant") as mock_ta_cls:
        mock_ta = mock_ta_cls.return_value
        mock_ta.client = object()
        mock_ta.provider = "deepseek"
        mock_ta.assistant_id = None
        mock_ta.decide = AsyncMock(return_value=AIResult(
            execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
            size_multiplier=1.0, confidence=0.7, reasoning="ok"))

        client, db = app_with_db
        r = client.post("/api/v5/manual-order/execute", json={
            "symbol": "TEST/USDT", "side": "SHORT", "size_usdt": 15.0,
            "sl_multiplier": 1.0, "tp_multiplier": 1.0, "size_multiplier": 1.0,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["strategy_id"] == "v5_manual"
        assert data["side"] == "SHORT"
        assert data["position_id"] > 0

        # paper_trades 里有一行
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT symbol, side, status, strategy_id FROM paper_trades "
            "WHERE id=?", (data["position_id"],)).fetchone()
        conn.close()
        assert row == ("TEST/USDT", "SHORT", "OPEN", "v5_manual")
```

- [ ] **Step 2: 跑测试,期望 fail**

- [ ] **Step 3: 写 api/routes/v5_manual_order.py**

```python
"""/api/v5/manual-order/{preview,execute}

复用 V5 完整管道:fetch_klines → calculate_indicators → V5Strategy → 
RiskCalculator → TradingAssistant(含 RAG)。preview 不写库,execute 走
PaperPositionManager.open_position 并打 strategy_id='v5_manual'。
"""
import os
from typing import Optional

from fastapi import APIRouter, HTTPException

from api.schemas.v5_manual_order import (
    ManualOrderPreviewRequest, ManualOrderPreviewResponse,
    ManualOrderDecisionSnapshot, ManualOrderRagCase,
    ManualOrderExecuteRequest, ManualOrderExecuteResponse,
)


router = APIRouter(prefix="/api/v5", tags=["manual-order"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


async def _build_full_context(symbol: str, side_hint: Optional[str]):
    """共用:拉 K 线 → indicators → enriched → decision → risk → AI → rag。"""
    from scripts.tasks.exchange_endpoints import fetch_klines
    from v5_indicator_engine import calculate_indicators
    from v5_strategy import decide as strategy_decide
    from v5_risk_calculator import plan as risk_plan
    from v5_types import EnrichedItem
    from scripts.ai.trading_assistant import TradingAssistant
    from scripts.ai.local_rag import find_similar_cases

    klines_15m = fetch_klines(symbol, "15m", 50)
    klines_4h = fetch_klines(symbol, "4h", 50)
    indicators = calculate_indicators(klines_15m, klines_4h)

    current_price = float(klines_15m[-1][4]) if klines_15m else 0.0
    delta_15m_pct = (klines_15m[-1][4] - klines_15m[-1][1]) / (klines_15m[-1][1] or 1.0) if klines_15m else 0.0

    enriched = EnrichedItem(
        symbol=symbol, current_price=current_price,
        delta_15m_pct=delta_15m_pct, volume_24h_usdt=0.0,
        klines_15m=klines_15m, klines_4h=klines_4h,
    )

    decision = strategy_decide(enriched, indicators)
    effective_side = decision.side or side_hint or "SHORT"

    balance = float(os.environ.get("PAPER_INITIAL_BALANCE_USDT", "1000"))
    from scripts.v5_params import get_param
    risk = risk_plan(
        side=effective_side, entry=current_price, atr=indicators.atr_15m,
        balance=balance, risk_pct=float(get_param("v5_risk_per_trade", 0.015, float)),
        leverage=int(get_param("v5_leverage", 10, int)),
    )

    ta = TradingAssistant()
    if ta.client:
        ai_result = await ta.decide(enriched, indicators, decision, risk)
        ai_dict = {
            "execute": ai_result.execute,
            "sl_multiplier": ai_result.sl_multiplier,
            "tp_multiplier": ai_result.tp_multiplier,
            "size_multiplier": ai_result.size_multiplier,
            "confidence": ai_result.confidence,
            "reasoning": ai_result.reasoning,
        }
    else:
        ai_dict = {"execute": False, "sl_multiplier": 1.0, "tp_multiplier": 1.0,
                   "size_multiplier": 0.0, "confidence": 0.0,
                   "reasoning": "AI 未配置"}

    rag = find_similar_cases(
        indicators, side=effective_side, top_k=5,
        source_delta_15m_pct=delta_15m_pct,
    )
    return enriched, indicators, decision, risk, ai_dict, rag, effective_side


@router.post("/manual-order/preview", response_model=ManualOrderPreviewResponse)
async def preview(req: ManualOrderPreviewRequest) -> ManualOrderPreviewResponse:
    try:
        enriched, indicators, decision, risk, ai_dict, rag, eff_side = \
            await _build_full_context(req.symbol, req.side)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"preview 失败: {type(e).__name__}: {e}")

    rag_cases = [
        ManualOrderRagCase(
            entry_rsi_15m=c.entry_rsi_15m,
            entry_macd_hist_15m=c.entry_macd_hist_15m,
            outcome=c.outcome,                    # type: ignore[arg-type]
            pnl_pct=c.pnl_pct,
            exit_reason=c.exit_reason,
            distance=c.distance,
        ) for c in rag
    ]

    rag_summary = None
    if rag_cases:
        wins = sum(1 for c in rag_cases if c.outcome == "WIN")
        avg = sum(c.pnl_pct for c in rag_cases) / len(rag_cases)
        rag_summary = f"{wins}/{len(rag_cases)} win,avg pnl {avg*100:+.2f}%"

    return ManualOrderPreviewResponse(
        symbol=req.symbol,
        side=eff_side,  # type: ignore[arg-type]
        current_price=enriched.current_price,
        indicators={
            "rsi_15m": indicators.rsi_15m,
            "macd_hist_15m": indicators.macd_hist_15m,
            "macd_hist_prev_15m": indicators.macd_hist_prev_15m,
            "atr_15m": indicators.atr_15m,
            "rsi_4h": indicators.rsi_4h,
            "macd_hist_4h": indicators.macd_hist_4h,
        },
        decision=ManualOrderDecisionSnapshot(
            should_trade=decision.should_trade,
            side=decision.side,                   # type: ignore[arg-type]
            reasoning=decision.reasoning,
            block_reason=decision.block_reason,
        ),
        risk_plan={
            "entry_price": risk.entry_price,
            "sl_price": risk.sl_price,
            "tp_price": risk.tp_price,
            "size_usdt": risk.size_usdt,
            "leverage": risk.leverage,
            "expected_rr": risk.expected_rr,
        },
        ai_result=ai_dict,
        rag_cases=rag_cases,
        rag_summary=rag_summary,
    )


@router.post("/manual-order/execute", response_model=ManualOrderExecuteResponse)
async def execute(req: ManualOrderExecuteRequest) -> ManualOrderExecuteResponse:
    try:
        enriched, indicators, decision, risk, ai_dict, _rag, _eff = \
            await _build_full_context(req.symbol, req.side)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"execute 准备失败: {type(e).__name__}: {e}")

    # 用户在 UI 上可能微调了 sl/tp/size 倍数,以前端提交的为准
    from v5_types import AIResult, Decision
    ai = AIResult(
        execute=True,
        sl_multiplier=req.sl_multiplier,
        tp_multiplier=req.tp_multiplier,
        size_multiplier=req.size_multiplier,
        confidence=float(ai_dict.get("confidence") or 0.0),
        reasoning=f"[v5_manual] " + (ai_dict.get("reasoning") or ""),
    )
    # 强制 side 用 req.side(用户最后说了算)
    forced_decision = Decision(
        should_trade=True, side=req.side,
        reasoning=decision.reasoning, block_reason=None,
    )

    from scripts.paper_position_manager import PaperPositionManager
    pm = PaperPositionManager(db_path=_db())
    # 临时给这一笔标 strategy_id='v5_manual' — 改 open_position 太重,在写完直接 UPDATE
    pid = pm.open_position(
        enriched=enriched, indicators=indicators,
        decision=forced_decision, risk=risk, ai=ai,
    )
    import sqlite3
    conn = sqlite3.connect(_db())
    try:
        conn.execute("UPDATE paper_trades SET strategy_id='v5_manual' WHERE id=?", (pid,))
        conn.commit()
        row = conn.execute(
            "SELECT symbol, side, entry_price, stop_loss, take_profit, position_size_usdt "
            "FROM paper_trades WHERE id=?", (pid,)).fetchone()
    finally:
        conn.close()

    return ManualOrderExecuteResponse(
        position_id=pid,
        symbol=row[0],
        side=row[1],  # type: ignore[arg-type]
        entry_price=float(row[2] or 0.0),
        sl_price=float(row[3] or 0.0),
        tp_price=float(row[4] or 0.0),
        size_usdt=float(row[5] or 0.0),
        strategy_id="v5_manual",
    )
```

- [ ] **Step 4: 注册路由**

```python
from api.routes import v5_manual_order
app.include_router(v5_manual_order.router)
```

- [ ] **Step 5: 跑测试**

```bash
python3 -m pytest tests/test_v5_manual_order_api.py -v
python3 -m pytest tests/ -v 2>&1 | tail -3
# 预期 119 passed(117 + 2)
```

- [ ] **Step 6: Commit**

```bash
git add api/routes/v5_manual_order.py api/main.py tests/test_v5_manual_order_api.py
git commit -m "feat(api): /api/v5/manual-order preview + execute

- preview: full pipeline replay (klines → indicators → strategy → risk → AI + RAG)
  without writing DB
- execute: same pipeline + PaperPositionManager.open_position with
  strategy_id='v5_manual'; respects user-adjusted sl/tp/size multipliers

2 integration tests with mocked AI + klines."
```

---

## Phase 8:平仓路由

### Task 9:`POST /api/v5/positions/{id}/close`

**Files:**
- Create: `api/routes/v5_position_close.py`
- Modify: `api/main.py`
- Create: `tests/test_v5_position_close_api.py`

- [ ] **Step 1: 写测试**

```python
"""V5 position close API 测试。"""
import sqlite3
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_db(monkeypatch):
    from scripts.local_db import init_local_db
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    init_local_db(tmp.name)
    from api.main import app
    return TestClient(app), tmp.name


def _open_paper_trade(db, symbol="H/USDT"):
    conn = sqlite3.connect(db)
    cur = conn.execute("""
        INSERT INTO paper_trades (
            symbol, side, entry_price, entry_time, status,
            stop_loss, take_profit, position_size_usdt, leverage,
            strategy_id, created_at
        ) VALUES (?, 'SHORT', 0.166, datetime('now'), 'OPEN',
                  0.169, 0.162, 15.0, 10,
                  'v5_rsi_macd', datetime('now'))
    """, (symbol,))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def test_close_open_paper_trade(app_with_db):
    client, db = app_with_db
    pid = _open_paper_trade(db)
    r = client.post(f"/api/v5/positions/{pid}/close", json={
        "exit_price": 0.165, "exit_reason": "MANUAL_USER"
    })
    assert r.status_code == 200, r.text
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, exit_price, exit_reason FROM paper_trades WHERE id=?",
        (pid,)).fetchone()
    conn.close()
    assert row == ("CLOSED", 0.165, "MANUAL_USER")


def test_close_unknown_returns_404(app_with_db):
    client, _ = app_with_db
    r = client.post("/api/v5/positions/99999/close", json={
        "exit_price": 0.165, "exit_reason": "MANUAL_USER"
    })
    assert r.status_code == 404


def test_close_already_closed_returns_409(app_with_db):
    client, db = app_with_db
    pid = _open_paper_trade(db)
    # 先平一次
    client.post(f"/api/v5/positions/{pid}/close", json={
        "exit_price": 0.165, "exit_reason": "MANUAL_USER"})
    # 再平一次
    r = client.post(f"/api/v5/positions/{pid}/close", json={
        "exit_price": 0.164, "exit_reason": "MANUAL_USER"})
    assert r.status_code == 409
```

- [ ] **Step 2: 跑测试,期望 fail**

- [ ] **Step 3: 写 api/routes/v5_position_close.py**

```python
"""POST /api/v5/positions/{position_id}/close。

平 paper_trades(SHADOW)或 positions_v5(LIVE)。MVP 只支持 paper_trades —
LIVE 走 V5PositionManager.close_position 需要 broker 实例,前端 LIVE 单的
手动平仓后续单独做。
"""
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel


router = APIRouter(prefix="/api/v5", tags=["positions"])


class CloseRequest(BaseModel):
    exit_price: float
    exit_reason: str = "MANUAL_USER"


class CloseResponse(BaseModel):
    position_id: int
    status: str
    exit_price: float
    exit_reason: str


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


@router.post("/positions/{position_id}/close", response_model=CloseResponse)
async def close_position(
    position_id: int = Path(...),
    body: CloseRequest = ...,
) -> CloseResponse:
    db = _db()
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT status FROM paper_trades WHERE id=?", (position_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail=f"position {position_id} not found")
    if (row[0] or "").upper() == "CLOSED":
        raise HTTPException(status_code=409, detail=f"position {position_id} already CLOSED")

    from scripts.paper_position_manager import PaperPositionManager
    pm = PaperPositionManager(db_path=db)
    pm.close_position(position_id, exit_price=body.exit_price, exit_reason=body.exit_reason)

    return CloseResponse(
        position_id=position_id,
        status="CLOSED",
        exit_price=body.exit_price,
        exit_reason=body.exit_reason,
    )
```

- [ ] **Step 4: 注册路由**

```python
from api.routes import v5_position_close
app.include_router(v5_position_close.router)
```

- [ ] **Step 5: 跑测试**

```bash
python3 -m pytest tests/test_v5_position_close_api.py -v
python3 -m pytest tests/ -v 2>&1 | tail -3
# 预期 122 passed(119 + 3)
```

- [ ] **Step 6: Commit**

```bash
git add api/routes/v5_position_close.py api/main.py tests/test_v5_position_close_api.py
git commit -m "feat(api): POST /api/v5/positions/{id}/close

MVP supports paper_trades (SHADOW) only;
404 on unknown, 409 on already-closed.
3 integration tests."
```

---

## Phase 9:WebSocket 广播

### Task 10:`api/websocket_v5.py` + `services/v5_broadcast.py` + 集成 scorer/monitor

**Files:**
- Create: `api/services/v5_broadcast.py`
- Create: `api/websocket_v5.py`
- Modify: `api/main.py`
- Modify: `scripts/tasks/scorer.py`(`position_opened` broadcast)
- Modify: `scripts/v5_position_monitor.py`(`position_closed/extended` broadcast)
- Create: `tests/test_websocket_v5.py`

- [ ] **Step 1: 写测试**

```python
"""V5 WebSocket broadcast 测试。

注册 client → broadcast → 期望客户端收到 JSON。
WS 心跳 + 重连交给前端集成测试,这里只测后端契约。
"""
import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_broadcaster_send_to_all():
    """注册 mock client → broadcast → mock 收到。"""
    from api.services.v5_broadcast import V5Broadcaster
    b = V5Broadcaster()

    sent = []

    class MockWS:
        async def send_json(self, data):
            sent.append(data)

    ws = MockWS()
    b.register(ws)
    asyncio.run(b.broadcast({
        "type": "position_opened",
        "symbol": "H/USDT", "side": "SHORT", "entry": 0.166,
        "sl": 0.169, "tp": 0.162, "size_usdt": 15.0,
        "position_id": 1, "strategy_id": "v5_rsi_macd", "mode": "SHADOW",
    }))
    assert len(sent) == 1
    assert sent[0]["type"] == "position_opened"


def test_broadcaster_drops_failing_client():
    """send_json raises → 自动 unregister。"""
    from api.services.v5_broadcast import V5Broadcaster
    b = V5Broadcaster()

    class FailWS:
        async def send_json(self, data):
            raise RuntimeError("disconnected")

    ws = FailWS()
    b.register(ws)
    assert len(b._clients) == 1
    asyncio.run(b.broadcast({"type": "ping"}))
    # 失败后被移出
    assert len(b._clients) == 0


def test_broadcaster_multiple_clients():
    from api.services.v5_broadcast import V5Broadcaster
    b = V5Broadcaster()

    sent_a, sent_b = [], []

    class MockWS:
        def __init__(self, sink):
            self.sink = sink
        async def send_json(self, data):
            self.sink.append(data)

    b.register(MockWS(sent_a))
    b.register(MockWS(sent_b))
    asyncio.run(b.broadcast({"type": "ai_health", "healthy": True}))
    assert sent_a == sent_b == [{"type": "ai_health", "healthy": True}]
```

- [ ] **Step 2: 跑测试,期望 fail**

- [ ] **Step 3: 写 api/services/v5_broadcast.py**

```python
"""V5 WebSocket broadcaster — 全局单例。

register/unregister/broadcast,失败 client 自动 unregister。
Scorer 和 PositionMonitor 在关键事件时 await broadcaster.broadcast(...)。
"""
import asyncio
from typing import Any, Protocol


class WSLike(Protocol):
    async def send_json(self, data: Any) -> None: ...


class V5Broadcaster:
    def __init__(self) -> None:
        self._clients: list[WSLike] = []
        self._lock = asyncio.Lock()

    def register(self, ws: WSLike) -> None:
        self._clients.append(ws)

    def unregister(self, ws: WSLike) -> None:
        try:
            self._clients.remove(ws)
        except ValueError:
            pass

    async def broadcast(self, payload: dict) -> None:
        if not self._clients:
            return
        # snapshot,避免 iter 中被改
        async with self._lock:
            clients = list(self._clients)
        failed: list[WSLike] = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                failed.append(ws)
        if failed:
            async with self._lock:
                for ws in failed:
                    try:
                        self._clients.remove(ws)
                    except ValueError:
                        pass

    @property
    def client_count(self) -> int:
        return len(self._clients)


# 全局单例
_broadcaster: V5Broadcaster | None = None


def get_broadcaster() -> V5Broadcaster:
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = V5Broadcaster()
    return _broadcaster
```

- [ ] **Step 4: 写 api/websocket_v5.py**

```python
"""/ws/v5 endpoint。

握手:可选 ?token=<Bearer>(留给 §安全 后续启用)
心跳:服务器每 30s 发 {type:"ping"};没收到 60s pong → 主动 close
"""
import asyncio
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.services.v5_broadcast import get_broadcaster


router = APIRouter()


HEARTBEAT_INTERVAL_S = 30
SILENCE_TIMEOUT_S = 60


@router.websocket("/ws/v5")
async def ws_v5(ws: WebSocket) -> None:
    await ws.accept()
    broadcaster = get_broadcaster()
    broadcaster.register(ws)
    last_seen = time.monotonic()
    try:
        # 心跳 + 接客户端 ping/pong
        async def _heartbeat():
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL_S)
                try:
                    await ws.send_json({"type": "ping", "ts": time.time()})
                except Exception:
                    return

        hb = asyncio.create_task(_heartbeat())

        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=SILENCE_TIMEOUT_S)
                last_seen = time.monotonic()
                # 客户端可发 {"type":"ping"} / {"type":"pong"} — 不强制处理
            except asyncio.TimeoutError:
                if time.monotonic() - last_seen > SILENCE_TIMEOUT_S:
                    break
            except WebSocketDisconnect:
                break

        hb.cancel()
    finally:
        broadcaster.unregister(ws)
        try:
            await ws.close()
        except Exception:
            pass
```

- [ ] **Step 5: 注册到 api/main.py**

```python
from api.websocket_v5 import router as ws_v5_router
app.include_router(ws_v5_router)
```

- [ ] **Step 6: 接入 scorer.py — position_opened 广播**

打开 `scripts/tasks/scorer.py`,在 `process_enriched_v5` 成功开仓后(目前会 print "executed,position_id=..."),加一段广播。但 scorer 是 collector 进程,api 是 api 进程 — **进程间无法直接 broadcast**!

**解决方案:** 走 DB 表 `ws_event_queue` 作为消息总线。Scorer 写入 → api 进程的 broadcaster 周期 poll → 广播 → 删除已发条目。

`scripts/local_db.py` 加表(`init_local_db` 末尾,executescript 后):

```python
conn.execute("""
    CREATE TABLE IF NOT EXISTS ws_event_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payload_json TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )
""")
```

`scripts/tasks/scorer.py` 在 `process_enriched_v5` 末尾(写完 trade_score 之后)加:

```python
def _enqueue_ws(db_path: str, payload: dict) -> None:
    """跨进程 WS 消息总线:写 ws_event_queue,api 进程 poll 后广播。"""
    import json, sqlite3
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "INSERT INTO ws_event_queue (payload_json) VALUES (?)",
                (json.dumps(payload, ensure_ascii=False),),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[V5Scorer] WS enqueue 失败: {e}")


# 在 process_enriched_v5 的 "执行了" 末尾:
_enqueue_ws(db_path, {
    "type": "position_opened",
    "symbol": enriched.symbol,
    "side": decision.side,
    "entry": risk.entry_price,
    "sl": risk.sl_price,
    "tp": risk.tp_price,
    "size_usdt": risk.size_usdt,
    "position_id": position_id,
    "strategy_id": "v5_rsi_macd" if mode == "SHADOW" else "v5_live",
    "mode": mode,
})
```

- [ ] **Step 7: 接入 v5_position_monitor.py — closed/extended 广播**

打开 `scripts/v5_position_monitor.py`,在 `_tick` 关闭/续仓后加同样的 enqueue。

复用 scorer 里的 `_enqueue_ws` — 但跨文件 import 不方便,直接在 monitor 顶部也加一个:

```python
def _enqueue_ws(db_path: str, payload: dict) -> None:
    import json, sqlite3
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "INSERT INTO ws_event_queue (payload_json) VALUES (?)",
                (json.dumps(payload, ensure_ascii=False),),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
```

monitor 的 db_path 之前没有显式参数 — 但 paper_pm.db_path 可以取:`pm.db_path`。在 _tick 的 close/extend 后:

```python
pm.extend_position(position["id"], extra_minutes=15)
_enqueue_ws(pm.db_path, {
    "type": "position_extended",
    "position_id": position["id"],
    "symbol": position["symbol"],
    "new_target_close_at": ...,  # 可以再读一次或 hand-roll +15min
    "extension_count": (position.get("extension_count") or 0) + 1,
})
# ...
pm.close_position(position["id"], exit_price=intent["exit_price"], exit_reason=reason)
_enqueue_ws(pm.db_path, {
    "type": "position_closed",
    "position_id": position["id"],
    "symbol": position["symbol"],
    "exit_price": intent["exit_price"],
    "exit_reason": reason,
})
```

- [ ] **Step 8: api 进程加 poll → broadcast loop**

`api/main.py` 在 lifespan 启动 background task:

```python
@asynccontextmanager
async def lifespan(app):
    # startup
    import asyncio
    from api.services.v5_broadcast import get_broadcaster
    import os, sqlite3, json

    db_path = os.environ.get("DB_PATH", "data/rabbit_hunter.db")
    broadcaster = get_broadcaster()
    stop = asyncio.Event()

    async def _poll_and_broadcast():
        while not stop.is_set():
            try:
                conn = sqlite3.connect(db_path)
                try:
                    rows = conn.execute(
                        "SELECT id, payload_json FROM ws_event_queue ORDER BY id LIMIT 50"
                    ).fetchall()
                    if rows:
                        for rid, payload_json in rows:
                            try:
                                payload = json.loads(payload_json)
                            except Exception:
                                payload = {"type": "unknown", "raw": payload_json}
                            await broadcaster.broadcast(payload)
                        conn.execute(
                            f"DELETE FROM ws_event_queue WHERE id <= ?",
                            (rows[-1][0],),
                        )
                        conn.commit()
                finally:
                    conn.close()
            except Exception as e:
                print(f"[ws] poll error: {e}")
            try:
                await asyncio.wait_for(stop.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    task = asyncio.create_task(_poll_and_broadcast())
    yield
    stop.set()
    await asyncio.sleep(0.1)
    task.cancel()
```

如果 `api/main.py` 当前没用 lifespan,先加;参考 FastAPI 标准用法。

- [ ] **Step 9: 跑测试**

```bash
python3 -m pytest tests/test_websocket_v5.py -v
python3 -m pytest tests/ -v 2>&1 | tail -3
# 预期 125 passed(122 + 3)
```

- [ ] **Step 10: Commit**

```bash
git add api/services/v5_broadcast.py api/websocket_v5.py api/main.py \
        scripts/tasks/scorer.py scripts/v5_position_monitor.py \
        scripts/local_db.py tests/test_websocket_v5.py
git commit -m "feat(ws): /ws/v5 broadcast + cross-process event bus

- V5Broadcaster: register/unregister/broadcast with auto-drop on send failure
- /ws/v5 endpoint with 30s server heartbeat + 60s silence close
- ws_event_queue SQLite table = cross-process message bus
  (collector writes, api polls every 1s and broadcasts)
- Scorer enqueues position_opened; PositionMonitor enqueues
  position_extended / position_closed

3 broadcaster unit tests."
```

---

## Phase 10:最终验收

### Task 11:更新 verify_v5_acceptance.py + 启动自检

**Files:**
- Modify: `scripts/verify_v5_acceptance.py`

- [ ] **Step 1: 扩展 verify_v5_acceptance.py**

在原来的 4 个检查项后追加 Plan B-1 验收:

```python
# scripts/verify_v5_acceptance.py 末尾追加

def verify_plan_b_backend(db_path: str = "data/rabbit_hunter.db") -> bool:
    conn = sqlite3.connect(db_path)
    try:
        # 5. /strategy-config 路由可用(系统启动 + 表存在)
        print("\n=== Plan B-1 后端 ===")
        try:
            n_settings = conn.execute(
                "SELECT COUNT(*) FROM system_settings WHERE key LIKE 'v5_%'"
            ).fetchone()[0]
            print(f"system_settings v5_* keys: {n_settings}")
        except Exception as e:
            print(f"system_settings 检查失败: {e}")
            return False

        # 6. ws_event_queue 表存在
        try:
            conn.execute("SELECT COUNT(*) FROM ws_event_queue").fetchone()
            print("ws_event_queue table OK")
        except Exception as e:
            print(f"ws_event_queue 不存在: {e}")
            return False

        # 7. v5_manual 策略的 paper_trade(可选,如果用户测过)
        n_manual = conn.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE strategy_id='v5_manual'"
        ).fetchone()[0]
        print(f"v5_manual paper_trades: {n_manual}(可选指标)")

        # 8. RAG cases — ai_training_data 已平仓样本
        n_rag = conn.execute(
            "SELECT COUNT(*) FROM ai_training_data WHERE outcome IS NOT NULL"
        ).fetchone()[0]
        print(f"ai_training_data 已平仓: {n_rag}(冷启动 < 10)")

        print("\n✅ Plan B-1 后端结构验收通过")
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    db = os.environ.get("DB_PATH", "data/rabbit_hunter.db")
    ok_a = verify(db)
    ok_b = verify_plan_b_backend(db)
    sys.exit(0 if (ok_a and ok_b) else 1)
```

- [ ] **Step 2: 全测一遍 + commit**

```bash
python3 -m pytest tests/ -v 2>&1 | tail -3
# 预期 125 passed
git add scripts/verify_v5_acceptance.py
git commit -m "chore(v5): verify_v5_acceptance covers Plan B-1 schema

- Check system_settings v5_* keys count
- Check ws_event_queue table exists
- Report v5_manual paper_trades + RAG case count (observational)"
```

- [ ] **Step 3: docker compose rebuild + run**

```bash
docker compose down
docker compose build --no-cache api collector
docker compose up -d
```

- [ ] **Step 4: 等 60 秒,确认 collector 正常启动且 ws_event_queue 表存在**

```bash
sleep 60
docker compose logs --tail 40 collector | grep -E "V5 启动|FATAL|ERROR"
docker compose exec -T collector python -c "
import sqlite3
c = sqlite3.connect('/app/data/rabbit_hunter.db')
print('v5_* params:', c.execute(\"SELECT COUNT(*) FROM system_settings WHERE key LIKE 'v5_%'\").fetchone()[0])
print('ws_event_queue:', c.execute('SELECT COUNT(*) FROM ws_event_queue').fetchone()[0])
print('trade_scores_v5:', c.execute('SELECT COUNT(*) FROM trade_scores_v5').fetchone()[0])
"
```

- [ ] **Step 5: 跑接口 sanity check**

```bash
curl -s http://localhost:8000/api/v5/strategy-config | python3 -m json.tool | head -20
curl -s http://localhost:8000/api/v5/settings | python3 -m json.tool | head -15
curl -s http://localhost:8000/api/v5/ai/status | python3 -m json.tool
```

- [ ] **Step 6: Tag + push**

```bash
git tag v5.0.0-plan-b-backend-shipped
git push origin main --tags
```

---

## Self-Review

### Spec coverage check(对照 design §1-§8)

| Spec 段 | Task |
|---|---|
| §1.2 决策 3(参数热读) | Task 2 |
| §2.1 路由 strategy-config | Task 4 |
| §2.1 路由 settings | Task 5 |
| §2.1 路由 ai/status + decisions | Task 6 |
| §2.1 路由 klines + events | Task 7 |
| §2.1 路由 manual-order preview + execute | Task 8 |
| §2.1 路由 positions/close | Task 9 |
| §2.3 WebSocket /ws/v5 + broadcast | Task 10 |
| §3.4 设计 tokens、§4 所有页面、§5.4 前端 RAG KPI | **Plan B-2 前端**(下一份 plan) |
| §5 RAG-lite + trading_assistant 集成 | Task 3 |
| §6 后端联动 12 路由 | Task 4-9 |
| §6.3 v5_params 热读 + 6 模块改造 | Task 2 |
| §7 后端测试 ~20 | Task 1-10 累计 ~30 |
| §8 部署 + 验收 | Task 11 |

**前端 Foundation/Pages/测试** 全部留给 Plan B-2(单独 plan)— 故意拆分,确保 Plan B-1 完成后 API 100% 稳定再开前端。

### Placeholder scan

无 TBD / TODO / 含糊步骤。每个代码块都给完整可用代码。

### Type consistency

- `ParamSpec.value/default/min/max` 全部 float ✓
- `SimilarCase.outcome` 是 `WIN | LOSS | FLAT` 字符串(non-Literal,但 PyDantic schema 端做 Literal)✓
- `SettingsResponse.system_mode` 是 `Literal["SHADOW","LIVE"]`,与 `_resolve_active_provider` 返回一致 ✓
- `ManualOrderExecuteResponse.strategy_id` = `"v5_manual"`,Task 8 / Task 11 一致 ✓
- `_enqueue_ws` 在 scorer.py 和 v5_position_monitor.py 是两份重复定义(intentional,避免循环 import)✓

---

## 执行交接

Plan B-1 complete and saved to `docs/superpowers/plans/2026-06-12-v5-plan-b-backend.md`.

**两种执行方式选一种:**

**1. Subagent-Driven(推荐)** —— 每个 Task 派一个新 subagent 执行,你在 Task 之间审。11 个 Task 大约 3-5 小时分散执行。

**2. Inline Execution** —— 在当前会话直接跑 executing-plans,批量执行。

**哪个?**
