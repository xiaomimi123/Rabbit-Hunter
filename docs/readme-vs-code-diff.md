# README vs 代码 差异梳理

> 快照日期：2026-06-23
> 范围：`README.md` / `PROJECT_STRUCTURE.md` / `scripts/backtest/README.md` 三份文档对比当前主分支代码。
> 性质：只读盘点，不动代码、不动文档。

---

## 背景

过去半年项目经历了 Binance → OKX 迁移、引入 M6 walk-forward、M9 知识层、SHADOW/LIVE 双模式、AI fail-open/fail-closed 行为开关等大改动，但 `README.md` 仍以 v4.x/Binance 时代的语言描述系统。这造成两个具体风险：

1. 新开发者按 README 配 `BINANCE_API_KEY` 而漏掉 OKX 凭证 → 跑不起来。
2. AI/用户基于 README 推断"功能不存在"而重复实现已存在的 M6/M9 能力。

本文件是分类后的差异清单，作为后续 README 重写或文档同步任务的输入。

---

## 方法

- README/docs 这一侧的"声明"由 Explore agent 从 `README.md` + `PROJECT_STRUCTURE.md` + `scripts/backtest/README.md` 提取。
- 代码这一侧的"事实"由另一个 Explore agent 直接 grep 源码、`.env.example`、`docker-compose.yml`、`App.tsx` 得到。
- 每条差异都标了 README/代码两侧出处（文件:行号）。

---

## 差异清单

### A. 交易所迁移未在 README 体现

| 项 | README 声明 | 代码现状 | 出处 |
|---|---|---|---|
| 默认交易所 | Binance Futures 是主、OKX 是"支持" | 默认 `EXCHANGE=okx`，OKX 是主、Binance 是备用 | `README.md:15` vs `.env.example:19`、`docker-compose.yml:32,56` |
| OKX 凭证变量 | 未列出 | `OKX_API_KEY` / `OKX_SECRET` / `OKX_PASSPHRASE` 必填 | `README.md:152-153` 只列 `BINANCE_*` |
| Binance 残留 | 当作主线 | 仍在用：`scripts/binance_positions.py`、`api/routes/system.py` 内 `ccxt.binanceusdm()` 测试调用 | 见 docker-compose 注释 "v0.5.2+ defaults to OKX" |
| `scripts/binance_trader.py` | README 列为下单执行模块 | 代码现状未验证仍在用 — 需 grep 确认是否已被 OKX 等价物取代 | `README.md:54` |

### B. 新增里程碑（M6 / M9）完全未进 README

| 项 | README 声明 | 代码现状 | 出处 |
|---|---|---|---|
| M6 Walk-Forward | `scripts/backtest/README.md:97` 写 "defer to V2" | 已实装：`scripts/walkforward.py`、`tests/test_walkforward.py`、`api/routes/v5_walkforward.py`、`scripts/backtest/cost_model.py` | docker-compose 还专门挂了报告目录（行 40） |
| M9 知识层 | 完全未提 | 活：`scripts/m9_knowledge.py`、`scripts/m9_validate.py`、`api/routes/v5_m9.py`、前端 `KnowledgePage.tsx`、`ValidateModal` | git log 最近 3 个 commit 都在改 M9 |
| `BacktestPage` | 未提 | 路由 `/backtest` 存在 | `App.tsx:19-54` |

### C. SHADOW / LIVE 双模式未在 README 主干

| 项 | README 声明 | 代码现状 | 出处 |
|---|---|---|---|
| 默认运行模式 | 主干文案是 LIVE 假设（"真实下单"） | SHADOW 是默认且安全姿态，paper_trades 表承接 | `PROJECT_STRUCTURE.md:16` 提了；`README.md` 未提 |
| `AI_FAIL_OPEN` / `SL_TP_FAIL_OPEN` / `AI_JUDGE_ENABLED` | 未提 | `.env.example:99` 等定义；scorer 最近 commit `de6101d` 就在调 fail-open 行为 | `api/schemas/v5_settings.py` |
| 模式切换接口 | 未提 | `api/routes/system.py` 暴露 SHADOW↔LIVE 切换，`system_settings` 表持久化 | — |

### D. 前端路由 / 组件命名错位

README 列的前端组件是老命名（`KillBoard.tsx` / `PositionsPage` / `OrderPage` / `AIStatus` / `StrategyConfig` / `WeightHistory` / `AnatomyPanel`），代码侧实际路由如下（`App.tsx:19-54`）：

```
/dashboard /portfolio /history /backtest /knowledge /audit
/learning /collect /market /reliability /diagnostics /settings
/chart/:symbol /manual /glossary
```

差异点：

- README 提的组件名几乎都不直接是路由。**`/audit` / `/diagnostics` / `/learning` / `/reliability` / `/knowledge` / `/manual` / `/glossary` / `/backtest` 这 8 条路由 README 未提及**。
- 实际组件在 `components/pages-v4/` 子目录下（V4 架构），README 描述的是 V3 时代扁平 `components/`。

### E. 环境变量清单滞后

README 给出的变量是 v4.3 时代基线。`.env.example` 当前包含但 README 未列：

- `EXCHANGE=okx`（开关变量本身）
- `OKX_API_KEY` / `OKX_SECRET` / `OKX_PASSPHRASE`
- `API_BEARER_TOKEN`（前后端鉴权机制，README 完全没提）
- `AI_FAIL_OPEN` / `SL_TP_FAIL_OPEN` / `AI_JUDGE_ENABLED`
- `MIN_VOLUME_24H_USDT` / `MIN_EXPECTED_MOVE_PCT`（新风控门槛）
- `ENABLE_SHORT_TRADING`

反向：README 提到的 `SUPABASE_URL` / `SUPABASE_KEY` 仍在 `.env.example` 但已标注 v4.3 遗留、改用 SQLite —— 处于"半死"状态，要么彻底删要么文档明确归档。

### F. 端口号不一致

- README/前端开发：`npm run dev` 走 Vite 默认（早期文档暗示 3000）。
- `docker-compose.yml` 把前端服务的端口设为 **5173**（Vite 默认其实是 5173，3000 是 next/CRA 默认）。
- 两个 Explore agent 给的端口也不一致（一份说 3000、一份说 5173）。需要核对 `vite.config.ts` 实际配置后统一描述。

### G. AI 层描述与现状

| 项 | README | 代码 |
|---|---|---|
| OpenAI Assistants (GPT-4o) | 主决策 | ✓ `scripts/ai/trading_assistant.py:_try_init_openai()` 活跃 |
| Vector Store / 历史交易记忆 | 强调 | ✓ `memory_uploader.py` 仍在 |
| DeepSeek | 称可选辅助 | ✓ 存在但 `DEEPSEEK_ENABLED=false` 默认关；最近 commit `de6101d` 处理它的余额不足 |
| 本地 LR | 标为 deprecated 兜底 | 文件 `local_rag.py` 还在，是否被引用未确认 |
| `reflection_runner.py` / `kelly_sizing.py` | 未提 | 文件存在 |

### H. Walk-Forward 自相矛盾

`scripts/backtest/README.md:97` 写 "Walk-Forward defer to V2"，但代码里 walk-forward 已经是 M6 主线特性，并已暴露 API + 前端 BacktestPage + ValidateModal。该子 README 自身就是过期文档。

### I. 策略 / 风控数值

README 给出的 SNIPER（2.0x ATR SL / 3.0x ATR TP）、VULTURE（1.5x / 2.5x、OI 下降 >3%）、Guardrails（SL 1.2-3.0x ATR、TP 2.0-6.0x ATR、1.5:1 R:R、仓位 0.3-1.2x）是 v4.x 数值。当前代码（`scripts/core/risk_calculator.py`、`v5_risk_calculator`、`v5_strategy.decide`）的实际阈值未在本轮调查中比对——这是清单里**唯一一类"待核对"的差异**，需要单独读一遍风控代码确认。

### J. 版本号叙事错位

- README 主标题：v5.0；但行文内仍以 V4.3 / V4.4 名义介绍核心功能。
- 代码侧：`v5_*` 前缀全面铺开（routes/schemas/hooks 都是），M6/M9 是当前活跃里程碑；V4.3/V4.4 只剩 `.env` 风控参数和 ws 路径 `/ws/v43` 几个残留点。

---

## 不在本次差异清单内（明确剔除）

- 个别函数实现细节差异（不读完单元测试无法判断）。
- 注释 / docstring 与代码差异（颗粒度太细，超出"对照 README"的目标）。
- 用户私有的 `.env`（不读）。

---

## 验证方法（怎么确认这份清单本身没错）

1. `git grep -nE 'BINANCE_|OKX_' .env.example` ── 确认 E 节凭证清单。
2. `git grep -n 'ccxt\.' scripts api` ── 确认 A 节交易所实例化分布。
3. `cat "Rabbit Hunterfronted/vite.config.ts"` ── 确认 F 节端口。
4. `git grep -n 'binance_trader' scripts api` ── 确认 A 节最后一行（`binance_trader.py` 是否还活）。
5. `git grep -nE 'walk.?forward|Walk.?Forward' scripts/backtest/README.md` ── 确认 H 节子 README 老化。
6. 读一遍 `scripts/v44_strategy_router.py` + `scripts/core/risk_calculator.py` ── 确认 I 节是否真的需要重新核对数值（清单里唯一标"待核对"的项）。

---

## 后续动作选项（按代价从小到大）

1. **修 H**：`scripts/backtest/README.md` 那条"defer to V2"已是事实错误，一两行即可改。
2. **修 E**：在 `.env.example` 上给变量补充 README 同步注释 + 删除真正归档的 Supabase 残留。
3. **重写 README 顶层结构**：把 OKX 设为主、补 SHADOW/LIVE/M6/M9/前端新路由章节。建议单独立项。
4. **核对 I**：读一遍 v5 风控代码确认策略数值是否仍和 README 一致；不一致再决定是改文档还是改代码。
