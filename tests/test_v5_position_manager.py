"""V5PositionManager 测试 — broker 用 mock,只测 fail-closed 逻辑。"""
import pytest
from unittest.mock import MagicMock


def test_sl_tp_failure_rollbacks_main():
    """主仓开成功,SL 单失败 → 立刻市价平回滚。"""
    from scripts.v5_position_manager import V5PositionManager

    mock_broker = MagicMock()
    mock_broker.create_order.side_effect = [
        {"orderId": "main", "status": "filled"},
        Exception("SL order failed: insufficient margin"),
    ]
    mock_broker.close_position = MagicMock()

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

    mock_broker = MagicMock()
    mock_broker.create_order.return_value = {"orderId": "x", "status": "filled"}

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
