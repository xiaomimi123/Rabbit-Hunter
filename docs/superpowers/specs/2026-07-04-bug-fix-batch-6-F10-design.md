# Bug Fix Batch 6 · Finding 10 · V5Scorer.run 广谱 catch 静默丢 item · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 10；Batch 2 F5 建立的 `_enqueue_ws` 模式

---

## 一、问题陈述

`scripts/tasks/scorer.py:456-465` `V5Scorer.run()`：

```python
try:
    mode = self.resolve_mode()
    balance = self.fetch_balance()
    await process_enriched_v5(...)
except Exception as e:
    print(f"[V5Scorer] {enriched.symbol} 处理异常: {type(e).__name__}: {e}")
```

任何未预期异常（如 SQLite `database is locked`、AI timeout、indicator engine crash）冒泡到 L464，仅一行 print 后 loop 继续。**后果**：

- `trade_scores_v5` 无失败记录，AI 已请求过的成本沉没
- `_healthcheck_loop` 的"5 分钟无写入"告警在高频扫描下可能来不及触发
- 运营侧看不到任何实时信号

## 二、目标

在 catch 处新增一条 `ws_event_queue` `scorer_error` 事件，前端/运维实时可见。保留 print（现有日志基础设施）。不重构 V5Scorer 结构。

## 三、范围

**In scope**:
- `scripts/tasks/scorer.py` 顶部 import `_enqueue_ws`；catch 块新增 ws 事件写入（2-3 行）
- 新建 `tests/test_v5_scorer_run_catches.py` 1 test 覆盖异常路径

**Out of scope**:
- 不抽 `_process_one` helper（用户明确选 minimal，不 refactor V5Scorer 结构）
- 不改 `process_enriched_v5` 内部
- 不加 sqlite retry / batch write / 指数退避
- 不新增 healthcheck 逻辑
- 不改 F1/F2/F3/F4/F5（已修）
- 不动其他 P1 findings

## 四、Change 1 — `scripts/tasks/scorer.py`

### 4.1 顶部新 import

`_enqueue_ws` 在 `scripts/tasks/v5_position_monitor.py:15` 已定义为 module-level function（Batch 2 F5 建立）。为 P1 最小改动、避免立即改架构，直接从 monitor 反向 import：

```python
from scripts.tasks.v5_position_monitor import _enqueue_ws
```

**架构提示**：若未来 review 觉得反向 import (scorer → monitor) 不干净，可以另开 spec 把 `_enqueue_ws` 抽到 `scripts/tasks/ws_bus.py` 或类似 shared 位置。本 spec 只做 minimal ws 添加。

### 4.2 改 `V5Scorer.run()` 的 catch 块（L456-465 附近）

**Before**：
```python
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

**After**：
```python
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
    # Finding 10:发 ws 事件让前端/运维实时看见,不再依赖 healthcheck 5min 告警
    _enqueue_ws(self.db_path, {
        "type": "scorer_error",
        "symbol": enriched.symbol,
        "error": f"{type(e).__name__}: {e}",
    })
```

`_enqueue_ws` 内部已有 try/except（Batch 2 F5 验证过），若 DB 再次 locked/异常，只 print 不再 raise，不打断 scorer loop。

## 五、Change 2 — 新建 `tests/test_v5_scorer_run_catches.py`

```python
"""V5Scorer.run 广谱 catch 现在发 ws 事件而非静默 (Finding 10)."""
import asyncio
import sqlite3
import sys
from unittest.mock import MagicMock


def _stub_ccxt():
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = MagicMock()


def test_scorer_run_catches_exception_writes_ws_event(tmp_path, monkeypatch):
    """process_enriched_v5 抛异常 → run() 捕获后写 ws_event_queue scorer_error。"""
    _stub_ccxt()
    from scripts.local_db import init_local_db
    from scripts.tasks import scorer
    from scripts.v5_types import EnrichedItem

    db = str(tmp_path / "x.db")
    init_local_db(db)

    # mock process_enriched_v5 抛异常
    async def raiser(**kwargs):
        raise RuntimeError("db locked")
    monkeypatch.setattr(scorer, "process_enriched_v5", raiser)

    # 构造 EnrichedItem — 50 flat klines, symbol BTC/USDT
    enriched = EnrichedItem(
        symbol="BTC/USDT", current_price=30000.0,
        delta_15m_pct=0.03, volume_24h_usdt=1e9,
        klines_15m=[(i, 30000.0, 30001.0, 29999.0, 30000.0, 100.0) for i in range(50)],
        klines_4h=[(i, 30000.0, 30001.0, 29999.0, 30000.0, 100.0) for i in range(50)],
    )

    # 构造 queue + V5Scorer
    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(enriched)
    scorer_obj = scorer.V5Scorer(
        enriched_queue=queue,
        ai=MagicMock(),
        paper_pm=MagicMock(),
        live_pm=MagicMock(),
        mode_resolver=lambda: "SHADOW",
        balance_fetcher=lambda: 1000.0,
        db_path=db,
    )

    # 跑 run() 一次迭代;queue 空后 .get() 会阻塞,用 timeout 打断
    async def _run_once():
        try:
            await asyncio.wait_for(scorer_obj.run(), timeout=0.5)
        except asyncio.TimeoutError:
            pass
    asyncio.run(_run_once())

    # 验证 ws_event_queue 有一条 scorer_error
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT payload_json FROM ws_event_queue"
    ).fetchone()
    conn.close()
    assert row is not None
    payload = row[0]
    assert "scorer_error" in payload
    assert "BTC/USDT" in payload
    assert "db locked" in payload
```

`V5Scorer.__init__` 签名需要对上 —— spec 撰写时依据 scorer.py L440 的构造函数：
`V5Scorer(enriched_queue, ai, paper_pm, live_pm, mode_resolver, balance_fetcher, db_path="data/rabbit_hunter.db")`

## 六、验收标准

- `python3 -m pytest tests/test_v5_scorer_run_catches.py -v` → 1/1 pass
- 邻近 tests 无回归：
  - `test_v5_scorer.py` 1/1 pass (Batch 5 F3)
  - `test_v5_position_manager.py` 8/8
  - `test_v5_position_monitor.py` 15/3
  - `test_paper_position_manager_v5.py` 4/4
  - `test_settings_db.py` 6/6
  - `test_collector_main_v5.py` 3/3
- `grep -c "_enqueue_ws" scripts/tasks/scorer.py` ≥ 2 (1 import + 1 call)
- 只 stage 2 文件（`scripts/tasks/scorer.py` + `tests/test_v5_scorer_run_catches.py`）
- Commit subject: `fix(scorer): run() 广谱 catch 发 ws scorer_error 事件,不再静默丢 item (Finding 10)`

## 七、失效模式

- **`_enqueue_ws` 本身 raise**：`_enqueue_ws` 内部有 try/except（`v5_position_monitor.py:29-30`），静默 print，不会打断 scorer loop
- **原异常的 `str(e)` 里有敏感数据**（API key 之类）：`f"{type(e).__name__}: {e}"` 会写入 ws_event_queue。若真发生 —— 已经在 print 里也写过了，不额外扩大暴露面。若未来敏感需求上升，加 sanitizer 到 `_enqueue_ws` 处理。
- **前端不 subscribe scorer_error**：本次不改前端。事件先在 queue 累积，下一批可加 badge 显示。
- **enriched.symbol 是 None**：`enriched` 是 dataclass 且 symbol 是 str，`__init__` 时不允许 None，Python 会 raise —— 不用担心。

## 八、超范围声明

- 不重构 V5Scorer 类
- 不改 process_enriched_v5
- 不加 backoff / retry
- 不新增前端 UI
- 不修其他 P1 / P2

## 九、相关

- Bug audit: `docs/audit-2026-07/bug-fix-list.md` Finding 10（P1）
- 前置 spec：Batch 2 F5 `2026-07-03-bug-fix-batch-2-F5-design.md` 建立了 `_enqueue_ws` + `monitor_degraded` ws 事件模式
- Batch 5 F3 `2026-07-04-bug-fix-batch-5-F3-design.md` 显式避开了本 catch —— F3 的 `_fetch_balance` 返 None 而非 raise，就是为了不被 Finding 10 吞掉
- 引用文件：
  - `scripts/tasks/scorer.py:456-465`（当前 catch）
  - `scripts/tasks/v5_position_monitor.py:15-30`（`_enqueue_ws` 定义）
