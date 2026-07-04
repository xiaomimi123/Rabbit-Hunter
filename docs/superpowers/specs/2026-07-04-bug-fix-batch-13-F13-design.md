# Bug Fix Batch 13 · Finding 13 · manual-order execute 走 M3 铁律 · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 13 (P1)

---

## 一、问题陈述

`api/routes/v5_manual_order.py:141-190` `POST /manual-order/execute`:

```python
async def execute(req: ManualOrderExecuteRequest) -> ManualOrderExecuteResponse:
    ...
    from scripts.paper_position_manager import PaperPositionManager
    pm = PaperPositionManager(db_path=_db())
    pid = pm.open_position(...)  # 直接开仓
```

不走 `scorer.py:255-406` 的任何 M3 铁律闸门:
- **enable_short_trading** 未检查 → 强制关闭 SHORT 时 UI 仍能开
- **gate_setup_enabled** 未检查 → 禁用 setup 被绕过
- **gate_daily_drawdown** 未检查 → 已亏损当日仍继续开(违日熔断)
- **gate_per_trade_risk** 未检查 → 大 size_multiplier 直接过

运营点 UI"手动开单"按钮即可绕过全部风控。风控层作为**最后一道保护**被 side channel 完全 skip。

## 二、目标

`execute()` 在调 `pm.open_position()` 之前顺序跑同一套 M3 闸门,任何 gate 抛 `IronlawViolation` → HTTP 400 + JSON detail 含 `error_kind`/`gate`/`message`,不开仓,不写库。scorer 的自动路径与 manual 路径共用同一层守卫。

## 三、范围

**In scope**:
- `api/routes/v5_manual_order.py` execute 端点加 4 道 gate(short_disabled / setup_enabled / daily_drawdown / per_trade_risk)
- Response 保持不变(200 结构不动;违规走 HTTPException 400)
- 现有 `test_execute_writes_paper_trade` 需加 `ENABLE_SHORT_TRADING=true` env(否则默认 false 会触发 SHORT 拦截)
- 新增 2 tests:SHORT 禁用 / daily drawdown 触发

**Out of scope**:
- 不检查 `_enable_auto_trading` toggle —— manual 端点的整个目的就是绕过自动开关。宪法要求"manual override auto"
- 不重构 `_build_full_context()` (仅在 execute 的返回值上做 gate)
- 不改 `gate_*` 内部
- 不改前端 UI(前端拿到 400 detail 可直接展示 error_kind)
- 不改 preview 端点(preview 不写库,信息展示层不需守卫)
- 不加 `gate_min_rr` / `gate_final_sl_ratio` / `gate_liquidation_distance`(scorer 里也是分层守卫,本次先加 audit 明确要求的 4 大)

## 四、Change 1 — 加 imports

```python
from scripts.risk_gates import (
    IronlawViolation, gate_setup_enabled,
    gate_daily_drawdown, gate_per_trade_risk,
)
from scripts.config import get_config
```

## 五、Change 2 — execute 端点在 `pm.open_position` 之前加 gate 序列

**Before**(L141-190 大致骨架):
```python
async def execute(req):
    ... _build_full_context ...
    ai = AIResult(...)
    forced_decision = Decision(should_trade=True, side=req.side, ...)
    pm = PaperPositionManager(...)
    pid = pm.open_position(...)
    ...
```

**After**(在 `pm.open_position` 之前插入 gate 序列):
```python
async def execute(req):
    ... _build_full_context ...
    ai = AIResult(...)
    forced_decision = Decision(should_trade=True, side=req.side, ...)

    # ── M3 铁律层(Finding 13):manual 与 scorer 走同一层守卫 ──
    # 1. SHORT 全局开关
    if req.side == "SHORT" and not get_config().enable_short_trading:
        raise HTTPException(
            status_code=400,
            detail={
                "error_kind": "SHORT_DISABLED",
                "gate": "enable_short_trading",
                "message": "ENABLE_SHORT_TRADING=false;SHORT 交易被全局关闭",
            },
        )

    # 2. Setup 禁用清单
    try:
        from scripts.ai.setup_type import derive_setup_type
        setup_type = derive_setup_type({
            "side": req.side,
            "rsi_15m": indicators.rsi_15m,
            "macd_hist": indicators.macd_hist_15m,
            "macd_hist_prev": indicators.macd_hist_prev_15m,
            "funding_z_score": None,  # manual 不查 funding, 与 scorer 若无 funding 一致
        })
        gate_setup_enabled(setup_type=setup_type, db_path=_db())
    except IronlawViolation as e:
        raise HTTPException(
            status_code=400,
            detail={"error_kind": e.kind, "gate": "gate_setup_enabled", "message": str(e)},
        )

    # 3. 日熔断
    try:
        from scripts.risk_gates import get_today_realized_pnl  # 若在 risk_gates
    except ImportError:
        from scripts.tasks.scorer import get_today_realized_pnl
    balance = float(os.environ.get("PAPER_INITIAL_BALANCE_USDT", "1000"))
    try:
        today_pnl = get_today_realized_pnl(_db())
        gate_daily_drawdown(equity_usdt=balance, today_realized_pnl=today_pnl)
    except IronlawViolation as e:
        raise HTTPException(
            status_code=400,
            detail={"error_kind": e.kind, "gate": "gate_daily_drawdown", "message": str(e)},
        )

    # 4. 单笔风险
    from scripts.v5_params import get_param
    cap_pct = float(get_param("v5_risk_per_trade", 0.015, float))
    sl_dist = abs(risk.entry_price - risk.sl_price) * req.sl_multiplier
    sl_dist_pct = sl_dist / max(risk.entry_price, 1e-9)
    final_size = risk.size_usdt * req.size_multiplier
    planned_loss = final_size * risk.leverage * sl_dist_pct
    try:
        gate_per_trade_risk(
            equity_usdt=balance, planned_loss_usdt=planned_loss, cap_pct=cap_pct,
        )
    except IronlawViolation as e:
        raise HTTPException(
            status_code=400,
            detail={"error_kind": e.kind, "gate": "gate_per_trade_risk", "message": str(e)},
        )

    # ── M3 通过,进入原有开仓路径 ──
    pm = PaperPositionManager(db_path=_db())
    pid = pm.open_position(...)
    ...
```

**注意**:`get_today_realized_pnl` 在 scorer 里被 import 自 `scripts.tasks.scorer` 或 helper 模块。查 scorer.py 顶层 imports:是 `from scripts.tasks.scorer import get_today_realized_pnl` 循环。正确路径由 helper 决定,plan 里落地。

## 六、Change 3 — Response schema 不动

`ManualOrderExecuteResponse` 保持,violation 走 HTTPException detail(FastAPI 会转 JSON `{"detail": {...}}`)。

## 七、Change 4 — 修 `tests/test_v5_manual_order_api.py`

- **`test_execute_writes_paper_trade`**:该 test 用 SHORT + 默认 `enable_short_trading=false` → fix 后会 400。加 `monkeypatch.setenv("ENABLE_SHORT_TRADING", "true")`(在 monkeypatch.setenv PAPER 那行之后)。
- 若 `get_config()` 用 `@lru_cache`,需 monkeypatch 之后手动 `get_config.cache_clear()`。plan 里落地。

新增 2 tests:

```python
def test_execute_blocks_short_when_disabled(app_with_db, monkeypatch):
    """SHORT + enable_short_trading=false → 400 SHORT_DISABLED, 无 INSERT。"""
    klines_15m, klines_4h = _fake_klines()
    _inject_fake_exchange(monkeypatch, klines_15m, klines_4h)
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "60")
    monkeypatch.delenv("ENABLE_SHORT_TRADING", raising=False)
    # 清 config cache 若有
    try:
        from scripts.config import get_config
        get_config.cache_clear()
    except AttributeError:
        pass

    from v5_types import AIResult
    with patch("scripts.ai.trading_assistant.TradingAssistant") as mock_ta_cls:
        mock_ta = mock_ta_cls.return_value
        mock_ta.client = object()
        mock_ta.provider = "deepseek"
        mock_ta.assistant_id = None
        mock_ta.decide = AsyncMock(return_value=AIResult(
            execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
            size_multiplier=1.0, confidence=0.7, reasoning="ok"))

        client, db = app_with_db
        r = client.post("/api/v5/manual-order/execute", json={
            "symbol": "TEST/USDT", "side": "SHORT", "size_usdt": 15.0,
            "sl_multiplier": 1.0, "tp_multiplier": 1.0, "size_multiplier": 1.0,
        })
        assert r.status_code == 400
        body = r.json()
        assert body["detail"]["error_kind"] == "SHORT_DISABLED"
        assert body["detail"]["gate"] == "enable_short_trading"

    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'").fetchone()[0]
    conn.close()
    assert n == 0, "违规 SHORT 不应产生 OPEN 记录"


def test_execute_blocks_when_daily_drawdown_exceeded(app_with_db, monkeypatch):
    """monkeypatch gate_daily_drawdown 抛 IronlawViolation → 400 DAILY_DRAWDOWN。"""
    klines_15m, klines_4h = _fake_klines()
    _inject_fake_exchange(monkeypatch, klines_15m, klines_4h)
    monkeypatch.setenv("V5_RSI_OVERBOUGHT", "60")
    monkeypatch.setenv("ENABLE_SHORT_TRADING", "true")
    try:
        from scripts.config import get_config
        get_config.cache_clear()
    except AttributeError:
        pass

    from scripts.risk_gates import IronlawViolation

    def _bang(**_):
        raise IronlawViolation("DAILY_DRAWDOWN_HIT", "day pnl -50 exceeds cap 3%")

    monkeypatch.setattr(
        "api.routes.v5_manual_order.gate_daily_drawdown", _bang,
    )

    from v5_types import AIResult
    with patch("scripts.ai.trading_assistant.TradingAssistant") as mock_ta_cls:
        mock_ta = mock_ta_cls.return_value
        mock_ta.client = object()
        mock_ta.provider = "deepseek"
        mock_ta.assistant_id = None
        mock_ta.decide = AsyncMock(return_value=AIResult(
            execute=True, sl_multiplier=1.0, tp_multiplier=1.0,
            size_multiplier=1.0, confidence=0.7, reasoning="ok"))

        client, db = app_with_db
        r = client.post("/api/v5/manual-order/execute", json={
            "symbol": "TEST/USDT", "side": "SHORT", "size_usdt": 15.0,
            "sl_multiplier": 1.0, "tp_multiplier": 1.0, "size_multiplier": 1.0,
        })
        assert r.status_code == 400
        body = r.json()
        assert body["detail"]["error_kind"] == "DAILY_DRAWDOWN_HIT"
        assert body["detail"]["gate"] == "gate_daily_drawdown"

    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'").fetchone()[0]
    conn.close()
    assert n == 0
```

## 八、验收标准

- `python3 -m pytest tests/test_v5_manual_order_api.py -v` → 4/4 pass(现有 2 修 1 + 新 2)
- `grep -c "gate_setup_enabled\|gate_daily_drawdown\|gate_per_trade_risk" api/routes/v5_manual_order.py` → 3
- `grep -c "IronlawViolation" api/routes/v5_manual_order.py` → ≥1
- `grep -c "SHORT_DISABLED" api/routes/v5_manual_order.py` → 1
- 只 stage 2 文件(`api/routes/v5_manual_order.py` + `tests/test_v5_manual_order_api.py`)
- Commit subject EXACT: `fix(v5_manual_order): execute 端点走 M3 铁律 4 层守卫 (Finding 13)`

## 九、失效模式

- **`enable_short_trading` env 与 DB 不一致**:`get_config()` 读 env,若前端配的是 DB 值,可能覆盖不齐。可接受:当前 config 只读 env(与 scorer 同源),前端改 DB 是 SettingsPage 的 UI-only,后续 batch 或独立 fix
- **`get_today_realized_pnl` 抖动**:query 抛 sqlite Error → gate 处 catch 会漏,试图 raise IronlawViolation 但异常先冒 → HTTP 500。可接受:数据库故障时,manual 也开不了(fail-closed 更安全)
- **`get_config()` 缓存**:若 lru_cache,`monkeypatch.setenv` 后需 `get_config.cache_clear()`。test 已处理
- **AI multipliers 极端值**:`req.size_multiplier=10` + `req.sl_multiplier=0.1` → planned_loss 巨大 → gate_per_trade_risk 触发。这正是我们要拦的,是 by-design。
- **`derive_setup_type` 需 funding_z_score**:manual 不查 funding, 传 None。若 derive_setup_type 强依赖会抛,check 时用 try/except 包裹 setup 分支(spec 里已做)

## 十、超范围声明

- 不检查 `_enable_auto_trading`(manual 就是 override)
- 不加 `gate_min_rr` / `gate_final_sl_ratio` / `gate_liquidation_distance`
- 不改 preview 端点
- 不改前端 UI
- 不改 config 读取来源(env vs DB 分裂另修)

## 十一、相关

- Bug audit: `docs/audit-2026-07/bug-fix-list.md` Finding 13 (P1)
- 引用:
  - `api/routes/v5_manual_order.py:141-190`(execute 现状)
  - `scripts/tasks/scorer.py:261,278,288,395-399`(scorer 里的 4 层 gate 位置)
  - `scripts/risk_gates.py`(gate 实现)
  - `scripts/config.py:44,88`(enable_short_trading 定义)
- 相关 Finding:F1(Batch 3, SL_TP_FAIL_OPEN 也是 config 侧问题)、F11(Batch 11 open_position 二次校验)
