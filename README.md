# Rabbit Hunter v5.0

币安合约量化交易系统 — 规则引擎 + OpenAI 智能决策层

---

## 系统架构

```
市场数据 (Binance Futures)
        │
        ▼
  MarketScanner          扫描涨跌幅异动币种
        │
        ▼
  DeepCollector          采集 OI / 资金费率 / CVD / K线
        │
        ▼
  StrategyScorer         V4.3 特征提取 + 评分 + V4.4 策略路由
  (SNIPER / VULTURE)
        │
        │  高分信号
        ▼
  OpenAI TradingAssistant   二次审查 + TP/SL 参数调优
  (GPT-4o + Vector Store)
        │
        ▼
  BinanceTrader          下单 + 止盈 + 止损
        │
        ▼
  学习闭环               交易结果写入 Vector Store → AI 从历史学习
```

---

## 核心模块

### 后端 (`scripts/`)

| 模块 | 说明 |
|------|------|
| `tasks/collector_main.py` | 主入口，启动四个异步任务 |
| `tasks/scanner.py` | 扫描市场异动 |
| `tasks/deep_collector.py` | 深度数据采集 |
| `tasks/scorer.py` | 评分 + 策略路由 + AI 接入点 |
| `tasks/writer.py` | 异步写入 Supabase |
| `v44_strategy_router.py` | SNIPER / VULTURE 策略路由 |
| `v43_position_manager.py` | 持仓管理（开仓 / 平仓 / 止损更新） |
| `binance_trader.py` | Binance Futures 下单执行 (ccxt) |
| `core/risk_calculator.py` | ATR / 仓位 / 止损计算 |
| `config.py` | 统一配置 (`TradingConfig` 单例) |

### AI 层 (`scripts/ai/`)

| 文件 | 说明 |
|------|------|
| `trading_assistant.py` | OpenAI Assistants API 核心决策引擎 |
| `guardrails.py` | 硬规则：SL/TP/size 参数限幅 |
| `memory_uploader.py` | 交易结果日志 + 上传 Vector Store |
| `prompt.py` | GPT System Prompt |
| `setup_assistant.py` | 一次性初始化工具 |

### API 后端 (`api/`)

FastAPI 服务，提供前端所需的 REST 接口。

| 路由 | 说明 |
|------|------|
| `routes/positions.py` | 持仓查询 |
| `routes/scores.py` | 评分数据 |
| `routes/weights.py` | 权重管理 |
| `routes/market.py` | 市场数据 |
| `routes/system.py` | 系统状态 |

### 前端 (`Rabbit Hunterfronted/`)

React 19 + Vite 6 + TypeScript + TailwindCSS 交易终端。

| 组件 | 说明 |
|------|------|
| `components/KillBoard.tsx` | 信号列表 |
| `components/PositionsPage.tsx` | 持仓监控 |
| `hooks/usePositions.ts` | 持仓数据 (React Query) |
| `hooks/useKillQueue.ts` | Kill Queue 轮询 |
| `services/store.ts` | UI 状态 (Zustand) |

---

## 交易策略

### SNIPER（狙击手）
- 目标：P3A 早期拉升阶段
- 方向：做多 (LONG)
- 条件：结构分 > 60，OI 正向确认，资金费率正常
- 止损：2.0x ATR（默认），AI 可调整至 1.2–3.0x
- 止盈：3.0x ATR（默认），AI 可调整至 2.0–6.0x

### VULTURE（秃鹫）
- 目标：P3B/P4 出货阶段
- 方向：做空 (SHORT)
- 条件：OI 下降 > 3%，结构分 > 70
- 止损：1.5x ATR（默认），AI 可调整至 1.2–3.0x
- 止盈：2.5x ATR（默认），AI 可调整至 2.0–6.0x

### AI 决策层规则
AI 在规则引擎放行后做二次判断，可以：
- 拒绝执行信号（override 规则引擎）
- 调整 SL/TP 倍数（受 guardrails 限幅）
- 调整仓位大小（0.5x–1.2x）

硬性约束（guardrails，AI 无法突破）：
- SL: 1.2x–3.0x ATR
- TP: 2.0x–6.0x ATR，且 TP ≥ SL × 1.5（最低 1.5:1 风险收益比）
- 仓位: 0.3x–1.2x

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
pip install openai          # AI 层
```

### 2. 配置 `.env`

```env
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_service_role_key

# Binance
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=false       # true = 测试网

# 交易开关
ENABLE_AUTO_TRADING=true
V43_ENABLED=true
V44_ENABLED=true
V43_RISK_PER_TRADE=0.015    # 每笔最大风险 1.5%
BINANCE_LEVERAGE=10

# OpenAI AI 层
OPENAI_API_KEY=sk-...
OPENAI_AI_ENABLED=true
OPENAI_TRADING_MODEL=gpt-4o
OPENAI_DECISION_TIMEOUT=20  # 秒，超时自动走规则引擎
# 首次运行 setup_assistant.py 后填入：
OPENAI_ASSISTANT_ID=asst_xxx
OPENAI_VECTOR_STORE_ID=vs_xxx
```

### 3. 初始化 OpenAI Assistant（首次）

```bash
python scripts/ai/setup_assistant.py
```

打印出 `OPENAI_ASSISTANT_ID` 和 `OPENAI_VECTOR_STORE_ID`，填入 `.env`。

### 4. 上传历史交易数据（初始记忆）

将历史交易记录导出为 JSONL 格式放到 `data/ai_trade_log.jsonl`，然后：

```bash
python -m scripts.ai.memory_uploader --upload
```

### 5. 启动系统

```bash
# 后端 API
python -m api.main

# 数据采集 + AI 交易
python -m scripts.tasks.collector_main

# 前端
cd "Rabbit Hunterfronted"
npm run dev
```

---

## AI 学习闭环

每次交易平仓后，结果自动记录到 `data/ai_trade_log.jsonl`。

定期（建议每天/每周）运行上传命令，让 AI 从积累的交易记录中学习：

```bash
python -m scripts.ai.memory_uploader --upload
```

上传后，AI 在下次决策时会自动检索相似历史案例作为参考。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 交易执行 | Python + ccxt + Binance Futures API |
| 数据库 | Supabase (PostgreSQL) |
| AI 决策 | OpenAI Assistants API (GPT-4o) + Vector Store |
| API 服务 | FastAPI |
| 前端 | React 19 + Vite 6 + TypeScript + TailwindCSS |
| 状态管理 | React Query (服务端) + Zustand (UI) |

---

> 仅供学习研究使用。加密货币交易存在极高风险，请自行评估。
