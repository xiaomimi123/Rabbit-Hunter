# V6 Funding Rate 设计文档

> **核心目的:** 给 Rabbit Hunter 引入第一个**完全独立于 RSI/MACD 价格历史**的 alpha 信号源 — 永续合约资金费率(funding rate)。从"在散户挖了 20 年的指标空间里再翻找"切换到"测量散户杠杆拥挤度",AI 学习从 2 维特征空间(RSI×MACD)扩展到 3 维(+ funding_z_score)。
>
> **跟现有系统的关系:** **完全增量,不破坏 V5.1 trend_aligned + Reflection Phases 1-3。** funding 作为第三个维度并行存在,reflection 系统天然会从对比中告诉用户 "funding alpha 比 RSI/MACD 大多少"。
>
> **数据源:** OKX 公开 funding rate API (无需账号 / key)。多交易所聚合留作 V6.1。
>
> **底层纪律:** 跟 Reflection 一样 — AI 提案,人类批准,A/B 验证,赢家升级。

---

## §1 战略动机

### 1.1 为什么是 funding rate

RSI/MACD/Bollinger/KDJ/斐波那契 — 所有"价格历史的函数"指标本质都是同一种信息的不同表达。crypto perp 交易员里 90% 在用这些,**全世界量化基金已经把这个二维空间挖了 20 年**,边际 alpha 接近 0。你的实测数据证明这一点:V5.1 trend_aligned 跑 24h,29 笔自动单,累积 PnL -4.95%,胜率 41%,**23/29 笔(79%)因 SIGNAL_REVERSE 平仓** — 同一套指标 5 分钟后又叫你反向。

**资金费率是测散户杠杆拥挤度,不是测价格。** 它是**永续合约独有**的数据维度,跟 RSI/MACD 物理不相关:

- 价格 = 现货 + 期货溢价
- 资金费率 = 期货溢价的"再分配机制" — 多头超额时多头付钱给空头,反之亦然
- 资金费率高 = 杠杆多头拥挤
- 极端资金费率 = 反转早期信号(高费率不可持续,因为多头每 8h 都在出血)

**关键:** funding rate 的信号有 **物理强制性**。当 BTC funding 持续在年化 100%+,即使 BTC 还在涨,所有杠杆多头每 8h 都在付真金白银的成本。这种"成本累积"最终一定触发平仓潮 → 价格反转。**这是机械的,不是"市场情绪"。**

### 1.2 跟现有 V5.1 的关系

| | V5.1 trend_aligned(现有) | V6 funding(新增) |
|---|---|---|
| 信息来源 | 历史价格 K 线 | 永续合约杠杆持仓 |
| 滞后性 | 滞后 5-15 根 K 线 | 实时拥挤度,无滞后 |
| 信号频率 | 24h ~10-30 单 | 24h ~5-15 单(更精) |
| 反转 vs 趋势 | 趋势对齐 | 反转(逆拥挤) |
| 失效条件 | 强趋势市 / 横盘 | regime shift(ETF / 减半) |

**V5.1 看"价格在哪",V6 看"赌注在哪边"。** 两者完全独立,可以叠加(同时触发 = 高质量信号)或互斥(只其中一个触发 = 弱信号)。Reflection 系统天然能告诉你哪种组合在赚钱。

### 1.3 为什么现在做

**必要前置已经全部就位:**

1. ✅ Reflection Phases 1-3 上线(每笔关仓 AI 自动复盘)— V6 一上线就开始抓数据
2. ✅ setup_type 派生层(scripts/ai/setup_type.py)已经预留 `funding_z_score` 参数
3. ✅ failure_taxonomy `against_4h_trend_no_funding_filter` handler 已经存在,但目前 `funding_z_score=None` 永远不触发该过滤 — 接入 V6 后立即开始工作
4. ✅ Top-20 whitelist(V5.1)上线后,funding rate 数据需求降到 20 个币 × 8h 频率 = 极小调用量

### 1.4 失效场景的诚实评估

funding rate 在以下情境下边际下降或失效:

- **大规模事件冲击**(ETF 通过 / Mt.Gox 偿付 / 减半):**所有人**都极端做多/做空,funding 冲到极限然后停留,不再是反转信号
- **极低波动期**:funding 长期接近 0,z-score 失去区分度
- **新上线 / 流动性差的币**:OI 太小,funding 容易被单一大户搞,信号噪声大 → V5.1 已经过滤掉(top-20)

**缓解:**
- 启动期(前 30 天)只看 BTC/ETH/SOL 三个最大币的 funding,等积累足够样本再扩
- z-score 滚动窗口选 30d,自适应市场制度
- 单笔仓位上限 1.5%(已经在 v5_params),不让 funding 信号驱动赌博式重仓

---

## §2 架构总览

### 2.1 数据流图

```
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 0: OKX 公开 API (https://www.okx.com/api/v5/public/...)        │
│   funding-rate-history?instId=BTC-USDT-SWAP&limit=N                  │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 1: v5_funding_collector (新进程)                               │
│   每 5 min 拉 top-20 当前 + 最近 1h 数据                             │
│   每 1 h  跑一次 z-score 滚动重算(30d window)                      │
│   入库 funding_rates 表 + funding_zscore_cache 表                    │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 2: scorer.py 入场评分                                          │
│   process_enriched_v5 拿当前 funding_z_score 注入 candidate          │
│   写入 trade_scores_v5.funding_z_score (新增字段)                    │
│   ↓                                                                   │
│   setup_type 派生扩展:                                                │
│   - 旧: rsi_overbought_macd_bearish_short                            │
│   - 新: funding_extreme_short_rsi_overbought (如果 |z|>2.0)         │
│   ↓                                                                   │
│   failure_taxonomy.match_failure_modes(candidate) 用上真 z_score    │
│   - against_4h_trend_no_funding_filter 终于会触发                    │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 3: AI decision                                                  │
│   trading_assistant.decide 注入 funding 状态到 prompt:              │
│   "Current BTC funding: +0.05% / 8h (annualized +55%, z-score +2.3)" │
│   AI reasoning 现在含 funding 维度                                   │
│   ai_confidence_calibration 自动按 (model, conf) 桶累积              │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 4: reflection 复盘 (关仓后)                                    │
│   _load_close_context 拉 entry 时刻的 funding_z_score               │
│   prompt 注入:"Entry funding: ..., during-hold funding moved to ..." │
│   reflections.funding_z_score_at_entry (新增字段)                    │
│   AI 5 问的 failure_mode_key 现在可能包含                            │
│   funding-related modes(future taxonomy 扩展)                       │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 5: 学习闭环(继承自 Reflection)                                │
│   日聚合 setup_performance_daily 自动按新 setup_type 分桶            │
│   - funding_extreme_short_rsi_overbought n=?  win_rate=?            │
│   - rsi_overbought_macd_bearish_short n=?     win_rate=?            │
│   ↓                                                                   │
│   3-4 周后,Kelly engine 自动跑 fractional Kelly                      │
│   funding-based setup 的 sizing 会跟 RSI/MACD-based 的对比           │
│   你看 /v5/reflection Tab 3,数据告诉你哪种 setup 更值得加仓         │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 进程层

新增一个独立异步进程,跟 reflection_worker / position_monitor / scorer 同级:

```
scripts/tasks/
├── deep_collector.py          # 已存在
├── scorer.py                  # 已存在 (本设计改)
├── v5_position_monitor.py     # 已存在
├── v5_reflection_worker.py    # 已存在 (本设计无改)
└── v5_funding_collector.py    # ★ 本文新建
```

`collector_main.py` 启动时把 `V5FundingCollector` 加入 tasks 列表(跟其他 worker 一样)。

### 2.3 跟 V5.1 / Reflection 系统的关系

**完全 backward-compatible:**

| 已有 | V6 后变化 |
|---|---|
| scripts/v5_strategy.py decide() | 无变化,仍只读 RSI/MACD/4h |
| failure_taxonomy 8 个 handler | `against_4h_trend_no_funding_filter` 终于能触发,其他 7 个无变化 |
| reflection 5 问 | prompt 加 funding context,AI 输出 schema 无变化 |
| ai_confidence_calibration | 完全无变化(继续按 model × conf 桶累积) |
| Kelly sizing | 完全无变化(自动按新 setup_type 分桶) |
| 前端 /v5/reflection 三 tab | Tab 1 reflection card 加显示 funding;Tab 2/3 无变化 |
| 前端 V5AIStatusPage | 加 funding heatmap card |

**不破坏的承诺:** 即使 funding collector 完全挂掉,系统会 fallback 到 funding_z_score=None,等同于 V5.1 现在的行为。

---

## §3 数据模型

### 3.1 funding_rates(原始历史)

```sql
CREATE TABLE IF NOT EXISTS funding_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,                    -- e.g. 'BTCUSDT' (按 V5 内部规约)
    instrument_id TEXT NOT NULL,             -- e.g. 'BTC-USDT-SWAP' (OKX 原始)
    funding_time TEXT NOT NULL,              -- ISO UTC, 实际 funding 结算时间
    funding_rate REAL NOT NULL,              -- 原始 8h funding rate (e.g. 0.0001 = 0.01% / 8h)
    annualized_rate REAL NOT NULL,           -- = funding_rate * 365 * 3
    settled_rate REAL,                       -- OKX settFundingRate (可选)
    source TEXT NOT NULL DEFAULT 'okx',      -- 'okx' / 'binance' / 'bybit'
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, funding_time, source)
);

CREATE INDEX IF NOT EXISTS idx_funding_rates_symbol_time
    ON funding_rates(symbol, funding_time DESC);
```

**写入策略:**
- 每 5 min collector tick → 拉每个 top-20 symbol 的 last 3 funding(即过去 24h)
- `INSERT OR IGNORE` — 重复抓不重复写
- 启动时回填:首次跑读 OKX history 拉 90d × top-20

**存储估算:** 20 symbols × 3 funding/day × 365 days = 21,900 行/年。微不足道。

### 3.2 funding_zscore_cache(预计算 z-score)

```sql
CREATE TABLE IF NOT EXISTS funding_zscore_cache (
    symbol TEXT NOT NULL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    current_funding_rate REAL NOT NULL,      -- 最近一次结算的 funding
    mean_30d REAL,                            -- 过去 30 天 funding 均值
    std_30d REAL,                             -- 过去 30 天 funding 标准差
    zscore_30d REAL,                          -- (current - mean) / std
    sample_size_30d INTEGER,                  -- 实际样本数(用于稳定性判断)
    is_extreme INTEGER NOT NULL DEFAULT 0,    -- 1 if |zscore_30d| >= 2.0
    extreme_direction TEXT,                   -- 'long_crowded' (z>2) / 'short_crowded' (z<-2)
    PRIMARY KEY (symbol)
);
```

**写入策略:**
- 每 1 hour collector tick → 重算所有 top-20 的 z-score
- `INSERT OR REPLACE` 整行覆盖
- 读取端(scorer)读这张表,O(1) lookup

**为什么用 cache 表而不是 view:**
- SQLite view 每次查询都重算,数千 trade_scores_v5 评分会爆炸
- cache 表每小时跑一次,读端 < 1ms

### 3.3 修改 trade_scores_v5

新增一列(append-only,backward compat):

```sql
ALTER TABLE trade_scores_v5 ADD COLUMN funding_z_score REAL;
ALTER TABLE trade_scores_v5 ADD COLUMN funding_rate_8h REAL;
```

写入策略:`scorer.py` 在 `_write_trade_score` 时读 cache 表填入。Cache miss → 写 NULL。

### 3.4 修改 reflections

新增两列(关仓时快照):

```sql
ALTER TABLE reflections ADD COLUMN funding_z_score_at_entry REAL;
ALTER TABLE reflections ADD COLUMN funding_rate_at_entry REAL;
```

`reflection_runner._load_close_context` 在拉 entry snapshot 时 JOIN funding_rates 拿到最接近 entry_time 的费率。

---

## §4 关键算法

### 4.1 z-score 计算

```python
def compute_zscore_30d(symbol: str, db: sqlite3.Connection) -> Optional[dict]:
    """计算 symbol 的 30 天 funding rolling z-score。

    返回 None 如果样本不足(< 20 个 funding period,即 < 6.7 天)。
    """
    rows = db.execute("""
        SELECT funding_rate FROM funding_rates
         WHERE symbol = ?
           AND source = 'okx'
           AND funding_time >= datetime('now', '-30 days')
         ORDER BY funding_time DESC
    """, (symbol,)).fetchall()

    rates = [r[0] for r in rows]
    if len(rates) < 20:
        return None

    import statistics
    current = rates[0]                # 最近一次
    historical = rates[1:]            # 用于算 mean/std,排除当前点
    mean = statistics.mean(historical)
    std = statistics.stdev(historical) if len(historical) >= 2 else 0.0

    if std == 0:
        zscore = 0.0
    else:
        zscore = (current - mean) / std

    return {
        "current_funding_rate": current,
        "mean_30d": mean,
        "std_30d": std,
        "zscore_30d": zscore,
        "sample_size_30d": len(rates),
        "is_extreme": abs(zscore) >= 2.0,
        "extreme_direction": (
            "long_crowded" if zscore >= 2.0
            else "short_crowded" if zscore <= -2.0
            else None
        ),
    }
```

**关键设计选择:**

1. **窗口选 30d**:足够覆盖一个完整波动周期,又不过老到无法响应制度变化。
2. **排除当前点算 mean/std**:防止当前极端值"污染"自己的基线。
3. **min sample 20**:对应 6.7 天 funding 历史,启动期前几天 NULL。
4. **|z| ≥ 2.0 = "extreme"**:对应正态分布尾部 ~5%。3.0 是极端尾部(0.3%),太严。

### 4.2 极端阈值与信号方向映射

| z-score | 含义 | 反转方向 | 信号强度 |
|---|---|---|---|
| `z ≥ 3.0` | 极端多头拥挤(罕见) | 强 SHORT 候选 | ★★★ |
| `2.0 ≤ z < 3.0` | 多头拥挤 | SHORT 候选 | ★★ |
| `-2.0 < z < 2.0` | 中性 | 无 funding 信号 | ★ |
| `-3.0 < z ≤ -2.0` | 空头拥挤 | LONG 候选 | ★★ |
| `z ≤ -3.0` | 极端空头拥挤(罕见,通常恐慌底) | 强 LONG 候选 | ★★★ |

**注意:** funding 信号方向跟 funding rate 的符号**相反** — 因为 funding 高(z 正)= 多头付钱 = 多头拥挤 = 反转应该 SHORT。

### 4.3 setup_type 派生扩展

修改 `scripts/ai/setup_type.py`:

```python
def derive_setup_type(entry: dict) -> str:
    side_lower = (entry.get("side") or "").lower()

    if entry.get("strategy_id") == "v5_manual":
        return f"manual_{side_lower}"

    rsi_state = ...    # 现有逻辑
    macd_state = ...   # 现有逻辑

    # V6: funding 维度优先
    fz = entry.get("funding_z_score")
    if fz is not None and abs(fz) >= 2.0:
        direction = "short" if fz > 0 else "long"
        return f"funding_extreme_{direction}_{rsi_state}"

    return f"{rsi_state}_{macd_state}_{side_lower}"
```

**结果:** 90 天后,reflection 中会出现以下 setup_type(预期分布):

| setup_type | 预期样本占比 |
|---|---|
| `rsi_neutral_macd_extending_*` | 60-70% (现有大多数) |
| `rsi_overbought_macd_bearish_short` | 10-15% (V5.1 主力) |
| `funding_extreme_short_*` | 5-10% (V6 新增) |
| `funding_extreme_long_*` | 5-10% (V6 新增) |
| 其他 | 5-10% |

**关键:** funding_extreme 是**独立的 setup_type 维度**,会在 setup_performance_daily 里**单独累积胜率/Sharpe**。3-4 周后,Kelly engine 会告诉你 "funding_extreme_short_* 平均 R 是 X,rsi_overbought_macd_bearish_short 平均 R 是 Y,要不要 sizing 比例 X:Y"。

### 4.4 failure_taxonomy 启用

修改 `scripts/ai/failure_taxonomy._h_against_4h_trend_no_funding` 的现有逻辑:

```python
def _h_against_4h_trend_no_funding(c: dict, db_path: str) -> bool:
    side_int = c.get("side_int") or 0
    macd_4h = c.get("macd_hist_4h") or 0
    fz = c.get("funding_z_score")     # 现在真正会拿到值

    if side_int == 0 or macd_4h == 0:
        return False
    if abs(macd_4h) < 0.004:           # 现有 noise floor,保留
        return False

    same_dir = (side_int > 0 and macd_4h > 0) or (side_int < 0 and macd_4h < 0)
    if same_dir:
        return False                     # 同向不触发

    # 反向 4h 趋势,看 funding 是否给反向背书
    if fz is None:
        return True                      # 无 funding 数据 fallback to original behavior
    return abs(fz) < 1.5                 # funding 中性 → 触发;funding 极端反向 → 不触发
```

**效果:** 当 V6 上线,这个规则真正开始拦截"逆 4h 趋势 + funding 不背书"的低质量信号。

### 4.5 AI prompt 注入

修改 `scripts/ai/trading_assistant._decide_via_chat` 的 user_msg 构建,在现有 indicators block 后加入:

```python
funding_block = ""
if candidate.get("funding_z_score") is not None:
    fz = candidate["funding_z_score"]
    fr = candidate.get("funding_rate_8h", 0)
    annualized = fr * 365 * 3 * 100
    crowding = (
        "extreme long crowding (potential SHORT setup)" if fz >= 2.0
        else "extreme short crowding (potential LONG setup)" if fz <= -2.0
        else "moderate long bias" if fz >= 0.5
        else "moderate short bias" if fz <= -0.5
        else "neutral"
    )
    funding_block = f"""
[FUNDING RATE CONTEXT]
Current 8h funding: {fr*100:+.4f}% (annualized {annualized:+.1f}%)
30-day z-score: {fz:+.2f}
Market positioning: {crowding}
"""
```

**AI 在 prompt 里看到 funding 上下文后**,会自然在 reasoning 里引用它。reflection 系统会记录 AI 引用 funding 的频率,日聚合给出 "AI 在 funding_extreme setup 里的胜率 vs 非 funding setup 里的胜率"对比。

### 4.6 reflection prompt 注入

修改 `scripts/ai/reflection_prompt.build_reflection_prompt`,在 entry snapshot 后加入:

```
[ENTRY FUNDING SNAPSHOT]
8h funding rate: {ctx.get('funding_rate_at_entry', 'N/A')}
30d z-score: {ctx.get('funding_z_score_at_entry', 'N/A')}

[DURING-HOLD FUNDING PATH]
{ctx.get('funding_during_hold_summary', 'not recorded')}
```

`during_hold_summary` 由 reflection_runner 在 _load_close_context 时计算:取 entry → exit 期间的 funding 结算次数(0-3 次,因为 8h 周期),展示每次的 rate 和方向变化。

---

## §5 模块文件清单

### 5.1 新增

| 文件 | 责任 |
|---|---|
| `scripts/tasks/v5_funding_collector.py` | 异步进程,5min 拉新 / 1h 算 z-score |
| `scripts/ai/funding_rate_calculator.py` | z-score 计算 + cache 读写,纯函数 |
| `api/schemas/v5_funding.py` | Pydantic schemas (FundingStatusResponse, FundingHistoryResponse) |
| `api/routes/v5_funding.py` | GET /api/v5/funding/status/{symbol}, /history/{symbol} |
| `tests/test_funding_collector.py` | 拉数据 + 入库 + idempotent |
| `tests/test_funding_zscore.py` | z-score 计算 / 边界 / 极端阈值 |
| `tests/test_funding_taxonomy_integration.py` | failure_taxonomy 用上 funding 后行为 |
| `tests/test_funding_api.py` | API 集成测试 |

### 5.2 修改

| 文件 | 改动 |
|---|---|
| `scripts/local_db.py` | 新增 2 表(funding_rates, funding_zscore_cache) + ALTER 现有 2 表 |
| `scripts/ai/setup_type.py` | 增加 funding_extreme 派生(spec §4.3) |
| `scripts/ai/failure_taxonomy.py` | 启用 `_h_against_4h_trend_no_funding` 真实判定 |
| `scripts/ai/trading_assistant.py` | 注入 funding context 到 _decide_via_chat prompt |
| `scripts/ai/reflection_runner.py` | _load_close_context 拉 funding_z_score 入 ctx |
| `scripts/ai/reflection_prompt.py` | prompt template 增加 funding section |
| `scripts/tasks/scorer.py` | process_enriched_v5 注入 funding,写 trade_scores |
| `scripts/tasks/collector_main.py` | 启动 V5FundingCollector |
| `Rabbit Hunterfronted/types.ts` | 增加 FundingStatus 类型 |
| `Rabbit Hunterfronted/components/pages/V5ReflectionPage.tsx` | reflection card 显示 funding |
| `Rabbit Hunterfronted/components/pages/V5AIStatusPage.tsx` | 加 funding heatmap card |

---

## §6 前端

### 6.1 reflection card 扩展

`V5ReflectionPage` 的 `ReflectionCard` 组件加一行 funding 数据:

```
━━━ pos 7 — BTCUSDT SHORT — R+1.20 — WIN ━━━
setup_type: funding_extreme_short_rsi_overbought    ← 新派生
funding @ entry: +0.08% / 8h (z +2.4) ★ 极端多头拥挤   ← 新增
realized R: +1.20  holding: 23min   AI: deepseek-chat (3.2s)

▶ 为什么开仓: BTC funding z-score +2.4 显示多头极端拥挤,RSI 71...
▶ 当时怎么想: 期望 funding 极端后回归,多头平仓潮推下跌...
▶ 实际怎么走: 价格 8h 后下跌 1.2 ATR,funding z 回到 +0.8...
▶ 下次怎么改 ★: ...
```

### 6.2 AI Status 新 HoloCard:funding 实况

赛博风格,top-20 一目了然:

```
▌ FUNDING RATE STATUS (top-20)              [refresh 5s]

BTCUSDT  +0.0008%/8h  z=+0.4  ░░░░░██░░░░  neutral
ETHUSDT  +0.0015%/8h  z=+1.1  ░░░░░░░██░░  mild long
SOLUSDT  +0.0250%/8h  z=+2.7  ░░░░░░░░██▓  ★ LONG CROWDED ★
BNBUSDT  -0.0050%/8h  z=-0.8  ░░░██░░░░░░  mild short
XRPUSDT  -0.0120%/8h  z=-2.1  ▓██░░░░░░░░  ★ SHORT CROWDED ★
DOGEUSDT +0.0035%/8h  z=+1.5  ░░░░░░░░█░░  long bias
...

▌ 5 symbols at |z| ≥ 2.0  → 5 SHORT/LONG candidates ready
```

视觉:用 `▓██░░░` ASCII bar 表示 z-score 位置,中心 = neutral,边缘 = 极端。

### 6.3 Dashboard funding × outcome 分项

`V5DashboardPage` 加一个新 card:"24h funding setup 表现"

| setup 维度 | 样本数 | 胜率 | 平均 R |
|---|---|---|---|
| funding_extreme_short_* | 3 | 67% | +1.2 |
| funding_extreme_long_* | 2 | 50% | +0.5 |
| rsi_overbought_macd_bearish | 8 | 38% | -0.1 |
| rsi_oversold_macd_bullish | 5 | 60% | +0.4 |
| 其他 | 20 | 42% | -0.05 |

**这是用户最关心的对比** — 数据本身告诉用户 funding 维度 vs 价格指标维度哪个赚钱。

---

## §7 风险、失效、缓解

### 7.1 数据可靠性

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| OKX API 临时挂(403/超时) | 中 | funding cache 不更新 | retry 3 次 + 指数退避,5min tick 容忍丢一两次 |
| OKX API 改 response 格式 | 低 | parser 错误 | Pydantic 校验返回数据,异常入 audit log |
| 单个 funding 期数据丢失 | 低 | 30d 窗口少 1 个样本 | min sample 20 保证 12+ 天就能算 |
| OKX 关闭(跑路) | 极低 | 整个 V6 数据停 | V6.1 多源聚合方案预留位 |

### 7.2 z-score 失效

| 失效情景 | 触发条件 | 检测 | 响应 |
|---|---|---|---|
| 制度突变 | BTC ATR 7d 变 > 50% | 自动监测 | warn,但不停 |
| Sustained extreme funding | 某币 z 连续 7d > 2 | 自动监测 | 该币暂停 funding-based entry 14d |
| 启动期 | 样本 < 20 | 强制 NULL | scorer 走旧逻辑 |

### 7.3 算法成本

OKX 公开 API rate limit:20 req/sec(IP-based,无 key 时降到 10)。

我们的实际消耗:
- 5min tick × 20 symbols = 4 req/sec 平均(burst 在 tick 瞬间 20 req)
- 1h z-score 重算 = 0 API call(纯 DB 计算)
- 启动回填 90d × 20 symbols = 20 next_page × 20 = 400 calls 一次性

**完全在 limit 内**,不需要付费 / 注册。

---

## §8 路线图(7 阶段)

每阶段验证通过才进下一阶段。

### 阶段 1(1 天):数据基础
- DB schema(2 新表 + 2 ALTER)
- v5_funding_collector 进程实现,每 5min tick
- 90d 历史回填一次
- 8 个测试(collector / z-score / 边界)
- **验收:** 启动 1h 后,funding_zscore_cache 有 top-20 × z-score 数据

### 阶段 2(0.5 天):scorer 集成
- scorer 写 trade_scores_v5.funding_z_score
- setup_type 派生扩展(funding_extreme_*)
- 3 测试
- **验收:** 新的 trade_scores 含 funding 数据;至少一笔 setup_type 是 funding_extreme_*

### 阶段 3(0.5 天):failure_taxonomy 启用
- `_h_against_4h_trend_no_funding` 用真 funding_z_score
- 2 测试(同方向背书 / 反向 veto)
- **验收:** 至少一笔被 FAILURE_MODE_MATCH:against_4h_trend_no_funding_filter veto

### 阶段 4(0.5 天):AI prompt 注入
- trading_assistant._decide_via_chat 加 funding block
- 2 测试(有 funding / 无 funding fallback)
- **验收:** AI reasoning text 至少有一次提到 "funding" 或 "z-score"

### 阶段 5(0.5 天):reflection 集成
- _load_close_context 拉 funding_z_score_at_entry
- reflection_prompt 加 funding section
- reflections.funding_z_score_at_entry 入库
- 2 测试
- **验收:** 新的 reflection 含 funding_z_score_at_entry,AI correction_idea 至少有一次提到 funding

### 阶段 6(1 天):API + 前端
- GET /api/v5/funding/status/{symbol} + GET /history/{symbol}
- types.ts 新类型
- V5ReflectionPage card 显示 funding
- V5AIStatusPage 加 funding HoloCard
- V5DashboardPage 加 setup_type 分项
- 4 测试(2 API + 2 RTL)
- **验收:** 浏览器 /v5/ai 显示 top-20 funding 状态;/v5/reflection 卡片有 funding 行

### 阶段 7(持续):监控 + 调参
- 跑 4 周累积数据
- 周聚合自动看 funding_extreme_* setup 的 win_rate 跟价格指标的对比
- Kelly engine 推 sizing 建议
- 用户批准或拒绝
- 视情况:
  - funding alpha 显著(>20% 改善 Sharpe)→ 进入 V6.1 多源聚合
  - funding alpha 弱(< 10% 改善)→ 重新考虑路线,可能换其他维度(OI、清算图谱)

---

## §9 验收标准

跑满 30 天后,以下都达成 = V6 真正在帮你赚钱:

1. **数据覆盖**:99%+ trade_scores_v5 有 funding_z_score(非 NULL)
2. **setup 多样性**:reflection 中至少 4 种独立 setup_type 含 funding_extreme 维度
3. **failure veto 触发**:against_4h_trend_no_funding_filter 至少在 5% 候选上触发
4. **AI 引用**:至少 30% reflection 的 correction_idea 提到 funding 维度
5. **PnL 对比**:funding_extreme_* setup 的累积 R 平均 vs RSI×MACD-only setup 的差异:
   - **目标**:funding-based ≥ rsi-based + 0.2 R(显著好)
   - **可接受**:差异在 ±0.1 R(信号独立有效但无明显胜负)
   - **失败**:funding-based < rsi-based - 0.2 R(funding 不工作,考虑换维度)
6. **Calibration 累积**:至少 3 个新 (model, conf) 桶因 funding-based 单达到 ≥10 笔样本

---

## §10 跟 V5.1 / Reflection / 未来 V7 的关系

### 与 V5.1 trend_aligned
- 完全并列,无依赖
- V5.1 处理"价格在哪",V6 处理"赌注在哪"
- 两者**同时触发**的 setup = 高质量信号
- 两者**单独触发**的 setup = 中等信号

### 与 Reflection
- V6 是 Reflection 的"养分":新 setup_type 维度让 reflection 系统抓到更多元化的失败/成功模式
- Reflection 完全无改动 — 它对 setup_type 是 schema-driven 的,新增维度 transparent

### 与未来 V7(可能的多特征 ML)
- V6 验证了"独立信息源"的价值(如果验收通过)
- V7 = V6 路径的延伸:
  - V6.1:多交易所 funding 聚合(去单点风险)
  - V6.2:OI 接入(类似 funding,但测仓位总量)
  - V6.3:清算图谱(Coinglass / 自建)
  - V7.0:替换 trading_assistant.decide 为 多特征 ML 模型(不是 LLM)

**这条路是渐进的:每加一个独立维度,reflection 系统自动告诉你这个维度有没有价值。** 完全数据驱动,不是凭感觉跳到 V7。

---

## §11 终态

90 天后,你的机器应该是:

- 你 **完全不用碰策略代码**
- 每周看 `/v5/reflection` Tab 3 的 Kelly 仓位建议,**批准或拒绝**
- 每月看 `/v5/dashboard` 的 setup_type 分项,**判断 funding 是不是真的赚到了**
- 数据 4 周累积后,**机器会告诉你下一步该做什么** — 是加 OI 还是换路子

**这才是 "可持续可学习的交易机器" 的真意:不是找完美策略,而是建一个能告诉你哪个特征维度真有 alpha 的系统。** V6 是验证这套范式的第一个独立维度。

---

**[End of design document]**
