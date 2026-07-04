# Bug Fix Batch 6 · Finding 10 · V5Scorer.run 广谱 catch 发 ws 事件 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `V5Scorer.run()` L456-465 广谱 `except Exception` 里在 print 之后新增一条 `ws_event_queue scorer_error` 事件写入，让前端/运维实时可见异常，不再静默丢弃 item。

**Architecture:** 单 task TDD 循环：先写 1 integration test（asyncio + queue + timeout 跑一次 iteration）→ RED（当前 catch 只 print，无 ws 记录）→ 加 import + 3 行 `_enqueue_ws` 调用 → GREEN → 邻近 tests 回归 → 单 commit。

**Tech Stack:** Python stdlib (asyncio, sqlite3) + pytest + monkeypatch。复用 `scripts/v5_position_monitor._enqueue_ws`（Batch 2 F5 建立）。无新增 pip 依赖。

## Global Constraints

- Only 2 files touched: `scripts/tasks/scorer.py` (modify) + `tests/test_v5_scorer_run_catches.py` (create)
- Import 路径 EXACT: `from scripts.v5_position_monitor import _enqueue_ws`（注意 monitor 在 `scripts/` 不在 `scripts/tasks/`）
- ws 事件 payload EXACT: `{"type": "scorer_error", "symbol": <str>, "error": "<TypeName>: <msg>"}`
- `V5Scorer.run()` 结构不动 —— 只在 catch 块 print 之后追加 3 行
- 不改 `process_enriched_v5` 内部
- 不改 `_enqueue_ws` 内部（它已有自己的 try/except 保护）
- 不抽 `_process_one` helper（用户选 minimal，不 refactor）
- Do NOT touch: 其他 P0 已修文件、`.githooks/`、dev-log、前端
- 现有测试无回归:
  - `test_v5_scorer.py` 1/1 (Batch 5 F3)
  - `test_v5_position_manager.py` 8/8
  - `test_v5_position_monitor.py` 15 pass / 3 pre-existing SIGNAL_REVERSE fail
  - `test_paper_position_manager_v5.py` 4/4
  - `test_settings_db.py` 6/6
  - `test_collector_main_v5.py` 3/3
- Single commit, subject: `fix(scorer): run() 广谱 catch 发 ws scorer_error 事件,不再静默丢 item (Finding 10)`

---

## File Structure

| 路径 | 动作 |
|---|---|
| `scripts/tasks/scorer.py` | Modify — 顶部加 `from scripts.v5_position_monitor import _enqueue_ws`；catch 块（现 L464-465）追加 3 行 `_enqueue_ws(...)` |
| `tests/test_v5_scorer_run_catches.py` | Create — 1 integration test 覆盖异常 → ws 事件路径 |

---

# Task 1: import _enqueue_ws + catch 块加 ws 事件 + 1 test

**Files:**
- Modify: `scripts/tasks/scorer.py`
- Create: `tests/test_v5_scorer_run_catches.py`

**Interfaces:**
- Consumes: `scripts.v5_position_monitor._enqueue_ws(db_path: str, payload: dict) -> None`（已在 Batch 2 F5 建立）
- Produces: 无新对外 API；`ws_event_queue.payload_json` 新增 `type='scorer_error'` 值

## RED phase — 先写 test 让它 fail

- [ ] **Step 1: 建 `tests/test_v5_scorer_run_catches.py`**

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

    # 构造 EnrichedItem — 50 flat klines 保证 indicator engine 不会先 fail
    enriched = EnrichedItem(
        symbol="BTC/USDT", current_price=30000.0,
        delta_15m_pct=0.03, volume_24h_usdt=1e9,
        klines_15m=[(i, 30000.0, 30001.0, 29999.0, 30000.0, 100.0) for i in range(50)],
        klines_4h=[(i, 30000.0, 30001.0, 29999.0, 30000.0, 100.0) for i in range(50)],
    )

    # 构造 queue + V5Scorer,queue 里塞 1 个 item
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

- [ ] **Step 2: 跑 test —— 期望 RED**

```bash
python3 -m pytest tests/test_v5_scorer_run_catches.py -v
```

Expected: FAIL —— 断言 `row is not None` 失败（现有 catch 只 print，不写 ws 事件）。或断言 `"scorer_error" in payload` 失败（若 row 存在但内容不同）。

## GREEN phase — 加 import + 3 行 _enqueue_ws

- [ ] **Step 3: 在 `scripts/tasks/scorer.py` 顶部 imports 后追加 _enqueue_ws import**

现有顶部有 `import` 和 `from ...` 语句。在其后（可以是 imports 块底部）追加：

```python
from scripts.v5_position_monitor import _enqueue_ws
```

**注意路径**：`v5_position_monitor` 在 `scripts/` 而不是 `scripts/tasks/`。

- [ ] **Step 4: 改 `V5Scorer.run()` 的 catch 块（L456-465 附近）**

用 unique substring `except Exception as e:` 找到位置（该文件里可能有多处 `except Exception as e:` —— 用更长 anchor 定位到 `V5Scorer.run()` 内的那一处，比如结合前后行 `await process_enriched_v5(` 或者 `[V5Scorer]`）。

**Before**（L464-465 附近）：
```python
            except Exception as e:
                print(f"[V5Scorer] {enriched.symbol} 处理异常: {type(e).__name__}: {e}")
```

**After**：
```python
            except Exception as e:
                print(f"[V5Scorer] {enriched.symbol} 处理异常: {type(e).__name__}: {e}")
                # Finding 10:发 ws 事件让前端/运维实时看见,不再依赖 healthcheck 5min 告警
                _enqueue_ws(self.db_path, {
                    "type": "scorer_error",
                    "symbol": enriched.symbol,
                    "error": f"{type(e).__name__}: {e}",
                })
```

- [ ] **Step 5: 跑 test —— 期望 GREEN**

```bash
python3 -m pytest tests/test_v5_scorer_run_catches.py -v
```

Expected: 1/1 PASS。

若失败：
- 断言 `"scorer_error" in payload` FAIL → 检查 Step 4 payload dict 的 `type` 字段值
- 断言 `"BTC/USDT" in payload` FAIL → 检查 `symbol` 字段
- 断言 `"db locked" in payload` FAIL → 检查 `error` 字段 f-string 拼装
- 断言 `row is not None` FAIL → 检查 `_enqueue_ws` 是否真被调用（是否走进 except 块）；检查 `self.db_path` 是不是传对了

## 邻近回归 + sanity + commit

- [ ] **Step 6: 跑邻近 tests**

```bash
python3 -m pytest tests/test_v5_scorer.py tests/test_v5_position_manager.py tests/test_v5_position_monitor.py tests/test_paper_position_manager_v5.py tests/test_settings_db.py tests/test_collector_main_v5.py -v 2>&1 | tail -15
```

Expected:
- `test_v5_scorer.py` 1/1 PASS（Batch 5 F3 —— balance-None test）
- `test_v5_position_manager.py` 8/8 PASS（Batch 1 + 4）
- `test_v5_position_monitor.py` 15 PASS / 3 pre-existing FAIL（SIGNAL_REVERSE 超范围，数量不变）
- `test_paper_position_manager_v5.py` all PASS
- `test_settings_db.py` 6/6 PASS
- `test_collector_main_v5.py` 3/3 PASS

- [ ] **Step 7: sanity greps**

```bash
# _enqueue_ws 在 scorer 里有 2 次引用(1 import + 1 call)
grep -c "_enqueue_ws" scripts/tasks/scorer.py
# 期望：≥ 2

# scorer_error 关键词
grep -n "scorer_error" scripts/tasks/scorer.py
# 期望：1 hit (payload dict 里的 type 值)

# import 语句
grep -n "from scripts.v5_position_monitor import _enqueue_ws" scripts/tasks/scorer.py
# 期望：1 hit
```

- [ ] **Step 8: Commit**

```bash
git add scripts/tasks/scorer.py tests/test_v5_scorer_run_catches.py
git commit -m "$(cat <<'EOF'
fix(scorer): run() 广谱 catch 发 ws scorer_error 事件,不再静默丢 item (Finding 10)

修 bug-fix-list.md Finding 10:V5Scorer.run() L456-464 except Exception
仅 print 后 continue,任何未预期异常(SQLite database is locked / AI
timeout / 等) → item 无 trade_scores_v5 记录,healthcheck 5min 告警
可能延迟。Batch 5 F3 特意避开了这个陷阱(_fetch_balance 返 None 不 raise),
现在正面修。

Change:
- 顶部加 from scripts.v5_position_monitor import _enqueue_ws
  (反向 import monitor,复用 Batch 2 F5 建立的 ws bus)
- V5Scorer.run() catch 块 print 后加 _enqueue_ws({
    "type": "scorer_error", "symbol": ..., "error": ...
  })
- _enqueue_ws 内部有自己的 try/except (Batch 2 F5 验证过),
  即便 DB 再 locked 也不会二次抛断 loop
- 未 refactor V5Scorer 类结构 (P1 minimal)

Tests:
- 新增 tests/test_v5_scorer_run_catches.py 1 integration test
  用 asyncio.Queue + timeout 跑 run() 一次迭代验证 ws 事件
- 现有 1+8+15+4+6+3 tests 无回归
  (SIGNAL_REVERSE 3 pre-existing 仍在)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

# Self-Review 记录

- **spec § 四 Change 1 (import + catch 块)**：Step 3 (import) + Step 4 (catch 块 3 行) ✓
- **spec § 五 Change 2 (1 test)**：Step 1 完整实现 ✓
- **spec § 六 验收**：Step 2 (RED) + Step 5 (GREEN 1/1) + Step 6 (邻近回归) + Step 7 (sanity) ✓
- **spec § 七 失效模式**：`_enqueue_ws` 内 try/except 已存在（不打断 loop）；str(e) 可能含敏感数据 —— spec 声明可接受不扩大暴露面 ✓
- **placeholder scan**：无 TBD / TODO ✓
- **type consistency**：`_enqueue_ws(db_path: str, payload: dict) -> None` 签名与 monitor 里定义一致；payload 里 `type` / `symbol` / `error` 三键在 spec + plan + test 都一致 ✓
- **测试 RED→GREEN**：Step 2 = RED（1 FAIL）；Step 5 = GREEN（1/1 PASS）✓
- **atomicity**：单 commit at Step 8 ✓
- **import path 校对**：`from scripts.v5_position_monitor import _enqueue_ws`（而非 `scripts.tasks.v5_position_monitor`），已在 Global Constraints + Step 3 显式强调 ✓
