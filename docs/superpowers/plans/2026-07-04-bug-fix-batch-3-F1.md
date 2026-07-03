# Bug Fix Batch 3 · F1 SL_TP_FAIL_OPEN 现读 DB · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `SL_TP_FAIL_OPEN` 在 UI 改 Settings 后立刻生效 —— 抽 `scripts/settings_db.read_sl_tp_fail_open(db_path)` helper，`V5PositionManager.open_position()` 和 `OkxTrader.open_position()` 每次调用现读 DB；`api/routes/v5_settings.py` 里已有的 inline 逻辑改用 helper。

**Architecture:** 单 task TDD 循环：先写 6 个 helper unit test 验证 helper 尚不存在（RED）→ 建 helper → tests GREEN → 3 个消费者切换到 helper → 现有 v5_pm 测试无回归 → sanity → 单 commit。

**Tech Stack:** Python + pytest + sqlite3 stdlib + monkeypatch。无新增 pip 依赖。

## Global Constraints

- Only 5 files touched: 1 new (`scripts/settings_db.py`) + 1 new test (`tests/test_settings_db.py`) + 3 modified (`scripts/v5_position_manager.py`, `scripts/okx_trader.py`, `api/routes/v5_settings.py`)
- Helper 签名固定：`read_sl_tp_fail_open(db_path: str) -> bool`
- Helper 逻辑：DB `system_settings.sl_tp_fail_open` > env `SL_TP_FAIL_OPEN` > False；每次调用现读，不缓存
- 空值兼容 old 行为：`if not val: fallback` —— DB 里空字符串 也走 env
- **`SL_TP_FAIL_OPEN` 模块常量删除**（v5_position_manager.py L20 + okx_trader.py L36）
- **不改**：`scripts/binance_trader.py`（已确认无引用）、`scripts/config.py` `TradingConfig`、v5_settings.py 的 PATCH 写入路径、v5_settings.py 自己 module-local `_read_setting(conn, key, default)`（其他 handler 还在用）、前端 UI、`.githooks/`、dev-log
- 现有 `tests/test_v5_position_manager.py` 3 tests 必须依旧全 pass
- 3 pre-existing SIGNAL_REVERSE fail 在 `tests/test_v5_position_monitor.py` 依旧存在（超范围）
- Single commit, subject: `fix(settings): SL_TP_FAIL_OPEN 现读 system_settings + helper 抽取 (F1)`

---

## File Structure

| 路径 | 动作 |
|---|---|
| `scripts/settings_db.py` | **Create** — 20-30 行，含 `_read_setting(conn, key)` + `read_sl_tp_fail_open(db_path)` |
| `tests/test_settings_db.py` | **Create** — 6 unit tests |
| `scripts/v5_position_manager.py` | **Modify** — 删 L20 模块 const；`open_position()` 头部现读；L108/L141/L155/L184 引用改局部变量 |
| `scripts/okx_trader.py` | **Modify** — 删 L36 `_SL_TP_FAIL_OPEN`；`open_position()` 头部现读；L550/L566 引用改局部变量 |
| `api/routes/v5_settings.py` | **Modify** — L79-80 inline 逻辑改用 helper（仅这 1 行；enable_auto_trading / ai_fail_open 不动） |

---

# Task 1: helper + 6 tests + 3 消费者切换（single atomic commit）

**Files:**
- Create: `scripts/settings_db.py`
- Create: `tests/test_settings_db.py`
- Modify: `scripts/v5_position_manager.py`
- Modify: `scripts/okx_trader.py`
- Modify: `api/routes/v5_settings.py`

**Interfaces:**
- Consumes: sqlite3 stdlib
- Produces:
  - `scripts.settings_db.read_sl_tp_fail_open(db_path: str) -> bool`
  - `scripts.settings_db._read_setting(conn: sqlite3.Connection, key: str) -> Optional[str]`

## RED phase — 先写测试让它 fail

- [ ] **Step 1: 建 `tests/test_settings_db.py`**

```python
"""Unit tests for scripts.settings_db.read_sl_tp_fail_open."""
import sqlite3

import pytest

from scripts.settings_db import read_sl_tp_fail_open


def _make_db_with_setting(tmp_path, key: str, value: str) -> str:
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


def _make_db_with_empty_settings(tmp_path) -> str:
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
    # DB 值 = false;env 即使是 true 也不应生效（DB 优先）
    monkeypatch.setenv("SL_TP_FAIL_OPEN", "true")
    db = _make_db_with_setting(tmp_path, "sl_tp_fail_open", "false")
    assert read_sl_tp_fail_open(db) is False


def test_falls_back_to_env_when_db_missing_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SL_TP_FAIL_OPEN", "1")
    db = _make_db_with_empty_settings(tmp_path)
    assert read_sl_tp_fail_open(db) is True


def test_falls_back_to_env_when_db_unopenable(tmp_path, monkeypatch):
    monkeypatch.setenv("SL_TP_FAIL_OPEN", "yes")
    non_existent = str(tmp_path / "does_not_exist.db")
    # sqlite 会创建空的但没有 system_settings 表 → _read_setting 内部错误 → 返 None → 用 env
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

- [ ] **Step 2: 跑测试 —— 期望 RED**

```bash
python3 -m pytest tests/test_settings_db.py -v
```

Expected: 6 tests all FAIL —— `ModuleNotFoundError: No module named 'scripts.settings_db'`.

## GREEN phase (helper) — 写 helper 让 tests pass

- [ ] **Step 3: 建 `scripts/settings_db.py`**

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
      - True: system_settings.sl_tp_fail_open 或 env SL_TP_FAIL_OPEN 是
        "1"/"true"/"yes" (大小写空白忽略)
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
    # 空字符串也降级到 env（兼容 v5_settings.py:79 的旧 `or` 行为）
    if not val:
        val = os.environ.get("SL_TP_FAIL_OPEN", "false")
    return str(val).strip().lower() in ("1", "true", "yes")
```

- [ ] **Step 4: 跑测试 —— 期望 GREEN**

```bash
python3 -m pytest tests/test_settings_db.py -v
```

Expected: 6/6 PASS.

若失败：
- `test_reads_true_from_db` / `test_reads_false_from_db`：检查 `_read_setting` 返回值和 `if not val:` 逻辑
- `test_falls_back_to_env_when_db_unopenable`：sqlite `connect(non_existent)` 会创建文件；表不存在 → `_read_setting` 抛异常并返 None（外层 try 也有一层保护）；确认异常处理链正确
- `test_db_priority_over_env`：DB 有值不为空 → 应该 skip env；检查 `if not val`

## 消费者切换 (v5_position_manager, okx_trader, v5_settings)

- [ ] **Step 5: 改 `scripts/v5_position_manager.py`**

**删** L20（`SL_TP_FAIL_OPEN = ...` 模块常量）。

**改** L4 文件顶部 docstring（把 `SL_TP_FAIL_OPEN=true` 措辞改成 `sl_tp_fail_open=true`）：

```python
"""V5 LIVE 持仓管理 — 走 Broker(Binance/OKX)真实下单。

fail-closed: 主仓成功 + SL/TP 失败 → 立即市价平回滚。
fail-open  : 运行时 sl_tp_fail_open=true 时保留主仓,但带 sl_attached=False 标记。

... (剩下原样)
"""
```

**改** `open_position(...)` 方法头部（原 L65+ 附近），在 `position_size_coins = size_usdt / entry_price` 前加两行：

```python
    def open_position(self, *, symbol: str, side: str, entry_price: float,
                      sl_price: float, tp_price: float, size_usdt: float,
                      leverage: int) -> int:
        """LIVE 开仓三阶段状态机..."""
        from scripts.settings_db import read_sl_tp_fail_open
        sl_tp_fail_open = read_sl_tp_fail_open(self.db_path)

        position_size_coins = size_usdt / entry_price
        # ...原代码继续
```

**改** L108 `if not SL_TP_FAIL_OPEN:` → `if not sl_tp_fail_open:`

**改** L141 打印语句：`SL_TP_FAIL_OPEN=true` → `sl_tp_fail_open=true`：

```python
            print(f"[V5PositionManager] ⚠️  SL 失败但 sl_tp_fail_open=true 保留主仓: {e_sl}")
```

**改** L155 `if not SL_TP_FAIL_OPEN:` → `if not sl_tp_fail_open:`

**改** L184 打印语句：`SL_TP_FAIL_OPEN=true` → `sl_tp_fail_open=true`：

```python
            print(f"[V5PositionManager] ⚠️  TP 失败但 sl_tp_fail_open=true 保留主仓: {e_tp}")
```

- [ ] **Step 6: 改 `scripts/okx_trader.py`**

**删** L36 `_SL_TP_FAIL_OPEN = os.environ.get(...)` 模块常量（保留 L34-35 注释，可以留原样，`_SL_TP_FAIL_OPEN` 变量注释也可以顺便删）。

**改** `OkxTrader.open_position(...)` 方法头部（原 L465）。在方法开头加两行，替换旧模块常量的用途：

```python
    def open_position(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Dict[str, Any]:
        """OKX 开仓..."""
        from scripts.settings_db import read_sl_tp_fail_open
        fail_open = read_sl_tp_fail_open(
            os.environ.get("DB_PATH", "data/rabbit_hunter.db")
        )
        # ...原代码继续
```

**改** L550 `if not _SL_TP_FAIL_OPEN:` → `if not fail_open:`

**改** L566 `if not _SL_TP_FAIL_OPEN:` → `if not fail_open:`

**改** L533 注释里 `SL_TP_FAIL_OPEN` → `sl_tp_fail_open`。

- [ ] **Step 7: 改 `api/routes/v5_settings.py`**

**改** L79-80 —— 目前是：

```python
        sl_tp_fail_open = (_read_setting(conn, "sl_tp_fail_open") or
                           os.environ.get("SL_TP_FAIL_OPEN", "false")).lower() in ("1", "true")
```

改为：

```python
        sl_tp_fail_open = read_sl_tp_fail_open(_db())
```

**顶部 import 添加**（如果尚未 import）：

```python
from scripts.settings_db import read_sl_tp_fail_open
```

其他 handler 里对 `enable_auto_trading` / `ai_fail_open` 的 inline 逻辑**不动**（本 spec 只处理 `sl_tp_fail_open`）。v5_settings.py 自己 module-local `_read_setting(conn, key, default)` 也**不动**（其他 handler 还用）。

## 验证 + commit

- [ ] **Step 8: 跑 helper 测试 + v5_pm 现有测试 + 邻近**

```bash
python3 -m pytest tests/test_settings_db.py tests/test_v5_position_manager.py tests/test_paper_position_manager_v5.py tests/test_v5_position_monitor.py -v 2>&1 | tail -20
```

Expected:
- `tests/test_settings_db.py` 6/6 PASS
- `tests/test_v5_position_manager.py` 3/3 PASS（无回归）
- `tests/test_paper_position_manager_v5.py` 全 PASS
- `tests/test_v5_position_monitor.py` 15 PASS / 3 pre-existing FAIL（SIGNAL_REVERSE 超范围，数目不变）

- [ ] **Step 9: sanity greps**

```bash
# 模块常量已删
grep -n "^SL_TP_FAIL_OPEN = \|^_SL_TP_FAIL_OPEN = " scripts/v5_position_manager.py scripts/okx_trader.py
# 期望：0 hits

# helper 被 3 处消费
grep -rn "read_sl_tp_fail_open" scripts/ api/ 
# 期望：至少 4 hits（helper 自身 1 + v5_position_manager 2（import + call） + okx_trader 2 + v5_settings 2）—— 具体计数不定,但一定要 ≥ 4

# helper 存在
grep -n "def read_sl_tp_fail_open" scripts/settings_db.py
# 期望：1 hit

# v5_settings.py 保留 _db() 和自己的 _read_setting
grep -n "def _db\|def _read_setting" api/routes/v5_settings.py
# 期望：2 hits (无损失)
```

- [ ] **Step 10: Commit**

```bash
git add scripts/settings_db.py tests/test_settings_db.py scripts/v5_position_manager.py scripts/okx_trader.py api/routes/v5_settings.py
git commit -m "$(cat <<'EOF'
fix(settings): SL_TP_FAIL_OPEN 现读 system_settings + helper 抽取 (F1)

修 bug-fix-list.md Finding 1:V5PositionManager 和 OkxTrader 之前把
SL_TP_FAIL_OPEN 当模块常量在 import 时读 env,UI 在 Settings 页面改
sl_tp_fail_open 后不生效(需重启进程)。

Change:
- 新增 scripts/settings_db.py 含 read_sl_tp_fail_open(db_path) helper
  DB 优先 > env fallback > False,每次现读无缓存
- V5PositionManager.open_position() 每次调 helper 读 self.db_path
- OkxTrader.open_position() 每次调 helper 读 env DB_PATH 默认路径
- api/routes/v5_settings.py L79-80 inline 逻辑改用 helper (DRY)

Tests:
- 新增 tests/test_settings_db.py 6 unit tests
  (DB true/false/env fallback/DB 不可开/双缺席/DB 优先)
- 现有 test_v5_position_manager.py 3 tests 无回归
- test_v5_position_monitor.py 3 条 SIGNAL_REVERSE fail 超范围仍在

超范围:binance_trader.py (无引用)、TradingConfig.sl_tp_fail_open
(另一个 spec 重构整个 config 层)、PATCH 写入路径 (已正确)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

# Self-Review 记录

- **spec § 四 Helper**：Step 3 (helper 完整实现) + Step 1 (6 tests 直接测) ✓
- **spec § 五 v5_position_manager**：Step 5（删 const、docstring、方法头现读、L108/L141/L155/L184 引用）✓
- **spec § 六 okx_trader**：Step 6（删 const、方法头现读、L550/L566/L533 引用）✓
- **spec § 七 v5_settings dedup**：Step 7（L79-80 一行改）✓
- **spec § 八 6 tests**：Step 1 全部展开 ✓
- **spec § 九 回归保护**：Step 8 显示跑 v5_pm + paper_pm + monitor ✓
- **spec § 十 验收**：Step 8 (pytest) + Step 9 (sanity greps) + 只 5 files staged (Step 10) ✓
- **placeholder scan**：无 TBD / TODO / "similar to Task N" ✓
- **type consistency**：`read_sl_tp_fail_open(db_path)` 签名在 spec + plan + tests + 3 消费者调用点一致 ✓
- **behavior compatibility**：`if not val` 处理空字符串走 env fallback，与旧 `or` 行为一致 ✓
