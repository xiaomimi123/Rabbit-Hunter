# 风控宪法 vs v5 代码 一致性报告

> 快照 2026-06-23
> 范围：宪法 7 条铁律 + 交易所路径
> 性质：核对 + 修复记录。每条标注"审计时状态"与"本次提交后状态"，方便回看。

---

## 一句话总览

审计当下 7 条铁律有 3 条不达标（其中 1 条高风险静默偏差）；本次提交全部修复 + 加单测防回归 + 文档同步。

| 优先级 | 规则 | 审计时 | 本次提交后 |
|---|---|---|---|
| 🔴 P0 | 规则 6 ENABLE_SHORT_TRADING 默认关 | ❌ 死开关、形同虚设 | ✅ 默认 false + scorer 硬闸门 + 单测 |
| 🟠 P1 | 规则 4 杠杆 3-5x 起步 + 反推 | ❌ 固定 10x、无反推；强平闸门兜底 ✅ | ✅ 默认 5x + `derive_safe_leverage` 反推 + 单测 |
| 🟡 P2 | 规则 1 单笔风险 1% | ⚠️ config/.env 默认 1.5%，靠 scorer `min()` 兜底 | ✅ 三处默认对齐 1% + 加 assert 防回归 |
| ✅ | 规则 2 SL 必挂 + 回滚 | ✅ | ✅ |
| ✅ | 规则 3 日内 -3% 锁仓 | ✅ | ✅ |
| ✅ | 规则 5 进化层窄区间 | ✅ | ✅ |
| ✅ | 规则 7 隐形杀手禁用 | ✅ | ✅ |
| ✅ | 任务 2.3 交易所路径 | ✅ | ✅ |

---

## 🔴 P0 — 规则 6：ENABLE_SHORT_TRADING 死开关

### 审计时

| 字段 | 宪法基准 | 代码实际 | 出处 | 一致性 |
|---|---|---|---|---|
| .env.example 默认 | `false` | `false` | `.env.example:78` | ✅ |
| config.py 默认 | `false` | **`"true"`** | `scripts/config.py:85`（旧） | ❌ |
| 调用链是否真的拦 SHORT | 是 | **整个 scorer / strategy / position_manager 路径**未读这个值 | — | ❌ |

**实际行为 + 风险**：用户以为 SHORT 已禁用（看 `.env.example`），但 (a) 没填 `.env` 时 `config.py` 默认值是 `"true"`；(b) 即便填了 `false`，也没有任何代码读它来拒做空——`strategy.decide()` 可直接返回 `side="SHORT"`，scorer 不二次检查。
**风险面**：宪法明确"自动批量做空默认关闭"，实际现状是默认放行。

### 本次提交后

| 字段 | 状态 | 落点 |
|---|---|---|
| dataclass 默认 | `False` | `scripts/config.py:46` |
| env 默认（`_load_from_env`） | `"false"` | `scripts/config.py:89` |
| scorer 硬闸门 | 已加 | `scripts/tasks/scorer.py` — AUTO_TRADING_DISABLED 之后：`decision.side=="SHORT" and not get_config().enable_short_trading → block_reason="SHORT_DISABLED"` |
| 单测 | 已加 | `tests/test_v5_scoring_pipeline.py::test_short_decision_blocked_when_enable_short_trading_is_false` |
| 防回归 | 已加 | `tests/test_safety_defaults.py::test_config_default_enable_short_trading_is_false` |

---

## 🟠 P1 — 规则 4：杠杆起步 3-5x + 反推

### 审计时

| 字段 | 宪法基准 | 代码实际 | 出处 | 一致性 |
|---|---|---|---|---|
| 起步杠杆 | 3-5x | **10x** | `scripts/config.py:25`、`scripts/v5_params.py:29`（旧） | ❌ |
| 按风险反推杠杆 | 实现 | **未实现**，`v5_risk_calculator` 把 `leverage` 当外部参数 | `scripts/v5_risk_calculator.py:28-70` | ❌ |
| 开仓前强平闸门（强平距 ≥ SL 距 × 2） | 实现 | ✅ 已实装，`MIN_LIQ_TO_SL_DISTANCE_RATIO=2.0` | `scripts/risk_gates.py:106-139` → `scorer.py:333-336` | ✅ |

**实际行为 + 风险**：杠杆永远 10x，没有"按 SL 距离反推到舒服的 3-5x"的逻辑。`gate_liquidation_distance` 是被动兜底——窄 ATR 行情下符合宪法预期的高质量单会被 10x 自我封死，gate 一直拒。

### 本次提交后

| 字段 | 状态 | 落点 |
|---|---|---|
| 默认杠杆 | 5x（三处） | `scripts/config.py:25,80`、`scripts/v5_params.py:111`、`.env.example:36` |
| 反推函数 | 已实装 | `scripts/v5_risk_calculator.py:derive_safe_leverage()` —— `max_safe = floor(entry / (R × sl_dist))`，cap 到用户配置 |
| scorer 调用顺序 | 已接入 | `scorer.py` 在 `plan()` 前先 `derive_safe_leverage()`，把反推结果传给 `plan(leverage=...)` |
| 单测 | 5 个新断言 | `tests/test_safety_defaults.py::test_derive_safe_leverage_*` |
| 兜底关系 | 不变 | `gate_liquidation_distance` 仍在，反推不满足时由它拒单 |

---

## 🟡 P2 — 规则 1：单笔风险 1%

### 审计时

| 字段 | 宪法基准 | 代码实际 | 出处 | 一致性 |
|---|---|---|---|---|
| 宪法常量 | 0.01 | 0.01 (`MAX_PER_TRADE_RISK_PCT`) | `scripts/risk_constitution.py:15` | ✅ |
| `config.py` 默认 | 0.01 | **0.015** | `scripts/config.py:47`（旧） | ❌ |
| `.env.example` 默认 | 0.01 | **0.015** | `.env.example:72`（旧） | ❌ |
| `v5_params.py` 默认 | 0.01 | 0.015 | `scripts/v5_params.py:110`（旧） | ❌ |
| 实际生效（scorer `_risk_per_trade`） | 0.01 | `min(constitution_pct, param_pct)` ⇒ 实际取 0.01（**靠 min() 兜底**） | `scripts/tasks/scorer.py:59-61` | ⚠️ |

**实际行为 + 风险**：典型"config 说一套、实际跑一套"——但方向是反过来的**安全偏差**。`config.py` / `.env` / `v5_params` 三处默认都是 1.5%，宪法常量是 1%。`scorer._risk_per_trade()` 用 `min(宪法, param)` 把实际值拉回 1%。
**潜在风险（中等）**：
1. 任何**新增**消费者只要直接 `cfg.risk_per_trade` 或 `os.getenv("V43_RISK_PER_TRADE")`，就会拿到 1.5%，绕过 scorer 的 `min()`。
2. 配置面误导：读 `.env.example` 会以为风险是 1.5%。
3. `min()` 一旦被改成 `max()` 或某次重构丢了，就是直接亏钱的静默偏差。

### 本次提交后

| 字段 | 状态 | 落点 |
|---|---|---|
| dataclass 默认 | `0.01` + 注释指向 `resolve_risk_pct_for_equity` | `scripts/config.py:50` |
| env 默认 | `"0.01"` | `scripts/config.py:90` |
| .env.example | `V43_RISK_PER_TRADE=0.01` + 注释指向资格层 | `.env.example:73` |
| v5_params 默认 | `0.01` | `scripts/v5_params.py:110` |
| 防回归 assert | 已加 | `scripts/tasks/scorer.py:_risk_per_trade()` 末尾，`assert result ≤ max(EQUITY_TIERS pct)` |
| 单测 | 4 个新断言 | `tests/test_safety_defaults.py::test_config_*_risk_per_trade_*` + `test_scorer_risk_per_trade_*` |

---

## ✅ 已守宪法的几条（保持不变）

### 规则 2 — SL 必挂 + 回滚

| 字段 | 宪法基准 | 代码实际 | 出处 | 一致性 |
|---|---|---|---|---|
| 开仓后同秒必挂 SL | ✅ | `V5PositionManager` 在 `try` 里 `create_order(stop_market)` | `scripts/v5_position_manager.py:36-47` | ✅ |
| 失败回滚 + 不写库 | ✅ | `SL_TP_FAIL_OPEN=false` 时 `broker.close_position()` 回滚 | `scripts/v5_position_manager.py:43-47` | ✅ |
| `gate_sl_attached` 二次验证 | ✅ | SL 价格非空才放行 | `scripts/risk_gates.py:142-148` → `scorer.py:332` | ✅ |

### 规则 3 — 日内 -3% 锁仓

| 字段 | 宪法基准 | 代码实际 | 出处 | 一致性 |
|---|---|---|---|---|
| `DAILY_DRAWDOWN_LIMIT_PCT` | 0.03 | 0.03 | `scripts/risk_constitution.py:22` | ✅ |
| `gate_daily_drawdown` | 实现 | 读 `paper_trades` 求和、比阈值拒新单 | `scripts/risk_gates.py:74-89` | ✅ |
| 调用时机 | 开仓前 | scorer setup-enabled 之后第一个 gate | `scripts/tasks/scorer.py:252-260` | ✅ |

### 规则 5 — 进化层窄区间

| 字段 | 宪法基准 | 代码实际 | 出处 | 一致性 |
|---|---|---|---|---|
| SL 下限 (×ATR) | 1.5 | 1.5 (`FINAL_SL_ATR_RATIO_MIN`) | `scripts/risk_constitution.py:50` | ✅ |
| SL 上限 (×ATR) | 2.2 | 2.2 (`FINAL_SL_ATR_RATIO_MAX`) | `scripts/risk_constitution.py:51` | ✅ |
| 最低 RR | 1.5 | 1.5 (`MIN_RR`) | `scripts/risk_constitution.py:28` | ✅ |
| 仓位下限 | 0.6 | 0.6 (`EVOLUTION_SIZE_MULT_MIN`) | `scripts/risk_constitution.py:67` | ✅ |
| 仓位上限 | 1.1 | 1.1 (`EVOLUTION_SIZE_MULT_MAX`) | `scripts/risk_constitution.py:68` | ✅ |

V4 时代的宽笼子（SL 1.2-3.0×、仓位 0.3-1.2×）确实已经收紧到宪法窄区间。`gate_final_sl_ratio` / `gate_min_rr` / `clamp_evolution_size_mult` 在 `scorer.py:317,326,327` 真正落到了开仓前。

### 规则 7 — 隐形杀手禁用

| 字段 | 宪法基准 | 代码实际 | 出处 | 一致性 |
|---|---|---|---|---|
| `rsi_neutral_macd_extending_long` 在禁用名单 | ✅ | 在 `DEFAULT_DISABLED_SETUPS` | `scripts/risk_constitution.py:29-30` | ✅ |
| 开仓前 `gate_setup_enabled` 检查 | ✅ | 拒掉禁用 setup | `scripts/risk_gates.py:151-173` → `scorer.py:244` | ✅ |

### 任务 2.3 — `binance_trader.py` 动钱路径

| 字段 | 实际 | 出处 |
|---|---|---|
| Factory 路由 | `EXCHANGE=okx` 默认走 `OkxTrader`，`=binance` 走 `BinanceTrader` | `scripts/exchange_factory.py:20-37,107-117` |
| 接口对齐 | 两边 `open_position` / `close_position` / `set_stop_loss` / `set_take_profit` 同 surface | `scripts/okx_trader.py` 顶部注释明确"与 BinanceTrader 同 surface" |
| 风险 | **无半死风险**——双路径都活跃 | — |

---

## 验收（怎么确认本报告 + 修复都没出错）

跑测试：

```bash
python3 -m pytest tests/test_safety_defaults.py tests/test_risk_gates.py tests/test_v5_scoring_pipeline.py -v
```

期望全绿（截至本次快照：51 + 7 = 58/58 passed）。

全套：

```bash
python3 -m pytest tests/ -q
```

允许失败：**仅** `tests/test_deepseek_adapter.py::test_decide_uses_chat_completions_in_deepseek_mode` 及其两个邻居——这是 `158c90f feat(reflection): failure_taxonomy 表 + 8 种子模式` 引入的 `chase_after_3pct_move` 分类器拦截测试 fixture，**在本次审计前就坏**，不在本次范围内。

---

## 不在本次范围（明确留给后续）

- DeepSeek adapter 3 个测试因 failure_taxonomy seed 失效——需独立修复。
- 策略层数值（SNIPER/VULTURE 阈值、anti-chase 参数）是否仍贴文档 §15 KPI——未核对。
- AI 失败分类语义是否与文档 §10 反思层一致——未核对。
- 杠杆反推用的 isolated margin 简化模型（`liq_dist ≈ entry / leverage`）忽略了 maintenance margin；OKX/Binance 实际 liq 公式更复杂，反推结果在极端低杠杆 (1-2x) 下可能保守过头。如果出现"明明应该能开但 gate 总拒"的实例，再单独立项把 `derive_safe_leverage` 升级成与交易所 liq 公式一致。
