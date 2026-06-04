"""
local_db.py — SQLite 本地数据库，替代 Supabase。

特性：
  - 单文件存储: data/rabbit_hunter.db
  - Supabase 兼容接口: .table().select().eq().execute()
  - WAL 模式，支持读写并发
  - 自动按天清理过期历史数据
  - 所有 dict/list 字段自动序列化为 JSON
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ─── 路径 ─────────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent
_DB_DIR = _ROOT / "data"
_DB_PATH = _DB_DIR / "rabbit_hunter.db"

# ─── 数据保留天数 ──────────────────────────────────────────────────────────────

RETENTION_DAYS = {
    "trade_scores_v43": 30,
    "market_snapshot": 7,
    "paper_trades": 90,
    # positions_v43: OPEN 永久保留，CLOSED 保留 90 天（见 prune_old_data）
}

# ─── 建表 SQL ─────────────────────────────────────────────────────────────────

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS trade_scores_v43 (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol                   TEXT    NOT NULL UNIQUE,
    final_score              REAL,
    structure_score          REAL,
    volatility_score         REAL,
    sentiment_score          REAL,
    manipulation_score       REAL,
    phase                    TEXT,
    side                     TEXT,
    strategy_id              TEXT,
    should_trade             INTEGER DEFAULT 1,
    block_reason             TEXT,
    confidence               REAL,
    position_size_multiplier REAL,
    features                 TEXT,
    decision_policy          TEXT,
    reason                   TEXT,
    ai_reasoning             TEXT,
    ai_sl_multiplier         REAL,
    ai_tp_multiplier         REAL,
    price                    REAL,
    created_at               TEXT,
    updated_at               TEXT
);

CREATE TABLE IF NOT EXISTS positions_v43 (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol           TEXT    NOT NULL,
    side             TEXT,
    entry_price      REAL,
    current_price    REAL,
    position_size    REAL,
    leverage         INTEGER DEFAULT 10,
    stop_price       REAL,
    take_profit      REAL,
    atr_k            REAL,
    status           TEXT    DEFAULT 'OPEN',
    phase            TEXT,
    phase_age        INTEGER,
    order_id         TEXT,
    pnl              REAL,
    pnl_percent      REAL,
    exit_reason      TEXT,
    closed_at        TEXT,
    strategy_id      TEXT,
    ai_confidence    REAL,
    ai_sl_multiplier REAL,
    ai_tp_multiplier REAL,
    created_at       TEXT,
    updated_at       TEXT
);

CREATE TABLE IF NOT EXISTS ai_weights_v43 (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    weights             TEXT,
    rationale           TEXT,
    applied             INTEGER DEFAULT 0,
    performance_context TEXT,
    created_at          TEXT,
    updated_at          TEXT
);

CREATE TABLE IF NOT EXISTS market_snapshot (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT    NOT NULL UNIQUE,
    price        REAL,
    funding_rate REAL,
    oi_value     REAL,
    ls_ratio     REAL,
    phase        TEXT,
    created_at   TEXT,
    updated_at   TEXT
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT,
    side        TEXT,
    entry_price REAL,
    exit_price  REAL,
    pnl         REAL,
    pnl_percent REAL,
    strategy_id TEXT,
    reason      TEXT,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS system_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT
);
"""

# ─── 连接管理 ─────────────────────────────────────────────────────────────────

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _DB_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(_SCHEMA)
        _conn.commit()
        print(f"[LocalDB] SQLite 初始化完成: {_DB_PATH}")
    return _conn


# ─── 自动清理 ─────────────────────────────────────────────────────────────────

def prune_old_data() -> None:
    """删除超过保留期的历史数据，每天运行一次即可。"""
    conn = get_connection()
    with _lock:
        for table, days in RETENTION_DAYS.items():
            try:
                conn.execute(
                    f"DELETE FROM {table} WHERE DATE(created_at) < DATE('now', ?)",
                    (f"-{days} days",),
                )
            except Exception as e:
                print(f"[LocalDB] 清理 {table} 失败: {e}")
        # positions_v43：只清理 CLOSED 超过 90 天的记录
        try:
            conn.execute(
                "DELETE FROM positions_v43 WHERE status='CLOSED' AND DATE(created_at) < DATE('now', '-90 days')"
            )
        except Exception as e:
            print(f"[LocalDB] 清理 positions_v43 失败: {e}")
        conn.commit()
    print("[LocalDB] 自动清理完成")


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def _serialize(row: dict) -> dict:
    """将 dict/list 字段序列化为 JSON 字符串，并注入时间戳。"""
    now = datetime.now(timezone.utc).isoformat()
    result = {}
    for k, v in row.items():
        if isinstance(v, (dict, list)):
            result[k] = json.dumps(v, ensure_ascii=False)
        elif v is True:
            result[k] = 1
        elif v is False:
            result[k] = 0
        else:
            result[k] = v
    if "created_at" not in result:
        result["created_at"] = now
    result["updated_at"] = now
    return result


def _deserialize_row(row: dict) -> dict:
    """尝试将 JSON 字符串字段还原为 Python 对象。"""
    result = {}
    for k, v in row.items():
        if isinstance(v, str) and v and v[0] in ('{', '['):
            try:
                result[k] = json.loads(v)
            except Exception:
                result[k] = v
        else:
            result[k] = v
    return result


# ─── Supabase 兼容查询构建器 ──────────────────────────────────────────────────

class _Result:
    def __init__(self, data: list[dict]):
        self.data = data


class _Query:
    """
    模拟 Supabase Python 客户端的 fluent 接口，内部使用 SQLite。

    支持的操作：
      .select()  .eq()  .neq()  .gte()  .lte()
      .order()   .limit()
      .insert()  .upsert()  .update()  .delete()
      .execute()
    """

    def __init__(self, conn: sqlite3.Connection, table: str):
        self._conn = conn
        self._table = table
        self._op: str = "select"
        self._cols: str = "*"
        self._where: list[tuple[str, str, Any]] = []
        self._order_col: Optional[str] = None
        self._order_desc: bool = False
        self._limit_n: Optional[int] = None
        self._offset_n: Optional[int] = None
        self._data: Optional[dict | list] = None
        self._on_conflict: Optional[str] = None

    # ── 过滤器 ────────────────────────────────────────────────────────────────

    def select(self, cols: str = "*") -> "_Query":
        self._op = "select"
        self._cols = cols
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._where.append((col, "=", val))
        return self

    def neq(self, col: str, val: Any) -> "_Query":
        self._where.append((col, "!=", val))
        return self

    def gte(self, col: str, val: Any) -> "_Query":
        self._where.append((col, ">=", val))
        return self

    def lte(self, col: str, val: Any) -> "_Query":
        self._where.append((col, "<=", val))
        return self

    def order(self, col: str, desc: bool = False) -> "_Query":
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n: int) -> "_Query":
        self._limit_n = n
        return self

    def offset(self, n: int) -> "_Query":
        self._offset_n = n
        return self

    # ── 写操作 ────────────────────────────────────────────────────────────────

    def insert(self, data: dict | list) -> "_Query":
        self._op = "insert"
        self._data = data
        return self

    def upsert(self, data: dict | list, on_conflict: Optional[str] = None) -> "_Query":
        self._op = "upsert"
        self._data = data
        self._on_conflict = on_conflict
        return self

    def update(self, data: dict) -> "_Query":
        self._op = "update"
        self._data = data
        return self

    def delete(self) -> "_Query":
        self._op = "delete"
        return self

    # ── 执行 ──────────────────────────────────────────────────────────────────

    def execute(self) -> _Result:
        with _lock:
            if self._op == "select":
                return self._do_select()
            elif self._op == "insert":
                return self._do_insert()
            elif self._op == "upsert":
                return self._do_upsert()
            elif self._op == "update":
                return self._do_update()
            elif self._op == "delete":
                return self._do_delete()
            raise ValueError(f"未知操作: {self._op}")

    def _where_clause(self) -> tuple[str, list]:
        if not self._where:
            return "", []
        parts = [f"{col} {op} ?" for col, op, _ in self._where]
        vals = [v for _, _, v in self._where]
        return "WHERE " + " AND ".join(parts), vals

    def _do_select(self) -> _Result:
        where_sql, params = self._where_clause()
        order_sql = ""
        if self._order_col:
            order_sql = f"ORDER BY {self._order_col} {'DESC' if self._order_desc else 'ASC'}"
        limit_sql = f"LIMIT {self._limit_n}" if self._limit_n else ""
        offset_sql = f"OFFSET {self._offset_n}" if self._offset_n else ""
        sql = f"SELECT {self._cols} FROM {self._table} {where_sql} {order_sql} {limit_sql} {offset_sql}"
        cur = self._conn.execute(sql, params)
        rows = [_deserialize_row(dict(r)) for r in cur.fetchall()]
        return _Result(rows)

    def _do_insert(self) -> _Result:
        rows = self._data if isinstance(self._data, list) else [self._data]
        inserted = []
        for row in rows:
            row = _serialize(row)
            cols = ", ".join(row.keys())
            placeholders = ", ".join("?" * len(row))
            sql = f"INSERT OR IGNORE INTO {self._table} ({cols}) VALUES ({placeholders})"
            self._conn.execute(sql, list(row.values()))
            inserted.append(row)
        self._conn.commit()
        return _Result(inserted)

    def _do_upsert(self) -> _Result:
        rows = self._data if isinstance(self._data, list) else [self._data]
        upserted = []
        for row in rows:
            row = _serialize(row)
            cols = ", ".join(row.keys())
            placeholders = ", ".join("?" * len(row))
            # 排除 id 和 created_at，避免覆盖原始值
            update_sets = ", ".join(
                f"{k}=excluded.{k}"
                for k in row
                if k not in ("id", "created_at")
            )
            sql = (
                f"INSERT INTO {self._table} ({cols}) VALUES ({placeholders}) "
                f"ON CONFLICT DO UPDATE SET {update_sets}"
            )
            self._conn.execute(sql, list(row.values()))
            upserted.append(row)
        self._conn.commit()
        return _Result(upserted)

    def _do_update(self) -> _Result:
        data = _serialize(self._data)
        data.pop("created_at", None)  # 不覆盖创建时间
        where_sql, where_params = self._where_clause()
        set_clauses = ", ".join(f"{k}=?" for k in data)
        sql = f"UPDATE {self._table} SET {set_clauses} {where_sql}"
        self._conn.execute(sql, list(data.values()) + where_params)
        self._conn.commit()
        return _Result([])

    def _do_delete(self) -> _Result:
        where_sql, params = self._where_clause()
        sql = f"DELETE FROM {self._table} {where_sql}"
        self._conn.execute(sql, params)
        self._conn.commit()
        return _Result([])


# ─── 公开接口 ─────────────────────────────────────────────────────────────────

class LocalDB:
    """
    Supabase 客户端的本地 SQLite 替代品。
    所有调用 supabase.table(...) 的地方换成 db.table(...) 即可。
    """

    def __init__(self):
        self._conn = get_connection()

    def table(self, name: str) -> _Query:
        return _Query(self._conn, name)


# 模块级单例
_instance: Optional[LocalDB] = None


def get_local_db() -> LocalDB:
    global _instance
    if _instance is None:
        _instance = LocalDB()
    return _instance
