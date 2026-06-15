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
    "trade_scores_v5": 30,
    "paper_trades": 90,
    "ai_training_data": 30,
    # positions_v5: OPEN 永久保留，CLOSED 保留 90 天（见 prune_old_data）
}

# ─── 建表 SQL ─────────────────────────────────────────────────────────────────

# V5 新表 schema
_V5_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trade_scores_v5 (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol              TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    delta_15m_pct       REAL,
    volume_24h_usdt     REAL,
    rsi_15m             REAL,
    macd_15m            REAL,
    macd_signal_15m     REAL,
    macd_hist_15m       REAL,
    macd_hist_prev_15m  REAL,
    rsi_4h              REAL,
    macd_hist_4h        REAL,
    atr_15m             REAL,
    current_price       REAL,
    should_trade        INTEGER DEFAULT 0,
    side                TEXT,
    reasoning           TEXT,
    block_reason        TEXT,
    ai_confidence       REAL,
    ai_sl_multiplier    REAL,
    ai_tp_multiplier    REAL,
    ai_size_multiplier  REAL,
    ai_reasoning        TEXT,
    ai_decision_id      INTEGER,
    entry_price         REAL,
    sl_price            REAL,
    tp_price            REAL,
    size_usdt           REAL,
    expected_rr         REAL,
    executed            INTEGER DEFAULT 0,
    position_id         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_trade_scores_v5_symbol_created
    ON trade_scores_v5(symbol, created_at);
CREATE INDEX IF NOT EXISTS idx_trade_scores_v5_executed
    ON trade_scores_v5(executed, created_at);
CREATE INDEX IF NOT EXISTS idx_trade_scores_v5_should_trade
    ON trade_scores_v5(should_trade, created_at);

CREATE TABLE IF NOT EXISTS positions_v5 (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol              TEXT NOT NULL,
    side                TEXT NOT NULL,
    status              TEXT NOT NULL,
    entry_price         REAL,
    entry_time          TEXT,
    sl_price            REAL,
    tp_price            REAL,
    size_usdt           REAL,
    leverage            INTEGER,
    position_size_coins REAL,
    target_close_at     TEXT,
    extension_count     INTEGER DEFAULT 0,
    entry_rsi_15m       REAL,
    entry_macd_hist_15m REAL,
    entry_rsi_4h        REAL,
    entry_atr_15m       REAL,
    exit_price          REAL,
    exit_time           TEXT,
    exit_reason         TEXT,
    pnl_usdt            REAL,
    pnl_pct             REAL,
    holding_minutes     REAL,
    source_score_id     INTEGER,
    ai_decision_id      INTEGER,
    created_at          TEXT,
    updated_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_positions_v5_status_symbol
    ON positions_v5(status, symbol);
CREATE INDEX IF NOT EXISTS idx_positions_v5_status_entry
    ON positions_v5(status, entry_time);
CREATE INDEX IF NOT EXISTS idx_positions_v5_exit_time
    ON positions_v5(exit_time);

CREATE TABLE IF NOT EXISTS ai_training_data (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at               TEXT,
    symbol                   TEXT,
    side                     TEXT,
    entry_price              REAL,
    entry_rsi_15m            REAL,
    entry_macd_hist_15m      REAL,
    entry_rsi_4h             REAL,
    delta_15m_pct            REAL,
    ai_reasoning             TEXT,
    exit_price               REAL,
    exit_reason              TEXT,
    holding_minutes          REAL,
    pnl_pct                  REAL,
    outcome                  TEXT,
    uploaded_to_vector_store INTEGER DEFAULT 0,
    uploaded_at              TEXT
);

CREATE TABLE IF NOT EXISTS system_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS ws_event_queue (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    payload_json TEXT NOT NULL,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reflection_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_trade_id INTEGER NOT NULL UNIQUE,
    enqueued_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    error TEXT,
    retry_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_reflection_queue_pending
    ON reflection_queue(completed_at, retry_count)
    WHERE completed_at IS NULL;

CREATE TABLE IF NOT EXISTS reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_trade_id INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    why_entered TEXT NOT NULL,
    what_was_expected TEXT NOT NULL,
    what_actually_happened TEXT NOT NULL,
    correction_idea TEXT NOT NULL,
    failure_mode_key TEXT,
    setup_type TEXT NOT NULL,
    outcome_class TEXT NOT NULL,
    realized_r REAL NOT NULL,
    holding_minutes INTEGER NOT NULL,
    confidence_at_entry REAL NOT NULL,
    self_assessed_prediction_accuracy REAL,
    is_in_predicted_failure_mode INTEGER,
    ai_provider TEXT,
    ai_model TEXT,
    ai_latency_ms INTEGER,
    prompt_version TEXT,
    raw_response_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_reflections_setup_type
    ON reflections(setup_type, created_at);

CREATE TABLE IF NOT EXISTS failure_taxonomy (
    key TEXT PRIMARY KEY,
    label_zh TEXT NOT NULL,
    label_en TEXT NOT NULL,
    description TEXT NOT NULL,
    detection_rule TEXT,
    is_active INTEGER DEFAULT 1,
    sample_count INTEGER DEFAULT 0,
    avg_loss_pct REAL,
    last_seen_at TEXT,
    seeded INTEGER DEFAULT 0,
    approved_by TEXT,
    approved_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS setup_performance_daily (
    date TEXT NOT NULL,
    setup_type TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    win_count INTEGER NOT NULL,
    loss_count INTEGER NOT NULL,
    scratch_count INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    avg_realized_r REAL NOT NULL,
    avg_holding_minutes REAL,
    expectancy REAL,
    sharpe_30d REAL,
    top_failure_mode TEXT,
    PRIMARY KEY (date, setup_type)
);

CREATE TABLE IF NOT EXISTS position_sizing_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setup_type TEXT NOT NULL,
    proposed_at TEXT DEFAULT (datetime('now')),
    current_size_multiplier REAL NOT NULL,
    recommended_size_multiplier REAL NOT NULL,
    confidence_score REAL NOT NULL,
    rationale TEXT NOT NULL,
    sample_count_30d INTEGER,
    sample_count_60d INTEGER,
    sample_count_90d INTEGER,
    kelly_f_30d REAL,
    kelly_f_60d REAL,
    kelly_f_90d REAL,
    fractional_kelly_applied REAL,
    status TEXT DEFAULT 'pending',
    user_decision_at TEXT,
    user_decision_note TEXT,
    user_modified_value REAL,
    ab_test_started_at TEXT,
    ab_test_target_sample INTEGER,
    ab_test_result TEXT
);

CREATE TABLE IF NOT EXISTS ai_confidence_calibration (
    ai_model TEXT NOT NULL,
    confidence_bucket REAL NOT NULL,
    predicted_win_rate REAL NOT NULL,
    actual_win_rate REAL NOT NULL,
    sample_count INTEGER NOT NULL,
    calibration_multiplier REAL NOT NULL,
    last_updated TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (ai_model, confidence_bucket)
);
"""

# V4.3/V4.4 废弃表列表 — init_local_db 会 DROP
_V43_TABLES_TO_DROP = [
    "trade_scores_v43",
    "positions_v43",
    "ai_weights_v43",
    "market_snapshot",
]

# paper_trades V5 新增字段
_PAPER_TRADES_V5_COLUMNS = [
    ("target_close_at",     "TEXT"),
    ("extension_count",     "INTEGER DEFAULT 0"),
    ("entry_rsi_15m",       "REAL"),
    ("entry_macd_hist_15m", "REAL"),
    ("entry_rsi_4h",        "REAL"),
    ("entry_atr_15m",       "REAL"),
    ("ai_decision_id",      "INTEGER"),
    ("source_score_id",     "INTEGER"),
]

# paper_trades 完整建表 SQL（供 init_local_db 在新 DB 上建表用）
_PAPER_TRADES_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS paper_trades (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol              TEXT    NOT NULL,
    side                TEXT,                    -- LONG / SHORT
    entry_price         REAL,
    entry_time          TEXT,
    current_price       REAL,                    -- 实时跟踪用
    exit_price          REAL,
    exit_time           TEXT,
    exit_reason         TEXT,                    -- TP_HIT / SL_HIT / HORIZON_TIMEOUT / MANUAL
    status              TEXT    DEFAULT 'OPEN',  -- OPEN / CLOSED
    -- 风险参数（开仓时锁定）
    stop_loss           REAL,
    take_profit         REAL,
    atr_k               REAL,
    position_size_usdt  REAL,                    -- 虚拟仓位价值
    leverage            INTEGER DEFAULT 10,
    horizon_hours       INTEGER DEFAULT 24,
    -- 来源信号
    strategy_id         TEXT,
    signal_score        REAL,
    source_score_id     INTEGER,                 -- 关联 trade_scores_v5.id
    -- AI 决策快照
    ai_confidence       REAL,
    ai_sl_multiplier    REAL,
    ai_tp_multiplier    REAL,
    ai_reason           TEXT,
    reason              TEXT,                    -- 总体说明
    -- 结算
    pnl                 REAL,                    -- 虚拟 PnL（USDT）
    pnl_percent         REAL,                    -- 虚拟收益率
    holding_hours       REAL,
    created_at          TEXT,
    updated_at          TEXT
);
"""

# 沿用旧连接初始化的 _SCHEMA（保留 PRAGMA + paper_trades + system_settings 供 get_connection 用）
_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

-- v0.5.4：paper_trades 大幅扩展 — 之前 9 列只够离线回测；现在要支持在线 SHADOW
-- 模式实时开虚拟仓 + 跟踪 SL/TP 触发 + 结算
CREATE TABLE IF NOT EXISTS paper_trades (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol              TEXT    NOT NULL,
    side                TEXT,                    -- LONG / SHORT
    entry_price         REAL,
    entry_time          TEXT,
    current_price       REAL,                    -- 实时跟踪用
    exit_price          REAL,
    exit_time           TEXT,
    exit_reason         TEXT,                    -- TP_HIT / SL_HIT / HORIZON_TIMEOUT / MANUAL
    status              TEXT    DEFAULT 'OPEN',  -- OPEN / CLOSED
    -- 风险参数（开仓时锁定）
    stop_loss           REAL,
    take_profit         REAL,
    atr_k               REAL,
    position_size_usdt  REAL,                    -- 虚拟仓位价值
    leverage            INTEGER DEFAULT 10,
    horizon_hours       INTEGER DEFAULT 24,
    -- 来源信号
    strategy_id         TEXT,
    signal_score        REAL,
    source_score_id     INTEGER,                 -- 关联 trade_scores_v5.id
    -- AI 决策快照
    ai_confidence       REAL,
    ai_sl_multiplier    REAL,
    ai_tp_multiplier    REAL,
    ai_reason           TEXT,
    reason              TEXT,                    -- 总体说明
    -- 结算
    pnl                 REAL,                    -- 虚拟 PnL（USDT）
    pnl_percent         REAL,                    -- 虚拟收益率
    holding_hours       REAL,
    created_at          TEXT,
    updated_at          TEXT
);
-- 注意：paper_trades 的索引在 _apply_migrations 跑完 ALTER TABLE 之后再创建
-- （老 DB 的 paper_trades 缺 status 列，先 INDEX 会挂）

-- v0.5.3：补 created_at（_serialize 会自动注，不补会让 system_settings 写崩）
CREATE TABLE IF NOT EXISTS system_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    created_at TEXT,
    updated_at TEXT
);
"""

# ─── 连接管理 ─────────────────────────────────────────────────────────────────

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _create_post_migration_indexes(conn: sqlite3.Connection) -> None:
    """v0.5.4：依赖 ALTER TABLE 加的列的索引在这里建（必须 migration 跑完后才行）。"""
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_paper_trades_symbol     ON paper_trades(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_paper_trades_status     ON paper_trades(status)",
        "CREATE INDEX IF NOT EXISTS idx_paper_trades_created_at ON paper_trades(created_at)",
    ]
    for sql in indexes:
        try:
            conn.execute(sql)
        except Exception as e:
            print(f"[LocalDB] 索引创建跳过: {sql.split('(')[0].strip()}: {e}")


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """对已存在的 DB 做就地结构迁移。所有迁移必须是幂等的（重复跑无副作用）。"""

    # ── A) ADD COLUMN 类型 — PRAGMA 探测后再 ALTER ──────────────────────
    add_column_migrations = [
        # (表名, 列名, 列类型)
        ("positions_v43", "highest_price", "REAL"),
        ("positions_v43", "lowest_price",  "REAL"),
        # v0.5.1：market_snapshot 补 scorer._build_snapshot_row 真正写入的列
        ("market_snapshot", "risk_score",             "REAL"),
        ("market_snapshot", "risk_level",             "TEXT"),
        ("market_snapshot", "regime",                 "TEXT"),
        ("market_snapshot", "ai_score",               "REAL"),
        ("market_snapshot", "ai_allowed",             "INTEGER"),
        ("market_snapshot", "ai_reason",              "TEXT"),
        ("market_snapshot", "ai_version",             "TEXT"),
        ("market_snapshot", "p3a_match_score",        "REAL"),
        ("market_snapshot", "ai_effective_threshold", "REAL"),
        # v0.5.3：system_settings 也需要 created_at（_serialize 自动注）
        ("system_settings", "created_at",             "TEXT"),
        # v0.5.4：paper_trades 扩展 — SHADOW 模式在线 paper trading 用
        ("paper_trades", "entry_time",         "TEXT"),
        ("paper_trades", "current_price",      "REAL"),
        ("paper_trades", "exit_time",          "TEXT"),
        ("paper_trades", "exit_reason",        "TEXT"),
        ("paper_trades", "status",             "TEXT"),
        ("paper_trades", "stop_loss",          "REAL"),
        ("paper_trades", "take_profit",        "REAL"),
        ("paper_trades", "atr_k",              "REAL"),
        ("paper_trades", "position_size_usdt", "REAL"),
        ("paper_trades", "leverage",           "INTEGER"),
        ("paper_trades", "horizon_hours",      "INTEGER"),
        ("paper_trades", "signal_score",       "REAL"),
        ("paper_trades", "source_score_id",    "INTEGER"),
        ("paper_trades", "ai_confidence",      "REAL"),
        ("paper_trades", "ai_sl_multiplier",   "REAL"),
        ("paper_trades", "ai_tp_multiplier",   "REAL"),
        ("paper_trades", "ai_reason",          "TEXT"),
        ("paper_trades", "holding_hours",      "REAL"),
        ("paper_trades", "updated_at",         "TEXT"),
        # v0.5.4：scorer 实际写入 trade_scores_v43 的字段 schema 没有 — 写时全静默挂
        ("trade_scores_v43", "weights",                   "TEXT"),
        ("trade_scores_v43", "weights_version",           "TEXT"),
        ("trade_scores_v43", "ai_decision_id",            "INTEGER"),
        ("trade_scores_v43", "opportunity_density_score", "REAL"),
        ("trade_scores_v43", "executed",                  "INTEGER"),
        ("trade_scores_v43", "strategy_score",            "REAL"),
        # ai_training_data 也缺 scorer 写的两列
        ("ai_training_data", "p3a_match_score",        "REAL"),
        ("ai_training_data", "ai_effective_threshold", "REAL"),
    ]
    for table, column, col_type in add_column_migrations:
        try:
            cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        except Exception as e:
            print(f"[LocalDB] 迁移探测失败 {table}: {e}")
            continue
        if column in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            print(f"[LocalDB] 迁移：已为 {table} 增加列 {column} {col_type}")
        except Exception as e:
            print(f"[LocalDB] 迁移失败 {table}.{column}: {e}")

    # ── B) trade_scores_v43 — 去掉 symbol 的 UNIQUE 约束（变 append-only） ─
    # SQLite 不支持 DROP CONSTRAINT，得 RENAME + 新建 + 复制 + DROP
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='trade_scores_v43'"
        ).fetchone()
        if row and row["sql"]:
            create_sql = row["sql"]
            # 检测 "symbol ... UNIQUE" 模式（容忍空格 / 换行 / 大小写）
            symbol_line = ""
            for line in create_sql.splitlines():
                low = line.lower()
                if "symbol" in low and ("text" in low or "varchar" in low):
                    symbol_line = low
                    break
            if "unique" in symbol_line:
                print("[LocalDB] 迁移：检测到 trade_scores_v43.symbol UNIQUE — 开始重建")
                _rebuild_trade_scores_v43_drop_unique(conn)
    except Exception as e:
        print(f"[LocalDB] trade_scores_v43 UNIQUE 检测失败: {e}")


def _rebuild_trade_scores_v43_drop_unique(conn: sqlite3.Connection) -> None:
    """RENAME 旧表 → CREATE 新表（无 UNIQUE）→ INSERT SELECT → DROP 旧表。
    用事务保证整个过程原子，失败回滚。"""
    new_table_sql = """
        CREATE TABLE trade_scores_v43 (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol                   TEXT    NOT NULL,
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
        )
    """
    try:
        old_cols = [
            r["name"]
            for r in conn.execute("PRAGMA table_info(trade_scores_v43)").fetchall()
        ]
    except Exception as e:
        print(f"[LocalDB] 读取旧 trade_scores_v43 列失败，跳过重建: {e}")
        return

    # 计算新表的列（去掉 id）
    new_cols = [
        "symbol", "final_score", "structure_score", "volatility_score", "sentiment_score",
        "manipulation_score", "phase", "side", "strategy_id", "should_trade", "block_reason",
        "confidence", "position_size_multiplier", "features", "decision_policy", "reason",
        "ai_reasoning", "ai_sl_multiplier", "ai_tp_multiplier", "price", "created_at", "updated_at",
    ]
    common_cols = [c for c in new_cols if c in old_cols]
    if not common_cols:
        print("[LocalDB] 旧表无可迁移列，跳过 — 留作手动处理")
        return

    col_csv = ", ".join(common_cols)
    try:
        conn.execute("BEGIN")
        conn.execute("ALTER TABLE trade_scores_v43 RENAME TO trade_scores_v43_old_unique")
        conn.execute(new_table_sql)
        conn.execute(
            f"INSERT INTO trade_scores_v43 ({col_csv}) SELECT {col_csv} FROM trade_scores_v43_old_unique"
        )
        conn.execute("DROP TABLE trade_scores_v43_old_unique")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_scores_v43_symbol ON trade_scores_v43(symbol)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_scores_v43_created_at ON trade_scores_v43(created_at)")
        conn.commit()
        print(f"[LocalDB] 迁移：trade_scores_v43 重建完成，迁移列 {len(common_cols)} 个")
    except Exception as e:
        conn.rollback()
        print(f"[LocalDB] trade_scores_v43 重建失败已回滚: {e}")


def init_local_db(db_path: str = "data/rabbit_hunter.db") -> None:
    """初始化 V5 schema。
    1. 检测旧 V43 表 → DROP
    2. 建 V5 表
    3. paper_trades 加 V5 字段
    4. ai_training_data 老 schema 不兼容 → 重建
    """
    import os
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        # 1. DROP 旧 V43/V44 表
        for table in _V43_TABLES_TO_DROP:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        # ai_training_data 老 schema 不兼容，DROP 重建
        conn.execute("DROP TABLE IF EXISTS ai_training_data")

        # 2. 建 V5 表
        conn.executescript(_V5_SCHEMA_SQL)

        # 3. paper_trades 表：旧表存在则 ALTER，不存在则 CREATE
        existing = {row[1] for row in conn.execute("PRAGMA table_info(paper_trades)")}
        if not existing:
            conn.executescript(_PAPER_TRADES_CREATE_SQL)
            existing = {row[1] for row in conn.execute("PRAGMA table_info(paper_trades)")}
        for col, col_type in _PAPER_TRADES_V5_COLUMNS:
            if col not in existing:
                conn.execute(f"ALTER TABLE paper_trades ADD COLUMN {col} {col_type}")

        # 4. system_settings 清掉 V43/V44 key（表存在时才清）
        ss_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='system_settings'"
        ).fetchone()
        if ss_exists:
            conn.execute("""
                DELETE FROM system_settings
                WHERE key LIKE 'ai_weights_v43%'
                   OR key LIKE 'v44_%'
                   OR key LIKE 'v43_%'
            """)

        _seed_failure_taxonomy(conn)
        conn.commit()
    finally:
        conn.close()


def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _DB_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(_SCHEMA)
        _apply_migrations(_conn)
        _create_post_migration_indexes(_conn)
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
    def __init__(self, data: list[dict], count: Optional[int] = None):
        self.data = data
        # v0.5.1：兼容 supabase-py 的 .select(count="exact") 返回的 .count 属性
        self.count = count


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

    def select(self, cols: str = "*", count: Optional[str] = None) -> "_Query":
        """v0.5.1: 增加 count 关键字兼容 supabase-py 的 .select("*", count="exact")。
        count 值此处实际不影响 SQL 生成 — _Result.count 会在 execute() 时填上。"""
        self._op = "select"
        self._cols = cols
        self._count_mode = count
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

    def range(self, start: int, end: int) -> "_Query":
        """Supabase-py 的 `.range(start, end)` 兼容（包含上下界）→ offset+limit。

        v0.5.1：kill_queue_manager 用 .range() 做分页，之前 LocalDB 没实现导致
        AttributeError，让 /api/v43/kill-queue 永远返回 dataFreshness=ERROR。
        """
        self._offset_n = max(0, int(start))
        self._limit_n = max(0, int(end) - int(start) + 1)
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

        # v0.5.1：若 .select(count="exact") 被调用，再额外跑一次 COUNT(*) 拿总数
        total_count: Optional[int] = None
        if getattr(self, "_count_mode", None) == "exact":
            try:
                count_sql = f"SELECT COUNT(*) AS c FROM {self._table} {where_sql}"
                row = self._conn.execute(count_sql, params).fetchone()
                total_count = int(row["c"]) if row else 0
            except Exception:
                total_count = None
        return _Result(rows, count=total_count)

    def _do_insert(self) -> _Result:
        """普通 INSERT — 不带 OR IGNORE。

        v45 前为 INSERT OR IGNORE，配合 trade_scores_v43.symbol UNIQUE 导致每个 symbol
        只保留首条记录。现在 trade_scores_v43 已经是 append-only（UNIQUE 已被迁移移除），
        若有 UNIQUE 冲突应该噪声暴露而不是静默丢数据。需要"upsert"语义时显式调 upsert()。"""
        rows = self._data if isinstance(self._data, list) else [self._data]
        inserted = []
        for row in rows:
            row = _serialize(row)
            cols = ", ".join(row.keys())
            placeholders = ", ".join("?" * len(row))
            sql = f"INSERT INTO {self._table} ({cols}) VALUES ({placeholders})"
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


def enqueue_reflection(paper_trade_id: int, *, db_path: str = "data/rabbit_hunter.db") -> None:
    """关仓后入队 reflection。idempotent — 重复入队同一 paper_trade 安全忽略。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO reflection_queue (paper_trade_id) VALUES (?)",
            (paper_trade_id,),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_failure_taxonomy(conn) -> None:
    """Idempotent — INSERT OR IGNORE 8 预置失败模式。"""
    from scripts.ai.failure_taxonomy_seed import SEEDS
    for s in SEEDS:
        conn.execute("""
            INSERT OR IGNORE INTO failure_taxonomy
                (key, label_zh, label_en, description, detection_rule,
                 seeded, approved_by, approved_at)
            VALUES (?, ?, ?, ?, ?, 1, 'system', datetime('now'))
        """, (s["key"], s["label_zh"], s["label_en"],
              s["description"], s["detection_rule"]))
