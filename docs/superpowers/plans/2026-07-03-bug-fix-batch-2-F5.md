# Bug Fix Batch 2 · F5 monitor silent live_pm None · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修 `V5PositionMonitor._tick` 在 `live_pm=None` 时静默 return —— 新增 `_resolve_pm(mode)` sync helper 做 WARN 日志 + `get_trader()` 重试 + 失败时写 `ws_event_queue` `monitor_degraded` 事件。

**Architecture:** 单 task TDD 循环：先写 5 个 unit test 直接测新 helper（RED —— helper 尚不存在）→ 加 `_resolve_pm` 方法 + `_tick` 内 1 行调用点改造 → GREEN → sanity → 单 commit。

**Tech Stack:** Python + pytest + `monkeypatch` + `:memory:` / `tmp_path` sqlite。无新增 pip 依赖。

## Global Constraints

- Only 2 files touched: `scripts/v5_position_monitor.py` + `tests/test_v5_position_monitor.py`
- **`V5PositionMonitor.__init__` 签名不变**（保持 `(paper_pm, live_pm, ai_assistant, indicator_fetcher, mode_resolver, poll_interval_s=30, db_path=...)`）
- **`_tick()` 主体不动**（只改 pm 解析那 4 行）
- **不改**：`scripts/tasks/scorer.py`, `scripts/v5_position_manager.py`, `scripts/exchange_factory.py`, `scripts/paper_position_manager.py`, `.githooks/`, dev-log
- 3 条 pre-existing SIGNAL_REVERSE 测试失败**不改动**（超范围；确认它们数量不变）
- 新增 helper 名称：`V5PositionMonitor._resolve_pm(mode: str) -> Optional[Any]`
- ws 事件格式：`{"type": "monitor_degraded", "reason": "live_pm_unavailable", "error": "..."}`
- Commit subject: `fix(v5_monitor): 抽 _resolve_pm helper 让 live_pm=None 时能恢复 + 5 tests (F5)`

---

## File Structure

| 路径 | 动作 |
|---|---|
| `scripts/v5_position_monitor.py` | Add `_resolve_pm(mode)` method 在 `_tick` 前；Modify `_tick` L184-187 的 4 行 |
| `tests/test_v5_position_monitor.py` | Add `_make_monitor` helper；Add 5 new `test_resolve_pm_*` tests |

---

# Task 1: `_resolve_pm` helper + `_tick` 改造 + 5 unit tests

**Files:**
- Modify: `scripts/v5_position_monitor.py`（新增 `_resolve_pm` 方法 + 改 `_tick` 内 pm 解析）
- Modify: `tests/test_v5_position_monitor.py`（顶部 import + `_make_monitor` helper + 5 tests）

**Interfaces:**
- Consumes: `scripts.exchange_factory.get_trader`, `scripts.v5_position_manager.V5PositionManager`（延迟 import 在 helper 内）
- Produces: `V5PositionMonitor._resolve_pm(mode: str) -> Optional[Any]` sync method
- `V5PositionMonitor.__init__` 签名不变

## RED phase — 先写测试让它 fail

- [ ] **Step 1: 顶部 import + `_make_monitor` helper**

在 `tests/test_v5_position_monitor.py` 头部（现有 imports 之后、`_open_position` 之前）追加：

```python
from unittest.mock import MagicMock


def _make_monitor(paper_pm=None, live_pm=None, db_path=":memory:"):
    """构造最小 V5PositionMonitor,测 _resolve_pm 时不需要真实依赖。

    db_path=:memory: 用于不涉及 ws_event_queue 的路径；否则传 tmp_path 建的真库。
    """
    from scripts.v5_position_monitor import V5PositionMonitor
    from scripts.local_db import init_local_db
    if db_path != ":memory:":
        init_local_db(db_path)
    return V5PositionMonitor(
        paper_pm=paper_pm or MagicMock(),
        live_pm=live_pm,
        ai_assistant=MagicMock(),
        indicator_fetcher=MagicMock(),
        mode_resolver=lambda: "LIVE",
        db_path=db_path,
    )
```

- [ ] **Step 2: 追加 5 个 test 到文件末尾**

```python


def test_resolve_pm_shadow_returns_paper():
    paper = MagicMock(name="paper")
    monitor = _make_monitor(paper_pm=paper, live_pm=None)
    assert monitor._resolve_pm("SHADOW") is paper


def test_resolve_pm_live_returns_live_when_set():
    live = MagicMock(name="live")
    monitor = _make_monitor(paper_pm=MagicMock(), live_pm=live)
    assert monitor._resolve_pm("LIVE") is live


def test_resolve_pm_live_recovers_via_get_trader(tmp_path, monkeypatch):
    """live_pm=None + get_trader mock 返 fake trader → self.live_pm 被替换。"""
    from scripts.local_db import init_local_db
    db = str(tmp_path / "test.db")
    init_local_db(db)

    monitor = _make_monitor(live_pm=None, db_path=db)

    fake_trader = MagicMock(name="trader")
    monkeypatch.setattr(
        "scripts.exchange_factory.get_trader", lambda: fake_trader
    )
    result = monitor._resolve_pm("LIVE")

    assert result is monitor.live_pm     # 已被替换
    assert monitor.live_pm is not None   # 显式再断一次


def test_resolve_pm_live_fails_emits_ws_event(tmp_path, monkeypatch):
    """get_trader 返 None → 返 None + ws_event_queue 一行 monitor_degraded。"""
    import sqlite3
    from scripts.local_db import init_local_db
    db = str(tmp_path / "test.db")
    init_local_db(db)

    monitor = _make_monitor(live_pm=None, db_path=db)
    monkeypatch.setattr(
        "scripts.exchange_factory.get_trader", lambda: None
    )

    result = monitor._resolve_pm("LIVE")
    assert result is None

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT payload_json FROM ws_event_queue"
    ).fetchone()
    conn.close()
    assert row is not None
    assert "monitor_degraded" in row[0]
    assert "live_pm_unavailable" in row[0]


def test_resolve_pm_live_recovery_exception_still_returns_none(tmp_path, monkeypatch):
    """get_trader 抛异常 → helper 不抛,返 None + ws 事件里 error 字段非空。"""
    import sqlite3
    from scripts.local_db import init_local_db
    db = str(tmp_path / "test.db")
    init_local_db(db)

    monitor = _make_monitor(live_pm=None, db_path=db)

    def raiser():
        raise RuntimeError("network timeout")
    monkeypatch.setattr("scripts.exchange_factory.get_trader", raiser)

    result = monitor._resolve_pm("LIVE")
    assert result is None

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT payload_json FROM ws_event_queue"
    ).fetchone()
    conn.close()
    assert row is not None
    assert "RuntimeError" in row[0]
    assert "network timeout" in row[0]
```

- [ ] **Step 3: 跑测试 —— 期望 RED**

Run:
```bash
python3 -m pytest tests/test_v5_position_monitor.py -v -k "resolve_pm"
```

Expected: 5 tests all FAIL —— 因为 `V5PositionMonitor` 尚无 `_resolve_pm` 属性 → `AttributeError`。

**这就是我们要证明的 gap**：helper 不存在，测试立刻暴露。

Also confirm no unintended regression on non-`_resolve_pm` tests:
```bash
python3 -m pytest tests/test_v5_position_monitor.py -v 2>&1 | tail -6
```
Expected 状况: 5 new FAIL + 9 pre-existing PASS + 3 pre-existing FAIL（SIGNAL_REVERSE 相关，不动）。

## GREEN phase — 加 helper + 改 _tick

- [ ] **Step 4: 在 `_tick` 前新增 `_resolve_pm` 方法**

Read `scripts/v5_position_monitor.py` L155-185 找到 `class V5PositionMonitor` + `__init__` + `run()` + `_tick`。在 `run()` 后、`_tick` 前插入：

```python
    def _resolve_pm(self, mode: str):
        """解析本 tick 用哪个 pm。LIVE 且 live_pm=None 时尝试恢复。

        Returns pm or None (caller should skip this tick if None).
        恢复失败会写 ws_event_queue monitor_degraded 事件。
        """
        if mode == "SHADOW":
            return self.paper_pm

        # LIVE 分支
        if self.live_pm is not None:
            return self.live_pm

        # live_pm=None → 尝试重建
        print("[V5PositionMonitor] WARN: LIVE mode but live_pm is None; "
              "attempting trader re-init")
        try:
            from scripts.exchange_factory import get_trader
            from scripts.v5_position_manager import V5PositionManager
            trader = get_trader()
        except Exception as e:
            print(f"[V5PositionMonitor] trader re-init failed: "
                  f"{type(e).__name__}: {e}")
            _enqueue_ws(self.db_path, {
                "type": "monitor_degraded",
                "reason": "live_pm_unavailable",
                "error": f"{type(e).__name__}: {e}",
            })
            return None

        if trader is None:
            _enqueue_ws(self.db_path, {
                "type": "monitor_degraded",
                "reason": "live_pm_unavailable",
                "error": "get_trader() returned None",
            })
            return None

        self.live_pm = V5PositionManager(broker=trader, db_path=self.db_path)
        print("[V5PositionMonitor] LIVE trader re-init OK; resuming monitoring")
        return self.live_pm
```

- [ ] **Step 5: 改 `_tick` 的 pm 解析（L184-187）**

找到 `_tick` 开头的 4 行：

```python
async def _tick(self):
    mode = self.resolve_mode()
    pm = self.paper_pm if mode == "SHADOW" else self.live_pm
    if not pm:
        return
```

改为：

```python
async def _tick(self):
    mode = self.resolve_mode()
    pm = self._resolve_pm(mode)
    if pm is None:
        return
```

（`_tick` 剩余部分 `for position in pm.get_open_positions(): ...` 一字不改）

- [ ] **Step 6: 跑测试 —— 期望 GREEN**

```bash
python3 -m pytest tests/test_v5_position_monitor.py -v -k "resolve_pm"
```
Expected: 5/5 PASS

```bash
python3 -m pytest tests/test_v5_position_monitor.py -v 2>&1 | tail -6
```
Expected: `14 passed, 3 failed` —— 5 new + 9 existing PASS；3 pre-existing SIGNAL_REVERSE FAIL 数目不变。

若 `_resolve_pm` 测试有 fail：
- `shadow_returns_paper` / `live_returns_live_when_set`：Step 4 helper 的 if 分支写错
- `recovers_via_get_trader`：可能 monkeypatch 生效但没赋值 self.live_pm，检查 Step 4 里 `self.live_pm = V5PositionManager(...)`
- `fails_emits_ws_event` / `recovery_exception_still_returns_none`：ws 事件没进 db，检查 `_enqueue_ws` 调用（helper 内应传 `self.db_path` 和有 `type/reason/error` 三键的 dict）
- Regression（if 已有的 9 pass 变少）：可能 `_tick` 改动误伤，重新对齐 Step 5

## Sanity + commit

- [ ] **Step 7: sanity greps**

```bash
# _tick 里现在应该是 `if pm is None:`（显式）
grep -n "if not pm" scripts/v5_position_monitor.py
# 期望: 0 hits

# _resolve_pm 应该 grep 得到（helper 存在）
grep -n "def _resolve_pm" scripts/v5_position_monitor.py
# 期望: 1 hit

# _tick 应该调用 helper
grep -n "self._resolve_pm(mode)" scripts/v5_position_monitor.py
# 期望: 1 hit
```

- [ ] **Step 8: 邻近测试无回归**

```bash
python3 -m pytest tests/test_v5_position_manager.py tests/test_paper_position_manager_v5.py -v 2>&1 | tail -5
```
Expected: 全 PASS（batch 1 的 3 tests + paper_position_manager tests）

- [ ] **Step 9: Commit**

```bash
git add scripts/v5_position_monitor.py tests/test_v5_position_monitor.py
git commit -m "$(cat <<'EOF'
fix(v5_monitor): 抽 _resolve_pm helper 让 live_pm=None 时能恢复 + 5 tests (F5)

修 bug-fix-list.md Finding 5：V5PositionMonitor._tick 之前遇到
live_pm=None（LIVE mode 但 trader 初始化失败）会直接 return,
所有 LIVE 仓位监控静默停摆。

Change:
- 新增 _resolve_pm(mode) sync helper：SHADOW → paper_pm；LIVE →
  live_pm；LIVE + None → WARN + get_trader() 重试 → 成功替换
  self.live_pm；失败写 ws_event_queue monitor_degraded 事件返 None
- _tick 内 pm 解析改为 pm = self._resolve_pm(mode); if pm is None: return
  （其余主体不动）

Tests:
- 追加 5 个 sync unit test 直接测 helper
- 现有 check_exit_triggers 测试原样保留
- 3 条 pre-existing SIGNAL_REVERSE 失败超范围,数量不变

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

# Self-Review 记录

- **spec § 五 Change 1**：Step 4 (_resolve_pm 全部逻辑) + Step 5 (_tick 4 行改) ✓
- **spec § 六 Change 2**：Step 1 (_make_monitor + import) + Step 2 (5 tests) ✓
- **spec § 七 验收标准**：
  - Step 6 跑 5/5 pass + 全文件 14 pass / 3 pre-existing fail ✓
  - Step 7 sanity greps 全 ✓
  - 只 stage 2 文件（Step 9）✓
  - `__init__` 签名不变（Step 4 只加 method）✓
- **spec § 八 失效模式**：
  - `get_trader()` 抛异常 → Step 4 内 try 覆盖 → 走 ws + return None ✓
  - `V5PositionManager()` 构造抛异常 → 外层 try 覆盖 ✓
  - db 写失败 → `_enqueue_ws` 已有 try/except（文件顶部 L15-30 现有）✓
- **spec § 九 超范围**：
  - collector_main.py 不动（Step 4/5 只在 monitor 文件里改）✓
  - 3 pre-existing fail 不动（Step 6 验证数量不变）✓
  - `_tick` 主体不动（Step 5 只改前 4 行）✓
- **Placeholder scan**：无 TBD/TODO；每 step 有完整代码或命令 ✓
- **Type consistency**：`_resolve_pm(mode: str)` 签名在 spec + plan + test 里一致；ws 事件 key `type/reason/error` 一致 ✓
