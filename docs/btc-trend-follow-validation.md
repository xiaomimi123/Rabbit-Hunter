# BTC 顺势 Pine 候选验证 — 证伪报告

> 2026-06-28 · 依据 `给终端的指令-BTC顺势候选验证.md`
> 候选 setup: `macd_trend_follow_long` (从用户 Pine V4.6 翻译)
> 性质: M9 候选验证,**只验不上**,出报告等用户拍板

## 一句话结论

**证伪。4 组对照 net PF 0.44 - 0.79,全部远低于判定线 1.2。"反转在大盘币不灵但顺势可能灵"假设不成立——顺势在 BTC/ETH/SOL 也不灵,在 17 山寨上更差。建议干净放弃,不进 M9 候选队列。**

## Pine → 候选规则翻译

| 项 | 原 Pine | 实现 (`scripts/experiments/macd_cross_entry_wf.py:_detect_trend_follow_long`) |
|---|---|---|
| 时间帧 | 用户 15m chart 测的 | 15m K 线 |
| MACD 金叉 | DIF 上穿 DEA (12/26/9) | ✓ |
| RSI 区间 | 40 < RSI < 70 | ✓ |
| 牛市过滤 | close > EMA(50) | ✓ |
| 方向 | 多 (空第一阶段关) | 只做多 |

新加 detector 是 15m-based,跟 reversal (Variant B) 的 4h-based 入场完全不同。

## 4 组对照设计

| 组 | 标的 | 出场 (SL/TP × ATR, max_hold) |
|---|---|---|
| 1 | BTC + ETH + SOL | Pine 原 (1.5 / 1.8, **120 min** ≈ 8 根 15m K 线) |
| 2 | BTC + ETH + SOL | RH 标准 (1.5 / **2.5**, **240 min**) |
| 3 | 17 山寨池 (对照) | Pine 原 |
| 4 | 17 山寨池 (对照) | RH 标准 |

固定: train 60d / OOS 14d / step 14d / Q1 2026 / OKX realistic 成本

## 4 组对照数据

| | **n** | **胜率** | **avg R** | **Net PF** | gross PF | maxDD R | avg 持仓 min |
|---|---|---|---|---|---|---|---|
| **BIG3 × Pine** | 135 | 42% | -0.23 | **0.60** | 1.14 | -31.1 | 79 |
| **BIG3 × RH** | 135 | 43% | -0.14 | **0.79** | 1.30 | -23.1 | 123 |
| **17 山寨 × Pine** | 886 | 36% | -0.38 | **0.44** | 0.77 | -335.2 | 74 |
| **17 山寨 × RH** | 886 | 34% | -0.36 | **0.54** | 0.83 | -321.6 | 109 |

### 出场原因分布

| | TP_HIT | SL_HIT | HORIZON |
|---|---|---|---|
| BIG3 × Pine | 36% | 33% | 30% |
| BIG3 × RH | 36% | **47%** | 16% |
| 17 山寨 × Pine | 30% | 46% | 24% |
| 17 山寨 × RH | 28% | **58%** | 14% |

TP 命中率不算低 (28-36%),但 RR 不够大。RH 标准下 SL 命中比例反而升 (TP 距离拉远 → 行情没走那么远就先碰 SL)。

## 按标的拆解 (BIG3)

### Pine 出场

| 标的 | n | 胜率 | net R | 评 |
|---|---|---|---|---|
| BTCUSDT | 39 | **56%** | -2.90 | 胜率高 entry 有 edge,但 RR 不行,总仍亏 |
| ETHUSDT | 53 | 36% | -16.28 | 失败 |
| SOLUSDT | 43 | 37% | -11.80 | 失败 |

### RH 标准

| 标的 | n | 胜率 | net R | 评 |
|---|---|---|---|---|
| BTCUSDT | 39 | 49% | **-0.52** | 几乎打平,但样本太少 |
| ETHUSDT | 53 | 40% | -10.75 | 失败 |
| SOLUSDT | 43 | 42% | -7.69 | 失败 |

## 核心解读

1. **顺势打法在大盘币也没找到 edge。** BIG3 净 PF 0.60-0.79,跟同期 reversal Variant B 在山寨池上的 PF 1.51 差距巨大。"反转不灵的地方顺势能灵"假设不成立。

2. **BTC 单标 Pine 出场胜率 56% 有 entry edge,但 RR 不行。** Pine 原方案 TP 1.8×ATR (RR 1.2:1) 过窄,winners 没充分跑;切到 RH TP 2.5 反而 SL 命中升到 47% — 行情没那么持续,中途反向就先碰 SL。**两种 RR 配置都吃不到顺势行情的肉。**

3. **17 山寨池 PF 0.44-0.54 比 BIG3 更差** (跟 reversal 在 17 池的 PF 1.51 完全反向)。说明:
   - 山寨币不是趋势驱动,顺势策略噪音多
   - 反转策略本来就是为山寨设计的,顺势在山寨上是反向适配

4. **出场策略对比**:RH 标准比 Pine 略好(PF 0.79 vs 0.60),但都不够救。**问题不在出场,在 entry 本身没 edge。**

5. **不能再扩研究消化** — 已 4 组对照,trend 清晰。继续优化 (TP 倍数扫描 / 时间帧调整) 是给一个垂死想法续命,投资回报比低。

## 跟现 reversal 的相关性

按指令要求检查 "本候选与现有反转 setup 是否高度相关"。

由于 PF 远低于 1.2 已经证伪,**相关性已无意义**——一个亏钱策略跟赢钱策略不相关也不能补盲区。

(若需要原始数据可后补:对照 OOS entries 的 entry_ts 重叠,但本次因证伪无需做。)

## 判定

按指令第 56-58 行预定的判定标准:

| 阈值 | 结果 |
|---|---|
| PF > 1.5 (通过,新独立 setup) | ❌ 最高 0.79 |
| PF 1.2-1.5 (弱 edge,限定标的) | ❌ |
| **PF < 1.2 (证伪,丢弃)** | ✅ **触发** |

**判定: 证伪。**

引用指令原文:
> 3. PF < 1.2 → 证伪,丢弃。**这个"提高胜率版"若没通过,干净放弃,不可惜——证伪一个凭感觉的旧假设也是收获。**

## 建议

| 动作 | 说明 |
|---|---|
| ✅ 干净放弃 | 不进 M9 候选验证队列,不做 paper |
| ✅ 保留 detector 代码 | scripts/experiments/macd_cross_entry_wf.py 内的 `detect_entries_trend_follow_long` 留着,以后如要做"BTC 长期持有/逆势底"类的反向实验有基础设施 |
| ❌ 不动主线 | scripts/v5_strategy.py 不加 trend_follow_long mode |
| ❌ 不试图救 | 不做 TP 倍数扫描 / 时间帧切换 / RSI 边界微调。**沉没成本谬误警惕** |
| ✅ 沉淀经验 | 顺势 + 大盘币 + 短线 (60-240min) 这条线已经过严格验证,不需要再质疑 |

## 不做的方向 (留 explicit)

- BTC 长持(日线 / 周线)趋势跟随:本验证只覆盖 15m 短线,不能证伪/证实长持顺势
- 用 ETH/BTC 做"波动率筛选"的反转策略:不在本指令范围
- 用 funding rate 做"挤压做多"的非顺势/非反转策略:不在本指令范围

## 不动的代码 (按指令)

- ❌ 现 reversal 策略 (Variant B + 240 + SR 门槛 已落地)
- ❌ 风控宪法
- ❌ 仓位计算
- ❌ paper 配置 (v5_max_extensions=15 不动)
- ❌ M9 候选队列

## 产出

- `scripts/experiments/macd_cross_entry_wf.py` 扩展:
  + `Variant` 加 `"trend_follow_long"`
  + `detect_entries_trend_follow_long()` + `_rsi_series()` helper
  + CLI flags `--sl-atr-mult` `--tp-atr-mult` 让 Pine vs RH 出场参数可对照
- 5 份 walk-forward 报告 `data/experiments/btc_trend_follow_2026q1/*.json` (gitignored 本地保留)
- 本报告 `docs/btc-trend-follow-validation.md`
