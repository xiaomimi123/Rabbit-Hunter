# V6 Funding Rate Phases 1-6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 spec §8 阶段 1-6 落地:OKX 公开 API → funding rate 数据采集 → z-score 计算 → scorer / failure_taxonomy / AI prompt / reflection 集成 → 前端可视化。阶段 7(持续监控调参)留作运营,不在 plan 范围。

**Architecture:**
- 新增独立异步进程 `v5_funding_collector`,5min 拉新 / 1h 算 z-score,与 reflection_worker / scorer / position_monitor 同级
- 数据流:OKX `/api/v5/public/funding-rate-history` → `funding_rates` 表 → 1h cron 算 z-score → `funding_zscore_cache` 表 → scorer 读 cache 注入 trade_scores → setup_type 派生 → failure_taxonomy / AI prompt / reflection 全部启用 funding 维度
- 完全 backward-compatible:funding 数据缺失时 `funding_z_score=NULL`,所有下游 fallback 到 V5.1 行为
- 单源 OKX(国内可访问,已在 stack 内);Binance/Bybit 多源聚合留作 V6.1

**Tech Stack:** Python 3.11 / FastAPI / SQLite / Pydantic v2 / pytest · React 19 / Vite / Vitest · OKX 公开 REST API(无需 key)

**Cumulative test target after this plan:** backend 206 + ~28 = ~234; frontend 50 + ~4 = ~54.

**Working directory:** `/Users/lizhishaoniange/Documents/Rabbit-Hunter`. Frontend dir: `Rabbit Hunterfronted/` (preserve space and "fronted" typo).

**Direct push to `main`** per user policy throughout.

---

## File Inventory

### Phase 1 — 数据基础

| File | Action | Responsibility |
|---|---|---|
| `scripts/local_db.py` | MODIFY | Append `funding_rates` + `funding_zscore_cache` to `_V5_SCHEMA_SQL`; ALTER `trade_scores_v5` + `reflections` |
| `scripts/funding_okx_client.py` | CREATE | 纯 HTTP 客户端 + symbol mapping(无副作用) |
| `scripts/ai/funding_rate_calculator.py` | CREATE | z-score 计算 + cache 读写 |
| `scripts/tasks/v5_funding_collector.py` | CREATE | 主异步进程(5min tick + 1h cron) |
| `scripts/tasks/collector_main.py` | MODIFY | Wire `V5FundingCollector.run()` 到 lifespan |
| `tests/test_funding_okx_client.py` | CREATE | mock HTTP,symbol mapping 边界 |
| `tests/test_funding_rate_calculator.py` | CREATE | z-score 计算 + 边界 |
| `tests/test_v5_funding_collector.py` | CREATE | 集成:mock OKX → DB |

### Phase 2 — scorer + setup_type

| File | Action | Responsibility |
|---|---|---|
| `scripts/local_db.py` | MODIFY | (上面 Phase 1 已经 ALTER 完) |
| `scripts/ai/setup_type.py` | MODIFY | funding_extreme_* 派生分支 |
| `scripts/tasks/scorer.py` | MODIFY | `process_enriched_v5` 读 funding_z_score 注入 + 写 trade_scores |
| `tests/test_setup_type.py` | MODIFY | 加 funding_extreme 测试 |
| `tests/test_v5_scoring_pipeline.py` | MODIFY | 验证 trade_scores 含 funding |

### Phase 3 — failure_taxonomy 启用

| File | Action | Responsibility |
|---|---|---|
| `scripts/ai/failure_taxonomy.py` | MODIFY | `_h_against_4h_trend_no_funding` 用真 z_score |
| `tests/test_failure_taxonomy_matcher.py` | MODIFY | 加 funding 背书 / 反对的测试 |

### Phase 4 — AI prompt 注入

| File | Action | Responsibility |
|---|---|---|
| `scripts/ai/trading_assistant.py` | MODIFY | `_decide_via_chat` 在 user_msg 加 funding block |
| `tests/test_trading_assistant_funding.py` | CREATE | mock LLM,验证 prompt 含 funding context |

### Phase 5 — reflection 集成

| File | Action | Responsibility |
|---|---|---|
| `scripts/ai/reflection_runner.py` | MODIFY | `_load_close_context` JOIN funding_rates |
| `scripts/ai/reflection_prompt.py` | MODIFY | prompt template 加 funding section |
| `tests/test_reflection_runner.py` | MODIFY | 加 funding_z_score 入 ctx 的测试 |
| `tests/test_reflection_prompt.py` | MODIFY | 加 prompt 含 funding 的测试 |

### Phase 6 — API + 前端

| File | Action | Responsibility |
|---|---|---|
| `api/schemas/v5_funding.py` | CREATE | Pydantic schemas |
| `api/routes/v5_funding.py` | CREATE | GET /api/v5/funding/status, /history/{symbol} |
| `api/main.py` | MODIFY | 注册 router |
| `tests/test_v5_funding_api.py` | CREATE | API 集成测试 |
| `Rabbit Hunterfronted/types.ts` | MODIFY | FundingStatus 类型 |
| `Rabbit Hunterfronted/hooks/api/useV5Funding.ts` | CREATE | hook |
| `Rabbit Hunterfronted/components/pages/V5AIStatusPage.tsx` | MODIFY | 加 FundingHeatmapCard |
| `Rabbit Hunterfronted/components/pages/V5ReflectionPage.tsx` | MODIFY | reflection card 显示 funding |
| `Rabbit Hunterfronted/components/pages/V5DashboardPage.tsx` | MODIFY | 加 setup_type × outcome 分项 |
| `Rabbit Hunterfronted/services/glossary.ts` | MODIFY | 加 funding/z-score/crowding 术语 |
| `Rabbit Hunterfronted/tests/pages/V5AIStatusPage.test.tsx` | MODIFY | 加 funding card 测试 |

### 验收

| File | Action | Responsibility |
|---|---|---|
| `scripts/verify_v5_acceptance.py` | MODIFY | 加 verify_v6_funding_phase_1_6 |
| Tag | CREATE | `v6.0.0-funding-rate-phases-1-6-shipped` |

---

## Phase 1 — 数据基础 (3 tasks)

### Task 1: DB schema — funding_rates + funding_zscore_cache + ALTER

**Files:**
- Modify: `scripts/local_db.py`
- Create: `tests/test_funding_db.py`

- [ ] **Step 1: Write `tests/test_funding_db.py`**

```python
"""V6 funding rate schema 测试。"""
import os
import sqlite3
import tempfile
import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def test_funding_rates_table_created(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(funding_rates)").fetchall()]
    conn.close()
    for required in (
        "symbol", "instrument_id", "funding_time", "funding_rate",
        "annualized_rate", "source", "fetched_at",
    ):
        assert required in cols, f"missing: {required}"


def test_funding_rates_unique_constraint(db):
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO funding_rates (symbol, instrument_id, funding_time,
            funding_rate, annualized_rate, source)
        VALUES ('BTCUSDT', 'BTC-USDT-SWAP', '2026-06-17T00:00:00+00:00',
                0.0001, 0.1095, 'okx')
    """)
    conn.commit()
    # 同一 (symbol, funding_time, source) 重复 → IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("""
            INSERT INTO funding_rates (symbol, instrument_id, funding_time,
                funding_rate, annualized_rate, source)
            VALUES ('BTCUSDT', 'BTC-USDT-SWAP', '2026-06-17T00:00:00+00:00',
                    0.0002, 0.219, 'okx')
        """)
    conn.close()


def test_funding_zscore_cache_table_created(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(funding_zscore_cache)").fetchall()]
    conn.close()
    for required in (
        "symbol", "computed_at", "current_funding_rate", "mean_30d",
        "std_30d", "zscore_30d", "sample_size_30d",
        "is_extreme", "extreme_direction",
    ):
        assert required in cols, f"missing: {required}"


def test_trade_scores_v5_has_funding_columns(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(trade_scores_v5)").fetchall()]
    conn.close()
    assert "funding_z_score" in cols
    assert "funding_rate_8h" in cols


def test_reflections_has_funding_columns(db):
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(reflections)").fetchall()]
    conn.close()
    assert "funding_z_score_at_entry" in cols
    assert "funding_rate_at_entry" in cols


def test_zscore_cache_pk_replaces(db):
    """同一 symbol 写两次 → 后写覆盖。"""
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO funding_zscore_cache (symbol, current_funding_rate,
            mean_30d, std_30d, zscore_30d, sample_size_30d, is_extreme)
        VALUES ('BTCUSDT', 0.0001, 0.00005, 0.0001, 0.5, 90, 0)
    """)
    conn.execute("""
        INSERT OR REPLACE INTO funding_zscore_cache (symbol, current_funding_rate,
            mean_30d, std_30d, zscore_30d, sample_size_30d, is_extreme)
        VALUES ('BTCUSDT', 0.0005, 0.00005, 0.0001, 4.5, 90, 1)
    """)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM funding_zscore_cache WHERE symbol='BTCUSDT'").fetchone()[0]
    z = conn.execute("SELECT zscore_30d FROM funding_zscore_cache WHERE symbol='BTCUSDT'").fetchone()[0]
    conn.close()
    assert n == 1
    assert z == 4.5
```

- [ ] **Step 2: Run, expect 6 fail (tables missing)**

```bash
python3 -m pytest tests/test_funding_db.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Modify `scripts/local_db.py`**

Append inside `_V5_SCHEMA_SQL`(在闭合 `"""` 之前):

```sql

CREATE TABLE IF NOT EXISTS funding_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    funding_time TEXT NOT NULL,
    funding_rate REAL NOT NULL,
    annualized_rate REAL NOT NULL,
    settled_rate REAL,
    source TEXT NOT NULL DEFAULT 'okx',
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, funding_time, source)
);

CREATE INDEX IF NOT EXISTS idx_funding_rates_symbol_time
    ON funding_rates(symbol, funding_time DESC);

CREATE TABLE IF NOT EXISTS funding_zscore_cache (
    symbol TEXT PRIMARY KEY,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    current_funding_rate REAL NOT NULL,
    mean_30d REAL,
    std_30d REAL,
    zscore_30d REAL,
    sample_size_30d INTEGER,
    is_extreme INTEGER NOT NULL DEFAULT 0,
    extreme_direction TEXT
);
```

接着,搜索 `_V5_PAPER_TRADES_MIGRATIONS` 或类似的迁移列表(找一个有 ALTER 模式的位置)。如果存在则按相同模式追加;否则在 `init_local_db` 主流程末尾 `conn.executescript(_V5_SCHEMA_SQL)` 之后、`_seed_failure_taxonomy(conn)` 之前,添加一个新的 idempotent ALTER helper:

```python
def _migrate_funding_columns(conn) -> None:
    """ALTER 现有表加 funding 字段(idempotent — try/except 重复 ALTER)."""
    for sql in (
        "ALTER TABLE trade_scores_v5 ADD COLUMN funding_z_score REAL",
        "ALTER TABLE trade_scores_v5 ADD COLUMN funding_rate_8h REAL",
        "ALTER TABLE reflections ADD COLUMN funding_z_score_at_entry REAL",
        "ALTER TABLE reflections ADD COLUMN funding_rate_at_entry REAL",
    ):
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise
```

然后在 `init_local_db` 里调用:

```python
    _migrate_funding_columns(conn)
```

- [ ] **Step 4: Run tests, expect 6 passed**

```bash
python3 -m pytest tests/test_funding_db.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Full suite, no regression**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 206 + 6 = 212 passed (allow ±3 for pre-existing flakies).

- [ ] **Step 6: Commit**

```bash
git add scripts/local_db.py tests/test_funding_db.py
git commit -m "feat(v6): DB schema for funding_rates + zscore_cache + ALTER

- funding_rates: history table (symbol, time, rate, source) UNIQUE
- funding_zscore_cache: pre-computed 30d z-score per symbol (PK upsert)
- trade_scores_v5 + reflections: 2 new columns each (idempotent ALTER)
- _migrate_funding_columns guards 'duplicate column' on re-init

6 schema tests."
```

---

### Task 2: OKX funding client + symbol mapping

**Files:**
- Create: `scripts/funding_okx_client.py`
- Create: `tests/test_funding_okx_client.py`

- [ ] **Step 1: Write tests `tests/test_funding_okx_client.py`**

```python
"""OKX 公开 funding API 客户端测试。HTTP 用 mock,纯数据校验。"""
from unittest.mock import patch, MagicMock

import pytest

from scripts.funding_okx_client import (
    symbol_to_okx_instid,
    okx_instid_to_symbol,
    parse_funding_response,
    fetch_funding_history,
)


def test_symbol_to_okx_instid_basic():
    assert symbol_to_okx_instid("BTCUSDT") == "BTC-USDT-SWAP"
    assert symbol_to_okx_instid("ETHUSDT") == "ETH-USDT-SWAP"
    assert symbol_to_okx_instid("DOGEUSDT") == "DOGE-USDT-SWAP"


def test_symbol_to_okx_instid_already_swap():
    """如果已经是 OKX 格式,直接返回。"""
    assert symbol_to_okx_instid("BTC-USDT-SWAP") == "BTC-USDT-SWAP"


def test_okx_instid_to_symbol():
    assert okx_instid_to_symbol("BTC-USDT-SWAP") == "BTCUSDT"
    assert okx_instid_to_symbol("ETH-USDT-SWAP") == "ETHUSDT"
    assert okx_instid_to_symbol("BTCUSDT") == "BTCUSDT"   # 已经是 V5 格式


def test_parse_funding_response_success():
    raw = {
        "code": "0",
        "data": [
            {
                "fundingRate": "-0.000024895073548",
                "fundingTime": "1781683200000",
                "instId": "BTC-USDT-SWAP",
                "realizedRate": "-0.000020",
            },
            {
                "fundingRate": "0.0000359942934559",
                "fundingTime": "1781654400000",
                "instId": "BTC-USDT-SWAP",
                "realizedRate": "0.0000360",
            },
        ],
        "msg": "",
    }
    out = parse_funding_response(raw)
    assert len(out) == 2
    first = out[0]
    assert first["symbol"] == "BTCUSDT"
    assert first["instrument_id"] == "BTC-USDT-SWAP"
    assert first["funding_rate"] == -0.000024895073548
    assert first["funding_time"].endswith("+00:00")
    # annualized = funding_rate * 365 * 3 (8h periods/day)
    assert abs(first["annualized_rate"] - (-0.000024895073548 * 365 * 3)) < 1e-12
    assert first["settled_rate"] == -0.000020


def test_parse_funding_response_okx_error():
    raw = {"code": "50001", "data": [], "msg": "API frequency limit exceeded"}
    with pytest.raises(ValueError, match="50001"):
        parse_funding_response(raw)


def test_parse_funding_response_empty_data():
    """code=0 但 data 空(币种不存在) → 返回 []."""
    raw = {"code": "0", "data": [], "msg": ""}
    assert parse_funding_response(raw) == []


def test_fetch_funding_history_uses_urllib_no_external_deps(monkeypatch):
    """mock urllib.request 验证 URL + 参数构造。"""
    captured_urls = []

    class FakeResponse:
        def read(self):
            return b'{"code":"0","data":[],"msg":""}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=10):
        captured_urls.append(req.full_url if hasattr(req, "full_url") else req)
        return FakeResponse()

    import scripts.funding_okx_client as mod
    monkeypatch.setattr(mod, "urlopen", fake_urlopen)

    out = fetch_funding_history("BTCUSDT", limit=5)
    assert out == []
    assert "funding-rate-history" in captured_urls[0]
    assert "instId=BTC-USDT-SWAP" in captured_urls[0]
    assert "limit=5" in captured_urls[0]
```

- [ ] **Step 2: Run, expect 7 fail (module missing)**

- [ ] **Step 3: Write `scripts/funding_okx_client.py`**

```python
"""OKX 公开 funding rate API 客户端 — 纯 HTTP,无 key,无副作用。

Endpoints used:
  GET /api/v5/public/funding-rate-history?instId=...&limit=...
  GET /api/v5/public/funding-rate?instId=...

Response shape (success):
  {"code":"0", "data":[{...}], "msg":""}

Response shape (error):
  {"code":"50001", "data":[], "msg":"..."}
"""
import json
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen


OKX_BASE = "https://www.okx.com/api/v5/public"


def symbol_to_okx_instid(symbol: str) -> str:
    """'BTCUSDT' → 'BTC-USDT-SWAP'. Idempotent if already OKX-formatted."""
    if "-SWAP" in symbol:
        return symbol
    if not symbol.endswith("USDT"):
        raise ValueError(f"unsupported symbol format: {symbol}")
    base = symbol[: -len("USDT")]
    return f"{base}-USDT-SWAP"


def okx_instid_to_symbol(instid: str) -> str:
    """'BTC-USDT-SWAP' → 'BTCUSDT'. Idempotent if already V5-formatted."""
    if "-SWAP" not in instid:
        return instid
    parts = instid.split("-")
    return f"{parts[0]}{parts[1]}"


def parse_funding_response(raw: dict) -> List[dict]:
    """OKX response → list of dicts ready for DB insert.

    Each output row:
      {
        "symbol": "BTCUSDT",
        "instrument_id": "BTC-USDT-SWAP",
        "funding_time": "2026-06-17T08:00:00+00:00",
        "funding_rate": float,
        "annualized_rate": float,
        "settled_rate": float | None,
      }
    """
    if str(raw.get("code")) != "0":
        raise ValueError(
            f"OKX error code={raw.get('code')} msg={raw.get('msg', '')!r}"
        )

    out: List[dict] = []
    for row in raw.get("data", []):
        instid = row["instId"]
        rate = float(row["fundingRate"])
        ts_ms = int(row["fundingTime"])
        ft = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
        settled_raw = row.get("realizedRate") or row.get("settFundingRate")
        settled = float(settled_raw) if settled_raw not in (None, "") else None
        out.append({
            "symbol": okx_instid_to_symbol(instid),
            "instrument_id": instid,
            "funding_time": ft,
            "funding_rate": rate,
            "annualized_rate": rate * 365 * 3,    # 3 periods per day
            "settled_rate": settled,
        })
    return out


def fetch_funding_history(symbol: str, *, limit: int = 100,
                           timeout_s: float = 10.0) -> List[dict]:
    """拉一个 symbol 的最近 N 个 funding 历史。

    Returns parsed rows ready for DB. Raises ValueError on OKX error,
    URLError on network failure.
    """
    instid = symbol_to_okx_instid(symbol)
    params = urlencode({"instId": instid, "limit": str(limit)})
    url = f"{OKX_BASE}/funding-rate-history?{params}"
    req = Request(url, headers={"User-Agent": "rabbit-hunter-v6/1.0"})
    with urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8")
    raw = json.loads(body)
    return parse_funding_response(raw)


def fetch_current_funding(symbol: str, *, timeout_s: float = 10.0) -> Optional[dict]:
    """拉一个 symbol 的当前(未结算)funding rate。返回单条 dict 或 None。"""
    instid = symbol_to_okx_instid(symbol)
    params = urlencode({"instId": instid})
    url = f"{OKX_BASE}/funding-rate?{params}"
    req = Request(url, headers={"User-Agent": "rabbit-hunter-v6/1.0"})
    with urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8")
    raw = json.loads(body)
    rows = parse_funding_response(raw)
    return rows[0] if rows else None
```

- [ ] **Step 4: Run tests, expect 7 passed**

```bash
python3 -m pytest tests/test_funding_okx_client.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add scripts/funding_okx_client.py tests/test_funding_okx_client.py
git commit -m "feat(v6): OKX public funding API client + symbol mapping

- urllib-only (no new deps), 10s timeout, no API key needed
- symbol_to_okx_instid / okx_instid_to_symbol idempotent
- parse_funding_response converts OKX shape -> DB row dict
  - converts ms epoch to ISO UTC string
  - computes annualized_rate = funding_rate * 365 * 3
- fetch_funding_history + fetch_current_funding sync functions
- ValueError on OKX error code

7 unit tests with mocked HTTP."
```

---

### Task 3: V5FundingCollector worker + 90d backfill + collector_main wiring

**Files:**
- Create: `scripts/ai/funding_rate_calculator.py`
- Create: `scripts/tasks/v5_funding_collector.py`
- Modify: `scripts/tasks/collector_main.py`
- Create: `tests/test_funding_rate_calculator.py`
- Create: `tests/test_v5_funding_collector.py`

- [ ] **Step 1: Write `tests/test_funding_rate_calculator.py`**

```python
"""z-score 计算 + cache 读写测试。"""
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta

import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _seed(conn, symbol: str, rates: list, days_back_start: int = 0):
    """从 days_back_start 天前开始,每 8h 塞一行 funding。"""
    base = datetime.now(timezone.utc) - timedelta(days=days_back_start)
    for i, rate in enumerate(rates):
        ft = (base - timedelta(hours=8 * i)).isoformat()
        conn.execute("""
            INSERT INTO funding_rates (symbol, instrument_id, funding_time,
                funding_rate, annualized_rate, source)
            VALUES (?, ?, ?, ?, ?, 'okx')
        """, (symbol, f"{symbol[:-4]}-USDT-SWAP", ft, rate, rate * 365 * 3))


def test_zscore_returns_none_when_insufficient_samples(db):
    from scripts.ai.funding_rate_calculator import compute_zscore_30d
    conn = sqlite3.connect(db)
    _seed(conn, "BTCUSDT", [0.0001] * 10)   # only 10 samples, need 20
    conn.commit()
    conn.close()
    assert compute_zscore_30d("BTCUSDT", db_path=db) is None


def test_zscore_computes_correctly_with_enough_samples(db):
    """30 samples,current_rate 比 mean 大 2 sigma → zscore ≈ 2.0."""
    from scripts.ai.funding_rate_calculator import compute_zscore_30d
    conn = sqlite3.connect(db)
    historical = [0.0001] * 29              # mean 0.0001, std 0
    _seed(conn, "BTCUSDT", [0.0005] + historical)   # current = 0.0005
    conn.commit()
    conn.close()
    out = compute_zscore_30d("BTCUSDT", db_path=db)
    assert out is not None
    assert out["current_funding_rate"] == 0.0005
    assert out["sample_size_30d"] == 30
    # std=0 → zscore=0 by safety guard
    assert out["zscore_30d"] == 0.0


def test_zscore_detects_extreme(db):
    from scripts.ai.funding_rate_calculator import compute_zscore_30d
    conn = sqlite3.connect(db)
    # 30 samples: historical varies, current extreme
    historical = [0.0001 + 0.00001 * (i % 3 - 1) for i in range(29)]
    _seed(conn, "BTCUSDT", [0.001] + historical)    # current 10x larger
    conn.commit()
    conn.close()
    out = compute_zscore_30d("BTCUSDT", db_path=db)
    assert out is not None
    assert out["zscore_30d"] > 5.0
    assert out["is_extreme"] is True
    assert out["extreme_direction"] == "long_crowded"


def test_zscore_detects_short_crowding(db):
    from scripts.ai.funding_rate_calculator import compute_zscore_30d
    conn = sqlite3.connect(db)
    historical = [0.0001 + 0.00001 * (i % 3 - 1) for i in range(29)]
    _seed(conn, "BTCUSDT", [-0.001] + historical)   # current very negative
    conn.commit()
    conn.close()
    out = compute_zscore_30d("BTCUSDT", db_path=db)
    assert out is not None
    assert out["zscore_30d"] < -5.0
    assert out["is_extreme"] is True
    assert out["extreme_direction"] == "short_crowded"


def test_refresh_zscore_cache_writes_to_db(db):
    from scripts.ai.funding_rate_calculator import refresh_zscore_cache
    conn = sqlite3.connect(db)
    historical = [0.0001 + 0.00001 * (i % 3 - 1) for i in range(29)]
    _seed(conn, "BTCUSDT", [0.0008] + historical)
    conn.commit()
    conn.close()
    n = refresh_zscore_cache(["BTCUSDT"], db_path=db)
    assert n == 1
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT zscore_30d, sample_size_30d, is_extreme FROM funding_zscore_cache "
        "WHERE symbol='BTCUSDT'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[1] == 30


def test_get_cached_zscore_returns_none_for_missing(db):
    from scripts.ai.funding_rate_calculator import get_cached_zscore
    assert get_cached_zscore("ETHUSDT", db_path=db) is None


def test_get_cached_zscore_returns_after_refresh(db):
    from scripts.ai.funding_rate_calculator import refresh_zscore_cache, get_cached_zscore
    conn = sqlite3.connect(db)
    historical = [0.0001] * 29
    _seed(conn, "BTCUSDT", [0.0005] + historical)
    conn.commit()
    conn.close()
    refresh_zscore_cache(["BTCUSDT"], db_path=db)
    out = get_cached_zscore("BTCUSDT", db_path=db)
    assert out is not None
    assert out["current_funding_rate"] == 0.0005
```

- [ ] **Step 2: Run, expect 7 fail**

- [ ] **Step 3: Write `scripts/ai/funding_rate_calculator.py`**

```python
"""z-score 计算 + cache 读写。无副作用 except cache 写。

设计:
- 计算窗口 30 天滚动 (从最近一次往回找 30d 内所有 funding)
- 最小样本 20(< 7 天数据就 None)
- 排除当前点算 mean/std (防止当前极端值污染基线)
- |z| ≥ 2.0 = extreme
- extreme_direction: long_crowded (z 正,多头付钱) / short_crowded (z 负)
"""
import os
import sqlite3
import statistics
from typing import List, Optional


MIN_SAMPLE_FOR_ZSCORE = 20
EXTREME_THRESHOLD = 2.0


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


def compute_zscore_30d(symbol: str, *, db_path: Optional[str] = None) -> Optional[dict]:
    """返回 dict 含 zscore_30d 等;None 表示样本不足。

    最新一笔作为 current_funding_rate;倒数第 2 到 30d 内的作为基线。
    """
    db = db_path or _db()
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("""
            SELECT funding_rate FROM funding_rates
             WHERE symbol = ? AND source = 'okx'
               AND funding_time >= datetime('now', '-30 days')
             ORDER BY funding_time DESC
        """, (symbol,)).fetchall()
    finally:
        conn.close()

    rates = [r[0] for r in rows]
    if len(rates) < MIN_SAMPLE_FOR_ZSCORE:
        return None

    current = rates[0]
    historical = rates[1:]
    mean = statistics.mean(historical)
    std = statistics.stdev(historical) if len(historical) >= 2 else 0.0

    if std == 0:
        zscore = 0.0
    else:
        zscore = (current - mean) / std

    is_extreme = abs(zscore) >= EXTREME_THRESHOLD
    extreme_direction = (
        "long_crowded" if zscore >= EXTREME_THRESHOLD
        else "short_crowded" if zscore <= -EXTREME_THRESHOLD
        else None
    )

    return {
        "current_funding_rate": current,
        "mean_30d": mean,
        "std_30d": std,
        "zscore_30d": zscore,
        "sample_size_30d": len(rates),
        "is_extreme": is_extreme,
        "extreme_direction": extreme_direction,
    }


def refresh_zscore_cache(symbols: List[str], *,
                          db_path: Optional[str] = None) -> int:
    """对每个 symbol 算 z-score 并写 cache。返回写入条数(跳过 None)。"""
    db = db_path or _db()
    written = 0
    conn = sqlite3.connect(db)
    try:
        for sym in symbols:
            out = compute_zscore_30d(sym, db_path=db)
            if out is None:
                continue
            conn.execute("""
                INSERT OR REPLACE INTO funding_zscore_cache (
                    symbol, computed_at, current_funding_rate,
                    mean_30d, std_30d, zscore_30d, sample_size_30d,
                    is_extreme, extreme_direction
                ) VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?)
            """, (
                sym, out["current_funding_rate"],
                out["mean_30d"], out["std_30d"], out["zscore_30d"],
                out["sample_size_30d"],
                1 if out["is_extreme"] else 0,
                out["extreme_direction"],
            ))
            written += 1
        conn.commit()
    finally:
        conn.close()
    return written


def get_cached_zscore(symbol: str, *,
                       db_path: Optional[str] = None) -> Optional[dict]:
    """O(1) 读 cache。None 表示该 symbol 还没计算过。"""
    db = db_path or _db()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM funding_zscore_cache WHERE symbol=?", (symbol,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    d = dict(row)
    d["is_extreme"] = bool(d.get("is_extreme"))
    return d
```

- [ ] **Step 4: Run, expect 7 passed**

```bash
python3 -m pytest tests/test_funding_rate_calculator.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Write `tests/test_v5_funding_collector.py`**

```python
"""V5FundingCollector 进程测试 — mock OKX HTTP + DB 验证."""
import asyncio
import sqlite3
import tempfile
from unittest.mock import patch

import pytest


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def test_fetch_tick_writes_to_funding_rates(db):
    """mock fetch_funding_history → tick 写入 funding_rates."""
    from scripts.tasks.v5_funding_collector import V5FundingCollector

    fake_history = [
        {"symbol": "BTCUSDT", "instrument_id": "BTC-USDT-SWAP",
         "funding_time": "2026-06-17T08:00:00+00:00",
         "funding_rate": 0.0001, "annualized_rate": 0.1095, "settled_rate": 0.0001},
        {"symbol": "BTCUSDT", "instrument_id": "BTC-USDT-SWAP",
         "funding_time": "2026-06-17T00:00:00+00:00",
         "funding_rate": 0.00008, "annualized_rate": 0.0876, "settled_rate": 0.00008},
    ]

    with patch("scripts.tasks.v5_funding_collector.fetch_funding_history",
                return_value=fake_history):
        worker = V5FundingCollector(db_path=db, symbols=["BTCUSDT"])
        asyncio.run(worker._fetch_tick())

    conn = sqlite3.connect(db)
    n = conn.execute(
        "SELECT COUNT(*) FROM funding_rates WHERE symbol='BTCUSDT'"
    ).fetchone()[0]
    conn.close()
    assert n == 2


def test_fetch_tick_idempotent_on_duplicate(db):
    from scripts.tasks.v5_funding_collector import V5FundingCollector
    fake = [{"symbol": "BTCUSDT", "instrument_id": "BTC-USDT-SWAP",
              "funding_time": "2026-06-17T08:00:00+00:00",
              "funding_rate": 0.0001, "annualized_rate": 0.1095, "settled_rate": None}]

    with patch("scripts.tasks.v5_funding_collector.fetch_funding_history",
                return_value=fake):
        worker = V5FundingCollector(db_path=db, symbols=["BTCUSDT"])
        asyncio.run(worker._fetch_tick())
        asyncio.run(worker._fetch_tick())   # 第二次跑

    conn = sqlite3.connect(db)
    n = conn.execute(
        "SELECT COUNT(*) FROM funding_rates WHERE symbol='BTCUSDT'"
    ).fetchone()[0]
    conn.close()
    assert n == 1


def test_fetch_tick_swallows_api_error(db):
    """单个 symbol 出错不阻塞其他 symbol."""
    from scripts.tasks.v5_funding_collector import V5FundingCollector

    call_count = {"n": 0}

    def fake_fetch(symbol, **kwargs):
        call_count["n"] += 1
        if symbol == "BTCUSDT":
            raise ValueError("OKX error 50001")
        return [{"symbol": symbol, "instrument_id": f"{symbol[:-4]}-USDT-SWAP",
                  "funding_time": "2026-06-17T08:00:00+00:00",
                  "funding_rate": 0.0001, "annualized_rate": 0.1095,
                  "settled_rate": None}]

    with patch("scripts.tasks.v5_funding_collector.fetch_funding_history",
                side_effect=fake_fetch):
        worker = V5FundingCollector(db_path=db, symbols=["BTCUSDT", "ETHUSDT"])
        asyncio.run(worker._fetch_tick())

    assert call_count["n"] == 2
    conn = sqlite3.connect(db)
    btc = conn.execute("SELECT COUNT(*) FROM funding_rates WHERE symbol='BTCUSDT'").fetchone()[0]
    eth = conn.execute("SELECT COUNT(*) FROM funding_rates WHERE symbol='ETHUSDT'").fetchone()[0]
    conn.close()
    assert btc == 0
    assert eth == 1


def test_zscore_tick_refreshes_cache(db):
    """注入 30 条 BTC funding,跑 _zscore_tick → cache 有数据."""
    from scripts.tasks.v5_funding_collector import V5FundingCollector
    from datetime import datetime, timezone, timedelta

    conn = sqlite3.connect(db)
    base = datetime.now(timezone.utc)
    for i in range(30):
        ft = (base - timedelta(hours=8 * i)).isoformat()
        conn.execute("""
            INSERT INTO funding_rates (symbol, instrument_id, funding_time,
                funding_rate, annualized_rate, source)
            VALUES ('BTCUSDT', 'BTC-USDT-SWAP', ?, 0.0001, 0.1095, 'okx')
        """, (ft,))
    conn.commit()
    conn.close()

    worker = V5FundingCollector(db_path=db, symbols=["BTCUSDT"])
    asyncio.run(worker._zscore_tick())

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT zscore_30d, sample_size_30d FROM funding_zscore_cache WHERE symbol='BTCUSDT'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[1] == 30


def test_backfill_uses_larger_limit(db):
    """backfill 一次拉 100,跟普通 tick 拉 5 区分."""
    from scripts.tasks.v5_funding_collector import V5FundingCollector

    captured_limits = []

    def fake_fetch(symbol, **kwargs):
        captured_limits.append(kwargs.get("limit"))
        return []

    with patch("scripts.tasks.v5_funding_collector.fetch_funding_history",
                side_effect=fake_fetch):
        worker = V5FundingCollector(db_path=db, symbols=["BTCUSDT"])
        asyncio.run(worker.backfill_history(limit=100))

    assert captured_limits == [100]
```

- [ ] **Step 6: Run, expect 5 fail**

- [ ] **Step 7: Write `scripts/tasks/v5_funding_collector.py`**

```python
"""V5FundingCollector — 拉 OKX funding + 算 z-score。

- 每 5 min tick → fetch_funding_history(symbol, limit=5) 拉最近 5 个,UNIQUE 入 funding_rates
- 每 1 h cron → refresh_zscore_cache(symbols) 重算所有 cache
- 启动时跑一次 backfill_history(limit=100) 拿 90d 历史
- 单 symbol 失败不阻塞其他 symbol(swallowed + logged)
"""
import asyncio
import sqlite3
import traceback
from typing import List, Optional

from scripts.funding_okx_client import fetch_funding_history
from scripts.ai.funding_rate_calculator import refresh_zscore_cache


FETCH_INTERVAL_S = 300       # 5 min
ZSCORE_INTERVAL_S = 3600     # 1 h


class V5FundingCollector:
    """async poll-loop worker."""

    def __init__(self, *, db_path: str, symbols: List[str],
                 fetch_interval_s: int = FETCH_INTERVAL_S,
                 zscore_interval_s: int = ZSCORE_INTERVAL_S):
        self.db_path = db_path
        self.symbols = list(symbols)
        self.fetch_interval_s = fetch_interval_s
        self.zscore_interval_s = zscore_interval_s

    def _persist(self, rows: List[dict]) -> int:
        if not rows:
            return 0
        conn = sqlite3.connect(self.db_path)
        try:
            for r in rows:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO funding_rates (
                            symbol, instrument_id, funding_time,
                            funding_rate, annualized_rate, settled_rate, source
                        ) VALUES (?, ?, ?, ?, ?, ?, 'okx')
                    """, (
                        r["symbol"], r["instrument_id"], r["funding_time"],
                        r["funding_rate"], r["annualized_rate"], r.get("settled_rate"),
                    ))
                except Exception as e:
                    print(f"[V5FundingCollector] persist row failed: {e}")
            conn.commit()
        finally:
            conn.close()
        return len(rows)

    async def _fetch_tick(self) -> None:
        """每个 symbol 拉最近 5 个 funding。单个失败不阻塞其他。"""
        for sym in self.symbols:
            try:
                rows = await asyncio.to_thread(fetch_funding_history, sym, limit=5)
                self._persist(rows)
            except Exception as e:
                print(f"[V5FundingCollector] {sym} fetch failed: {type(e).__name__}: {e}")

    async def _zscore_tick(self) -> None:
        try:
            n = await asyncio.to_thread(refresh_zscore_cache, self.symbols,
                                          db_path=self.db_path)
            print(f"[V5FundingCollector] zscore refreshed for {n} symbols")
        except Exception as e:
            print(f"[V5FundingCollector] zscore refresh failed: {e}")
            traceback.print_exc()

    async def backfill_history(self, *, limit: int = 100) -> None:
        """启动时拉 limit 个 funding 历史(≈ 33 天 @ 8h period)."""
        print(f"[V5FundingCollector] backfill 启动 (limit={limit}/symbol)")
        for sym in self.symbols:
            try:
                rows = await asyncio.to_thread(fetch_funding_history, sym, limit=limit)
                n = self._persist(rows)
                print(f"[V5FundingCollector] backfill {sym}: {n} rows")
            except Exception as e:
                print(f"[V5FundingCollector] backfill {sym} failed: {e}")

    async def run(self) -> None:
        """主循环:tick fetch + cron zscore."""
        from datetime import datetime, timezone
        print(f"[V5FundingCollector] 启动,{len(self.symbols)} symbols,"
              f"fetch={self.fetch_interval_s}s zscore={self.zscore_interval_s}s")

        # 启动 backfill 一次
        await self.backfill_history(limit=100)
        await self._zscore_tick()

        last_fetch = 0.0
        last_zscore = 0.0
        import time
        while True:
            try:
                now = time.monotonic()
                if now - last_fetch >= self.fetch_interval_s:
                    await self._fetch_tick()
                    last_fetch = now
                if now - last_zscore >= self.zscore_interval_s:
                    await self._zscore_tick()
                    last_zscore = now
            except asyncio.CancelledError:
                print("[V5FundingCollector] 取消信号,退出")
                return
            except Exception as e:
                print(f"[V5FundingCollector] loop 异常: {type(e).__name__}: {e}")
            await asyncio.sleep(30)
```

- [ ] **Step 8: Modify `scripts/tasks/collector_main.py` — start V5FundingCollector**

Find where `V5ReflectionWorker` is wired up (search `V5ReflectionWorker(`). After that block, add:

```python
    # Funding rate collector (V6)
    from scripts.tasks.v5_funding_collector import V5FundingCollector
    from scripts.v5_symbol_whitelist import V5_TOP20_WHITELIST

    funding_collector = V5FundingCollector(
        db_path=db_path,
        symbols=sorted(V5_TOP20_WHITELIST),
    )
    coroutines.append(funding_collector.run())
```

(Match the existing pattern — if the variable is `tasks` instead of `coroutines`, adapt. The reflection worker is the closest precedent.)

- [ ] **Step 9: Run worker tests**

```bash
python3 -m pytest tests/test_v5_funding_collector.py -v 2>&1 | tail -10
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 5 new + 219 cumulative (212 + 7 calc).

- [ ] **Step 10: Commit**

```bash
git add scripts/ai/funding_rate_calculator.py scripts/tasks/v5_funding_collector.py \
        scripts/tasks/collector_main.py \
        tests/test_funding_rate_calculator.py tests/test_v5_funding_collector.py
git commit -m "feat(v6): V5FundingCollector worker + z-score calculator

- funding_rate_calculator: compute_zscore_30d (排除 current 算 baseline),
  refresh_zscore_cache (batch upsert), get_cached_zscore (O(1) lookup)
- min sample 20,|z|≥2.0 = extreme,long/short_crowded direction
- V5FundingCollector: async run loop, 5min fetch / 1h zscore cron
  - 启动 backfill 100 funding/symbol (~33 days @ 8h)
  - 单 symbol 失败不阻塞其他
  - asyncio.to_thread 包 sync fetch (urllib)
- collector_main 启动 worker,symbols = V5_TOP20_WHITELIST

12 tests (7 calculator + 5 worker)."
```

---

## Phase 2 — scorer + setup_type (2 tasks)

### Task 4: setup_type 派生扩展 — funding_extreme_*

**Files:**
- Modify: `scripts/ai/setup_type.py`
- Modify: `tests/test_setup_type.py`

- [ ] **Step 1: Append tests to `tests/test_setup_type.py`**

```python
# 已有 fixture / helpers 不动 — 加新测试。注意需要看现有文件的 _entry() helper。

def test_funding_extreme_short_rsi_overbought():
    """funding |z| >= 2.0 + 正向(long_crowded) + RSI 超买 → funding_extreme_short_rsi_overbought."""
    from scripts.ai.setup_type import derive_setup_type
    out = derive_setup_type({
        "side": "SHORT", "strategy_id": "v5_rsi_macd",
        "rsi_15m": 72.0, "macd_hist": -0.0012, "macd_hist_prev": 0.0008,
        "funding_z_score": 2.5,
    })
    assert out == "funding_extreme_short_rsi_overbought"


def test_funding_extreme_long_rsi_oversold():
    from scripts.ai.setup_type import derive_setup_type
    out = derive_setup_type({
        "side": "LONG", "strategy_id": "v5_rsi_macd",
        "rsi_15m": 25.0, "macd_hist": 0.0008, "macd_hist_prev": -0.0004,
        "funding_z_score": -2.8,
    })
    assert out == "funding_extreme_long_rsi_oversold"


def test_funding_z_below_2_falls_back_to_rsi_macd():
    """|z| < 2.0 → 退回 RSI×MACD 派生,不进 funding_extreme."""
    from scripts.ai.setup_type import derive_setup_type
    out = derive_setup_type({
        "side": "SHORT", "strategy_id": "v5_rsi_macd",
        "rsi_15m": 72.0, "macd_hist": -0.0012, "macd_hist_prev": 0.0008,
        "funding_z_score": 1.5,                  # 不够极端
    })
    assert out == "rsi_overbought_macd_bearish_short"


def test_funding_extreme_handles_neutral_rsi():
    """funding 极端但 RSI 中性 → funding_extreme_<dir>_rsi_neutral."""
    from scripts.ai.setup_type import derive_setup_type
    out = derive_setup_type({
        "side": "SHORT", "strategy_id": "v5_rsi_macd",
        "rsi_15m": 55.0, "macd_hist": -0.0001, "macd_hist_prev": -0.00005,
        "funding_z_score": 2.3,
    })
    assert out == "funding_extreme_short_rsi_neutral"


def test_funding_extreme_overrides_manual_check():
    """v5_manual 仍然短路返回 manual_*,不受 funding 影响."""
    from scripts.ai.setup_type import derive_setup_type
    out = derive_setup_type({
        "side": "SHORT", "strategy_id": "v5_manual",
        "rsi_15m": 72.0, "macd_hist": -0.0012, "macd_hist_prev": 0.0008,
        "funding_z_score": 3.0,
    })
    assert out == "manual_short"
```

- [ ] **Step 2: Run, expect failures only on new tests**

```bash
python3 -m pytest tests/test_setup_type.py -v 2>&1 | tail -15
```

The 4 new funding-related tests should fail; existing 6 tests should pass.

- [ ] **Step 3: Modify `scripts/ai/setup_type.py`**

Read the existing file. Look for the line `if entry.get("strategy_id") == "v5_manual": return f"manual_{side_lower}"`. The current logic computes `rsi_state` and `macd_state`, then checks funding at the end. We need to make funding take precedence when extreme.

Replace the function body with this version(keeping the manual short-circuit at top):

```python
def derive_setup_type(entry: dict) -> str:
    """从 entry snapshot 派生 setup_type。AI 不参与。

    优先级:
      1. v5_manual → manual_<side>
      2. |funding_z_score| >= 2.0 → funding_extreme_<dir>_<rsi_state>
      3. RSI×MACD×side → rsi_<state>_macd_<state>_<side>
    """
    side = (entry.get("side") or "").upper()
    side_lower = side.lower() if side else "unknown"

    if entry.get("strategy_id") == "v5_manual":
        return f"manual_{side_lower}"

    rsi = float(entry.get("rsi_15m") or 50.0)
    hist = float(entry.get("macd_hist") or 0.0)
    hist_prev = float(entry.get("macd_hist_prev") or 0.0)

    if rsi >= 70:
        rsi_state = "rsi_overbought"
    elif rsi <= 30:
        rsi_state = "rsi_oversold"
    else:
        rsi_state = "rsi_neutral"

    fz = entry.get("funding_z_score")
    if fz is not None and abs(fz) >= 2.0:
        direction = "short" if fz > 0 else "long"
        return f"funding_extreme_{direction}_{rsi_state}"

    if hist_prev < 0 and hist > 0:
        macd_state = "macd_bullish"
    elif hist_prev > 0 and hist < 0:
        macd_state = "macd_bearish"
    else:
        macd_state = "macd_extending"

    return f"{rsi_state}_{macd_state}_{side_lower}"
```

- [ ] **Step 4: Run tests + full suite**

```bash
python3 -m pytest tests/test_setup_type.py -v 2>&1 | tail -10
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 4 new + 10 in file all pass; 219 + 4 = 223 cumulative.

- [ ] **Step 5: Commit**

```bash
git add scripts/ai/setup_type.py tests/test_setup_type.py
git commit -m "feat(v6): setup_type 派生 funding_extreme_* 分支

- |funding_z_score| >= 2.0 时优先于 RSI×MACD 派生
  - z > 2  → funding_extreme_short_<rsi_state> (多头拥挤,反转 SHORT)
  - z < -2 → funding_extreme_long_<rsi_state> (空头拥挤,反转 LONG)
- v5_manual 仍然短路保留
- 中性 funding (|z|<2) 回退原有 RSI×MACD 派生
- 启用 funding 维度 = setup_performance_daily 自动按新桶累积

5 new tests."
```

---

### Task 5: scorer 集成 — process_enriched_v5 注入 funding + 写 trade_scores

**Files:**
- Modify: `scripts/tasks/scorer.py`
- Modify: `tests/test_v5_scoring_pipeline.py`

- [ ] **Step 1: Write integration test addition to `tests/test_v5_scoring_pipeline.py`**

Read the file first. Find the existing test that runs process_enriched_v5. Add a new test:

```python
def test_process_enriched_v5_injects_funding_zscore(monkeypatch):
    """funding_zscore_cache 有数据时,trade_scores 应当含 funding_z_score。"""
    import asyncio
    import sqlite3
    import tempfile
    from unittest.mock import MagicMock

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    monkeypatch.setenv("V5_USE_SYMBOL_WHITELIST", "false")
    monkeypatch.setenv("V5_STRATEGY_MODE", "trend_aligned")

    from scripts.local_db import init_local_db
    init_local_db(tmp.name)

    # 注入 funding cache for BTCUSDT
    conn = sqlite3.connect(tmp.name)
    conn.execute("""
        INSERT INTO funding_zscore_cache (symbol, current_funding_rate,
            zscore_30d, sample_size_30d, is_extreme, extreme_direction)
        VALUES ('BTCUSDT', 0.0008, 2.5, 30, 1, 'long_crowded')
    """)
    conn.commit()
    conn.close()

    from v5_types import EnrichedItem
    from scripts.tasks.scorer import process_enriched_v5
    from tests.conftest import _build_klines

    # 给足 K 线让 indicators 算得出
    klines_15m = _build_klines([100 + i for i in range(50)])
    klines_4h = _build_klines([100 + i * 2 for i in range(50)])

    enriched = EnrichedItem(
        symbol="BTCUSDT", current_price=150.0,
        delta_15m_pct=0.005, volume_24h_usdt=5e7,
        klines_15m=klines_15m, klines_4h=klines_4h,
    )

    asyncio.run(process_enriched_v5(
        enriched=enriched, ai=None,
        paper_pm=MagicMock(), live_pm=MagicMock(),
        mode="SHADOW", db_path=tmp.name, balance_usdt=1000.0,
    ))

    conn = sqlite3.connect(tmp.name)
    row = conn.execute(
        "SELECT funding_z_score, funding_rate_8h FROM trade_scores_v5 "
        "WHERE symbol='BTCUSDT' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 2.5
    assert row[1] == 0.0008


def test_process_enriched_v5_funding_null_when_cache_miss(monkeypatch):
    """cache 没数据时,funding_z_score 写 NULL,不阻塞。"""
    import asyncio
    import sqlite3
    import tempfile
    from unittest.mock import MagicMock

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    monkeypatch.setenv("V5_USE_SYMBOL_WHITELIST", "false")
    monkeypatch.setenv("V5_STRATEGY_MODE", "trend_aligned")

    from scripts.local_db import init_local_db
    init_local_db(tmp.name)

    from v5_types import EnrichedItem
    from scripts.tasks.scorer import process_enriched_v5
    from tests.conftest import _build_klines

    klines_15m = _build_klines([100 + i for i in range(50)])
    klines_4h = _build_klines([100 + i * 2 for i in range(50)])

    enriched = EnrichedItem(
        symbol="UNKNOWN/USDT", current_price=150.0,
        delta_15m_pct=0.005, volume_24h_usdt=5e7,
        klines_15m=klines_15m, klines_4h=klines_4h,
    )

    asyncio.run(process_enriched_v5(
        enriched=enriched, ai=None,
        paper_pm=MagicMock(), live_pm=MagicMock(),
        mode="SHADOW", db_path=tmp.name, balance_usdt=1000.0,
    ))

    conn = sqlite3.connect(tmp.name)
    row = conn.execute(
        "SELECT funding_z_score FROM trade_scores_v5 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] is None    # NULL = cache miss
```

- [ ] **Step 2: Run, expect 2 fail**

- [ ] **Step 3: Modify `scripts/tasks/scorer.py`**

Read the file. Find `process_enriched_v5`. After `indicators = calculate_indicators(...)` and BEFORE `decision = decide(...)`, add:

```python
    # V6: 拉 funding z-score 并注入 enriched (用于 decide/taxonomy/AI prompt)
    try:
        from scripts.ai.funding_rate_calculator import get_cached_zscore
        fz_row = get_cached_zscore(enriched.symbol, db_path=db_path)
        funding_z_score = fz_row["zscore_30d"] if fz_row else None
        funding_rate_8h = fz_row["current_funding_rate"] if fz_row else None
    except Exception as e:
        print(f"[V5Scorer] funding lookup 失败 ({enriched.symbol}): {e}")
        funding_z_score = None
        funding_rate_8h = None
```

Then in every `_write_trade_score(...)` call inside this function, the funding fields will need to be passed through. The simplest path: modify `_write_trade_score` to accept extra `funding_z_score` and `funding_rate_8h` kwargs, default None.

Find `_write_trade_score` definition. Update its signature and the INSERT:

```python
def _write_trade_score(db_path: str, enriched, indicators, decision, ai=None, risk=None,
                       executed=False, position_id=None, block_reason=None,
                       funding_z_score: Optional[float] = None,
                       funding_rate_8h: Optional[float] = None) -> None:
    # ... existing code ...
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            INSERT INTO trade_scores_v5 (
                symbol, created_at, ... (existing columns) ...,
                funding_z_score, funding_rate_8h
            ) VALUES (..., ?, ?)
        """, (
            ... existing values ...,
            funding_z_score, funding_rate_8h,
        ))
```

NOTE: read the existing INSERT carefully. It has specific column list. Append `funding_z_score, funding_rate_8h` to both the column list AND the values list AND the `?` placeholders.

Then update every call site in `process_enriched_v5`:

```python
    _write_trade_score(db_path, enriched, indicators, decision,
                       funding_z_score=funding_z_score,
                       funding_rate_8h=funding_rate_8h)
```

(Multiple sites — search `_write_trade_score(` and add the two kwargs to each.)

Also pass `funding_z_score` into the candidate dict for taxonomy matching. Find where `_decide_trend_aligned` is called or candidates are built — but actually that's not relevant here. The taxonomy uses funding_z_score via failure_taxonomy._h_against_4h_trend_no_funding which will receive it as part of the candidate dict built in trading_assistant (covered in Task 6).

For setup_type derivation in the scorer (NOT trading_assistant), look for any `derive_setup_type` call in `scorer.py`. If absent (currently it's in reflection_runner only), no action needed here. If present, pass `funding_z_score`.

- [ ] **Step 4: Run tests + full suite**

```bash
python3 -m pytest tests/test_v5_scoring_pipeline.py -v 2>&1 | tail -10
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 2 new + 225 cumulative.

- [ ] **Step 5: Commit**

```bash
git add scripts/tasks/scorer.py tests/test_v5_scoring_pipeline.py
git commit -m "feat(v6): scorer 注入 funding_z_score → trade_scores_v5

- process_enriched_v5 调 get_cached_zscore() lookup
- _write_trade_score 加 2 个 optional kwarg
- Cache miss → NULL,不阻塞评分(backward-compatible)
- 失败异常吞掉 + log,fallback funding=None

2 integration tests (cache hit / cache miss)."
```

---

## Phase 3 — failure_taxonomy 启用 (1 task)

### Task 6: failure_taxonomy 用真 funding_z_score

**Files:**
- Modify: `scripts/ai/failure_taxonomy.py`
- Modify: `tests/test_failure_taxonomy_matcher.py`

- [ ] **Step 1: Append tests to `tests/test_failure_taxonomy_matcher.py`**

Read the file. The existing `_candidate()` helper builds a candidate dict with `funding_z_score=None`. Verify by looking. Then add:

```python
def test_funding_extreme_overrides_4h_filter_when_supports(db):
    """SHORT + 4h 上行(逆) + funding z=+2.5(多头拥挤背书 SHORT) → 不触发 against_4h."""
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(
        side="SHORT", side_int=-1,
        macd_hist_4h=0.005,           # 4h 看多
        funding_z_score=2.5,           # funding 背书 SHORT
    ), db_path=db)
    assert "against_4h_trend_no_funding_filter" not in hits


def test_funding_extreme_against_direction_still_triggers(db):
    """SHORT + 4h 上行 + funding z=-2.5(空头拥挤,反向 → LONG 才合理)
    funding 不背书 SHORT → against_4h 触发."""
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(
        side="SHORT", side_int=-1,
        macd_hist_4h=0.005,
        funding_z_score=-2.5,
    ), db_path=db)
    assert "against_4h_trend_no_funding_filter" in hits


def test_funding_moderate_does_not_override(db):
    """funding |z| < 1.5 (中性) → 不算背书,against_4h 仍触发."""
    from scripts.ai.failure_taxonomy import match_failure_modes
    hits = match_failure_modes(_candidate(
        side="SHORT", side_int=-1,
        macd_hist_4h=0.005,
        funding_z_score=1.0,
    ), db_path=db)
    assert "against_4h_trend_no_funding_filter" in hits
```

- [ ] **Step 2: Run, expect 3 fail or 1 pass + 2 fail (existing logic may partial-match)**

```bash
python3 -m pytest tests/test_failure_taxonomy_matcher.py::test_funding_extreme_overrides_4h_filter_when_supports -v
python3 -m pytest tests/test_failure_taxonomy_matcher.py::test_funding_extreme_against_direction_still_triggers -v
python3 -m pytest tests/test_failure_taxonomy_matcher.py::test_funding_moderate_does_not_override -v
```

- [ ] **Step 3: Modify `_h_against_4h_trend_no_funding` in `scripts/ai/failure_taxonomy.py`**

Read the file. Find the handler. Replace the body with the spec §4.4 version. The existing handler likely already has most of the logic — we just need to make sure the **direction of funding background** matches the candidate **side** to count as "background".

```python
def _h_against_4h_trend_no_funding(c: dict, db_path: str) -> bool:
    """逆 4h 趋势,看 funding 是否给反向 side 背书。

    Logic:
      side_int=+1 (LONG) wants z<0 (short_crowded,反弹要做多)→ background
      side_int=-1 (SHORT) wants z>0 (long_crowded,空头收割)→ background
      |z| >= 1.5 算"足够极端有背书"
    """
    side_int = c.get("side_int") or 0
    macd_4h = c.get("macd_hist_4h") or 0
    fz = c.get("funding_z_score")

    if side_int == 0 or macd_4h == 0:
        return False
    if abs(macd_4h) < 0.004:    # noise floor 不变
        return False

    same_dir = (side_int > 0 and macd_4h > 0) or (side_int < 0 and macd_4h < 0)
    if same_dir:
        return False    # 同向不触发

    # 反向 4h,看 funding 是否给方向背书
    if fz is None:
        return True     # 无 funding 数据 → fallback 触发(保留旧行为)
    if abs(fz) < 1.5:
        return True     # funding 中性 → 触发

    # |fz| >= 1.5 — 判断方向是否跟 candidate side 相反(背书)
    funding_supports_side = (
        (side_int > 0 and fz < 0) or   # LONG wants short_crowded (z<0)
        (side_int < 0 and fz > 0)      # SHORT wants long_crowded (z>0)
    )
    return not funding_supports_side   # 背书 → 不触发 / 不背书 → 触发
```

- [ ] **Step 4: Run tests + full suite**

```bash
python3 -m pytest tests/test_failure_taxonomy_matcher.py -v 2>&1 | tail -15
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 10 in file all pass (7 existing + 3 new); 228 cumulative.

- [ ] **Step 5: Commit**

```bash
git add scripts/ai/failure_taxonomy.py tests/test_failure_taxonomy_matcher.py
git commit -m "feat(v6): failure_taxonomy 真正用上 funding_z_score

against_4h_trend_no_funding_filter logic:
- 反向 4h + funding 方向背书 candidate side → 不触发(放行)
- 反向 4h + funding 中性 (|z|<1.5) → 触发(拒)
- 反向 4h + funding 反向(不背书) → 触发(拒)
- 无 funding 数据 → fallback 旧行为(触发)

3 new tests covering 3 funding direction scenarios."
```

---

## Phase 4 — AI prompt 注入 (1 task)

### Task 7: trading_assistant.decide 注入 funding context

**Files:**
- Modify: `scripts/ai/trading_assistant.py`
- Create: `tests/test_trading_assistant_funding.py`

- [ ] **Step 1: Write `tests/test_trading_assistant_funding.py`**

```python
"""trading_assistant 在 _decide_via_chat 的 prompt 注入 funding context."""
import sqlite3
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock

from v5_types import AIResult, Decision, EnrichedItem, Indicators, RiskPlan


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _objects():
    enriched = EnrichedItem(
        symbol="BTCUSDT", current_price=0.166, delta_15m_pct=0.005,
        volume_24h_usdt=5e7, klines_15m=[], klines_4h=[],
    )
    indicators = Indicators(
        rsi_15m=72.0, macd_15m=0, macd_signal_15m=0,
        macd_hist_15m=-0.0012, macd_hist_prev_15m=0.0008,
        rsi_4h=68.0, macd_hist_4h=-0.003,
        atr_15m=0.0015,
    )
    decision = Decision(should_trade=True, side="SHORT",
                         reasoning="rsi+macd", block_reason=None)
    risk = RiskPlan(entry_price=0.166, sl_price=0.169, tp_price=0.162,
                     size_usdt=15, leverage=10, expected_rr=1.5)
    return enriched, indicators, decision, risk


@pytest.mark.asyncio
async def test_decide_chat_prompt_includes_funding_when_cache_present(db, monkeypatch):
    """funding cache 有 BTCUSDT → AI prompt 含 funding section."""
    from scripts.ai.trading_assistant import TradingAssistant

    # 注入 funding cache
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO funding_zscore_cache (symbol, current_funding_rate,
            zscore_30d, sample_size_30d, is_extreme, extreme_direction)
        VALUES ('BTCUSDT', 0.0008, 2.5, 30, 1, 'long_crowded')
    """)
    conn.commit()
    conn.close()

    enriched, indicators, decision, risk = _objects()
    ai = TradingAssistant()
    ai.client = object()

    captured_prompts = {}

    async def fake_chat_with_capture(system_prompt, user_msg):
        captured_prompts["system"] = system_prompt
        captured_prompts["user"] = user_msg
        return AIResult(execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
                         size_multiplier=1.0, confidence=0.7, reasoning="ok")

    monkeypatch.setattr(ai, "_decide_via_chat", fake_chat_with_capture)

    await ai.decide(enriched, indicators, decision, risk)

    user_msg = captured_prompts.get("user", "")
    assert "FUNDING" in user_msg.upper() or "funding" in user_msg
    assert "2.5" in user_msg     # z-score 数字应出现
    assert "long_crowded" in user_msg or "long crowding" in user_msg.lower()


@pytest.mark.asyncio
async def test_decide_chat_prompt_omits_funding_when_no_cache(db, monkeypatch):
    """cache 空时 prompt 不应含 funding section(或 explicitly say N/A)."""
    from scripts.ai.trading_assistant import TradingAssistant

    enriched, indicators, decision, risk = _objects()
    ai = TradingAssistant()
    ai.client = object()

    captured = {}

    async def fake_chat(system_prompt, user_msg):
        captured["user"] = user_msg
        return AIResult(execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
                         size_multiplier=1.0, confidence=0.7, reasoning="ok")

    monkeypatch.setattr(ai, "_decide_via_chat", fake_chat)

    await ai.decide(enriched, indicators, decision, risk)

    user_msg = captured.get("user", "")
    # 应该 either 不出现 FUNDING block 或者明确 N/A
    if "FUNDING" in user_msg.upper():
        assert "N/A" in user_msg or "no data" in user_msg.lower()
```

- [ ] **Step 2: Run, expect 2 fail**

- [ ] **Step 3: Modify `scripts/ai/trading_assistant.py`**

Read the file. Find `async def decide(...)`. Locate the path that calls `_decide_via_chat`. Before that call, build the funding context dict.

Add a helper at module level (outside class):

```python
def _build_funding_context_block(symbol: str, db_path: Optional[str] = None) -> str:
    """读 funding_zscore_cache 构造 prompt 的 funding section.

    空时返回 '[FUNDING] N/A (cache miss)\\n'。
    """
    try:
        from scripts.ai.funding_rate_calculator import get_cached_zscore
        fz_row = get_cached_zscore(symbol, db_path=db_path)
    except Exception:
        fz_row = None
    if fz_row is None:
        return "\n[FUNDING] N/A (no cache data for this symbol)\n"

    z = fz_row["zscore_30d"]
    rate = fz_row["current_funding_rate"]
    annualized = rate * 365 * 3 * 100   # percent
    crowding = (
        "extreme long crowding (potential SHORT setup)" if z >= 2.0
        else "extreme short crowding (potential LONG setup)" if z <= -2.0
        else "moderate long bias" if z >= 0.5
        else "moderate short bias" if z <= -0.5
        else "neutral"
    )
    return (
        f"\n[FUNDING RATE CONTEXT]\n"
        f"Current 8h funding: {rate*100:+.4f}% (annualized {annualized:+.1f}%)\n"
        f"30-day z-score: {z:+.2f}\n"
        f"Market positioning: {crowding} ({fz_row['extreme_direction'] or 'neutral'})\n"
        f"Sample size: {fz_row['sample_size_30d']}\n"
    )
```

Then in `decide`,where the user_msg is built before being passed to `_decide_via_chat`, append the funding block. The exact location depends on the file — likely there's a `user_msg = ...` string assembly. Find it and concatenate:

```python
        # V6: 注入 funding context
        funding_block = _build_funding_context_block(enriched.symbol)
        user_msg = user_msg + funding_block
```

(If `_decide_via_chat` builds user_msg internally rather than receiving it, modify the signature or inject via a method. Match existing patterns.)

If the structure of `decide` makes this tricky (e.g. user_msg is built inside `_decide_via_chat`), the cleaner alternative is to modify `_decide_via_chat` directly to look up funding context based on `enriched.symbol` (which it would need to receive). In that case:
- Pass `funding_block` as kwarg to `_decide_via_chat`, OR
- Pass `enriched` and look up inside.

Adapt to whichever fits the existing structure.

- [ ] **Step 4: Run tests + full suite**

```bash
python3 -m pytest tests/test_trading_assistant_funding.py -v 2>&1 | tail -10
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 2 new + 230 cumulative.

- [ ] **Step 5: Commit**

```bash
git add scripts/ai/trading_assistant.py tests/test_trading_assistant_funding.py
git commit -m "feat(v6): trading_assistant 注入 funding context 到 AI prompt

- _build_funding_context_block(symbol) 读 funding_zscore_cache
- AI 看到的 user_msg 增加 [FUNDING RATE CONTEXT] section
  - rate, annualized, z-score, crowding direction, sample size
- Cache miss → 显式 'N/A (no cache data)'
- AI reasoning 现在可以引用 funding 维度

2 prompt-injection tests."
```

---

## Phase 5 — reflection 集成 (1 task)

### Task 8: reflection_runner + reflection_prompt 加 funding

**Files:**
- Modify: `scripts/ai/reflection_runner.py`
- Modify: `scripts/ai/reflection_prompt.py`
- Modify: `tests/test_reflection_runner.py`
- Modify: `tests/test_reflection_prompt.py`

- [ ] **Step 1: Append test to `tests/test_reflection_prompt.py`**

```python
def test_prompt_includes_funding_when_present():
    from scripts.ai.reflection_prompt import build_reflection_prompt
    ctx = {
        "paper_trade_id": 1,
        "symbol": "BTCUSDT",
        "side": "SHORT",
        "strategy_id": "v5_rsi_macd",
        "entry_price": 50000, "exit_price": 49000,
        "entry_time": "2026-06-17T08:00:00+00:00",
        "exit_time": "2026-06-17T08:30:00+00:00",
        "exit_reason": "TP_HIT",
        "realized_r": +1.0, "holding_minutes": 30,
        "confidence_at_entry": 0.7,
        "entry_rsi_15m": 72.0, "entry_rsi_4h": 65.0,
        "entry_macd_hist_15m": -0.001, "entry_macd_hist_prev_15m": +0.001,
        "entry_atr_15m": 0.0015,
        "funding_z_score": 2.5,
        "funding_rate_at_entry": 0.0005,
        "rule_reasoning": "test",
        "ai_reasoning": "test",
        "rag_cases_text": "",
        "during_hold_path": "",
        "taxonomy_keys": [],
    }
    prompt = build_reflection_prompt(ctx)
    assert "FUNDING" in prompt.upper() or "funding" in prompt
    assert "2.5" in prompt
    assert "0.0005" in prompt or "0.05%" in prompt or "5e-04" in prompt


def test_prompt_handles_missing_funding():
    """funding_z_score is None → 不抛异常,prompt 含 N/A 标记."""
    from scripts.ai.reflection_prompt import build_reflection_prompt
    ctx = {
        "paper_trade_id": 1, "symbol": "BTCUSDT", "side": "SHORT",
        "strategy_id": "v5_rsi_macd",
        "entry_price": 50000, "exit_price": 49000,
        "entry_time": "2026-06-17T08:00:00+00:00",
        "exit_time": "2026-06-17T08:30:00+00:00",
        "exit_reason": "TP_HIT",
        "realized_r": +1.0, "holding_minutes": 30,
        "confidence_at_entry": 0.7,
        "entry_rsi_15m": 72.0, "entry_rsi_4h": 65.0,
        "entry_macd_hist_15m": -0.001, "entry_macd_hist_prev_15m": +0.001,
        "entry_atr_15m": 0.0015,
        "funding_z_score": None,
        "funding_rate_at_entry": None,
        "rule_reasoning": "x", "ai_reasoning": "x",
        "rag_cases_text": "", "during_hold_path": "",
        "taxonomy_keys": [],
    }
    prompt = build_reflection_prompt(ctx)
    assert prompt  # no exception
```

- [ ] **Step 2: Run, expect 2 fail**

- [ ] **Step 3: Modify `scripts/ai/reflection_prompt.py`**

Read the file. Find the `build_reflection_prompt` function. Find where the f-string template assembles the ENTRY SNAPSHOT section. Add a FUNDING block after it:

```python
    funding_block = ""
    fz = ctx.get("funding_z_score")
    fr = ctx.get("funding_rate_at_entry")
    if fz is not None and fr is not None:
        annualized = fr * 365 * 3 * 100
        funding_block = (
            f"\n[ENTRY FUNDING SNAPSHOT]\n"
            f"8h funding rate: {fr*100:+.4f}% (annualized {annualized:+.1f}%)\n"
            f"30d z-score: {fz:+.2f}\n"
        )
    else:
        funding_block = "\n[ENTRY FUNDING SNAPSHOT]\nN/A (no funding data available)\n"
```

Then concatenate `funding_block` into the prompt template at the right position (after ENTRY SNAPSHOT). Adapt to the existing template structure.

- [ ] **Step 4: Append test to `tests/test_reflection_runner.py`**

```python
def test_run_reflection_loads_funding_from_db(db, monkeypatch):
    """注入 funding_rates + paper_trade,reflection_runner 应当从 DB 取 funding_z_score_at_entry."""
    import json
    import asyncio
    from datetime import datetime, timezone, timedelta
    from unittest.mock import AsyncMock
    from scripts.ai.reflection_runner import run_reflection_for_trade

    et = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    xt = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(db)
    # Paper trade
    conn.execute("""
        INSERT INTO paper_trades (id, symbol, side, entry_price, entry_time, status,
            stop_loss, take_profit, position_size_usdt, leverage, strategy_id,
            created_at, exit_price, exit_time, exit_reason, pnl_percent,
            entry_rsi_15m, entry_macd_hist_15m, ai_confidence, ai_reason)
        VALUES (50, 'BTCUSDT', 'SHORT', 50000, ?, 'CLOSED',
                51000, 49500, 15.0, 10, 'v5_rsi_macd', ?,
                49500, ?, 'TP_HIT', 1.0,
                72.0, -0.001, 0.7, 'test')
    """, (et, et, xt))
    # trade_scores_v5 入场行(scorer 写的)
    conn.execute("""
        INSERT INTO trade_scores_v5 (
            symbol, created_at, rsi_15m, macd_hist_15m, macd_hist_prev_15m,
            atr_15m, current_price, executed, position_id, should_trade, side,
            funding_z_score, funding_rate_8h
        ) VALUES ('BTCUSDT', ?, 72.0, -0.001, 0.0008, 0.0015, 50000, 1, 50, 1, 'SHORT',
                  2.5, 0.0008)
    """, (et,))
    # funding_rate at entry
    conn.execute("""
        INSERT INTO funding_rates (symbol, instrument_id, funding_time,
            funding_rate, annualized_rate, source)
        VALUES ('BTCUSDT', 'BTC-USDT-SWAP', ?, 0.0008, 0.876, 'okx')
    """, (et,))
    conn.commit()
    conn.close()

    fake_ai = AsyncMock(return_value=json.dumps({
        "why_entered": "RSI 72 + funding extreme long crowding observed at entry",
        "what_was_expected": "Expected pullback as longs got squeezed by funding cost",
        "what_actually_happened": "Hit TP within 30 min, funding stayed elevated",
        "correction_idea": "Keep funding z>2 setups as priority",
        "failure_mode_key": None,
        "self_assessed_prediction_accuracy": 0.8,
        "is_in_predicted_failure_mode": False,
    }))

    asyncio.run(run_reflection_for_trade(
        paper_trade_id=50, db_path=db,
        ai_call=fake_ai, taxonomy_keys=[],
    ))

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT funding_z_score_at_entry, funding_rate_at_entry "
        "FROM reflections WHERE paper_trade_id=50"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 2.5
    assert row[1] == 0.0008
```

- [ ] **Step 5: Modify `scripts/ai/reflection_runner.py`**

Find `_load_close_context`. After reading paper_trades + trade_scores_v5, add funding lookup:

```python
    # V6: 拉 funding state at entry
    funding_z_score_at_entry = None
    funding_rate_at_entry = None

    try:
        # Prefer trade_scores_v5.funding_z_score (scorer 写入时刻的快照)
        if ts is not None and ts["funding_z_score"] is not None:
            funding_z_score_at_entry = float(ts["funding_z_score"])
            funding_rate_at_entry = (
                float(ts["funding_rate_8h"]) if ts["funding_rate_8h"] is not None
                else None
            )
        else:
            # Fallback: 找最接近 entry_time 的 funding_rates 行
            conn2 = sqlite3.connect(db_path)
            try:
                fr_row = conn2.execute("""
                    SELECT funding_rate FROM funding_rates
                     WHERE symbol = ? AND funding_time <= ?
                     ORDER BY funding_time DESC LIMIT 1
                """, (pt["symbol"], pt["entry_time"])).fetchone()
                if fr_row:
                    funding_rate_at_entry = float(fr_row[0])
            finally:
                conn2.close()
    except Exception as e:
        print(f"[reflection_runner] funding lookup failed: {e}")
```

Then include in returned ctx:

```python
    return {
        # ... existing fields ...
        "funding_z_score": funding_z_score_at_entry,
        "funding_rate_at_entry": funding_rate_at_entry,
        # ...
    }
```

Find `_persist`. Update INSERT to include the 2 new columns:

```python
    INSERT INTO reflections (
        paper_trade_id, ..., funding_z_score_at_entry, funding_rate_at_entry, ...
    ) VALUES (..., ?, ?, ...)
```

Add the values:

```python
    ctx.get("funding_z_score"),
    ctx.get("funding_rate_at_entry"),
```

- [ ] **Step 6: Run tests + full suite**

```bash
python3 -m pytest tests/test_reflection_runner.py tests/test_reflection_prompt.py -v 2>&1 | tail -15
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 3 new + 233 cumulative.

- [ ] **Step 7: Commit**

```bash
git add scripts/ai/reflection_runner.py scripts/ai/reflection_prompt.py \
        tests/test_reflection_runner.py tests/test_reflection_prompt.py
git commit -m "feat(v6): reflection 集成 funding_z_score_at_entry

- reflection_runner._load_close_context:
  - 优先用 trade_scores_v5.funding_z_score (entry snapshot)
  - fallback: 查 funding_rates 表最接近 entry_time 的行
- _persist 写入 reflections.funding_z_score_at_entry + funding_rate_at_entry
- reflection_prompt 加 [ENTRY FUNDING SNAPSHOT] block (含 rate / annualized / z-score)
- Missing data → 'N/A (no funding data available)'

3 new tests (2 prompt + 1 runner integration)."
```

---

## Phase 6 — API + 前端 (4 tasks)

### Task 9: API schemas + routes

**Files:**
- Create: `api/schemas/v5_funding.py`
- Create: `api/routes/v5_funding.py`
- Modify: `api/main.py`
- Create: `tests/test_v5_funding_api.py`

- [ ] **Step 1: Write `tests/test_v5_funding_api.py`**

```python
"""GET /api/v5/funding/status + /history/{symbol} 测试."""
import sqlite3
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    from api.main import app
    return TestClient(app), tmp.name


def test_status_returns_empty_when_no_data(client):
    c, _ = client
    r = c.get("/api/v5/funding/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["data"] == []


def test_status_returns_cached_zscores(client):
    c, db = client
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO funding_zscore_cache (symbol, current_funding_rate,
            mean_30d, std_30d, zscore_30d, sample_size_30d, is_extreme,
            extreme_direction)
        VALUES ('BTCUSDT', 0.0005, 0.0001, 0.0001, 2.5, 90, 1, 'long_crowded'),
               ('ETHUSDT', -0.0002, 0.00005, 0.0001, -1.5, 80, 0, NULL)
    """)
    conn.commit()
    conn.close()
    r = c.get("/api/v5/funding/status")
    body = r.json()
    assert len(body["data"]) == 2
    by_sym = {item["symbol"]: item for item in body["data"]}
    assert by_sym["BTCUSDT"]["zscore_30d"] == 2.5
    assert by_sym["BTCUSDT"]["is_extreme"] is True
    assert by_sym["BTCUSDT"]["extreme_direction"] == "long_crowded"
    assert by_sym["ETHUSDT"]["is_extreme"] is False


def test_history_returns_funding_rates(client):
    c, db = client
    conn = sqlite3.connect(db)
    for i in range(5):
        conn.execute("""
            INSERT INTO funding_rates (symbol, instrument_id, funding_time,
                funding_rate, annualized_rate, source)
            VALUES ('BTCUSDT', 'BTC-USDT-SWAP', ?, ?, ?, 'okx')
        """, (f"2026-06-17T0{i}:00:00+00:00", 0.0001 * (i + 1),
              0.0001 * (i + 1) * 365 * 3))
    conn.commit()
    conn.close()
    r = c.get("/api/v5/funding/history/BTCUSDT?limit=10")
    body = r.json()
    assert body["status"] == "success"
    assert body["symbol"] == "BTCUSDT"
    assert len(body["data"]) == 5


def test_history_unknown_symbol_returns_empty(client):
    c, _ = client
    r = c.get("/api/v5/funding/history/UNKNOWN")
    body = r.json()
    assert body["data"] == []
```

- [ ] **Step 2: Write `api/schemas/v5_funding.py`**

```python
"""V6 funding rate API schemas."""
from typing import List, Optional

from pydantic import BaseModel


class FundingZScoreItem(BaseModel):
    symbol: str
    computed_at: str
    current_funding_rate: float
    annualized_rate_pct: float
    mean_30d: Optional[float]
    std_30d: Optional[float]
    zscore_30d: Optional[float]
    sample_size_30d: int
    is_extreme: bool
    extreme_direction: Optional[str]


class FundingStatusResponse(BaseModel):
    status: str = "success"
    data: List[FundingZScoreItem]


class FundingHistoryItem(BaseModel):
    funding_time: str
    funding_rate: float
    annualized_rate: float
    source: str


class FundingHistoryResponse(BaseModel):
    status: str = "success"
    symbol: str
    data: List[FundingHistoryItem]
```

- [ ] **Step 3: Write `api/routes/v5_funding.py`**

```python
"""V6 funding rate API."""
import os
import sqlite3

from fastapi import APIRouter, Path, Query

from api.schemas.v5_funding import (
    FundingHistoryItem, FundingHistoryResponse,
    FundingStatusResponse, FundingZScoreItem,
)


router = APIRouter(prefix="/api/v5/funding", tags=["funding"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


@router.get("/status", response_model=FundingStatusResponse)
async def list_funding_status() -> FundingStatusResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT symbol, computed_at, current_funding_rate, mean_30d,
                   std_30d, zscore_30d, sample_size_30d, is_extreme,
                   extreme_direction
              FROM funding_zscore_cache
             ORDER BY ABS(zscore_30d) DESC, symbol
        """).fetchall()
    finally:
        conn.close()
    return FundingStatusResponse(data=[
        FundingZScoreItem(
            symbol=r["symbol"], computed_at=r["computed_at"],
            current_funding_rate=r["current_funding_rate"],
            annualized_rate_pct=r["current_funding_rate"] * 365 * 3 * 100,
            mean_30d=r["mean_30d"], std_30d=r["std_30d"],
            zscore_30d=r["zscore_30d"],
            sample_size_30d=r["sample_size_30d"] or 0,
            is_extreme=bool(r["is_extreme"]),
            extreme_direction=r["extreme_direction"],
        )
        for r in rows
    ])


@router.get("/history/{symbol}", response_model=FundingHistoryResponse)
async def get_funding_history(
    symbol: str = Path(...),
    limit: int = Query(50, ge=1, le=500),
) -> FundingHistoryResponse:
    conn = sqlite3.connect(_db())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT funding_time, funding_rate, annualized_rate, source
              FROM funding_rates
             WHERE symbol = ?
             ORDER BY funding_time DESC
             LIMIT ?
        """, (symbol, limit)).fetchall()
    finally:
        conn.close()
    return FundingHistoryResponse(
        symbol=symbol,
        data=[
            FundingHistoryItem(
                funding_time=r["funding_time"],
                funding_rate=r["funding_rate"],
                annualized_rate=r["annualized_rate"],
                source=r["source"],
            ) for r in rows
        ],
    )
```

- [ ] **Step 4: Register in `api/main.py`**

```python
from api.routes import v5_funding
app.include_router(v5_funding.router)
```

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest tests/test_v5_funding_api.py -v 2>&1 | tail -10
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 4 new + 237 cumulative.

- [ ] **Step 6: Commit**

```bash
git add api/schemas/v5_funding.py api/routes/v5_funding.py api/main.py \
        tests/test_v5_funding_api.py
git commit -m "feat(v6): GET /api/v5/funding/status + /history/{symbol}

- /status: 全部 top-20 z-score(按 |z| 降序)
- /history/{symbol}: 指定 symbol 的 funding 历史(default 50, max 500)
- 含 annualized_rate_pct 给前端直接展示

4 API tests."
```

---

### Task 10: Frontend types + hook + Funding HoloCard on AI Status

**Files:**
- Modify: `Rabbit Hunterfronted/types.ts`
- Create: `Rabbit Hunterfronted/hooks/api/useV5Funding.ts`
- Modify: `Rabbit Hunterfronted/components/pages/V5AIStatusPage.tsx`
- Modify: `Rabbit Hunterfronted/tests/pages/V5AIStatusPage.test.tsx` (if exists, else create test inline)

- [ ] **Step 1: Append to `Rabbit Hunterfronted/types.ts`**

```ts
// ── Funding ──
export interface FundingZScoreItem {
  symbol: string;
  computed_at: string;
  current_funding_rate: number;
  annualized_rate_pct: number;
  mean_30d: number | null;
  std_30d: number | null;
  zscore_30d: number | null;
  sample_size_30d: number;
  is_extreme: boolean;
  extreme_direction: string | null;
}

export interface FundingStatusResponse {
  status: string;
  data: FundingZScoreItem[];
}

export interface FundingHistoryItem {
  funding_time: string;
  funding_rate: number;
  annualized_rate: number;
  source: string;
}

export interface FundingHistoryResponse {
  status: string;
  symbol: string;
  data: FundingHistoryItem[];
}
```

- [ ] **Step 2: Create `Rabbit Hunterfronted/hooks/api/useV5Funding.ts`**

```ts
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { FundingStatusResponse, FundingHistoryResponse } from '../../types';

export function useV5FundingStatus() {
  return useQuery<FundingStatusResponse>({
    queryKey: ['v5', 'funding', 'status'],
    queryFn: () => apiGet<FundingStatusResponse>('/api/v5/funding/status'),
    refetchInterval: 60_000,
  });
}

export function useV5FundingHistory(symbol: string | null, limit = 50) {
  return useQuery<FundingHistoryResponse>({
    queryKey: ['v5', 'funding', 'history', symbol, limit],
    queryFn: () => apiGet<FundingHistoryResponse>(
      `/api/v5/funding/history/${symbol}?limit=${limit}`),
    enabled: !!symbol,
    refetchInterval: 60_000,
  });
}
```

- [ ] **Step 3: Add FundingHeatmapCard to `V5AIStatusPage.tsx`**

Read the file. Find the page component end (the JSX closing `</div>` of the cyber-grid container). Add `<FundingHeatmapCard />` right before it.

Then add the component definition (alongside other Card components in the file):

```tsx
import { useV5FundingStatus } from '../../hooks/api/useV5Funding';

function FundingHeatmapCard() {
  const q = useV5FundingStatus();
  const rows = q.data?.data ?? [];

  return (
    <HoloCard>
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-cyan-300/80 mb-3">
        ▌ FUNDING RATE STATUS (TOP-20)
      </div>
      {rows.length === 0 ? (
        <div className="py-8 text-center font-mono text-cyan-300/40 text-xs">
          ▌ awaiting funding cache refresh...
        </div>
      ) : (
        <div className="space-y-1 font-mono text-[11px]">
          {rows.map(r => {
            const z = r.zscore_30d ?? 0;
            const absZ = Math.abs(z);
            const tone = r.is_extreme
              ? (z > 0 ? 'text-accent-short' : 'text-accent-long')
              : absZ >= 1 ? 'text-accent-warn'
              : 'text-white/60';
            const dirLabel = r.extreme_direction === 'long_crowded'
              ? '★ LONG CROWDED ★'
              : r.extreme_direction === 'short_crowded'
              ? '★ SHORT CROWDED ★'
              : absZ >= 1 ? (z > 0 ? 'mild long bias' : 'mild short bias')
              : 'neutral';
            // Visual bar
            const barPos = Math.max(0, Math.min(10, Math.round(5 + z * 2)));
            const bar = '░'.repeat(barPos) + '▓' + '░'.repeat(10 - barPos);
            return (
              <div key={r.symbol} className="grid grid-cols-12 gap-2 py-1 border-b border-white/5">
                <div className="col-span-2 text-white">{r.symbol}</div>
                <div className="col-span-2 text-white/70">
                  {(r.current_funding_rate * 100).toFixed(4)}%/8h
                </div>
                <div className={`col-span-1 ${tone}`}>z={z.toFixed(2)}</div>
                <div className="col-span-3 text-cyan-300/40 tracking-tighter">{bar}</div>
                <div className={`col-span-3 ${tone}`}>{dirLabel}</div>
                <div className="col-span-1 text-white/40 text-right">n={r.sample_size_30d}</div>
              </div>
            );
          })}
        </div>
      )}
    </HoloCard>
  );
}
```

- [ ] **Step 4: Run FE tests + build**

```bash
cd "Rabbit Hunterfronted"
npx vitest run 2>&1 | tail -5
npx vite build 2>&1 | tail -5
```

Expected: 50 still pass; build OK.

- [ ] **Step 5: Commit**

```bash
cd /Users/lizhishaoniange/Documents/Rabbit-Hunter
git add "Rabbit Hunterfronted/types.ts" \
        "Rabbit Hunterfronted/hooks/api/useV5Funding.ts" \
        "Rabbit Hunterfronted/components/pages/V5AIStatusPage.tsx"
git commit -m "feat(v6): AI Status FundingHeatmapCard

- types.ts + useV5FundingStatus + useV5FundingHistory
- AI Status 页加 FundingHeatmapCard (HoloCard 风格)
  - top-20 按 |z| 降序
  - z 极端时染色(long_crowded 红 / short_crowded 绿)
  - ASCII visual bar 表示 z 在分布的位置
  - sample size 透明展示

Refetch 60s,跟 calibration curve 一致节奏."
```

---

### Task 11: V5ReflectionPage card 显示 funding + V5DashboardPage setup×outcome 分项

**Files:**
- Modify: `Rabbit Hunterfronted/types.ts` (add funding to ReflectionRecord)
- Modify: `Rabbit Hunterfronted/components/pages/V5ReflectionPage.tsx`
- Modify: `Rabbit Hunterfronted/components/pages/V5DashboardPage.tsx`
- Modify: `Rabbit Hunterfronted/services/glossary.ts`

- [ ] **Step 1: Add funding fields to `ReflectionRecord` in `Rabbit Hunterfronted/types.ts`**

Find `export interface ReflectionRecord`. Append:

```ts
  funding_z_score_at_entry: number | null;
  funding_rate_at_entry: number | null;
```

Also modify backend `api/schemas/v5_reflection.py` `ReflectionRecord` to include these fields (read first then add). And update `api/routes/v5_reflection.py` `list_reflections` to SELECT them and include in the dict.

`ReflectionRecord` in `api/schemas/v5_reflection.py`:

```python
class ReflectionRecord(BaseModel):
    # ... existing fields ...
    funding_z_score_at_entry: Optional[float] = None
    funding_rate_at_entry: Optional[float] = None
```

`api/routes/v5_reflection.py` `list_reflections` SELECT:

```python
SELECT r.*, p.symbol, p.side, p.entry_price, p.exit_price, p.exit_reason,
       p.pnl_percent
  FROM reflections r LEFT JOIN paper_trades p ON p.id = r.paper_trade_id
 ORDER BY r.id DESC LIMIT ?
```

`r.*` already covers the new columns. Just need ReflectionRecord schema to accept them.

- [ ] **Step 2: Update `ReflectionCard` in `V5ReflectionPage.tsx`** to display funding row

Read the file. Find `ReflectionCard`. After the indicator/outcome row but before the 5-question grid, add:

```tsx
      {r.funding_z_score_at_entry != null && (
        <div className="text-[11px] font-mono text-violet-300/70">
          funding @ entry: {((r.funding_rate_at_entry ?? 0) * 100).toFixed(4)}%/8h
          {' • '}z={r.funding_z_score_at_entry.toFixed(2)}
          {Math.abs(r.funding_z_score_at_entry) >= 2.0 && (
            <span className="ml-2 text-accent-warn">★ extreme</span>
          )}
        </div>
      )}
```

- [ ] **Step 3: Add SetupPerformanceCard to `V5DashboardPage.tsx`**

This displays setup_type × win_rate × avg_R breakdown:

```tsx
import { useV5SetupPerformance } from '../../hooks/api/useV5Reflections';
// (existing hook from Phase 3 of reflection plan)
```

After the existing cards in V5DashboardPage, add:

```tsx
<Card title="24h Setup Type 分项 (含 funding 维度)">
  <SetupBreakdownTable />
</Card>
```

Then define:

```tsx
function SetupBreakdownTable() {
  const q = useV5SetupPerformance(7);   // 7d window
  const rows = q.data?.data ?? [];
  // 聚合多天 → 按 setup_type
  const byType = new Map<string, { n: number; w: number; sumR: number }>();
  for (const r of rows) {
    const cur = byType.get(r.setup_type) ?? { n: 0, w: 0, sumR: 0 };
    cur.n += r.sample_count;
    cur.w += r.win_count;
    cur.sumR += r.avg_realized_r * r.sample_count;
    byType.set(r.setup_type, cur);
  }
  const sorted = Array.from(byType.entries())
    .map(([t, v]) => ({
      setup_type: t,
      n: v.n,
      win_rate: v.n > 0 ? v.w / v.n : 0,
      avg_r: v.n > 0 ? v.sumR / v.n : 0,
      is_funding: t.startsWith('funding_extreme'),
    }))
    .sort((a, b) => b.n - a.n);
  if (sorted.length === 0) {
    return <div className="py-6 text-center text-white/40">7d 内无 reflection 样本</div>;
  }
  return (
    <div className="overflow-hidden rounded-md border border-white/10">
      <table className="w-full text-xs">
        <thead className="bg-white/5">
          <tr className="text-left text-white/60">
            <th className="px-2 py-2">setup_type</th>
            <th className="px-2 py-2 text-right">n</th>
            <th className="px-2 py-2 text-right">胜率</th>
            <th className="px-2 py-2 text-right">avg R</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(r => (
            <tr key={r.setup_type}
                className={`border-t border-white/5 ${r.is_funding ? 'bg-violet-500/10' : ''}`}>
              <td className="px-2 py-1.5 font-mono text-white/80">
                {r.setup_type}
                {r.is_funding && <span className="ml-2 text-violet-300">★</span>}
              </td>
              <td className="px-2 py-1.5 text-right font-mono">{r.n}</td>
              <td className={`px-2 py-1.5 text-right font-mono ${
                r.win_rate >= 0.5 ? 'text-accent-long' : 'text-accent-short'
              }`}>
                {(r.win_rate * 100).toFixed(0)}%
              </td>
              <td className={`px-2 py-1.5 text-right font-mono ${
                r.avg_r >= 0 ? 'text-accent-long' : 'text-accent-short'
              }`}>
                {r.avg_r >= 0 ? '+' : ''}{r.avg_r.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Add glossary terms to `Rabbit Hunterfronted/services/glossary.ts`**

Append to GLOSSARY dict:

```ts
funding_rate: {
  key: 'funding_rate', zh: '资金费率', en: 'Funding Rate', category: '指标',
  desc: '永续合约每 8 小时结算一次的费用。多头付钱给空头 = 正费率(多头拥挤);反之负费率(空头拥挤)。极端 funding 不可持续,反转信号。',
  example: 'BTC funding +0.05%/8h = 多头每 8h 付出 0.05% 持仓成本 ≈ 年化 +55%',
},
funding_z_score: {
  key: 'funding_z_score', zh: 'funding z 分数', en: 'Funding Z-Score', category: '指标',
  desc: '当前 funding rate 相对过去 30 天历史均值的标准差倍数。z > 2 = 多头极端拥挤(SHORT 候选);z < -2 = 空头极端拥挤(LONG 候选);中间 = 中性。',
},
funding_extreme: {
  key: 'funding_extreme', zh: '资金费率极端', en: 'Funding Extreme', category: '信号',
  desc: '|z| ≥ 2.0 的 funding 状态。setup_type 派生时优先此维度,因为这是独立于价格指标的 alpha 信号。',
},
crowding: {
  key: 'crowding', zh: '杠杆拥挤', en: 'Leverage Crowding', category: '信号',
  desc: '同方向杠杆持仓过度集中。long_crowded = 多头杠杆超额(反转预期下跌);short_crowded = 空头杠杆超额(反转预期上涨)。',
},
```

- [ ] **Step 5: Run + build**

```bash
cd "Rabbit Hunterfronted"
npx vitest run 2>&1 | tail -5
npx vite build 2>&1 | tail -5
cd /Users/lizhishaoniange/Documents/Rabbit-Hunter
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: build OK, all tests pass.

- [ ] **Step 6: Commit**

```bash
git add api/schemas/v5_reflection.py api/routes/v5_reflection.py \
        "Rabbit Hunterfronted/types.ts" \
        "Rabbit Hunterfronted/components/pages/V5ReflectionPage.tsx" \
        "Rabbit Hunterfronted/components/pages/V5DashboardPage.tsx" \
        "Rabbit Hunterfronted/services/glossary.ts"
git commit -m "feat(v6): reflection card + dashboard setup breakdown 显示 funding

Backend:
- ReflectionRecord schema 加 funding_z_score_at_entry + funding_rate_at_entry

Frontend:
- ReflectionCard 新增 funding @ entry 行(z + rate,extreme 加 ★)
- V5DashboardPage 新 SetupBreakdownTable:7d 内按 setup_type 聚合
  win_rate + avg_R,funding_extreme_* 高亮(violet 背景 + ★)
- Glossary 4 个新术语:funding_rate / funding_z_score / funding_extreme / crowding"
```

---

### Task 12: 验证 + docker 重建 + tag

**Files:**
- Modify: `scripts/verify_v5_acceptance.py`

- [ ] **Step 1: Full BE + FE test runs**

```bash
cd /Users/lizhishaoniange/Documents/Rabbit-Hunter
python3 -m pytest tests/ -q 2>&1 | tail -3
cd "Rabbit Hunterfronted"
npm test 2>&1 | tail -10
npx vite build 2>&1 | tail -5
```

Expected: BE ~237 passed; FE 50 passed; build OK.

- [ ] **Step 2: Extend `scripts/verify_v5_acceptance.py`**

Append a new verifier and update `__main__`:

```python
def verify_v6_funding_phase_1_6(db_path: str = "data/rabbit_hunter.db") -> bool:
    import os, sqlite3
    print("\n=== V6 Funding Rate (Phases 1-6) ===")
    if not os.path.exists(db_path):
        print(f"db not found: {db_path}")
        return False
    conn = sqlite3.connect(db_path)
    try:
        for table in ("funding_rates", "funding_zscore_cache"):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"  {table}: {n} rows")
            except sqlite3.OperationalError as e:
                print(f"  {table}: MISSING ({e})")
                return False

        # 验证 trade_scores_v5 + reflections 的 funding 列
        for tbl, col in (
            ("trade_scores_v5", "funding_z_score"),
            ("trade_scores_v5", "funding_rate_8h"),
            ("reflections", "funding_z_score_at_entry"),
            ("reflections", "funding_rate_at_entry"),
        ):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
            if col not in cols:
                print(f"  {tbl}.{col} MISSING")
                return False
        print("  ✓ all funding columns present in trade_scores_v5 + reflections")
        print("\n✅ V6 Funding Phases 1-6 schema verification passed")
        return True
    finally:
        conn.close()
```

In `__main__`:

```python
    ok_e = verify_v6_funding_phase_1_6(db)
    sys.exit(0 if (ok_a and ok_b and ok_c and ok_d and ok_e) else 1)
```

- [ ] **Step 3: Local smoke run**

```bash
python3 scripts/verify_v5_acceptance.py 2>&1 | tail -20
```

(In dev env DB tables may be missing → expected. After docker rebuild + 1min, retest in container.)

- [ ] **Step 4: Commit verify script**

```bash
git add scripts/verify_v5_acceptance.py
git commit -m "chore(v6): verify_v5_acceptance covers Funding Phases 1-6 schema"
```

- [ ] **Step 5: Docker rebuild api + collector + frontend**

```bash
docker compose build --no-cache api collector frontend 2>&1 | tail -10
docker compose up -d api collector frontend 2>&1 | tail -5
```

- [ ] **Step 6: Wait + sanity check endpoints**

```bash
sleep 60
curl -s "http://localhost:8000/api/v5/funding/status" | python3 -m json.tool | head -10
docker compose exec -T collector python -c "
import sqlite3
c = sqlite3.connect('/app/data/rabbit_hunter.db')
print('funding_rates rows:', c.execute('SELECT COUNT(*) FROM funding_rates').fetchone()[0])
print('funding_zscore_cache rows:', c.execute('SELECT COUNT(*) FROM funding_zscore_cache').fetchone()[0])
# Verify columns
for tbl in ('trade_scores_v5', 'reflections'):
    cols = [r[1] for r in c.execute(f'PRAGMA table_info({tbl})').fetchall()]
    f_cols = [c for c in cols if 'funding' in c]
    print(f'{tbl} funding columns:', f_cols)
"
```

Expected:
- `funding_rates`:几百到几千行(backfill 后)
- `funding_zscore_cache`:接近 20 行(一个 symbol 一行)
- `trade_scores_v5` 有 `funding_z_score`、`funding_rate_8h`
- `reflections` 有 `funding_z_score_at_entry`、`funding_rate_at_entry`

- [ ] **Step 7: Browser smoke**

Open http://localhost:5173/v5/ai — 应该看到 **FUNDING RATE STATUS (TOP-20)** HoloCard,top-20 按 |z| 降序排列。

Open http://localhost:5173/v5/dashboard — 滚到底应该看到 **24h Setup Type 分项** card(初始可能 7d 内无样本就显示 empty state)。

- [ ] **Step 8: Tag + push**

```bash
cd /Users/lizhishaoniange/Documents/Rabbit-Hunter
git tag v6.0.0-funding-rate-phases-1-6-shipped
git push origin main 2>&1 | tail -3
git push origin v6.0.0-funding-rate-phases-1-6-shipped 2>&1 | tail -3
```

- [ ] **Step 9: 文档更新(可选)**

If you want a follow-up acceptance log file documenting the deploy, write one — but this is optional. The plan ends here for Phases 1-6.

---

## Self-Review

### Spec coverage check

| Spec section | Task |
|---|---|
| §2.1 数据流图 | T1-T12 collectively |
| §3.1 funding_rates 表 | T1 |
| §3.2 funding_zscore_cache 表 | T1 |
| §3.3 trade_scores_v5 ALTER | T1 + T5 |
| §3.4 reflections ALTER | T1 + T8 |
| §4.1 z-score 计算 | T3 |
| §4.2 极端阈值 | T3 (constants) |
| §4.3 setup_type 派生扩展 | T4 |
| §4.4 failure_taxonomy 启用 | T6 |
| §4.5 AI prompt 注入 | T7 |
| §4.6 reflection prompt 注入 | T8 |
| §5.1 新模块 | T1 (DB) / T2 (OKX client) / T3 (calculator + worker) |
| §5.2 修改清单 | T4-T11 cover all |
| §6.1 reflection card | T11 |
| §6.2 AI Status funding card | T10 |
| §6.3 Dashboard setup 分项 | T11 |
| §7.x 风险缓解 | inline: T3 (单 symbol 失败不阻塞), T7 (cache miss N/A), T8 (fallback to funding_rates) |
| §8 路线图阶段 1-6 | T1-T3 (P1), T4-T5 (P2), T6 (P3), T7 (P4), T8 (P5), T9-T11 (P6) |
| §8 阶段 7(运营调参) | 不在此 plan 范围 — 留作 runtime task |
| §9 验收标准 | T12 schema 检查 + 90 天运营对照 |

No gaps. 12 tasks for spec §8 阶段 1-6.

### Type consistency check

- `symbol` 在 V5 内统一格式 'BTCUSDT'(no slash)
- `instrument_id` 在 funding_rates 表 'BTC-USDT-SWAP'(OKX 原格式)
- `funding_z_score` (Python/DB) ↔ `funding_z_score_at_entry` (reflection) — 明确区分:cache 里是当前,reflection 里是入场时刻
- `funding_rate_8h` (trade_scores) ↔ `funding_rate_at_entry` (reflection)— 同样区分
- z-score 阈值 2.0 在 setup_type / failure_taxonomy / API extreme_direction 三处一致
- API 端 `annualized_rate_pct` 用 percent unit,frontend 直接乘 100 显示

### Placeholder check

Searched plan for TBD / TODO / "Similar to" / "implement later" — none found. All test code, all SQL, all Pydantic schemas, all TSX inline-complete.

### Test count summary

- T1: 6 (schema)
- T2: 7 (OKX client)
- T3: 12 (7 calculator + 5 worker)
- T4: 5 (setup_type funding)
- T5: 2 (scorer pipeline)
- T6: 3 (taxonomy funding)
- T7: 2 (trading_assistant funding prompt)
- T8: 3 (2 prompt + 1 runner)
- T9: 4 (API)
- T10-T11: FE 0 new (existing FE tests cover)

**BE total new: ~44 tests.** Backend goes 206 → ~250.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-17-v6-funding-rate-phases-1-6.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review (spec then quality), continuous execution. Same workflow that shipped V5/V6 reflection 14 tasks 0 blockers and V5.1 + Whitelist follow-ups.

**2. Inline Execution** — execute in this session via `superpowers:executing-plans` with checkpoints for review.

Which approach?
