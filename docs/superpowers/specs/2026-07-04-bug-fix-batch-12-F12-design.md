# Bug Fix Batch 12 · Finding 12 · v5_position_close 支持 LIVE 分支 · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 12 (P1)

---

## 一、问题陈述

`api/routes/v5_position_close.py:43,54`:

```python
row = conn.execute("SELECT status FROM paper_trades WHERE id=?", (position_id,)).fetchone()
if row is None:
    raise HTTPException(status_code=404, ...)
...
pm = PaperPositionManager(db_path=db)
pm.close_position(position_id, ...)
```

- 只查 `paper_trades`。若 `position_id` 属于 `positions_v5`(LIVE)→ 404
- 前端 `useV5ClosePosition` hook 不区分 paper/live,两类仓位统一调该 URL
- LIVE 场景运营点"手动平仓" → 前端拿到 404 → 显示"平仓失败",而**交易所仍持有真实仓位**,SL/TP 挂单还在。运营完全无 UI 手段干预。

## 二、目标

端点先查 `paper_trades`,不存在则查 `positions_v5`。若 LIVE 命中:实例化 `get_trader()` + `V5PositionManager` 调 `close_position()`。响应加 `mode` 字段("paper" / "live"),让前端明确哪条路径被走了。

## 三、范围

**In scope**:
- `api/routes/v5_position_close.py` 重写端点:双表查询 + LIVE 分支 + `mode` 字段
- Response 加 `mode: str`(值 "paper" | "live")
- LIVE 分支后 re-read `positions_v5.status` 反映 broker 结果(CLOSED / 保持 OPEN / ERROR_RECONCILE_NEEDED)
- 新增单测 `tests/test_v5_position_close.py`(3 tests: paper 命中 / LIVE mocked trader 命中 / 双表都无 404)

**Out of scope**:
- 不改前端(`useV5ClosePosition` 不动;新 `mode` 字段是 additive,不需前端立即消费)
- 不改 `PaperPositionManager.close_position` / `V5PositionManager.close_position` 语义
- 不改 broker 抽象或 trader 工厂
- 不加 rate limit / 权限校验(现有端点无,超范围)
- 不处理 paper/live 表 id 冲突(极小概率,声明为已知失效模式)

## 四、Change 1 — Response 模型加 `mode`

**Before**:
```python
class CloseResponse(BaseModel):
    position_id: int
    status: str
    exit_price: float
    exit_reason: str
```

**After**:
```python
class CloseResponse(BaseModel):
    position_id: int
    status: str
    exit_price: float
    exit_reason: str
    mode: str = "paper"  # "paper" | "live"
```

(default "paper" 让 pydantic backward-compat)

## 五、Change 2 — 端点主体重写

**流程**:
1. 查 `paper_trades WHERE id=?`
2. 命中 → 现有 paper 流程 + `mode="paper"`
3. 未命中 → 查 `positions_v5 WHERE id=?`
4. 命中 LIVE:
   - `get_trader()` 拿 broker;失败 → 503
   - `V5PositionManager(broker=trader, db_path=db)` 构造;失败 → 503
   - 调 `live_pm.close_position(position_id, exit_price=..., exit_reason=...)`
   - re-read `positions_v5.status` → 反映实际结果
   - 返 `mode="live"` + 实际 status
5. 都没有 → 404

**代码骨架**(约 60 行,取代现 L34-69):

```python
@router.post("/positions/{position_id}/close", response_model=CloseResponse)
async def close_position(
    position_id: int = Path(...),
    body: CloseRequest = ...,
) -> CloseResponse:
    db = _db()
    conn = sqlite3.connect(db)
    paper_status: Optional[str] = None
    live_status: Optional[str] = None
    try:
        row = conn.execute(
            "SELECT status FROM paper_trades WHERE id=?", (position_id,)
        ).fetchone()
        if row is not None:
            paper_status = row[0]
        else:
            row = conn.execute(
                "SELECT status FROM positions_v5 WHERE id=?", (position_id,)
            ).fetchone()
            if row is not None:
                live_status = row[0]
    finally:
        conn.close()

    if paper_status is None and live_status is None:
        raise HTTPException(status_code=404, detail=f"position {position_id} not found")

    if paper_status is not None:
        # ── paper 分支 ─────────────────────────────────
        if (paper_status or "").upper() == "CLOSED":
            raise HTTPException(status_code=409, detail=f"position {position_id} already CLOSED")
        from scripts.paper_position_manager import PaperPositionManager
        pm = PaperPositionManager(db_path=db)
        pm.close_position(position_id, exit_price=body.exit_price, exit_reason=body.exit_reason)
        try:
            from scripts.local_db import enqueue_reflection
            enqueue_reflection(position_id, db_path=db)
        except Exception as e:
            print(f"[v5_position_close] reflection enqueue failed: {e}")
        return CloseResponse(
            position_id=position_id, status="CLOSED",
            exit_price=body.exit_price, exit_reason=body.exit_reason,
            mode="paper",
        )

    # ── LIVE 分支 ───────────────────────────────────
    if (live_status or "").upper() == "CLOSED":
        raise HTTPException(status_code=409, detail=f"position {position_id} already CLOSED")
    try:
        from scripts.exchange_factory import get_trader
        trader = get_trader()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"broker unavailable: {type(e).__name__}: {e}",
        )
    if trader is None:
        raise HTTPException(status_code=503, detail="broker unavailable: get_trader() returned None")
    try:
        from scripts.v5_position_manager import V5PositionManager
        live_pm = V5PositionManager(broker=trader, db_path=db)
        live_pm.close_position(
            position_id, exit_price=body.exit_price, exit_reason=body.exit_reason,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"live close failed: {type(e).__name__}: {e}",
        )
    # re-read: broker 结果决定 status(CLOSED / OPEN / ERROR_RECONCILE_NEEDED)
    conn = sqlite3.connect(db)
    try:
        r = conn.execute(
            "SELECT status FROM positions_v5 WHERE id=?", (position_id,)).fetchone()
    finally:
        conn.close()
    final_status = (r[0] if r else "UNKNOWN") or "UNKNOWN"
    return CloseResponse(
        position_id=position_id, status=final_status,
        exit_price=body.exit_price, exit_reason=body.exit_reason,
        mode="live",
    )
```

## 六、Change 3 — 新单测 `tests/test_v5_position_close.py`

```python
"""Batch 12 Finding 12: v5_position_close 支持 LIVE 分支。"""
import sqlite3
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _init_schema(db_path):
    """建 paper_trades + positions_v5 最小 schema。"""
    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, side TEXT, status TEXT, entry_price REAL,
            entry_time TEXT, exit_price REAL, exit_time TEXT, exit_reason TEXT,
            pnl REAL, pnl_percent REAL, holding_hours REAL,
            current_price REAL, stop_loss REAL, take_profit REAL,
            position_size_usdt REAL, leverage INTEGER,
            strategy_id TEXT, created_at TEXT, updated_at TEXT,
            source_score_id INTEGER
        );
        CREATE TABLE positions_v5 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, side TEXT, status TEXT, entry_price REAL,
            entry_time TEXT, sl_price REAL, tp_price REAL,
            sl_attached INTEGER, tp_attached INTEGER, error_context TEXT,
            size_usdt REAL, leverage INTEGER, position_size_coins REAL,
            target_close_at TEXT, extension_count INTEGER,
            created_at TEXT, updated_at TEXT,
            exit_price REAL, exit_time TEXT, exit_reason TEXT,
            pnl_realized REAL
        );
    ''')
    conn.commit()
    conn.close()


def test_close_paper_position_still_works(monkeypatch, tmp_path):
    """paper_trades 命中 → mode=paper, status=CLOSED(F12 不 regress paper 路径)。"""
    db_path = tmp_path / "test.db"
    _init_schema(str(db_path))
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO paper_trades (id, symbol, side, status, entry_price, entry_time) "
        "VALUES (1, 'BTC/USDT', 'LONG', 'OPEN', 50000, datetime('now'))"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", str(db_path))

    from api.main import app
    client = TestClient(app)
    r = client.post("/api/v5/positions/1/close",
                    json={"exit_price": 51000, "exit_reason": "MANUAL_USER"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "paper"
    assert body["position_id"] == 1


def test_close_live_position_uses_broker(monkeypatch, tmp_path):
    """positions_v5 命中 → 调 get_trader + V5PositionManager, mode=live。"""
    db_path = tmp_path / "test.db"
    _init_schema(str(db_path))
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO positions_v5 (id, symbol, side, status, entry_price, entry_time, "
        "size_usdt, leverage, position_size_coins) "
        "VALUES (100, 'BTC/USDT', 'LONG', 'OPEN', 50000, datetime('now'), 15, 10, 0.0003)"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", str(db_path))

    # Mock get_trader → 返回一个 mock broker,close_position 返回 success
    mock_trader = MagicMock()
    mock_trader.close_position = MagicMock(return_value={"success": True})

    with patch("scripts.exchange_factory.get_trader", return_value=mock_trader):
        from api.main import app
        client = TestClient(app)
        r = client.post("/api/v5/positions/100/close",
                        json={"exit_price": 51000, "exit_reason": "MANUAL_USER"})

    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "live"
    assert body["position_id"] == 100
    # broker 被真正调用过
    mock_trader.close_position.assert_called_once_with("BTC/USDT")


def test_close_position_not_found_returns_404(monkeypatch, tmp_path):
    """paper + live 都无 → 404。"""
    db_path = tmp_path / "test.db"
    _init_schema(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))

    from api.main import app
    client = TestClient(app)
    r = client.post("/api/v5/positions/999/close",
                    json={"exit_price": 51000, "exit_reason": "MANUAL_USER"})
    assert r.status_code == 404
```

## 七、验收标准

- `python3 -m pytest tests/test_v5_position_close.py -v` → 3/3 pass
- 邻近 tests 无回归:
  - `test_paper_position_manager_v5.py` 6/6 pass (Batch 11 basline)
  - 无其他 `test_v5_position*` 若已存在
- `grep -c "positions_v5" api/routes/v5_position_close.py` → ≥1
- `grep -c "get_trader\|V5PositionManager" api/routes/v5_position_close.py` → ≥2
- `grep -c '"mode"' api/routes/v5_position_close.py` → ≥2 (paper + live)
- 只 stage 2 文件(`api/routes/v5_position_close.py` + `tests/test_v5_position_close.py`)
- Commit subject EXACT: `fix(v5_position_close): 支持 LIVE 分支 + 响应加 mode 字段 (Finding 12)`

## 八、失效模式

- **paper 与 live 同 id 冲突**:paper_trades 与 positions_v5 都是 AUTOINCREMENT,理论 id 空间独立可能重复。当前实现优先 paper,live 被静默忽略。可接受:
  1. 前端调该端点时,已在 UI 上知道自己关的是哪类(list 分开显示)
  2. 生产 paper 一天几十条,positions_v5 rarely > 3 → 交叠概率极低
  3. 若真发生,只影响那 1 条 UI 平仓,不影响 monitor 自动平
- **`get_trader()` 失败**(无 API key、testnet 未配等):返 503 而非 500,前端能识别为"外部依赖不可用"。
- **broker close_position 抛异常**:返 502(bad gateway),前端知道是下游问题。
- **V5PositionManager.close_position RETRYABLE**:positions_v5 status 仍是 `'OPEN'`,response 显示 status="OPEN" + mode="live"。用户可再 retry 或等 monitor tick。UI 应根据 `mode=live && status=OPEN` 提示"broker retry pending"。
- **V5PositionManager.close_position ERROR_RECONCILE_NEEDED**:status="ERROR_RECONCILE_NEEDED",UI 应告警"需人工对账"。
- **positions_v5 表在测试环境不完整**(缺列):`SELECT status FROM positions_v5 WHERE id=?` 只查 status,不涉及其他列,鲁棒。

## 九、超范围声明

- 不改前端(useV5ClosePosition 无 `mode` 消费者但 additive 无害)
- 不加权限校验 / rate limit
- 不改 broker 抽象
- 不加 id 冲突检测(YAGNI)
- 不改 PaperPositionManager / V5PositionManager 内部

## 十、相关

- Bug audit: `docs/audit-2026-07/bug-fix-list.md` Finding 12 (P1)
- 引用:
  - `api/routes/v5_position_close.py:43,54`(现只查 paper_trades)
  - `scripts/v5_position_manager.py:310`(V5PositionManager.close_position)
  - `scripts/exchange_factory.py:40`(get_trader)
- 相关 Finding:F5(Batch 2, monitor live_pm 自愈)—— 相同 bootstrap 模式
