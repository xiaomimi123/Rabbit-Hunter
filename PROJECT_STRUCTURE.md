# Rabbit Hunter 项目逻辑结构总览

> 版本：v0.5.x · 最后更新：2026-06-08
> 这是一份项目逻辑骨架文档,用于快速理解整套系统的模块边界、数据流向和关键设计。

---

## 一、项目定位

**Rabbit Hunter** 是一套面向币安 / OKX 永续合约的**量化交易系统**,核心闭环:

> 市场扫描 → 深度采集 → 四维评分 → 策略路由(SNIPER/VULTURE) → AI 二次审查(GPT-4o) → 下单执行 → 持仓监控 → 平仓学习

支持三种运行模式:
- **LIVE 实盘** —— 真实下单
- **SHADOW 影子(纸面交易)** —— 信号同实盘,只下"假单",用真实行情验证策略
- **TESTNET 测试网** —— 币安/OKX 测试环境

设计哲学:**Fail-closed 安全姿态**(AI 失败 = 拒绝交易,而非冒险放行)。

---

## 二、技术栈

| 层 | 技术 |
|----|------|
| 交易执行 | Python 3.11 + CCXT 4.4 + Binance / OKX Futures API |
| 数据库 | SQLite(本地, 单文件) |
| 采集 & 评分 | asyncio + Pandas + NumPy |
| AI 决策 | OpenAI Assistants API (GPT-4o) + Vector Store(RAG 记忆) |
| API 服务 | FastAPI 0.115 + Uvicorn + WebSocket + Bearer Token 鉴权 |
| 前端 | React 19 + Vite 6 + TypeScript + TailwindCSS + React Query 5 + Zustand |
| 容器 | Docker + docker-compose(api / collector / frontend 三服务) |

---

## 三、目录骨架

```
Rabbit-Hunter/
├── api/                          # FastAPI 后端
│   ├── main.py                   # 入口:启动 FastAPI + WebSocket + 安全检查
│   ├── dependencies.py           # 依赖注入(DB、鉴权)
│   ├── websocket_server.py       # WebSocket(kill-queue 实时推送)
│   ├── routes/                   # 路由分层
│   │   ├── positions.py          # 持仓查询/平仓/同步检查
│   │   ├── scores.py             # 评分数据/AI 决策结果
│   │   ├── weights.py            # 策略权重管理
│   │   ├── market.py             # 市场数据/交易所状态
│   │   └── system.py             # 系统状态/余额/OpenAI 初始化
│   ├── services/                 # 业务逻辑层
│   └── schemas/                  # Pydantic 数据模型
│
├── scripts/                      # 核心采集 / 评分 / 交易逻辑
│   ├── config.py                 # TradingConfig 单例(环境变量集中读取)
│   ├── local_db.py               # SQLite 初始化、ORM、自动清理
│   ├── exchange_factory.py       # 交易所工厂(Binance / OKX 切换)
│   ├── binance_trader.py         # Binance 下单执行器
│   ├── okx_trader.py             # OKX 下单执行器
│   ├── binance_position_sync.py  # 持仓同步、blip 防护(三道防线)
│   │
│   ├── tasks/                    # 异步采集管道(主入口)
│   │   ├── collector_main.py     # 启动 4 个异步任务 + AI 初始化
│   │   ├── scanner.py            # MarketScanner:扫异动币种
│   │   ├── deep_collector.py     # DeepCollector:采 OI/资金费/CVD/K 线
│   │   ├── scorer.py             # StrategyScorer:特征→评分→路由→AI
│   │   └── writer.py             # DatabaseWriter:异步写 SQLite + WS 广播
│   │
│   ├── ai/                       # AI 决策层
│   │   ├── trading_assistant.py  # GPT-4o 核心决策引擎
│   │   ├── guardrails.py         # 硬规则限幅(SL/TP/size 区间)
│   │   ├── memory_uploader.py    # 交易日志 → Vector Store
│   │   ├── prompt.py             # System Prompt
│   │   └── setup_assistant.py    # 初始化 Assistant + Vector Store
│   │
│   ├── core/
│   │   └── risk_calculator.py    # ATR / 仓位 / 止损计算
│   │
│   ├── v43_score_calculator.py   # 四维评分(结构/波动/情绪/操控)
│   ├── v43_position_manager.py   # 持仓状态机 + Chandelier Exit
│   ├── v44_strategy_router.py    # 策略路由(SNIPER/VULTURE/SNIFFER)
│   ├── v41_structure_analyzer.py # 结构特征识别(P2/P3A/P3B/P4)
│   ├── backtest_paper_trades.py  # 回测框架
│   └── [40+ 工具脚本]            # 诊断/调参/监控
│
├── Rabbit Hunterfronted/         # React 前端 SPA
│   ├── App.tsx                   # 路由 + 全局布局
│   ├── components/               # 业务组件
│   │   ├── Layout.tsx            # 侧边栏 + 顶栏(状态指示灯)
│   │   ├── KillBoard.tsx         # 信号列表(实时推送)
│   │   ├── PositionsPage.tsx     # 持仓监控(SL/TP 进度条)
│   │   ├── OrderPage.tsx         # 订单历史
│   │   ├── Dashboard.tsx         # 账户统计
│   │   ├── AIStatus.tsx          # AI 状态 + Vector Store 统计
│   │   ├── TradeScores.tsx       # 评分明细
│   │   ├── StrategyConfig.tsx    # 策略参数编辑
│   │   ├── WeightHistory.tsx     # 权重时间线
│   │   ├── TradingViewChart.tsx  # K 线图(Lightweight Charts)
│   │   └── AnatomyPanel.tsx      # 币种深度分析
│   ├── hooks/                    # React Query 查询 Hook
│   ├── services/                 # API 调用 + WebSocket + Zustand store
│   └── ui/                       # 原子组件(Badge/ScoreBar/PnlDisplay)
│
├── data/                         # 运行时数据(.gitignore)
│   ├── rabbit_hunter.db          # SQLite 主库
│   └── ai_trade_log.jsonl        # AI 学习日志(JSONL)
│
├── docker-compose.yml            # 3 服务编排
├── Dockerfile                    # 后端镜像
├── .env.example                  # 环境变量模板
├── requirements.txt              # Python 依赖
├── README.md                     # 项目说明
└── CHANGELOG.md                  # 版本日志
```

---

## 四、核心数据流

```
              [Binance / OKX Futures 行情]
                         │
                         ▼
              ┌─────────────────────────┐
              │  MarketScanner          │   每秒扫涨跌幅 Top N
              │  (tasks/scanner.py)     │
              └────────────┬────────────┘
                           │ movers_queue
                           ▼
              ┌─────────────────────────┐
              │  DeepCollector          │   采集 OI/资金费/CVD/K 线
              │  (tasks/deep_collector) │
              └────────────┬────────────┘
                           │ enriched_queue(完整特征集)
                           ▼
              ┌─────────────────────────┐    ┌──────────────────┐
              │  StrategyScorer         │    │  AI 决策层        │
              │  V4.3 四维评分          │───▶│  GPT-4o 二次审查 │
              │  V4.4 策略路由          │◀───│  + Vector Store  │
              │  (tasks/scorer.py)      │    │  (RAG 历史案例)  │
              └────────────┬────────────┘    └──────────────────┘
                           │ write_queue
                           ▼
              ┌─────────────────────────┐
              │  DatabaseWriter         │   异步写 SQLite + 广播
              │  (tasks/writer.py)      │
              └────┬───────────────┬────┘
                   │               │
        ┌──────────┘               └────────────┐
        ▼                                       ▼
   [SQLite 表]                          [WebSocket 广播]
   trade_scores_v43                            │
   positions_v43                               ▼
   orders_history                      [前端 KillBoard 实时刷新]
   ai_training_data                            │
        │                                      ▼
        │                            [用户点击 → 下单]
        ▼                                      │
   [PositionManager] ◀────────────────────────┘
        │                  下单 / 平仓 / 止盈止损
        ▼
   [BinanceTrader / OkxTrader]
        │
        ▼
   [BinancePositionSync 三道防线]
   异常分类 + bulk-blip 检测 + N 次缺失保护
        │
        ▼
   平仓 → 写 ai_trade_log.jsonl → 上传 Vector Store → AI 下次学习
```

---

## 五、后端模块详解

### 5.1 异步采集管道(scripts/tasks/)

四个独立的 asyncio 任务,通过 `asyncio.Queue` 串联,独立扩缩、互不阻塞。

| 任务 | 职责 | 输入 → 输出 |
|------|------|-------------|
| **MarketScanner** | 每秒扫描全市场,挑出涨跌幅 Top N 异动币种 | 行情 → `movers_queue` |
| **DeepCollector** | 对异动币种深度采集 OI / 资金费率 / CVD / K 线 OHLCV | `movers_queue` → `enriched_queue` |
| **StrategyScorer** | 四维评分 + V4.4 路由 + 调用 AI 二次审查 | `enriched_queue` → `write_queue` |
| **DatabaseWriter** | 异步批量写 SQLite + 触发 WebSocket 广播 | `write_queue` → DB + WS |

入口:`python -m scripts.tasks.collector_main`

### 5.2 评分系统(V4.3)

`scripts/v43_score_calculator.py` —— 四维加权:

| 维度 | 权重 | 含义 |
|------|------|------|
| 结构分 | 40% | P2/P3A/P3B/P4 阶段识别(`v41_structure_analyzer.py`) |
| 波动分 | 20% | ATR、波动率、价格分布 |
| 情绪分 | 20% | 成交量、持仓量、资金费率 |
| 操控分 | 20% | 庄家活动强度、大额单 |

### 5.3 策略路由(V4.4)

`scripts/v44_strategy_router.py` —— 根据评分 + 市场结构选择策略:

| 策略 | 阶段 | 方向 | SL × ATR | TP × ATR | 状态 |
|------|------|------|----------|----------|------|
| **SNIPER 狙击手** | P3A 主升 | LONG 做多 | 2.0 | 3.0 | 默认开启 |
| **VULTURE 秃鹫** | P3B/P4 出货 | SHORT 做空 | 1.5 | 2.5 | v0.5.0 默认禁用(数学修复中) |
| **SNIFFER 潜伏者** | P2 吸筹 | LONG | 自定义 | 自定义 | opt-in |

### 5.4 AI 决策层(scripts/ai/)

`TradingAssistant` 接收规则引擎信号 → GPT-4o 二次审查 → 可拒绝 / 调整 SL/TP / 调整仓位。

**Guardrails 硬约束**(无论 AI 怎么调,都不能越界):
- SL: **1.2 – 3.0 × ATR**
- TP: **2.0 – 6.0 × ATR**,且 RR ≥ 1.5 : 1
- 仓位: **0.3 – 1.2 ×** 基准倍数

**学习闭环:**
平仓 → 自动写 `data/ai_trade_log.jsonl` → 手动或定时 `python -m scripts.ai.memory_uploader --upload` → 推送 Vector Store → 下次决策自动 RAG 检索相似历史案例。

### 5.5 交易执行

| 模块 | 文件 | 关键能力 |
|------|------|----------|
| 交易所工厂 | `exchange_factory.py` | 按 `EXCHANGE=binance/okx` 切换 |
| 下单执行 | `binance_trader.py` / `okx_trader.py` | CCXT 封装、precision、clientOrderId、reduceOnly、`_safe_create_order` 幂等重试 |
| 持仓管理 | `v43_position_manager.py` | OPEN→CLOSING→CLOSED 状态机、Chandelier Exit 动态止损 |
| 持仓同步 | `binance_position_sync.py` | 每分钟与 Broker 对账,三道防线防 API blip 误平仓 |

### 5.6 API 服务(api/)

入口 `api/main.py`,启动时做安全检查(默认绑定 `127.0.0.1`,强制 Bearer Token)。

| 路由 | 路径前缀 | 用途 |
|------|----------|------|
| `routes/positions.py` | `/api/v43/positions` | 持仓列表 / 平仓 / 同步检查 |
| `routes/scores.py` | `/api/v43/scores` | 评分快照 / AI 决策详情 |
| `routes/weights.py` | `/api/v43/weights` | 策略权重 |
| `routes/market.py` | `/api/v43/market` | 市场数据 |
| `routes/system.py` | `/api/v43/system` | 系统状态 / 余额 / OpenAI 初始化 |
| `websocket_server.py` | `/ws/v43` | 实时推送 kill-queue / 仓位变化 |

---

## 六、前端模块详解

### 6.1 页面与组件

| 组件 | 作用 |
|------|------|
| `Layout.tsx` | 折叠侧边栏 + 顶栏,采集器/API/WebSocket 状态指示灯,SNIPER/VULTURE 徽章,LIVE/SHADOW 模式切换 |
| `KillBoard.tsx` | 信号列表(React Query 轮询 + WebSocket 实时补推),展开卡显示评分 + AI 决策 + 风险 |
| `PositionsPage.tsx` | OPEN 仓位监控,SL/TP 进度条,一键平仓 |
| `OrderPage.tsx` | CLOSED 订单历史,已实现盈亏,触发原因 |
| `Dashboard.tsx` | 账户余额、可用余额、总盈亏、胜率 |
| `AIStatus.tsx` | OpenAI Assistant 状态、Vector Store 记忆统计、一键上传记忆 |
| `TradeScores.tsx` | 四维评分明细表 |
| `StrategyConfig.tsx` | SNIPER/VULTURE 参数动态编辑 |
| `WeightHistory.tsx` | 权重变化时间线 |
| `TradingViewChart.tsx` | Lightweight Charts K 线图 |
| `AnatomyPanel.tsx` | 单币种深度分析(结构/特征/历史) |
| `SettingsPage.tsx` | 交易所 + AI 配置(DB 持久化) |

### 6.2 数据流

```
React Query Hook ── apiGet/apiPost ──▶ apiInterceptor ──▶ FastAPI
   (useKillQueue)        (services/api.ts)   (注入 Bearer Token)
        │
        ▼
   组件渲染 + Zustand UI 状态(store.ts)
        ▲
        │
   WebSocket(services/websocket.ts)
        │
   ws://api/ws/v43?token=...  ◀── Collector 广播
```

### 6.3 状态管理分层

- **React Query** —— 服务端状态(kill-queue、positions、scores)
- **Zustand** —— UI 本地状态(侧边栏折叠、模式切换、当前选中币种)
- **WebSocket** —— 实时事件推送(替代某些场景的轮询)

---

## 七、数据库(SQLite)

文件:`data/rabbit_hunter.db`,关键表:

| 表 | 内容 | 保留策略 |
|----|------|----------|
| `trade_scores_v43` | 最新评分快照(append-only) | 滚动清理 |
| `positions_v43` | 持仓状态(OPEN/CLOSING/CLOSED) | OPEN 永久 / CLOSED 90 天 |
| `orders_history` | 订单历史 | 滚动清理 |
| `ai_training_data` | AI 历史决策(与 Vector Store 同步) | 永久 |
| `market_snapshot` | 市场快照 | 7 天 |
| `ai_weights_v43` | 权重历史 | 90 天 |

---

## 八、配置与部署

### 8.1 环境变量(.env)分组

**交易所:**
```bash
EXCHANGE=okx                 # 或 binance
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BINANCE_TESTNET=true
BINANCE_LEVERAGE=10
ENABLE_AUTO_TRADING=true     # false = 只看不下
ENABLE_SHORT_TRADING=false   # VULTURE 开关,默认关
```

**AI:**
```bash
OPENAI_API_KEY=sk-...
OPENAI_AI_ENABLED=true
OPENAI_ASSISTANT_ID=asst_xxx
OPENAI_VECTOR_STORE_ID=vs_xxx
```

**安全:**
```bash
API_BEARER_TOKEN=$(openssl rand -hex 32)
API_BIND_HOST=127.0.0.1
API_ENABLE_DOCS=false
```

**风控:**
```bash
V43_ENABLED=true
V43_RISK_PER_TRADE=0.015     # 单笔 1.5% 账户风险
AI_FAIL_OPEN=false           # AI 不可用 = 拒绝交易
SL_TP_FAIL_OPEN=false        # 止损失败 = 立即回滚
```

### 8.2 Docker 启动

```bash
cp .env.example .env
# 编辑 .env 后:
docker compose up -d
# 前端: http://localhost:5173
# API : http://localhost:8000
```

### 8.3 首次初始化 OpenAI

```bash
python scripts/ai/setup_assistant.py
# 打印 OPENAI_ASSISTANT_ID、OPENAI_VECTOR_STORE_ID,填回 .env
```

### 8.4 上传历史记忆

```bash
python -m scripts.ai.memory_uploader --upload
# 把 data/ai_trade_log.jsonl 推送到 Vector Store
```

---

## 九、运行模式对比

| 模式 | 信号 | 下单 | 用途 |
|------|------|------|------|
| **LIVE 实盘** | 真实 | 真实 Broker 下单 | 生产 |
| **SHADOW 影子** | 真实 | 内存模拟,记录 paper_trades | 验证策略 / 评估 AI 决策 KPI |
| **TESTNET 测试网** | 真实 | Binance/OKX 测试网下单 | 集成验证 |

**SHADOW 模式**(v0.4 引入,v0.4.x 修复为真实纸面交易循环):
- 与实盘共用同一套信号 + AI 决策
- 不调用 Broker,直接写 `paper_trades` 表
- 前端 Dashboard 展示 paper KPI(纸面胜率、PnL),作为上线前的"温度计"

---

## 十、安全姿态(Fail-Closed)

v0.5.0 的核心定位 —— **不确定 = 拒绝交易**:

| 失败场景 | 默认行为 |
|----------|----------|
| AI 调用超时 / 异常 | 跳过该信号(不放行) |
| SL / TP 下单失败 | **立即市价平仓**回滚主仓 |
| Broker 仓位同步异常 | 三道防线(异常分类 + bulk-blip + N 次缺失保护) |
| API 绑定非本机且无 Token | **拒绝启动** |

---

## 十一、核心设计理念

1. **异步管道** —— 四任务通过队列解耦,高吞吐低延迟
2. **本地优先** —— SQLite 单文件,零网络延迟,支持离线分析
3. **规则 + AI 双层** —— 规则提供可解释下限,AI 提供学习上限,Guardrails 兜底
4. **学习闭环** —— 交易结果自动记忆,Vector Store RAG 复用历史经验
5. **Fail-closed** —— 任何不确定都拒绝交易,而非冒险放行
6. **三服务 Docker 化** —— api / collector / frontend 独立扩缩,共享 data volume

---

## 十二、关键脚本工具索引(scripts/)

| 分类 | 脚本 | 用途 |
|------|------|------|
| **诊断** | `diagnose_collector.py` / `diagnose_data_flow.py` | 检查采集管道 / 数据流 |
| **回测** | `backtest_paper_trades.py` / `report_paper_trades.py` | 历史回测 / 交易统计 |
| **监控** | `position_monitor.py` / `binance_positions.py` | 实时仓位同步 |
| **调参** | `ai_auto_tuner.py` / `ai_config_manager.py` | AI 参数自动优化 |
| **清理** | `clear_open_positions.py` | 一键平仓所有仓位 |
| **测试** | `test_binance_api.py` | API 连接测试 |

---

**文档定位:** 这份文档是项目的"逻辑地图"。要看实现细节请直接读源码;要看版本演进请读 `CHANGELOG.md`;要看快速上手请读 `README.md`。

---

## [待整合 · Task 7 会重写] 从 docs/project-structure.md 合并的段落

> 以下段落来自已删除的 `docs/project-structure.md`，由 Task 6 原样搬入。Task 7 会统一重写并合并进正文。
> 来源行范围: §5.1 (254-273), §7 (319-332), §8.3 (366-382), §9 (386-414), §10 (419-432), §11 (438-450), §12 (454-467)

### 5.1 视觉系统 — "Field Instrument" tokens

定义在 `tailwind.config.js`,镜像在 `services/tokens.ts`。

| 用途 | Token class | Hex | 语义 |
|---|---|---|---|
| 背景主 | `bg-bg-base` | #0F1115 | 暖深黑 |
| 卡片 | `bg-bg-surface` | #171A20 | 上浮一档 |
| 深底 | `bg-bg-deep` | #0A0C0F | 输入框 |
| 文本 | `text-ivory` / `-70` / `-40` / `-25` | #F1ECDD | 象牙白 + 4 档透明度 |
| 强调 | `text-brass` / `bg-brass-soft` | #C9A14B | 黄铜金 — primary / active |
| LONG / 正盈 | `text-sage` / `bg-sage-soft` | #6B8568 | 鼠灰绿 |
| SHORT / 负盈 | `text-oxblood` / `bg-oxblood-soft` | #A53E32 | 暗红 |
| Info | `text-ink` / `bg-ink-soft` | #5A7691 | 灰蓝 |
| 描边 | `border-hairline` / `-strong` | rgba(241,236,221,.10/.18) | 发丝细线 |
| 字间 | `tracking-wider2/3/4` | .18/.22/.26em | eyebrow letter-spacing |
| 字体 | `font-mono` | Fira Code | tabular-nums |

🎯 **优化此处不要碰 token 名 — 它们已扩散到 50+ 文件**。改 token 值(hex)反而 OK,全局生效。

---

## 7. 风控宪法 7 条 — 改这里影响动钱代码

定义在 `scripts/risk_constitution.py`,在 `scripts/risk_gates.py` 实现 gate,在 `scripts/tasks/scorer.py` 串接执行。

| 规则 | 常量 / 函数 | 执行点 | API 暴露 |
|---|---|---|---|
| 1 单笔风险 ≤ 1% | `MAX_PER_TRADE_RISK_PCT` + `resolve_risk_pct_for_equity()` | `scorer._risk_per_trade()` + `gate_per_trade_risk()` | `trader-kpi.constitution.rule_1_*` |
| 2 进场必挂 SL + 失败回滚 | `SL_MANDATORY_AT_ENTRY` + `gate_sl_attached()` | `v5_position_manager.open_position` | `rule_2_*` |
| 3 日内 -3% 锁仓 | `DAILY_DRAWDOWN_LIMIT_PCT = 0.03` + `gate_daily_drawdown()` | `scorer:252` | `rule_3_*` |
| 4 杠杆 3-5x + 反推 | `MIN_LIQ_TO_SL_DISTANCE_RATIO = 2.0` + `derive_safe_leverage()` + `gate_liquidation_distance()` | `v5_risk_calculator` + `scorer:333` | `rule_4_*` |
| 5 SL ratio ∈ [1.5, 2.2] + 仓位 [0.6, 1.1] | `FINAL_SL_ATR_RATIO_MIN/MAX` + `EVOLUTION_SIZE_MULT_MIN/MAX` + `gate_final_sl_ratio()` + `clamp_evolution_*()` | `scorer:317,326` | `rule_5_*` |
| 6 SHORT 默认关 | `config.enable_short_trading = False` + scorer 内联 gate | `scorer:235` (我加的) | `rule_6_*` |
| 7 杀手 setup 禁用 | `DEFAULT_DISABLED_SETUPS` frozenset + `gate_setup_enabled()` | `scorer:244` | `rule_7_*` |

🎯 **关键文件**: `docs/risk-constitution-audit.md` 有完整的"宪法 vs 代码"核对清单 + 修复历史。

---

### 8.3 热配置 (system_settings, 前端可改)

```
v5_strategy_mode                  trend_aligned / and_strict / macd_reversal_long
v5_use_symbol_whitelist           true / false
v5_sl_atr_mult / v5_tp_atr_mult   SL/TP ATR 倍数
v5_rsi_overbought / v5_rsi_oversold
v5_trend_rsi_long/short_threshold
v5_funding_anti_pile_threshold
v5_max_concurrent                 同时活仓数上限 (默认 3)
v5_leverage                       杠杆 cap (默认 5, derive_safe_leverage 会再压)
v5_risk_per_trade                 单笔风险 (默认 0.01)
v5_anti_chase_pct / window_bars
v5_symbol_whitelist               逗号分隔字符串覆盖默认 22
deepseek_api_key                  AI key (前端 Settings 填)
okx_api_key / secret / passphrase OKX 凭证 (前端 Settings 填)
```

---

## 9. 测试 (`tests/`, 53 个文件)

```
test_v5_strategy*.py          ★ 决策器 3 mode 边界
test_safety_defaults.py       ★ 风控默认值 + leverage 反推
test_risk_gates.py            ★ 7 个 gate_* 函数
test_v5_scoring_pipeline.py   ★ scorer 端到端
test_v5_risk_calculator.py    plan() 公式
test_walkforward.py           M6 引擎
test_m9_*.py                  M9 知识层
test_paper_position_manager_v5.py
test_v5_position_*.py
test_v5_funding_*.py
test_v5_indicator_engine.py
test_v5_symbol_whitelist.py
test_trading_assistant_*.py
test_deepseek_adapter.py      ⚠️ 3 失败 (158c90f 引入,本会话未触)
test_failure_taxonomy_*.py
test_reflection_*.py
test_ai_v5_adapter.py / test_kelly_sizing.py / test_confidence_calibration.py
test_setup_*.py
test_local_db_v5.py / test_funding_db.py
test_v5_*_api.py              FastAPI 路由 (10+ 文件)
test_websocket_v5.py
test_collector_preflight.py
test_chandelier.py / test_local_rag.py
```

跑全套: `python3 -m pytest tests/ -q`
现状: **425 passed / 3 known-broken (test_deepseek_adapter)**.

---

## 10. 关键扩展点速查表 (✨ "我想做 X — 改哪")

| 想做的事 | 改哪个文件 | 新加文件 |
|---|---|---|
| 加一个新页面 (前端) | `App.tsx` 加 Route | `components/pages-v4/XxxPage.tsx` |
| 加一个新 API endpoint | `api/main.py` import + include | `api/routes/v5_xxx.py` |
| 加一个新前端 hook | — | `Rabbit Hunterfronted/hooks/api/useV5Xxx.ts` |
| 加一个新风控闸门 | `scorer.py` 串接 + 测试 | `risk_gates.py` 加 `gate_xxx()` |
| 加新策略 mode | `v5_strategy.py:decide()` 加分支 + 测试 | 新 `_decide_xxx()` |
| 加新 setup_type | `scripts/ai/setup_type.py:derive_setup_type()` | — |
| 加新指标 (TA) | `v5_indicator_engine.py` 加纯函数 | — |
| 加新 backtest 实验 | — | `scripts/experiments/xxx.py` (复用 cost_model + position_sim) |
| 加新 setting 项 | `v5_params.py:_ENV_MAP/DEFAULTS/PARAM_META` + 前端 SettingsPage | — |
| 改宪法常量 | `scripts/risk_constitution.py` + 跑全测试 | — |
| 加新视觉 token | `tailwind.config.js:colors` + `services/tokens.ts` (mirror) | — |
| 加新 db 表 | `scripts/local_db.py` 加 CREATE + migration | — |

---

## 11. Legacy / 半死 / 跳过区 (改的时候避开)

| 路径 | 状态 | 说明 |
|---|---|---|
| `scripts/collector.py` | 归档 | 旧入口,直接运行打 deprecation 退出。用 `scripts/tasks/collector_main` |
| `scripts/core/risk_calculator.py` | V4 老版 | V5 用 `scripts/v5_risk_calculator.py`,核心计算在那 |
| `scripts/diagnose_*.py / check_*.py` | 一次性诊断 | 不在运行时,不要跑 |
| `Rabbit Hunterfronted/components/pages/V5*` 里 8 个 | legacy | App.tsx 未引用,`/v5/*` 已 redirect 到 pages-v4。改了不生效 |
| `Rabbit Hunterfronted/components/primitives/` | legacy V2 | 当前用 primitives-v3 |
| `api/websocket_server.py` | V4 ws | 不主推,主用 websocket_v5 |
| `scripts/binance_*.py` (除 trader) | 备用 | 主用 OKX。binance 路径需 `EXCHANGE=binance` 才激活 |
| `Rabbit Hunterfronted/ui/` | 空 | 历史目录 |
| `data/rabbit_hunter.db.backup-pre-v5.*` / `*.malformed-*` | 备份 | 不要动 |
| 8 个 `weights_router / system_router / market_router` 注册被 `# TODO(v5)` 注释 | V4.3 残留 | 注释里写 "rewire to SQLite/V5" |

---

## 12. Docker compose 拓扑

```yaml
services:
  api:        FastAPI on 127.0.0.1:8000
  collector:  python -m scripts.tasks.collector_main (no HTTP port)
  frontend:   nginx 静态前端 on 127.0.0.1:5173 (反代 /api → api:8000)

挂卷:
  ./data    → /app/data     (SQLite + JSONL + backtest cache)
  ./reports → /app/reports  (walk-forward 输出)
```

启动: `docker compose up -d`

---
