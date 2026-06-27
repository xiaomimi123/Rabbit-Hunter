# Rabbit-Hunter 全面代码审计报告

> 快照: 2026-06-27
> 范围: 开单 / 止盈止损 / 持仓时间 / 死代码 4 块,按"动钱风险"排序
> 性质: **只报告、未改任何代码**。每条 finding 带 file:line 出处,可单独提取做修复 commit。

---

## 一句话结论

**代码层面有 2 个 HIGH 风险点会让真钱出问题**(LIVE 模式下 SL/TP 挂单状态可能跟 DB 脱离),**1 个策略层洞察值得优先处理**(SIGNAL_REVERSE 主导导致 TP_HIT 永不触发),其余多为设计去耦/死代码清理。

按"动钱风险"排:

| # | 严重性 | 类别 | 问题 | 推荐动作 |
|---|---|---|---|---|
| 1 | 🔴 HIGH | 开单 | LIVE 主仓成交但 SL/TP/回滚都失败 → 真实持仓孤立,DB 无记录 | 必修 |
| 2 | 🔴 HIGH | 开单 | `SL_TP_FAIL_OPEN=true` 时 SL 失败 → 仍写库为 OPEN,无 SL 保护 | 必修 |
| 3 | 🔴 HIGH | 开单 | OkxTrader.open_position 主仓成功就返 success=True,**忽略 SL/TP 失败**——与 v5_pm fail-closed 矛盾 | 必修 |
| 4 | 🔴 HIGH | 开单 | AI infra error 用 `startswith` 前缀判,漏匹配会让 SHADOW 误放真单或 LIVE 错拒 | 必修 |
| 5 | 🟠 MED | 出场 | **实际 52 笔 paper 0 个 TP_HIT** — SIGNAL_REVERSE (2.4min 平均) 抢先压制了 TP | 策略层调 |
| 6 | 🟠 MED | 出场 | V4.3 paper_monitor 与 V5 v5_position_monitor 两套出场引擎并存,V5 路径无 HORIZON_TIMEOUT 检查 | 选择性删 |
| 7 | 🟠 MED | 开单 | `ai_fail_open` 读 DB 优先,跟 config.py 环变量来源冲突 | 统一来源 |
| 8 | 🟠 MED | SL/TP | `positions_v5.sl_price`(规则值) vs `paper_trades.stop_loss`(AI 修正后) 语义不一致 | 字段统一 |
| 9 | 🟠 MED | 出场 | 4 个时间限制相互冲突: 8h backtest / 24h horizon / 15min soft / 3 extensions = 60min | 文档/统一 |
| 10 | 🟡 LOW | 设计 | 风控闸门顺序非 fail-fast(SHORT_DISABLED / setup_enabled 位置可优化) | 重排 |
| 11 | 🟡 LOW | 死代码 | 28+ 文件 (19 Python + 9 前端) 完全未引用 | git rm |
| 12 | 🟡 LOW | 死代码 | 3 个 API 路由 (weights/market/system) 已 commented out 但 .py 还在 | 删除 |

---

## 一、开单链路 (动钱核心)

### 1.1 完整链路 (从信号到下单)

```
enriched_queue.get()
  → [1] 白名单 (v5_symbol_whitelist) silently skip
  → [2] 指标 calculate_indicators (RSI/MACD/ATR)
  → [3] strategy.decide() — 三 mode 之一返回 Decision
  → [4] 并发上限检查 _count_open_positions ≥ 3 → MAX_CONCURRENT_POSITIONS
  → [5] 自动交易开关 _enable_auto_trading → AUTO_TRADING_DISABLED
  → [6] SHORT_DISABLED gate (config.enable_short_trading)
  → [7] gate_setup_enabled (DEFAULT_DISABLED_SETUPS + M8 自动剪枝)
  → [8] gate_daily_drawdown (今日累计 PnL vs 3%)
  → [9] plan() 算 RiskPlan + derive_safe_leverage 反推杠杆
  → [10] AI 二审 trading_assistant.decide
     ├ failure_taxonomy 匹配 → AI_REJECTED
     ├ infra error + SHADOW || ai_fail_open → pass-through
     └ AI 拒 → AI_REJECTED
  → [11] clamp_evolution_* (sl/tp/size multipliers 钳到窄区)
  → [12] 最后铁律 (5 个 gate):
     gate_final_sl_ratio / gate_min_rr / gate_sl_attached
     / gate_liquidation_distance / gate_per_trade_risk
  → [13] paper_pm.open_position 或 live_pm.open_position
     LIVE: broker.create_order(主) → 挂 SL → 挂 TP → INSERT positions_v5
  → [14] 写 trade_scores(executed=1) + WS 广播
```

### 1.2 🔴 HIGH-1: LIVE 孤立持仓风险

**位置**: `scripts/v5_position_manager.py:30-78`,`scripts/okx_trader.py:527-551`

**场景**:
1. 主仓 `broker.create_order(market)` 成功 → 交易所实际有持仓
2. SL 挂单失败
3. fail-closed 触发 `broker.close_position(symbol)` 回滚 — **回滚也失败**(网络/API 错误)
4. v5_pm 抛异常 → scorer 写 `block_reason=OPEN_FAILED:...` — **不写 position_id**

**结果**: 交易所有真实持仓 + DB 无对应记录 → position_monitor 找不到该仓位 → 需手动 reconcile。

**叠加**: 同时 `OkxTrader.open_position()` 即使 SL/TP 失败也返回 `success=True`(只把 error 塞到 `result["stop_loss_error"]`),上层 v5_pm 若没显式检查 error 字段,就以为整个 open 成功。

**建议**:
- v5_pm 回滚失败时仍 INSERT positions_v5 但 `status='ERROR_RECONCILE_NEEDED'`,保留所有 context 让人工平账
- OkxTrader.open_position 在 `SL_TP_FAIL_OPEN=false` 时 SL/TP 失败必须 raise

### 1.3 🔴 HIGH-2: SL_TP_FAIL_OPEN=true 真单无 SL

**位置**: `scripts/v5_position_manager.py:43-47`

```python
except Exception as e:
    if not SL_TP_FAIL_OPEN:
        self.broker.close_position(symbol)
        raise Exception(...)
    else:
        print(f"SL 失败但保留: {e}")  # ← 代码继续
# 继续写库 status='OPEN'
```

**问题**: 若用户某天打开 `SL_TP_FAIL_OPEN=true`(应急用),SL 挂单失败时仅打印 warn,继续写库 status='OPEN'。**库里有仓位、交易所无 SL** → 监控代码以为 SL 挂上了。

**建议**:
- 改成 `status='OPEN_NO_SL'`,或额外字段 `sl_attached: bool`
- 文档明确这是应急模式,不该常态开启
- SHADOW 模式忽略此旋钮(SHADOW 不挂真单)

### 1.4 🔴 HIGH-3: OkxTrader fail-open vs v5_pm fail-closed 矛盾

**位置**: `scripts/okx_trader.py:527-551`

```python
sl_result = self._place_protective_stop(...)
if sl_result.get("success"):
    result["stop_loss"] = stop_loss
else:
    result["stop_loss_error"] = err     # ← 仅记录,不 raise

if take_profit:
    tp_result = ...
    if tp_result.get("success"):
        result["take_profit"] = take_profit
    else:
        result["take_profit_error"] = err
        # ← 也仅记录

return result   # success=True (主仓成功就 True)
```

`v5_position_manager` 期望 `broker.create_order(stop_market)` 失败时 raise(它的 try/except 才能触发回滚),但 OkxTrader.open_position 包了一层 try-and-store-error,**SL/TP 失败永远不抛**。

**结果**: v5_pm 的 fail-closed 逻辑形同虚设——OkxTrader 已经把 SL/TP 失败"消化"了。

**建议**: OkxTrader 在 `SL_TP_FAIL_OPEN=false`(或读 env)时,SL/TP 失败必须 raise。

### 1.5 🔴 HIGH-4: AI infra error 前缀判别不完备

**位置**: `scripts/tasks/scorer.py:319-322`

```python
is_infra_error = (
    reasoning.startswith("AI 调用异常")
    or reasoning.startswith("AI 调用超时")
)
```

`trading_assistant.py` 实际可能返回的前缀:
- `"AI 调用异常 {type}:..."`(line 450)
- `"AI 调用超时(>...s)..."`(line 446)
- `"FAILURE_MODE_MATCH:..."`(line 369) — 非 infra,正常拒
- `"AI 未初始化"`(line 379) — 是 infra 但前缀不一样

**结果**: "AI 未初始化" 不匹配 → SHADOW 模式不会 pass-through 而是真拒单。或者未来新加错误前缀漏匹配 → SHADOW 模式误放 / LIVE 模式错拒。

**建议**: 在 `AIResult` 里加 `error_kind: Literal['infra' | 'rule' | 'ok']` 字段,scorer 显式 switch,不靠 reasoning 字符串。

### 1.6 🟠 MED 级别其他 (简列)

- **MED-1: SHORT_DISABLED 位置非 fail-fast** — `scorer.py:247` 在 setup_enabled / daily_dd 之后才检查;若 SHORT 信号多,白白查 DB。建议提前到 `_enable_auto_trading` 之后。
- **MED-2: close_position 异常吞** — `v5_position_manager.py:119-122`,平仓 broker 失败仅打印不抛。回滚路径里这会让外层以为回滚成功。
- **MED-3: final_size 除零风险** — `scorer.py:365-372` 若 `final_sl_dist_pct=0` (极端 ATR) 会 `ZeroDivisionError`,被 OPEN_FAILED 吞掉但语义错误。
- **MED-4: `_ai_fail_open(db_path)` vs `config.ai_fail_open` 双来源** — 库优先,库未初始化时默认 false,导致 env var `AI_FAIL_OPEN=true` 被忽略。
- **MED-5: SHADOW 路径 SL_TP_FAIL_OPEN 不该生效** — 旋钮全局,但 SHADOW 不挂真单,该值应被忽略。

---

## 二、止盈止损 + 杠杆 + 仓位

### 2.1 公式拆解 (动钱算式)

```
entry        = enriched.current_price                    (无延迟)
atr_15m      = indicators.atr_15m                        (Wilder 14)
sl_distance  = v5_sl_atr_mult(1.5) × ai.sl_mult[0.8,1.5] × atr_15m
                                  → clamp → final ratio ∈ [1.5, 2.2] × atr
tp_distance  = v5_tp_atr_mult(2.5) × ai.tp_mult[1.5,3.5] × atr_15m
size_usdt    = (balance × risk_pct) / (sl_dist_pct × leverage)
                × ai.size_mult[0.6, 1.1]
                cap by   (balance × risk_pct) / (final_sl_dist_pct × lev)
leverage     = derive_safe_leverage(entry, atr, leverage_cap=5)
                = min(5, floor(entry / (2 × sl_distance)))
                cap_low 1
```

### 2.2 宪法对齐

| 宪法铁律 | 代码实现 | 一致性 |
|---|---|---|
| ① 单笔风险 ≤ 1% | `gate_per_trade_risk` 在 final_size 后兜底 | ✅ |
| ② 进场必挂 SL | LIVE: `v5_position_manager` try/挂/失败回滚 | ✅(但见 1.2/1.3 HIGH) |
| ③ 日内 -3% 锁仓 | `gate_daily_drawdown` 开仓前查 | ✅ |
| ④ 杠杆 3-5x | `derive_safe_leverage` + `gate_liquidation_distance` 双兜底 | ✅ |
| ⑤ SL ∈ [1.5, 2.2]×ATR | `gate_final_sl_ratio` + AI clamp [0.8, 1.5] | ⚠️ 见 2.3 |
| ⑥ SHORT 默认关 | `scorer.py:247` SHORT_DISABLED gate | ✅ |
| ⑦ 杀手 setup 禁用 | `gate_setup_enabled` + `DEFAULT_DISABLED_SETUPS` | ✅ |

### 2.3 ⚠️ 数学不闭合: AI 0.8 必拒

`EVOLUTION_AI_SL_MULT_MIN = 0.8`(risk_constitution.py:58)
`FINAL_SL_ATR_RATIO_MIN  = 1.5`(risk_constitution.py:50)
`v5_sl_atr_mult           = 1.5`(默认)

→ 当 AI 给 `sl_multiplier = 0.8`,final ratio = 1.5 × 0.8 = **1.2** < 1.5 → `gate_final_sl_ratio` **必然拒单**。

意味着 AI 在 0.8 - 1.0 区间内的所有调整都会被宪法拒,**clamp 区间下沿是"法律死区"**。代码行为正确(拒),但 clamp 配置本身不闭合。

**建议**: 把 `EVOLUTION_AI_SL_MULT_MIN` 改 1.0,或把 `FINAL_SL_ATR_RATIO_MIN` 改 1.2 以扩大 AI 可调下限。

### 2.4 🟠 MED-8: 两张表 SL 字段语义不同

| 表 | 字段 | 含义 |
|---|---|---|
| `positions_v5` | `sl_price` | **规则 SL**(plan() 出,AI 修正前) |
| `paper_trades` | `stop_loss` | **AI 修正后 SL** |

`v5_position_manager.py:68-72` 写 `positions_v5.sl_price = risk.sl_price` (规则值)
`paper_position_manager.py:114-121` 写 `paper_trades.stop_loss = final_sl_price` (AI 修正后)

**风险**: 任何监控/导出/前端展示如果对两张表用同一逻辑读 sl_price,会得到不同语义的值。

**建议**: 统一在 positions_v5 也存 AI 修正后的 final_sl_price(那才是真挂到交易所的价)。

---

## 三、持仓时间 + 出场逻辑 (重要洞察)

### 3.1 实际 52 笔 paper 出场分布 (现场数据)

```
exit_reason       次数  pnl%    avg 持仓h
─────────────────────────────────────────
SIGNAL_REVERSE     28   +0.41    0.04  (2.4 min!)
AI_TIMEBOX         13   -1.17    0.25  (15 min)
MANUAL_USER         8   +0.21    0.005
SL_HIT              2   -3.56    0.068
TRAILING_SL_HIT     1   -2.03    0.036
TP_HIT              0    —       —      🚨
HORIZON_TIMEOUT     0    —       —      🚨
AI_EXTEND_MAX       0    —       —      🚨
```

### 3.2 🟠 MED-5: 0 个 TP_HIT — SIGNAL_REVERSE 抢先压制

**SIGNAL_REVERSE 占 53.8% 且平均 2.4 分钟就出**,完全没给 TP 触发机会。`v5_position_monitor.py:60-76` 判定逻辑:

- LONG 仓持仓中: RSI 涨过 35 *或* MACD 柱由金叉转死叉 → SIGNAL_REVERSE
- 检查频率 30 秒(`scripts/tasks/paper_monitor.py`)

**症状**:
- 入场刚成立 (RSI < 40, MACD 刚金叉),价格稍涨 → RSI 触 35 阈值 → 立即 SIGNAL_REVERSE
- 即便方向是对的,**平均只赚 +0.41%**,远没让仓位走到 2.5×ATR 的 TP

**这是策略层的"次优出场"** —— 不是 bug,但实际兑现的 RR 远低于 1.5(SL 距 ≈ 2.5%, 实际平均 +0.4%)。本质是 entry 进场条件 (RSI/MACD 极端) 跟 exit 反转条件 (RSI 回到中性) 时间窗太近。

**3 个备选优化**(改前都要 backtest):

1. **删 SIGNAL_REVERSE** — 只用 SL/TP 出场,让 TP 有机会触发
2. **加最短持仓** — SIGNAL_REVERSE 只在 entry 后 ≥30 分钟生效
3. **改 RSI/MACD 阈值** — RSI 触发线从 35 改 55 之类,留更宽容忍

### 3.3 🟠 MED-6: 两套出场引擎并存

**V4.3 路径**: `scripts/tasks/paper_monitor.py` → `paper_position_manager.update_current_price()` → 检查 SL/TP/**HORIZON**
**V5 路径**: `scripts/v5_position_monitor.py:check_exit_triggers()` → 检查 SL/TP/SIGNAL_REVERSE/SOFT_TARGET (**无 HORIZON**)

实际数据中 `HORIZON_TIMEOUT = 0` 表明:V4.3 路径要么没在跑、要么仓位都在 24h 前就被 V5 路径平掉了。

**建议**: 选择性归一 — V5 monitor 加 `gate_horizon_timeout`,或确认 V4.3 paper_monitor 仍在跑。

### 3.4 🟠 MED-9: 4 套时间限制不对齐

| 限制 | 值 | 设定 | 检查 |
|---|---|---|---|
| backtest max_hold | 8h (480 min) | `backtest/runner.py:38` | `position_sim.py:35` |
| paper horizon | 24h | `local_db.py:328,372` | `paper_position_manager.py:337-345` |
| soft_target | 15 min | `paper_position_manager.py:36` | `v5_position_monitor.py:108-118` |
| max_extensions | 3 | `v5_params.py:107` | `v5_position_monitor.py:114` |

最严的"实际有效"是 soft_target × (1+3 extensions) = **60 min** < backtest 8h < paper 24h。**backtest 跟实战的"最长持仓"差 8 倍。**

**含义**: 主实验 backtest PF 2.08 是按 8h max-hold 跑的,实战 60 min 截止 → 实战 vs backtest 存在**结构性持仓窗口 mismatch**。这可能是 paper 战绩 PF 0.77 比 backtest 差的隐藏原因之一。

**建议**: 让 backtest 跟 paper 用同一个 max-hold(都 60 min 或都 8h),才能比较公平。或者让 paper 也允许 8h(去掉 max_extensions 上限或调大)。

### 3.5 💡 AI_TIMEBOX 是亏的 (策略洞察)

13 笔 AI_TIMEBOX 平均 -1.17% — 说明 AI 在 15min 续仓决策时倾向于"留住"但实际市场没回报。`extension_count` all = 0 (从未续仓) 说明 AI 总在 `quick_yes_no()` 时返回 "CLOSE"。

**可能原因**: AI prompt 没强调"等待 TP"的好处,或 DeepSeek 在短线上更保守。

---

## 四、死代码清单 (Phase 1 可零风险删除)

### 4.1 Python 脚本 (8 个直接删)

```bash
git rm scripts/technical_indicators.py        # 重复 — v5_indicator_engine 已替代
git rm scripts/setup_database.py             # V4.3 一次性建库
git rm scripts/execute_schema.py             # V4.3 schema 工具
git rm scripts/diagnose_ai_tuning.py         # 一次性诊断
git rm scripts/diagnose_binance_config.py    # 一次性诊断
git rm scripts/diagnose_data_flow.py         # 一次性诊断
git rm scripts/check_collection_data.py      # 一次性检查
git rm scripts/create_test_weight_history.py # V4.3 测试脚手架
git rm scripts/collector.py                  # 已 DEPRECATED stub
```

### 4.2 前端 V5 legacy pages (9 个直接删)

App.tsx 路由表完全未引用:

```bash
cd 'Rabbit Hunterfronted/components/pages'
git rm V5ActivePositionsPage.tsx
git rm V5AIStatusPage.tsx
git rm V5DashboardPage.tsx
git rm V5OrderHistoryPage.tsx
git rm V5ReflectionPage.tsx
git rm V5SettingsPage.tsx
git rm V5SignalHistoryPage.tsx
git rm V5SignalsPage.tsx
git rm V5StrategyConfigPage.tsx
```

(保留 V5ChartPage / V5ManualOrderPage / V5GlossaryPage — 仍被 App.tsx 引用)

### 4.3 API 路由僵尸 (3 个)

`api/main.py:258-260` 已 `# include_router` 注释:
```bash
git rm api/routes/weights.py    # V4.3 schema, 未 rewire
git rm api/routes/market.py     # V4.3 schema
git rm api/routes/system.py     # V4.3 schema (system_mode 切换由 v5_settings 接管)
```

### 4.4 Phase 2 待人工确认 (8 个)

- `scripts/ai_learning_loop.py` — reflection worker 是否完全替代?
- `scripts/deepseek_ai_learner.py` — 跟 trading_assistant.py 关系?
- `scripts/cvd_analyzer.py` — 仍是生产指标?
- `scripts/monitor_deepseek.py` — 临时开发工具?
- `scripts/compute_rewards.py` — M9 还用?
- `scripts/position_stats.py` — KPI endpoint 已替代?
- `scripts/backfill_p3a_match_and_thr.py` — V4.3 迁移用,归档?
- `Rabbit Hunterfronted/ui/`(整个目录) — 已经空,确认后 `rm -rf`

### 4.5 数据库 schema 死字段

paper_trades 表里 V4.3 时期的字段(如 `weights / weights_version / ai_decision_id / opportunity_density_score` 等)在最近 collector 日志里持续报 "迁移失败,表不存在" — 已经清掉了,日志噪音可忽略。

---

## 五、可执行建议清单 (按优先级)

### 🔴 立即修 (3 个 HIGH,动钱风险)

1. **v5_position_manager 回滚失败时仍写 DB** (status='ERROR_RECONCILE_NEEDED' + 完整 context) — 防孤立持仓
2. **OkxTrader.open_position SL/TP 失败必须 raise** — 让 v5_pm 的 fail-closed 真生效
3. **AI infra error 改成 enum 字段** — 不靠 reasoning prefix 判别

### 🟠 计划修 (策略 + 半死)

4. **解决 0 TP_HIT 问题** — 选 A/B/C 之一:删 SIGNAL_REVERSE / 加最短持仓窗 / 调 RSI 反转阈值。**先 backtest 验证再上**
5. **统一 backtest vs paper max-hold** — 都 60 min 或都 8h,做新 backtest 验
6. **统一两张表 SL 字段语义** — positions_v5.sl_price 也存 AI 修正后值

### 🟡 收尾 (清理 + 文档)

7. **Phase 1 死代码 git rm** — 19 文件,零风险
8. **ai_fail_open 来源统一** — 让 DB 是唯一真相源,或让 env 是唯一真相源
9. **闸门顺序重排** — SHORT_DISABLED / setup_enabled 提前
10. **文档化 SL_TP_FAIL_OPEN=true 为"应急模式仅限"**

---

## 附录: 报告生成的 4 个 sub-agent 原始数据

由 4 个并行 Explore agent 产出,本报告做了交叉验证 + 重新排序。原始数据可在 conversation 上下文中找到:

- **A (开单链路)**: 2 HIGH + 5 MED + 4 设计 finding
- **B (SL/TP/杠杆)**: 3 节公式拆解 + 7 条宪法对齐表 + 实际挂单时序
- **C (出场逻辑)**: 7 个 exit_reason 全集 + 4 套时间限制冲突 + 实际数据 SQL 验证
- **D (死代码)**: 28+ 文件清单,分 Phase 1/2/3 可执行
