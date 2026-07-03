# Rabbit Hunter v5

加密合约量化交易系统 — 规则引擎 + AI 决策层 + Walk-forward 验证 + 知识库

> **默认安全态：SHADOW（影子）模式**。
> 全新克隆后开箱即用，所有信号写入 `paper_trades`，**不触及真实账户**。
> 要切真实下单，明确把 `.env` 里 `ENABLE_AUTO_TRADING=true`，并通过 `/system/mode` 接口或前端 Settings 页切到 LIVE。

> **v45 入口约定**：唯一受支持的采集器入口是 `python -m scripts.tasks.collector_main`。
> 旧的 `scripts/collector.py` 已彻底删除。

---

## 系统架构

```
市场数据 (默认 OKX Futures；EXCHANGE=binance 可切回 Binance)
        │
        ▼
  MarketScanner          异动扫描 + 24h 成交额过滤
        │
        ▼
  DeepCollector          OI / funding / CVD / K线
        │
        ▼
  StrategyScorer         V4.3 特征 + V4.4 策略路由 + 风控闸门
  (SNIPER / VULTURE)
        │
        │  高分信号
        ▼
  OpenAI TradingAssistant   二次审查 + TP/SL 调优
  (GPT-4o + Vector Store)
        │
        ▼
  Exchange Factory          EXCHANGE=okx → OkxTrader
                            EXCHANGE=binance → BinanceTrader
        │
        ▼
  SHADOW → paper_trades 表     |     LIVE → 真实下单 + positions_v5
        │
        ▼
  学习闭环 + 反思层           平仓 → Vector Store + 结构化反思
```

并行旁支（不在主流程，但喂养决策依据）：

```
M9 知识层    书籍 / 笔记 → 候选规则 → m9_validate（异步 walk-forward）→ reports/wf_*.json
M6 回测      scripts/walkforward.py + cost_model + reporter
```

---

## SHADOW / LIVE 双模式

| 模式 | 触发 | 行为 | 落地 |
|---|---|---|---|
| **SHADOW**（默认） | `ENABLE_AUTO_TRADING=false` 或显式切换 | 信号完整通过、虚拟下单 | `paper_trades` |
| **LIVE** | `ENABLE_AUTO_TRADING=true` + 模式切到 LIVE | 真实下单到 OKX / Binance | `positions_v5` + 远端账户 |

模式状态持久化在 `system_settings` 表，可通过 `api/routes/v5_settings.py` 的 PATCH `/api/v5/settings` 接口在线切换（key: `enable_auto_trading` / `system_mode`）。

行为旋钮（`.env`，默认全部 fail-closed）：

| 变量 | 默认 | 含义 |
|---|---|---|
| `AI_FAIL_OPEN` | `false` | AI 故障时是否仍下单（true = 绕过 AI 决策） |
| `SL_TP_FAIL_OPEN` | `false` | SL/TP 挂单失败是否保留刚开的仓位 |
| `AI_JUDGE_ENABLED` | `false` | 本地 LR 兜底（deprecated） |

注：SHADOW 模式在 AI 推理基础设施失败时（如 DeepSeek 余额不足）会 pass-through 放行；LIVE 模式仍 fail-closed。详见 `scripts/tasks/scorer.py`。

---

## 核心模块

### 后端核心（`scripts/`）

| 模块 | 说明 |
|------|------|
| `tasks/collector_main.py` | v45 唯一入口，启动 7+ 个异步协程（scanner / scorer / monitor / reflection_worker / funding_collector 等）|
| `tasks/scanner.py` | 市场异动扫描 |
| `tasks/deep_collector.py` | 深度采集（OI / funding / CVD / K线） |
| `tasks/scorer.py` | 评分 + 策略路由 + AI 接入点 + 风控闸门 |
| `tasks/writer.py` | 异步写 SQLite（可选 Supabase 镜像） |
| `tasks/v5_funding_collector.py` | 资金费率独立采集器 |
| `tasks/v5_reflection_worker.py` | 平仓后异步反思 |
| `tasks/paper_monitor.py` | SHADOW 仓位监控 |
| `v5_strategy.py` | 三 mode 策略规则引擎（and_strict / trend_aligned / macd_reversal_long）|
| `v5_position_manager.py` | LIVE 持仓管理（开仓 / 止损 / 回滚）|
| `paper_position_manager.py` | SHADOW 虚拟持仓管理 |
| `risk_constitution.py` | 风控宪法（铁律） |
| `exchange_factory.py` | 按 `EXCHANGE` 选 OkxTrader / BinanceTrader |
| `okx_trader.py` / `binance_trader.py` | 两套同接口的下单实现 |
| `core/risk_calculator.py` | ATR / 仓位 / 止损计算 |
| `walkforward.py` | M6 walk-forward 回测引擎 |
| `m9_knowledge.py` / `m9_validate.py` | M9 知识库 + 候选规则异步验证 |
| `config.py` | `TradingConfig` 单例 |

### AI 层（`scripts/ai/`）

| 文件 | 说明 |
|------|------|
| `trading_assistant.py` | OpenAI Assistants API + DeepSeek 兼容客户端（同文件） |
| `guardrails.py` | SL/TP/size 限幅 |
| `kelly_sizing.py` | Kelly 仓位计算 |
| `memory_uploader.py` | 平仓日志 → Vector Store |
| `reflection_runner.py` / `reflection_prompt.py` | 反思层 |
| `confidence_calibration.py` | 置信度校准 |
| `failure_taxonomy.py` / `failure_taxonomy_seed.py` | 失败模式分类 |
| `local_rag.py` | 本地 LR 兜底（deprecated） |
| `setup_assistant.py` | Assistant + Vector Store 首次初始化 |
| `prompt.py` | System prompt |

### API 后端（`api/routes/`）

FastAPI，容器内绑 `0.0.0.0:8000`，host 默认 `127.0.0.1:8000`。

| 路由 | 说明 |
|------|------|
| `positions.py` | 持仓查询 |
| `scores.py` | 信号评分 |
| `v5_account.py` | OKX 账户资产同步 |
| `v5_ai.py` | AI 决策日志 |
| `v5_charts.py` | K 线数据 |
| `v5_constitution.py` | 风控宪法读取 / 调整 |
| `v5_funding.py` | 资金费率视图 |
| `v5_m9.py` | M9 候选规则 CRUD + 验证触发 |
| `v5_manual_order.py` | 手动下单 |
| `v5_position_close.py` | 主动平仓 |
| `v5_reflection.py` | 反思结果查询 |
| `v5_settings.py` | 用户设置持久化 |
| `v5_strategy_config.py` | 策略参数 |
| `v5_walkforward.py` | Walk-forward 报告 |
| `v5_trader_kpi.py` | KPI 中控（PF / Sharpe / MaxDD / 宪法违规 / AI 健康度）|

### 前端（`Rabbit Hunterfronted/`）

React 19 + Vite 6 + TypeScript + TailwindCSS + Zustand + React Query。

路由表（`App.tsx`）：

| 路径 | 页面 |
|---|---|
| `/overview` | 账户概览（资产 / 活仓汇总 / KPI，为根路径 `/` 的重定向目标）|
| `/dashboard` | 仪表盘（OKX 资产 / 实时持仓 / AI 决策） |
| `/portfolio` | 活跃持仓 |
| `/history` | 交易历史 |
| `/market` | 市场扫描 |
| `/collect` | 数据采集监控 |
| `/learning` | 学习层 |
| `/backtest` | Walk-forward 报告（M6） |
| `/knowledge` | 候选规则 + 书籍管理（M9） |
| `/audit` | 反思 / 审计 |
| `/diagnostics` | AI 决策诊断 |
| `/reliability` | 可靠性检查 |
| `/settings` | 配置 |
| `/chart/:symbol` | K 线图 |
| `/manual` | 手动下单 |
| `/glossary` | 术语表 |

旧路径 `/v5/*` 全部重定向到新路径（`App.tsx:46-57`）。

---

## 交易策略

> 以下默认数值取自 v4.3/v4.4 时代。`v5_risk_calculator` 与 `v5_strategy_config` 路由可能暴露更动态的阈值，精确数值以代码为准。

### SNIPER（狙击手）
- 目标：P3A 早期拉升
- 方向：做多
- 默认 SL：2.0x ATR；TP：3.0x ATR

### VULTURE（秃鹫）
- 目标：P3B / P4 出货
- 方向：做空（**默认禁用**，需 `ENABLE_SHORT_TRADING=true`）
- 默认 SL：1.5x ATR；TP：2.5x ATR

### 风控宪法（`risk_constitution.py` + `guardrails.py`，AI 无法突破）
- SL 倍数：1.2x – 3.0x ATR
- TP 倍数：2.0x – 6.0x ATR
- 风险收益比：TP ≥ SL × 1.5
- 仓位倍数：0.3x – 1.2x
- 单笔风险：`V43_RISK_PER_TRADE`（默认 1.5%）

---

## AI 决策层

仓库里历史上存在三套"AI 给交易打分 / 审查"的实现。v5 角色分工：

| 实现 | 文件 | 角色 | 默认 | 开启方式 |
|------|------|------|------|----------|
| **OpenAI Assistant** | `scripts/ai/trading_assistant.py` (`_try_init_openai`) | 主决策（规则放行后再审，可调 SL/TP/仓位） | 开 | 配 `OPENAI_API_KEY` + 跑 `setup_assistant.py` |
| **DeepSeek** | 同上文件内的 `_try_init_deepseek()` | 辅助打分器（产生 `ai_score`） | 关 | `DEEPSEEK_ENABLED=true` |
| **本地 LR** | `scripts/ai/local_rag.py` | 兜底（deprecated，需训练 npz） | 关 | `AI_JUDGE_ENABLED=true`（不推荐） |

---

## 快速开始

### A. Docker Compose（推荐）

```bash
cp .env.example .env
# 至少填：OKX_API_KEY / OKX_API_SECRET / OKX_API_PASSPHRASE（公开行情可空，私有端点必填）
# AI 决策层：填 OPENAI_API_KEY
docker compose up -d

# 浏览器
open http://localhost:5173        # 前端
curl http://localhost:8000/system/healthz   # API 健康检查
```

服务：

- `api`：FastAPI（host 127.0.0.1:8000）
- `collector`：`scripts.tasks.collector_main`
- `frontend`：nginx 反代静态前端（host 127.0.0.1:5173）

挂载卷：

- `./data` → `/app/data`（SQLite + JSONL 日志）
- `./reports` → `/app/reports`（M6 walk-forward 报告）

### B. 本地开发

```bash
# 后端依赖
pip install -r requirements.txt
cp .env.example .env  # 填 OKX / OPENAI

# API
python -m api.main          # http://localhost:8000

# 采集 + 交易
python -m scripts.tasks.collector_main

# 前端（注意：本地 dev 端口是 3000，与 Docker 的 5173 不同）
cd "Rabbit Hunterfronted"
npm install
npm run dev                 # http://localhost:3000
```

### C. 首次 OpenAI Assistant 初始化

```bash
python scripts/ai/setup_assistant.py
# 打印出 OPENAI_ASSISTANT_ID + OPENAI_VECTOR_STORE_ID，回填到 .env
```

### D. 上传历史交易（可选）

```bash
python -m scripts.ai.memory_uploader --upload
# Vector Store 更新后，下次 AI 决策会自动检索相似案例
```

---

## 配置（.env）

完整字段见 `.env.example`，分五组：

| 组 | 关键字段 |
|---|---|
| ① 最小集 | `EXCHANGE`（默认 `okx`）/ `OKX_API_*` / `BINANCE_API_*` / `OKX_TESTNET` / `BINANCE_TESTNET` / `ENABLE_AUTO_TRADING`（默认 `false`） |
| ② AI | `OPENAI_API_KEY` / `OPENAI_ASSISTANT_ID` / `OPENAI_VECTOR_STORE_ID` / `OPENAI_DECISION_TIMEOUT` / `DEEPSEEK_*` |
| ③ 安全 | `API_BEARER_TOKEN` + 前端构建参数 `VITE_API_TOKEN` |
| ④ 风控 | `V43_*` / `V44_*` / `ENABLE_SHORT_TRADING` / `MIN_VOLUME_24H_USDT` / `MIN_EXPECTED_MOVE_PCT` |
| ⑤ 行为旋钮 | `AI_FAIL_OPEN` / `SL_TP_FAIL_OPEN` / `AI_JUDGE_ENABLED` |

**安全 / 鉴权**：默认所有端口绑到 `127.0.0.1`。想暴露到 LAN：

1. 改 `docker-compose.yml` 前端 ports 为 `0.0.0.0:5173:80`；
2. 同时设 `API_BEARER_TOKEN` 和前端构建 `VITE_API_TOKEN`（必须相同；docker-compose 已自动同步）。

---

## M9 知识层

候选规则的全生命周期：

```
书籍 / 笔记 → 候选规则 (m9_knowledge.py) → walk-forward 验证 (m9_validate.py 异步) → reports/wf_*.json → 前端 BacktestPage
```

入口在前端 `/knowledge`（`KnowledgePage.tsx`）。验证通过 `ValidateModal` 触发，异步落到 `reports/`。

后端 API：`api/routes/v5_m9.py`、`api/routes/v5_walkforward.py`。

---

## M6 Walk-Forward 回测

`scripts/walkforward.py` 是独立 walk-forward 引擎，配合：

- `scripts/backtest/cost_model.py` — 成本模型（realistic / optimistic / pessimistic）
- `scripts/backtest/reporter.py` — KPI 判定

报告输出到 `reports/wf_*.json`，前端 `/backtest` 页查看。docker-compose 已挂卷。

---

## 学习闭环与反思

```
平仓 → data/ai_trade_log.jsonl
     → memory_uploader.py → Vector Store
     → v5_reflection_worker → reflection_runner → SQLite → 前端 /audit
```

每笔平仓自动写日志；定期手动跑 `memory_uploader --upload` 让 Vector Store 更新。反思层全自动，结果在 `/audit` 页查看。

---

## 数据持久化

| 存储 | 内容 |
|---|---|
| SQLite `data/rabbit_hunter.db` | 主库：信号、持仓、纸面交易、反思、设置 |
| `data/ai_trade_log.jsonl` | 平仓 JSONL 日志（喂 Vector Store） |
| `reports/wf_*.json` | M6 walk-forward 报告 |
| Supabase（可选） | v4.3 历史选项，留空即关 |

---

## 技术栈

| 层 | 技术 |
|----|------|
| 交易执行 | Python + ccxt + OKX / Binance（factory 切换） |
| 后端 | FastAPI + asyncio |
| AI 决策 | OpenAI Assistants API (GPT-4o) + Vector Store；DeepSeek（兼容客户端） |
| 主库 | SQLite；可选 Supabase 镜像 |
| 前端 | React 19 + Vite 6 + TypeScript + TailwindCSS |
| 状态 | React Query（服务端）+ Zustand（UI） |
| 测试 | Vitest + Testing Library + MSW（前端）；pytest（后端，`tests/`） |
| 编排 | docker-compose（api + collector + frontend） |

---

> 仅供学习研究使用。加密货币合约交易存在极高风险，请自行评估。
