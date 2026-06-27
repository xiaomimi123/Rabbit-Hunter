# Paper 0.77 vs Backtest 2.08 — Max-Hold 时间窗实验

> 2026-06-27 · walk-forward 实测对照 · 由审计报告 MED-5/MED-9 引发
> 实验脚本: `scripts/experiments/macd_cross_entry_wf.py`
> 报告产物: `data/experiments/exit_time_2026q1/baseline_max{60,480}.json`

## 一句话结论

**Paper PF 0.77 不是策略变差,是 max_hold 窗口被压到 60 分钟把赢单提前掐死。** Backtest 把 `MAX_HOLD_MINUTES=480` 改成 60,在完全同一份 OOS 数据上 net PF 从 **1.51 退到 0.50**,刚好跨过 paper 区间。

## 实验设计

|  | 配置 |
|---|---|
| 策略 | macd_reversal_long (Variant B,4h MACD 零轴下方金叉) |
| 标的池 | 17 (APT/ARB/ATOM/AVAX/BNB/DOGE/DOT/FIL/LINK/LTC/NEAR/PEPE/SOL/UNI/WLD/XRP/ZEC) |
| 期间 | 2026-01-01 → 2026-03-31 (Q1,独立于训练) |
| Walk-forward | train 60d / OOS 14d / step 14d → 2 fold,总 OOS 76 笔 |
| 成本模型 | OKX maker 0.02% / taker 0.05% / slip 0.05% (realistic preset) |
| 出场基础 | SL 1.5×ATR / TP 2.5×ATR (固定倍数) |
| **变量** | `--max-hold-minutes` 分两组: **60** (paper 实际) vs **480** (backtest 默认) |

## 实测数据

### 净指标

| 指标 | max_hold = 60 min | max_hold = 480 min | 变化 |
|---|---|---|---|
| OOS 笔数 | 76 | 76 | 同 |
| 胜率 | **38%** | **58%** | +20 pp |
| 平均 R | **-0.24** | **+0.26** | +0.50 R |
| Gross PF | 1.04 | **2.30** | 2.2× |
| **Net PF** | **0.50** | **1.51** | **3.0×** |
| Max DD (R) | -21.9 | -9.1 | -2.4× |

### 出场原因分布 (76 笔 OOS)

| 出场原因 | 60min | 480min | 差 |
|---|---|---|---|
| **TP_HIT** | 7 (**9 %**) | 40 (**53 %**) | **+44 pp** |
| SL_HIT | 16 (21 %) | 30 (39 %) | +18 pp |
| HORIZON_TIMEOUT | **53 (70 %)** | 6 (8 %) | **-62 pp** |

### 每类出场的真实回报

| 出场原因 (60min) | 笔数 | 胜率 | avg net R |
|---|---|---|---|
| TP_HIT | 7 | 100% | **+1.40** |
| SL_HIT | 16 | 0% | -1.27 |
| HORIZON_TIMEOUT | 53 | 42% | **-0.14** (基本平,但是负的) |

## 解读

### 为什么 paper 跟 backtest 差 3 倍

Backtest 的 PF 2.08 是基于"每笔仓位最长可持有 8 小时"算的——这给 53% 的信号留出了走到 TP(2.5×ATR)的时间窗。**Paper 的实际窗口是 60 分钟**(`v5_position_monitor` 的 `SOFT_TARGET_MINUTES=15` × 4 次 extension = 60),60 分钟内**只够 9% 的信号走到 TP**;剩下的:
- 21% 走到 SL → 凭空亏 1.27R/笔
- **70% 时间到强平**,平均轻微浮亏 -0.14R/笔

也就是说,**paper 把 80% 应该走到 TP 的赢单提前用"中性强平"结掉了**——但中性强平的 avg_R 仍是负的(-0.14),因为成本(fee+slip 0.07R 单笔)无法被中性结算覆盖。

### 这跟审计报告的关系

`docs/code-audit-report.md` MED-5 推测 SIGNAL_REVERSE(2.4分钟即出局)是元凶,但本实验**不需要 SIGNAL_REVERSE 也能复现** paper 的差成绩,只要把 max_hold 从 480 改到 60。SIGNAL_REVERSE 实际是在 60 分钟窗口里 "提前赌一把"——把"等到 HORIZON 中性平"变成"碰到 RSI 反转早平",**两者都源于窗口太短**。

## 3 个候选方向(都需要回测/paper 双验)

| 方向 | 改什么 | 预期 PF 落点 | 风险 |
|---|---|---|---|
| **α. 延长 paper 窗口** | `v5_max_extensions: 3 → 30+`,让最长 480 min | 1.51 | 锁定时间长,仓位周转慢,同时活仓 3 个的并发上限更紧 |
| **β. 收紧 TP 距离** | `v5_tp_atr_mult: 2.5 → 1.5`,让 TP 在 60 min 内更容易触达 | 0.8 - 1.2 (估) | 总 R 上限降,但触达率上;扫到部分赢单中途回吐 |
| **γ. 双管齐下** | extensions 拉到 8 (= 120 min) + tp_mult 调 2.0 | 中位 | 折中 |

**推荐先做 α**——只需改 v5_params.py 一个值,不动出场逻辑,可立即跑一周 paper 验。如果 paper PF 能升到 1.0+ 说明这就是主因,后续再细调 β/γ。

## 副发现 — Vegas 出场不是答案

之前 vegas 实验 (`docs/vegas-exit-experiment.md`)否决了 vegas 通道出场——98% 信号在通道下方被 reject。本实验给的解释:**vegas 不是出场太严,是 macd_reversal_long 这种"早期反转入场"本来就在长期 EMA 下方做**——用任何"超出通道范围"的出场都会大砍信号。问题始终在 max-hold 窗口,不在出场结构。

## 没在本次跑的(留待下次)

- `max_hold = 120 / 240` 中位档(数据点之间应是连续函数)
- 启用 `vegas_sl_only`(SL = vegas 下沿) × max_hold 240,看 SL 距离能否吸收 HORIZON 损失
- Paper 实地跑 1 周 `v5_max_extensions=30`,验证 backtest α 推断

## 不动主线代码

按约定本次只跑实验出报告,**不改 `v5_params.py` 任何默认值**。下次再讨论是否切 paper 配置。
