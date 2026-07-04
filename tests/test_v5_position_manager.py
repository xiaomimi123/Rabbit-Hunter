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
