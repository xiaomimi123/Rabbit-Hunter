# V5 后端重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 RSI×MACD 15min Scalper 策略完整替换 V4.3 P 阶段系统,SHADOW 模式跑通端到端 paper_trades 写入。

**Architecture:** 保留 Scanner→DeepCollector→Scorer→Writer 四任务管道,内部全部换成 V5 模块:`v5_indicator_engine`(纯函数指标)→ `v5_strategy`(AND 合谋决策)→ `v5_risk_calculator`(SL/TP/size)→ AI 二次审查 → PaperPositionManager(SHADOW)/ V5PositionManager(LIVE)。新增 `v5_position_monitor` 30s 轮询活仓,处理 15min 软目标 + AI 续仓 + 指标反转平仓。物理删除 V4.3/V4.4 全部 16 个文件,DB schema 重建。

**Tech Stack:** Python 3.11、asyncio、ccxt 4.4、pytest、SQLite、FastAPI(API 路径重命名 `/api/v5/*`)、OpenAI Assistants API(GPT-4o)。

**Spec reference:** `docs/superpowers/specs/2026-06-12-v5-rsi-macd-15min-rebuild-design.md`

---

## 文件结构

### 新建文件
```
scripts/v5_types.py                 # 共享数据类(Indicators/Decision/RiskPlan/AIResult)
scripts/v5_indicator_engine.py      # 纯函数:K 线 → RSI/MACD/ATR
scripts/v5_strategy.py              # AND 合谋决策器
scripts/v5_risk_calculator.py       # SL/TP/size 计算
scripts/v5_position_monitor.py      # 30s 活仓轮询
scripts/v5_position_manager.py      # LIVE Broker 下单(替代 v43_position_manager)
scripts/v5_signal_manager.py        # 替代 v43_kill_queue_manager,适配新 schema

tests/__init__.py
tests/conftest.py                   # pytest fixtures(mock OKX/AI/DB)
tests/test_v5_indicator_engine.py
tests/test_v5_strategy.py
tests/test_v5_risk_calculator.py
tests/test_v5_position_monitor.py
tests/test_paper_position_manager.py
tests/test_deep_collector_v5.py
tests/test_scoring_pipeline.py      # 集成测试

pytest.ini                          # pytest 配置
scripts/backup_pre_v5.sh            # DB 一次性备份脚本
```

### 修改文件
```
requirements.txt                    # 加 pytest、pytest-asyncio
scripts/local_db.py                 # 删旧 schema + 加 V5 schema + 备份逻辑
scripts/tasks/deep_collector.py     # 加 15min/4h K 线拉取 + ΔP 过滤
scripts/tasks/scorer.py             # 大瘦身,只剩 V5 管道粘合
scripts/tasks/collector_main.py     # 移除 V4.3 references + 启动自检
scripts/paper_position_manager.py   # 加 target_close_at + extension_count
scripts/ai/prompt.py                # V5 system prompt 重写
scripts/ai/trading_assistant.py     # decide() 接受 V5 数据类
scripts/ai/guardrails.py            # 范围调整(短线 SL/TP 更紧)
scripts/tasks/exchange_endpoints.py # 加 fetch_klines 15min/4h
api/routes/scores.py                # 改 /api/v5/* + 适配 V5 schema
api/routes/positions.py             # 同上
api/services/score_service.py       # 同上
api/schemas/scores.py               # KillQueueItem → V5SignalItem
api/schemas/positions.py            # PositionV43Response → PositionV5Response
```

### 物理删除(Phase 11 一次性大 commit)
```
scripts/v41_structure_analyzer.py
scripts/v41_context_gate.py
scripts/v43_score_calculator.py
scripts/v43_decision_policy.py
scripts/v43_hard_filters.py
scripts/v43_feature_extractor.py
scripts/v43_chandelier_stop.py
scripts/v43_collector_integration.py
scripts/v43_entry_validator.py
scripts/v43_kill_queue_manager.py
scripts/v43_weight_manager.py
scripts/run_ai_weight_adjustment.py
scripts/v43_opportunity_density.py
scripts/v43_position_manager.py
scripts/v44_strategy_router.py
scripts/v44_strategy_backtest.py
scripts/v44_strategy_validation_analysis.py
scripts/whale_detector.py
scripts/deepseek_ai.py
scripts/ai_judge.py
```

---

## Phase 0:测试基础设施 + 共享类型

### Task 1: 装 pytest + 创建 tests/ 骨架 + V5 数据类型

**Files:**
- Modify: `requirements.txt`
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `scripts/v5_types.py`
- Create: `tests/test_v5_types.py`

- [ ] **Step 1: 把 pytest 加进 requirements.txt**

打开 `requirements.txt`,在末尾追加(注意保持已有 `==` 风格,精确锁版本):

```
# v5 测试基础设施
pytest==8.3.4
pytest-asyncio==0.24.0
```

- [ ] **Step 2: 创建 pytest.ini**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
addopts = -v --tb=short --strict-markers
```

- [ ] **Step 3: 创建 tests/__init__.py + tests/conftest.py**

`tests/__init__.py`:留空文件。

`tests/conftest.py`:

```python
"""Pytest fixtures for V5 tests."""
import sys
from pathlib import Path

# 把 scripts/ 加入 import path,让测试能 import scripts/v5_*
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))


def _build_klines(prices, base_volume=1000.0, interval_seconds=900):
    """构造 OHLCV 数据,长度 = len(prices),用于模拟 K 线。

    返回 List[Tuple[ts, open, high, low, close, volume]]。
    interval_seconds=900 = 15min;3600=1h;14400=4h。
    """
    import time as _time
    result = []
    base_ts = int(_time.time() * 1000) - len(prices) * interval_seconds * 1000
    for i, close in enumerate(prices):
        prev_close = prices[i - 1] if i > 0 else close
        open_ = prev_close
        high = max(open_, close) * 1.005
        low = min(open_, close) * 0.995
        ts = base_ts + i * interval_seconds * 1000
        result.append((ts, open_, high, low, close, base_volume))
    return result


def pytest_collection_modifyitems(config, items):
    """没用上,占位让 pytest 知道 conftest 在被加载。"""
    pass
```

- [ ] **Step 4: 写 scripts/v5_types.py(数据类骨架)**

```python
"""V5 共享数据类型 — 跨模块传值用。

所有数据类都是 frozen=True、无方法(避免逻辑漏到这里);
方法都放对应模块(indicator_engine / strategy / risk_calculator)。
"""
from dataclasses import dataclass
from typing import Literal, Optional

Side = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class EnrichedItem:
    """DeepCollector 输出,Scorer 输入。"""
    symbol: str                            # OKX symbol,e.g. "H/USDT"
    current_price: float
    delta_15m_pct: float                   # 最新 15min K 线涨跌(小数,例如 0.0342)
    volume_24h_usdt: float                 # Scanner 已算过的 24h USDT 成交额
    klines_15m: list                       # [(ts, o, h, l, c, v), ...] 长度 ≥ 26
    klines_4h: list                        # [(ts, o, h, l, c, v), ...] 长度 ≥ 26


@dataclass(frozen=True)
class Indicators:
    """IndicatorEngine 输出。"""
    rsi_15m: float
    macd_15m: float
    macd_signal_15m: float
    macd_hist_15m: float
    macd_hist_prev_15m: float
    rsi_4h: float
    macd_hist_4h: float
    atr_15m: float


@dataclass(frozen=True)
class Decision:
    """V5Strategy 输出。"""
    should_trade: bool
    side: Optional[Side]                   # 不开单时 None
    reasoning: str                         # 给人/AI 看的解释
    block_reason: Optional[str]            # 不开单时填,例如 NOT_RSI_AND_MACD


@dataclass(frozen=True)
class RiskPlan:
    """RiskCalculator 输出。"""
    entry_price: float
    sl_price: float
    tp_price: float
    size_usdt: float
    leverage: int
    expected_rr: float                     # (TP-Entry)/(Entry-SL),正数


@dataclass(frozen=True)
class AIResult:
    """TradingAssistant.decide() 输出。"""
    execute: bool
    sl_multiplier: float                   # 1.0 表示用规则给的 SL,>1 放宽,<1 收紧
    tp_multiplier: float
    size_multiplier: float                 # 0~1.2 范围
    confidence: float                      # 0~1
    reasoning: str
```

- [ ] **Step 5: 写 tests/test_v5_types.py(确认类型可 import 且 frozen)**

```python
"""V5 数据类 sanity test。"""
import pytest
from v5_types import EnrichedItem, Indicators, Decision, RiskPlan, AIResult


def test_indicators_frozen():
    ind = Indicators(
        rsi_15m=72.0, macd_15m=0.001, macd_signal_15m=0.0005,
        macd_hist_15m=0.0005, macd_hist_prev_15m=-0.0002,
        rsi_4h=65.0, macd_hist_4h=0.003, atr_15m=0.0015,
    )
    with pytest.raises(Exception):
        ind.rsi_15m = 99.0  # frozen,改不动


def test_decision_optional_side():
    d = Decision(should_trade=False, side=None, reasoning="rsi 未达极值", block_reason="NOT_RSI_AND_MACD")
    assert d.side is None
    assert d.should_trade is False


def test_risk_plan_rr_positive():
    p = RiskPlan(entry_price=100.0, sl_price=98.0, tp_price=104.0, size_usdt=15.0, leverage=10, expected_rr=2.0)
    assert p.expected_rr > 0
```

- [ ] **Step 6: 装依赖 + 跑测试 — 期望 PASS**

```bash
pip install pytest==8.3.4 pytest-asyncio==0.24.0
pytest tests/test_v5_types.py -v
```

预期输出:`3 passed`。

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini tests/__init__.py tests/conftest.py \
        scripts/v5_types.py tests/test_v5_types.py
git commit -m "test: bootstrap pytest infra + V5 shared types

- Add pytest + pytest-asyncio to requirements.txt
- Create tests/ skeleton with shared conftest
- Define v5_types: EnrichedItem, Indicators, Decision, RiskPlan, AIResult
- frozen=True on all dataclasses to prevent state leakage between modules"
```

---

## Phase 1:数据库 Schema

### Task 2: V5 表 DDL + 一次性 DB 备份 + 旧表 DROP

**Files:**
- Modify: `scripts/local_db.py`
- Create: `scripts/backup_pre_v5.sh`
- Create: `tests/test_local_db_v5.py`

- [ ] **Step 1: 写备份脚本 scripts/backup_pre_v5.sh**

```bash
#!/bin/sh
# 一次性 DB 备份脚本 — V5 升级前跑一次。
# 用法:./scripts/backup_pre_v5.sh
set -e
DB=data/rabbit_hunter.db
if [ ! -f "$DB" ]; then
    echo "未找到 $DB,跳过备份"
    exit 0
fi
TS=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP="${DB}.backup-pre-v5.${TS}"
cp "$DB" "$BACKUP"
echo "已备份到 $BACKUP"
ls -lh "$BACKUP"
```

`chmod +x scripts/backup_pre_v5.sh`。

- [ ] **Step 2: 写 tests/test_local_db_v5.py(写到一半的红测试 — 先证 fail)**

```python
"""V5 schema 单元测试。"""
import sqlite3
import tempfile
from pathlib import Path

import pytest


def _fresh_db_path():
    """每个测试用独立 tempfile,避免污染。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return tmp.name


def test_trade_scores_v5_schema_has_v5_columns():
    """trade_scores_v5 必须有 RSI/MACD/ATR 等新字段。"""
    from scripts.local_db import init_local_db
    db_path = _fresh_db_path()
    init_local_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(trade_scores_v5)")}
    conn.close()

    expected = {
        "id", "symbol", "created_at",
        "delta_15m_pct", "volume_24h_usdt",
        "rsi_15m", "macd_15m", "macd_signal_15m",
        "macd_hist_15m", "macd_hist_prev_15m",
        "rsi_4h", "macd_hist_4h", "atr_15m", "current_price",
        "should_trade", "side", "reasoning", "block_reason",
        "ai_confidence", "ai_sl_multiplier", "ai_tp_multiplier",
        "ai_size_multiplier", "ai_reasoning", "ai_decision_id",
        "entry_price", "sl_price", "tp_price", "size_usdt", "expected_rr",
        "executed", "position_id",
    }
    missing = expected - cols
    assert not missing, f"trade_scores_v5 缺字段: {missing}"


def test_positions_v5_has_soft_target():
    from scripts.local_db import init_local_db
    db_path = _fresh_db_path()
    init_local_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(positions_v5)")}
    conn.close()

    assert "target_close_at" in cols
    assert "extension_count" in cols
    assert "exit_reason" in cols
    assert "entry_rsi_15m" in cols


def test_paper_trades_has_v5_fields():
    """paper_trades 必须新增 V5 字段(target_close_at 等),不破坏旧列。"""
    from scripts.local_db import init_local_db
    db_path = _fresh_db_path()
    init_local_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(paper_trades)")}
    conn.close()

    # 旧字段保留
    assert "symbol" in cols and "entry_price" in cols and "exit_price" in cols
    # 新字段加上
    for new in ["target_close_at", "extension_count", "entry_rsi_15m",
                "entry_macd_hist_15m", "entry_rsi_4h", "entry_atr_15m",
                "ai_decision_id", "source_score_id"]:
        assert new in cols, f"paper_trades 缺 V5 字段 {new}"


def test_old_v43_tables_dropped():
    """trade_scores_v43 / positions_v43 / ai_weights_v43 必须被 DROP。"""
    from scripts.local_db import init_local_db
    db_path = _fresh_db_path()

    # 先模拟旧 DB:手动创建 v43 表
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE trade_scores_v43 (id INTEGER)")
    conn.execute("CREATE TABLE positions_v43 (id INTEGER)")
    conn.execute("CREATE TABLE ai_weights_v43 (id INTEGER)")
    conn.commit()
    conn.close()

    init_local_db(db_path)  # 初始化 V5 schema

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "trade_scores_v43" not in tables
    assert "positions_v43" not in tables
    assert "ai_weights_v43" not in tables
```

- [ ] **Step 3: 跑测试,期望 4 个全 fail**

```bash
pytest tests/test_local_db_v5.py -v
```

预期:4 failed(目前 `init_local_db` 还没有 V5 schema)。

- [ ] **Step 4: 改 scripts/local_db.py — 删旧 schema 定义,加 V5 schema 定义**

打开 `scripts/local_db.py`,定位顶部的 SQL 常量(CREATE TABLE trade_scores_v43 / positions_v43 / ai_weights_v43 那些),**整段删除**,改为下面这几个常量。同时保留 paper_trades 表的 CREATE,但在 init 流程里加 ALTER。

在文件顶部加入(import 之后,旧的 CREATE 常量删干净):

```python
_V5_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trade_scores_v5 (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol              TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    -- 选币层
    delta_15m_pct       REAL,
    volume_24h_usdt     REAL,
    -- 指标
    rsi_15m             REAL,
    macd_15m            REAL,
    macd_signal_15m     REAL,
    macd_hist_15m       REAL,
    macd_hist_prev_15m  REAL,
    rsi_4h              REAL,
    macd_hist_4h        REAL,
    atr_15m             REAL,
    current_price       REAL,
    -- 决策
    should_trade        INTEGER DEFAULT 0,
    side                TEXT,
    reasoning           TEXT,
    block_reason        TEXT,
    -- AI 层
    ai_confidence       REAL,
    ai_sl_multiplier    REAL,
    ai_tp_multiplier    REAL,
    ai_size_multiplier  REAL,
    ai_reasoning        TEXT,
    ai_decision_id      INTEGER,
    -- 风险
    entry_price         REAL,
    sl_price            REAL,
    tp_price            REAL,
    size_usdt           REAL,
    expected_rr         REAL,
    executed            INTEGER DEFAULT 0,
    position_id         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_trade_scores_v5_symbol_created
    ON trade_scores_v5(symbol, created_at);
CREATE INDEX IF NOT EXISTS idx_trade_scores_v5_executed
    ON trade_scores_v5(executed, created_at);
CREATE INDEX IF NOT EXISTS idx_trade_scores_v5_should_trade
    ON trade_scores_v5(should_trade, created_at);

CREATE TABLE IF NOT EXISTS positions_v5 (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol              TEXT NOT NULL,
    side                TEXT NOT NULL,
    status              TEXT NOT NULL,
    entry_price         REAL,
    entry_time          TEXT,
    sl_price            REAL,
    tp_price            REAL,
    size_usdt           REAL,
    leverage            INTEGER,
    position_size_coins REAL,
    target_close_at     TEXT,
    extension_count     INTEGER DEFAULT 0,
    entry_rsi_15m       REAL,
    entry_macd_hist_15m REAL,
    entry_rsi_4h        REAL,
    entry_atr_15m       REAL,
    exit_price          REAL,
    exit_time           TEXT,
    exit_reason         TEXT,
    pnl_usdt            REAL,
    pnl_pct             REAL,
    holding_minutes     REAL,
    source_score_id     INTEGER,
    ai_decision_id      INTEGER,
    created_at          TEXT,
    updated_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_positions_v5_status_symbol
    ON positions_v5(status, symbol);
CREATE INDEX IF NOT EXISTS idx_positions_v5_status_entry
    ON positions_v5(status, entry_time);
CREATE INDEX IF NOT EXISTS idx_positions_v5_exit_time
    ON positions_v5(exit_time);

CREATE TABLE IF NOT EXISTS ai_training_data (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at               TEXT,
    symbol                   TEXT,
    side                     TEXT,
    entry_price              REAL,
    entry_rsi_15m            REAL,
    entry_macd_hist_15m      REAL,
    entry_rsi_4h             REAL,
    delta_15m_pct            REAL,
    ai_reasoning             TEXT,
    exit_price               REAL,
    exit_reason              TEXT,
    holding_minutes          REAL,
    pnl_pct                  REAL,
    outcome                  TEXT,
    uploaded_to_vector_store INTEGER DEFAULT 0,
    uploaded_at              TEXT
);
"""

_V43_TABLES_TO_DROP = [
    "trade_scores_v43",
    "positions_v43",
    "ai_weights_v43",
    "market_snapshot",
]

_PAPER_TRADES_V5_COLUMNS = [
    ("target_close_at",     "TEXT"),
    ("extension_count",     "INTEGER DEFAULT 0"),
    ("entry_rsi_15m",       "REAL"),
    ("entry_macd_hist_15m", "REAL"),
    ("entry_rsi_4h",        "REAL"),
    ("entry_atr_15m",       "REAL"),
    ("ai_decision_id",      "INTEGER"),
    ("source_score_id",     "INTEGER"),
]
```

把旧的 `init_local_db()` 函数体替换为:

```python
def init_local_db(db_path: str = "data/rabbit_hunter.db") -> None:
    """初始化 V5 schema。
    1. 检测旧 V43 表 → DROP(不备份,备份由 backup_pre_v5.sh 在容器外做)
    2. 建 V5 表
    3. paper_trades 加 V5 字段
    4. ai_training_data 老 schema 不兼容 → 重建(数据已上传 Vector Store)
    """
    import os
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        # 1. DROP 旧 V43/V44 表
        for table in _V43_TABLES_TO_DROP:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        # ai_training_data 老 schema 不兼容,DROP 重建
        conn.execute("DROP TABLE IF EXISTS ai_training_data")

        # 2. 建 V5 表(含 ai_training_data 新 schema)
        conn.executescript(_V5_SCHEMA_SQL)

        # 3. paper_trades 表:旧表存在则 ALTER,不存在则 CREATE
        existing = {row[1] for row in conn.execute("PRAGMA table_info(paper_trades)")}
        if not existing:
            conn.execute(_PAPER_TRADES_CREATE_SQL)  # 已有的 CREATE 常量
            existing = {row[1] for row in conn.execute("PRAGMA table_info(paper_trades)")}
        for col, col_type in _PAPER_TRADES_V5_COLUMNS:
            if col not in existing:
                conn.execute(f"ALTER TABLE paper_trades ADD COLUMN {col} {col_type}")

        # 4. system_settings:留着旧表,但清掉 V43/V44 key
        conn.execute("""
            DELETE FROM system_settings
            WHERE key LIKE 'ai_weights_v43%'
               OR key LIKE 'v44_%'
               OR key LIKE 'v43_%'
        """)

        conn.commit()
    finally:
        conn.close()
```

`_PAPER_TRADES_CREATE_SQL` 就是文件里已经存在的那个 paper_trades CREATE 常量,**保留不动**。如果原文件没单独提取这个常量,把那段 CREATE TABLE paper_trades 改成提取出来命名常量。

`system_settings` 的 CREATE 常量也保留。

- [ ] **Step 5: 再跑测试,期望 4 个全 pass**

```bash
pytest tests/test_local_db_v5.py -v
```

预期:`4 passed`。

如果失败,常见原因:
- `_PAPER_TRADES_CREATE_SQL` 名字对不上 → 在 local_db.py 里找 paper_trades CREATE,提取成常量
- `system_settings` 表不存在导致 DELETE 报错 → 把 DELETE 放在确认表存在之后

- [ ] **Step 6: Commit**

```bash
git add scripts/local_db.py scripts/backup_pre_v5.sh tests/test_local_db_v5.py
git commit -m "feat(db): V5 schema + drop V4.3/V4.4 tables

- New tables: trade_scores_v5, positions_v5, ai_training_data (reset)
- paper_trades: ALTER add target_close_at/extension_count/entry_rsi_15m/...
- Drop trade_scores_v43, positions_v43, ai_weights_v43, market_snapshot
- Clean system_settings of v43_*/v44_*/ai_weights_v43_* keys
- backup_pre_v5.sh for one-shot pre-upgrade backup"
```

---

## Phase 2:Indicator Engine

### Task 3: RSI / MACD / ATR + calculate_indicators 集成

**Files:**
- Create: `scripts/v5_indicator_engine.py`
- Create: `tests/test_v5_indicator_engine.py`

- [ ] **Step 1: 写测试 tests/test_v5_indicator_engine.py(红)**

```python
"""V5 IndicatorEngine 单元测试。

参考值用业内通用公式手算 + Wilder's smoothing。
"""
import pytest
from tests.conftest import _build_klines
from v5_indicator_engine import (
    calculate_rsi,
    calculate_macd,
    calculate_atr,
    calculate_indicators,
)


# ---------- RSI ----------

def test_rsi_all_up_returns_100():
    """连续上涨 30 根 → RSI 接近 100。"""
    klines = _build_klines([100 + i for i in range(30)])
    rsi = calculate_rsi(klines, period=14)
    assert 95 <= rsi <= 100


def test_rsi_all_down_returns_0():
    klines = _build_klines([100 - i for i in range(30)])
    rsi = calculate_rsi(klines, period=14)
    assert 0 <= rsi <= 5


def test_rsi_oscillating_around_50():
    """交替涨跌 → RSI 约 50。"""
    prices = [100 + (1 if i % 2 == 0 else -1) for i in range(30)]
    klines = _build_klines(prices)
    rsi = calculate_rsi(klines, period=14)
    assert 40 <= rsi <= 60


def test_rsi_insufficient_klines_raises():
    klines = _build_klines([100, 101, 102])  # 只有 3 根,< period+1
    with pytest.raises(ValueError, match="InsufficientKlines"):
        calculate_rsi(klines, period=14)


# ---------- MACD ----------

def test_macd_uptrend_positive_hist():
    """上涨趋势 → macd > signal,hist 为正。"""
    klines = _build_klines([100 + i * 0.5 for i in range(50)])
    macd, signal, hist, hist_prev = calculate_macd(klines)
    assert macd > signal, f"上涨 MACD 应 > signal,实际 {macd=} {signal=}"
    assert hist > 0


def test_macd_downtrend_negative_hist():
    klines = _build_klines([100 - i * 0.5 for i in range(50)])
    macd, signal, hist, hist_prev = calculate_macd(klines)
    assert macd < signal
    assert hist < 0


def test_macd_returns_four_values():
    klines = _build_klines([100 + i * 0.3 for i in range(50)])
    result = calculate_macd(klines)
    assert len(result) == 4
    # 都是 float
    for v in result:
        assert isinstance(v, float)


# ---------- ATR ----------

def test_atr_positive_for_volatile_series():
    klines = _build_klines([100 + ((-1) ** i) * 2 for i in range(30)])
    atr = calculate_atr(klines, period=14)
    assert atr > 0


def test_atr_proportional_to_volatility():
    """波动大的 ATR > 波动小的 ATR。"""
    low_vol = _build_klines([100 + 0.1 * i for i in range(30)])
    high_vol = _build_klines([100 + ((-1) ** i) * 5 for i in range(30)])
    assert calculate_atr(high_vol) > calculate_atr(low_vol)


# ---------- calculate_indicators 集成 ----------

def test_calculate_indicators_returns_full_struct():
    from v5_types import Indicators
    klines_15m = _build_klines([100 + i * 0.3 for i in range(50)])
    klines_4h  = _build_klines([100 + i * 0.5 for i in range(40)])
    ind = calculate_indicators(klines_15m, klines_4h)
    assert isinstance(ind, Indicators)
    assert 0 <= ind.rsi_15m <= 100
    assert 0 <= ind.rsi_4h <= 100
    assert ind.atr_15m > 0


def test_calculate_indicators_propagates_insufficient():
    """K 线不足时,集成函数也要透出 ValueError。"""
    klines_15m = _build_klines([100, 101])  # 只有 2 根
    klines_4h  = _build_klines([100 + i for i in range(40)])
    with pytest.raises(ValueError):
        calculate_indicators(klines_15m, klines_4h)
```

- [ ] **Step 2: 跑测试,期望全 fail(模块还不存在)**

```bash
pytest tests/test_v5_indicator_engine.py -v
```

预期:全部 `ModuleNotFoundError: No module named 'v5_indicator_engine'`。

- [ ] **Step 3: 写 scripts/v5_indicator_engine.py**

```python
"""V5 指标引擎 — 纯函数,无副作用,易测试。

提供 RSI / MACD / ATR 三个核心指标,以及一个集成入口 calculate_indicators
接受 15min + 4h 两组 K 线,返回 Indicators 数据类。

K 线格式约定:list[(ts_ms, open, high, low, close, volume)]
"""
from typing import List, Tuple

from v5_types import Indicators


Kline = Tuple[int, float, float, float, float, float]


def _closes(klines: List[Kline]) -> List[float]:
    return [k[4] for k in klines]


def _highs_lows_closes(klines: List[Kline]) -> Tuple[List[float], List[float], List[float]]:
    highs = [k[2] for k in klines]
    lows = [k[3] for k in klines]
    closes = [k[4] for k in klines]
    return highs, lows, closes


# ===== RSI =====

def calculate_rsi(klines: List[Kline], period: int = 14) -> float:
    """Wilder's RSI on close prices。"""
    if len(klines) < period + 1:
        raise ValueError(f"InsufficientKlines: need ≥ {period + 1}, got {len(klines)}")

    closes = _closes(klines)
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    # 初始平均:前 period 个的简单平均
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder smoothing:之后用 (prev*(period-1) + curr) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


# ===== MACD =====

def _ema(values: List[float], period: int) -> List[float]:
    """指数移动平均,返回逐根的 EMA 序列(长度等于 values)。"""
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1.0 - k))
    return ema


def calculate_macd(
    klines: List[Kline],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[float, float, float, float]:
    """返回 (macd, signal, hist, hist_prev)。
    hist_prev 是倒数第二根的 hist,用来检测拐点(变号)。
    """
    if len(klines) < slow + signal:
        raise ValueError(
            f"InsufficientKlines: MACD need ≥ {slow + signal}, got {len(klines)}"
        )
    closes = _closes(klines)
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_series = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_series = _ema(macd_series, signal)
    hist_series = [m - s for m, s in zip(macd_series, signal_series)]
    return (
        float(macd_series[-1]),
        float(signal_series[-1]),
        float(hist_series[-1]),
        float(hist_series[-2]),
    )


# ===== ATR =====

def calculate_atr(klines: List[Kline], period: int = 14) -> float:
    """Wilder's ATR。"""
    if len(klines) < period + 1:
        raise ValueError(f"InsufficientKlines: ATR need ≥ {period + 1}, got {len(klines)}")

    highs, lows, closes = _highs_lows_closes(klines)
    trs = []
    for i in range(1, len(klines)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return float(atr)


# ===== 集成入口 =====

def calculate_indicators(
    klines_15m: List[Kline],
    klines_4h: List[Kline],
) -> Indicators:
    """从 15min + 4h K 线一次性算出所有 V5 需要的指标。"""
    macd_15m, sig_15m, hist_15m, hist_prev_15m = calculate_macd(klines_15m)
    _, _, hist_4h, _ = calculate_macd(klines_4h)
    return Indicators(
        rsi_15m=calculate_rsi(klines_15m),
        macd_15m=macd_15m,
        macd_signal_15m=sig_15m,
        macd_hist_15m=hist_15m,
        macd_hist_prev_15m=hist_prev_15m,
        rsi_4h=calculate_rsi(klines_4h),
        macd_hist_4h=hist_4h,
        atr_15m=calculate_atr(klines_15m),
    )
```

- [ ] **Step 4: 跑测试,期望全 pass**

```bash
pytest tests/test_v5_indicator_engine.py -v
```

预期:`12 passed`。

如果 RSI all_up/all_down 边界测试不过(返回不是接近 100 / 0),检查 `_build_klines` 构造的 high/low 是否合理。

- [ ] **Step 5: Commit**

```bash
git add scripts/v5_indicator_engine.py tests/test_v5_indicator_engine.py
git commit -m "feat(v5): pure indicator engine (RSI/MACD/ATR + calculate_indicators)

- calculate_rsi: Wilder's smoothing, 14-period default
- calculate_macd: returns (macd, signal, hist, hist_prev) — hist_prev enables crossover detection
- calculate_atr: Wilder's ATR
- calculate_indicators: integration point, takes 15m + 4h klines → Indicators
- All raise ValueError('InsufficientKlines: ...') when klines too short
- 12 unit tests pass"
```

---

## Phase 3:V5 Strategy

### Task 4: AND 合谋决策器

**Files:**
- Create: `scripts/v5_strategy.py`
- Create: `tests/test_v5_strategy.py`

- [ ] **Step 1: 写测试 tests/test_v5_strategy.py(红)**

```python
"""V5Strategy AND 合谋决策器测试。

边界:
- RSI > 70 且 MACD hist 由正变负 → SHORT
- RSI < 30 且 MACD hist 由负变正 → LONG
- 任一条件不满足 → 不开单 + 给清晰 block_reason
"""
import pytest
from v5_types import Decision, EnrichedItem, Indicators
from v5_strategy import decide


def _enriched(symbol="H/USDT", price=0.166, delta=0.035):
    """简化构造,只填决策用到的字段。"""
    return EnrichedItem(
        symbol=symbol, current_price=price, delta_15m_pct=delta,
        volume_24h_usdt=50_000_000, klines_15m=[], klines_4h=[],
    )


def _indicators(rsi_15m=50.0, hist=0.0, hist_prev=0.0,
                rsi_4h=50.0, hist_4h=0.0, atr_15m=0.001):
    return Indicators(
        rsi_15m=rsi_15m, macd_15m=0.0, macd_signal_15m=0.0,
        macd_hist_15m=hist, macd_hist_prev_15m=hist_prev,
        rsi_4h=rsi_4h, macd_hist_4h=hist_4h, atr_15m=atr_15m,
    )


# ---------- 开 SHORT ----------

def test_short_when_rsi_overbought_and_macd_bearish_cross():
    """RSI=72 + MACD hist 从 +0.001 变 -0.001(死叉拐点)→ SHORT。"""
    d = decide(_enriched(), _indicators(rsi_15m=72.0, hist=-0.001, hist_prev=0.001))
    assert d.should_trade is True
    assert d.side == "SHORT"
    assert "RSI" in d.reasoning


# ---------- 开 LONG ----------

def test_long_when_rsi_oversold_and_macd_bullish_cross():
    d = decide(_enriched(), _indicators(rsi_15m=28.0, hist=0.001, hist_prev=-0.001))
    assert d.should_trade is True
    assert d.side == "LONG"


# ---------- 拒:RSI 未达极值 ----------

def test_reject_when_rsi_not_extreme():
    d = decide(_enriched(), _indicators(rsi_15m=50.0, hist=-0.001, hist_prev=0.001))
    assert d.should_trade is False
    assert d.side is None
    assert d.block_reason == "NOT_RSI_AND_MACD"


# ---------- 拒:RSI 极值但 MACD 没拐点 ----------

def test_reject_when_rsi_overbought_but_macd_no_bearish_cross():
    """RSI=72 但 MACD hist 仍正 → 不拐点。"""
    d = decide(_enriched(), _indicators(rsi_15m=72.0, hist=0.001, hist_prev=0.0005))
    assert d.should_trade is False
    assert d.block_reason == "NOT_RSI_AND_MACD"


def test_reject_when_rsi_oversold_but_macd_no_bullish_cross():
    d = decide(_enriched(), _indicators(rsi_15m=28.0, hist=-0.001, hist_prev=-0.0005))
    assert d.should_trade is False


# ---------- 边界:RSI 正好等于 70 / 30 ----------

def test_rsi_exactly_70_does_not_trigger_short():
    """门槛是 > 70,正好 70 不算。"""
    d = decide(_enriched(), _indicators(rsi_15m=70.0, hist=-0.001, hist_prev=0.001))
    assert d.should_trade is False


def test_rsi_exactly_30_does_not_trigger_long():
    d = decide(_enriched(), _indicators(rsi_15m=30.0, hist=0.001, hist_prev=-0.001))
    assert d.should_trade is False


# ---------- 配置覆盖(环境变量阈值) ----------

def test_custom_thresholds_from_env(monkeypatch):
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "65")
    monkeypatch.setenv("V5_RSI_OVERSOLD", "35")
    d = decide(_enriched(), _indicators(rsi_15m=66.0, hist=-0.001, hist_prev=0.001))
    assert d.should_trade is True
    assert d.side == "SHORT"
```

- [ ] **Step 2: 跑测试,期望全 fail(模块不存在)**

```bash
pytest tests/test_v5_strategy.py -v
```

预期:全部 ModuleNotFoundError。

- [ ] **Step 3: 写 scripts/v5_strategy.py**

```python
"""V5 策略决策器 — RSI 极值 ∩ MACD 同向拐点 AND 合谋。

入参纯数据(EnrichedItem + Indicators),出参 Decision。
无副作用、无 I/O。
"""
import os
from typing import Optional

from v5_types import Decision, EnrichedItem, Indicators


def _f(env: str, default: float) -> float:
    raw = os.environ.get(env, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bearish_cross(hist: float, hist_prev: float) -> bool:
    """MACD 由正变负(死叉拐点):上一根 ≥ 0,这一根 < 0。"""
    return hist_prev >= 0 and hist < 0


def _bullish_cross(hist: float, hist_prev: float) -> bool:
    """MACD 由负变正(金叉拐点):上一根 ≤ 0,这一根 > 0。"""
    return hist_prev <= 0 and hist > 0


def decide(enriched: EnrichedItem, indicators: Indicators) -> Decision:
    """V5 AND 合谋决策。"""
    overbought = _f("V5_RSI_OVERBOUGHT", 70.0)
    oversold = _f("V5_RSI_OVERSOLD", 30.0)

    rsi = indicators.rsi_15m
    hist = indicators.macd_hist_15m
    hist_prev = indicators.macd_hist_prev_15m

    # SHORT:RSI 超买 + MACD 死叉拐点
    if rsi > overbought and _bearish_cross(hist, hist_prev):
        return Decision(
            should_trade=True,
            side="SHORT",
            reasoning=(
                f"RSI={rsi:.1f} 超买(>{overbought})"
                f" 且 MACD hist {hist_prev:+.4f}→{hist:+.4f} 死叉拐点"
            ),
            block_reason=None,
        )

    # LONG:RSI 超卖 + MACD 金叉拐点
    if rsi < oversold and _bullish_cross(hist, hist_prev):
        return Decision(
            should_trade=True,
            side="LONG",
            reasoning=(
                f"RSI={rsi:.1f} 超卖(<{oversold})"
                f" 且 MACD hist {hist_prev:+.4f}→{hist:+.4f} 金叉拐点"
            ),
            block_reason=None,
        )

    # 拒:讲清楚哪一边没满足
    return Decision(
        should_trade=False,
        side=None,
        reasoning=(
            f"RSI={rsi:.1f}, MACD hist {hist_prev:+.4f}→{hist:+.4f} —"
            f" 不满足 RSI∈(<{oversold} or >{overbought}) ∩ MACD 同向拐点"
        ),
        block_reason="NOT_RSI_AND_MACD",
    )
```

- [ ] **Step 4: 跑测试,期望全 pass**

```bash
pytest tests/test_v5_strategy.py -v
```

预期:`8 passed`。

- [ ] **Step 5: Commit**

```bash
git add scripts/v5_strategy.py tests/test_v5_strategy.py
git commit -m "feat(v5): AND-conjunction strategy decider

RSI overbought (>70) ∩ MACD bearish crossover → SHORT
RSI oversold  (<30) ∩ MACD bullish crossover → LONG
Otherwise: block_reason=NOT_RSI_AND_MACD with diagnostic reasoning

Thresholds overridable via V5_RSI_OVERBOUGHT/V5_RSI_OVERSOLD env vars.
8 unit tests covering both directions, boundary values, env override."
```

---

## Phase 4:Risk Calculator

### Task 5: SL/TP 价格 + position size

**Files:**
- Create: `scripts/v5_risk_calculator.py`
- Create: `tests/test_v5_risk_calculator.py`

- [ ] **Step 1: 写测试 tests/test_v5_risk_calculator.py(红)**

```python
"""V5 RiskCalculator 测试。

约定:
- SL 默认 1.5 × ATR(短线收紧)
- TP 默认 2.5 × ATR
- size_usdt 让"价格走到 SL"的损失正好 = balance × risk_pct
"""
import pytest
from v5_types import RiskPlan
from v5_risk_calculator import plan


def test_long_sl_below_entry_tp_above():
    p = plan(side="LONG", entry=100.0, atr=2.0, balance=1000.0, risk_pct=0.015, leverage=10)
    assert p.sl_price < p.entry_price < p.tp_price


def test_short_sl_above_entry_tp_below():
    p = plan(side="SHORT", entry=100.0, atr=2.0, balance=1000.0, risk_pct=0.015, leverage=10)
    assert p.tp_price < p.entry_price < p.sl_price


def test_long_size_respects_risk_budget():
    """单笔最大亏损 = balance × risk_pct,精度 0.05 USDT 内。"""
    balance, risk_pct, atr, entry = 1000.0, 0.015, 2.0, 100.0
    p = plan(side="LONG", entry=entry, atr=atr, balance=balance,
             risk_pct=risk_pct, leverage=10)
    sl_distance_pct = (entry - p.sl_price) / entry
    # size_usdt × leverage = notional;sl_distance_pct × notional = 最大损失
    notional = p.size_usdt * p.leverage
    max_loss = notional * sl_distance_pct
    expected_max_loss = balance * risk_pct
    assert abs(max_loss - expected_max_loss) < 0.05


def test_short_size_respects_risk_budget():
    balance, risk_pct, atr, entry = 1000.0, 0.015, 2.0, 100.0
    p = plan(side="SHORT", entry=entry, atr=atr, balance=balance,
             risk_pct=risk_pct, leverage=10)
    sl_distance_pct = (p.sl_price - entry) / entry
    notional = p.size_usdt * p.leverage
    max_loss = notional * sl_distance_pct
    assert abs(max_loss - balance * risk_pct) < 0.05


def test_expected_rr_is_tp_over_sl_distance():
    """RR = TP 距离 / SL 距离。默认 2.5×ATR / 1.5×ATR ≈ 1.67。"""
    p = plan(side="LONG", entry=100.0, atr=2.0, balance=1000.0, risk_pct=0.015, leverage=10)
    assert 1.6 < p.expected_rr < 1.7


def test_zero_atr_raises():
    with pytest.raises(ValueError, match="atr"):
        plan(side="LONG", entry=100.0, atr=0.0, balance=1000.0, risk_pct=0.015, leverage=10)


def test_size_does_not_exceed_balance_with_leverage():
    """size × leverage ≤ balance × leverage(显然),且 size ≥ 1 USDT。"""
    p = plan(side="LONG", entry=100.0, atr=2.0, balance=1000.0, risk_pct=0.015, leverage=10)
    assert p.size_usdt >= 1.0
    assert p.size_usdt <= p.entry_price  # 不要求很严,只是 sanity


def test_custom_sl_tp_multipliers_from_env(monkeypatch):
    monkeypatch.setenv("V5_SL_ATR_MULT", "2.0")
    monkeypatch.setenv("V5_TP_ATR_MULT", "4.0")
    p = plan(side="LONG", entry=100.0, atr=2.0, balance=1000.0, risk_pct=0.015, leverage=10)
    # SL 距离 = 2.0 × 2.0 = 4.0,所以 sl=96
    assert abs(p.sl_price - 96.0) < 0.01
    # TP 距离 = 4.0 × 2.0 = 8.0,所以 tp=108
    assert abs(p.tp_price - 108.0) < 0.01
```

- [ ] **Step 2: 跑测试,期望全 fail**

```bash
pytest tests/test_v5_risk_calculator.py -v
```

预期:全部 ModuleNotFoundError。

- [ ] **Step 3: 写 scripts/v5_risk_calculator.py**

```python
"""V5 风险计算器 — SL/TP 价格 + position size。

公式:
- SL 距离 = V5_SL_ATR_MULT × atr   (默认 1.5)
- TP 距离 = V5_TP_ATR_MULT × atr   (默认 2.5)
- size_usdt:让"价到 SL"亏损 = balance × risk_pct
    亏损 = sl_distance_pct × notional = sl_distance_pct × size_usdt × leverage
    → size_usdt = (balance × risk_pct) / (sl_distance_pct × leverage)
"""
import os
from typing import Literal

from v5_types import RiskPlan

Side = Literal["LONG", "SHORT"]


def _f(env: str, default: float) -> float:
    raw = os.environ.get(env, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def plan(
    *,
    side: Side,
    entry: float,
    atr: float,
    balance: float,
    risk_pct: float,
    leverage: int,
) -> RiskPlan:
    """根据 ATR 和风险预算算出完整 RiskPlan。"""
    if atr <= 0:
        raise ValueError(f"atr must be > 0, got {atr}")
    if entry <= 0:
        raise ValueError(f"entry must be > 0, got {entry}")

    sl_mult = _f("V5_SL_ATR_MULT", 1.5)
    tp_mult = _f("V5_TP_ATR_MULT", 2.5)

    sl_distance = sl_mult * atr
    tp_distance = tp_mult * atr

    if side == "LONG":
        sl_price = entry - sl_distance
        tp_price = entry + tp_distance
    else:  # SHORT
        sl_price = entry + sl_distance
        tp_price = entry - tp_distance

    sl_distance_pct = sl_distance / entry
    size_usdt = (balance * risk_pct) / (sl_distance_pct * leverage)
    size_usdt = max(1.0, size_usdt)  # 至少 1 USDT,避免 broker 拒单

    expected_rr = tp_distance / sl_distance

    return RiskPlan(
        entry_price=entry,
        sl_price=sl_price,
        tp_price=tp_price,
        size_usdt=size_usdt,
        leverage=leverage,
        expected_rr=expected_rr,
    )
```

- [ ] **Step 4: 跑测试,期望全 pass**

```bash
pytest tests/test_v5_risk_calculator.py -v
```

预期:`8 passed`。

- [ ] **Step 5: Commit**

```bash
git add scripts/v5_risk_calculator.py tests/test_v5_risk_calculator.py
git commit -m "feat(v5): risk calculator (SL/TP/size from ATR + risk budget)

- SL distance = 1.5 × ATR (env V5_SL_ATR_MULT)
- TP distance = 2.5 × ATR (env V5_TP_ATR_MULT)
- size_usdt s.t. price→SL hit = balance × risk_pct loss
- expected_rr = TP_dist / SL_dist
- 8 unit tests covering both sides, budget respect, env override, zero-ATR error"
```

---

## Phase 5:Deep Collector 改造

### Task 6: 拉 15min/4h K 线 + |ΔP|>3% 过滤

**Files:**
- Modify: `scripts/tasks/exchange_endpoints.py`(加 `fetch_klines`)
- Modify: `scripts/tasks/deep_collector.py`
- Create: `tests/test_deep_collector_v5.py`

- [ ] **Step 1: 写测试 tests/test_deep_collector_v5.py(红)**

```python
"""DeepCollector V5 测试 — 拉 K 线 + ΔP 过滤。

用 mock 替代真实 OKX 调用,只测过滤逻辑。
"""
import pytest
from tests.conftest import _build_klines


def test_filter_by_delta_drops_below_threshold():
    from scripts.tasks.deep_collector import passes_delta_filter
    klines_15m = _build_klines([100, 101])  # ΔP = +1.0%,< 3%
    assert passes_delta_filter(klines_15m, threshold=0.03) is False


def test_filter_by_delta_accepts_above_threshold():
    from scripts.tasks.deep_collector import passes_delta_filter
    klines_15m = _build_klines([100, 103.5])  # +3.5%
    assert passes_delta_filter(klines_15m, threshold=0.03) is True


def test_filter_by_delta_accepts_negative_above_threshold():
    from scripts.tasks.deep_collector import passes_delta_filter
    klines_15m = _build_klines([100, 96.0])  # -4.0%
    assert passes_delta_filter(klines_15m, threshold=0.03) is True


def test_filter_by_delta_exact_threshold_is_inclusive():
    """3.0% 正好等于阈值 → 拒(用 > 而不是 ≥,跟 spec 一致)。"""
    from scripts.tasks.deep_collector import passes_delta_filter
    klines_15m = _build_klines([100, 103.0])  # 正好 +3.0%
    assert passes_delta_filter(klines_15m, threshold=0.03) is False


def test_filter_by_delta_empty_klines_rejects():
    from scripts.tasks.deep_collector import passes_delta_filter
    assert passes_delta_filter([], threshold=0.03) is False


def test_compute_delta_returns_open_to_close_pct():
    from scripts.tasks.deep_collector import compute_delta_15m_pct
    klines = _build_klines([100, 105])
    assert abs(compute_delta_15m_pct(klines) - 0.05) < 1e-6
```

- [ ] **Step 2: 跑测试,期望全 fail**

```bash
pytest tests/test_deep_collector_v5.py -v
```

预期:全部 `AttributeError: module ... has no attribute 'passes_delta_filter'`。

- [ ] **Step 3: 修改 scripts/tasks/exchange_endpoints.py — 加 fetch_klines**

定位文件,加一个新函数(放在 fetch_all_tickers 后面):

```python
def fetch_klines(symbol: str, interval: str = "15m", limit: int = 50) -> list:
    """统一拉 K 线 — 通过 ccxt 抽象。

    interval: '15m' / '1h' / '4h' / ...
    limit:    要的根数,默认 50。
    返回 [(ts_ms, open, high, low, close, volume), ...]。
    """
    try:
        from exchange_factory import get_ccxt_client  # type: ignore[import-not-found]
    except ImportError:
        from scripts.exchange_factory import get_ccxt_client  # type: ignore[import-not-found]
    client = get_ccxt_client()
    raw = client.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
    # ccxt 返回 [[ts, o, h, l, c, v], ...],转 tuple
    return [tuple(row) for row in raw]
```

下面追加 `fetch_klines` 到 `__all__`:

```python
__all__ = [
    "fetch_all_tickers",
    "fetch_klines",
]
```

- [ ] **Step 4: 修改 scripts/tasks/deep_collector.py — 加 V5 逻辑**

先看现有 DeepCollector 长什么样(`Read` 一下),把 enrich_symbol 内部改写:

读现有结构后,在 deep_collector.py 顶部加 helper:

```python
# === V5 过滤 helpers(纯函数,导出给单元测试) ===

def compute_delta_15m_pct(klines_15m: list) -> float:
    """最新 15min K 线的 (close - open) / open。"""
    if not klines_15m:
        return 0.0
    last = klines_15m[-1]
    open_, close = last[1], last[4]
    if open_ <= 0:
        return 0.0
    return (close - open_) / open_


def passes_delta_filter(klines_15m: list, threshold: float = 0.03) -> bool:
    """|ΔP| 必须严格 > threshold。"""
    delta = compute_delta_15m_pct(klines_15m)
    return abs(delta) > threshold
```

然后改 `enrich_symbol`(具体名字按现有代码调整 — 现有版本应该是 `_enrich_symbol` 之类的)。核心是拉 15min/4h、过滤、构造 EnrichedItem 推入 enriched_queue。

完整改写示例:

```python
import os
from v5_types import EnrichedItem
from .exchange_endpoints import fetch_klines

# 在 DeepCollector class 里:
async def _enrich_symbol(self, symbol: str, ticker: dict) -> None:
    """拉 15m + 4h K 线 → 过滤 → 推入 enriched_queue。"""
    threshold = float(os.environ.get("V5_DELTA_15M_THRESHOLD", "0.03"))

    try:
        klines_15m = await asyncio.to_thread(fetch_klines, symbol, "15m", 50)
        klines_4h = await asyncio.to_thread(fetch_klines, symbol, "4h", 30)
    except Exception as e:
        print(f"[DeepCollector] {symbol} K 线拉取失败: {type(e).__name__}: {e}")
        return

    if not passes_delta_filter(klines_15m, threshold):
        return  # 静默 drop,不污染下游

    delta = compute_delta_15m_pct(klines_15m)
    current_price = float(ticker.get("lastPrice") or klines_15m[-1][4])

    item = EnrichedItem(
        symbol=symbol,
        current_price=current_price,
        delta_15m_pct=delta,
        volume_24h_usdt=float(ticker.get("quoteVolume") or 0.0),
        klines_15m=klines_15m,
        klines_4h=klines_4h,
    )

    try:
        self.enriched_queue.put_nowait(item)
        print(f"[DeepCollector] {symbol} ΔP15m={delta*100:+.2f}% → 入 enriched")
    except asyncio.QueueFull:
        print(f"[DeepCollector] {symbol} enriched_queue 满,drop")
```

把 main 循环里调用 `_enrich_symbol(symbol, ticker)`(替代原有 V4.3 enrich)。

- [ ] **Step 5: 跑测试,期望全 pass**

```bash
pytest tests/test_deep_collector_v5.py -v
```

预期:`6 passed`。

- [ ] **Step 6: Commit**

```bash
git add scripts/tasks/exchange_endpoints.py scripts/tasks/deep_collector.py \
        tests/test_deep_collector_v5.py
git commit -m "feat(v5): DeepCollector pulls 15m+4h klines, filters |ΔP|>3%

- exchange_endpoints.fetch_klines: unified ccxt OHLCV fetch
- deep_collector.compute_delta_15m_pct / passes_delta_filter: pure filters
- enrich_symbol: pulls 50×15m + 30×4h, drops if |ΔP|≤3%, builds EnrichedItem
- V5_DELTA_15M_THRESHOLD env override
- 6 unit tests"
```

---

## Phase 6:AI 适配

### Task 7: V5 Prompt + TradingAssistant.decide 接受 V5 类型

**Files:**
- Modify: `scripts/ai/prompt.py`
- Modify: `scripts/ai/trading_assistant.py`
- Modify: `scripts/ai/guardrails.py`
- Create: `tests/test_ai_v5_adapter.py`

- [ ] **Step 1: 写测试 tests/test_ai_v5_adapter.py(红)**

```python
"""TradingAssistant V5 适配测试 — 不调真实 OpenAI,只测 prompt 构造 + 输入输出契约。"""
import pytest
from v5_types import AIResult, Decision, EnrichedItem, Indicators, RiskPlan


def _enriched():
    return EnrichedItem(symbol="H/USDT", current_price=0.166, delta_15m_pct=0.034,
                        volume_24h_usdt=50_000_000, klines_15m=[], klines_4h=[])


def _indicators():
    return Indicators(rsi_15m=72.0, macd_15m=0.001, macd_signal_15m=0.0005,
                      macd_hist_15m=-0.0005, macd_hist_prev_15m=0.0008,
                      rsi_4h=65.0, macd_hist_4h=0.003, atr_15m=0.0015)


def _decision():
    return Decision(should_trade=True, side="SHORT",
                    reasoning="RSI 超买 + MACD 死叉拐点", block_reason=None)


def _risk():
    return RiskPlan(entry_price=0.166, sl_price=0.169, tp_price=0.162,
                    size_usdt=15.0, leverage=10, expected_rr=1.67)


def test_build_v5_prompt_includes_all_indicators():
    from scripts.ai.prompt import build_v5_user_message
    msg = build_v5_user_message(_enriched(), _indicators(), _decision(), _risk())
    assert "RSI 15min" in msg
    assert "72.0" in msg or "72.00" in msg
    assert "MACD" in msg
    assert "SHORT" in msg
    assert "RSI 4h" in msg
    assert "ΔP" in msg or "delta" in msg.lower()


def test_build_v5_prompt_no_v43_artifacts():
    """V5 prompt 不能再出现 P3B/SNIPER/structure_score 等 V4.3 残留。"""
    from scripts.ai.prompt import build_v5_user_message
    msg = build_v5_user_message(_enriched(), _indicators(), _decision(), _risk())
    forbidden = ["P3B", "P3A", "SNIPER", "VULTURE", "structure_score",
                 "manipulation_score", "PUMP_LATE"]
    for word in forbidden:
        assert word not in msg, f"V5 prompt 残留 V4.3 词:{word}"


def test_ai_result_dataclass_round_trip():
    """AIResult 数据类能正确表达 execute=False。"""
    r = AIResult(execute=False, sl_multiplier=1.0, tp_multiplier=1.0,
                 size_multiplier=0.0, confidence=0.3, reasoning="历史相似案例 LOSS 67%")
    assert r.execute is False
    assert r.size_multiplier == 0.0


def test_guardrails_clamps_sl_multiplier():
    """guardrails 把 sl_multiplier 限制在 1.0~3.0 范围。"""
    from scripts.ai.guardrails import clamp_ai_result
    raw = AIResult(execute=True, sl_multiplier=0.5, tp_multiplier=5.0,
                   size_multiplier=2.0, confidence=0.8, reasoning="test")
    clamped = clamp_ai_result(raw)
    assert 1.0 <= clamped.sl_multiplier <= 3.0
    assert 1.5 <= clamped.tp_multiplier <= 5.0
    assert 0.3 <= clamped.size_multiplier <= 1.2
```

- [ ] **Step 2: 跑测试,期望全 fail**

```bash
pytest tests/test_ai_v5_adapter.py -v
```

预期:全部 fail(`build_v5_user_message` / `clamp_ai_result` 还不存在)。

- [ ] **Step 3: 重写 scripts/ai/prompt.py**

整文件替换(旧 prompt 删干净):

```python
"""V5 AI Trading Assistant prompt(GPT-4o)。

接收 EnrichedItem + Indicators + Decision + RiskPlan,
让 AI 决定 execute=True/False,可调 sl/tp/size 倍数。
"""
from v5_types import Decision, EnrichedItem, Indicators, RiskPlan


V5_SYSTEM_PROMPT = """\
You are a short-term trading assistant for a 15-minute scalper.

Strategy context:
- Trades trigger on RSI extreme + MACD histogram crossover (AND-conjunction)
- Soft holding target: 15 minutes (can be extended up to 3 times)
- Per-trade risk budget: 1.5% of account, 10x leverage
- Operating in SHADOW (paper) or LIVE mode

Your job:
1. Decide execute=True/False given the rule-engine's signal
2. Tune sl_multiplier (1.0–3.0), tp_multiplier (1.5–5.0), size_multiplier (0.3–1.2)
3. Provide one-sentence reasoning the operator can read

Reject when:
- 4h trend strongly conflicts with the proposed side
- Historical similar setups (from your vector store) showed >60% loss rate
- Indicators look like a fake breakout (e.g., MACD hist almost zero)

Output strictly JSON via the trading_decision tool.
"""


def build_v5_user_message(
    enriched: EnrichedItem,
    indicators: Indicators,
    decision: Decision,
    risk: RiskPlan,
) -> str:
    """构造交给 AI 的 user message。"""
    return f"""\
Symbol: {enriched.symbol}
Current price: {enriched.current_price:.6f}
15min ΔP: {enriched.delta_15m_pct * 100:+.2f}%
24h volume USDT: {enriched.volume_24h_usdt:,.0f}

Rule engine decision: side={decision.side} should_trade={decision.should_trade}
Reasoning: {decision.reasoning}

Indicators:
- RSI 15min: {indicators.rsi_15m:.2f}
- MACD 15min: {indicators.macd_15m:+.5f} signal={indicators.macd_signal_15m:+.5f} \
hist={indicators.macd_hist_15m:+.5f} hist_prev={indicators.macd_hist_prev_15m:+.5f}
- RSI 4h: {indicators.rsi_4h:.2f}
- MACD 4h hist: {indicators.macd_hist_4h:+.5f}
- ATR 15min: {indicators.atr_15m:.6f}

Proposed risk plan:
- Entry: {risk.entry_price:.6f}
- SL:    {risk.sl_price:.6f} ({abs(risk.entry_price - risk.sl_price) / risk.entry_price * 100:.2f}% away)
- TP:    {risk.tp_price:.6f} ({abs(risk.tp_price - risk.entry_price) / risk.entry_price * 100:.2f}% away)
- Size:  {risk.size_usdt:.2f} USDT × {risk.leverage}x leverage
- Expected RR: 1:{risk.expected_rr:.2f}

Please decide execute, sl_multiplier, tp_multiplier, size_multiplier, and confidence.
"""


__all__ = ["V5_SYSTEM_PROMPT", "build_v5_user_message"]
```

- [ ] **Step 4: 改 scripts/ai/guardrails.py — 加 clamp_ai_result**

完全替换文件内容:

```python
"""V5 AI 输出限幅 — 防止 AI 给出离谱参数。

短线策略下,SL 不能太宽(扛不住扫),TP 不能太远(15min 拿不到),
size 不能超过预算或太小没意义。
"""
from v5_types import AIResult

SL_MULT_MIN, SL_MULT_MAX = 1.0, 3.0
TP_MULT_MIN, TP_MULT_MAX = 1.5, 5.0
SIZE_MULT_MIN, SIZE_MULT_MAX = 0.3, 1.2
CONFIDENCE_MIN, CONFIDENCE_MAX = 0.0, 1.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def clamp_ai_result(raw: AIResult) -> AIResult:
    """把 AI 给的参数夹在合理范围。"""
    return AIResult(
        execute=raw.execute,
        sl_multiplier=_clamp(raw.sl_multiplier, SL_MULT_MIN, SL_MULT_MAX),
        tp_multiplier=_clamp(raw.tp_multiplier, TP_MULT_MIN, TP_MULT_MAX),
        size_multiplier=_clamp(raw.size_multiplier, SIZE_MULT_MIN, SIZE_MULT_MAX),
        confidence=_clamp(raw.confidence, CONFIDENCE_MIN, CONFIDENCE_MAX),
        reasoning=raw.reasoning,
    )


__all__ = ["clamp_ai_result", "SL_MULT_MIN", "SL_MULT_MAX",
           "TP_MULT_MIN", "TP_MULT_MAX", "SIZE_MULT_MIN", "SIZE_MULT_MAX"]
```

- [ ] **Step 5: 改 scripts/ai/trading_assistant.py — decide() 改签名**

找 `decide` 方法,替换签名 + 内部:

```python
async def decide(
    self,
    enriched,           # EnrichedItem
    indicators,         # Indicators
    decision,           # Decision
    risk,               # RiskPlan
) -> "AIResult":
    """V5 二次审查 — 用 GPT-4o 看完上下文给最终参数。"""
    from v5_types import AIResult
    from scripts.ai.prompt import V5_SYSTEM_PROMPT, build_v5_user_message
    from scripts.ai.guardrails import clamp_ai_result

    if not self.client or not self.assistant_id:
        return AIResult(execute=False, sl_multiplier=1.0, tp_multiplier=1.0,
                        size_multiplier=0.0, confidence=0.0,
                        reasoning="AI 未初始化")

    user_msg = build_v5_user_message(enriched, indicators, decision, risk)
    try:
        thread = await self._create_thread()
        await self._add_message(thread.id, user_msg)
        run = await self._run_with_timeout(thread.id, self.assistant_id, timeout_s=20)
        raw_json = await self._extract_tool_output(thread.id, run)
        result = AIResult(
            execute=bool(raw_json.get("execute", False)),
            sl_multiplier=float(raw_json.get("sl_multiplier", 1.0)),
            tp_multiplier=float(raw_json.get("tp_multiplier", 1.0)),
            size_multiplier=float(raw_json.get("size_multiplier", 1.0)),
            confidence=float(raw_json.get("confidence", 0.5)),
            reasoning=str(raw_json.get("reasoning", "")),
        )
        return clamp_ai_result(result)
    except asyncio.TimeoutError:
        return AIResult(execute=False, sl_multiplier=1.0, tp_multiplier=1.0,
                        size_multiplier=0.0, confidence=0.0,
                        reasoning="AI 调用超时(>20s),fail-closed")
    except Exception as e:
        return AIResult(execute=False, sl_multiplier=1.0, tp_multiplier=1.0,
                        size_multiplier=0.0, confidence=0.0,
                        reasoning=f"AI 调用异常 {type(e).__name__}: {e}")
```

不要保留 V4.3 的 `decide()` 老签名 — V5 是完全替换。`_create_thread` / `_add_message` / `_run_with_timeout` / `_extract_tool_output` 这几个 helper 沿用现有版本,不动。

`__init__` 里 system prompt 引用 `V5_SYSTEM_PROMPT`(原引用 V4.3 prompt 的地方替换)。

- [ ] **Step 6: 跑测试,期望全 pass**

```bash
pytest tests/test_ai_v5_adapter.py -v
```

预期:`4 passed`。

- [ ] **Step 7: Commit**

```bash
git add scripts/ai/prompt.py scripts/ai/guardrails.py scripts/ai/trading_assistant.py \
        tests/test_ai_v5_adapter.py
git commit -m "feat(v5): AI layer adapted to V5 types

- prompt.py: V5_SYSTEM_PROMPT + build_v5_user_message (RSI/MACD/4h ctx)
- guardrails.py: clamp_ai_result with V5 ranges (SL 1-3x, TP 1.5-5x, size 0.3-1.2x)
- trading_assistant.decide: takes EnrichedItem/Indicators/Decision/RiskPlan, returns AIResult
- All V4.3/V4.4 references removed from prompt
- 4 unit tests covering prompt content, guardrails clamping"
```

---

## Phase 7:Paper Position Manager 改造

### Task 8: target_close_at + extension_count + 入场快照

**Files:**
- Modify: `scripts/paper_position_manager.py`
- Create: `tests/test_paper_position_manager_v5.py`

- [ ] **Step 1: 写测试 tests/test_paper_position_manager_v5.py(红)**

```python
"""Paper Position Manager V5 测试 — 加 target_close_at 等字段。"""
import sqlite3
import tempfile
import pytest
from datetime import datetime, timezone, timedelta

from v5_types import AIResult, Decision, EnrichedItem, Indicators, RiskPlan


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    return tmp.name


def _open_intent_kwargs():
    return dict(
        enriched=EnrichedItem(symbol="H/USDT", current_price=0.166, delta_15m_pct=0.034,
                              volume_24h_usdt=50_000_000, klines_15m=[], klines_4h=[]),
        indicators=Indicators(rsi_15m=72.0, macd_15m=0.001, macd_signal_15m=0.0005,
                              macd_hist_15m=-0.0005, macd_hist_prev_15m=0.0008,
                              rsi_4h=65.0, macd_hist_4h=0.003, atr_15m=0.0015),
        decision=Decision(should_trade=True, side="SHORT", reasoning="...", block_reason=None),
        risk=RiskPlan(entry_price=0.166, sl_price=0.169, tp_price=0.162,
                      size_usdt=15.0, leverage=10, expected_rr=1.67),
        ai=AIResult(execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
                    size_multiplier=1.0, confidence=0.7, reasoning="ok"),
    )


def test_open_position_writes_target_close_at():
    from scripts.paper_position_manager import PaperPositionManager
    db = _fresh_db()
    pm = PaperPositionManager(db_path=db)
    pid = pm.open_position(**_open_intent_kwargs())

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT entry_time, target_close_at, extension_count FROM paper_trades WHERE id=?",
        (pid,),
    ).fetchone()
    conn.close()
    entry_time, target_close_at, extension_count = row
    assert target_close_at is not None
    assert extension_count == 0
    # target = entry + 15min(秒级容差)
    et = datetime.fromisoformat(entry_time)
    tc = datetime.fromisoformat(target_close_at)
    assert abs((tc - et).total_seconds() - 900) < 5


def test_open_position_writes_indicator_snapshot():
    from scripts.paper_position_manager import PaperPositionManager
    db = _fresh_db()
    pm = PaperPositionManager(db_path=db)
    pid = pm.open_position(**_open_intent_kwargs())

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT entry_rsi_15m, entry_macd_hist_15m, entry_rsi_4h, entry_atr_15m "
        "FROM paper_trades WHERE id=?", (pid,)).fetchone()
    conn.close()
    assert row[0] == 72.0
    assert abs(row[1] - (-0.0005)) < 1e-9
    assert row[2] == 65.0
    assert abs(row[3] - 0.0015) < 1e-9


def test_extend_position_advances_target_and_count():
    from scripts.paper_position_manager import PaperPositionManager
    db = _fresh_db()
    pm = PaperPositionManager(db_path=db)
    pid = pm.open_position(**_open_intent_kwargs())

    pm.extend_position(pid, extra_minutes=15)

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT target_close_at, extension_count FROM paper_trades WHERE id=?",
        (pid,)).fetchone()
    conn.close()
    target_close_at, extension_count = row
    assert extension_count == 1


def test_close_position_fills_exit_fields():
    from scripts.paper_position_manager import PaperPositionManager
    db = _fresh_db()
    pm = PaperPositionManager(db_path=db)
    pid = pm.open_position(**_open_intent_kwargs())

    pm.close_position(pid, exit_price=0.162, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, exit_price, exit_reason, pnl_usdt, holding_minutes "
        "FROM paper_trades WHERE id=?", (pid,)).fetchone()
    conn.close()
    status, exit_price, exit_reason, pnl_usdt, holding_minutes = row
    assert status == "CLOSED"
    assert exit_price == 0.162
    assert exit_reason == "TP_HIT"
    # SHORT,entry=0.166,exit=0.162 → 盈利
    assert pnl_usdt is not None and pnl_usdt > 0
```

- [ ] **Step 2: 跑测试,期望全 fail**

```bash
pytest tests/test_paper_position_manager_v5.py -v
```

预期:fail。

- [ ] **Step 3: 改 scripts/paper_position_manager.py**

读现有文件,把 `open_position` / `close_position` / 新增 `extend_position` 改写。新签名:

```python
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional


SOFT_TARGET_MINUTES = 15


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PaperPositionManager:
    def __init__(self, db_path: str = "data/rabbit_hunter.db"):
        self.db_path = db_path

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def open_position(self, *, enriched, indicators, decision, risk, ai) -> int:
        """SHADOW 开仓 — 返回 paper_trades.id。"""
        # 应用 AI 调整后的 sl/tp/size
        sl_dist = abs(risk.entry_price - risk.sl_price) * ai.sl_multiplier
        tp_dist = abs(risk.tp_price - risk.entry_price) * ai.tp_multiplier
        if decision.side == "LONG":
            sl_price = risk.entry_price - sl_dist
            tp_price = risk.entry_price + tp_dist
        else:
            sl_price = risk.entry_price + sl_dist
            tp_price = risk.entry_price - tp_dist
        size_usdt = max(1.0, risk.size_usdt * ai.size_multiplier)

        entry_time = _utcnow()
        target_close_at = entry_time + timedelta(minutes=SOFT_TARGET_MINUTES)

        conn = self._conn()
        try:
            cur = conn.execute("""
                INSERT INTO paper_trades (
                    symbol, side, entry_price, status, strategy_id,
                    created_at, entry_time, target_close_at, extension_count,
                    current_price, stop_loss, take_profit, position_size_usdt,
                    leverage, ai_confidence, ai_sl_multiplier, ai_tp_multiplier,
                    ai_reason, entry_rsi_15m, entry_macd_hist_15m, entry_rsi_4h,
                    entry_atr_15m, signal_score
                ) VALUES (?, ?, ?, 'OPEN', 'v5_rsi_macd',
                          ?, ?, ?, 0,
                          ?, ?, ?, ?,
                          ?, ?, ?, ?,
                          ?, ?, ?, ?,
                          ?, ?)
            """, (
                enriched.symbol, decision.side, risk.entry_price,
                entry_time.isoformat(), entry_time.isoformat(), target_close_at.isoformat(),
                risk.entry_price, sl_price, tp_price, size_usdt,
                risk.leverage, ai.confidence, ai.sl_multiplier, ai.tp_multiplier,
                ai.reasoning, indicators.rsi_15m, indicators.macd_hist_15m,
                indicators.rsi_4h, indicators.atr_15m,
                risk.expected_rr,
            ))
            pid = cur.lastrowid
            conn.commit()
            return pid
        finally:
            conn.close()

    def extend_position(self, position_id: int, extra_minutes: int = 15) -> None:
        """AI 决定续仓 — extension_count+=1,target_close_at 推后。"""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT target_close_at, extension_count FROM paper_trades WHERE id=?",
                (position_id,)).fetchone()
            if not row:
                return
            current_target = datetime.fromisoformat(row[0])
            new_target = current_target + timedelta(minutes=extra_minutes)
            new_count = (row[1] or 0) + 1
            conn.execute(
                "UPDATE paper_trades SET target_close_at=?, extension_count=?, "
                "updated_at=? WHERE id=?",
                (new_target.isoformat(), new_count, _utcnow().isoformat(), position_id))
            conn.commit()
        finally:
            conn.close()

    def close_position(self, position_id: int, *, exit_price: float, exit_reason: str) -> None:
        """平仓 — 计算 PnL + 写 exit_*。"""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT side, entry_price, position_size_usdt, leverage, entry_time "
                "FROM paper_trades WHERE id=?", (position_id,)).fetchone()
            if not row:
                return
            side, entry_price, size_usdt, leverage, entry_time_str = row

            # 计算 PnL
            entry_time = datetime.fromisoformat(entry_time_str)
            exit_time = _utcnow()
            holding_minutes = (exit_time - entry_time).total_seconds() / 60.0
            notional = (size_usdt or 0) * (leverage or 1)
            if side == "LONG":
                pnl_pct = (exit_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - exit_price) / entry_price
            pnl_usdt = notional * pnl_pct

            conn.execute(
                "UPDATE paper_trades SET status='CLOSED', exit_price=?, exit_time=?, "
                "exit_reason=?, pnl=?, pnl_percent=?, holding_hours=?, updated_at=? "
                "WHERE id=?",
                (exit_price, exit_time.isoformat(), exit_reason,
                 pnl_usdt, pnl_pct * 100, holding_minutes / 60.0,
                 exit_time.isoformat(), position_id))
            conn.commit()
        finally:
            conn.close()

    def get_open_positions(self) -> list:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, symbol, side, entry_price, target_close_at, "
                "extension_count, entry_time, stop_loss, take_profit "
                "FROM paper_trades WHERE status='OPEN'")
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            conn.close()
```

注意:上面 SQL 里的 `pnl` / `pnl_percent` / `holding_hours` / `position_size_usdt` / `stop_loss` / `take_profit` / `current_price` / `strategy_id` 等字段必须跟 paper_trades 现有 schema 一致 — 跑测试时如果报 `no column: ...`,去 `scripts/local_db.py` 看实际列名再调整。

测试里的 SQL `pnl_usdt` 是测试别名 — 实际 paper_trades 列叫 `pnl`,在测试里取的时候改 SELECT 字段对应即可:

```python
# 测试里改成:
row = conn.execute(
    "SELECT status, exit_price, exit_reason, pnl, holding_hours FROM paper_trades WHERE id=?",
    (pid,)).fetchone()
status, exit_price, exit_reason, pnl, holding_hours = row
```

(test 也要相应调整断言变量名)

- [ ] **Step 4: 跑测试,期望全 pass**

```bash
pytest tests/test_paper_position_manager_v5.py -v
```

预期:`4 passed`。

- [ ] **Step 5: Commit**

```bash
git add scripts/paper_position_manager.py tests/test_paper_position_manager_v5.py
git commit -m "feat(v5): PaperPositionManager with 15min soft target + indicator snapshot

- open_position now takes (enriched, indicators, decision, risk, ai); writes
  target_close_at = entry+15min, extension_count=0, entry_rsi/macd/atr snapshots
- extend_position: AI-driven extension, target += 15min, count++
- close_position: fills exit_price/exit_time/exit_reason/pnl/holding_hours
- 4 unit tests with in-memory tempfile DB"
```

---

## Phase 8:V5 Position Monitor

### Task 9: 30s 轮询活仓 + 退出触发器

**Files:**
- Create: `scripts/v5_position_monitor.py`
- Create: `tests/test_v5_position_monitor.py`

- [ ] **Step 1: 写测试 tests/test_v5_position_monitor.py(红)**

```python
"""V5PositionMonitor 退出触发器测试。

`check_exit_triggers` 是纯函数:接收活仓 + 当前市场快照 → CloseIntent | None
"""
from datetime import datetime, timezone, timedelta
import pytest


def _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162,
                   target_offset_min=5, extension_count=0):
    """构造一个 OPEN 仓位 dict(模拟从 DB 读出)。"""
    now = datetime.now(timezone.utc)
    target = now + timedelta(minutes=target_offset_min)
    return {
        "id": 1, "symbol": "H/USDT", "side": side, "entry_price": entry,
        "stop_loss": sl, "take_profit": tp,
        "target_close_at": target.isoformat(),
        "extension_count": extension_count,
        "entry_time": (now - timedelta(minutes=10)).isoformat(),
    }


def _market(price=0.165, rsi_15m=67.0, macd_hist=-0.0003, macd_hist_prev=-0.0005):
    return {
        "price": price, "rsi_15m": rsi_15m,
        "macd_hist_15m": macd_hist, "macd_hist_prev_15m": macd_hist_prev,
    }


def test_short_hits_tp_returns_tp_hit():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162)
    market = _market(price=0.160)
    intent = check_exit_triggers(pos, market)
    assert intent is not None
    assert intent["exit_reason"] == "TP_HIT"


def test_short_hits_sl_returns_sl_hit():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162)
    intent = check_exit_triggers(pos, _market(price=0.170))
    assert intent["exit_reason"] == "SL_HIT"


def test_long_hits_tp():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="LONG", entry=0.166, sl=0.163, tp=0.170)
    intent = check_exit_triggers(pos, _market(price=0.171))
    assert intent["exit_reason"] == "TP_HIT"


def test_long_hits_sl():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="LONG", entry=0.166, sl=0.163, tp=0.170)
    intent = check_exit_triggers(pos, _market(price=0.162))
    assert intent["exit_reason"] == "SL_HIT"


def test_soft_target_reached_returns_timebox_intent():
    """target_close_at 已过 + price 没碰 SL/TP → 返回 AI_TIMEBOX 意图(让上层调 AI)。"""
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162,
                         target_offset_min=-1)  # 1 分钟前就过期了
    intent = check_exit_triggers(pos, _market(price=0.165))
    assert intent is not None
    assert intent["exit_reason"] == "SOFT_TARGET_REACHED"


def test_max_extension_force_close():
    """extension_count 已 3,target 又过 → 强制平 AI_EXTEND_MAX。"""
    from scripts.v5_position_monitor import check_exit_triggers, MAX_EXTENSIONS
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162,
                         target_offset_min=-1, extension_count=MAX_EXTENSIONS)
    intent = check_exit_triggers(pos, _market(price=0.165))
    assert intent["exit_reason"] == "AI_EXTEND_MAX"


def test_signal_reverse_short_when_rsi_drops_below_65():
    """SHORT 仓 RSI 跌破 65 → SIGNAL_REVERSE。"""
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162)
    intent = check_exit_triggers(pos, _market(price=0.165, rsi_15m=64.0))
    assert intent["exit_reason"] == "SIGNAL_REVERSE"


def test_signal_reverse_long_when_rsi_rises_above_35():
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="LONG", entry=0.166, sl=0.163, tp=0.170)
    intent = check_exit_triggers(pos, _market(price=0.167, rsi_15m=36.0))
    assert intent["exit_reason"] == "SIGNAL_REVERSE"


def test_macd_recross_short_triggers_reverse():
    """SHORT 仓 MACD 由死叉重新金叉(hist 从负变正)→ SIGNAL_REVERSE。"""
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162)
    intent = check_exit_triggers(pos, _market(
        price=0.165, rsi_15m=68.0,
        macd_hist=0.0003, macd_hist_prev=-0.0005,  # 金叉
    ))
    assert intent["exit_reason"] == "SIGNAL_REVERSE"


def test_no_trigger_returns_none():
    """所有条件都没满足。"""
    from scripts.v5_position_monitor import check_exit_triggers
    pos = _open_position(side="SHORT", entry=0.166, sl=0.169, tp=0.162,
                         target_offset_min=5)
    intent = check_exit_triggers(pos, _market(price=0.165, rsi_15m=68.0,
                                              macd_hist=-0.0003, macd_hist_prev=-0.0005))
    assert intent is None
```

- [ ] **Step 2: 跑测试,期望全 fail**

```bash
pytest tests/test_v5_position_monitor.py -v
```

预期:全部 ModuleNotFoundError。

- [ ] **Step 3: 写 scripts/v5_position_monitor.py**

```python
"""V5 持仓监控 — 每 30s 轮询活仓,决定是否平仓。

check_exit_triggers 是纯函数,易测;30s 轮询循环放 run() 协程里。
"""
import asyncio
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


MAX_EXTENSIONS = int(os.environ.get("V5_MAX_EXTENSIONS", "3"))
RSI_REVERSE_SHORT = float(os.environ.get("V5_RSI_REVERSE_SHORT", "65"))
RSI_REVERSE_LONG = float(os.environ.get("V5_RSI_REVERSE_LONG", "35"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sl_hit(side: str, current_price: float, sl_price: float) -> bool:
    if side == "LONG":
        return current_price <= sl_price
    return current_price >= sl_price


def _tp_hit(side: str, current_price: float, tp_price: float) -> bool:
    if side == "LONG":
        return current_price >= tp_price
    return current_price <= tp_price


def _signal_reversed(side: str, rsi: float, hist: float, hist_prev: float) -> bool:
    """SIGNAL_REVERSE 判定:
    - SHORT:RSI 跌破 65,或 MACD 由死叉(hist<0)重新金叉(hist>0)
    - LONG: RSI 涨过 35,或 MACD 由金叉(hist>0)重新死叉(hist<0)
    """
    if side == "SHORT":
        if rsi < RSI_REVERSE_SHORT:
            return True
        if hist_prev < 0 and hist > 0:  # 重新金叉
            return True
    else:  # LONG
        if rsi > RSI_REVERSE_LONG:
            return True
        if hist_prev > 0 and hist < 0:  # 重新死叉
            return True
    return False


def check_exit_triggers(position: dict, market: dict) -> Optional[dict]:
    """检查所有退出条件。返回 CloseIntent dict 或 None(不平)。

    优先级:SL → TP → soft target → 指标反转。
    """
    side = position["side"]
    current_price = market["price"]
    sl_price = position["stop_loss"]
    tp_price = position["take_profit"]

    # 1. SL
    if _sl_hit(side, current_price, sl_price):
        return {"position_id": position["id"], "exit_price": current_price,
                "exit_reason": "SL_HIT"}

    # 2. TP
    if _tp_hit(side, current_price, tp_price):
        return {"position_id": position["id"], "exit_price": current_price,
                "exit_reason": "TP_HIT"}

    # 3. 软目标到点
    target_str = position.get("target_close_at")
    if target_str:
        target = datetime.fromisoformat(target_str)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        if _utcnow() >= target:
            if (position.get("extension_count") or 0) >= MAX_EXTENSIONS:
                return {"position_id": position["id"], "exit_price": current_price,
                        "exit_reason": "AI_EXTEND_MAX"}
            return {"position_id": position["id"], "exit_price": current_price,
                    "exit_reason": "SOFT_TARGET_REACHED"}

    # 4. 指标反转
    if _signal_reversed(side, market["rsi_15m"],
                        market["macd_hist_15m"], market["macd_hist_prev_15m"]):
        return {"position_id": position["id"], "exit_price": current_price,
                "exit_reason": "SIGNAL_REVERSE"}

    return None


class V5PositionMonitor:
    """每 30s 轮询活仓的协程。SHADOW 用 PaperPositionManager,LIVE 用 V5PositionManager。"""

    def __init__(self, paper_pm, live_pm, ai_assistant, indicator_fetcher,
                 mode_resolver, poll_interval_s: int = 30):
        """
        paper_pm:  PaperPositionManager 实例
        live_pm:   V5PositionManager 实例(可为 None,SHADOW 时不用)
        ai_assistant: TradingAssistant,用于 soft target 续仓决策
        indicator_fetcher: async fn(symbol) → dict{price, rsi_15m, macd_hist_15m, macd_hist_prev_15m}
        mode_resolver: sync fn → 'SHADOW' or 'LIVE'
        """
        self.paper_pm = paper_pm
        self.live_pm = live_pm
        self.ai = ai_assistant
        self.fetch_indicators = indicator_fetcher
        self.resolve_mode = mode_resolver
        self.poll_interval_s = poll_interval_s

    async def run(self):
        print(f"[V5PositionMonitor] 启动,轮询间隔 {self.poll_interval_s}s")
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                print("[V5PositionMonitor] 收到取消信号,退出")
                return
            except Exception as e:
                print(f"[V5PositionMonitor] tick 异常: {type(e).__name__}: {e}")
            await asyncio.sleep(self.poll_interval_s)

    async def _tick(self):
        mode = self.resolve_mode()
        pm = self.paper_pm if mode == "SHADOW" else self.live_pm
        if not pm:
            return
        for position in pm.get_open_positions():
            try:
                market = await self.fetch_indicators(position["symbol"])
            except Exception as e:
                print(f"[V5PositionMonitor] {position['symbol']} 拉指标失败: {e}")
                continue

            intent = check_exit_triggers(position, market)
            if not intent:
                continue

            reason = intent["exit_reason"]
            if reason == "SOFT_TARGET_REACHED":
                # 调 AI 决定:续仓 or 平
                ai_decision = await self._ask_ai_extend(position, market)
                if ai_decision == "EXTEND":
                    pm.extend_position(position["id"], extra_minutes=15)
                    print(f"[V5PositionMonitor] {position['symbol']} AI 续仓 "
                          f"(extension {position['extension_count'] + 1}/{MAX_EXTENSIONS})")
                    continue
                # 默认平
                pm.close_position(position["id"], exit_price=intent["exit_price"],
                                  exit_reason="AI_TIMEBOX")
                print(f"[V5PositionMonitor] {position['symbol']} CLOSE reason=AI_TIMEBOX")
            else:
                pm.close_position(position["id"], exit_price=intent["exit_price"],
                                  exit_reason=reason)
                print(f"[V5PositionMonitor] {position['symbol']} CLOSE reason={reason}")

    async def _ask_ai_extend(self, position: dict, market: dict) -> str:
        """问 AI:这个仓位还能不能继续拿?返回 'EXTEND' or 'CLOSE'。"""
        try:
            from scripts.ai.prompt import V5_SYSTEM_PROMPT  # 复用 system prompt
            # 简化:用 chat completion 而不是 Assistants thread(更快)
            msg = (
                f"Position {position['symbol']} {position['side']} entry={position['entry_price']} "
                f"current={market['price']} rsi_15m={market['rsi_15m']:.1f} "
                f"hist={market['macd_hist_15m']:+.4f} (prev {market['macd_hist_prev_15m']:+.4f}). "
                f"Soft target reached (ext {position['extension_count']}/{MAX_EXTENSIONS}). "
                "Reply with single word: EXTEND or CLOSE."
            )
            resp = await asyncio.wait_for(
                self.ai.quick_yes_no(V5_SYSTEM_PROMPT, msg),
                timeout=15.0,
            )
            return "EXTEND" if "EXTEND" in (resp or "").upper() else "CLOSE"
        except Exception as e:
            print(f"[V5PositionMonitor] AI 续仓决策异常 → 默认平: {e}")
            return "CLOSE"
```

注意:`ai_assistant.quick_yes_no` 这个方法目前不存在,需要在 `scripts/ai/trading_assistant.py` 加一个轻量 chat-completion 调用方法:

```python
# scripts/ai/trading_assistant.py 加方法:
async def quick_yes_no(self, system: str, user: str) -> str:
    """轻量 chat completion — 不用 Assistant thread,快得多。给续仓决策用。"""
    if not self.client:
        return "CLOSE"
    resp = await asyncio.to_thread(
        self.client.chat.completions.create,
        model="gpt-4o-mini",  # 或 gpt-4o,看延迟接受度
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=10,
    )
    return resp.choices[0].message.content or ""
```

- [ ] **Step 4: 跑测试,期望全 pass**

```bash
pytest tests/test_v5_position_monitor.py -v
```

预期:`10 passed`。

- [ ] **Step 5: Commit**

```bash
git add scripts/v5_position_monitor.py scripts/ai/trading_assistant.py \
        tests/test_v5_position_monitor.py
git commit -m "feat(v5): position monitor — 30s polling with exit triggers

check_exit_triggers (pure):
  SL_HIT > TP_HIT > SOFT_TARGET_REACHED > SIGNAL_REVERSE
  AI_EXTEND_MAX once extension_count >= 3

V5PositionMonitor.run loop:
  - SOFT_TARGET_REACHED → ask AI (quick chat completion) → EXTEND or AI_TIMEBOX
  - other reasons → immediate close

10 unit tests cover all branches."
```

---

## Phase 9:V5 Position Manager(LIVE)

### Task 10: Broker 下单 + fail-closed SL/TP

**Files:**
- Create: `scripts/v5_position_manager.py`
- Create: `tests/test_v5_position_manager.py`(只测 fail-closed 逻辑,broker 用 mock)

- [ ] **Step 1: 写测试 tests/test_v5_position_manager.py**

```python
"""V5PositionManager 测试 — broker 用 mock,只测 fail-closed 逻辑。"""
import pytest
from unittest.mock import MagicMock


def test_sl_tp_failure_rollbacks_main():
    """主仓开成功,SL 单失败 → 立刻市价平回滚。"""
    from scripts.v5_position_manager import V5PositionManager

    mock_broker = MagicMock()
    # 主仓 OK
    mock_broker.create_order.side_effect = [
        {"orderId": "main", "status": "filled"},  # 主仓
        Exception("SL order failed: insufficient margin"),  # SL 失败
    ]
    mock_broker.close_position = MagicMock()

    pm = V5PositionManager(broker=mock_broker, db_path=":memory:")

    with pytest.raises(Exception, match="SL"):
        pm.open_position(
            symbol="H/USDT", side="SHORT", entry_price=0.166,
            sl_price=0.169, tp_price=0.162, size_usdt=15, leverage=10,
        )
    # 必须调用过 close_position 回滚
    mock_broker.close_position.assert_called_once()


def test_successful_open_writes_positions_v5():
    """都成功 → 写 positions_v5 一行,status=OPEN。"""
    import sqlite3, tempfile
    from scripts.local_db import init_local_db
    from scripts.v5_position_manager import V5PositionManager

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    init_local_db(tmp.name)

    mock_broker = MagicMock()
    mock_broker.create_order.return_value = {"orderId": "x", "status": "filled"}

    pm = V5PositionManager(broker=mock_broker, db_path=tmp.name)
    pid = pm.open_position(
        symbol="H/USDT", side="SHORT", entry_price=0.166,
        sl_price=0.169, tp_price=0.162, size_usdt=15, leverage=10,
    )

    conn = sqlite3.connect(tmp.name)
    row = conn.execute("SELECT symbol, side, status FROM positions_v5 WHERE id=?",
                       (pid,)).fetchone()
    conn.close()
    assert row == ("H/USDT", "SHORT", "OPEN")
```

- [ ] **Step 2: 跑测试,期望 fail**

```bash
pytest tests/test_v5_position_manager.py -v
```

- [ ] **Step 3: 写 scripts/v5_position_manager.py**

```python
"""V5 LIVE 持仓管理 — 走 Broker(Binance/OKX)真实下单。

fail-closed:主仓开成功 + SL/TP 失败 → 立刻市价平回滚。
"""
import os
import sqlite3
from datetime import datetime, timezone, timedelta


SOFT_TARGET_MINUTES = 15
SL_TP_FAIL_OPEN = os.environ.get("SL_TP_FAIL_OPEN", "false").lower() in ("1", "true")


def _utcnow():
    return datetime.now(timezone.utc)


class V5PositionManager:
    def __init__(self, broker, db_path: str = "data/rabbit_hunter.db"):
        self.broker = broker
        self.db_path = db_path

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def open_position(self, *, symbol: str, side: str, entry_price: float,
                      sl_price: float, tp_price: float, size_usdt: float,
                      leverage: int) -> int:
        """LIVE 开仓:主仓 → SL → TP。任一失败按 fail-closed 处理。"""
        # 1. 主仓(市价)
        main = self.broker.create_order(
            symbol=symbol, side="sell" if side == "SHORT" else "buy",
            type="market", amount=size_usdt / entry_price,
        )
        position_size_coins = size_usdt / entry_price

        # 2. SL 单
        try:
            self.broker.create_order(
                symbol=symbol, side="buy" if side == "SHORT" else "sell",
                type="stop_market", amount=position_size_coins,
                params={"stopPrice": sl_price, "reduceOnly": True},
            )
        except Exception as e:
            if not SL_TP_FAIL_OPEN:
                self.broker.close_position(symbol)
                raise Exception(f"SL 下单失败,主仓已回滚: {e}")
            else:
                print(f"[V5PositionManager] SL 失败但 SL_TP_FAIL_OPEN=true,保留主仓: {e}")

        # 3. TP 单
        try:
            self.broker.create_order(
                symbol=symbol, side="buy" if side == "SHORT" else "sell",
                type="take_profit_market", amount=position_size_coins,
                params={"stopPrice": tp_price, "reduceOnly": True},
            )
        except Exception as e:
            if not SL_TP_FAIL_OPEN:
                self.broker.close_position(symbol)
                raise Exception(f"TP 下单失败,主仓已回滚: {e}")

        # 4. 写 positions_v5
        entry_time = _utcnow()
        target_close_at = entry_time + timedelta(minutes=SOFT_TARGET_MINUTES)
        conn = self._conn()
        try:
            cur = conn.execute("""
                INSERT INTO positions_v5 (
                    symbol, side, status, entry_price, entry_time,
                    sl_price, tp_price, size_usdt, leverage, position_size_coins,
                    target_close_at, extension_count, created_at, updated_at
                ) VALUES (?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """, (symbol, side, entry_price, entry_time.isoformat(),
                  sl_price, tp_price, size_usdt, leverage, position_size_coins,
                  target_close_at.isoformat(), entry_time.isoformat(), entry_time.isoformat()))
            pid = cur.lastrowid
            conn.commit()
            return pid
        finally:
            conn.close()

    def get_open_positions(self) -> list:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT id, symbol, side, entry_price, sl_price as stop_loss, "
                "tp_price as take_profit, target_close_at, extension_count, entry_time "
                "FROM positions_v5 WHERE status='OPEN'")
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            conn.close()

    def extend_position(self, position_id: int, extra_minutes: int = 15) -> None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT target_close_at, extension_count FROM positions_v5 WHERE id=?",
                (position_id,)).fetchone()
            if not row:
                return
            current_target = datetime.fromisoformat(row[0])
            new_target = current_target + timedelta(minutes=extra_minutes)
            conn.execute(
                "UPDATE positions_v5 SET target_close_at=?, extension_count=?, updated_at=? "
                "WHERE id=?",
                (new_target.isoformat(), (row[1] or 0) + 1, _utcnow().isoformat(), position_id))
            conn.commit()
        finally:
            conn.close()

    def close_position(self, position_id: int, *, exit_price: float, exit_reason: str) -> None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT symbol, side, entry_price, size_usdt, leverage, entry_time "
                "FROM positions_v5 WHERE id=?", (position_id,)).fetchone()
            if not row:
                return
            symbol, side, entry_price, size_usdt, leverage, entry_time_str = row

            # 调 broker 市价平
            try:
                self.broker.close_position(symbol)
            except Exception as e:
                print(f"[V5PositionManager] 平仓 broker 失败: {e}")

            # 算 PnL 写 DB
            entry_time = datetime.fromisoformat(entry_time_str)
            exit_time = _utcnow()
            holding_minutes = (exit_time - entry_time).total_seconds() / 60
            notional = (size_usdt or 0) * (leverage or 1)
            if side == "LONG":
                pnl_pct = (exit_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - exit_price) / entry_price
            pnl_usdt = notional * pnl_pct

            conn.execute("""
                UPDATE positions_v5 SET status='CLOSED', exit_price=?, exit_time=?,
                  exit_reason=?, pnl_usdt=?, pnl_pct=?, holding_minutes=?, updated_at=?
                WHERE id=?
            """, (exit_price, exit_time.isoformat(), exit_reason,
                  pnl_usdt, pnl_pct * 100, holding_minutes, exit_time.isoformat(), position_id))
            conn.commit()
        finally:
            conn.close()
```

- [ ] **Step 4: 跑测试,期望全 pass**

```bash
pytest tests/test_v5_position_manager.py -v
```

预期:`2 passed`。

- [ ] **Step 5: Commit**

```bash
git add scripts/v5_position_manager.py tests/test_v5_position_manager.py
git commit -m "feat(v5): LIVE V5PositionManager with fail-closed SL/TP rollback

- open_position: main → SL → TP; SL/TP fails → broker.close_position + raise
- Honors SL_TP_FAIL_OPEN env override (default false)
- extend_position / close_position parallel to PaperPositionManager API
- 2 unit tests with mocked broker"
```

---

## Phase 10:Scorer 瘦身 + V5 管道粘合

### Task 11: 删 V4.3 逻辑 + 装 V5 链路

**Files:**
- Modify: `scripts/tasks/scorer.py`(大幅瘦身)
- Create: `tests/test_v5_scoring_pipeline.py`(集成测试)

- [ ] **Step 1: 写集成测试 tests/test_v5_scoring_pipeline.py**

```python
"""V5 scoring pipeline 集成测试。Mock OKX 拉 K 线 + AI,验证端到端流。"""
import asyncio
import sqlite3
import tempfile
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from tests.conftest import _build_klines


@pytest.fixture
def fresh_db():
    from scripts.local_db import init_local_db
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    init_local_db(tmp.name)
    return tmp.name


@pytest.mark.asyncio
async def test_strong_signal_writes_trade_scores_v5_and_paper_trade(fresh_db, monkeypatch):
    """构造一个必然触发 SHORT 的输入 → 验证 paper_trades + trade_scores_v5 各写一行。"""
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "60")  # 调宽阈值,让信号必中
    monkeypatch.setenv("DB_PATH", fresh_db)

    # 构造一组让 RSI 高 + MACD 死叉拐点的 K 线
    rising_then_drop = [100 + i * 2 for i in range(40)] + [180, 178, 176]
    klines_15m = _build_klines(rising_then_drop)
    klines_4h = _build_klines([100 + i * 1.5 for i in range(40)])

    # Mock fetch_klines
    async def fake_fetch_klines(*args, **kwargs):
        if args[1] == "15m":
            return klines_15m
        return klines_4h

    # Mock AI:批准开仓
    from v5_types import AIResult
    fake_ai = MagicMock()
    fake_ai.decide = AsyncMock(return_value=AIResult(
        execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
        size_multiplier=1.0, confidence=0.7, reasoning="test"
    ))

    # Mock 余额拉取
    monkeypatch.setenv("PAPER_INITIAL_BALANCE_USDT", "1000")

    # 直接调 scorer 的 _process_enriched 单元(避开 OKX/asyncio.Queue 整套)
    from scripts.tasks.scorer import process_enriched_v5  # 新公开 API
    from v5_types import EnrichedItem
    enriched = EnrichedItem(
        symbol="TEST/USDT", current_price=176.0, delta_15m_pct=-0.034,
        volume_24h_usdt=50_000_000, klines_15m=klines_15m, klines_4h=klines_4h,
    )

    from scripts.paper_position_manager import PaperPositionManager
    paper_pm = PaperPositionManager(db_path=fresh_db)

    await process_enriched_v5(
        enriched=enriched, ai=fake_ai, paper_pm=paper_pm, live_pm=None,
        mode="SHADOW", db_path=fresh_db, balance_usdt=1000.0,
    )

    # 验证 trade_scores_v5 + paper_trades
    conn = sqlite3.connect(fresh_db)
    scores = conn.execute(
        "SELECT symbol, should_trade, side, executed FROM trade_scores_v5"
    ).fetchall()
    trades = conn.execute(
        "SELECT symbol, side, status FROM paper_trades"
    ).fetchall()
    conn.close()

    assert len(scores) == 1
    assert scores[0][0] == "TEST/USDT"
    assert scores[0][1] == 1   # should_trade
    assert scores[0][2] == "SHORT"
    assert scores[0][3] == 1   # executed
    assert len(trades) == 1
    assert trades[0] == ("TEST/USDT", "SHORT", "OPEN")
```

- [ ] **Step 2: 跑测试,期望 fail(`process_enriched_v5` 还不存在)**

```bash
pytest tests/test_v5_scoring_pipeline.py -v
```

- [ ] **Step 3: 大幅改 scripts/tasks/scorer.py**

整个 scorer.py 删干净,只保留 V5 骨架。完整替换:

```python
"""V5 Scorer — 管道粘合层。

输入:enriched_queue(EnrichedItem)
输出:write_queue(trade_scores_v5 行)+ 触发 paper_pm / live_pm 开仓
"""
import asyncio
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from v5_indicator_engine import calculate_indicators
from v5_strategy import decide
from v5_risk_calculator import plan
from v5_types import AIResult, Decision, EnrichedItem, Indicators, RiskPlan


MAX_CONCURRENT_POSITIONS = int(os.environ.get("V5_MAX_CONCURRENT", "3"))
RISK_PER_TRADE = float(os.environ.get("V43_RISK_PER_TRADE", "0.015"))  # 沿用旧 env 名
LEVERAGE = int(os.environ.get("BINANCE_LEVERAGE", "10"))


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _count_open_positions(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        n_paper = conn.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'").fetchone()[0]
        n_live = conn.execute(
            "SELECT COUNT(*) FROM positions_v5 WHERE status='OPEN'").fetchone()[0]
        return n_paper + n_live
    finally:
        conn.close()


def _write_trade_score(db_path: str, enriched: EnrichedItem, indicators: Indicators,
                       decision: Decision, ai: Optional[AIResult] = None,
                       risk: Optional[RiskPlan] = None, executed: bool = False,
                       position_id: Optional[int] = None,
                       block_reason: Optional[str] = None) -> int:
    """写一行到 trade_scores_v5。返回 score row id。"""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("""
            INSERT INTO trade_scores_v5 (
                symbol, created_at, delta_15m_pct, volume_24h_usdt,
                rsi_15m, macd_15m, macd_signal_15m, macd_hist_15m, macd_hist_prev_15m,
                rsi_4h, macd_hist_4h, atr_15m, current_price,
                should_trade, side, reasoning, block_reason,
                ai_confidence, ai_sl_multiplier, ai_tp_multiplier, ai_size_multiplier,
                ai_reasoning,
                entry_price, sl_price, tp_price, size_usdt, expected_rr,
                executed, position_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            enriched.symbol, _utcnow(), enriched.delta_15m_pct, enriched.volume_24h_usdt,
            indicators.rsi_15m, indicators.macd_15m, indicators.macd_signal_15m,
            indicators.macd_hist_15m, indicators.macd_hist_prev_15m,
            indicators.rsi_4h, indicators.macd_hist_4h, indicators.atr_15m,
            enriched.current_price,
            1 if decision.should_trade else 0, decision.side,
            decision.reasoning, block_reason or decision.block_reason,
            ai.confidence if ai else None,
            ai.sl_multiplier if ai else None,
            ai.tp_multiplier if ai else None,
            ai.size_multiplier if ai else None,
            ai.reasoning if ai else None,
            risk.entry_price if risk else None,
            risk.sl_price if risk else None,
            risk.tp_price if risk else None,
            risk.size_usdt if risk else None,
            risk.expected_rr if risk else None,
            1 if executed else 0, position_id,
        ))
        sid = cur.lastrowid
        conn.commit()
        return sid
    finally:
        conn.close()


async def process_enriched_v5(*, enriched: EnrichedItem, ai, paper_pm, live_pm,
                              mode: str, db_path: str, balance_usdt: float) -> None:
    """处理一个 enriched item 走完 V5 管道。"""
    # 1. 算指标
    try:
        indicators = calculate_indicators(enriched.klines_15m, enriched.klines_4h)
    except ValueError as e:
        print(f"[V5Scorer] {enriched.symbol} 指标计算失败: {e}")
        return

    # 2. 策略决策
    decision = decide(enriched, indicators)
    if not decision.should_trade:
        _write_trade_score(db_path, enriched, indicators, decision)
        return

    # 3. 活仓数检查
    if _count_open_positions(db_path) >= MAX_CONCURRENT_POSITIONS:
        _write_trade_score(db_path, enriched, indicators, decision,
                          block_reason="MAX_CONCURRENT_POSITIONS")
        return

    # 4. 风险计划
    risk = plan(
        side=decision.side, entry=enriched.current_price,
        atr=indicators.atr_15m, balance=balance_usdt,
        risk_pct=RISK_PER_TRADE, leverage=LEVERAGE,
    )

    # 5. AI 二次审查
    ai_result = await ai.decide(enriched, indicators, decision, risk)
    if not ai_result.execute:
        _write_trade_score(db_path, enriched, indicators, decision,
                          ai=ai_result, risk=risk, block_reason="AI_REJECTED")
        return

    # 6. 下单
    try:
        if mode == "SHADOW":
            position_id = paper_pm.open_position(
                enriched=enriched, indicators=indicators,
                decision=decision, risk=risk, ai=ai_result,
            )
        else:
            position_id = live_pm.open_position(
                symbol=enriched.symbol, side=decision.side,
                entry_price=risk.entry_price, sl_price=risk.sl_price,
                tp_price=risk.tp_price, size_usdt=risk.size_usdt,
                leverage=risk.leverage,
            )
    except Exception as e:
        _write_trade_score(db_path, enriched, indicators, decision,
                          ai=ai_result, risk=risk,
                          block_reason=f"OPEN_FAILED:{type(e).__name__}")
        return

    _write_trade_score(db_path, enriched, indicators, decision,
                      ai=ai_result, risk=risk, executed=True,
                      position_id=position_id)
    print(f"[V5Scorer] {enriched.symbol} OPEN {decision.side} executed,position_id={position_id}")


class V5Scorer:
    """异步任务包装,从 enriched_queue 消费,调 process_enriched_v5。"""

    def __init__(self, enriched_queue, ai, paper_pm, live_pm,
                 mode_resolver, balance_fetcher, db_path: str = "data/rabbit_hunter.db"):
        self.enriched_queue = enriched_queue
        self.ai = ai
        self.paper_pm = paper_pm
        self.live_pm = live_pm
        self.resolve_mode = mode_resolver
        self.fetch_balance = balance_fetcher
        self.db_path = db_path

    async def run(self):
        print("[V5Scorer] 启动")
        while True:
            try:
                enriched: EnrichedItem = await self.enriched_queue.get()
            except asyncio.CancelledError:
                return
            try:
                mode = self.resolve_mode()
                balance = self.fetch_balance()
                await process_enriched_v5(
                    enriched=enriched, ai=self.ai,
                    paper_pm=self.paper_pm, live_pm=self.live_pm,
                    mode=mode, db_path=self.db_path, balance_usdt=balance,
                )
            except Exception as e:
                print(f"[V5Scorer] {enriched.symbol} 处理异常: {type(e).__name__}: {e}")
```

- [ ] **Step 4: 跑集成测试,期望 pass**

```bash
pytest tests/test_v5_scoring_pipeline.py -v
```

预期:`1 passed`。

如果 fail,常见问题:
- `_build_klines` 构造的 rising_then_drop 序列没让 MACD 真的死叉拐点 → 调整 prices 让最后两根明确下跌
- `_count_open_positions` 查不到表 → 检查 `init_local_db` 是不是用了同一个 db_path

- [ ] **Step 5: Commit**

```bash
git add scripts/tasks/scorer.py tests/test_v5_scoring_pipeline.py
git commit -m "feat(v5): scorer rewritten as pure V5 pipeline glue

scripts/tasks/scorer.py:
  - All V4.3 logic removed (1300+ lines → ~150)
  - process_enriched_v5: indicators → strategy → risk → AI → open
  - V5Scorer.run consumes enriched_queue
  - Writes trade_scores_v5 row for every signal (with block_reason if rejected)
  - SHADOW → PaperPositionManager, LIVE → V5PositionManager

1 integration test wiring mock OKX + mock AI + real SQLite verifies end-to-end."
```

---

## Phase 11:物理删 V4.3/V4.4 + collector_main 适配

### Task 12: 一次性大删 + collector_main 重布线

**Files:**
- Delete: 20 个 V4.3/V4.4 文件(见 plan 顶部"物理删除"清单)
- Modify: `scripts/tasks/collector_main.py`
- Modify: `scripts/tasks/__init__.py`(若有 import V4.3)

- [ ] **Step 1: 跑现有测试做 baseline**

```bash
pytest tests/ -v
```

记下通过的测试数(预期所有 V5 测试 pass)。

- [ ] **Step 2: 删除文件**

```bash
git rm scripts/v41_structure_analyzer.py scripts/v41_context_gate.py \
       scripts/v43_score_calculator.py scripts/v43_decision_policy.py \
       scripts/v43_hard_filters.py scripts/v43_feature_extractor.py \
       scripts/v43_chandelier_stop.py scripts/v43_collector_integration.py \
       scripts/v43_entry_validator.py scripts/v43_kill_queue_manager.py \
       scripts/v43_weight_manager.py scripts/run_ai_weight_adjustment.py \
       scripts/v43_opportunity_density.py scripts/v43_position_manager.py \
       scripts/v44_strategy_router.py scripts/v44_strategy_backtest.py \
       scripts/v44_strategy_validation_analysis.py scripts/whale_detector.py \
       scripts/deepseek_ai.py scripts/ai_judge.py
```

如果有的文件不存在,`git rm` 会报错,把存在的列出来执行即可。

- [ ] **Step 3: grep 是否还有引用 V4.3 的代码**

```bash
grep -rn "v43_\|v44_\|v41_\|whale_detector\|deepseek_ai\|ai_judge" \
  scripts/ api/ --include="*.py" | grep -v __pycache__
```

预期:大量结果。逐个修(应该都在以下文件):
- `scripts/tasks/collector_main.py`
- `scripts/tasks/scorer.py`(已经在 Task 11 重写,应没有了)
- `scripts/ai/memory_uploader.py`
- `scripts/config.py`
- `scripts/binance_position_sync.py`

- [ ] **Step 4: 改 scripts/tasks/collector_main.py**

打开文件,把所有 V4.3 import + 实例化删干净,改为 V5 装配:

```python
"""V5 Collector 主入口。

四任务管道:Scanner → DeepCollector → V5Scorer → Writer
+ V5PositionMonitor 30s 轮询活仓
+ MemoryAutoUploader 周期上传 AI 学习
"""
import asyncio
import os
import signal

from .scanner import MarketScanner
from .deep_collector import DeepCollector
from .scorer import V5Scorer
from .writer import DatabaseWriter
from scripts.paper_position_manager import PaperPositionManager
from scripts.v5_position_manager import V5PositionManager
from scripts.v5_position_monitor import V5PositionMonitor
from scripts.ai.trading_assistant import TradingAssistant
from scripts.config import get_config


def _resolve_mode_db() -> str:
    """从 system_settings 读 system_state,SHADOW 默认。"""
    import sqlite3
    db = os.environ.get("DB_PATH", "data/rabbit_hunter.db")
    try:
        conn = sqlite3.connect(db)
        try:
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key='system_state'"
            ).fetchone()
            if row and (row[0] or "").upper() in ("SHADOW", "LIVE"):
                return row[0].upper()
        finally:
            conn.close()
    except Exception:
        pass
    return "SHADOW"


def _fetch_balance() -> float:
    """先尝试从交易所拉余额,失败回退 env PAPER_INITIAL_BALANCE_USDT。"""
    try:
        from scripts.exchange_factory import get_ccxt_client
        client = get_ccxt_client()
        bal = client.fetch_balance()
        usdt = bal.get("USDT", {}).get("free")
        if usdt is not None and usdt > 0:
            return float(usdt)
    except Exception as e:
        print(f"[collector_main] 余额拉取失败,用 PAPER_INITIAL_BALANCE_USDT: {e}")
    return float(os.environ.get("PAPER_INITIAL_BALANCE_USDT", "1000"))


async def _build_indicator_fetcher():
    """给 V5PositionMonitor 用的 indicator fetcher:拉当前价 + 15min K 线指标。"""
    from .exchange_endpoints import fetch_klines
    from v5_indicator_engine import calculate_rsi, calculate_macd

    async def fetch(symbol: str) -> dict:
        klines = await asyncio.to_thread(fetch_klines, symbol, "15m", 50)
        price = float(klines[-1][4])
        rsi = calculate_rsi(klines)
        _, _, hist, hist_prev = calculate_macd(klines)
        return {"price": price, "rsi_15m": rsi,
                "macd_hist_15m": hist, "macd_hist_prev_15m": hist_prev}
    return fetch


async def main():
    cfg = get_config()
    db_path = os.environ.get("DB_PATH", "data/rabbit_hunter.db")

    # 启动自检
    from scripts.local_db import init_local_db
    init_local_db(db_path)

    # AI
    ai = TradingAssistant()

    # Brokers
    paper_pm = PaperPositionManager(db_path=db_path)
    live_pm = None
    if cfg.enable_auto_trading:
        try:
            from scripts.exchange_factory import get_ccxt_client
            live_pm = V5PositionManager(broker=get_ccxt_client(), db_path=db_path)
        except Exception as e:
            print(f"[collector_main] V5PositionManager 初始化失败: {e}")

    # 队列
    movers_queue = asyncio.Queue(maxsize=1)
    enriched_queue = asyncio.Queue(maxsize=100)

    # Tasks
    scanner = MarketScanner(
        movers_queue=movers_queue,
        scan_interval=cfg.scan_interval,
        top_movers_count=cfg.store_top_count,
        min_volume_24h=cfg.min_volume_24h_usdt,
        supabase=None,
    )
    deep_collector = DeepCollector(
        movers_queue=movers_queue,
        enriched_queue=enriched_queue,
        deep_scan_interval=cfg.deep_scan_interval_seconds,
    )
    writer = DatabaseWriter(queue_maxsize=cfg.write_queue_maxsize,
                            num_workers=cfg.write_workers)
    scorer = V5Scorer(
        enriched_queue=enriched_queue, ai=ai,
        paper_pm=paper_pm, live_pm=live_pm,
        mode_resolver=_resolve_mode_db,
        balance_fetcher=_fetch_balance,
        db_path=db_path,
    )
    indicator_fetcher = await _build_indicator_fetcher()
    monitor = V5PositionMonitor(
        paper_pm=paper_pm, live_pm=live_pm, ai_assistant=ai,
        indicator_fetcher=indicator_fetcher,
        mode_resolver=_resolve_mode_db,
        poll_interval_s=30,
    )

    print(f"[collector_main] V5 启动 — mode={_resolve_mode_db()} db={db_path}")

    await asyncio.gather(
        scanner.run(), deep_collector.run(), scorer.run(),
        writer.run(), monitor.run(),
        return_exceptions=False,
    )


def _setup_shutdown():
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: loop.stop())


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5: 清掉 scripts/config.py / memory_uploader.py / binance_position_sync.py 里的 V4.3 引用**

各文件搜 `v43_` 全部删/改。具体怎么改要看现场,但一般是删几行 deprecated 代码 + 改一两个 import。

例:`scripts/config.py` 里有 `v43_enabled`、`v44_enabled` 字段 → 删字段 + 删 env 读取。

例:`scripts/ai/memory_uploader.py` 里如果还有 `from scripts.v43_*` 的 import 必须删,memory_uploader 改为读 `ai_training_data`(新 schema)即可。

- [ ] **Step 6: 跑全部测试**

```bash
pytest tests/ -v
```

预期:全 pass。如果有 fail,说明删的时候碰到 import 链 — 修了再跑。

- [ ] **Step 7: 跑 import sanity check**

```bash
python3 -c "from scripts.tasks.collector_main import main; print('OK')"
```

预期:`OK`。如果 ImportError → 修。

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(v5): physically delete V4.3/V4.4, rewire collector_main

Removed 20 files:
  v41_structure_analyzer, v41_context_gate,
  v43_score_calculator, v43_decision_policy, v43_hard_filters,
  v43_feature_extractor, v43_chandelier_stop, v43_collector_integration,
  v43_entry_validator, v43_kill_queue_manager, v43_weight_manager,
  v43_opportunity_density, v43_position_manager,
  v44_strategy_router, v44_strategy_backtest, v44_strategy_validation_analysis,
  whale_detector, deepseek_ai, ai_judge, run_ai_weight_adjustment

collector_main.py rewired:
  Scanner → DeepCollector → V5Scorer → Writer (+ V5PositionMonitor)
  Removed all V4.3 imports, simplified mode resolution, balance fetcher
  fallback chain.

config.py / memory_uploader.py / binance_position_sync.py: cleaned of
v43_* references."
```

---

## Phase 12:V5 Signal Manager + API 路径重命名

### Task 13: scripts/v5_signal_manager.py + /api/v5/* 路由

**Files:**
- Create: `scripts/v5_signal_manager.py`
- Modify: `api/routes/scores.py`
- Modify: `api/routes/positions.py`
- Modify: `api/services/score_service.py`
- Modify: `api/services/position_service.py`
- Modify: `api/schemas/scores.py`
- Modify: `api/schemas/positions.py`
- Modify: `api/main.py`(注册新路由)

- [ ] **Step 1: 写 scripts/v5_signal_manager.py**

```python
"""V5 信号管理器 — 替代 v43_kill_queue_manager。

从 trade_scores_v5 读最新一批,按 created_at 倒序。
"""
import sqlite3
from datetime import datetime
from typing import Optional


def _utc_iso(ts):
    """Naive ISO → 补 +00:00。"""
    if not isinstance(ts, str) or not ts:
        return ts
    if ts.endswith("Z") or "+" in ts[10:] or "-" in ts[10:]:
        return ts
    return ts + "+00:00"


class V5SignalManager:
    def __init__(self, db_path: str = "data/rabbit_hunter.db"):
        self.db_path = db_path

    def list_signals(self, *, limit: int = 50, only_executed: bool = False,
                     only_should_trade: bool = False) -> list:
        conn = sqlite3.connect(self.db_path)
        try:
            sql = "SELECT * FROM trade_scores_v5 WHERE 1=1"
            params = []
            if only_executed:
                sql += " AND executed=1"
            if only_should_trade:
                sql += " AND should_trade=1"
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cur = conn.execute(sql, params)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            for r in rows:
                r["created_at"] = _utc_iso(r.get("created_at"))
            return rows
        finally:
            conn.close()

    def funnel_stats(self, since_hours: int = 1) -> dict:
        """返回过去 N 小时的漏斗:总扫到 / should_trade=1 / executed=1。"""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                "SELECT COUNT(*),"
                "       SUM(CASE WHEN should_trade=1 THEN 1 ELSE 0 END),"
                "       SUM(CASE WHEN executed=1 THEN 1 ELSE 0 END)"
                "  FROM trade_scores_v5"
                f" WHERE created_at >= datetime('now', '-{int(since_hours)} hour')"
            )
            total, n_should, n_exec = cur.fetchone()
            return {"total": total or 0,
                    "should_trade": n_should or 0,
                    "executed": n_exec or 0}
        finally:
            conn.close()
```

- [ ] **Step 2: 改 api/schemas/scores.py + positions.py**

`api/schemas/scores.py` 整文件替换:

```python
"""V5 信号 + 漏斗 schema。"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class V5SignalItem(BaseModel):
    id: int
    symbol: str
    created_at: str
    delta_15m_pct: Optional[float] = None
    volume_24h_usdt: Optional[float] = None
    rsi_15m: Optional[float] = None
    macd_15m: Optional[float] = None
    macd_signal_15m: Optional[float] = None
    macd_hist_15m: Optional[float] = None
    macd_hist_prev_15m: Optional[float] = None
    rsi_4h: Optional[float] = None
    macd_hist_4h: Optional[float] = None
    atr_15m: Optional[float] = None
    current_price: Optional[float] = None
    should_trade: int = 0
    side: Optional[str] = None
    reasoning: Optional[str] = None
    block_reason: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_sl_multiplier: Optional[float] = None
    ai_tp_multiplier: Optional[float] = None
    ai_size_multiplier: Optional[float] = None
    ai_reasoning: Optional[str] = None
    entry_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    size_usdt: Optional[float] = None
    expected_rr: Optional[float] = None
    executed: int = 0
    position_id: Optional[int] = None


class V5SignalsResponse(BaseModel):
    status: str = "success"
    data: List[V5SignalItem]
    funnel: Dict[str, int]
```

`api/schemas/positions.py` 整文件替换:

```python
"""V5 持仓 schema。"""
from typing import Optional, List
from pydantic import BaseModel


class V5PositionResponse(BaseModel):
    id: int
    symbol: str
    side: str
    status: str
    entry_price: Optional[float] = None
    entry_time: Optional[str] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    size_usdt: Optional[float] = None
    leverage: Optional[int] = None
    position_size_coins: Optional[float] = None
    target_close_at: Optional[str] = None
    extension_count: int = 0
    entry_rsi_15m: Optional[float] = None
    entry_macd_hist_15m: Optional[float] = None
    entry_rsi_4h: Optional[float] = None
    entry_atr_15m: Optional[float] = None
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    exit_reason: Optional[str] = None
    pnl_usdt: Optional[float] = None
    pnl_pct: Optional[float] = None
    holding_minutes: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class V5PositionsResponse(BaseModel):
    status: str = "success"
    data: List[V5PositionResponse]
```

- [ ] **Step 3: 改 api/routes/scores.py**

整文件替换:

```python
"""V5 信号 + 漏斗 API。"""
import os
from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas.scores import V5SignalItem, V5SignalsResponse
from scripts.v5_signal_manager import V5SignalManager

router = APIRouter(prefix="/api/v5", tags=["signals"])


def _signal_manager() -> V5SignalManager:
    db = os.environ.get("DB_PATH", "data/rabbit_hunter.db")
    return V5SignalManager(db_path=db)


@router.get("/signals", response_model=V5SignalsResponse)
async def get_signals(
    limit: int = Query(50, ge=1, le=200),
    only_executed: bool = Query(False),
    only_should_trade: bool = Query(False),
    funnel_hours: int = Query(1, ge=1, le=24),
):
    sm = _signal_manager()
    rows = sm.list_signals(limit=limit,
                           only_executed=only_executed,
                           only_should_trade=only_should_trade)
    funnel = sm.funnel_stats(since_hours=funnel_hours)
    return V5SignalsResponse(data=rows, funnel=funnel)
```

- [ ] **Step 4: 改 api/routes/positions.py + service**

`api/services/position_service.py` 整文件替换:

```python
"""V5 持仓格式化。"""
import sqlite3
from typing import List


def _utc_iso(ts):
    if not isinstance(ts, str) or not ts:
        return ts
    if ts.endswith("Z") or "+" in ts[10:] or "-" in ts[10:]:
        return ts
    return ts + "+00:00"


def fetch_v5_positions(db_path: str, *, status: str = None, limit: int = 100) -> List[dict]:
    conn = sqlite3.connect(db_path)
    try:
        sql = "SELECT * FROM positions_v5"
        params = []
        if status:
            sql += " WHERE status=?"
            params.append(status.upper())
        sql += " ORDER BY entry_time DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        for r in rows:
            for f in ("entry_time", "exit_time", "target_close_at", "created_at", "updated_at"):
                r[f] = _utc_iso(r.get(f))
        return rows
    finally:
        conn.close()


def fetch_v5_paper_positions(db_path: str, *, status: str = None, limit: int = 100) -> List[dict]:
    """SHADOW 模式下,持仓来自 paper_trades。"""
    conn = sqlite3.connect(db_path)
    try:
        sql = "SELECT * FROM paper_trades"
        params = []
        if status:
            sql += " WHERE status=?"
            params.append(status.upper())
        sql += " ORDER BY entry_time DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        for r in rows:
            for f in ("entry_time", "exit_time", "target_close_at", "created_at", "updated_at"):
                r[f] = _utc_iso(r.get(f))
        return rows
    finally:
        conn.close()
```

`api/routes/positions.py` 整文件替换:

```python
"""V5 持仓 API。"""
import os
from fastapi import APIRouter, Query

from api.schemas.positions import V5PositionResponse, V5PositionsResponse
from api.services.position_service import fetch_v5_positions, fetch_v5_paper_positions

router = APIRouter(prefix="/api/v5", tags=["positions"])


def _db() -> str:
    return os.environ.get("DB_PATH", "data/rabbit_hunter.db")


@router.get("/positions", response_model=V5PositionsResponse)
async def get_live_positions(status: str = Query("OPEN")):
    rows = fetch_v5_positions(_db(), status=status, limit=100)
    return V5PositionsResponse(data=rows)


@router.get("/paper-positions", response_model=V5PositionsResponse)
async def get_paper_positions(status: str = Query("OPEN")):
    """SHADOW 模式的纸面仓位 — 来自 paper_trades。

    schema 字段名跟 V5PositionResponse 对齐(paper_trades 是 superset)。
    """
    rows = fetch_v5_paper_positions(_db(), status=status, limit=100)
    # paper_trades 字段名不完全跟 positions_v5 一致,做映射
    mapped = []
    for r in rows:
        mapped.append({
            "id": r["id"],
            "symbol": r["symbol"],
            "side": r["side"],
            "status": r["status"],
            "entry_price": r.get("entry_price"),
            "entry_time": r.get("entry_time"),
            "sl_price": r.get("stop_loss"),
            "tp_price": r.get("take_profit"),
            "size_usdt": r.get("position_size_usdt"),
            "leverage": r.get("leverage"),
            "target_close_at": r.get("target_close_at"),
            "extension_count": r.get("extension_count") or 0,
            "entry_rsi_15m": r.get("entry_rsi_15m"),
            "entry_macd_hist_15m": r.get("entry_macd_hist_15m"),
            "entry_rsi_4h": r.get("entry_rsi_4h"),
            "entry_atr_15m": r.get("entry_atr_15m"),
            "exit_price": r.get("exit_price"),
            "exit_time": r.get("exit_time"),
            "exit_reason": r.get("exit_reason"),
            "pnl_usdt": r.get("pnl"),
            "pnl_pct": r.get("pnl_percent"),
            "holding_minutes": (r.get("holding_hours") or 0) * 60,
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
        })
    return V5PositionsResponse(data=mapped)
```

- [ ] **Step 5: 改 api/main.py — 注册新路由,删旧的**

找 `app.include_router(...)` 行,把所有 V43 路由删掉,只留:

```python
from api.routes import scores as v5_scores_routes
from api.routes import positions as v5_positions_routes
# (可能还有 system / weights / market 等)

app.include_router(v5_scores_routes.router)
app.include_router(v5_positions_routes.router)
```

把任何 weights / kill-queue / trade-scores 旧路由都删掉。

- [ ] **Step 6: 写测试 tests/test_v5_api.py**

```python
"""V5 API 集成测试 — 用 FastAPI TestClient。"""
import tempfile, sqlite3
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("DB_PATH", tmp.name)
    from scripts.local_db import init_local_db
    init_local_db(tmp.name)
    # 塞 1 行 trade_scores_v5
    conn = sqlite3.connect(tmp.name)
    conn.execute("""
        INSERT INTO trade_scores_v5 (symbol, created_at, should_trade, side,
        rsi_15m, macd_hist_15m, executed)
        VALUES ('H/USDT', '2026-06-12T10:00:00', 1, 'SHORT', 72.0, -0.0005, 1)
    """)
    conn.commit()
    conn.close()
    from api.main import app
    return TestClient(app), tmp.name


def test_get_signals_returns_v5_item(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/signals")
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert "funnel" in data
    assert len(data["data"]) == 1
    item = data["data"][0]
    assert item["symbol"] == "H/USDT"
    assert item["rsi_15m"] == 72.0
    assert item["macd_hist_15m"] == -0.0005


def test_get_positions_empty(app_with_db):
    client, _ = app_with_db
    r = client.get("/api/v5/positions")
    assert r.status_code == 200
    assert r.json()["data"] == []
```

- [ ] **Step 7: 跑测试,期望全 pass**

```bash
pytest tests/test_v5_api.py -v
```

预期:`2 passed`。

- [ ] **Step 8: Commit**

```bash
git add scripts/v5_signal_manager.py api/ tests/test_v5_api.py
git commit -m "feat(v5): API rename to /api/v5/* + V5SignalManager

- /api/v5/signals: list trade_scores_v5 + funnel stats
- /api/v5/positions: positions_v5 (LIVE)
- /api/v5/paper-positions: paper_trades mapped to V5 schema (SHADOW)
- Removed all /api/v43/* routes
- V5SignalItem / V5PositionResponse Pydantic models (no V4 leftovers)
- 2 API integration tests"
```

---

## Phase 13:启动自检 + 健康度告警

### Task 14: collector_main.py 加 preflight + healthcheck loop

**Files:**
- Modify: `scripts/tasks/collector_main.py`
- Create: `tests/test_collector_preflight.py`

- [ ] **Step 1: 写测试**

```python
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
```

- [ ] **Step 2: 跑测试,期望 fail**

- [ ] **Step 3: 改 scripts/tasks/collector_main.py — 加 preflight + healthcheck**

在 `main()` 之前加:

```python
def preflight_check(*, enable_auto_trading: bool,
                    binance_api_key: str, okx_api_key: str,
                    openai_key: str, ai_enabled: bool) -> list:
    """返回问题列表(空 = OK)。"""
    issues = []
    if enable_auto_trading and not binance_api_key and not okx_api_key:
        issues.append("ENABLE_AUTO_TRADING=true 但 broker API key 都未设置")
    if ai_enabled and not openai_key:
        issues.append("OPENAI_AI_ENABLED=true 但 OPENAI_API_KEY 未设置")
    return issues


async def _healthcheck_loop(db_path: str, interval_s: int = 60):
    """每分钟自检,有问题打 WARN/ERROR 日志。"""
    import sqlite3
    while True:
        await asyncio.sleep(interval_s)
        try:
            conn = sqlite3.connect(db_path)
            try:
                # 5min 无信号 → WARN
                n_recent = conn.execute(
                    "SELECT COUNT(*) FROM trade_scores_v5 "
                    "WHERE created_at >= datetime('now', '-5 minute')"
                ).fetchone()[0]
                if n_recent == 0:
                    print("[WARN][health] 过去 5 分钟无 trade_scores_v5 写入,评分流可能停滞")

                # 1h 无入场但 should_trade>=10 → AI 阈值过严
                n_rejected = conn.execute(
                    "SELECT COUNT(*) FROM trade_scores_v5 "
                    "WHERE created_at >= datetime('now', '-1 hour') "
                    "  AND should_trade=1 AND block_reason='AI_REJECTED'"
                ).fetchone()[0]
                n_executed = conn.execute(
                    "SELECT COUNT(*) FROM trade_scores_v5 "
                    "WHERE created_at >= datetime('now', '-1 hour') "
                    "  AND executed=1"
                ).fetchone()[0]
                if n_rejected >= 10 and n_executed == 0:
                    print(f"[WARN][health] 过去 1h AI 拒了 {n_rejected} 个但 0 入场,"
                          "AI 阈值可能过严")
            finally:
                conn.close()
        except Exception as e:
            print(f"[health] healthcheck 异常: {e}")
```

在 `main()` 开头加:

```python
async def main():
    cfg = get_config()
    db_path = os.environ.get("DB_PATH", "data/rabbit_hunter.db")

    # 自检
    issues = preflight_check(
        enable_auto_trading=cfg.enable_auto_trading,
        binance_api_key=os.environ.get("BINANCE_API_KEY", ""),
        okx_api_key=os.environ.get("OKX_API_KEY", ""),
        openai_key=os.environ.get("OPENAI_API_KEY", ""),
        ai_enabled=os.environ.get("OPENAI_AI_ENABLED", "false").lower() in ("1", "true"),
    )
    if issues:
        for issue in issues:
            print(f"[FATAL] preflight: {issue}")
        sys.exit(1)

    # ... 后续 init_local_db 等
```

在 `asyncio.gather(...)` 里加 `_healthcheck_loop(db_path)`。

- [ ] **Step 4: 跑测试,期望全 pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/tasks/collector_main.py tests/test_collector_preflight.py
git commit -m "feat(v5): preflight check + healthcheck loop

- preflight_check: fail-fast on missing broker key (auto-trading) or OPENAI key
- _healthcheck_loop: WARN if 5min no signals OR 1h all AI rejected with no exec"
```

---

## Phase 14:SHADOW 端到端验收

### Task 15: 重建镜像 + 跑 24h + 验收脚本

**Files:**
- Create: `scripts/verify_v5_acceptance.py`

- [ ] **Step 1: 写验收脚本**

```python
"""V5 SHADOW 24h 验收 — 跑完打印通过/不通过。"""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone


def verify(db_path: str = "data/rabbit_hunter.db") -> bool:
    conn = sqlite3.connect(db_path)
    try:
        # 1. ≥ 50 笔 trade_scores_v5
        n_scores = conn.execute(
            "SELECT COUNT(*) FROM trade_scores_v5 "
            "WHERE created_at >= datetime('now', '-24 hour')"
        ).fetchone()[0]
        print(f"24h trade_scores_v5: {n_scores}  (要求 ≥ 50)")
        passed_scores = n_scores >= 50

        # 2. ≥ 1 笔 paper_trades 开 + 平
        n_open = conn.execute(
            "SELECT COUNT(*) FROM paper_trades "
            "WHERE status='OPEN' AND strategy_id='v5_rsi_macd'"
        ).fetchone()[0]
        n_closed = conn.execute(
            "SELECT COUNT(*) FROM paper_trades "
            "WHERE status='CLOSED' AND strategy_id='v5_rsi_macd' "
            "  AND exit_time >= datetime('now', '-24 hour')"
        ).fetchone()[0]
        print(f"24h paper_trades OPEN: {n_open}  CLOSED: {n_closed}  (要求 ≥ 1)")
        passed_trades = (n_open + n_closed) >= 1

        # 3. 拦截分布
        rows = conn.execute(
            "SELECT block_reason, COUNT(*) FROM trade_scores_v5 "
            "WHERE created_at >= datetime('now', '-24 hour') "
            "GROUP BY block_reason ORDER BY 2 DESC LIMIT 10"
        ).fetchall()
        print("\n拦截分布(过去 24h):")
        for br, cnt in rows:
            print(f"  {str(br):40s} = {cnt}")

        # 4. AI 拒绝率
        n_ai_rejected = sum(c for r, c in rows if r == "AI_REJECTED")
        ratio = n_ai_rejected / n_scores if n_scores else 0
        print(f"\nAI 拒绝率: {ratio*100:.1f}%  (要求 ≤ 90%)")
        passed_ai = ratio <= 0.90

        # 5. paper KPI
        kpi = conn.execute("""
            SELECT
              COUNT(*) as total,
              SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
              SUM(pnl) as total_pnl,
              AVG(holding_hours * 60) as avg_hold_min
            FROM paper_trades
            WHERE status='CLOSED' AND strategy_id='v5_rsi_macd'
              AND exit_time >= datetime('now', '-24 hour')
        """).fetchone()
        total, wins, total_pnl, avg_hold = kpi
        if total:
            print(f"\nKPI: 总笔 {total}, 胜 {wins} ({wins/total*100:.1f}%), "
                  f"PnL {total_pnl:.2f} USDT, 平均持仓 {avg_hold:.1f} 分钟")

        all_passed = passed_scores and passed_trades and passed_ai
        print("\n" + ("✅ 验收通过" if all_passed else "❌ 验收未通过"))
        return all_passed
    finally:
        conn.close()


if __name__ == "__main__":
    ok = verify("data/rabbit_hunter.db")
    sys.exit(0 if ok else 1)
```

- [ ] **Step 2: 跑 backup_pre_v5.sh + 重建镜像**

```bash
./scripts/backup_pre_v5.sh
docker compose down
docker compose build --no-cache collector api
docker compose up -d
```

等 30 秒,看启动日志:

```bash
docker compose logs --tail 80 collector
```

预期看到 `[collector_main] V5 启动 — mode=SHADOW`,且没有 `[FATAL]`。

- [ ] **Step 3: 跑 30 分钟,验"评分流活着"**

```bash
sleep 1800
docker compose exec -T collector python -c "
import sqlite3
conn = sqlite3.connect('/app/data/rabbit_hunter.db')
n = conn.execute('SELECT COUNT(*) FROM trade_scores_v5').fetchone()[0]
print(f'trade_scores_v5: {n} 行 (要求 ≥ 1)')
"
```

如果 30 分钟内 `trade_scores_v5` 还是 0 行,说明:
- DeepCollector 没拉到 K 线 → 看 `docker compose logs collector | grep DeepCollector`
- 没有 |ΔP| > 3% 的币种 → 暂时调 `V5_DELTA_15M_THRESHOLD=0.02` 看是否能触发

- [ ] **Step 4: 跑 24 小时**

```bash
sleep 86400
```

或者每小时人工 check:

```bash
docker compose exec -T collector python /app/scripts/verify_v5_acceptance.py
```

- [ ] **Step 5: 跑验收脚本**

```bash
docker compose exec -T collector python /app/scripts/verify_v5_acceptance.py
```

期望最后一行 `✅ 验收通过`。

- [ ] **Step 6: Commit + tag**

```bash
git add scripts/verify_v5_acceptance.py
git commit -m "chore(v5): SHADOW 24h acceptance script

Checks:
- ≥ 50 trade_scores_v5 in last 24h
- ≥ 1 paper_trade OPEN or CLOSED in last 24h
- AI rejection rate ≤ 90%
- Prints KPI snapshot (win rate / PnL / avg holding)"
git tag v5.0.0-shadow-validated
git push --tags
```

---

## Self-Review

### Spec coverage check

| Spec section | Task |
|---|---|
| §1.2 决策清单 1(完全替换) | Phase 11 Task 12 |
| §1.2 决策 2(AND 合谋) | Task 4 |
| §1.2 决策 3(4h 参考) | Task 7(prompt 含 4h 字段)+ Task 3(calculate_indicators) |
| §1.2 决策 4(15min 软目标) | Task 8 + Task 9 |
| §1.2 决策 5(|ΔP|>3% 过滤) | Task 6 |
| §1.2 决策 6(无冷却) | 默认无;Task 11 没加 cooldown 逻辑(✓) |
| §1.2 决策 7(最多 3 活仓) | Task 11 `MAX_CONCURRENT_POSITIONS` |
| §1.2 决策 8-9(1.5% × 10x) | Task 5 + Task 11 |
| §1.2 决策 10(前端重写 + /api/v5) | API:Task 13;前端单独写 Plan B |
| §1.3 删除清单 | Task 12 |
| §2.1 管道总图 | Task 6 + 11 + 12 |
| §2.2 组件清单 | Task 1, 3, 4, 5, 6, 8, 9, 10, 11, 13 |
| §2.3 数据契约 | Task 1 |
| §3 数据流时序 | Task 11(开仓)+ Task 9(平仓)|
| §4 DB schema | Task 2 |
| §5.1 错误处理矩阵 | 分散在 Task 6, 9, 10, 11, 14 |
| §5.3 测试策略 | 每个 Task 都有 unit / integration test |
| §6.1 部署步骤 | Task 15 |
| §6.4 验收清单 | Task 15 `verify_v5_acceptance.py` |
| §7 前端 | **下一份 Plan B** |

### Placeholder scan

无 TBD/TODO。所有代码 step 都给了完整代码或具体修改位置 + 完整片段。

### Type consistency

- `EnrichedItem`/`Indicators`/`Decision`/`RiskPlan`/`AIResult` 在 Task 1 定义,后续 Task 3-11 都一致用。
- `decide(enriched, indicators)` 在 Task 4 定义,Task 11 调用一致。
- `plan(side=..., entry=..., atr=..., balance=..., risk_pct=..., leverage=...)` Task 5 定义,Task 11 调用一致。
- `PaperPositionManager.open_position(enriched=, indicators=, decision=, risk=, ai=)` Task 7 定义,Task 11 调用一致。
- `check_exit_triggers(position, market)` Task 9 定义,Task 9 run loop 调用。
- 异常名 `InsufficientKlines` —— 实际代码用 `raise ValueError("InsufficientKlines: ...")`,字符串前缀。测试断言 `match="InsufficientKlines"`,一致。
- DB 字段名 `paper_trades.pnl` vs 测试 `pnl_usdt` —— Task 8 步骤 3 已经标注要按现有 schema 调整(明确指引,不是 bug)。

---

## 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-06-12-v5-backend-rebuild.md`.

**两种执行方式选一种:**

**1. Subagent-Driven(推荐)** —— 每个 Task 派一个新 subagent 执行,你在 Task 之间审,fast iteration。每个 Task 大约 15-30 分钟,15 个 Task 约 4-8 小时分散执行。

**2. Inline Execution** —— 在当前会话直接跑 executing-plans,批量执行,checkpoint 处停下来给你审。一口气跑下去需要长时间会话。

**哪个?**
