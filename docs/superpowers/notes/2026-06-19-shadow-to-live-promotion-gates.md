# SHADOW → LIVE 升级硬门槛清单

> **Owner:** 你
> **目的:** 用真钱开仓前,必须每条都打勾。任何一条不达标 → 不准切 LIVE。
> **背景:** 历史 42 笔 paper trade 跑出过 -477 USDT / -212% drawdown。
>           可见这个 system 在没经过严格门槛验证前,完全有可能让你亏真钱。
> **检查命令:** `docker exec rabbit-hunter-api python /app/scripts/check_live_readiness.py`

---

## 一类:数据量 (Sample Size)

必须有足够统计意义的样本,不然评估出来是噪音。

- [ ] **A1.** SHADOW trial 已运行 ≥ **14 个连续日**(不含 collector 停机时段)
- [ ] **A2.** 自动开仓(`strategy_id='v5_rsi_macd'`)的 **closed paper_trades ≥ 100 笔**
- [ ] **A3.** 至少 **2 个 setup_type 桶各有 ≥ 30 笔**(不能全靠 1 个桶的运气)

---

## 二类:盈利能力 (Profitability)

毛收益 ≥ 0 太宽松。必须扣"现实成本"后仍然正。

- [ ] **B1.** 自动单**毛总 PnL > 0 USDT**(累加所有自动 v5_rsi_macd 的 pnl 列)
- [ ] **B2.** 自动单**扣 0.20% 往返成本后净 PnL > 0 USDT**
      *(模拟:每笔减去 entry_price × 0.002 × size_usdt 的成本)*
- [ ] **B3.** 自动单**净 Profit Factor ≥ 1.20**(sum(净正 pnl) / |sum(净负 pnl)|)
- [ ] **B4.** **avg 净 PnL/笔 ≥ +0.05 USDT**(微利但显著 > 0)
- [ ] **B5.** 胜率 ≥ **42%**(配合 R:R=1.67,42% 是盈亏平衡线)

---

## 三类:风险控制 (Risk Control)

最重要 — 即使整体赚也不能有撑不住的回撤。

- [ ] **C1.** **最大回撤 ≤ 30% of peak** *(用累计 PnL 曲线算 max drawdown)*
- [ ] **C2.** **单笔最大亏损 ≤ 账户 3%**(应该被 risk_per_trade=1.5% 约束,但要验证没漏)
- [ ] **C3.** **连续亏损 ≤ 8 笔**(对 PF 1.2 边际策略,9 连败几乎必然心态崩)
- [ ] **C4.** **0 笔触发 `OPEN_FAILED:*`**(代码异常导致开仓失败,说明实盘要爆)

---

## 四类:系统行为 (System Behavior Hygiene)

数据要干净,否则不知道测的是 system 还是你的情绪。

- [ ] **D1.** trial 期间 **0 笔 `MANUAL_USER` 平仓**(不要按"立即平仓",让系统自主跑)
- [ ] **D2.** trial 期间 **0 笔 `v5_manual` 策略开单**(不要从 Signals 页点"此参数模拟开单")
- [ ] **D3.** AI 失败率 (`AI_REJECTED` 中含 "调用异常" 的) ≤ **5%** of all AI calls
- [ ] **D4.** 没有任何 `AI_UNAVAILABLE_LIVE_FAIL_CLOSED` 拦截(说明 AI 健康度)
- [ ] **D5.** trial 期间没改过 `v5_*` 策略参数(改了就时钟归零重新跑)

---

## 五类:配置一致性 (Config Consistency)

SHADOW 跑的参数,要跟你切 LIVE 后用的参数**完全一致**。

- [ ] **E1.** `v5_funding_anti_pile_threshold` 跟 SHADOW trial 完全相同
- [ ] **E2.** `v5_trend_rsi_long_threshold` 跟 SHADOW trial 完全相同
- [ ] **E3.** `v5_sl_atr_mult` / `v5_tp_atr_mult` 跟 SHADOW 完全相同
- [ ] **E4.** `v5_risk_per_trade` 跟 SHADOW 完全相同 *(LIVE 时,可以小于 SHADOW 用于试水)*
- [ ] **E5.** `v5_leverage` 跟 SHADOW 完全相同(或者 LIVE 更低)
- [ ] **E6.** AI provider + model 跟 SHADOW 完全相同
- [ ] **E7.** `MIN_VOLUME_24H_USDT` 跟 SHADOW 完全相同(扫到的 symbol 池一致)

---

## 六类:基础设施 (Infrastructure Ready)

切 LIVE 当下不会因为缺配置炸掉。

- [ ] **F1.** OKX **API key + secret + passphrase** 全部配置在 .env / docker-compose
- [ ] **F2.** OKX API 测试通过 — 能成功 `fetch_balance()` 返回真实余额
- [ ] **F3.** `enable_auto_trading=true` 在 system_settings(`v5_settings` PATCH 设)
- [ ] **F4.** OKX 账户 USDT 余额 **≥ 100 USDT**(避免余额不够开仓直接 error)
- [ ] **F5.** OKX 账户 **leverage 已手动设到 10x**(跟 SHADOW 一致)
- [ ] **F6.** OKX 账户**没有任何手动开的 position**(避免污染监控)
- [ ] **F7.** 切到 LIVE 时,先 `system_mode='LIVE'` 但 `enable_auto_trading=false`,
        盯前 30 分钟手动观察:**信号生成 OK + AI 调 OK + 但不真开仓**。
        前 30 分钟无异常 → 再开 `enable_auto_trading=true`。

---

## 七类:认知准备 (Mental Checklist) — 给自己看

每条都要诚实回答。

- [ ] **G1.** 我能接受最大回撤 30% — 真亏 30 USDT/100 USDT 我不会去看 K 线 5 分钟一次
- [ ] **G2.** 我读完了 backtest 跟 SHADOW 真实持仓时间 18 倍差异的报告,知道 backtest 数字水分
- [ ] **G3.** 我承诺 LIVE 前 14 天 SHADOW 数据全部公开诚实统计,不挑好的看
- [ ] **G4.** 如果 LIVE 第 1 天亏损 > 5%,我会立刻 `system_mode='SHADOW'` 暂停,不会"再忍一忍"

---

## 中止条件 (Abort Criteria)

trial 期间任何一条触发 → **立刻停 SHADOW trial,reset 配置,重新做实验**:

| 信号 | 行动 |
|---|---|
| 累计 PnL < -200 USDT(就算只跑了 3 天) | abort,debug 原因 |
| 单日回撤 > 30% | abort,可能策略碰到 regime 切换 |
| 连续 5 笔自动单亏损 | 暂停 24h 观察行情,不要追加规则改动 |
| AI 失败率持续 > 20%(超 1 小时) | 检查 key / DeepSeek 状态 |
| `paper_pm.open_position` 抛异常 | 立刻看代码,先 fix 再说别的 |

---

## 评估流程

1. 跑 `check_live_readiness.py` 看你现在打了几个勾
2. 没打满的 → 继续 SHADOW 等
3. 打满的 → 把当前所有 v5_param 和 docker-compose env 拍快照存档(`docs/superpowers/notes/N-live-config-snapshot.md`)
4. 按 F7 渐进切换(LIVE+no-auto → LIVE+auto)
5. 第 1 周设 `risk_per_trade=0.5%`(SHADOW 是 1.5%),小仓位验证
6. 第 1 周通过 → 升到 SHADOW 的 1.5%
7. 持续监控 G1-G4

---

## 当前预估 (2026-06-19 时点)

历史 42 笔(SHADOW 之前的数据,**不算 trial 数据**):
- A2 自动 closed ≥ 100? **不达标**(只有 29 笔)
- B1 自动总 PnL > 0? **几乎不达标**(-2.69 USDT)
- B5 胜率 ≥ 42%? **不达标**(45% 含手动单,自动单单独算可能更低)
- C1 max DD ≤ 30%? **远不达标**(-212% peak)
- D1 0 笔 MANUAL_USER? **不达标**(已有 8 笔)
- D2 0 笔 v5_manual? **不达标**(已有 13 笔)
- F4 OKX 余额 ≥ 100 USDT? **未验证**(`fetch_balance` 之前一直异常)

**结论:目前完全没有任何接近 LIVE-ready 的状态。SHADOW trial 必须按规则从零开始跑 14 天,期间禁止手动干预。**
