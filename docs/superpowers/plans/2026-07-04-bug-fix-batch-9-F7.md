# Bug Fix Batch 9 · Finding 7 · preview 端点改读 paper_trades · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /api/v5/strategy-config/preview` 计算 `estimated_win_rate` 时,从 0 行的 `ai_training_data` 改读 `paper_trades JOIN trade_scores_v5`。响应加 `data_source`/`sample_n`,让前端区分"真实历史"vs"零数据"。

**Architecture:** 单 task TDD 循环:先写 3 tests(RED —— 老代码返 0.0,不含新字段)→ 改 schema + route → GREEN → 单 commit。

**Tech Stack:** Python stdlib + FastAPI TestClient + pytest tmp_path + sqlite3。无新增 pip 依赖。

## Global Constraints

- Only 3 files touched:
  - `api/schemas/v5_strategy_config.py` (add 2 fields to Response)
  - `api/routes/v5_strategy_config.py` (rewrite lines 136-149 + return block)
  - `tests/test_v5_strategy_config_preview.py` (create, 3 tests)
- Response 新增字段:
  - `data_source: str = "no_data"` (取值 "paper_trades" | "no_data")
  - `sample_n: int = 0`
- SQL 关系:JOIN via `paper_trades.source_score_id = trade_scores_v5.id`
- WIN 判定:`pnl > 0`；totals 判定:`status='CLOSED' AND pnl IS NOT NULL`
- 不改 `estimated_hourly_entries` / `sample_days` / cache / invalidate 逻辑
- 不删 `ai_training_data` 表
- 不改前端
- 现有 tests 无回归
- Single commit, subject EXACT: `fix(v5_strategy_config): preview 改读 paper_trades 计算胜率 + data_source/sample_n (Finding 7)`

---

## File Structure

| 路径 | 动作 |
|---|---|
| `api/schemas/v5_strategy_config.py` | Modify —— 加 2 字段 |
| `api/routes/v5_strategy_config.py` | Modify L136-150 + return block |
| `tests/test_v5_strategy_config_preview.py` | Create —— 3 tests |

---

# Task 1: preview 端点重写 + response schema 扩展 + 3 tests

**Files:**
- Modify: `api/schemas/v5_strategy_config.py`
- Modify: `api/routes/v5_strategy_config.py`
- Create: `tests/test_v5_strategy_config_preview.py`

**Interfaces:**
- Consumes: pytest `monkeypatch` + `tmp_path` fixtures, `fastapi.testclient.TestClient`
- Produces: `StrategyConfigPreviewResponse` 新增 `data_source` / `sample_n` 字段
- 端点行为变化:`estimated_win_rate` 计算源从 `ai_training_data` 改为 `paper_trades JOIN trade_scores_v5`

## RED phase

- [ ] **Step 1: 创建 `tests/test_v5_strategy_config_preview.py`(3 tests)**

```python
"""Batch 9 Finding 7: preview 端点用 paper_trades 算胜率。"""
import sqlite3
from fastapi.testclient import TestClient


def _seed_db(db_path):
    """建表 + 塞 8 条 paper_trades JOIN trade_scores_v5:
    - 3 SHORT with rsi_15m=75 (符合 overbought=70): pnl 1, 2, -1 → 2 WIN
    - 3 LONG  with rsi_15m=25 (符合 oversold=30):  pnl -1, -2, 1 → 1 WIN
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
    score_rows = [
        (75, 'SHORT'), (75, 'SHORT'), (75, 'SHORT'),
        (25, 'LONG'),  (25, 'LONG'),  (25, 'LONG'),
        (50, 'SHORT'), (50, 'LONG'),
    ]
    for rsi, side in score_rows:
        conn.execute(
            "INSERT INTO trade_scores_v5 (symbol, created_at, rsi_15m, side, should_trade) "
            "VALUES (?, datetime('now'), ?, ?, 1)",
            ('BTC/USDT', rsi, side)
        )
    paper_rows = [
        ('BTC/USDT', 'SHORT', 'CLOSED', 1.0, 1),
        ('BTC/USDT', 'SHORT', 'CLOSED', 2.0, 2),
        ('BTC/USDT', 'SHORT', 'CLOSED', -1.0, 3),
        ('BTC/USDT', 'LONG',  'CLOSED', -1.0, 4),
        ('BTC/USDT', 'LONG',  'CLOSED', -2.0, 5),
        ('BTC/USDT', 'LONG',  'CLOSED', 1.0, 6),
        ('BTC/USDT', 'SHORT', 'CLOSED', 5.0, 7),
        ('BTC/USDT', 'LONG',  'CLOSED', 5.0, 8),
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
    r = client.post(
        "/api/v5/strategy-config/preview",
        json={"candidate_params": {"v5_rsi_overbought": 70, "v5_rsi_oversold": 30}}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sample_n"] == 6
    assert body["data_source"] == "paper_trades"
    assert body["estimated_win_rate"] == 0.5


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
    r = client.post(
        "/api/v5/strategy-config/preview",
        json={"candidate_params": {"v5_rsi_overbought": 70, "v5_rsi_oversold": 30}}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sample_n"] == 0
    assert body["data_source"] == "no_data"
    assert body["estimated_win_rate"] == 0.0


def test_preview_excludes_out_of_range_rsi(monkeypatch, tmp_path):
    """阈值 overbought=80 → 数据里 rsi=75 都不入统计,sample_n=0。"""
    db_path = tmp_path / "test.db"
    _seed_db(str(db_path))
    monkeypatch.setenv("DB_PATH", str(db_path))
    from api.main import app
    client = TestClient(app)
    r = client.post(
        "/api/v5/strategy-config/preview",
        json={"candidate_params": {"v5_rsi_overbought": 80, "v5_rsi_oversold": 20}}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sample_n"] == 0
    assert body["data_source"] == "no_data"
```

- [ ] **Step 2: 跑 tests —— 期望 RED**

```bash
python3 -m pytest tests/test_v5_strategy_config_preview.py -v
```

Expected: 3/3 FAIL 或 error。老代码 Response 无 `data_source` / `sample_n` 字段 → KeyError 或 pydantic 拒生成 → 断言失败。

## GREEN phase

- [ ] **Step 3: 改 `api/schemas/v5_strategy_config.py` —— 加 2 字段**

用 Edit,anchor unique substring 是整个 `StrategyConfigPreviewResponse` 类。

**Before**:
```python
class StrategyConfigPreviewResponse(BaseModel):
    """回测预览。"""
    candidate_params: dict[str, float]
    estimated_hourly_entries: float
    estimated_win_rate: float
    sample_days: int
```

**After**:
```python
class StrategyConfigPreviewResponse(BaseModel):
    """回测预览。"""
    candidate_params: dict[str, float]
    estimated_hourly_entries: float
    estimated_win_rate: float
    sample_days: int
    data_source: str = "no_data"
    sample_n: int = 0
```

- [ ] **Step 4: 改 `api/routes/v5_strategy_config.py:136-150` + return block**

用 Edit。老 anchor 是从 `wins = conn.execute(` 到 `win_rate = (wins / totals) if totals else 0.0`。

**Before**(约 L136-150):
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

**After**:
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

- [ ] **Step 5: 改 return block**

anchor 是 `return StrategyConfigPreviewResponse(` 那 6 行。

**Before**:
```python
    return StrategyConfigPreviewResponse(
        candidate_params=candidate,
        estimated_hourly_entries=round(hourly, 2),
        estimated_win_rate=round(win_rate, 3),
        sample_days=sample_days,
    )
```

**After**:
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

- [ ] **Step 6: 跑 tests —— 期望 GREEN**

```bash
python3 -m pytest tests/test_v5_strategy_config_preview.py -v
```

Expected: 3/3 PASS

若失败:
- Test 1 win_rate ≠ 0.5 → 检查 SQL WIN 条件 `pnl > 0` 与 totals 条件 `pnl IS NOT NULL`
- Test 1 sample_n ≠ 6 → 检查 JOIN 是否 exclude 掉了 rsi=50 的 2 条
- Test 2 data_source ≠ "no_data" → 检查 `data_source` 变量初始化
- Test 3 sample_n ≠ 0 → 检查阈值边界(严格大于 / 小于)

## 邻近回归 + sanity + commit

- [ ] **Step 7: 邻近回归**

```bash
# 找并跑现有 strategy_config 测试
find tests -name "test_v5_strategy_config*.py" -type f
# 若已有 test_v5_strategy_config.py 之类,跑一遍
python3 -m pytest tests/test_v5_strategy_config_preview.py -v 2>&1 | tail -10
```

Expected: 无 test 因此改动 FAIL(该 route 的 GET/PATCH 端点未动)。

- [ ] **Step 8: sanity greps**

```bash
# ai_training_data 不再在 preview 里
grep -c "ai_training_data" api/routes/v5_strategy_config.py
# 期望: 0

# paper_trades JOIN 到位
grep -c "paper_trades pt" api/routes/v5_strategy_config.py
# 期望: 2 (wins + totals 两查询)

# 新字段在 schema
grep -c "data_source\|sample_n" api/schemas/v5_strategy_config.py
# 期望: 2
```

- [ ] **Step 9: Commit**

```bash
git add api/schemas/v5_strategy_config.py api/routes/v5_strategy_config.py tests/test_v5_strategy_config_preview.py
git commit -m "$(cat <<'EOF'
fix(v5_strategy_config): preview 改读 paper_trades 计算胜率 + data_source/sample_n (Finding 7)

修 bug-fix-list.md Finding 7 (P1):POST /api/v5/strategy-config/preview
从 0 行的 ai_training_data 表读 outcome/entry_rsi_15m 算胜率,结果
恒为 0.0,前端 StrategyConfig 页调阈值时看不出参数优劣。

Change:
- Response 加 data_source(paper_trades/no_data) + sample_n
- SQL 改 JOIN paper_trades pt ON pt.source_score_id=ts.id
- WIN 判定: pnl > 0；totals 判定: status='CLOSED' AND pnl IS NOT NULL
- RSI 阈值仍用候选参数,过滤 SHORT rsi>overbought / LONG rsi<oversold

Tests:
- 新增 tests/test_v5_strategy_config_preview.py 3 tests
  - 6 in-range paper_trades → win_rate=0.5, sample_n=6
  - 空 DB → win_rate=0, sample_n=0, data_source=no_data
  - 阈值范围外 → sample_n=0(防边界回归)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

# Self-Review 记录

- **spec § 四 Change 1 (schema 加 2 字段)**: Step 3 ✓
- **spec § 五 Change 2 (route 重写查询)**: Step 4 ✓
- **spec § 六 Change 3 (return 填新字段)**: Step 5 ✓
- **spec § 七 Change 4 (3 tests)**: Step 1 完整 ✓
- **spec § 八 验收**: Step 6 (3/3) + Step 7 (回归) + Step 8 (sanity) ✓
- **spec § 九 失效模式**: 已声明 source_score_id NULL / FLAT 处理 / 索引 YAGNI ✓
- **placeholder scan**: 无 TBD ✓
- **type consistency**: `data_source` / `sample_n` 名字在 spec + plan + test + schema + route 一致 ✓
- **测试 RED→GREEN**: Step 2 = RED；Step 6 = GREEN ✓
- **atomicity**: 单 commit at Step 9 ✓
