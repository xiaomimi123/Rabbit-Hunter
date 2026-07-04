# Bug Fix Batch 9 · Finding 7 · preview 端点改读 paper_trades 计算胜率 · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 7 (P1)

---

## 一、问题陈述

`api/routes/v5_strategy_config.py:136-149`：

```python
wins = conn.execute(
    "SELECT COUNT(*) FROM ai_training_data "
    "WHERE outcome='WIN' AND ..."
).fetchone()[0] or 0
totals = conn.execute(
    "SELECT COUNT(*) FROM ai_training_data "
    "WHERE outcome IN ('WIN','LOSS','FLAT') AND ..."
).fetchone()[0] or 0
win_rate = (wins / totals) if totals else 0.0
```

- `ai_training_data` 表本地 SQLite 永久为 0 行（已由 `dead-code-and-tables.md` 核实）
- 无论 RSI 阈值如何调，`totals=0` → `win_rate=0.0` → 端点始终返 HTTP 200 + `estimated_win_rate=0.0`
- 运营在 StrategyConfig 页调阈值 → 响应总显示 0，无法比较参数优劣，也无任何"零数据"提示

## 二、目标

改用 `paper_trades`（已有真实历史数据）计算胜率。JOIN `trade_scores_v5` 获取 `rsi_15m`，按候选 RSI 阈值过滤，`pnl > 0` 视为 WIN。响应加 `data_source` / `sample_n` 让前端区分"真实历史胜率" vs "零样本"。

## 三、范围

**In scope**：
- `api/routes/v5_strategy_config.py:136-150` 改用 `paper_trades JOIN trade_scores_v5`
- `api/schemas/v5_strategy_config.py:StrategyConfigPreviewResponse` 加 `data_source: str` + `sample_n: int` 字段
- 新增单测 `tests/test_v5_strategy_config_preview.py` —— fixture 插数据、断言胜率、断言 data_source

**Out of scope**：
- 不改 `estimated_hourly_entries`（仍读 `trade_scores_v5`，与本 Finding 无关）
- 不改 `sample_days`（同上）
- 不改前端（V5StrategyConfigPage 已删除, 见 git status D 行；本 fix 是 API 侧,前端后续单独做）
- 不给 `paper_trades` 加 `entry_rsi_15m` 冗余列（能 JOIN 就够）
- 不删除 `ai_training_data` 表（还有其他消费者/未来复用）

## 四、Change 1 — `api/schemas/v5_strategy_config.py`

**Before**：
```python
class StrategyConfigPreviewResponse(BaseModel):
    """回测预览。"""
    candidate_params: dict[str, float]
    estimated_hourly_entries: float
    estimated_win_rate: float
    sample_days: int
```

**After**（追加 2 字段, 保 backward-compat）：
```python
class StrategyConfigPreviewResponse(BaseModel):
    """回测预览。"""
    candidate_params: dict[str, float]
    estimated_hourly_entries: float
    estimated_win_rate: float
    sample_days: int
    data_source: str = "no_data"  # "paper_trades" | "no_data"
    sample_n: int = 0             # 参与胜率计算的 CLOSED paper_trades 数
```

（default 值让老 caller 若不用新字段也不 break; 但本端点每次都会填新字段）

## 五、Change 2 — `api/routes/v5_strategy_config.py:136-150`

**Before**（14 行）：
```python
wins = conn.execute(
    "SELECT COUNT(*) FROM ai_training_data "
    "WHERE outcome='WIN' "
    "  AND ((side='SHORT' AND entry_rsi_15m > ?) "
    "    OR (side='LONG'  AND entry_rsi_15m < ?))",
    (overbought, oversold),
).fetchone()[0] or 0
totals = conn.execute(
    "SELECT COUNT(*) FROM ai_training_data "
    "WHERE outcome IN ('WIN','LOSS','FLAT') "
    "  AND ((side='SHORT' AND entry_rsi_15m > ?) "
    "    OR (side='LONG'  AND entry_rsi_15m < ?))",
    (overbought, oversold),
).fetchone()[0] or 0
win_rate = (wins / totals) if totals else 0.0
```

**After**：
```python
# JOIN paper_trades → trade_scores_v5 via source_score_id
# 过滤: CLOSED 交易 + 符合候选 RSI 阈值。WIN = pnl > 0
totals = conn.execute(
    "SELECT COUNT(*) FROM paper_trades pt "
    "JOIN trade_scores_v5 ts ON pt.source_score_id = ts.id "
    "WHERE pt.status = 'CLOSED' "
    "  AND pt.pnl IS NOT NULL "
    "  AND ((pt.side = 'SHORT' AND ts.rsi_15m > ?) "
    "    OR (pt.side = 'LONG'  AND ts.rsi_15m < ?))",
    (overbought, oversold),
).fetchone()[0] or 0
wins = conn.execute(
    "SELECT COUNT(*) FROM paper_trades pt "
    "JOIN trade_scores_v5 ts ON pt.source_score_id = ts.id "
    "WHERE pt.status = 'CLOSED' "
    "  AND pt.pnl > 0 "
    "  AND ((pt.side = 'SHORT' AND ts.rsi_15m > ?) "
    "    OR (pt.side = 'LONG'  AND ts.rsi_15m < ?))",
    (overbought, oversold),
).fetchone()[0] or 0
win_rate = (wins / totals) if totals else 0.0
data_source = "paper_trades" if totals > 0 else "no_data"
```

（return 处新增 `data_source=data_source, sample_n=totals`）

## 六、Change 3 — `return` 处扩展

**Before**：
```python
return StrategyConfigPreviewResponse(
    candidate_params=candidate,
    estimated_hourly_entries=round(hourly, 2),
    estimated_win_rate=round(win_rate, 3),
    sample_days=sample_days,
)
```

**After**：
```python
return StrategyConfigPreviewResponse(
    candidate_params=candidate,
    estimated_hourly_entries=round(hourly, 2),
    estimated_win_rate=round(win_rate, 3),
    sample_days=sample_days,
    data_source=data_source,
    sample_n=totals,
)
```

## 七、Change 4 — 新单测 `tests/test_v5_strategy_config_preview.py`

3 tests:

```python
"""Batch 9 Finding 7: preview 端点用 paper_trades 算胜率。"""
import os
import sqlite3
from fastapi.testclient import TestClient


def _seed_db(db_path):
    """建表 + 塞 6 条 paper_trades 关联 trade_scores_v5:
    - 3 SHORT with rsi_15m=75 (符合 overbought=70): 2 WIN + 1 LOSS → 66.7%
    - 3 LONG  with rsi_15m=25 (符合 oversold=30):  1 WIN + 2 LOSS → 33.3%
    - 2 out-of-range (rsi=50), 不该出现在结果中
    """
    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE trade_scores_v5 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, created_at TEXT, rsi_15m REAL, side TEXT,
            should_trade INTEGER
        );
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, side TEXT, status TEXT, pnl REAL,
            source_score_id INTEGER
        );
    ''')
    # 6 相关 + 2 out-of-range
    rows_scores = [
        # (rsi, side)
        (75, 'SHORT'), (75, 'SHORT'), (75, 'SHORT'),   # SHORT overbought
        (25, 'LONG'),  (25, 'LONG'),  (25, 'LONG'),    # LONG  oversold
        (50, 'SHORT'), (50, 'LONG'),                    # 中间, 不该入统计
    ]
    for rsi, side in rows_scores:
        conn.execute(
            "INSERT INTO trade_scores_v5 (symbol, created_at, rsi_15m, side, should_trade) "
            "VALUES (?, datetime('now'), ?, ?, 1)",
            ('BTC/USDT', rsi, side)
        )
    # 8 对应 paper_trades, source_score_id 顺序 1..8
    # SHORT 3 条: pnl = +1, +2, -1 → 2 WIN
    # LONG  3 条: pnl = -1, -2, +1 → 1 WIN
    # 中间 2 条:  pnl = +5, +5 → 若代码 bug 会误计入,期望不入统计
    paper_rows = [
        ('BTC/USDT', 'SHORT', 'CLOSED', 1.0, 1),
        ('BTC/USDT', 'SHORT', 'CLOSED', 2.0, 2),
        ('BTC/USDT', 'SHORT', 'CLOSED', -1.0, 3),
        ('BTC/USDT', 'LONG',  'CLOSED', -1.0, 4),
        ('BTC/USDT', 'LONG',  'CLOSED', -2.0, 5),
        ('BTC/USDT', 'LONG',  'CLOSED', 1.0, 6),
        ('BTC/USDT', 'SHORT', 'CLOSED', 5.0, 7),   # rsi=50, 不符 overbought=70
        ('BTC/USDT', 'LONG',  'CLOSED', 5.0, 8),   # rsi=50, 不符 oversold=30
    ]
    for row in paper_rows:
        conn.execute(
            "INSERT INTO paper_trades (symbol, side, status, pnl, source_score_id) "
            "VALUES (?, ?, ?, ?, ?)", row
        )
    conn.commit()
    conn.close()


def test_preview_uses_paper_trades_win_rate(monkeypatch, tmp_path):
    """符合阈值的 6 条 paper_trades → win_rate=3/6=0.5, sample_n=6, data_source=paper_trades。"""
    db_path = tmp_path / "test.db"
    _seed_db(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))
    from api.main import app
    client = TestClient(app)
    r = client.post("/api/v5/strategy-config/preview",
                    json={"candidate_params": {"v5_rsi_overbought": 70, "v5_rsi_oversold": 30}})
    assert r.status_code == 200
    body = r.json()
    assert body["sample_n"] == 6
    assert body["data_source"] == "paper_trades"
    assert body["estimated_win_rate"] == 0.5   # 3 WIN / 6 total


def test_preview_no_data_falls_back_to_zero(monkeypatch, tmp_path):
    """paper_trades 为空 → win_rate=0, sample_n=0, data_source=no_data。"""
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript('''
        CREATE TABLE trade_scores_v5 (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, created_at TEXT, rsi_15m REAL, side TEXT, should_trade INTEGER);
        CREATE TABLE paper_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, side TEXT, status TEXT, pnl REAL, source_score_id INTEGER);
    ''')
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", str(db_path))
    from api.main import app
    client = TestClient(app)
    r = client.post("/api/v5/strategy-config/preview",
                    json={"candidate_params": {"v5_rsi_overbought": 70, "v5_rsi_oversold": 30}})
    assert r.status_code == 200
    body = r.json()
    assert body["sample_n"] == 0
    assert body["data_source"] == "no_data"
    assert body["estimated_win_rate"] == 0.0


def test_preview_excludes_out_of_range_rsi(monkeypatch, tmp_path):
    """阈值 overbought=80 → 只有 rsi>80 的 SHORT 计入,rsi=75 的不计。"""
    db_path = tmp_path / "test.db"
    _seed_db(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))
    from api.main import app
    client = TestClient(app)
    r = client.post("/api/v5/strategy-config/preview",
                    json={"candidate_params": {"v5_rsi_overbought": 80, "v5_rsi_oversold": 20}})
    assert r.status_code == 200
    body = r.json()
    # rsi=75/50/25 都不符 80/20 阈值 → 0 样本
    assert body["sample_n"] == 0
    assert body["data_source"] == "no_data"
```

## 八、验收标准

- `python3 -m pytest tests/test_v5_strategy_config_preview.py -v` → 3/3 pass
- `grep -c "ai_training_data" api/routes/v5_strategy_config.py` → 0（老表不再被 preview 端点引用）
- `grep -c "paper_trades" api/routes/v5_strategy_config.py` → ≥1
- 邻近 tests 无回归：`test_v5_strategy_config*.py`（若已存在）不动
- 只 stage 3 文件（`api/routes/v5_strategy_config.py` + `api/schemas/v5_strategy_config.py` + `tests/test_v5_strategy_config_preview.py`）
- Commit subject EXACT: `fix(v5_strategy_config): preview 改读 paper_trades 计算胜率 + data_source/sample_n (Finding 7)`

## 九、失效模式

- **paper_trades.source_score_id 为 NULL**：JOIN 会漏掉该行。可接受 —— 老 paper_trades（v0.5.4 之前）少数可能没关联，样本量略偏小；新数据都有链接。若真为大量 NULL 值将 `sample_n=0`，前端会看到 `data_source=no_data`。
- **paper_trades OPEN 中的持仓**：`status='CLOSED'` 过滤已排除。
- **`pnl=0` 的 FLAT 交易**：`pnl > 0` 判 WIN 时 FLAT 不计 win，但计入 totals（如 pnl=0 属 CLOSED）。可接受：FLAT 视为非 WIN。**注意**：这与老逻辑 `WIN/LOSS/FLAT` 都计入 totals 一致。
- **JOIN 性能**：paper_trades 无 source_score_id 索引，全表扫。生产 paper_trades 量目前 <10k，可接受，未来若上万条再加索引。

## 十、超范围声明

- 不改 `estimated_hourly_entries` / `sample_days` 逻辑
- 不改前端（deleted V5StrategyConfigPage 后续补 UI 时再消费 data_source）
- 不删 ai_training_data 表
- 不加 source_score_id 索引（YAGNI，量小）

## 十一、相关

- Bug audit: `docs/audit-2026-07/bug-fix-list.md` Finding 7 (P1)
- 引用：
  - `api/routes/v5_strategy_config.py:136-149`（现状 ai_training_data 查询）
  - `api/schemas/v5_strategy_config.py:26-31`（Response 模型）
  - `scripts/local_db.py:358-392`（paper_trades schema）
  - `scripts/local_db.py:40-72`（trade_scores_v5 schema）
