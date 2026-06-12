# V5 前端重写 + AI 学习闭环 — 设计稿(Plan B)

- **状态:** 已对齐(待用户最终 review)
- **作者:** lizhishaoniange + Claude
- **日期:** 2026-06-12
- **依赖:** `docs/superpowers/specs/2026-06-12-v5-rsi-macd-15min-rebuild-design.md` 的 §7,以及已落地的 V5 后端(`/api/v5/*` 在 commit `9aa764f` 起)
- **目标:** 把前端 100% 重写到 V5 视觉 + V5 API,新增"图表分析"专业页 + "手动模拟开单工作流" + "DeepSeek 本地 RAG-lite 学习闭环",让 SHADOW 跑出 paper trades 时用户能在新 UI 上看到完整 Pipeline(信号 → AI → 活仓 → 平仓 → 学习)。

---

## §1 总览

### 1.1 一句话定位

> **专业交易终端 + AI 持续进化 + 完整可观测性**:V5 视觉、V5 API、V5 状态管理,10 个新页面(含图表分析专业大屏),DeepSeek 本地 RAG 让 AI 看着历史相似 case 做决策。

### 1.2 已对齐决策清单

| # | 维度 | 决策 |
|---|---|---|
| 1 | 重写范围 | **全部 18 组件 + 7 hooks + 7 services 重写**(连工具类一起) |
| 2 | WebSocket 范围 | 只推重要事件(开/平/续/AI 健康/告警);信号面板靠 React Query 10s 轮询 |
| 3 | 策略参数持久化 | **DB 写 + collector 5s cache 热读**,不重启 |
| 4 | 测试覆盖 | **Vitest 单测 ~25 + RTL 集成 ~10**,后端补 ~20 测试 |
| 5 | 实施路径 | **Foundation-first**:先共享层(API hooks/store/WS/tokens),再批量做页面 |
| 6 | K 线图形态 | **独立 ChartPage 专业大屏**(/v5/chart/:symbol)+ 在卡片里"📈 查看图表"跳转 |
| 7 | AI 学习载体(DeepSeek 没 Vector Store) | **本地 RAG-lite**:SQLite ai_training_data top-K 加权欧氏距离 + Prompt 注入 |
| 8 | 手动开单形态 | **三步工作流**:选 → AI 评估展示(含 RAG case) → 确认开 |

### 1.3 风险声明(总体)

- 一次性全重写 18 组件 + 7 hooks + 7 services + 删旧建新,**不可回滚**:一旦合就要往前修
- Plan A V4.3→V5 已经走过同模式;Plan B 同样心态
- Wall-clock 10-11 天(纯净工时 12 天),用户可以同步跑 SHADOW 观察后端行为

---

## §2 目录结构 + 删除清单

### 2.1 新目录(替换整个 `Rabbit Hunterfronted/`)

```
Rabbit Hunterfronted/
├── App.tsx                      # 路由根,/v5/* 全新,根路径 → /v5/signals
├── index.tsx
├── index.css
├── types.ts                     # V5 API 响应类型,从 api/schemas/*.py 对齐
│
├── components/
│   ├── pages/                   # 10 个新页面(路由级)
│   │   ├── V5SignalsPage.tsx
│   │   ├── V5ActivePositionsPage.tsx
│   │   ├── V5OrderHistoryPage.tsx
│   │   ├── V5DashboardPage.tsx
│   │   ├── V5AIStatusPage.tsx
│   │   ├── V5SignalHistoryPage.tsx
│   │   ├── V5StrategyConfigPage.tsx
│   │   ├── V5SettingsPage.tsx
│   │   ├── V5ManualOrderPage.tsx    # 三步工作流
│   │   └── V5ChartPage.tsx          # ★ 图表分析专业大屏
│   ├── shared/
│   │   ├── IndicatorGauges.tsx
│   │   ├── ActivePositionCard.tsx
│   │   ├── SignalFunnel.tsx
│   │   ├── KpiCard.tsx
│   │   ├── RecentAIDecisions.tsx
│   │   └── IndicatorOverlayChart.tsx   # ★ K 线主图 + RSI/MACD 副图 + 标注层
│   ├── layout/
│   │   ├── AppShell.tsx
│   │   ├── Sidebar.tsx
│   │   └── TopBar.tsx
│   └── primitives/
│       ├── Card.tsx · Badge.tsx · ProgressBar.tsx · GaugeArc.tsx
│       ├── ErrorBoundary.tsx · Toast.tsx · LoadingSkeleton.tsx
│       ├── Modal.tsx · Select.tsx · Slider.tsx · NumberInput.tsx
│       └── VirtualList.tsx
│
├── hooks/
│   ├── api/                     # 每 endpoint 一文件
│   │   ├── useV5Signals.ts
│   │   ├── useV5ActivePositions.ts
│   │   ├── useV5OrderHistory.ts
│   │   ├── useV5Dashboard.ts
│   │   ├── useV5AIStatus.ts
│   │   ├── useV5StrategyConfig.ts        # GET + PATCH
│   │   ├── useV5Settings.ts              # GET + PATCH
│   │   ├── useV5ManualOrder.ts           # preview + execute 两 mutation
│   │   ├── useV5Klines.ts                # ChartPage K 线
│   │   └── useV5SymbolEvents.ts          # ChartPage 标注事件
│   ├── useV5WebSocket.ts        # 连接管理 + 重连 + 事件分发
│   └── useSystemMode.ts         # SHADOW/LIVE 镜像
│
├── services/
│   ├── api.ts                   # fetch 封装 + Bearer 注入
│   ├── apiInterceptor.ts
│   ├── store.ts                 # Zustand:仅 UI 状态
│   └── tokens.ts                # 设计 tokens 真相源
│
└── tests/
    ├── hooks/
    ├── shared/
    └── pages/
```

### 2.2 删除清单(整个 `Rabbit Hunterfronted/` 旧内容)

| 旧文件 | 处置 |
|---|---|
| `KillBoard.tsx` / `TradeScores.tsx` / `PositionsPage.tsx` / `Dashboard.tsx` / `AIStatus.tsx` / `StrategyConfig.tsx` / `WeightHistory.tsx` / `AnatomyPanel.tsx` / `Charts.tsx` | 删,V5 重写 |
| `Layout.tsx` / `SettingsPage.tsx` / `OrderPage.tsx` / `FeatureFlagsPanel.tsx` | 删,V5 重写 |
| `ErrorBoundary.tsx` / `Toast.tsx` / `VirtualList.tsx` | 删,迁到 `primitives/` 重写 |
| `TradingViewChart.tsx` | 删,V5 用 `IndicatorOverlayChart.tsx` 取代 |
| `hooks/useKillQueue.ts` / `useWeights.ts` / `usePaperTrades.ts` / `useExchange.ts` / `usePositions.ts` / `useSystemStatus.ts` | 删,V5 重写 |
| `services/store.ts` / `api.ts` / `apiInterceptor.ts` / `featureFlags.ts` / `geminiService.ts` / `tradingViewChart.ts` / `websocket.ts` | 删,V5 重写 |

---

## §3 共享层契约

### 3.1 API hooks 表(10 个)

| Hook | Endpoint | Query Key | Refetch |
|---|---|---|---|
| `useV5Signals(limit, filter)` | `GET /api/v5/signals?limit=50&...` | `['v5','signals',filter]` | 10s |
| `useV5ActivePositions()` | `GET /api/v5/positions?status=OPEN` + `GET /api/v5/paper-positions?status=OPEN` | `['v5','active']` | 5s |
| `useV5OrderHistory(limit)` | `GET /api/v5/positions?status=CLOSED` + paper-positions | `['v5','history',limit]` | 30s |
| `useV5Dashboard()` | 复用 signals 漏斗 + paper-positions closed | `['v5','dashboard']` | 30s |
| `useV5AIStatus()` | `GET /api/v5/ai/status` | `['v5','ai']` | 60s |
| `useV5StrategyConfig()` | `GET /api/v5/strategy-config` + `PATCH` | `['v5','config']` | 不轮询,手动 invalidate |
| `useV5Settings()` | `GET /api/v5/settings` + `PATCH` | `['v5','settings']` | 不轮询 |
| `useV5ManualOrder()` | `POST /api/v5/manual-order/preview` + `POST /execute` | — | mutation |
| `useV5Klines(symbol, interval, limit)` | `GET /api/v5/klines/{symbol}` | `['v5','klines',symbol,interval]` | 15s |
| `useV5SymbolEvents(symbol, limit)` | `GET /api/v5/events/{symbol}` | `['v5','events',symbol]` | 15s |

### 3.2 Zustand store(`services/store.ts`)

只存**纯客户端 UI 状态**,服务端数据完全归 React Query:

```ts
type UIState = {
  sidebarCollapsed: boolean;
  expandedSignalIds: Set<number>;
  selectedSymbolForChart: string | null;
  recentWsEvents: WsEvent[];              // toast 队列
  systemMode: 'SHADOW' | 'LIVE' | null;
  effectiveAiProvider: 'deepseek' | 'openai' | null;
  themePreference: 'auto' | 'dark';
  klineInterval: '15m' | '1h' | '4h';

  toggleSidebar: () => void;
  toggleSignalExpanded: (id: number) => void;
  pushWsEvent: (ev: WsEvent) => void;
  popWsEvent: () => void;
  setSystemMode: (m: 'SHADOW' | 'LIVE') => void;
};
```

### 3.3 WebSocket 客户端(`hooks/useV5WebSocket.ts`)

```
连接:       wss://host/ws/v5?token=<Bearer>
心跳:       客户端每 30s 发 {type:"ping"};15s 没收 pong → 断开重连
重连:       Exponential backoff 1s → 2s → 4s → 8s → 16s → 30s 上限
看门狗:     lastReceivedAt > 30s → 强制断开重连
事件分发:   收 → store.pushWsEvent → queryClient.invalidateQueries → Toast(重要事件)
降级:       3 次重连失败 → wsHealthy=false,React Query polling 频率加倍
```

5 个事件:`position_opened` / `position_closed` / `position_extended` / `ai_health` / `scoring_stalled`(详细 schema 见 §6.2)。

### 3.4 设计 tokens(`services/tokens.ts`)

```ts
export const tokens = {
  color: {
    bg: { base: '#0F1419', surface: '#1A2030', surfaceHover: '#222B3D', border: 'rgba(255,255,255,0.08)' },
    text: { primary: '#FFFFFF', secondary: 'rgba(255,255,255,0.72)', muted: 'rgba(255,255,255,0.48)' },
    accent: {
      long: '#10B981', short: '#EF4444', warn: '#F59E0B',
      info: '#3B82F6', primary: '#F97316',
    },
    risk: { block: '#EF4444', watch: '#F59E0B', trade: '#10B981' },
  },
  font: {
    mono: '"JetBrains Mono", "IBM Plex Mono", monospace',
    sans: '"PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif',
  },
  space: { 1: 4, 2: 8, 3: 12, 4: 16, 6: 24, 8: 32, 12: 48 },
  radius: { sm: 4, md: 8, lg: 12, full: 9999 },
  motion: {
    fast: '120ms cubic-bezier(0.4, 0, 0.2, 1)',
    base: '200ms cubic-bezier(0.4, 0, 0.2, 1)',
    slow: '400ms cubic-bezier(0.4, 0, 0.2, 1)',
  },
};
```

Tailwind 配置从 tokens 自动注入。

### 3.5 路由结构(`App.tsx`)

```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

<Routes>
  <Route path="/" element={<Navigate to="/v5/signals" replace />} />
  <Route path="/v5" element={<AppShell />}>
    <Route index               element={<Navigate to="signals" replace />} />
    <Route path="signals"      element={<V5SignalsPage />} />
    <Route path="active"       element={<V5ActivePositionsPage />} />
    <Route path="orders"       element={<V5OrderHistoryPage />} />
    <Route path="dashboard"    element={<V5DashboardPage />} />
    <Route path="ai"           element={<V5AIStatusPage />} />
    <Route path="history"      element={<V5SignalHistoryPage />} />
    <Route path="config"       element={<V5StrategyConfigPage />} />
    <Route path="settings"     element={<V5SettingsPage />} />
    <Route path="manual"       element={<V5ManualOrderPage />} />
    <Route path="chart/:symbol" element={<V5ChartPage />} />
  </Route>
  {/* 旧路径 301 → V5 */}
  <Route path="/signals"   element={<Navigate to="/v5/signals"   replace />} />
  <Route path="/positions" element={<Navigate to="/v5/active"    replace />} />
  <Route path="/dashboard" element={<Navigate to="/v5/dashboard" replace />} />
  <Route path="*"          element={<Navigate to="/v5/signals"   replace />} />
</Routes>
```

**新依赖:** `react-router-dom@7`(原项目里没有)。

---

## §4 十个页面组件设计

每页统一模板:**路由 · 数据源 · 主区块 · 关键交互 · 错误/空态**。

### 4.1 V5SignalsPage 实时信号

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 实时信号                              过去 1h: 47 个扫到 → 8 通过 AND → 2 入场│
│ 筛选: [全部 ▾]   方向: [全部 ▾]   仅显示已入场 [○]              [手动刷新⟳]│
├─────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │ H/USDT          ΔP15m: +3.42%        09:48:21  ●●●  [▾]                 ││
│ │ ┌──RSI 15min──┐  ┌──MACD 15min──┐    🎯 SHORT  📊 score 78              ││
│ │ │     72.1    │  │  hist:-0.0012 │   AI 已批准 ✓                        ││
│ │ │ ██████████░ │  │  prev:+0.0008 │   sl 2.0x  tp 2.8x                   ││
│ │ │  超买 ⚠️    │  │  死叉拐点 ✓   │   size 14.8 USDT                     ││
│ │ └─────────────┘  └───────────────┘                                       ││
│ │ 4h 参考: rsi=68 macd_hist=+0.003(上扬)  → AI: "短线反弹中带空有利"      ││
│ │ [📈 查看图表]                                       [📝 此参数模拟开单]   ││
│ └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

- **路由:** `/v5/signals`
- **数据源:** `useV5Signals(50, filter)` 10s 轮询
- **每卡:** Symbol + ΔP15m + 时间 + 三色 dot (●●●/●●○/●○○) + 评分 + 风险标签 + 展开
- **展开卡:** `IndicatorGauges` + 4h 参考 + AI reasoning + "📈 查看图表" + "📝 此参数模拟开单"
- **空态:** "等待行情出现 RSI/MACD 合谋信号..."

### 4.2 V5ActivePositionsPage 活仓监控

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 活仓监控          2 / 3                                  下一次轮询 18s 后 ⟳ │
├─────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │  H/USDT  SHORT  -10x          软目标剩 04:23      [立即平] [📈 图表]    ││
│ │      入场             当前             SL         TP                    ││
│ │     $0.1665         $0.1641         $0.1715    $0.1592                  ││
│ │  ●═══════════●═══════════════════════>○         ○                       ││
│ │   PnL: +0.42% (+0.62 USDT)  当前 RSI: 67 ✓还在超买区                    ││
│ │   持仓 10:37  续仓 0/3                                                  ││
│ │  最近 AI 决策: "信号方向继续,maintain"  09:38:11                         ││
│ └─────────────────────────────────────────────────────────────────────────┘│
│ ┌─────────────────────────────────────────────────────────────────────────┐│
│ │  [+] 空闲槽位 (最多 3)                                                  ││
│ └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

- **路由:** `/v5/active`
- **数据源:** `useV5ActivePositions()` 5s 轮询 + WS 触发 invalidate
- **关键交互:** "立即平" → confirm modal → `POST /api/v5/positions/:id/close`

### 4.3 V5OrderHistoryPage 订单历史

- **路由:** `/v5/orders`
- **数据源:** `useV5OrderHistory(200)` 30s 轮询
- **表格列:** 时间 / Symbol / Side / Entry→Exit / 平仓原因 / PnL$ / PnL% / 持仓分钟
- **每行末:** "📈 图表" → `/v5/chart/:symbol?eventId=...` 自动定位

### 4.4 V5DashboardPage Dashboard

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Dashboard          24h 总览                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                            │
│ │  胜率   │ │累计 PnL │ │ 平均持仓│ │  活仓数 │                            │
│ │  63%    │ │ +18.40  │ │  17 min │ │   2/3   │                            │
│ │ ▴ +5pt  │ │  USDT   │ │ ─ 持平  │ │ 全部 ●● │                            │
│ │ vs 昨天 │ │ +1.84%  │ │         │ │         │                            │
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘                            │
│                                                                              │
│ ─── 24h 信号漏斗 ───(点任一层 → /v5/history?block_reason=...)              │
│ Scanner 扫到      ████████████████████████████████████████████  872          │
│ 15min ΔP>3%        █████████████████░░░░░░░░░░░░░░░░░░░░░░░░  213           │
│ RSI×MACD AND        ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   34           │
│ AI 批准              █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   12           │
│ 实际开仓             █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   11           │
│                                                                              │
│ ─── 24h PnL 曲线 ───(Recharts)─── 拦截分布 ─── 平仓原因分布 ───           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.5 V5AIStatusPage AI 状态

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ AI 状态                                                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │   Provider       │  │  RAG 利用率      │  │   决策延迟       │          │
│  │   DeepSeek       │  │   78%            │  │   平均 7.8s      │          │
│  │   deepseek-chat  │  │  (24h)           │  │   P95: 14.2s     │          │
│  │   ● 在线          │  │  本地 142 case   │  │                  │          │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
│                                                                              │
│ ── 最近 20 笔 AI 决策 ──                                                     │
│ ┌──────┬───────────┬──────┬───────────┬────────────────────────────────┐  │
│ │ 时间 │ 币种      │ 决定 │ Top-1相似 │ 推理摘要                       │  │
│ ├──────┼───────────┼──────┼───────────┼────────────────────────────────┤  │
│ │09:48 │ H/USDT    │ ✓ 批准│ d=0.08    │ RAG: 4/5 历史盈,继续做空      │  │
│ │09:47 │ BEAT/USDT │ ✗ 拒 │ d=0.12    │ RAG: 类似 case 3/5 输,跳过    │  │
│ │ ...  │           │      │           │                                │  │
│ └──────┴───────────┴──────┴───────────┴────────────────────────────────┘  │
│                                                                              │
│ ── 续仓决策(过去 24h) ──                                                   │
│ 总续仓请求 18    续(让 AI 决定继续) 11    平(15min 到点平) 7              │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **路由:** `/v5/ai`
- **数据源:** `useV5AIStatus()` 60s 轮询
- **新增 KPI:** RAG 利用率 = 过去 24h 决策中 query 命中 ≥1 历史 case 的比例

### 4.6 V5SignalHistoryPage 信号历史

- **路由:** `/v5/history`
- **数据源:** `useV5Signals(200, filter)` 30s 轮询
- **高级过滤:** 时间窗 / Symbol / 拦截原因 / AI 决策结果
- **URL query 同步:** 例如 `?block_reason=NOT_RSI_AND_MACD&since=2026-06-13`

### 4.7 V5StrategyConfigPage 策略配置

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 策略配置                                              [恢复默认] [保存修改] │
├─────────────────────────────────────────────────────────────────────────────┤
│ ── 选币层 ──                                                                 │
│ 最低 24h 成交额(USDT)         [30,000,000]                                  │
│ 最低 15min |ΔP|                [3.0 %]        ▭▭▭▭●▭▭▭▭▭ (1% — 5%)         │
│                                                                              │
│ ── RSI 触发器 ──                                                             │
│ RSI 周期                       [14]                                          │
│ 超买阈值(开空)                [70.0]      ▭▭▭▭▭▭▭●▭▭ (60 — 80)           │
│ 超卖阈值(开多)                [30.0]      ▭●▭▭▭▭▭▭▭▭ (20 — 40)           │
│                                                                              │
│ ── MACD 触发器 ──                                                            │
│ MACD 快/慢/信号                 [12]  [26]  [9]                              │
│                                                                              │
│ ── 风险参数 ──                                                               │
│ SL × ATR                        [1.5]                                        │
│ TP × ATR                        [2.5]                                        │
│ 单笔风险预算                    [1.5 %]                                       │
│ 同时活仓上限                    [3]                                          │
│                                                                              │
│ ── 软目标 ──                                                                 │
│ 持仓软目标(分钟)              [15]                                          │
│ AI 续仓上限                     [3]                                          │
│                                                                              │
│ ── 模拟预览(基于过去 7 天数据)──                                            │
│ 当前阈值预计每小时入场: 0.8 笔                                              │
│ 预计胜率: 58%                    [   预览新阈值的回测结果   ]               │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **关键交互:** 修改 → dirty state → 保存触发 `PATCH /api/v5/strategy-config` → React Query invalidate
- **后端补:** `GET /api/v5/strategy-config/preview`

### 4.8 V5SettingsPage 系统设置

- **路由:** `/v5/settings`
- **主区块:** 交易所配置(Binance/OKX) + AI 配置(provider 选择) + 系统模式(SHADOW/LIVE 切换) + Fail-closed 旋钮
- **安全:** SHADOW → LIVE 切换需二次确认 modal,显示当前持仓 + 余额

### 4.9 V5ManualOrderPage 三步工作流 ★

**Step 1 · 选标的**
```
Symbol [H/USDT ▾]    Side [SHORT ▾]   Size [15 USDT]
(或从信号面板带过来,自动填好)        [模拟评估 →]
```

**Step 2 · AI 评估**
```
┌─────────────────────────────────────────────────────────────────┐
│  当前指标          规则决策             AI 二次审查              │
│  RSI 72.1 ⚠️     ✓ SHORT             ✓ execute=true            │
│  MACD 死叉拐点    "RSI 超买 + 死叉..." sl=1.8x tp=2.6x conf=0.7  │
│  4h: rsi=68      建议 SL=$0.169       AI 推理:                   │
│  ATR 0.0015      建议 TP=$0.162       "4h 仍偏多但 15min 转折   │
│                                       明确,RAG 类似 case 3/5 盈" │
│                                                                  │
│  ── RAG 检索 top-5 ────                                         │
│  case1  rsi=73.2 hist=-0.0006 → WIN +0.4% TP_HIT                │
│  case2  rsi=71.5 hist=-0.0004 → LOSS -0.3% SL_HIT               │
│  case3  rsi=72.8 hist=-0.0008 → WIN +0.6% TP_HIT                │
│  case4  rsi=70.9 hist=-0.0005 → WIN +0.3% AI_TIMEBOX            │
│  case5  rsi=73.7 hist=-0.0007 → LOSS -0.4% SL_HIT               │
│  历史胜率 3/5 = 60%,平均 PnL +0.12%                            │
│                                                                  │
│  [↩ 回到 Step 1]                          [确认模拟开仓 →]     │
└─────────────────────────────────────────────────────────────────┘
```

**Step 3 · 已开仓 → 跳 /v5/active**

- 模拟单 `strategy_id='v5_manual'`,其他完全跟自动信号一样进入监控、命中 SL/TP 平仓、平仓后写 `ai_training_data` 供 RAG 学习
- **限制:** 仅 SHADOW 模式可见,LIVE 模式入口隐藏

### 4.10 V5ChartPage 图表分析 ★ 核心

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ H/USDT                       15m │ 1h │ 4h     [⟳]       现价 $0.1641     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [Lightweight Charts 主图,200 根 K 线,左侧 0.155–0.175 价格轴]              │
│                                                                              │
│      ╱╲      ●═══════ TP 0.162                                              │
│     ╱  ╲    ╱─                                                              │
│  ──╯    ╲──╯                                                                │
│              ▼ SHORT 入场 $0.1665  09:48  ← RSI 72.1, MACD 死叉拐点         │
│              ●─────────────────────● 当前 $0.1641                           │
│  ────────────────────────────────────────── SL 0.169                         │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  RSI 15min                                          MACD 15min               │
│  ─── 70                                              hist  ▂▃▅▇█▇▅▃▁         │
│      ╱╲╱╲ 72.1                                       signal ──────           │
│  ─── 30                                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **路由:** `/v5/chart/:symbol?eventId=<optional>`
- **数据源:** `useV5Klines(symbol, interval, 200)` 15s + `useV5SymbolEvents(symbol, 50)` 15s
- **主图:** Lightweight Charts K 线
- **副图:** Lightweight Charts 第二个 chartApi(RSI + MACD)— 跟主图共享 timeScale
- **标注层:**
  - ▼ 红 = SHORT 入场,▲ 绿 = LONG 入场,hover tooltip 显示 RSI/MACD/AI reasoning
  - TP/SL 水平虚线,平仓后 ● 在交叉点(标 TP_HIT / SL_HIT / AI_TIMEBOX)
  - 当前价格水平线 + 闪烁
- **关键交互:**
  - `?eventId=` query param → 自动定位 + 高亮
  - interval 切换 → URL 同步 + 重新拉 K 线

### 4.11 共用 shared 组件契约

| 组件 | Props | 用途 |
|---|---|---|
| `IndicatorGauges` | `{ rsi_15m, rsi_4h, macd_hist_15m, macd_hist_prev_15m, atr_15m }` | RSI 表盘 + MACD 柱 |
| `ActivePositionCard` | `{ position, onClose, onChart }` | 顶摘要、进度条、PnL、续仓徽章 |
| `SignalFunnel` | `{ steps: [{name, count, rejected_breakdown?}], onLayerClick }` | Dashboard 漏斗 |
| `KpiCard` | `{ title, value, unit?, deltaVsYesterday?, sparkLine? }` | 通用 KPI |
| `RecentAIDecisions` | `{ decisions: AIDecision[], limit }` | AIStatusPage 表格 |
| `IndicatorOverlayChart` | `{ klines, indicators, events, interval, onIntervalChange }` | ChartPage 大图 |

### 4.12 AppShell(Layout)

- 折叠侧边栏(分组:**交易**(信号/活仓/订单/图表/手动) / **智能**(AI 状态/历史/策略配置) / **系统**(Dashboard/设置))
- 顶栏:Logo + 版本 + Exchange chip + Mode chip(SHADOW/LIVE)+ WS 心跳 ● + Bell(Toast 队列) + 设置 ⚙

---

## §5 AI 学习闭环(后端 RAG-lite)

### 5.1 架构

```
平仓事件               trading_assistant.decide
   │                            │
   ▼                            ▼ ① 查相似历史
v5_position_monitor       local_rag.find_similar_cases(
     ↓                         indicators, side, top_k=5)
write ai_training_data         ↓
   ↓ (outcome, pnl,         返回 top-5 cases
   ↓  reasoning, rsi,
   ↓  macd_hist, rsi_4h,    ② 拼装到 user_msg:
   ↓  delta_15m_pct,          "过去 5 个类似 setup:
   ↓  exit_reason)            case1 RSI=73 hist=-0.0006 → PnL +0.4% TP_HIT
                              case2 RSI=71 hist=-0.0004 → PnL -0.3% SL_HIT
                              ..."

                          ③ DeepSeek chat completion 看着这 5 个案例做决策
```

### 5.2 `scripts/ai/local_rag.py`(新文件)

```python
def find_similar_cases(
    indicators: Indicators,
    side: str,
    top_k: int = 5,
    db_path: str = "data/rabbit_hunter.db",
) -> list[SimilarCase]:
    """查 ai_training_data 中已平仓且同 side 的样本,按加权欧氏距离排序。

    距离公式:
      d = sqrt(
        ((rsi_15m - entry_rsi_15m) / 100) ** 2 +
        ((macd_hist_15m - entry_macd_hist_15m) * 1000) ** 2 +
        ((rsi_4h - entry_rsi_4h) / 100) ** 2 * 0.5 +
        ((delta_15m_pct - source.delta_15m_pct) * 10) ** 2 * 0.3
      )

    返回 top-K(可能少于 K):
      [SimilarCase(entry_rsi_15m, entry_macd_hist_15m, outcome, pnl_pct, exit_reason, distance), ...]

    冷启动:数据 < 10 行 → 返回 []
    """
```

### 5.3 集成

`trading_assistant._decide_via_chat` 在拼 `user_msg` 之前调一次,把 `rag_cases` 格式化注入 system prompt 末尾:

```
Historical similar cases (top 5 by indicator distance):
  case1  entry_rsi=73.2 hist=-0.0006 outcome=WIN pnl=+0.4% exit=TP_HIT
  case2  entry_rsi=71.5 hist=-0.0004 outcome=LOSS pnl=-0.3% exit=SL_HIT
  ...
Use these as base-rate hints. Don't override your own analysis blindly.
```

### 5.4 前端可见性(V5AIStatusPage 加 KPI)

- **RAG 利用率** = "过去 24h 决策中 query 命中 ≥1 历史 case 的比例"
- 决策表加列 **Top-1 距离** 显示最近 case 的距离值

---

## §6 后端联动详细契约

### 6.1 新增 API 路由(12 个)

| 方法 | 路径 | 用途 | 来自 |
|---|---|---|---|
| `GET` | `/api/v5/klines/{symbol}` | ChartPage 主图 K 线(query: `interval` `limit`) | §4.10 |
| `GET` | `/api/v5/events/{symbol}` | 该 symbol 的入场/平仓事件列表(标注层) | §4.10 |
| `GET` | `/api/v5/strategy-config` | 8 个旋钮当前值 + 默认值 + 范围 | §4.7 |
| `PATCH` | `/api/v5/strategy-config` | 写 `system_settings` + invalidate cache | §4.7 |
| `GET` | `/api/v5/strategy-config/preview` | 回测预览 | §4.7 |
| `GET` | `/api/v5/settings` | broker/AI 配置(脱敏 key 显示 `sk-***xxxx`) | §4.8 |
| `PATCH` | `/api/v5/settings` | 修改 + 危险操作记日志 | §4.8 |
| `GET` | `/api/v5/ai/status` | provider/chat_model/RAG 利用率/最近 24h 决策数 | §4.5 |
| `GET` | `/api/v5/ai/decisions` | 最近 N 笔 AI 决策(`ai_training_data` JOIN) | §4.5 |
| `POST` | `/api/v5/manual-order/preview` | 模拟评估,返回 `{indicators, decision, ai_result, rag_cases}` | §4.9 |
| `POST` | `/api/v5/manual-order/execute` | 真正写 `paper_trades`(`strategy_id='v5_manual'`) | §4.9 |
| `POST` | `/api/v5/positions/{id}/close` | 立即平仓(SHADOW 直接平,LIVE 调 broker) | §4.2 |

响应统一 Pydantic 模型,所有时间字段过 `ensure_utc_iso`。

### 6.2 WebSocket(`/ws/v5`)

```
握手:  WSS upgrade,query ?token=<Bearer>(可选,API_BEARER_TOKEN 配置时强制)
心跳:  服务器每 30s 发 {type:"ping"};客户端不响应 60s → 服务器主动 close
广播:  集成在 V5PositionMonitor + V5Scorer 的关键事件

事件 schema:
  position_opened    {symbol, side, entry, sl, tp, size_usdt, position_id, strategy_id, mode}
  position_closed    {position_id, symbol, exit_price, exit_reason, pnl_usdt, pnl_pct, holding_minutes}
  position_extended  {position_id, symbol, new_target_close_at, extension_count}
  ai_health          {provider, chat_model, last_latency_ms, healthy: bool}
  scoring_stalled    {seconds_since_last_score, last_symbol_seen}

广播频率上限:  每事件类 10/秒,超出走 drop
保存到 DB:    不(WS 是瞬时通道)
```

**实现位置:** `api/websocket_v5.py`(新文件,替代当前 stub 的 `websocket_server.py`)

### 6.3 策略参数热读(`scripts/v5_params.py` 新)

```python
class V5Params:
    """5s 缓存的参数读取层。

    用法:
      from scripts.v5_params import get_param
      threshold = get_param("v5_delta_15m_threshold", default=0.03, cast=float)

    优先级:env > system_settings DB > 代码 default
    (env 设了就锁死;DB 没设走 default)
    """
    _cache: dict = {}
    _cache_ts: float = 0.0
    _ttl = 5.0
```

**改造范围:** `v5_strategy.py` / `v5_risk_calculator.py` / `v5_position_monitor.py` / `tasks/deep_collector.py` / `tasks/scorer.py` 全部把 `os.environ.get` 替换为 `get_param`。

**新增 system_settings key:** `v5_rsi_overbought` / `v5_rsi_oversold` / `v5_macd_fast/slow/signal` / `v5_sl_atr_mult` / `v5_tp_atr_mult` / `v5_delta_15m_threshold` / `v5_min_expected_move_pct` / `v5_max_concurrent` / `v5_max_extensions` / `v5_rsi_reverse_short/long` / `v5_risk_per_trade` / `v5_leverage` / `v5_soft_target_minutes`

### 6.4 手动开单逻辑

`/api/v5/manual-order/preview` 内部:

```python
klines_15m = fetch_klines(symbol, "15m", 50)
klines_4h = fetch_klines(symbol, "4h", 50)
indicators = calculate_indicators(klines_15m, klines_4h)
enriched = EnrichedItem(...)
decision = decide(enriched, indicators)
risk = plan(side=decision.side or req.side, ...)
ai_result = await trading_assistant.decide(enriched, indicators, decision, risk)
rag_cases = local_rag.find_similar_cases(indicators, decision.side or req.side)
return ManualOrderPreviewResponse(indicators, decision, risk, ai_result, rag_cases)
```

`/api/v5/manual-order/execute`:同样流程 + `paper_pm.open_position(...)` + 触发 WS `position_opened`。

### 6.5 后端工时

| 模块 | 工时 |
|---|---|
| 12 个新路由 + Pydantic 模型 | 1.5 天 |
| WebSocket `websocket_v5.py` + broadcast 集成 | 0.5 天 |
| `v5_params.py` 热读层 + 6 模块改造 | 0.5 天 |
| `local_rag.py` + 接 trading_assistant | 0.5 天 |
| 单元 + 集成测试(~20 新增) | 0.5 天 |
| **后端合计** | **3.5 天** |

---

## §7 错误处理 + 测试策略

### 7.1 前端错误矩阵

| 失败点 | 默认行为 | 兜底显示 |
|---|---|---|
| API 4xx | React Query `isError`,组件显示重试按钮 | "数据获取失败:[详情]" |
| API 5xx | 自动重试 1 次 + 退避 2s | 同上 + Toast |
| API 超时(15s) | 显示 stale 数据(灰显) + 顶栏告警 dot | "数据可能过期" |
| WS 断开 1 次 | exponential backoff 重连 | 顶栏 ● 转黄 |
| WS 断开 3 次 | wsHealthy=false + 加倍 React Query polling | 顶栏 ● 转红 + Toast |
| 组件渲染异常 | `ErrorBoundary` 隔离到该页面 | "本页加载失败" |
| K 线为空 | 显示 Skeleton 直至有数据 | "等待 K 线数据..." |
| RAG 命中 0 case | 决策卡显示 "RAG 冷启动,无历史样本" | 不报错 |
| AI 决策超时 20s | 沿用 V5 backend fail-closed | 普通 block_reason 卡 |
| Manual preview 失败 | Step 2 显示错误,不能进 Step 3 | "评估失败:[exception]" |
| 401/403(token 无效) | 跳 `/v5/settings` + Toast | "Token 失效,请重新配置" |

### 7.2 前端测试

#### 单元(Vitest,~25)

```
hooks/         useV5Signals · useV5ActivePositions · useV5WebSocket
services/      store · tokens
shared/        IndicatorGauges · ActivePositionCard · IndicatorOverlayChart
utils/         formatTime · formatPnl
```

#### 集成(RTL,~10)

```
pages/    V5SignalsPage · V5ActivePositionsPage · V5DashboardPage
          V5StrategyConfigPage · V5ManualOrderPage(三步流)
```

测试用 MSW 拦截 fetch,WS 用 `mock-socket`。

#### 端到端(可选,Playwright 1 个)

> SHADOW 启动 → 5min 后真实信号 → 浏览器自动:/v5/signals → /v5/manual → 模拟开 → /v5/active 看到 → PnL 变化

P1 优先级,可放 SHADOW 验收后做。

### 7.3 后端测试(~20)

```
tests/  test_v5_klines_api · test_v5_strategy_config_api · test_v5_manual_order_api
        test_v5_params_hot_reload · test_local_rag · test_websocket_v5
```

目标:Plan A 77 + Plan B 后端 ~20 + Plan B 前端 ~35 = 130+ 全绿才进 SHADOW 验收。

---

## §8 部署 / 回滚 / 验收

### 8.1 部署步骤

```
1. v5-frontend 分支(本次用户选 main 直推,不分支)
2. 后端 PR 子任务先合(12 路由 + WS + v5_params + local_rag + 测试)
3. 前端 PR 整体覆盖式合(删旧 + 新建)
4. docker compose down && docker compose build --no-cache && docker compose up -d
5. 浏览器访问 http://localhost:5173/v5/signals 看到新 UI
6. 24h SHADOW 跑(同 Plan A 验收)
7. 跑扩展验收脚本(§8.3)
```

### 8.2 回滚

**软回滚不可行:** `git revert <merge>` 后系统进入 "V5 + V4.3 混合 broken" 状态。

**实际操作:** Plan B 一旦上,只能向前修。心态同 Plan A V4.3→V5。

**硬回滚:** 回 commit `9aa764f` + 手动重建 DB(因为可能有 manual-order 写过 paper_trades)。

### 8.3 验收(扩展 `verify_v5_acceptance.py`)

新增检查:

```
✓ 后端测试 130+ 全绿(Plan A 77 + Plan B 后端 20 + 前端 35)
✓ 前端 build 成功(vite build)
✓ 前端单元 25 + RTL 10 全绿
✓ 24h:trade_scores_v5 ≥ 50
✓ 24h:paper_trades ≥ 1
✓ 浏览器 /v5/signals 看到信号(或空态)
✓ 浏览器 /v5/active 看到 0~3 槽位结构
✓ 浏览器 /v5/chart/H/USDT 看到 K 线 + 副图 + 标注
✓ /v5/manual 完成一次模拟开单(手动验证)
✓ AI 决策日志里有 RAG cases 注入(grep "Historical similar cases" docker logs)
✓ RAG 利用率 KPI 显示数字(冷启动 0% → 累积后涨)
```

### 8.4 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|----|----|----|
| Lightweight Charts + 副图同步联动不稳 | 中 | ChartPage 体验差 | 共享 timeRange via Zustand;副图用 Lightweight Charts 第二 chartApi 而非 Recharts |
| WS 触发频繁导致 React Query thrashing | 中 | 性能 | 加 invalidate 节流 1s + 同事件去重 |
| 策略参数热读未生效(cache 未失效) | 中 | UI 显示一致但实际跑旧值 | PATCH 后强制 `_cache_ts = 0` |
| RAG 冷启动期 AI 决策飘忽 | 高 | 短期 KPI 不稳 | UI 标注"RAG 冷启动期",验收只看技术指标 |
| 手动开单污染 ai_training_data | 中 | RAG 检索取出非真实信号 | `strategy_id='v5_manual'` 区分;RAG 可选过滤 |
| 后端 schema 跟前端 hook 不一致 | 中 | 运行 4xx | `test_v5_api_schema.py` 跑 OpenAPI 校验 |

### 8.5 工时全表

| 阶段 | 子项 | 工时 |
|---|---|---|
| **后端**(§6.5) | 12 路由 + WS + params 热读 + RAG-lite + 测试 | **3.5 天** |
| **前端 Foundation** | App.tsx + tokens + Tailwind + primitives + AppShell + WS hook + Zustand | **2 天** |
| **前端 API hooks** | 10 个 hook + 类型从后端同步 | **1 天** |
| **前端 Shared 组件** | IndicatorGauges/ActivePositionCard/SignalFunnel/KpiCard/RecentAIDecisions/**IndicatorOverlayChart** | **1.5 天** |
| **前端 Pages** | 9 页平均 0.3 天 + **ChartPage 单独 1 天** + ManualOrderPage 0.5 天 | **2.5 + 1 天** |
| **测试** | Vitest 25 + RTL 10 | **1 天** |
| **联调 + UI 抛光** | docker 起,真实跑通 + Toast 排版 + 移动最小适配 | **0.5 天** |
| **合计** | | **12 天 纯净工时** |

并行度:后端 PR 先合,前端依赖,wall-clock 约 **10-11 天**。

---

## §9 终态:进入实现阶段

设计稿全部确认后,下一步:

1. 调用 `superpowers:writing-plans` skill 把这份 design 拆成可执行的实现计划
2. plan 拆分按 §8.5 的 12 天工作量分阶段(后端先 / 前端 Foundation / 前端 Pages / 测试 / 联调)
3. 每个阶段独立可验证(单元 + 集成测试通过 + 本地跑通)

---

**[End of design document]**
