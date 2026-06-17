# Rabbit Hunter V6 — UI Design Brief for AI Generation

> **Purpose of this document:** A self-contained brief you can paste into any UI generation AI (v0.dev / Lovable / Bolt / Cursor / Claude / etc.) to generate visual designs that match the existing app's tech stack, data shapes, and aesthetic direction. The receiving AI has zero project context — everything it needs is here.

---

## 1. Project Background (one paragraph)

Rabbit Hunter is a **self-hosted crypto futures trading bot driver's seat** — a real-time control panel for an automated trading system that runs in SHADOW (paper) or LIVE mode. The single user is the operator: they watch incoming market signals, oversee AI-driven decisions, review post-trade reflections, approve position-sizing recommendations, and tune strategy parameters. **It is a serious quant tool, not a consumer trading app.** Dark theme always. Information density is high. The user spends hours staring at it; cognitive ergonomics matter.

---

## 2. Design Direction

### 2.1 Aesthetic — "Quant Terminal / Cyber Cockpit"

The current implementation establishes the visual language. Stay within it; refine, don't reinvent.

**Mood references:**
- Bloomberg terminal (information density, mono-spaced numeric tables)
- Cyberpunk 2077 menus (cyan/violet neon, ▓░ ASCII bars, ▌ ▶ glyphs)
- Sci-fi HUDs (holographic gradient borders, animated pulse on healthy states)
- High-end DAW or pro-audio plugins (precise, calm under busy state)

**What to avoid:**
- Skeuomorphic "trading app" tropes (no fake glass, no candle 3D)
- Gamified UI (no XP bars, no rewards, no confetti)
- Cute icons (no rounded mascots; lucide-react line icons only)
- Consumer-app rounded edges everywhere (use radius=sm/md/lg purposefully)
- Light theme (none, ever)
- Emoji-heavy headers (one symbol per element max)

### 2.2 Voice

- Terminal-style affordances: `▌` `▶` `★` `░░░▓` are deliberate and welcomed
- Chinese (zh-CN) primary copy with monospace English/numeric values
- Microcopy is direct: "等待行情" not "Watching the market for you" — no marketing fluff
- Data labels stay concise: `R+1.20` `z=+2.4` `n=30` — assume the user understands jargon (and we have tooltips for those who don't)

---

## 3. Design Tokens

These are authoritative — read them as the source of truth for any color/spacing decision.

```ts
export const tokens = {
  color: {
    bg: {
      base:        '#0F1419',      // page background
      surface:     '#1A2030',      // card background
      surfaceHover:'#222B3D',
      border:      'rgba(255,255,255,0.08)',
    },
    text: {
      primary:   '#FFFFFF',
      secondary: 'rgba(255,255,255,0.72)',
      muted:     'rgba(255,255,255,0.48)',
    },
    accent: {
      long:    '#10B981',  // green — LONG positions, wins, healthy
      short:   '#EF4444',  // red — SHORT positions, losses, danger
      warn:    '#F59E0B',  // amber — caution, anti-chase, mild drift
      info:    '#3B82F6',  // blue — neutral info, primary CTA
      primary: '#F97316',  // orange — brand accent (rare)
      // cyber palette (used on AI-style HoloCards)
      cyan:    '#22D3EE',
      violet:  '#A78BFA',
    },
    risk: {
      block: '#EF4444',
      watch: '#F59E0B',
      trade: '#10B981',
    },
  },
  font: {
    mono: '"JetBrains Mono", "IBM Plex Mono", monospace',
    sans: '"PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif',
  },
  space:  { 1: 4, 2: 8, 3: 12, 4: 16, 6: 24, 8: 32, 12: 48 },  // px
  radius: { sm: 4, md: 8, lg: 12, full: 9999 },
  motion: {
    fast: '120ms cubic-bezier(0.4,0,0.2,1)',
    base: '200ms cubic-bezier(0.4,0,0.2,1)',
    slow: '400ms cubic-bezier(0.4,0,0.2,1)',
  },
};
```

**Typography rules:**
- All numbers (prices, percentages, z-scores, RSI, sample counts) → `font-mono` + `tabular-nums`
- All Chinese / mixed prose → `font-sans`
- Hero numbers on KPI cards: `text-2xl font-mono`
- Body data tables: `text-xs font-mono`
- Page section titles: `text-sm font-medium text-white/90`

**Tailwind class examples for tokens (already configured):**
- `bg-bg-base` `bg-bg-surface`
- `text-accent-long` `text-accent-short` `text-accent-warn` `text-accent-info`
- `border-white/10` (matches token border)
- `rounded-sm` `rounded-md` `rounded-lg`

### 3.1 Special Cyber Effects (used on AI-themed surfaces only)

```css
/* Already in index.css */
@keyframes neonPulse {
  0%, 100% { box-shadow: 0 0 8px rgba(34,211,238,0.4), inset 0 0 8px rgba(34,211,238,0.1); }
  50%      { box-shadow: 0 0 16px rgba(34,211,238,0.7), inset 0 0 16px rgba(34,211,238,0.2); }
}
.neon-pulse  { animation: neonPulse 2.4s ease-in-out infinite; }
.cyber-grid {
  background-image:
    linear-gradient(rgba(34,211,238,0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(34,211,238,0.04) 1px, transparent 1px);
  background-size: 32px 32px;
}
.cyan-glow   { text-shadow: 0 0 4px rgba(34,211,238,0.4); }
```

**Use `neon-pulse` / `cyber-grid` ONLY on:** AI Status page, Reflection page, certain prominent "live data" cards. **DO NOT** use on trading-critical pages (Positions, Orders) — there the calm grid is more important.

---

## 4. Layout System

### 4.1 AppShell (every page lives inside this)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ◀ Sidebar (collapsible)              │  TopBar  (sticky)               │
│                                       ├──────────────────────────────────┤
│  [Brand:猎兔者 V5]                    │                                  │
│                                       │       Outlet (page content)      │
│  ━ 交易                                │                                  │
│   • 实时信号    /v5/signals           │                                  │
│   • 活仓监控    /v5/active            │                                  │
│   • 订单历史    /v5/orders            │                                  │
│   • 手动开单    /v5/manual            │                                  │
│                                       │                                  │
│  ━ 智能                                │                                  │
│   • AI 状态     /v5/ai                │                                  │
│   • 信号历史    /v5/history           │                                  │
│   • 策略配置    /v5/config            │                                  │
│   • 复盘工作台  /v5/reflection        │                                  │
│                                       │                                  │
│  ━ 系统                                │                                  │
│   • Dashboard   /v5/dashboard         │                                  │
│   • 系统设置    /v5/settings          │                                  │
│   • 术语词典    /v5/glossary          │                                  │
│                                       │                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

**Sidebar:** width 208px expanded, 56px collapsed. Three groups with uppercase tracked headers (`text-[10px] uppercase tracking-wider text-white/40`). Active nav has `bg-accent-info/15 text-accent-info`.

**TopBar:** height 48px. Left: version chip + Mode badge (🟡 SHADOW or 🔴 LIVE) + AI provider chip. Right: WS connection status (Wi-Fi icon green/red) + Bell with queue count badge.

### 4.2 Page Content Container

Always: `<main class="flex-1 overflow-y-auto p-6">`. Inside, content is a vertical stack with `space-y-4`.

---

## 5. Shared Primitives

Already implemented — match these APIs when designing variants.

### 5.1 Card (most common container)

```tsx
<Card
  title="实时信号"
  actions={<button>⟳</button>}
>
  {children}
</Card>
```

Renders: 1px border, rounded-md, dark surface. Header has title left + actions right, divider below. Body has `p-4`.

### 5.2 HoloCard (cyber variant — AI Status, Reflection)

```tsx
<HoloCard glow={healthy}>
  ...
</HoloCard>
```

Wrap with gradient border `bg-gradient-to-r from-cyan-500/40 via-violet-500/30 to-cyan-500/40 p-px`. Inner is `rounded-md bg-bg-surface/95 backdrop-blur p-4`. When `glow={true}` add `neon-pulse` class.

### 5.3 Badge

```tsx
<Badge variant="long | short | warn | info | neutral">LONG</Badge>
```

Pill with subtle background tint + border + colored text. Mono font.

### 5.4 KpiCard

```tsx
<KpiCard
  title="胜率"
  value="63%"
  unit="(7d)"
  deltaVsYesterday={{ value: 5, positiveIsGood: true }}
/>
```

Title small/muted, value large mono, optional delta below with up/down arrow.

### 5.5 Modal

Centered, dark overlay, escape-to-close. Used for: confirm close position, confirm switch to LIVE mode, confirm sizing approval.

### 5.6 Tooltip + Term

Hover over jargon (`SL`, `TP`, `RSI`, `funding_z_score`) → tooltip with Chinese explanation + example. The `<Term k="SL">SL</Term>` pattern wraps any text. Implemented globally; designers don't need to reinvent.

### 5.7 ProgressBar / GaugeArc

Standard horizontal bar (with optional label + percentage). GaugeArc is a semi-circle gauge (for RSI display).

---

## 6. Pages — In Order of Importance

For each page below: route, purpose, data shape (TypeScript interface), layout, key interactions.

---

### 6.1 V5SignalsPage — `/v5/signals`

**Purpose:** Real-time stream of incoming RSI/MACD/funding signals being scored by the engine. The trader watches this like a radar.

**Data:**
```ts
interface V5Signal {
  id: number;
  symbol: string;            // 'BTCUSDT'
  created_at: string;        // ISO UTC
  delta_15m_pct: number;     // 0.0342 = +3.42%
  volume_24h_usdt: number;
  rsi_15m: number;
  rsi_4h: number | null;
  macd_15m: number;
  macd_signal_15m: number;
  macd_hist_15m: number;
  macd_hist_prev_15m: number;
  macd_hist_4h: number | null;
  atr_15m: number;
  current_price: number;
  should_trade: boolean;
  side: 'LONG' | 'SHORT' | null;
  reasoning: string;
  block_reason: string | null;
  ai_confidence: number | null;
  ai_sl_multiplier: number | null;
  ai_tp_multiplier: number | null;
  ai_size_multiplier: number | null;
  ai_reasoning: string | null;
  executed: boolean;
  position_id: number | null;
}
```

**Layout:**
- Top: filter bar (Side: 全部 / SHORT only / LONG only, "仅已入场" checkbox, refresh button) + summary line `过去窗口: 47 扫到 → 8 通过 AND → 2 入场`
- Below: scrollable list of expandable signal cards (polling every 10s)
- Each card collapsed: `[Symbol] [Side badge] ΔP15m: +3.42%  score 78  ●●●  09:48:21  ▾`
- Expanded: shows IndicatorGauges (RSI dial + MACD bars + 4h reference), block_reason (if any), ai_reasoning, two CTA buttons:`[📈 查看图表]` `[📝 此参数模拟开单]`
- Empty state: `等待行情出现 RSI/MACD 合谋信号...`

**Critical:** signal count + executed count is real-time gauge of system health. The user notices "0 executed in 24h" instantly.

---

### 6.2 V5ActivePositionsPage — `/v5/active`

**Purpose:** Live monitoring of open positions. The most critical "hot" page.

**Data:** `V5Position[]` (LIVE + paper merged)

```ts
interface V5Position {
  id: number;
  symbol: string;
  side: 'LONG' | 'SHORT';
  status: 'OPEN' | 'CLOSED';
  entry_price: number | null;
  entry_time: string | null;
  sl_price: number | null;
  tp_price: number | null;
  size_usdt: number | null;
  leverage: number | null;
  extension_count: number;
  pnl_usdt: number | null;
  pnl_pct: number | null;
  holding_minutes: number | null;
  strategy_id: string | null;
  // ...
}
```

**Layout:**
- Top: card title `活仓监控  2 / 3   每 5s 自动刷新` (count out of MAX_CONCURRENT)
- Below: vertical stack of ActivePositionCard, each showing:
  - Top row: Symbol + Side badge + ×Leverage + Strategy badge (手动/自动) + `[立即平] [📈 图表]` buttons
  - Middle row: 4-column grid `入场 / 当前 / SL / TP` with prices (SL red, TP green, current/entry white)
  - Bottom row: `PnL +1.44% (+0.22 USDT)` colored + `持仓 10min · 续仓 0/3`
  - If `ai_reason` present: muted gray italic line below
- Empty state placeholder: `[+] 空闲槽位 (最多 3)`
- `[立即平]` triggers confirm Modal showing entry/current/PnL with two buttons

**Critical visual:** if pnl > 0 → green tone on PnL row; if < 0 → red. Holding minutes counts up in real-time (refetchInterval 5s).

---

### 6.3 V5OrderHistoryPage — `/v5/orders`

**Purpose:** Past trades table — closed positions sorted by exit_time DESC.

**Data:** Same `V5Position[]` but `status='CLOSED'`.

**Layout:** Dense data table, 11 columns:

| 平仓时间 | 币种 | 方向 | 入场 | 出场 | 原因 | PnL$ | PnL% | 持仓min | 策略 | [📈 图表] |
|---|---|---|---|---|---|---|---|---|---|---|

- Table row hover: `bg-white/[0.02]`
- PnL cells colored green/red
- Exit reason has its own variant chips: TP_HIT (long), SL_HIT (short), SOFT_TARGET (warn), SIGNAL_REVERSE (warn), MANUAL_USER (info)
- Last column: small `[📈]` button → `/v5/chart/:symbol?eventId=:id`

---

### 6.4 V5DashboardPage — `/v5/dashboard`

**Purpose:** Operator's home page — 24h overview at a glance.

**Layout:**
1. **4 KPI tiles** in `grid grid-cols-4 gap-3`:
   - 胜率 (with deltaVsYesterday)
   - 累计 PnL (USDT)
   - 平均持仓 (min)
   - 活仓数 (2/3)
2. **24h 信号漏斗** card (clickable layers):
   ```
   Scanner 扫到      ████████████████  872
   通过 AND          ████████          213
   实际开仓          █                 11
   ```
   Each layer is a button → navigates to `/v5/history?block_reason=...`
3. **24h 胜率总览** card (richer breakdown):
   - Left column: rows for `LONG / SHORT / 自动 / 手动 / [exit reasons]` with WinRateRow (label + horizontal bar + W/L count + per-bucket PnL)
   - Right column: 总样本 / Profit Factor / 最佳单 / 最差单 / 最大连胜连败
4. **24h PnL 曲线** (Recharts LineChart)
5. **拦截原因分布** (vertical text list, sorted desc by count)
6. **24h Setup Type 分项 (含 funding 维度)** — table with 4 columns: setup_type / n / 胜率 / avg R. **Rows starting with `funding_extreme_` get violet background tint + `★` marker** to make the new alpha dimension visible.

---

### 6.5 V5AIStatusPage — `/v5/ai` (cyber-styled)

**Purpose:** Show what the AI brain is currently doing.

**Layout (this page IS allowed to be flashy):**

Container has `cyber-grid -m-6 p-6 min-h-full` so the grid background bleeds to edges.

1. **3 HoloCards in `grid grid-cols-3`:**
   - **Provider** (with `neon-pulse` when healthy): shows `▶ DEEPSEEK-CHAT`, model name, online dot
   - **RAG Memory**: utilization % big number + `▌ N cases indexed` + thin gradient progress bar
   - **Decisions (24h)**: count + small confidence Sparkline

2. **Optional alert banner** (when last `ai_health` WS event present): `▌ Last AI health beacon: provider=deepseek healthy=true latency=Xms` in cyan

3. **Decision Stream** HoloCard:
   - Header: `▌ DECISION STREAM — last N events` + animated pulsing Radio icon + `▌ tail -f /var/log/v5/ai/decisions`
   - Table: 12-col grid (time, symbol, decision, confidence, top1_distance, RAG count, reasoning)
   - Row left-border tinted by execute=true/false (green/red)
   - Each row appears with `ticker-row` slide-in animation when new

4. **CONFIDENCE CALIBRATION CURVE** HoloCard:
   - Table showing model × confidence_bucket: predicted → actual → drift Δ → multiplier
   - Drift colored: <±5% green, <±15% warn, ≥15% red
   - Shows N samples per row

5. **★ NEW: FUNDING RATE STATUS (TOP-20)** HoloCard:
   - Per-symbol row with ASCII bar visualization:
     ```
     BTCUSDT  +0.0008%/8h  z=+0.4   ░░░░░██░░░░  neutral             n=90
     DOGEUSDT -0.0001%/8h  z=-2.6   ▓░░░░░░░░░░  ★ SHORT CROWDED ★  n=93
     ```
   - Extreme rows colored red (long_crowded) or green (short_crowded) with `★ LONG CROWDED ★` flag
   - Refetches every 60s

**Critical visual feedback:** The page should *feel* alive. Pulsing dot when healthy. Soft glow on extreme funding rows. The user should be able to tell at a glance "system is processing things" vs "system is stuck."

---

### 6.6 V5ReflectionPage — `/v5/reflection`

**Purpose:** Where the user audits AI's post-trade analyses and approves sizing recommendations.

**Layout: 3-tab page.**

#### Tab 1 — 最近复盘流 (default)

List of ReflectionCard:

```ts
interface ReflectionRecord {
  id: number;
  paper_trade_id: number;
  created_at: string;
  why_entered: string;
  what_was_expected: string;
  what_actually_happened: string;
  correction_idea: string;
  failure_mode_key: string | null;
  setup_type: string;
  outcome_class: 'WIN' | 'LOSS' | 'SCRATCH';
  realized_r: number;
  holding_minutes: number;
  confidence_at_entry: number;
  self_assessed_prediction_accuracy: number | null;
  ai_model: string | null;
  ai_latency_ms: number | null;
  symbol: string | null;
  side: 'LONG' | 'SHORT' | null;
  pnl_pct: number | null;
  funding_z_score_at_entry: number | null;
  funding_rate_at_entry: number | null;
}
```

Each card:
```
━━━ pos 7 — BTCUSDT SHORT — R+1.20 — WIN ━━━
setup_type: funding_extreme_short_rsi_overbought    
funding @ entry: +0.08%/8h • z=+2.4 ★ extreme        ← purple, only if data present
realized R: +1.20  holding: 23min   AI: deepseek-chat (3.2s)
                                                    
▶ 为什么开仓      | ▶ 当时怎么想
[text]            | [text]
▶ 实际怎么走      | ▶ 下次怎么改 ★
[text]            | [text]                    ← gold accent on correction
                                                    
[failure_mode badge if present]    AI: deepseek-chat • 自评 85%
```

The `▶` markers are cyan. The 5 questions are a 2-column grid. `★` on "下次怎么改" because it's the most actionable.

#### Tab 2 — 失败模式

Data:
```ts
interface FailureMode {
  key: string;
  label_zh: string;
  description: string;
  detection_rule: string | null;
  sample_count: number;
  is_active: boolean;
  seeded: boolean;
}
```

Table: 6 cols `key / 中文标签 / 命中次数 / detection_rule / 来源 / 激活`. Sample count colored warn if > 0. Seeded = 预置 badge (info), AI-proposed = AI 提案 badge (warn).

#### Tab 3 — 仓位建议

Each pending recommendation is a card:

```
setup_type: rsi_overbought_macd_bearish_short            confidence 78%
┌────────────────┬──────────────────┬──────────────────────┐
│ 当前 size 倍数 │ 推荐 size 倍数   │ Kelly 30/60/90d      │
│ 1.000          │ 0.600 (-40%)     │ 0.012 / 0.014 / ...  │
└────────────────┴──────────────────┴──────────────────────┘
30d Kelly=0.012, 60d=0.014, 90d=0.011; 一致性 86%; fractional_k=0.40

[批准 ✓]  [拒绝 ✗]  [改值: ____] [修改后批准]
```

Delta % colored. Buttons are clean rectangles with subtle border-tint. "修改后批准" button is disabled until user types in the input.

---

### 6.7 V5ChartPage — `/v5/chart/:symbol`

**Purpose:** Detailed visual analysis of one symbol's K-line with entry/exit markers.

**Layout:**
- Header: Symbol + current price + interval pills (15m / 1h / 4h)
- **Hover data row** above the chart: `▌ time | O / H / L / C | RSI | MACD hist` — updates as cursor moves
- Main chart: 360px Lightweight Charts candlestick with entry/exit markers + current price horizontal line
- Two sub-charts in 2-col grid below: RSI (with 70/30 lines) + MACD histogram

**Crosshair behavior:** Cyan vertical line. When user hovers in main chart, sub-charts get synchronized vertical lines at same X. Reverse also works.

---

### 6.8 V5ManualOrderPage — `/v5/manual` (3-step wizard)

**Purpose:** Operator-driven simulated trade with AI evaluation. SHADOW-only (LIVE shows warning).

**Step 1:** 3 inputs (Symbol / Side / Size USDT) + "模拟评估 →" button
**Step 2:** Three cards in grid: 当前指标 (IndicatorGauges) / 规则决策 (rule reasoning + SL/TP) / AI 二次审查 (verdict + multipliers user can tweak: SL × / TP × / Size ×)
- Below: RAG cases table (top-5 similar historical trades): RSI / MACD hist / 结果 / PnL / 原因 / 距离
- Bottom row: `[↩ 回到 Step 1]` and `[确认模拟开仓 →]`
**Step 3:** "✓ 模拟开仓成功" large + auto-redirect to /v5/active after 800ms

---

### 6.9 V5StrategyConfigPage — `/v5/config`

**Purpose:** Tune the 13 strategy parameters via sliders.

**Layout:** A list of parameter rows, each:
```
[v5_rsi_overbought]            ━━━━━●━━ [70.0]    ●(if changed)
开空 RSI 阈值
```
12-col grid: 3 cols param name + description (gray italic), 6 cols slider, 2 cols NumberInput, 1 col unit + changed marker.

Action bar at top: `[撤销修改]  [预览效果]  [保存修改]`. Buttons disabled until dirty. Preview shows estimated entries/hour + estimated win rate.

---

### 6.10 V5SettingsPage — `/v5/settings`

**Purpose:** Exchange / AI keys / Mode / Fail-closed knobs.

**Layout:** Stacked cards:
1. **交易所**: badge showing current
2. **AI 配置**: 2 password inputs for DeepSeek/OpenAI keys (placeholder shows masked) + active provider badge + Save button
3. **系统模式**: Mode badge (🟡 SHADOW or 🔴 LIVE) + toggle button. **LIVE switch requires modal confirm with warning.**
4. **Fail-closed 旋钮**: 3 checkboxes for `ai_fail_open`, `sl_tp_fail_open`, `enable_auto_trading`

---

### 6.11 V5SignalHistoryPage — `/v5/history`

Similar to OrderHistoryPage but for raw signals — 7-column table: 时间 / 币种 / 方向 / ΔP15m / RSI / MACD hist / 结果. Filter dropdown for block_reason. Color-coded result column.

---

### 6.12 V5GlossaryPage — `/v5/glossary`

Reference page. 6 category sections (仓位 / 指标 / 信号 / AI / 平仓原因 / 统计). Each section: grid of small term cards `key (mono) | zh label | description | optional example`. Search input filters across all fields.

---

## 7. Charts & Visualizations Guidance

### 7.1 Lightweight Charts (K-line)

- **Use for:** ChartPage main candles + RSI/MACD sub-charts
- Configure: dark theme, `bg = #0F1419`, grid lines `rgba(255,255,255,0.04)`, time axis border `rgba(255,255,255,0.08)`
- Candle colors: up `#10B981`, down `#EF4444`
- Crosshair: cyan `rgba(34,211,238,0.6)`, mode = Normal
- Markers: arrowUp (LONG entry, green), arrowDown (SHORT entry, red), circle (exit, colored by TP_HIT/SL_HIT)
- Price lines (SL, TP, current): dashed thin

### 7.2 Recharts (analytics)

- **Use for:** Dashboard PnL curve, future analytics charts
- Configure: stroke `#3B82F6`, no dots on line, `XAxis stroke="rgba(255,255,255,0.4)"`, ResponsiveContainer
- Tooltip background `#1A2030` matches surface

### 7.3 ASCII Visualizations (cyber)

- **Use for:** Funding heatmap z-score bar, RAG bars, anywhere mono+playful
- Format: `▓` for active position, `░` for empty: `░░░░░▓░░░░░`
- Each character ~12px in font-mono; 10 chars width works well at `text-[11px]`

### 7.4 Sparkline

- **Use for:** AI confidence over recent decisions, anywhere you need a 24-char-wide trend hint
- SVG `<polyline>` only — no library. Stroke `#22D3EE`, width 1.5px.

---

## 8. State Patterns

- **Loading**: `<LoadingSkeleton rows={N} />` — gray pulsing bars
- **Empty**: italic muted text with leading `▌` glyph: `▌ 等待第一笔关仓后,reflection worker 自动生成`
- **Error**: red border card with detail string + retry button
- **Stale data**: small dot + tooltip "数据可能过期" in TopBar
- **Filter active**: chip-style badge showing filter value, click to clear

---

## 9. Interaction Patterns

- **Refresh button**: small `⟳` icon top-right of any data card. Manual refetch overrides polling.
- **Drilldown navigation**: clickable list items / table rows / funnel layers always navigate. Cursor pointer.
- **Confirm modals**: every destructive or LIVE-flow action needs one. Two buttons (Cancel + Confirm). Confirm uses semantic color (short for close/danger, info for neutral).
- **Inline editing**: NumberInput components for thresholds, multipliers. Slider companion for visual scrub.
- **Toast**: emit on save success/failure. Top-right stack. Auto-dismiss 4s.
- **WebSocket events**: surface as toast pop OR badge increment on TopBar bell. Don't interrupt user.

---

## 10. Mobile / Tablet

**Not a primary target — but graceful breakpoints expected.** Operator runs this on desktop 99% of the time. Phone usage is for quick checks while away.

- Below 1024px: sidebar collapses, hamburger toggle
- Below 768px: KPI grid 4 → 2 cols, tables become horizontal-scroll
- Below 640px: ChartPage K-line height shrinks to 240px, sub-charts stack vertically
- No iOS-style bottom nav

---

## 11. Tech Stack Constraints

The generated UI must be compatible with:

- **React 19** (`react@^19.2.3`, `react-dom@^19.2.3`)
- **TypeScript 5.8** (strict mode off, but typing matters)
- **Vite 6** (build tool, you don't generate vite config)
- **Tailwind 3.4** (config injects design tokens — use `bg-bg-base`, `text-accent-long`, etc as classes)
- **React Router 7** (`<NavLink>`, `<Outlet>`)
- **TanStack Query 5** (`useQuery` / `useMutation` for data fetching)
- **Zustand 4** (UI state only — sidebar collapse, expanded signal IDs, WS event queue)
- **Lightweight Charts 4.1** (candle + sub-charts)
- **Recharts 3.7** (analytics charts)
- **lucide-react 0.563** (icons — pick from this set only)
- **mock-socket 9** (dev only, WS tests)
- **MSW 2** (dev only, API mocking)

**You may NOT introduce:**
- Material UI, Ant Design, Mantine, Chakra (any UI lib)
- styled-components, Emotion (no CSS-in-JS — Tailwind only)
- Framer Motion (use CSS animations from index.css)
- Heroicons or other icon sets (lucide-react only)
- Date libraries beyond `Date` + `Intl.DateTimeFormat`
- Form libraries (react-hook-form etc — uncontrolled inputs are fine)

---

## 12. API Endpoint Reference

All endpoints under `/api/v5/*`. Response shape is consistently `{status: "success", data: [...]}` for lists, `{status, ...flat fields}` for single objects.

| Endpoint | Returns | Used By |
|---|---|---|
| `GET /signals?limit=&side=` | `{status, data: V5Signal[]}` | SignalsPage, SignalHistoryPage |
| `GET /positions?status=OPEN\|CLOSED` | `{status, data: V5Position[]}` | ActivePositionsPage, OrderHistoryPage |
| `GET /paper-positions?status=...` | `{status, data: V5Position[]}` | same |
| `POST /positions/:id/close` | `{position_id, status, exit_price, exit_reason}` | ActivePositionsPage |
| `GET /ai/status` | flat `AIStatusResponse` | AIStatusPage |
| `GET /ai/decisions?limit=` | `{status, data: AIDecisionItem[]}` | AIStatusPage |
| `GET /strategy-config` | `{status, params: ParamSpec[]}` | StrategyConfigPage |
| `PATCH /strategy-config` | same | save action |
| `POST /strategy-config/preview` | `StrategyConfigPreviewResponse` | preview action |
| `GET /settings` | flat `SettingsResponse` | SettingsPage |
| `PATCH /settings` | same | save action |
| `POST /manual-order/preview` | `ManualOrderPreviewResponse` | ManualOrderPage Step 1→2 |
| `POST /manual-order/execute` | `ManualOrderExecuteResponse` | ManualOrderPage Step 2→3 |
| `GET /klines/:symbol?interval=&limit=` | `{symbol, interval, klines: Kline[]}` | ChartPage |
| `GET /events/:symbol?limit=` | `{symbol, events: SymbolEvent[]}` | ChartPage |
| `GET /reflections?limit=` | `{status, data: ReflectionRecord[]}` | ReflectionPage Tab 1 |
| `GET /failure-taxonomy` | `{status, data: FailureMode[]}` | ReflectionPage Tab 2 |
| `GET /sizing-recommendations?status=pending` | `{status, data: SizingRecommendation[]}` | ReflectionPage Tab 3 |
| `PATCH /sizing-recommendations/:id` | `{status, rec_id, new_status}` | ReflectionPage Tab 3 |
| `GET /setup-performance?days=` | `{status, data: SetupPerformanceItem[]}` | DashboardPage SetupBreakdownTable |
| `GET /confidence-calibration` | `{status, data: CalibrationPoint[]}` | AIStatusPage CalibrationCurveCard |
| `GET /funding/status` | `{status, data: FundingZScoreItem[]}` ★ V6 | AIStatusPage FundingHeatmapCard |
| `GET /funding/history/:symbol` | `{status, symbol, data: FundingHistoryItem[]}` ★ V6 | (future symbol detail page) |

**WebSocket:** `ws://host/ws/v5` — pushes `{type: 'position_opened' | 'position_closed' | 'position_extended' | 'ai_health' | 'scoring_stalled' | 'ping', ...}`. Use these to invalidate React Query keys + push to a Toast queue.

---

## 13. Information Hierarchy Cheatsheet

When designing any new page or refactoring an existing one, prioritize information visibility in this order:

1. **What is the system doing RIGHT NOW** (active count, last action, WS health)
2. **What is at risk RIGHT NOW** (open positions PnL, AI health)
3. **What needs my decision** (pending sizing recs, settings drift)
4. **Recent outcomes** (last reflections, last closed trades)
5. **Aggregated 24h / 7d numbers** (KPIs, breakdowns)
6. **Historical browse** (signal history, order history)
7. **Configuration** (strategy params, settings, glossary)

A high-priority piece of info should be 1 click away from the home page (Dashboard). Anything below #3 can be on a sub-page.

---

## 14. Things to Get Right

- **Numbers are sacred.** Use `tabular-nums`. Use mono font. Right-align all numeric table columns. Don't truncate prices, only volumes.
- **Color = direction.** Green = LONG / WIN / healthy. Red = SHORT / LOSS / danger. Amber = warn / drift. Blue = neutral info. Never mix metaphors.
- **Polling is shown.** Each data card has its refetch interval visible (`每 5s 自动刷新` text in card actions). User trusts what they can see.
- **Failure modes need eye-catching presence.** When a `failure_mode_key` shows up in a reflection card or a `block_reason=FAILURE_MODE_MATCH:...` in a signal, color it amber or red consistently.
- **Funding signals are the new alpha.** Anything `funding_extreme_*` should get a small ★ + violet tint to make the user notice them differently from old RSI/MACD setups.
- **Cyber styling is exclusive.** HoloCard / neon-pulse / cyber-grid → AI Status only. Other pages stay calm and tabular.

---

## 15. Things to Avoid

- Don't add cards labeled "Quick Actions" or floating action buttons. The sidebar is the action surface.
- Don't add modal-based onboarding tours. The user is the operator; they know what they want.
- Don't add login/signup screens. This is a self-hosted single-user app.
- Don't add a "stats over all time" page. Operator works in 24h / 7d / 30d windows.
- Don't add chat/comment UI. There's no social layer.
- Don't add light/dark theme toggle. Dark only.
- Don't add notification permission popups.
- Don't add "you have unread" badges that grow unboundedly. WS event queue caps at 20.

---

## 16. Quick Page-to-Component Map (for AI generation order)

If you're generating UIs page-by-page in priority order:

1. **AppShell + Sidebar + TopBar** (the chrome)
2. **V5DashboardPage** (most-visited)
3. **V5SignalsPage** (most-watched)
4. **V5ActivePositionsPage** (most-critical)
5. **V5ChartPage** (most visually demanding)
6. **V5AIStatusPage** (most styled, cyber direction reference)
7. **V5ReflectionPage** (most semantically rich)
8. **V5ManualOrderPage** (most multi-step)
9. Remaining pages (Orders / History / Config / Settings / Glossary)

Each can be generated independently; they all live inside AppShell's `<Outlet />`.

---

## 17. Output Format Hint for the Generating AI

When you produce designs, prefer:

- **For mockups**: render an HTML preview using Tailwind CDN classes that match the tokens above. Don't use inline styles; classes only.
- **For component code**: TypeScript `.tsx` files with `'use client'` directive at top (in case it's used in Next.js), TanStack Query hooks for data, lucide-react icons, Tailwind classes only.
- **For visual variants**: produce 2-3 options when ambiguous — the operator wants to compare.
- **For data placeholders**: use realistic sample data matching the TypeScript interfaces above (e.g., `BTCUSDT` symbols, prices `0.166`, RSI `72.1`, z-score `+2.4`).
- **No animations** beyond CSS keyframes from §3.1.

---

**[End of brief — paste this entire document as context to your UI generation AI.]**
