"""V5PositionManager 测试 — broker 用 mock,只测 fail-closed 逻辑。"""
import sys
import pytest
from unittest.mock import MagicMock

# ccxt 在 CI / 本地可能未安装；用 MagicMock stub 让 OkxTrader 可导入（只用它的类 spec）
if "ccxt" not in sys.modules:
    sys.modules["ccxt"] = MagicMock()
from scripts.okx_trader import OkxTrader


def test_sl_tp_failure_rollbacks_main():
    """主仓开成功,SL 单失败 → 立刻市价平回滚。"""
    from scripts.v5_position_manager import V5PositionManager

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.open_position.return_value = {
        "success": True, "order_id": "main", "symbol": "H/USDT", "side": "SHORT",
    }
    mock_broker.set_stop_loss.return_value = {
        "success": False, "error": "insufficient margin", "error_kind": "PERMANENT",
    }
    mock_broker.close_position.return_value = {
        "success": True, "order_id": "rb", "symbol": "H/USDT",
    }

    pm = V5PositionManager(broker=mock_broker, db_path=":memory:")

    with pytest.raises(Exception, match="SL"):
        pm.open_position(
            symbol="H/USDT", side="SHORT", entry_price=0.166,
            sl_price=0.169, tp_price=0.162, size_usdt=15, leverage=10,
        )
    mock_broker.close_position.assert_called_once()


def test_successful_open_writes_positions_v5():
    """都成功 → 写 positions_v5 一行,status=OPEN。"""
    import sqlite3, tempfile
    from scripts.local_db import init_local_db
    from scripts.v5_position_manager import V5PositionManager

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    init_local_db(tmp.name)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.open_position.return_value = {
        "success": True, "order_id": "main", "symbol": "H/USDT", "side": "SHORT",
    }
    mock_broker.set_stop_loss.return_value = {
        "success": True, "order_id": "sl", "symbol": "H/USDT",
    }
    mock_broker.set_take_profit.return_value = {
        "success": True, "order_id": "tp", "symbol": "H/USDT",
    }

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


def test_broker_missing_method_fails_fast():
    """spec=OkxTrader 拦住任何 attribute 打错的 bug（F4 类回归防护）."""
    mock_broker = MagicMock(spec=OkxTrader)
    # OkxTrader 上没有 create_order 方法。spec mock 应拒绝这个访问。
    with pytest.raises(AttributeError):
        mock_broker.create_order(symbol="H/USDT", side="sell")


# ── F2 close_position 分支测试 ─────────────────

def _seeded_open_position(db_path: str) -> int:
    """辅助:插一条 status=OPEN 的 LIVE 记录,返回 position_id。"""
    from unittest.mock import MagicMock
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.open_position.return_value = {"success": True, "order_id": "x"}
    mock_broker.set_stop_loss.return_value = {"success": True, "order_id": "sl"}
    mock_broker.set_take_profit.return_value = {"success": True, "order_id": "tp"}
    pm = V5PositionManager(broker=mock_broker, db_path=db_path)
    return pm.open_position(
        symbol="H/USDT", side="SHORT", entry_price=0.166,
        sl_price=0.169, tp_price=0.162, size_usdt=15, leverage=10,
    )


def test_close_success_marks_closed(tmp_path):
    """broker.close_position 返 success=True → DB 标 CLOSED,PnL 有值。"""
    import sqlite3
    from unittest.mock import MagicMock
    from scripts.local_db import init_local_db
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    db = str(tmp_path / "x.db")
    init_local_db(db)
    pid = _seeded_open_position(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.close_position.return_value = {"success": True, "order_id": "rb"}
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, exit_price, exit_reason FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == "CLOSED"
    assert row[1] == 0.163
    assert row[2] == "TP_HIT"


def test_close_broker_permanent_still_marks_closed(tmp_path):
    """PERMANENT (交易所已平) → DB 补记 CLOSED,exit_reason 追加 broker_permanent。"""
    import sqlite3
    from unittest.mock import MagicMock
    from scripts.local_db import init_local_db
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    db = str(tmp_path / "x.db")
    init_local_db(db)
    pid = _seeded_open_position(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.close_position.return_value = {
        "success": False, "error_kind": "PERMANENT",
        "error": "position not found on exchange",
    }
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, exit_reason FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == "CLOSED"
    assert "broker_permanent" in row[1]
    assert "not found" in row[1]


def test_close_broker_retryable_keeps_open(tmp_path):
    """RETRYABLE → 保持 OPEN + error_context 有 RETRYABLE close_error。"""
    import sqlite3
    import json
    from unittest.mock import MagicMock
    from scripts.local_db import init_local_db
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    db = str(tmp_path / "x.db")
    init_local_db(db)
    pid = _seeded_open_position(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.close_position.return_value = {
        "success": False, "error_kind": "RETRYABLE",
        "error": "network timeout",
    }
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, error_context FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == "OPEN"
    ctx = json.loads(row[1])
    assert ctx["close_error"]["kind"] == "RETRYABLE"
    assert "network timeout" in ctx["close_error"]["msg"]


def test_close_broker_exception_marks_reconcile(tmp_path):
    """broker.close_position 抛异常 → ERROR_RECONCILE_NEEDED + error_context 含 UNKNOWN。"""
    import sqlite3
    import json
    from unittest.mock import MagicMock
    from scripts.local_db import init_local_db
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    db = str(tmp_path / "x.db")
    init_local_db(db)
    pid = _seeded_open_position(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.close_position.side_effect = RuntimeError("unexpected explode")
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, error_context FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == "ERROR_RECONCILE_NEEDED"
    ctx = json.loads(row[1])
    assert ctx["close_error"]["kind"] == "UNKNOWN"
    assert "unexpected explode" in ctx["close_error"]["msg"]


def test_close_success_after_retryable_clears_stale_error_context(tmp_path):
    """RETRYABLE 后再次调 close 成功 → CLOSED 记录 error_context 不带 stale close_error。"""
    import sqlite3
    import json
    from unittest.mock import MagicMock
    from scripts.local_db import init_local_db
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    db = str(tmp_path / "x.db")
    init_local_db(db)
    pid = _seeded_open_position(db)

    # 第一次:RETRYABLE
    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.close_position.return_value = {
        "success": False, "error_kind": "RETRYABLE", "error": "timeout",
    }
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    # 确认 stale close_error 在
    conn = sqlite3.connect(db)
    ctx_json = conn.execute(
        "SELECT error_context FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()[0]
    conn.close()
    assert "close_error" in json.loads(ctx_json)

    # 第二次:success → CLOSED,stale 应被清
    mock_broker2 = MagicMock(spec=OkxTrader)
    mock_broker2.close_position.return_value = {"success": True, "order_id": "rb2"}
    pm2 = V5PositionManager(broker=mock_broker2, db_path=db)
    pm2.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, error_context FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == "CLOSED"
    # error_context 应为 None (清空后我们存 NULL) 或不含 close_error 键
    if row[1] is not None:
        assert "close_error" not in json.loads(row[1])


def test_close_success_uses_broker_fill_price(tmp_path):
    """F14: broker 返 {'success':True, 'price':0.99} → DB exit_price=0.99 (非 caller 0.163) + source=broker_fill。"""
    import sqlite3
    import json
    from unittest.mock import MagicMock
    from scripts.local_db import init_local_db
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    db = str(tmp_path / "x.db")
    init_local_db(db)
    pid = _seeded_open_position(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.close_position.return_value = {"success": True, "price": 0.99, "order_id": "rb"}
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT exit_price, error_context FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == 0.99, "应用 broker fill price 0.99, 非 caller 传入 0.163"
    ctx = json.loads(row[1])
    assert ctx["exit_price_source"] == "broker_fill"


def test_close_success_no_broker_price_falls_back_to_caller(tmp_path):
    """F14: broker 返 success 但无 price 字段 → fallback caller's exit_price + source=monitor_tick。"""
    import sqlite3
    import json
    from unittest.mock import MagicMock
    from scripts.local_db import init_local_db
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    db = str(tmp_path / "x.db")
    init_local_db(db)
    pid = _seeded_open_position(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.close_position.return_value = {"success": True, "order_id": "rb"}  # 无 price
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT exit_price, error_context FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == 0.163, "无 price → fallback caller"
    ctx = json.loads(row[1])
    assert ctx["exit_price_source"] == "monitor_tick"


def test_close_permanent_marks_monitor_tick_permanent_source(tmp_path):
    """F14: PERMANENT (交易所已平) → 用 caller exit_price + source=monitor_tick_permanent。"""
    import sqlite3
    import json
    from unittest.mock import MagicMock
    from scripts.local_db import init_local_db
    from scripts.okx_trader import OkxTrader
    from scripts.v5_position_manager import V5PositionManager

    db = str(tmp_path / "x.db")
    init_local_db(db)
    pid = _seeded_open_position(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.close_position.return_value = {
        "success": False, "error_kind": "PERMANENT",
        "error": "position not found on exchange",
    }
    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pm.close_position(pid, exit_price=0.163, exit_reason="TP_HIT")

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, exit_price, error_context FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == "CLOSED"
    assert row[1] == 0.163
    ctx = json.loads(row[2])
    assert ctx["exit_price_source"] == "monitor_tick_permanent"


# ── 保命核实 · open_position 失败链条(rollback 成功已有,补 3 条) ─────────


def test_sl_fail_rollback_also_fails_marks_reconcile_needed(tmp_path, monkeypatch):
    """主仓 success + SL fail + rollback fail → 写 ERROR_RECONCILE_NEEDED + 抛异常。

    保命场景:交易所有主仓,我们没 SL,回滚 close 也挂了 → 必须留 DB 记录
    让人工介入,不能悄悄放过。
    """
    import sqlite3
    import json
    from scripts.local_db import init_local_db
    from scripts.v5_position_manager import V5PositionManager

    monkeypatch.setenv("SL_TP_FAIL_OPEN", "false")
    db = str(tmp_path / "x.db")
    init_local_db(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.open_position.return_value = {
        "success": True, "order_id": "main", "symbol": "H/USDT",
    }
    mock_broker.set_stop_loss.return_value = {
        "success": False, "error": "SL insufficient margin", "error_kind": "PERMANENT",
    }
    mock_broker.close_position.return_value = {
        "success": False, "error": "rollback network timeout", "error_kind": "TRANSIENT",
    }

    pm = V5PositionManager(broker=mock_broker, db_path=db)
    with pytest.raises(Exception, match="SL 失败且回滚失败"):
        pm.open_position(
            symbol="H/USDT", side="SHORT", entry_price=0.166,
            sl_price=0.169, tp_price=0.162, size_usdt=15, leverage=10,
        )

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, sl_attached, tp_attached, error_context "
        "FROM positions_v5 WHERE status='ERROR_RECONCILE_NEEDED'"
    ).fetchone()
    conn.close()
    assert row is not None, "必须留 ERROR_RECONCILE_NEEDED 记录让人工介入"
    assert row[0] == "ERROR_RECONCILE_NEEDED"
    assert row[1] == 0  # sl_attached=False
    assert row[2] == 0  # tp_attached=False
    ctx = json.loads(row[3])
    assert "sl_error" in ctx
    assert "SL insufficient margin" in ctx["sl_error"]
    assert "rollback_error" in ctx
    assert "rollback network timeout" in ctx["rollback_error"]


def test_tp_fail_rollback_also_fails_marks_reconcile_needed(tmp_path, monkeypatch):
    """主仓 success + SL success + TP fail + rollback fail → 写 ERROR_RECONCILE_NEEDED。

    保命场景:主仓 + SL 都成了,只差 TP 没挂上,回滚也挂 → 必须留记录人工介入。
    """
    import sqlite3
    import json
    from scripts.local_db import init_local_db
    from scripts.v5_position_manager import V5PositionManager

    monkeypatch.setenv("SL_TP_FAIL_OPEN", "false")
    db = str(tmp_path / "x.db")
    init_local_db(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.open_position.return_value = {
        "success": True, "order_id": "main", "symbol": "H/USDT",
    }
    mock_broker.set_stop_loss.return_value = {
        "success": True, "order_id": "sl", "symbol": "H/USDT",
    }
    mock_broker.set_take_profit.return_value = {
        "success": False, "error": "TP order rejected", "error_kind": "PERMANENT",
    }
    mock_broker.close_position.return_value = {
        "success": False, "error": "rollback timeout", "error_kind": "TRANSIENT",
    }

    pm = V5PositionManager(broker=mock_broker, db_path=db)
    with pytest.raises(Exception, match="TP 失败且回滚失败"):
        pm.open_position(
            symbol="H/USDT", side="SHORT", entry_price=0.166,
            sl_price=0.169, tp_price=0.162, size_usdt=15, leverage=10,
        )

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, sl_attached, tp_attached, error_context "
        "FROM positions_v5 WHERE status='ERROR_RECONCILE_NEEDED'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "ERROR_RECONCILE_NEEDED"
    assert row[1] == 1  # sl_attached=True (SL 成了)
    assert row[2] == 0  # tp_attached=False
    ctx = json.loads(row[3])
    assert "tp_error" in ctx
    assert "TP order rejected" in ctx["tp_error"]
    assert "rollback_error" in ctx
    assert "rollback timeout" in ctx["rollback_error"]


def test_sl_fail_with_fail_open_preserves_main_as_open_degraded(tmp_path, monkeypatch):
    """sl_tp_fail_open=true + SL fail → 保留主仓,不回滚,写 OPEN_DEGRADED。

    保命场景:运营明确开启 fail-open,SL 挂不上时不平仓强行留仓,monitor 会
    继续跟踪(get_open_positions 用 status IN (OPEN, OPEN_DEGRADED))。
    """
    import sqlite3
    import json
    from scripts.local_db import init_local_db
    from scripts.v5_position_manager import V5PositionManager

    monkeypatch.setenv("SL_TP_FAIL_OPEN", "true")
    db = str(tmp_path / "x.db")
    init_local_db(db)

    mock_broker = MagicMock(spec=OkxTrader)
    mock_broker.open_position.return_value = {
        "success": True, "order_id": "main", "symbol": "H/USDT",
    }
    mock_broker.set_stop_loss.return_value = {
        "success": False, "error": "SL rejected", "error_kind": "PERMANENT",
    }
    mock_broker.set_take_profit.return_value = {
        "success": True, "order_id": "tp", "symbol": "H/USDT",
    }

    pm = V5PositionManager(broker=mock_broker, db_path=db)
    pid = pm.open_position(
        symbol="H/USDT", side="SHORT", entry_price=0.166,
        sl_price=0.169, tp_price=0.162, size_usdt=15, leverage=10,
    )

    mock_broker.close_position.assert_not_called()

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, sl_attached, tp_attached, error_context "
        "FROM positions_v5 WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    assert row[0] == "OPEN_DEGRADED"
    assert row[1] == 0  # sl_attached=False
    assert row[2] == 1  # tp_attached=True
    ctx = json.loads(row[3])
    assert "sl_error" in ctx
    assert "SL rejected" in ctx["sl_error"]
    assert "rollback_error" not in ctx  # fail-open 分支不尝试回滚

    # monitor 视角:OPEN_DEGRADED 记录仍能被 get_open_positions 拉到
    opens = pm.get_open_positions()
    assert any(p["id"] == pid for p in opens), "monitor 必须能看到 OPEN_DEGRADED 继续跟踪"
