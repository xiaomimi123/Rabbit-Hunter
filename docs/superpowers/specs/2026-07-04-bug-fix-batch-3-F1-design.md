# Bug Fix Batch 3 · F1 SL_TP_FAIL_OPEN 模块常量不响应 UI · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 1

---

## 一、问题陈述

UI Settings 页面能修改 `sl_tp_fail_open`（`api/routes/v5_settings.py:254-255` 写入 `system_settings.sl_tp_fail_open`），但**真正决策路径的两个模块常量只在 import 时读 env**：

- `scripts/v5_position_manager.py:20` `SL_TP_FAIL_OPEN = os.environ.get("SL_TP_FAIL_OPEN", "false").lower() in ("1", "true")`
- `scripts/okx_trader.py:36` `_SL_TP_FAIL_OPEN = os.environ.get("SL_TP_FAIL_OPEN", "false").lower() in ("1", "true", "yes")`

用户在 UI 改 → 存 DB → 下单代码仍读 env → 行为不变。必须重启进程才生效，与"运行时配置"语义完全脱节。

## 二、目标

- **每次开仓时现读 DB**（`system_settings.sl_tp_fail_open`）
- **DB 缺失时降级到 env**（保持向下兼容）
- **两处均改**（v5_position_manager + okx_trader）
- **v5_settings.py 已有的 inline 读逻辑改用同一 helper**（DRY）

## 三、范围

**In scope**:
- 新建 `scripts/settings_db.py` — 含 `read_sl_tp_fail_open(db_path)` helper
- 改 `scripts/v5_position_manager.py` — 删模块 const，`open_position()` 内现读 DB
- 改 `scripts/okx_trader.py` — 删模块 const `_SL_TP_FAIL_OPEN`，`open_position()` 内现读 DB
- 改 `api/routes/v5_settings.py` L79-80 — 用 helper dedup 掉 inline 逻辑
- 新建 `tests/test_settings_db.py` — 6 单元测试直接测 helper

**Out of scope**:
- `scripts/binance_trader.py` — 已确认无 `SL_TP_FAIL_OPEN` 引用（不受此 bug 影响）
- `scripts/config.py` `TradingConfig.sl_tp_fail_open` 字段 — 目前没有 runtime 消费者（另一个 spec 该重构整个 config 层）
- PATCH 写路径不动（写入 `system_settings` 已正确）
- 前端 UI 不动（已能改）
- 其他 P0（F2 / F3 / SIGNAL_REVERSE 测试）
- 不加 caching / TTL（YAGNI；SELECT overhead < 1ms，交易频率下无感）

## 四、Helper 接口

**新文件**：`scripts/settings_db.py`

```python
"""动态从 system_settings 读运行时可变的设置。

优先级:DB > env > 硬编码 fallback。DB 未启用时降级到 env。
每次调用现读,不缓存 —— 交易频率下 SELECT overhead 可忽略。
"""
import os
import sqlite3
from typing import Optional


def _read_setting(conn: sqlite3.Connection, key: str) -> Optional[str]:
    """读一个 system_settings 键。表不存在 or 键不存在 → None。"""
    try:
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None


def read_sl_tp_fail_open(db_path: str) -> bool:
    """DB > env > False. 现读现返。

    返回:
      - True: system_settings.sl_tp_fail_open 或 env SL_TP_FAIL_OPEN 是 "1"/"true"/"yes"
      - False: 上述都不满足
    """
    val: Optional[str] = None
    try:
        conn = sqlite3.connect(db_path)
        try:
            val = _read_setting(conn, "sl_tp_fail_open")
        finally:
            conn.close()
    except sqlite3.Error:
        val = None
    if val is None:
        val = os.environ.get("SL_TP_FAIL_OPEN", "false")
    return str(val).strip().lower() in ("1", "true", "yes")
```

## 五、Change 1 — `scripts/v5_position_manager.py`

### 5.1 删模块常量 L20

```python
# 删除这一行 —— 不再需要
SL_TP_FAIL_OPEN = os.environ.get("SL_TP_FAIL_OPEN", "false").lower() in ("1", "true")
```

### 5.2 `open_position()` 头部现读

在 `open_position` 第一行加：

```python
def open_position(self, *, symbol, side, entry_price, sl_price, tp_price, size_usdt, leverage) -> int:
    from scripts.settings_db import read_sl_tp_fail_open
    sl_tp_fail_open = read_sl_tp_fail_open(self.db_path)
    # ... 原来的方法体继续
```

### 5.3 用局部变量替换常量引用

- L108 `if not SL_TP_FAIL_OPEN:` → `if not sl_tp_fail_open:`
- L155 `if not SL_TP_FAIL_OPEN:` → `if not sl_tp_fail_open:`
- L141 print 消息里 `SL_TP_FAIL_OPEN=true` 措辞改为 `sl_tp_fail_open=true`（更准确 —— 现在的来源不一定是 env）
- L184 同理

### 5.4 文件顶部 docstring L4

`fail-open : SL_TP_FAIL_OPEN=true 时保留主仓...` 更新为 `fail-open : 运行时 sl_tp_fail_open=true 时保留主仓...`

## 六、Change 2 — `scripts/okx_trader.py`

### 6.1 删模块常量 L36

```python
# 删除这一行
_SL_TP_FAIL_OPEN = os.environ.get("SL_TP_FAIL_OPEN", "false").lower() in ("1", "true", "yes")
```

### 6.2 `open_position()` 头部现读

在 OkxTrader.open_position 方法开头加：

```python
def open_position(self, symbol, side, quantity, order_type="MARKET", price=None, stop_loss=None, take_profit=None):
    from scripts.settings_db import read_sl_tp_fail_open
    fail_open = read_sl_tp_fail_open(os.environ.get("DB_PATH", "data/rabbit_hunter.db"))
    # ... 方法体继续
```

**注**：`OkxTrader` 没有 `self.db_path`（架构上 broker 是 DB-agnostic），用 env `DB_PATH` fallback 到 `data/rabbit_hunter.db` —— 与 `collector_main.py`（L216）等地约定一致。这不是理想架构，但避免了给 OkxTrader/BinanceTrader 加 DB 依赖的大改动。若未来 `LOCAL_DB_PATH` vs `DB_PATH` 分裂（Phase 0 tech-debt Finding 1）修好后可统一。

### 6.3 用局部变量替换常量引用

- L550 `if not _SL_TP_FAIL_OPEN:` → `if not fail_open:`
- L566 同上
- L533 注释里 `SL_TP_FAIL_OPEN` 措辞改成 `sl_tp_fail_open`

## 七、Change 3 — `api/routes/v5_settings.py` L79-80 dedup

现有 inline 逻辑：

```python
sl_tp_fail_open = (_read_setting(conn, "sl_tp_fail_open") or
                   os.environ.get("SL_TP_FAIL_OPEN", "false")).lower() in ("1", "true")
```

改为（`v5_settings.py:22` 已有 `_db()` 辅助函数返回 db path）：

```python
# 顶部 imports
from scripts.settings_db import read_sl_tp_fail_open

# L79-80 改造前后（在 GET /api/v5/settings handler 内）
# BEFORE:
sl_tp_fail_open = (_read_setting(conn, "sl_tp_fail_open") or
                   os.environ.get("SL_TP_FAIL_OPEN", "false")).lower() in ("1", "true")
# AFTER:
sl_tp_fail_open = read_sl_tp_fail_open(_db())
```

注意：`read_sl_tp_fail_open` 自己会开新 conn，因此 handler 传的 `conn` 参数不再用于本行。不要拆除 v5_settings.py 自己的 module-local `_read_setting(conn, key, default)` —— 它签名带 `default`，本文件其他地方还在用，dedup 那个是另一件事。

## 八、Change 4 — 新增测试

**新文件** `tests/test_settings_db.py`：

```python
"""Unit tests for scripts.settings_db.read_sl_tp_fail_open."""
import os
import sqlite3
import tempfile

import pytest

from scripts.settings_db import read_sl_tp_fail_open


def _make_db_with_setting(tmp_path, key: str, value: str):
    db = str(tmp_path / "settings.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE system_settings (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.execute(
        "INSERT INTO system_settings (key, value) VALUES (?, ?)", (key, value),
    )
    conn.commit()
    conn.close()
    return db


def _make_db_with_empty_settings(tmp_path):
    db = str(tmp_path / "settings.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE system_settings (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.commit()
    conn.close()
    return db


def test_reads_true_from_db(tmp_path, monkeypatch):
    monkeypatch.delenv("SL_TP_FAIL_OPEN", raising=False)
    db = _make_db_with_setting(tmp_path, "sl_tp_fail_open", "true")
    assert read_sl_tp_fail_open(db) is True


def test_reads_false_from_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SL_TP_FAIL_OPEN", "true")  # env 会被 DB 覆盖
    db = _make_db_with_setting(tmp_path, "sl_tp_fail_open", "false")
    assert read_sl_tp_fail_open(db) is False


def test_falls_back_to_env_when_db_missing_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SL_TP_FAIL_OPEN", "1")
    db = _make_db_with_empty_settings(tmp_path)
    assert read_sl_tp_fail_open(db) is True


def test_falls_back_to_env_when_db_unopenable(tmp_path, monkeypatch):
    monkeypatch.setenv("SL_TP_FAIL_OPEN", "yes")
    non_existent = str(tmp_path / "does_not_exist.db")
    # sqlite 会创建空的,但没有 system_settings 表 → 内部错误 → 返 None → 用 env
    assert read_sl_tp_fail_open(non_existent) is True


def test_returns_false_when_both_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("SL_TP_FAIL_OPEN", raising=False)
    db = _make_db_with_empty_settings(tmp_path)
    assert read_sl_tp_fail_open(db) is False


def test_db_priority_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SL_TP_FAIL_OPEN", "true")
    db = _make_db_with_setting(tmp_path, "sl_tp_fail_open", "false")
    assert read_sl_tp_fail_open(db) is False
```

## 九、Regression 保护

- `tests/test_v5_position_manager.py` 3 条现有 tests —— 都在 fail-closed 默认路径下断言，改动应不受影响
- 需在 spec 验收时 pytest 确认这 3 条 pass（14→15 not applicable，此文件是 v5_position_manager，独立于 monitor）
- `tests/test_v5_position_monitor.py` 15 pass / 3 pre-existing fail 数量不变

## 十、验收标准

- `python3 -m pytest tests/test_settings_db.py -v` → 6/6 pass
- `python3 -m pytest tests/test_v5_position_manager.py -v` → 3/3 pass（无回归）
- `grep -n "SL_TP_FAIL_OPEN =" scripts/v5_position_manager.py scripts/okx_trader.py` → 0 hits（模块常量已删）
- `grep -n "read_sl_tp_fail_open" scripts/ api/` → 至少 3 hits（v5_pm + okx_trader + v5_settings）
- 只 stage 5 文件（1 新 helper + 3 modified + 1 新 test）

## 十一、失效模式与降级

- **DB 不存在 / 表不存在**：`_read_setting` 内部 try/except 返 None → helper 走 env 分支
- **env 未设**：默认 `"false"` → 返 False（fail-closed 默认，安全）
- **DB 中值不是标准 bool 字符串**（如 `"yes"`, `"1"`）：helper 内的 `.strip().lower() in ("1", "true", "yes")` 兼容
- **DB 中值不合法**（如 `""` / `"maybe"`）：不匹配 truthy 集合 → 返 False（安全兜底）
- **并发写 vs 读**：SQLite 单文件 fine；读一个 key 是原子的（一 SELECT）；不涉及事务

## 十二、相关

- Bug audit: `docs/audit-2026-07/bug-fix-list.md` Finding 1
- 前置 batch: `docs/superpowers/specs/2026-07-03-bug-fix-batch-1-F4-design.md`, `2026-07-03-bug-fix-batch-2-F5-design.md`
- 相关但未修的关联 Finding：Phase 0 tech-debt `LOCAL_DB_PATH` vs `DB_PATH` 命名分裂（应会与本 spec 的 `os.environ.get("DB_PATH", ...)` 约定一同修）
