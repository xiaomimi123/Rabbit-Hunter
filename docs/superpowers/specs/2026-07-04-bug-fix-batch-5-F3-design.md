# Bug Fix Batch 5 · F3 LIVE 余额拉取失败 fallback paper · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 3

---

## 一、问题陈述

`scripts/tasks/collector_main.py:67-89` `_fetch_balance()` 在 LIVE 模式下拉不到真实余额时**仍返 `_PAPER_BALANCE`（1000 USDT）**：

```python
def _fetch_balance() -> float:
    if _resolve_mode_db() != "LIVE":
        return _PAPER_BALANCE           # SHADOW 兜底,正常
    try:
        trader = _get_live_trader()
        if trader is not None:
            bal = trader.fetch_balance()
            # ...parse USDT...
            if usdt is not None and float(usdt) > 0:
                return float(usdt)       # LIVE 成功
    except Exception as e:
        print(f"[collector_main] LIVE 余额拉取失败,用 PAPER_INITIAL_BALANCE_USDT: {e}")
    return _PAPER_BALANCE                # ← 病根:LIVE 失败也返 1000
```

**后果**：LIVE 模式下真账户余额假设是 100 USDT，balance 被伪造成 1000 → `gate_per_trade_risk(equity=1000, cap_pct=1.5%)` 允许 15 USDT 单笔风险 → 但真实账户里 15 USDT 是 15% 风险，**10 倍超风险**。触发一次 SL 就把账户打掉 15%。

## 二、目标

- LIVE 失败 → 返 `None`（signal），不再伪造
- scorer 见 `balance_usdt is None` → 写 `trade_scores_v5` 带 `block_reason='BALANCE_UNAVAILABLE'`，skip 本次开仓
- SHADOW 分支不变（继续返 `_PAPER_BALANCE`，SHADOW = 纸面交易，1000 USDT 是设计）

## 三、范围

**In scope**:
- `scripts/tasks/collector_main.py` `_fetch_balance()` 签名 + LIVE 失败分支
- `scripts/tasks/scorer.py` `process_enriched_v5` 签名 + 新 gate（`gate_daily_drawdown` 之前）
- 新建 `tests/test_collector_main_v5.py` 覆盖 `_fetch_balance` 3 场景
- 追加 1 test 到 `tests/test_v5_scorer.py`（若不存在则新建）覆盖 `process_enriched_v5(balance_usdt=None)`

**Out of scope**:
- 不改 `V5Scorer.run()` L458-465（依然 `balance = self.fetch_balance()`；只是 balance 可能是 None，process_enriched_v5 会处理）
- 不修 Finding 8（scorer L464 广谱 catch）—— P1 tech-debt，另外一批。**关键**：本设计返 None 不抛异常 → 避开 Finding 8 的吞异常路径
- 不改 SHADOW 分支
- 不加 balance 缓存 / retry（YAGNI，30s scanner tick 已足够慢）
- 不改前端 —— `BALANCE_UNAVAILABLE` 是新 block_reason 值，若前端要专门展示需另外加
- 不动其他 P0 / SIGNAL_REVERSE

## 四、Change 1 — `scripts/tasks/collector_main.py`

### 4.1 顶部 import

若 `from typing import Optional` 未存在则添加。

### 4.2 `_fetch_balance` 签名 + 主体

**Before** (L67-89)：
```python
def _fetch_balance() -> float:
    """SHADOW 模式直接返回 PAPER_INITIAL_BALANCE_USDT ..."""
    if _resolve_mode_db() != "LIVE":
        return _PAPER_BALANCE
    try:
        trader = _get_live_trader()
        if trader is not None:
            bal = trader.fetch_balance()
            usdt = None
            if isinstance(bal, dict):
                if "USDT" in bal and isinstance(bal["USDT"], dict):
                    usdt = bal["USDT"].get("free") or bal["USDT"].get("available")
                elif "free" in bal:
                    usdt = bal["free"]
                elif "available" in bal:
                    usdt = bal["available"]
            if usdt is not None and float(usdt) > 0:
                return float(usdt)
    except Exception as e:
        print(f"[collector_main] LIVE 余额拉取失败,用 PAPER_INITIAL_BALANCE_USDT: {e}")
    return _PAPER_BALANCE
```

**After**：
```python
def _fetch_balance() -> Optional[float]:
    """SHADOW 模式直接返回 PAPER_INITIAL_BALANCE_USDT
    (避免每次 scoring 都打一堆 fetch_balance / load_markets 失败的日志)。
    LIVE 模式才真正去拉真实余额。LIVE 失败返 None (由 scorer 端写 BALANCE_UNAVAILABLE
    block 记录,不伪造成 1000 USDT 假余额,防止风险计算被误导 —— F3)。"""
    if _resolve_mode_db() != "LIVE":
        return _PAPER_BALANCE
    try:
        trader = _get_live_trader()
        if trader is not None:
            bal = trader.fetch_balance()
            usdt = None
            if isinstance(bal, dict):
                if "USDT" in bal and isinstance(bal["USDT"], dict):
                    usdt = bal["USDT"].get("free") or bal["USDT"].get("available")
                elif "free" in bal:
                    usdt = bal["free"]
                elif "available" in bal:
                    usdt = bal["available"]
            if usdt is not None and float(usdt) > 0:
                return float(usdt)
    except Exception as e:
        print(f"[collector_main] LIVE 余额拉取失败,scorer 侧将写 BALANCE_UNAVAILABLE: {e}")
    return None
```

## 五、Change 2 — `scripts/tasks/scorer.py`

### 5.1 `process_enriched_v5` 签名

**Before** (L191-192)：
```python
async def process_enriched_v5(*, enriched: EnrichedItem, ai, paper_pm, live_pm,
                              mode: str, db_path: str, balance_usdt: float) -> None:
```

**After**：
```python
async def process_enriched_v5(*, enriched: EnrichedItem, ai, paper_pm, live_pm,
                              mode: str, db_path: str,
                              balance_usdt: Optional[float]) -> None:
```

（`Optional` 需 import from typing 若未有）

### 5.2 新 gate — 插入位置

在 `gate_daily_drawdown` 之前（约 L269-274 附近，`try:` 块开头之前）插入：

```python
    # F3:LIVE 余额拉取失败(_fetch_balance 返 None) → 不能可靠算风险,skip 本次开仓
    if balance_usdt is None:
        _write_trade_score(db_path, enriched, indicators, decision,
                          block_reason="BALANCE_UNAVAILABLE",
                          funding_z_score=funding_z_score,
                          funding_rate_8h=funding_rate_8h)
        return
```

放在 `gate_daily_drawdown` 之前是因为它是 balance 的第一个消费者。此时 `indicators` + `decision` 已就绪，可以写完整 trade_scores_v5 记录。

## 六、Change 3 — 测试

### 6.1 新建 `tests/test_collector_main_v5.py`

```python
"""V5 collector_main 的 _fetch_balance 分支测试 (F3)."""
import os
import sys
from unittest.mock import MagicMock

import pytest


def _stub_ccxt():
    """ccxt 在测试环境未装,先 stub 避免 collector_main import 时崩。"""
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = MagicMock()


def test_fetch_balance_shadow_returns_paper(monkeypatch):
    _stub_ccxt()
    from scripts.tasks import collector_main

    monkeypatch.setattr(collector_main, "_resolve_mode_db", lambda: "SHADOW")
    monkeypatch.setenv("PAPER_INITIAL_BALANCE_USDT", "1000")

    # SHADOW 分支不 hit trader,不用 mock
    result = collector_main._fetch_balance()
    assert result == 1000.0


def test_fetch_balance_live_success_returns_real(monkeypatch):
    _stub_ccxt()
    from scripts.tasks import collector_main

    monkeypatch.setattr(collector_main, "_resolve_mode_db", lambda: "LIVE")

    fake_trader = MagicMock()
    fake_trader.fetch_balance.return_value = {"USDT": {"free": 500.5, "available": 500.5}}
    monkeypatch.setattr(collector_main, "_get_live_trader", lambda: fake_trader)

    result = collector_main._fetch_balance()
    assert result == 500.5


def test_fetch_balance_live_failure_returns_none(monkeypatch):
    """LIVE trader.fetch_balance 抛 → 返 None(不再 fallback 到 1000)."""
    _stub_ccxt()
    from scripts.tasks import collector_main

    monkeypatch.setattr(collector_main, "_resolve_mode_db", lambda: "LIVE")

    fake_trader = MagicMock()
    fake_trader.fetch_balance.side_effect = RuntimeError("network error")
    monkeypatch.setattr(collector_main, "_get_live_trader", lambda: fake_trader)

    result = collector_main._fetch_balance()
    assert result is None
```

### 6.2 新建 `tests/test_v5_scorer.py`

```python
"""V5 Scorer process_enriched_v5 分支测试 (F3 balance=None)."""
import asyncio
import sqlite3
import sys
from unittest.mock import MagicMock

import pytest


def _stub_ccxt():
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = MagicMock()


def _make_enriched():
    """构造一个最小 EnrichedItem 让 decide() 能跑通。"""
    from scripts.tasks.scanner_types import EnrichedItem
    from datetime import datetime, timezone
    return EnrichedItem(
        symbol="H/USDT",
        current_price=0.166,
        delta_15m_pct=1.2,
        volume_24h_usdt=1_500_000,
        # ... 视 EnrichedItem 实际字段填充最小可跑值
    )


def test_process_enriched_none_balance_writes_block(tmp_path, monkeypatch):
    """balance_usdt=None → 写 trade_scores_v5 block_reason=BALANCE_UNAVAILABLE, skip 开仓."""
    _stub_ccxt()
    from scripts.local_db import init_local_db
    from scripts.tasks.scorer import process_enriched_v5

    db = str(tmp_path / "x.db")
    init_local_db(db)

    enriched = _make_enriched()

    # 最小 mock:ai / paper_pm / live_pm 都不该被调,因为 None balance gate 会提前 return
    paper_pm = MagicMock()
    live_pm = MagicMock()
    ai = MagicMock()

    asyncio.run(process_enriched_v5(
        enriched=enriched, ai=ai, paper_pm=paper_pm, live_pm=live_pm,
        mode="LIVE", db_path=db, balance_usdt=None,
    ))

    # 验证 trade_scores_v5 有一条 BALANCE_UNAVAILABLE 记录
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT block_reason FROM trade_scores_v5 WHERE symbol=?", (enriched.symbol,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "BALANCE_UNAVAILABLE"

    # 验证 paper_pm / live_pm 未被调用（skip 了开仓）
    paper_pm.open_position.assert_not_called()
    live_pm.open_position.assert_not_called()
```

**Note**：`_make_enriched()` 里的 `EnrichedItem` 字段列表需按实际类定义填充。若实施时发现有更多必填字段（比如 rsi / macd），补齐即可。

## 七、验收标准

- `python3 -m pytest tests/test_collector_main_v5.py tests/test_v5_scorer.py -v` → 4/4 pass
- 邻近 tests 无回归：`test_v5_position_manager.py` 8/8，`test_v5_position_monitor.py` 15 pass / 3 pre-existing fail，`test_paper_position_manager_v5.py` 4/4，`test_settings_db.py` 6/6，`test_v5_position_close_api.py` 全 pass
- 只 stage 4 文件：`scripts/tasks/collector_main.py` + `scripts/tasks/scorer.py` + 2 新 test 文件
- Commit message subject: `fix(collector+scorer): LIVE 余额拉失败不再 fallback 到 1000,scorer 写 BALANCE_UNAVAILABLE (F3)`

## 八、失效模式

- **SHADOW 模式**：`_fetch_balance` 返 `_PAPER_BALANCE`；scorer 侧看到非 None，走原流程。行为不变。
- **LIVE 成功**：返真实 USDT；scorer 走原流程。行为不变。
- **LIVE trader is None** (`_get_live_trader()` 返 None)：外层 try 内的 `if trader is not None:` 跳过，走到最外层 return None（新分支）。scorer 端写 BALANCE_UNAVAILABLE。
- **LIVE trader.fetch_balance() 抛**：except 捕获 → return None → scorer 写 BALANCE_UNAVAILABLE。
- **LIVE 返 dict 无 USDT / usdt=0 / usdt is None**：走到最外层 return None。
- **process_enriched_v5 收到 None balance**：新 gate 写 BALANCE_UNAVAILABLE + return，`paper_pm`/`live_pm` 不被调。

## 九、超范围声明

- 不改 `V5Scorer.run()` L458-465 结构
- 不加 balance 缓存 / retry state
- 不新 ws_event_queue 事件（trade_scores_v5 里 BALANCE_UNAVAILABLE 记录已提供完整审计）
- 不改前端 / 展示
- 不修 F1 / F2 / F4 / F5（已修）/ Finding 8 / SIGNAL_REVERSE

## 十、相关

- Bug audit: `docs/audit-2026-07/bug-fix-list.md` Finding 3
- 前置 batches: `2026-07-03-bug-fix-batch-1-F4-design.md` / `2026-07-03-bug-fix-batch-2-F5-design.md` / `2026-07-03-bug-fix-batch-3-F1-design.md` / `2026-07-04-bug-fix-batch-4-F2-design.md`
- 引用文件：
  - `scripts/tasks/collector_main.py:67-89`（当前 `_fetch_balance`）
  - `scripts/tasks/scorer.py:191-192`（`process_enriched_v5` 签名）
  - `scripts/tasks/scorer.py:274`（第一个 balance-consuming gate）
  - `scripts/tasks/scorer.py:145-175`（`_write_trade_score` 签名，已支持 block_reason）
