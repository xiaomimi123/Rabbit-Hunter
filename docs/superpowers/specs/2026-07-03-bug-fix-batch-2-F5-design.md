# Bug Fix Batch 2 · F5 V5PositionMonitor silent live_pm None · Design

> 日期: 2026-07-03
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 5；`docs/superpowers/specs/2026-07-03-bug-fix-batch-1-F4-design.md`（Batch 1 已上线 → F5 现在成为真实触发路径）

---

## 一、问题陈述

`V5PositionMonitor._tick()` 在 `scripts/v5_position_monitor.py:184-187`：

```python
async def _tick(self):
    mode = self.resolve_mode()
    pm = self.paper_pm if mode == "SHADOW" else self.live_pm
    if not pm:
        return
```

当 `mode == "LIVE"` 且 `live_pm is None`（trader 初始化失败时 `collector_main.py:230-237` 把 live_pm 置 None），`_tick` 立刻返回。每 30s 一次的 tick 全 no-op：所有 LIVE 仓位的 SL/TP 触发检查、Chandelier trailing 更新、软时限平仓、SIGNAL_REVERSE 平仓全部**静默停摆**。运营看不到任何异常信号 —— log 里没输出、前端没提示。

Batch 1 前 F5 是"潜伏 P0"（因为 F4 拦住了 LIVE 开仓，永远不会有 live 仓位需要监控）。Batch 1 修好后 F5 成为真实触发路径。

## 二、目标

在 `live_pm=None` 时：
1. **可见**：至少一条 WARN 日志
2. **能恢复**：每 tick 尝试重新拿 broker（`get_trader()`），成功则替换 `self.live_pm` 继续监控
3. **不可恢复时可见**：写 `ws_event_queue` 一条 `monitor_degraded` 事件让前端/运维可查

## 三、范围

**In scope**：
- `scripts/v5_position_monitor.py` 新增 `_resolve_pm(mode)` sync helper（约 25 行）+ `_tick` 内改 1 行调用
- `tests/test_v5_position_monitor.py` 追加 5 个 unit test（都是 sync，直接测 helper）

**Out of scope**：
- 不改 `_tick()` 主体（chandelier / exit-trigger / _enqueue_ws 逻辑）
- 不改 `V5PositionManager`（已在 Batch 1 修）
- 不改 `V5PositionMonitor.__init__` 签名
- 不加 backoff / retry state（YAGNI，30s tick × network fail-fast 足够）
- 不改 `PaperPositionManager`
- 不动 monitor 已知的 3 条 pre-existing 测试失败（另一 spec）

## 四、broker & 依赖调用面

- `from scripts.exchange_factory import get_trader` —— 已存在函数，返 `OkxTrader | BinanceTrader | None`
- `from scripts.v5_position_manager import V5PositionManager` —— constructor 签名 `(broker, db_path="data/rabbit_hunter.db")`
- `_enqueue_ws(self.db_path, payload)` —— 已在文件顶部 L15-30 定义，`ws_event_queue` 表已存在

## 五、Change 1 — `scripts/v5_position_monitor.py`

### 5.1 新增 `_resolve_pm(self, mode: str)` 在 `_tick` 之前

```python
def _resolve_pm(self, mode: str):
    """解析本 tick 用哪个 pm。LIVE 且 live_pm=None 时尝试恢复。

    Returns pm (paper_pm | live_pm | new V5PositionManager) or None
    (调用方应 skip 本 tick)。恢复失败会写 ws_event_queue monitor_degraded 事件。
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

### 5.2 `_tick()` 调用点改 1 行

原 L184-187：
```python
mode = self.resolve_mode()
pm = self.paper_pm if mode == "SHADOW" else self.live_pm
if not pm:
    return
```

改为：
```python
mode = self.resolve_mode()
pm = self._resolve_pm(mode)
if pm is None:
    return
```

（`if not pm:` → `if pm is None:` 是显式化，避免 truthy 陷阱）

## 六、Change 2 — `tests/test_v5_position_monitor.py`

### 6.1 追加 5 个 unit test（都 sync，直接测 helper）

```python
from unittest.mock import MagicMock


def _make_monitor(paper_pm=None, live_pm=None, db_path=":memory:"):
    """构造最小 V5PositionMonitor，测 _resolve_pm 时不需要真实依赖。"""
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


def test_resolve_pm_shadow_returns_paper():
    paper = MagicMock(name="paper")
    monitor = _make_monitor(paper_pm=paper, live_pm=None)
    assert monitor._resolve_pm("SHADOW") is paper


def test_resolve_pm_live_returns_live_when_set():
    live = MagicMock(name="live")
    monitor = _make_monitor(paper_pm=MagicMock(), live_pm=live)
    assert monitor._resolve_pm("LIVE") is live


def test_resolve_pm_live_recovers_via_get_trader(tmp_path, monkeypatch):
    """live_pm=None，get_trader mock 返 fake trader → self.live_pm 被替换。"""
    import tempfile
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
    assert monitor.live_pm is not None   # 显式重复


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
    """get_trader 抛异常 → helper 不抛，返 None + ws 事件里 error 字段有内容。"""
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

### 6.2 现有测试不动

`check_exit_triggers` 相关测试原样保留 —— F5 fix 不触碰纯函数。

## 七、验收标准

- `python3 -m pytest tests/test_v5_position_monitor.py::test_resolve_pm -v` → 5/5 pass（用 `-k test_resolve_pm` 定位新测试）
- `python3 -m pytest tests/test_v5_position_monitor.py -v` 显示：新 5 pass + 现有 check_exit_triggers 测试全 pass。3 条 pre-existing fail 属超范围，不因本 change 增加或减少
- `grep -n "if not pm" scripts/v5_position_monitor.py` → 0 hits（`_tick` 里改成 `if pm is None`；helper 里用 `if trader is None`）
- 只 stage 2 文件（`scripts/v5_position_monitor.py` + `tests/test_v5_position_monitor.py`）
- `V5PositionMonitor.__init__` 签名不变

## 八、失效模式与降级

- **`get_trader()` 内部 network hang**：以 `get_trader` 现有实现为准（应有 timeout）；本 spec 不加超时逻辑
- **`V5PositionManager()` 构造抛异常**：外层 try 覆盖，走 ws 事件 + return None 路径
- **db 写 `ws_event_queue` 失败**：`_enqueue_ws` 内部已有 try/except（L15-30 现有代码），静默 print
- **前端不 subscribe monitor_degraded**：本次不改前端。事件先在 queue 里累积；下一批可能加前端 badge 展示

## 九、超范围声明

- 不改 collector_main.py（其 live_pm 传参逻辑不变）
- 不加 monitor 健康状态查询 API（下一批可能加）
- 不改 SHADOW 分支
- 不改 `_tick` 主体
- 不改 `.githooks/` / dev-log 机制

## 十、相关

- 前置：Batch 1 `2026-07-03-bug-fix-batch-1-F4-design.md`（F4 修好 F5 才有意义）
- 前置：Bug audit `docs/audit-2026-07/bug-fix-list.md` Finding 5
- 引用文件：
  - `scripts/v5_position_monitor.py:160-169`（constructor）
  - `scripts/v5_position_monitor.py:184-187`（_tick 现状）
  - `scripts/exchange_factory.py`（`get_trader`）
  - `scripts/v5_position_manager.py`（`V5PositionManager`）
