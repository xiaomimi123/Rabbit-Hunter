# V5 Plan B-2 Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the entire `Rabbit Hunterfronted/` V4.3 React codebase with a V5 stack: 10 pages built on a typed React-Query+Zustand+WS foundation, sharing a tokens-driven design system, fully wired to the 12 V5 backend routes + `/ws/v5` shipped in `v5.0.0-plan-b-backend-shipped`.

**Architecture:**
- **Foundation first** — tokens → primitives → AppShell → routes; pages plug in last
- **Server state in React Query, UI state in Zustand** — no overlap, no cached duplicates
- **WebSocket is a notifier, not a data source** — events trigger `queryClient.invalidateQueries`, never write directly to component state
- **Chart pages use Lightweight Charts 4** for K-line + sub-charts (RSI/MACD); Dashboard uses Recharts for analytics

**Tech Stack:**
- Existing: React 19, Vite 6, TS 5.8, Tailwind 3.4, Vitest 1.0, jsdom, RTL 14, @tanstack/react-query 5.90, zustand 4.4, lightweight-charts 4.1, recharts 3.7, lucide-react 0.563
- **Added in T1:** `react-router-dom@7`, `msw@2` (dev), `mock-socket@9` (dev)

**Working directory:** `/Users/lizhishaoniange/Documents/Rabbit-Hunter/Rabbit Hunterfronted/` (preserve the space; "fronted" typo is the real folder name).

**Backend contract (already shipped, do not modify):**

| Hook | Method + URL | Response file |
|---|---|---|
| useV5Signals | `GET /api/v5/signals?limit=&filter=` | `api/schemas/scores.py` V5SignalsResponse |
| useV5ActivePositions | `GET /api/v5/positions?status=OPEN` + `GET /api/v5/paper-positions?status=OPEN` | `api/schemas/positions.py` V5PositionsResponse |
| useV5OrderHistory | `GET /api/v5/positions?status=CLOSED` + paper-positions | same |
| useV5Dashboard | derives from signals + paper-positions (no dedicated endpoint) | — |
| useV5AIStatus | `GET /api/v5/ai/status` + `GET /api/v5/ai/decisions?limit=` | `api/schemas/v5_ai.py` |
| useV5StrategyConfig | `GET/PATCH /api/v5/strategy-config` + `POST /preview` | `api/schemas/v5_strategy_config.py` |
| useV5Settings | `GET/PATCH /api/v5/settings` | `api/schemas/v5_settings.py` SettingsResponse |
| useV5ManualOrder | `POST /api/v5/manual-order/preview` + `POST /execute` | `api/schemas/v5_manual_order.py` |
| useV5Klines | `GET /api/v5/klines/{symbol}?interval=&limit=` (symbol uses `_` for `/`) | `api/schemas/v5_charts.py` KlinesResponse |
| useV5SymbolEvents | `GET /api/v5/events/{symbol}` | `api/schemas/v5_charts.py` SymbolEventsResponse |
| WebSocket | `wss://host/ws/v5` events: `position_opened` / `position_closed` / `position_extended` / `ai_health` / `scoring_stalled` | — |
| Position close | `POST /api/v5/positions/{id}/close` body `{exit_price, exit_reason}` | inline CloseResponse |

**Phases**
1. **Cleanup + foundation** (T1-T6): scaffold, types, tokens, fetch wrapper, store, WS hook
2. **Primitives** (T7): Card/Badge/Modal/Slider/etc
3. **Shared components** (T8-T9): IndicatorGauges/KpiCard/etc + IndicatorOverlayChart
4. **Layout + routing** (T10): AppShell + Sidebar + TopBar + App.tsx
5. **Pages** (T11-T16): 10 pages, batched by similarity
6. **Verification** (T17): build + tests + docker + tag

**Direct push to `main`** per user policy throughout — no PRs, no branches.

---

## Phase 1: Cleanup + Foundation

### Task 1: Scaffold + dependency install + delete V4.3 files

**Files:**
- Modify: `Rabbit Hunterfronted/package.json` (add deps, rename, bump version)
- Delete: 18 V4.3 component/hook/service files (full list below)
- Create: empty placeholder dirs to lock the structure

- [ ] **Step 1: Inventory old files (sanity check)**

Run: `ls "Rabbit Hunterfronted/components/" "Rabbit Hunterfronted/hooks/" "Rabbit Hunterfronted/services/"`. Confirm the following exist before deletion (if not, adjust the delete list — don't blindly `rm`):

```
components/: AIStatus.tsx AnatomyPanel.tsx Charts.tsx Dashboard.tsx ErrorBoundary.tsx
             FeatureFlagsPanel.tsx KillBoard.tsx Layout.tsx OrderPage.tsx PositionsPage.tsx
             SettingsPage.tsx StrategyConfig.tsx Toast.tsx TradeScores.tsx TradingViewChart.tsx
             VirtualList.tsx WeightHistory.tsx
hooks/:      useExchange.ts useKillQueue.ts usePaperTrades.ts usePositions.ts
             useSystemMode.ts useSystemStatus.ts useWeights.ts
services/:   api.ts apiInterceptor.ts featureFlags.ts geminiService.ts store.ts
             tradingViewChart.ts websocket.ts
```

- [ ] **Step 2: Delete V4.3 files**

```bash
cd "Rabbit Hunterfronted"
rm -f components/AIStatus.tsx components/AnatomyPanel.tsx components/Charts.tsx \
      components/Dashboard.tsx components/ErrorBoundary.tsx components/FeatureFlagsPanel.tsx \
      components/KillBoard.tsx components/Layout.tsx components/OrderPage.tsx \
      components/PositionsPage.tsx components/SettingsPage.tsx components/StrategyConfig.tsx \
      components/Toast.tsx components/TradeScores.tsx components/TradingViewChart.tsx \
      components/VirtualList.tsx components/WeightHistory.tsx
rm -f hooks/useExchange.ts hooks/useKillQueue.ts hooks/usePaperTrades.ts \
      hooks/usePositions.ts hooks/useSystemMode.ts hooks/useSystemStatus.ts hooks/useWeights.ts
rm -f services/api.ts services/apiInterceptor.ts services/featureFlags.ts \
      services/geminiService.ts services/store.ts services/tradingViewChart.ts services/websocket.ts
rm -f App.tsx constants.tsx types.ts
rm -rf components/ui
```

- [ ] **Step 3: Create V5 directory skeleton**

```bash
mkdir -p components/pages components/shared components/layout components/primitives
mkdir -p hooks/api
mkdir -p tests/hooks tests/shared tests/pages tests/services
```

- [ ] **Step 4: Update package.json**

Read `Rabbit Hunterfronted/package.json`, then write the file (the Write tool will overwrite) with:

```json
{
  "name": "rabbit-hunter-v5-cockpit",
  "private": true,
  "version": "5.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:ui": "vitest --ui",
    "test:coverage": "vitest --coverage"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.90.21",
    "lightweight-charts": "^4.1.0",
    "lucide-react": "^0.563.0",
    "react": "^19.2.3",
    "react-dom": "^19.2.3",
    "react-router-dom": "^7.1.1",
    "recharts": "^3.7.0",
    "zustand": "^4.4.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.1.5",
    "@testing-library/react": "^14.1.2",
    "@testing-library/user-event": "^14.5.1",
    "@types/node": "^22.14.0",
    "@vitejs/plugin-react": "^5.0.0",
    "autoprefixer": "^10.4.17",
    "jsdom": "^23.0.1",
    "mock-socket": "^9.3.1",
    "msw": "^2.7.0",
    "postcss": "^8.4.32",
    "tailwindcss": "^3.4.1",
    "typescript": "~5.8.2",
    "vite": "^6.2.0",
    "vitest": "^1.0.4"
  }
}
```

Notes on removed deps: `@google/genai` (V4.3 only); `react-is` (was a peer override no longer needed).

- [ ] **Step 5: Install**

```bash
cd "Rabbit Hunterfronted"
npm install 2>&1 | tail -5
```

Expected: completes without errors; `node_modules/react-router-dom` and `node_modules/msw` exist.

- [ ] **Step 6: Strip Gemini env from vite.config.ts**

`Rabbit Hunterfronted/vite.config.ts` — remove the `define: { 'process.env.API_KEY': ..., 'process.env.GEMINI_API_KEY': ... }` block and the `loadEnv` import. Replace with:

```ts
import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  server: {
    port: 3000,
    host: '0.0.0.0',
  },
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
});
```

- [ ] **Step 7: Strip Gemini script-tag from index.html**

`Rabbit Hunterfronted/index.html`: remove any `<script type="importmap">` referencing `@google/genai`, plus any inline references to `process.env.GEMINI_API_KEY`. Keep `<div id="root">`, `<script type="module" src="/index.tsx">`, the head meta/title.

- [ ] **Step 8: Commit**

```bash
git add -A "Rabbit Hunterfronted/package.json" "Rabbit Hunterfronted/package-lock.json" \
            "Rabbit Hunterfronted/vite.config.ts" "Rabbit Hunterfronted/index.html"
git add -A "Rabbit Hunterfronted/components" "Rabbit Hunterfronted/hooks" \
            "Rabbit Hunterfronted/services" "Rabbit Hunterfronted/tests"
# also stage deletions of App.tsx / constants.tsx / types.ts
git add -A "Rabbit Hunterfronted/App.tsx" "Rabbit Hunterfronted/constants.tsx" \
            "Rabbit Hunterfronted/types.ts" 2>/dev/null || true
git commit -m "chore(frontend): wipe V4.3, scaffold V5 skeleton, add deps

- Delete 18 V4.3 component/hook/service files + App.tsx/constants.tsx/types.ts
- Create components/{pages,shared,layout,primitives}, hooks/api, tests/*
- Add react-router-dom@7, msw@2, mock-socket@9; drop @google/genai, react-is
- Strip Gemini env wiring from vite.config.ts + index.html"
```

---

### Task 2: types.ts mirror of V5 Pydantic schemas

**Files:**
- Create: `Rabbit Hunterfronted/types.ts`

The frontend types must match the field names exactly as Pydantic serializes them (snake_case).

- [ ] **Step 1: Write `Rabbit Hunterfronted/types.ts`**

```ts
// V5 API types. Field names mirror api/schemas/*.py exactly.
// Time fields are ISO 8601 UTC strings (ensure_utc_iso()).

export type Side = 'LONG' | 'SHORT';
export type Mode = 'SHADOW' | 'LIVE';
export type OutcomeLabel = 'WIN' | 'LOSS' | 'FLAT';
export type EventType = 'entry' | 'exit' | 'extension';
export type Interval = '15m' | '1h' | '4h';
export type AIProvider = 'deepseek' | 'openai';

// ── Signals ──
export interface V5Signal {
  id: number;
  symbol: string;
  created_at: string;
  delta_15m_pct: number;
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
  side: Side | null;
  reasoning: string;
  block_reason: string | null;
  ai_confidence: number | null;
  ai_sl_multiplier: number | null;
  ai_tp_multiplier: number | null;
  ai_size_multiplier: number | null;
  ai_reasoning: string | null;
  entry_price: number | null;
  sl_price: number | null;
  tp_price: number | null;
  size_usdt: number | null;
  expected_rr: number | null;
  executed: boolean;
  position_id: number | null;
}

export interface V5SignalsResponse {
  signals: V5Signal[];
  count: number;
}

// ── Positions ──
export interface V5Position {
  id: number;
  symbol: string;
  side: Side;
  status: 'OPEN' | 'CLOSED';
  entry_price: number;
  current_price: number | null;
  stop_loss: number;
  take_profit: number;
  position_size_usdt: number;
  leverage: number;
  entry_time: string;
  exit_time: string | null;
  exit_price: number | null;
  exit_reason: string | null;
  pnl_percent: number | null;
  pnl_usdt: number | null;
  entry_rsi_15m: number | null;
  entry_macd_hist_15m: number | null;
  extension_count: number | null;
  target_close_at: string | null;
  ai_reason: string | null;
  strategy_id: string | null;
}

export interface V5PositionsResponse {
  positions: V5Position[];
  count: number;
}

// ── Strategy Config ──
export interface ParamSpec {
  key: string;
  value: number;
  default: number;
  min: number;
  max: number;
  unit: string;
  description: string;
}
export interface StrategyConfigResponse {
  params: ParamSpec[];
}
export interface StrategyConfigPatchRequest {
  [key: string]: number;
}
export interface StrategyConfigPreviewResponse {
  estimated_entries_per_hour: number;
  estimated_win_rate: number;
  note: string;
}

// ── Settings ──
export interface SettingsResponse {
  exchange: string;
  openai_api_key_masked: string;
  openai_assistant_id: string | null;
  openai_vector_store_id: string | null;
  deepseek_api_key_masked: string;
  deepseek_enabled: boolean;
  active_ai_provider: AIProvider | null;
  active_chat_model: string;
  system_mode: Mode;
  enable_auto_trading: boolean;
  ai_fail_open: boolean;
  sl_tp_fail_open: boolean;
}
export interface SettingsPatchRequest {
  exchange?: string;
  openai_api_key?: string;
  openai_assistant_id?: string | null;
  deepseek_api_key?: string;
  deepseek_enabled?: boolean;
  system_mode?: Mode;
  enable_auto_trading?: boolean;
  ai_fail_open?: boolean;
  sl_tp_fail_open?: boolean;
}

// ── AI Status ──
export interface AIStatusResponse {
  provider: AIProvider | null;
  chat_model: string;
  healthy: boolean;
  last_latency_ms: number | null;
  decisions_24h: number;
  rag_utilization_24h: number;
  rag_cases_in_db: number;
}
export interface AIDecisionItem {
  id: number;
  created_at: string;
  symbol: string;
  side: Side | null;
  execute: boolean;
  confidence: number | null;
  reasoning: string;
  top1_distance: number | null;
  rag_case_count: number;
}
export interface AIDecisionsResponse {
  decisions: AIDecisionItem[];
  count: number;
}

// ── Charts ──
export interface Kline {
  ts: number;     // ms epoch
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}
export interface KlinesResponse {
  symbol: string;
  interval: Interval;
  klines: Kline[];
}
export interface SymbolEvent {
  event_type: EventType;
  side: Side;
  price: number;
  timestamp: string;
  position_id: number;
  reasoning?: string;
  rsi_15m?: number | null;
  macd_hist_15m?: number | null;
  exit_reason?: string | null;
  pnl_pct?: number | null;
}
export interface SymbolEventsResponse {
  symbol: string;
  events: SymbolEvent[];
}

// ── Manual Order ──
export interface ManualOrderPreviewRequest {
  symbol: string;
  side: Side;
  size_usdt: number;
}
export interface ManualOrderDecisionSnapshot {
  should_trade: boolean;
  side: Side | null;
  reasoning: string;
  block_reason: string | null;
}
export interface ManualOrderRagCase {
  entry_rsi_15m: number;
  entry_macd_hist_15m: number;
  outcome: OutcomeLabel;
  pnl_pct: number;
  exit_reason: string | null;
  distance: number;
}
export interface ManualOrderAiResult {
  execute: boolean;
  sl_multiplier: number;
  tp_multiplier: number;
  size_multiplier: number;
  confidence: number;
  reasoning: string;
}
export interface ManualOrderPreviewResponse {
  symbol: string;
  side: Side;
  current_price: number;
  indicators: Record<string, number>;
  decision: ManualOrderDecisionSnapshot;
  risk_plan: Record<string, number>;
  ai_result: ManualOrderAiResult;
  rag_cases: ManualOrderRagCase[];
  rag_summary: string | null;
}
export interface ManualOrderExecuteRequest {
  symbol: string;
  side: Side;
  size_usdt: number;
  sl_multiplier: number;
  tp_multiplier: number;
  size_multiplier: number;
}
export interface ManualOrderExecuteResponse {
  position_id: number;
  symbol: string;
  side: Side;
  entry_price: number;
  sl_price: number;
  tp_price: number;
  size_usdt: number;
  strategy_id: string;
}

// ── Close Position ──
export interface ClosePositionRequest {
  exit_price: number;
  exit_reason: string;
}
export interface ClosePositionResponse {
  position_id: number;
  status: 'CLOSED';
  exit_price: number;
  exit_reason: string;
}

// ── WebSocket ──
export type WsEvent =
  | { type: 'position_opened'; symbol: string; side: Side; entry: number; sl: number; tp: number; size_usdt: number; position_id: number; strategy_id: string; mode: Mode }
  | { type: 'position_closed'; position_id: number; symbol: string; exit_price: number; exit_reason: string; pnl_usdt?: number; pnl_pct?: number; holding_minutes?: number }
  | { type: 'position_extended'; position_id: number; symbol: string; new_target_close_at?: string; extension_count: number }
  | { type: 'ai_health'; provider: AIProvider; chat_model: string; last_latency_ms: number | null; healthy: boolean }
  | { type: 'scoring_stalled'; seconds_since_last_score: number; last_symbol_seen: string | null }
  | { type: 'ping'; ts: number };
```

- [ ] **Step 2: Sanity-check TS compiles**

```bash
cd "Rabbit Hunterfronted"
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors. (If types.ts references something not in scope, the only file consuming it is itself — should compile clean.)

- [ ] **Step 3: Commit**

```bash
git add "Rabbit Hunterfronted/types.ts"
git commit -m "feat(frontend): V5 types.ts mirroring backend Pydantic schemas

- Signals/Positions/Settings/AI/Strategy/Charts/ManualOrder/Close/Ws
- Time fields stay strings (ISO 8601 UTC), epoch ms only for Kline.ts
- snake_case preserved to match FastAPI default serialization"
```

---

### Task 3: Design tokens + Tailwind config

**Files:**
- Create: `Rabbit Hunterfronted/services/tokens.ts`
- Modify: `Rabbit Hunterfronted/tailwind.config.js`
- Modify: `Rabbit Hunterfronted/index.css`

- [ ] **Step 1: Write `Rabbit Hunterfronted/services/tokens.ts`**

```ts
// Single source of truth for V5 colors / spacing / radius / motion / fonts.
// Tailwind reads these via tailwind.config.js; components can read directly via import.

export const tokens = {
  color: {
    bg: {
      base: '#0F1419',
      surface: '#1A2030',
      surfaceHover: '#222B3D',
      border: 'rgba(255,255,255,0.08)',
    },
    text: {
      primary: '#FFFFFF',
      secondary: 'rgba(255,255,255,0.72)',
      muted: 'rgba(255,255,255,0.48)',
    },
    accent: {
      long: '#10B981',
      short: '#EF4444',
      warn: '#F59E0B',
      info: '#3B82F6',
      primary: '#F97316',
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
  space: { 1: 4, 2: 8, 3: 12, 4: 16, 6: 24, 8: 32, 12: 48 },
  radius: { sm: 4, md: 8, lg: 12, full: 9999 },
  motion: {
    fast: '120ms cubic-bezier(0.4, 0, 0.2, 1)',
    base: '200ms cubic-bezier(0.4, 0, 0.2, 1)',
    slow: '400ms cubic-bezier(0.4, 0, 0.2, 1)',
  },
} as const;

export type Tokens = typeof tokens;
```

- [ ] **Step 2: Rewrite `Rabbit Hunterfronted/tailwind.config.js`**

```js
import { tokens } from './services/tokens.ts';

export default {
  content: [
    './index.html',
    './App.tsx',
    './components/**/*.{ts,tsx}',
    './hooks/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: tokens.color.bg,
        accent: tokens.color.accent,
        risk: tokens.color.risk,
        muted: tokens.color.text.muted,
      },
      fontFamily: {
        mono: tokens.font.mono.split(',').map(s => s.trim().replace(/"/g, '')),
        sans: tokens.font.sans.split(',').map(s => s.trim().replace(/"/g, '')),
      },
      borderRadius: {
        sm: `${tokens.radius.sm}px`,
        md: `${tokens.radius.md}px`,
        lg: `${tokens.radius.lg}px`,
      },
      transitionDuration: {
        fast: '120ms',
        base: '200ms',
        slow: '400ms',
      },
    },
  },
  plugins: [],
};
```

Note: `tailwind.config.js` importing a `.ts` file works because we use ESM (`"type": "module"` in package.json) and PostCSS/Tailwind handles it; if Tailwind complains about TS at build, change tokens.ts to tokens.mjs or duplicate the values (the duplication risk is acceptable here since tokens rarely change).

- [ ] **Step 3: Write `Rabbit Hunterfronted/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color-scheme: dark;
  font-family: "PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif;
  background-color: #0F1419;
  color: #FFFFFF;
}

body {
  margin: 0;
  min-height: 100vh;
  background-color: #0F1419;
  color: #FFFFFF;
}

#root {
  min-height: 100vh;
}

.font-mono {
  font-family: "JetBrains Mono", "IBM Plex Mono", monospace;
  font-variant-numeric: tabular-nums;
}

/* Scrollbar */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.24);
}
```

- [ ] **Step 4: Sanity build**

```bash
cd "Rabbit Hunterfronted"
npx tailwindcss -i index.css -o /tmp/tw-test.css 2>&1 | tail -5
```

Expected: writes `/tmp/tw-test.css` without error. (If the `.ts` import fails, fall back: copy tokens values inline into tailwind.config.js as plain JS object literal and skip the import — note the duplication in a comment.)

- [ ] **Step 5: Commit**

```bash
git add "Rabbit Hunterfronted/services/tokens.ts" "Rabbit Hunterfronted/tailwind.config.js" \
        "Rabbit Hunterfronted/index.css"
git commit -m "feat(frontend): design tokens + Tailwind injection

- services/tokens.ts as single source of truth
- tailwind.config.js extends colors/font/radius from tokens
- index.css base styles + scrollbar"
```

---

### Task 4: API client + interceptor

**Files:**
- Create: `Rabbit Hunterfronted/services/api.ts`
- Create: `Rabbit Hunterfronted/services/apiInterceptor.ts`
- Create: `Rabbit Hunterfronted/tests/services/api.test.ts`

- [ ] **Step 1: Write failing test `Rabbit Hunterfronted/tests/services/api.test.ts`**

```ts
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { apiGet, apiPost, apiPatch, ApiError } from '@/services/api';

describe('api client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('apiGet returns parsed JSON on 200', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    const out = await apiGet<{ ok: boolean }>('/api/v5/signals');
    expect(out).toEqual({ ok: true });
  });

  it('apiGet throws ApiError on 4xx with detail', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'nope' }), { status: 404 }),
    );
    await expect(apiGet('/api/v5/x')).rejects.toMatchObject({
      status: 404,
      detail: 'nope',
    });
  });

  it('apiPost sends JSON body and parses response', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ id: 42 }), { status: 200 }),
    );
    const out = await apiPost<{ id: number }>('/api/v5/x', { side: 'SHORT' });
    expect(out.id).toBe(42);
    const call = (fetch as any).mock.calls[0];
    expect(call[1].method).toBe('POST');
    expect(JSON.parse(call[1].body)).toEqual({ side: 'SHORT' });
    expect(call[1].headers['Content-Type']).toBe('application/json');
  });

  it('apiPatch uses PATCH method', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({}), { status: 200 }),
    );
    await apiPatch('/api/v5/strategy-config', { v5_rsi_overbought: 68 });
    expect((fetch as any).mock.calls[0][1].method).toBe('PATCH');
  });

  it('attaches Authorization header when API_BEARER_TOKEN is set', async () => {
    (fetch as any).mockResolvedValueOnce(new Response('{}', { status: 200 }));
    (window as any).__API_BEARER_TOKEN__ = 'tok123';
    await apiGet('/api/v5/x');
    expect((fetch as any).mock.calls[0][1].headers.Authorization).toBe('Bearer tok123');
    delete (window as any).__API_BEARER_TOKEN__;
  });

  it('5xx without body raises with generic detail', async () => {
    (fetch as any).mockResolvedValueOnce(new Response('', { status: 503 }));
    await expect(apiGet('/api/v5/x')).rejects.toMatchObject({
      status: 503,
    });
  });
});
```

- [ ] **Step 2: Run, expect 6 fail (no module yet)**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/services/api.test.ts 2>&1 | tail -10
```

- [ ] **Step 3: Write `Rabbit Hunterfronted/services/api.ts`**

```ts
// V5 fetch wrapper. Adds Authorization header if window.__API_BEARER_TOKEN__ set.
// Throws ApiError on 4xx/5xx so React Query treats them as errors.

export class ApiError extends Error {
  status: number;
  detail: string;
  url: string;
  constructor(status: number, detail: string, url: string) {
    super(`[${status}] ${detail} (${url})`);
    this.status = status;
    this.detail = detail;
    this.url = url;
  }
}

const BASE = '';   // same-origin in production (nginx proxies /api/* to FastAPI)

function buildHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...extra };
  const token = (typeof window !== 'undefined' && (window as any).__API_BEARER_TOKEN__) || null;
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function parseOrThrow<T>(res: Response, url: string): Promise<T> {
  if (res.ok) {
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }
  let detail = res.statusText || `HTTP ${res.status}`;
  try {
    const body = await res.json();
    if (body && typeof body.detail === 'string') detail = body.detail;
  } catch {
    // body not JSON — keep statusText
  }
  throw new ApiError(res.status, detail, url);
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE}${path}`;
  const res = await fetch(url, { method: 'GET', headers: buildHeaders(), ...init });
  return parseOrThrow<T>(res, url);
}

export async function apiPost<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
  const url = `${BASE}${path}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: buildHeaders(),
    body: body == null ? undefined : JSON.stringify(body),
    ...init,
  });
  return parseOrThrow<T>(res, url);
}

export async function apiPatch<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
  const url = `${BASE}${path}`;
  const res = await fetch(url, {
    method: 'PATCH',
    headers: buildHeaders(),
    body: body == null ? undefined : JSON.stringify(body),
    ...init,
  });
  return parseOrThrow<T>(res, url);
}

export async function apiDelete<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE}${path}`;
  const res = await fetch(url, { method: 'DELETE', headers: buildHeaders(), ...init });
  return parseOrThrow<T>(res, url);
}
```

- [ ] **Step 4: Write `Rabbit Hunterfronted/services/apiInterceptor.ts`**

```ts
// Toast-bus on 401/403 + network failures. Subscribed by AppShell + WS hook.
import type { ApiError } from './api';

type Listener = (err: ApiError) => void;
const listeners: Listener[] = [];

export function onApiError(fn: Listener): () => void {
  listeners.push(fn);
  return () => {
    const i = listeners.indexOf(fn);
    if (i >= 0) listeners.splice(i, 1);
  };
}

export function reportApiError(err: ApiError): void {
  for (const fn of listeners) {
    try { fn(err); } catch { /* swallow */ }
  }
}

// React Query queryFn wrapper: catches ApiError, reports to listeners, rethrows.
export function withInterceptor<T>(p: Promise<T>): Promise<T> {
  return p.catch((err) => {
    if (err && typeof err === 'object' && 'status' in err) {
      reportApiError(err as ApiError);
    }
    throw err;
  });
}
```

- [ ] **Step 5: Setup vitest aliasing + run tests**

If `Rabbit Hunterfronted/tests/setup.ts` doesn't exist or doesn't import `@testing-library/jest-dom`, write it:

```ts
import '@testing-library/jest-dom/vitest';
```

Run:
```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/services/api.test.ts 2>&1 | tail -10
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add "Rabbit Hunterfronted/services/api.ts" "Rabbit Hunterfronted/services/apiInterceptor.ts" \
        "Rabbit Hunterfronted/tests/services/api.test.ts" "Rabbit Hunterfronted/tests/setup.ts"
git commit -m "feat(frontend): typed fetch wrapper + ApiError + interceptor bus

- apiGet/Post/Patch/Delete return parsed JSON, throw ApiError on non-2xx
- Bearer token auto-attached from window.__API_BEARER_TOKEN__
- apiInterceptor: pub-sub for AppShell toast on 401/403

6 unit tests."
```

---

### Task 5: Zustand UI store

**Files:**
- Create: `Rabbit Hunterfronted/services/store.ts`
- Create: `Rabbit Hunterfronted/tests/services/store.test.ts`

- [ ] **Step 1: Write failing test `Rabbit Hunterfronted/tests/services/store.test.ts`**

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { useUIStore } from '@/services/store';

describe('UIStore', () => {
  beforeEach(() => {
    // reset by re-setting all fields to initial via setState
    useUIStore.setState({
      sidebarCollapsed: false,
      expandedSignalIds: new Set(),
      selectedSymbolForChart: null,
      recentWsEvents: [],
      systemMode: null,
      effectiveAiProvider: null,
      themePreference: 'auto',
      klineInterval: '15m',
    });
  });

  it('toggleSidebar flips bool', () => {
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(true);
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
  });

  it('toggleSignalExpanded adds and removes id', () => {
    useUIStore.getState().toggleSignalExpanded(42);
    expect(useUIStore.getState().expandedSignalIds.has(42)).toBe(true);
    useUIStore.getState().toggleSignalExpanded(42);
    expect(useUIStore.getState().expandedSignalIds.has(42)).toBe(false);
  });

  it('pushWsEvent appends and caps queue at 20', () => {
    for (let i = 0; i < 25; i++) {
      useUIStore.getState().pushWsEvent({ type: 'ping', ts: i } as any);
    }
    expect(useUIStore.getState().recentWsEvents.length).toBe(20);
    expect(useUIStore.getState().recentWsEvents[0]).toMatchObject({ ts: 5 });
  });

  it('popWsEvent removes oldest', () => {
    useUIStore.getState().pushWsEvent({ type: 'ping', ts: 1 } as any);
    useUIStore.getState().pushWsEvent({ type: 'ping', ts: 2 } as any);
    useUIStore.getState().popWsEvent();
    expect(useUIStore.getState().recentWsEvents.length).toBe(1);
    expect(useUIStore.getState().recentWsEvents[0]).toMatchObject({ ts: 2 });
  });

  it('setSystemMode updates value', () => {
    useUIStore.getState().setSystemMode('LIVE');
    expect(useUIStore.getState().systemMode).toBe('LIVE');
  });
});
```

- [ ] **Step 2: Run, expect 5 fail**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/services/store.test.ts 2>&1 | tail -10
```

- [ ] **Step 3: Write `Rabbit Hunterfronted/services/store.ts`**

```ts
import { create } from 'zustand';
import type { Mode, AIProvider, WsEvent, Interval } from '../types';

interface UIState {
  sidebarCollapsed: boolean;
  expandedSignalIds: Set<number>;
  selectedSymbolForChart: string | null;
  recentWsEvents: WsEvent[];
  systemMode: Mode | null;
  effectiveAiProvider: AIProvider | null;
  themePreference: 'auto' | 'dark';
  klineInterval: Interval;

  toggleSidebar: () => void;
  toggleSignalExpanded: (id: number) => void;
  setSelectedSymbol: (sym: string | null) => void;
  pushWsEvent: (ev: WsEvent) => void;
  popWsEvent: () => void;
  setSystemMode: (m: Mode) => void;
  setEffectiveAiProvider: (p: AIProvider | null) => void;
  setKlineInterval: (i: Interval) => void;
}

const MAX_WS_QUEUE = 20;

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  expandedSignalIds: new Set(),
  selectedSymbolForChart: null,
  recentWsEvents: [],
  systemMode: null,
  effectiveAiProvider: null,
  themePreference: 'auto',
  klineInterval: '15m',

  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  toggleSignalExpanded: (id) =>
    set((s) => {
      const next = new Set(s.expandedSignalIds);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { expandedSignalIds: next };
    }),

  setSelectedSymbol: (sym) => set({ selectedSymbolForChart: sym }),

  pushWsEvent: (ev) =>
    set((s) => {
      const next = [...s.recentWsEvents, ev];
      while (next.length > MAX_WS_QUEUE) next.shift();
      return { recentWsEvents: next };
    }),

  popWsEvent: () =>
    set((s) => ({ recentWsEvents: s.recentWsEvents.slice(1) })),

  setSystemMode: (m) => set({ systemMode: m }),
  setEffectiveAiProvider: (p) => set({ effectiveAiProvider: p }),
  setKlineInterval: (i) => set({ klineInterval: i }),
}));
```

- [ ] **Step 4: Run tests**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/services/store.test.ts 2>&1 | tail -10
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add "Rabbit Hunterfronted/services/store.ts" "Rabbit Hunterfronted/tests/services/store.test.ts"
git commit -m "feat(frontend): Zustand UI store (no server state)

- sidebar / expanded signals / WS event queue (max 20) / system mode mirror
- pure setters, no derived state
- 5 unit tests"
```

---

### Task 6: WebSocket hook + system-mode hook

**Files:**
- Create: `Rabbit Hunterfronted/hooks/useV5WebSocket.ts`
- Create: `Rabbit Hunterfronted/hooks/useSystemMode.ts`
- Create: `Rabbit Hunterfronted/tests/hooks/useV5WebSocket.test.ts`

- [ ] **Step 1: Write failing test `Rabbit Hunterfronted/tests/hooks/useV5WebSocket.test.ts`**

```ts
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { Server, WebSocket as MockWS } from 'mock-socket';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useV5WebSocket } from '@/hooks/useV5WebSocket';
import { useUIStore } from '@/services/store';

const WS_URL = 'ws://localhost/ws/v5';

function wrapper(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

describe('useV5WebSocket', () => {
  let server: Server;
  let originalWS: typeof WebSocket;

  beforeEach(() => {
    originalWS = globalThis.WebSocket;
    (globalThis as any).WebSocket = MockWS;
    server = new Server(WS_URL);
    useUIStore.setState({ recentWsEvents: [] });
  });

  afterEach(() => {
    server.stop();
    (globalThis as any).WebSocket = originalWS;
  });

  it('connects and reports healthy after open', async () => {
    const qc = new QueryClient();
    const { result } = renderHook(() => useV5WebSocket(WS_URL), { wrapper: wrapper(qc) });
    await waitFor(() => expect(result.current.connected).toBe(true), { timeout: 1000 });
  });

  it('pushes received event into UI store', async () => {
    const qc = new QueryClient();
    server.on('connection', (sock) => {
      sock.send(JSON.stringify({
        type: 'position_opened', symbol: 'H/USDT', side: 'SHORT',
        entry: 0.166, sl: 0.169, tp: 0.162, size_usdt: 15,
        position_id: 7, strategy_id: 'v5_rsi_macd', mode: 'SHADOW',
      }));
    });
    renderHook(() => useV5WebSocket(WS_URL), { wrapper: wrapper(qc) });
    await waitFor(() =>
      expect(useUIStore.getState().recentWsEvents.length).toBeGreaterThan(0)
    , { timeout: 1000 });
    expect(useUIStore.getState().recentWsEvents[0].type).toBe('position_opened');
  });

  it('invalidates positions query on position_opened', async () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    server.on('connection', (sock) => {
      sock.send(JSON.stringify({
        type: 'position_opened', symbol: 'H/USDT', side: 'SHORT',
        entry: 0.166, sl: 0.169, tp: 0.162, size_usdt: 15,
        position_id: 7, strategy_id: 'v5_rsi_macd', mode: 'SHADOW',
      }));
    });
    renderHook(() => useV5WebSocket(WS_URL), { wrapper: wrapper(qc) });
    await waitFor(() => expect(spy).toHaveBeenCalled(), { timeout: 1000 });
    const calls = spy.mock.calls.map(c => (c[0] as any).queryKey?.[1]);
    expect(calls).toContain('active');
  });
});
```

- [ ] **Step 2: Run, expect fails**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/hooks/useV5WebSocket.test.ts 2>&1 | tail -15
```

- [ ] **Step 3: Write `Rabbit Hunterfronted/hooks/useV5WebSocket.ts`**

```ts
import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useUIStore } from '../services/store';
import type { WsEvent } from '../types';

const HEARTBEAT_MS = 30_000;
const SILENCE_TIMEOUT_MS = 60_000;
const BACKOFF_STEPS = [1000, 2000, 4000, 8000, 16000, 30000];

interface Status {
  connected: boolean;
  unhealthyCount: number;
  lastReceivedAt: number | null;
}

export function useV5WebSocket(url: string): Status {
  const qc = useQueryClient();
  const pushWsEvent = useUIStore((s) => s.pushWsEvent);
  const setEffectiveAi = useUIStore((s) => s.setEffectiveAiProvider);

  const [status, setStatus] = useState<Status>({
    connected: false,
    unhealthyCount: 0,
    lastReceivedAt: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const watchdogRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const attemptRef = useRef<number>(0);
  const lastReceivedRef = useRef<number>(Date.now());
  const teardownRef = useRef<boolean>(false);

  useEffect(() => {
    teardownRef.current = false;

    const dispatchInvalidate = (ev: WsEvent) => {
      switch (ev.type) {
        case 'position_opened':
        case 'position_closed':
        case 'position_extended':
          qc.invalidateQueries({ queryKey: ['v5', 'active'] });
          qc.invalidateQueries({ queryKey: ['v5', 'history'] });
          qc.invalidateQueries({ queryKey: ['v5', 'dashboard'] });
          break;
        case 'ai_health':
          qc.invalidateQueries({ queryKey: ['v5', 'ai'] });
          setEffectiveAi((ev as any).provider ?? null);
          break;
        case 'scoring_stalled':
          // surface via toast; no invalidate
          break;
      }
    };

    const connect = () => {
      if (teardownRef.current) return;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        lastReceivedRef.current = Date.now();
        setStatus((s) => ({ ...s, connected: true, unhealthyCount: 0 }));
        if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);
        heartbeatTimerRef.current = setInterval(() => {
          try {
            ws.send(JSON.stringify({ type: 'ping', ts: Date.now() }));
          } catch { /* ignore */ }
        }, HEARTBEAT_MS);

        if (watchdogRef.current) clearInterval(watchdogRef.current);
        watchdogRef.current = setInterval(() => {
          if (Date.now() - lastReceivedRef.current > SILENCE_TIMEOUT_MS) {
            try { ws.close(); } catch { /* ignore */ }
          }
        }, 10_000);
      };

      ws.onmessage = (msg) => {
        lastReceivedRef.current = Date.now();
        setStatus((s) => ({ ...s, lastReceivedAt: lastReceivedRef.current }));
        let payload: WsEvent | null = null;
        try {
          payload = JSON.parse(msg.data);
        } catch {
          return;
        }
        if (!payload || typeof payload !== 'object') return;
        if (payload.type === 'ping') return;   // server keep-alive
        pushWsEvent(payload);
        dispatchInvalidate(payload);
      };

      ws.onclose = () => {
        setStatus((s) => ({ ...s, connected: false, unhealthyCount: s.unhealthyCount + 1 }));
        if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);
        if (watchdogRef.current) clearInterval(watchdogRef.current);
        if (teardownRef.current) return;
        const idx = Math.min(attemptRef.current, BACKOFF_STEPS.length - 1);
        const delay = BACKOFF_STEPS[idx];
        attemptRef.current += 1;
        reconnectTimerRef.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        // onclose will fire next — let it handle backoff
      };
    };

    connect();

    return () => {
      teardownRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);
      if (watchdogRef.current) clearInterval(watchdogRef.current);
      try { wsRef.current?.close(); } catch { /* ignore */ }
    };
  }, [url, qc, pushWsEvent, setEffectiveAi]);

  return status;
}
```

- [ ] **Step 4: Write `Rabbit Hunterfronted/hooks/useSystemMode.ts`**

```ts
import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { apiGet } from '../services/api';
import { useUIStore } from '../services/store';
import type { SettingsResponse, Mode } from '../types';

export function useSystemMode(): { mode: Mode | null; isLoading: boolean } {
  const q = useQuery<SettingsResponse>({
    queryKey: ['v5', 'settings'],
    queryFn: () => apiGet<SettingsResponse>('/api/v5/settings'),
    staleTime: 60_000,
  });
  const setSystemMode = useUIStore((s) => s.setSystemMode);

  useEffect(() => {
    if (q.data?.system_mode) setSystemMode(q.data.system_mode);
  }, [q.data?.system_mode, setSystemMode]);

  return {
    mode: q.data?.system_mode ?? null,
    isLoading: q.isLoading,
  };
}
```

- [ ] **Step 5: Run tests**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/hooks/useV5WebSocket.test.ts 2>&1 | tail -10
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add "Rabbit Hunterfronted/hooks/useV5WebSocket.ts" \
        "Rabbit Hunterfronted/hooks/useSystemMode.ts" \
        "Rabbit Hunterfronted/tests/hooks/useV5WebSocket.test.ts"
git commit -m "feat(frontend): /ws/v5 client hook + system-mode mirror

- 30s client ping, 60s silence → reconnect
- exponential backoff 1s→30s, max
- dispatches React Query invalidate on position/AI events
- useSystemMode hydrates Zustand from /api/v5/settings

3 RTL tests using mock-socket."
```

---

## Phase 2: API Hooks

### Task 7: 10 React-Query API hooks

**Files:**
- Create: `Rabbit Hunterfronted/hooks/api/useV5Signals.ts`
- Create: `Rabbit Hunterfronted/hooks/api/useV5ActivePositions.ts`
- Create: `Rabbit Hunterfronted/hooks/api/useV5OrderHistory.ts`
- Create: `Rabbit Hunterfronted/hooks/api/useV5Dashboard.ts`
- Create: `Rabbit Hunterfronted/hooks/api/useV5AIStatus.ts`
- Create: `Rabbit Hunterfronted/hooks/api/useV5StrategyConfig.ts`
- Create: `Rabbit Hunterfronted/hooks/api/useV5Settings.ts`
- Create: `Rabbit Hunterfronted/hooks/api/useV5ManualOrder.ts`
- Create: `Rabbit Hunterfronted/hooks/api/useV5Klines.ts`
- Create: `Rabbit Hunterfronted/hooks/api/useV5SymbolEvents.ts`
- Create: `Rabbit Hunterfronted/tests/hooks/useV5Signals.test.ts`
- Create: `Rabbit Hunterfronted/tests/hooks/useV5ManualOrder.test.ts`

- [ ] **Step 1: Write failing tests `Rabbit Hunterfronted/tests/hooks/useV5Signals.test.ts`**

```ts
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useV5Signals } from '@/hooks/api/useV5Signals';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { qc, wrapper: ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children) };
}

describe('useV5Signals', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('fetches /api/v5/signals?limit=50 by default', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ signals: [], count: 0 }), { status: 200 })
    );
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5Signals(50), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect((fetch as any).mock.calls[0][0]).toContain('/api/v5/signals?limit=50');
  });

  it('passes side filter through', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ signals: [], count: 0 }), { status: 200 })
    );
    const { wrapper } = makeWrapper();
    renderHook(() => useV5Signals(50, { side: 'SHORT' }), { wrapper });
    await waitFor(() => expect((fetch as any).mock.calls.length).toBeGreaterThan(0));
    expect((fetch as any).mock.calls[0][0]).toContain('side=SHORT');
  });
});
```

- [ ] **Step 2: Write `Rabbit Hunterfronted/tests/hooks/useV5ManualOrder.test.ts`**

```ts
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useV5ManualOrder } from '@/hooks/api/useV5ManualOrder';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useV5ManualOrder', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('preview hits /preview with body and returns response', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({
        symbol: 'H/USDT', side: 'SHORT', current_price: 0.166,
        indicators: {}, decision: { should_trade: true, side: 'SHORT', reasoning: '', block_reason: null },
        risk_plan: {}, ai_result: { execute: true, sl_multiplier: 1, tp_multiplier: 1,
          size_multiplier: 1, confidence: 0.7, reasoning: 'ok' },
        rag_cases: [], rag_summary: null,
      }), { status: 200 })
    );
    const { result } = renderHook(() => useV5ManualOrder(), { wrapper: makeWrapper() });
    let preview: any;
    await act(async () => {
      preview = await result.current.preview.mutateAsync({ symbol: 'H/USDT', side: 'SHORT', size_usdt: 15 });
    });
    expect(preview.symbol).toBe('H/USDT');
    expect((fetch as any).mock.calls[0][0]).toContain('/manual-order/preview');
    expect((fetch as any).mock.calls[0][1].method).toBe('POST');
  });

  it('execute hits /execute and returns position_id', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({
        position_id: 42, symbol: 'H/USDT', side: 'SHORT',
        entry_price: 0.166, sl_price: 0.169, tp_price: 0.162,
        size_usdt: 15, strategy_id: 'v5_manual',
      }), { status: 200 })
    );
    const { result } = renderHook(() => useV5ManualOrder(), { wrapper: makeWrapper() });
    let out: any;
    await act(async () => {
      out = await result.current.execute.mutateAsync({
        symbol: 'H/USDT', side: 'SHORT', size_usdt: 15,
        sl_multiplier: 1, tp_multiplier: 1, size_multiplier: 1,
      });
    });
    expect(out.position_id).toBe(42);
    expect((fetch as any).mock.calls[0][0]).toContain('/manual-order/execute');
  });
});
```

- [ ] **Step 3: Run, expect fails**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/hooks/useV5Signals.test.ts tests/hooks/useV5ManualOrder.test.ts 2>&1 | tail -15
```

- [ ] **Step 4: Write all 10 hooks**

`Rabbit Hunterfronted/hooks/api/useV5Signals.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { V5SignalsResponse, Side } from '../../types';

interface Filter {
  side?: Side | null;
  showExecutedOnly?: boolean;
  blockReason?: string | null;
  since?: string | null;
}

export function useV5Signals(limit = 50, filter: Filter = {}) {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  if (filter.side) params.set('side', filter.side);
  if (filter.showExecutedOnly) params.set('executed_only', 'true');
  if (filter.blockReason) params.set('block_reason', filter.blockReason);
  if (filter.since) params.set('since', filter.since);
  const qs = params.toString();
  return useQuery<V5SignalsResponse>({
    queryKey: ['v5', 'signals', filter, limit],
    queryFn: () => apiGet<V5SignalsResponse>(`/api/v5/signals?${qs}`),
    refetchInterval: 10_000,
    staleTime: 5_000,
  });
}
```

`Rabbit Hunterfronted/hooks/api/useV5ActivePositions.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { V5PositionsResponse, V5Position } from '../../types';

interface CombinedActive {
  live: V5Position[];
  paper: V5Position[];
  combined: V5Position[];
  total: number;
}

export function useV5ActivePositions() {
  return useQuery<CombinedActive>({
    queryKey: ['v5', 'active'],
    queryFn: async () => {
      const [live, paper] = await Promise.all([
        apiGet<V5PositionsResponse>('/api/v5/positions?status=OPEN'),
        apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=OPEN'),
      ]);
      return {
        live: live.positions,
        paper: paper.positions,
        combined: [...live.positions, ...paper.positions],
        total: live.count + paper.count,
      };
    },
    refetchInterval: 5_000,
  });
}
```

`Rabbit Hunterfronted/hooks/api/useV5OrderHistory.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { V5PositionsResponse, V5Position } from '../../types';

export function useV5OrderHistory(limit = 200) {
  return useQuery<V5Position[]>({
    queryKey: ['v5', 'history', limit],
    queryFn: async () => {
      const [live, paper] = await Promise.all([
        apiGet<V5PositionsResponse>(`/api/v5/positions?status=CLOSED&limit=${limit}`),
        apiGet<V5PositionsResponse>(`/api/v5/paper-positions?status=CLOSED&limit=${limit}`),
      ]);
      const merged = [...live.positions, ...paper.positions];
      merged.sort((a, b) => (b.exit_time || '').localeCompare(a.exit_time || ''));
      return merged.slice(0, limit);
    },
    refetchInterval: 30_000,
  });
}
```

`Rabbit Hunterfronted/hooks/api/useV5Dashboard.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { V5SignalsResponse, V5PositionsResponse, V5Position } from '../../types';

export interface DashboardData {
  signals_24h: number;
  signals_passed_and: number;
  signals_executed: number;
  signals_block_counts: Record<string, number>;
  win_rate_24h: number;
  pnl_total_usdt: number;
  pnl_total_pct: number;
  avg_holding_minutes: number;
  active_count: number;
  closed_24h: V5Position[];
}

export function useV5Dashboard() {
  return useQuery<DashboardData>({
    queryKey: ['v5', 'dashboard'],
    queryFn: async () => {
      const [signals, history, active] = await Promise.all([
        apiGet<V5SignalsResponse>('/api/v5/signals?limit=2000'),
        apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=CLOSED&limit=500'),
        apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=OPEN'),
      ]);

      const cutoff = Date.now() - 24 * 60 * 60 * 1000;
      const in24 = (iso: string | null) => iso ? new Date(iso).getTime() >= cutoff : false;

      const s24 = signals.signals.filter(s => in24(s.created_at));
      const passedAnd = s24.filter(s => s.should_trade);
      const executed = s24.filter(s => s.executed);

      const blockCounts: Record<string, number> = {};
      for (const s of s24) {
        const k = s.block_reason || (s.executed ? 'EXECUTED' : (s.should_trade ? 'NONE' : 'OTHER'));
        blockCounts[k] = (blockCounts[k] ?? 0) + 1;
      }

      const closed24 = history.positions.filter(p => in24(p.exit_time));
      const wins = closed24.filter(p => (p.pnl_percent ?? 0) > 0).length;
      const winRate = closed24.length > 0 ? wins / closed24.length : 0;
      const pnlSum = closed24.reduce((acc, p) => acc + (p.pnl_usdt ?? 0), 0);
      const pnlPctSum = closed24.reduce((acc, p) => acc + (p.pnl_percent ?? 0), 0);
      const avgHold = closed24.length > 0
        ? closed24.reduce((acc, p) => {
            if (!p.entry_time || !p.exit_time) return acc;
            const mins = (new Date(p.exit_time).getTime() - new Date(p.entry_time).getTime()) / 60_000;
            return acc + mins;
          }, 0) / closed24.length
        : 0;

      return {
        signals_24h: s24.length,
        signals_passed_and: passedAnd.length,
        signals_executed: executed.length,
        signals_block_counts: blockCounts,
        win_rate_24h: winRate,
        pnl_total_usdt: pnlSum,
        pnl_total_pct: pnlPctSum,
        avg_holding_minutes: avgHold,
        active_count: active.count,
        closed_24h: closed24,
      };
    },
    refetchInterval: 30_000,
  });
}
```

`Rabbit Hunterfronted/hooks/api/useV5AIStatus.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { AIStatusResponse, AIDecisionsResponse } from '../../types';

export function useV5AIStatus() {
  return useQuery<AIStatusResponse>({
    queryKey: ['v5', 'ai'],
    queryFn: () => apiGet<AIStatusResponse>('/api/v5/ai/status'),
    refetchInterval: 60_000,
  });
}

export function useV5AIDecisions(limit = 20) {
  return useQuery<AIDecisionsResponse>({
    queryKey: ['v5', 'ai', 'decisions', limit],
    queryFn: () => apiGet<AIDecisionsResponse>(`/api/v5/ai/decisions?limit=${limit}`),
    refetchInterval: 30_000,
  });
}
```

`Rabbit Hunterfronted/hooks/api/useV5StrategyConfig.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPatch, apiPost } from '../../services/api';
import type {
  StrategyConfigResponse, StrategyConfigPatchRequest, StrategyConfigPreviewResponse,
} from '../../types';

export function useV5StrategyConfig() {
  const qc = useQueryClient();
  const query = useQuery<StrategyConfigResponse>({
    queryKey: ['v5', 'config'],
    queryFn: () => apiGet<StrategyConfigResponse>('/api/v5/strategy-config'),
  });
  const patch = useMutation({
    mutationFn: (body: StrategyConfigPatchRequest) =>
      apiPatch<StrategyConfigResponse>('/api/v5/strategy-config', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['v5', 'config'] }),
  });
  const preview = useMutation({
    mutationFn: (body: StrategyConfigPatchRequest) =>
      apiPost<StrategyConfigPreviewResponse>('/api/v5/strategy-config/preview', body),
  });
  return { query, patch, preview };
}
```

`Rabbit Hunterfronted/hooks/api/useV5Settings.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPatch } from '../../services/api';
import type { SettingsResponse, SettingsPatchRequest } from '../../types';

export function useV5Settings() {
  const qc = useQueryClient();
  const query = useQuery<SettingsResponse>({
    queryKey: ['v5', 'settings'],
    queryFn: () => apiGet<SettingsResponse>('/api/v5/settings'),
  });
  const patch = useMutation({
    mutationFn: (body: SettingsPatchRequest) =>
      apiPatch<SettingsResponse>('/api/v5/settings', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['v5', 'settings'] }),
  });
  return { query, patch };
}
```

`Rabbit Hunterfronted/hooks/api/useV5ManualOrder.ts`:

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../../services/api';
import type {
  ManualOrderPreviewRequest, ManualOrderPreviewResponse,
  ManualOrderExecuteRequest, ManualOrderExecuteResponse,
} from '../../types';

export function useV5ManualOrder() {
  const qc = useQueryClient();
  const preview = useMutation({
    mutationFn: (body: ManualOrderPreviewRequest) =>
      apiPost<ManualOrderPreviewResponse>('/api/v5/manual-order/preview', body),
  });
  const execute = useMutation({
    mutationFn: (body: ManualOrderExecuteRequest) =>
      apiPost<ManualOrderExecuteResponse>('/api/v5/manual-order/execute', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['v5', 'active'] });
      qc.invalidateQueries({ queryKey: ['v5', 'history'] });
    },
  });
  return { preview, execute };
}
```

`Rabbit Hunterfronted/hooks/api/useV5Klines.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { KlinesResponse, Interval } from '../../types';

function encodeSymbol(sym: string): string {
  return sym.replace('/', '_');
}

export function useV5Klines(symbol: string | null, interval: Interval = '15m', limit = 200) {
  return useQuery<KlinesResponse>({
    queryKey: ['v5', 'klines', symbol, interval, limit],
    queryFn: () => apiGet<KlinesResponse>(
      `/api/v5/klines/${encodeSymbol(symbol!)}?interval=${interval}&limit=${limit}`),
    enabled: !!symbol,
    refetchInterval: 15_000,
  });
}
```

`Rabbit Hunterfronted/hooks/api/useV5SymbolEvents.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { SymbolEventsResponse } from '../../types';

function encodeSymbol(sym: string): string {
  return sym.replace('/', '_');
}

export function useV5SymbolEvents(symbol: string | null, limit = 50) {
  return useQuery<SymbolEventsResponse>({
    queryKey: ['v5', 'events', symbol, limit],
    queryFn: () => apiGet<SymbolEventsResponse>(
      `/api/v5/events/${encodeSymbol(symbol!)}?limit=${limit}`),
    enabled: !!symbol,
    refetchInterval: 15_000,
  });
}
```

Add a position-close helper inline next to active-positions:

Append to `Rabbit Hunterfronted/hooks/api/useV5ActivePositions.ts`:

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../../services/api';
import type { ClosePositionRequest, ClosePositionResponse } from '../../types';

export function useV5ClosePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: ClosePositionRequest }) =>
      apiPost<ClosePositionResponse>(`/api/v5/positions/${id}/close`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['v5', 'active'] });
      qc.invalidateQueries({ queryKey: ['v5', 'history'] });
    },
  });
}
```

Adjust the top import in that file to combine: `import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';`

- [ ] **Step 5: Run tests**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/hooks/useV5Signals.test.ts tests/hooks/useV5ManualOrder.test.ts 2>&1 | tail -10
```

Expected: 4 passed.

- [ ] **Step 6: Type-check**

```bash
cd "Rabbit Hunterfronted"
npx tsc --noEmit 2>&1 | grep -E "error|hooks/" | head -20
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add "Rabbit Hunterfronted/hooks/api" "Rabbit Hunterfronted/tests/hooks"
git commit -m "feat(frontend): 10 React-Query hooks for V5 endpoints

- read: signals (10s) / active (5s) / history (30s) / dashboard (30s) /
        ai status+decisions (60s/30s) / klines (15s) / events (15s)
- mutation: strategy-config patch+preview / settings patch /
            manual-order preview+execute / close-position
- query keys: ['v5', <resource>, ...filter]

4 hook tests (signals + manual-order)."
```

---

## Phase 3: Primitives + Shared Components

### Task 8: Primitives suite

**Files (all under `Rabbit Hunterfronted/components/primitives/`):**
- Create: `Card.tsx Badge.tsx ProgressBar.tsx GaugeArc.tsx`
- Create: `ErrorBoundary.tsx Toast.tsx LoadingSkeleton.tsx`
- Create: `Modal.tsx Select.tsx Slider.tsx NumberInput.tsx`
- Create: `VirtualList.tsx`
- Create: `Rabbit Hunterfronted/tests/shared/primitives.test.tsx`

- [ ] **Step 1: Write failing test `Rabbit Hunterfronted/tests/shared/primitives.test.tsx`**

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Card } from '@/components/primitives/Card';
import { Badge } from '@/components/primitives/Badge';
import { ProgressBar } from '@/components/primitives/ProgressBar';
import { Modal } from '@/components/primitives/Modal';
import { NumberInput } from '@/components/primitives/NumberInput';

describe('primitives', () => {
  it('Card renders title and children', () => {
    render(<Card title="Hi"><div>body</div></Card>);
    expect(screen.getByText('Hi')).toBeInTheDocument();
    expect(screen.getByText('body')).toBeInTheDocument();
  });

  it('Badge variant changes background class', () => {
    const { rerender } = render(<Badge variant="long">L</Badge>);
    expect(screen.getByText('L').className).toMatch(/accent-long|bg-/);
    rerender(<Badge variant="short">S</Badge>);
    expect(screen.getByText('S').className).toMatch(/accent-short|bg-/);
  });

  it('ProgressBar clamps value 0-100 and shows label', () => {
    render(<ProgressBar value={120} label="loading" />);
    const bar = screen.getByRole('progressbar');
    expect(bar.getAttribute('aria-valuenow')).toBe('100');
    expect(screen.getByText('loading')).toBeInTheDocument();
  });

  it('Modal shows when open, hides when not', () => {
    const { rerender } = render(
      <Modal open={false} onClose={() => {}}><div>content</div></Modal>
    );
    expect(screen.queryByText('content')).not.toBeInTheDocument();
    rerender(<Modal open onClose={() => {}}><div>content</div></Modal>);
    expect(screen.getByText('content')).toBeInTheDocument();
  });

  it('NumberInput respects min/max and calls onChange', async () => {
    const user = userEvent.setup();
    let val = 50;
    const onChange = (v: number) => { val = v; };
    render(<NumberInput value={50} min={0} max={100} step={1} onChange={onChange} />);
    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    await user.clear(input);
    await user.type(input, '75');
    expect(val).toBe(75);
  });
});
```

- [ ] **Step 2: Run, expect fails**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/shared/primitives.test.tsx 2>&1 | tail -10
```

- [ ] **Step 3: Write primitives**

`Card.tsx`:

```tsx
import React from 'react';

interface CardProps {
  title?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}

export function Card({ title, actions, className = '', children }: CardProps) {
  return (
    <div className={`rounded-md border border-white/10 bg-bg-surface ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          {title && <div className="text-sm font-medium text-white/90">{title}</div>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}
```

`Badge.tsx`:

```tsx
import React from 'react';

type Variant = 'long' | 'short' | 'warn' | 'info' | 'neutral';

const BG: Record<Variant, string> = {
  long: 'bg-accent-long/15 text-accent-long border-accent-long/30',
  short: 'bg-accent-short/15 text-accent-short border-accent-short/30',
  warn: 'bg-accent-warn/15 text-accent-warn border-accent-warn/30',
  info: 'bg-accent-info/15 text-accent-info border-accent-info/30',
  neutral: 'bg-white/5 text-white/70 border-white/10',
};

export function Badge({ variant = 'neutral', children }: { variant?: Variant; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-xs font-mono ${BG[variant]}`}>
      {children}
    </span>
  );
}
```

`ProgressBar.tsx`:

```tsx
import React from 'react';

interface Props {
  value: number;
  max?: number;
  label?: React.ReactNode;
  tone?: 'long' | 'short' | 'warn' | 'info';
}

const TONE: Record<NonNullable<Props['tone']>, string> = {
  long: 'bg-accent-long',
  short: 'bg-accent-short',
  warn: 'bg-accent-warn',
  info: 'bg-accent-info',
};

export function ProgressBar({ value, max = 100, label, tone = 'info' }: Props) {
  const clamped = Math.max(0, Math.min(max, value));
  const pct = max > 0 ? (clamped / max) * 100 : 0;
  return (
    <div className="w-full">
      {label && <div className="mb-1 flex justify-between text-xs text-white/60">
        <span>{label}</span><span className="font-mono">{Math.round(pct)}%</span>
      </div>}
      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={max}
        className="h-2 w-full overflow-hidden rounded-sm bg-white/5"
      >
        <div
          className={`h-full ${TONE[tone]} transition-all duration-base`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
```

`GaugeArc.tsx`:

```tsx
import React from 'react';

interface Props {
  value: number;
  min?: number;
  max?: number;
  thresholds?: { warn?: number; danger?: number };
  label?: React.ReactNode;
  size?: number;
}

export function GaugeArc({ value, min = 0, max = 100, thresholds, label, size = 100 }: Props) {
  const v = Math.max(min, Math.min(max, value));
  const pct = (v - min) / (max - min);
  const angle = pct * 180 - 90;     // -90 to 90
  const radius = size / 2 - 8;
  const cx = size / 2;
  const cy = size / 2;
  const x = cx + radius * Math.cos(((angle - 90) * Math.PI) / 180);
  const y = cy + radius * Math.sin(((angle - 90) * Math.PI) / 180);

  let stroke = '#3B82F6';
  if (thresholds?.danger != null && v >= thresholds.danger) stroke = '#EF4444';
  else if (thresholds?.warn != null && v >= thresholds.warn) stroke = '#F59E0B';

  return (
    <svg width={size} height={size * 0.6} viewBox={`0 0 ${size} ${size * 0.6}`}>
      <path
        d={`M ${8} ${cy} A ${radius} ${radius} 0 0 1 ${size - 8} ${cy}`}
        stroke="rgba(255,255,255,0.1)" strokeWidth={6} fill="none" strokeLinecap="round"
      />
      <path
        d={`M ${8} ${cy} A ${radius} ${radius} 0 0 ${pct > 0.5 ? 1 : 0} ${x} ${y}`}
        stroke={stroke} strokeWidth={6} fill="none" strokeLinecap="round"
      />
      <text x={cx} y={cy - 6} textAnchor="middle" fill="white" fontSize={size / 6} fontFamily="JetBrains Mono">
        {v.toFixed(1)}
      </text>
      {label && (
        <text x={cx} y={cy + 8} textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize={size / 12}>
          {label}
        </text>
      )}
    </svg>
  );
}
```

`Modal.tsx`:

```tsx
import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';

interface Props {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  children: React.ReactNode;
  maxWidth?: string;
}

export function Modal({ open, onClose, title, children, maxWidth = '480px' }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="w-full rounded-md border border-white/10 bg-bg-surface shadow-lg"
        style={{ maxWidth }}
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <div className="border-b border-white/10 px-4 py-3 text-sm font-medium">
            {title}
          </div>
        )}
        <div className="p-4">{children}</div>
      </div>
    </div>,
    document.body
  );
}
```

`Select.tsx`:

```tsx
import React from 'react';

interface Option { value: string; label: string }
interface Props {
  value: string | null;
  options: Option[];
  onChange: (v: string) => void;
  className?: string;
  disabled?: boolean;
}

export function Select({ value, options, onChange, className = '', disabled }: Props) {
  return (
    <select
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className={`rounded-sm border border-white/10 bg-bg-base px-2 py-1 text-sm text-white outline-none focus:border-accent-info ${className}`}
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}
```

`Slider.tsx`:

```tsx
import React from 'react';

interface Props {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  className?: string;
}

export function Slider({ value, min, max, step = 1, onChange, className = '' }: Props) {
  return (
    <input
      type="range"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={(e) => onChange(Number(e.target.value))}
      className={`h-2 w-full appearance-none rounded-sm bg-white/10 outline-none accent-accent-info ${className}`}
    />
  );
}
```

`NumberInput.tsx`:

```tsx
import React from 'react';

interface Props {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
  className?: string;
}

export function NumberInput({ value, min, max, step = 0.01, onChange, className = '' }: Props) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={(e) => {
        const n = Number(e.target.value);
        if (Number.isNaN(n)) return;
        const clamped = Math.max(min ?? -Infinity, Math.min(max ?? Infinity, n));
        onChange(clamped);
      }}
      className={`w-24 rounded-sm border border-white/10 bg-bg-base px-2 py-1 text-right font-mono text-sm text-white outline-none focus:border-accent-info ${className}`}
    />
  );
}
```

`LoadingSkeleton.tsx`:

```tsx
import React from 'react';

export function LoadingSkeleton({ rows = 3, className = '' }: { rows?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-4 w-full animate-pulse rounded-sm bg-white/5" />
      ))}
    </div>
  );
}
```

`ErrorBoundary.tsx`:

```tsx
import React from 'react';

interface State { error: Error | null }
interface Props { children: React.ReactNode; fallback?: (err: Error) => React.ReactNode }

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };
  static getDerivedStateFromError(error: Error): State {
    return { error };
  }
  componentDidCatch(error: Error) {
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error);
  }
  reset = () => this.setState({ error: null });
  render() {
    const { error } = this.state;
    if (error) {
      if (this.props.fallback) return this.props.fallback(error);
      return (
        <div className="rounded-md border border-accent-short/30 bg-accent-short/10 p-4 text-sm text-accent-short">
          本页加载失败:{error.message}
          <button onClick={this.reset} className="ml-3 underline">重试</button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

`Toast.tsx`:

```tsx
import React, { useEffect } from 'react';

export type ToastTone = 'info' | 'success' | 'warn' | 'error';

interface Props {
  message: string;
  tone?: ToastTone;
  durationMs?: number;
  onDismiss: () => void;
}

const TONE: Record<ToastTone, string> = {
  info: 'border-accent-info/40 bg-accent-info/10 text-accent-info',
  success: 'border-accent-long/40 bg-accent-long/10 text-accent-long',
  warn: 'border-accent-warn/40 bg-accent-warn/10 text-accent-warn',
  error: 'border-accent-short/40 bg-accent-short/10 text-accent-short',
};

export function Toast({ message, tone = 'info', durationMs = 4000, onDismiss }: Props) {
  useEffect(() => {
    const t = setTimeout(onDismiss, durationMs);
    return () => clearTimeout(t);
  }, [durationMs, onDismiss]);
  return (
    <div className={`rounded-md border px-3 py-2 text-sm shadow-md ${TONE[tone]}`}>
      {message}
    </div>
  );
}
```

`VirtualList.tsx`:

```tsx
import React, { useRef, useState, useEffect } from 'react';

interface Props<T> {
  items: T[];
  itemHeight: number;
  height: number;
  renderItem: (item: T, index: number) => React.ReactNode;
  overscan?: number;
  className?: string;
}

export function VirtualList<T>({ items, itemHeight, height, renderItem, overscan = 4, className = '' }: Props<T>) {
  const ref = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onScroll = () => setScrollTop(el.scrollTop);
    el.addEventListener('scroll', onScroll);
    return () => el.removeEventListener('scroll', onScroll);
  }, []);
  const start = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
  const end = Math.min(items.length, Math.ceil((scrollTop + height) / itemHeight) + overscan);
  const visible = items.slice(start, end);
  return (
    <div ref={ref} className={`overflow-auto ${className}`} style={{ height }}>
      <div style={{ height: items.length * itemHeight, position: 'relative' }}>
        <div style={{ transform: `translateY(${start * itemHeight}px)` }}>
          {visible.map((it, i) => (
            <div key={start + i} style={{ height: itemHeight }}>
              {renderItem(it, start + i)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/shared/primitives.test.tsx 2>&1 | tail -10
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add "Rabbit Hunterfronted/components/primitives" "Rabbit Hunterfronted/tests/shared/primitives.test.tsx"
git commit -m "feat(frontend): primitives (Card/Badge/ProgressBar/GaugeArc/Modal/Slider/NumberInput/LoadingSkeleton/Toast/ErrorBoundary/Select/VirtualList)

- Tailwind-driven, design-tokens-aligned
- ErrorBoundary catches per-page; Modal portals to body + Escape close
- VirtualList covers signal/history tables

5 primitives tests."
```

---

### Task 9: Shared composite components (no chart)

**Files (all under `Rabbit Hunterfronted/components/shared/`):**
- Create: `IndicatorGauges.tsx`
- Create: `KpiCard.tsx`
- Create: `SignalFunnel.tsx`
- Create: `RecentAIDecisions.tsx`
- Create: `ActivePositionCard.tsx`
- Create: `Rabbit Hunterfronted/tests/shared/IndicatorGauges.test.tsx`
- Create: `Rabbit Hunterfronted/tests/shared/ActivePositionCard.test.tsx`

- [ ] **Step 1: Write tests**

`Rabbit Hunterfronted/tests/shared/IndicatorGauges.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IndicatorGauges } from '@/components/shared/IndicatorGauges';

describe('IndicatorGauges', () => {
  it('renders RSI value and tone label when overbought', () => {
    render(<IndicatorGauges
      rsi_15m={72.1} rsi_4h={68} macd_hist_15m={-0.0012}
      macd_hist_prev_15m={0.0008} atr_15m={0.0015} />);
    expect(screen.getByText(/72\.1/)).toBeInTheDocument();
    expect(screen.getByText(/超买/)).toBeInTheDocument();
  });

  it('shows oversold tone when RSI < 30', () => {
    render(<IndicatorGauges
      rsi_15m={22.5} rsi_4h={32} macd_hist_15m={0.0005}
      macd_hist_prev_15m={-0.0004} atr_15m={0.001} />);
    expect(screen.getByText(/超卖/)).toBeInTheDocument();
  });

  it('flags MACD bullish cross when hist flips negative→positive', () => {
    render(<IndicatorGauges
      rsi_15m={45} rsi_4h={50} macd_hist_15m={0.0005}
      macd_hist_prev_15m={-0.0004} atr_15m={0.001} />);
    expect(screen.getByText(/金叉/)).toBeInTheDocument();
  });

  it('flags MACD bearish cross when hist flips positive→negative', () => {
    render(<IndicatorGauges
      rsi_15m={70} rsi_4h={50} macd_hist_15m={-0.0005}
      macd_hist_prev_15m={0.0004} atr_15m={0.001} />);
    expect(screen.getByText(/死叉/)).toBeInTheDocument();
  });
});
```

`Rabbit Hunterfronted/tests/shared/ActivePositionCard.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ActivePositionCard } from '@/components/shared/ActivePositionCard';
import type { V5Position } from '@/types';

const POS: V5Position = {
  id: 7, symbol: 'H/USDT', side: 'SHORT', status: 'OPEN',
  entry_price: 0.1665, current_price: 0.1641,
  stop_loss: 0.1715, take_profit: 0.1592,
  position_size_usdt: 15, leverage: 10,
  entry_time: '2026-06-12T09:48:00+00:00',
  exit_time: null, exit_price: null, exit_reason: null,
  pnl_percent: 1.44, pnl_usdt: 0.22,
  entry_rsi_15m: 72, entry_macd_hist_15m: -0.0006,
  extension_count: 0, target_close_at: null, ai_reason: 'short setup',
  strategy_id: 'v5_rsi_macd',
};

describe('ActivePositionCard', () => {
  it('renders symbol, side, entry, sl, tp', () => {
    render(<ActivePositionCard position={POS} onClose={() => {}} onChart={() => {}} />);
    expect(screen.getByText('H/USDT')).toBeInTheDocument();
    expect(screen.getByText(/SHORT/)).toBeInTheDocument();
    expect(screen.getByText(/0\.1665/)).toBeInTheDocument();
    expect(screen.getByText(/0\.1715/)).toBeInTheDocument();
    expect(screen.getByText(/0\.1592/)).toBeInTheDocument();
  });

  it('positive PnL displays in long tone for SHORT going down', () => {
    render(<ActivePositionCard position={POS} onClose={() => {}} onChart={() => {}} />);
    expect(screen.getByText(/\+1\.44%/)).toBeInTheDocument();
  });

  it('calls onClose when 立即平 clicked', () => {
    const cb = vi.fn();
    render(<ActivePositionCard position={POS} onClose={cb} onChart={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /立即平/ }));
    expect(cb).toHaveBeenCalledWith(POS);
  });
});
```

- [ ] **Step 2: Run, expect fail**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/shared/IndicatorGauges.test.tsx tests/shared/ActivePositionCard.test.tsx 2>&1 | tail -10
```

- [ ] **Step 3: Write shared components**

`Rabbit Hunterfronted/components/shared/IndicatorGauges.tsx`:

```tsx
import React from 'react';
import { GaugeArc } from '../primitives/GaugeArc';
import { Badge } from '../primitives/Badge';

interface Props {
  rsi_15m: number;
  rsi_4h: number | null;
  macd_hist_15m: number;
  macd_hist_prev_15m: number;
  atr_15m: number;
}

export function IndicatorGauges({ rsi_15m, rsi_4h, macd_hist_15m, macd_hist_prev_15m, atr_15m }: Props) {
  const rsiTone = rsi_15m >= 70 ? '超买' : rsi_15m <= 30 ? '超卖' : '中性';
  const rsiBadge: 'short' | 'long' | 'neutral' = rsi_15m >= 70 ? 'short' : rsi_15m <= 30 ? 'long' : 'neutral';

  const flipped = (macd_hist_prev_15m < 0 && macd_hist_15m > 0)
    ? '金叉'
    : (macd_hist_prev_15m > 0 && macd_hist_15m < 0)
    ? '死叉'
    : null;

  return (
    <div className="flex gap-4">
      <div className="flex flex-col items-center">
        <GaugeArc value={rsi_15m} min={0} max={100} thresholds={{ warn: 70, danger: 80 }} label="RSI 15m" size={120} />
        <Badge variant={rsiBadge}>{rsiTone}</Badge>
      </div>
      <div className="flex flex-col items-center justify-center text-xs font-mono">
        <div className="text-white/60">MACD hist 15m</div>
        <div className="text-base text-white">{macd_hist_15m.toFixed(4)}</div>
        <div className="text-white/50">prev {macd_hist_prev_15m.toFixed(4)}</div>
        {flipped && <Badge variant={flipped === '金叉' ? 'long' : 'short'}>{flipped}拐点</Badge>}
      </div>
      <div className="flex flex-col items-center justify-center text-xs font-mono">
        <div className="text-white/60">4h 参考</div>
        <div className="text-base text-white">RSI {rsi_4h?.toFixed(1) ?? '—'}</div>
        <div className="text-white/50">ATR {atr_15m.toFixed(4)}</div>
      </div>
    </div>
  );
}
```

`Rabbit Hunterfronted/components/shared/KpiCard.tsx`:

```tsx
import React from 'react';

interface Props {
  title: string;
  value: React.ReactNode;
  unit?: string;
  deltaVsYesterday?: { value: number; positiveIsGood?: boolean };
  sparkLine?: number[];
}

export function KpiCard({ title, value, unit, deltaVsYesterday }: Props) {
  let deltaColor = 'text-white/40';
  let deltaSign = '';
  if (deltaVsYesterday) {
    const isUp = deltaVsYesterday.value > 0;
    const good = deltaVsYesterday.positiveIsGood ?? true;
    deltaColor = isUp === good ? 'text-accent-long' : 'text-accent-short';
    deltaSign = isUp ? '▴' : (deltaVsYesterday.value < 0 ? '▾' : '─');
  }
  return (
    <div className="rounded-md border border-white/10 bg-bg-surface p-4">
      <div className="text-xs text-white/50">{title}</div>
      <div className="mt-2 flex items-baseline gap-2">
        <div className="text-2xl font-mono text-white">{value}</div>
        {unit && <div className="text-xs text-white/40">{unit}</div>}
      </div>
      {deltaVsYesterday && (
        <div className={`mt-2 text-xs font-mono ${deltaColor}`}>
          {deltaSign} {Math.abs(deltaVsYesterday.value).toFixed(2)} vs 昨天
        </div>
      )}
    </div>
  );
}
```

`Rabbit Hunterfronted/components/shared/SignalFunnel.tsx`:

```tsx
import React from 'react';

interface Step {
  name: string;
  count: number;
  hint?: string;
}

interface Props {
  steps: Step[];
  onLayerClick?: (step: Step) => void;
}

export function SignalFunnel({ steps, onLayerClick }: Props) {
  const maxCount = steps.reduce((a, b) => Math.max(a, b.count), 0) || 1;
  return (
    <div className="space-y-1">
      {steps.map((s) => {
        const pct = (s.count / maxCount) * 100;
        return (
          <button
            key={s.name}
            type="button"
            onClick={() => onLayerClick?.(s)}
            className="flex w-full items-center gap-3 rounded-sm px-2 py-1 text-left hover:bg-white/5"
          >
            <div className="w-32 text-xs text-white/80">{s.name}</div>
            <div className="flex-1">
              <div className="h-3 rounded-sm bg-white/5">
                <div
                  className="h-full rounded-sm bg-accent-info"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
            <div className="w-14 text-right font-mono text-sm text-white">{s.count}</div>
          </button>
        );
      })}
    </div>
  );
}
```

`Rabbit Hunterfronted/components/shared/RecentAIDecisions.tsx`:

```tsx
import React from 'react';
import type { AIDecisionItem } from '../../types';
import { Badge } from '../primitives/Badge';

interface Props {
  decisions: AIDecisionItem[];
  limit?: number;
}

export function RecentAIDecisions({ decisions, limit = 20 }: Props) {
  const items = decisions.slice(0, limit);
  return (
    <div className="overflow-hidden rounded-md border border-white/10">
      <table className="w-full text-xs">
        <thead className="bg-white/5">
          <tr className="text-left text-white/60">
            <th className="px-2 py-2">时间</th>
            <th className="px-2 py-2">币种</th>
            <th className="px-2 py-2">决定</th>
            <th className="px-2 py-2">Top-1 相似</th>
            <th className="px-2 py-2">推理摘要</th>
          </tr>
        </thead>
        <tbody>
          {items.map(d => (
            <tr key={d.id} className="border-t border-white/5 hover:bg-white/[0.02]">
              <td className="px-2 py-1.5 font-mono text-white/70">
                {new Date(d.created_at).toLocaleTimeString('zh-CN', { hour12: false })}
              </td>
              <td className="px-2 py-1.5 text-white/90">{d.symbol}</td>
              <td className="px-2 py-1.5">
                <Badge variant={d.execute ? 'long' : 'short'}>
                  {d.execute ? '✓ 批准' : '✗ 拒'}
                </Badge>
              </td>
              <td className="px-2 py-1.5 font-mono text-white/70">
                {d.top1_distance == null ? '—' : `d=${d.top1_distance.toFixed(2)}`}
              </td>
              <td className="px-2 py-1.5 text-white/60">
                {d.reasoning.length > 60 ? d.reasoning.slice(0, 60) + '…' : d.reasoning}
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan={5} className="px-2 py-6 text-center text-white/40">暂无决策记录</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
```

`Rabbit Hunterfronted/components/shared/ActivePositionCard.tsx`:

```tsx
import React from 'react';
import type { V5Position } from '../../types';
import { Badge } from '../primitives/Badge';

interface Props {
  position: V5Position;
  onClose: (p: V5Position) => void;
  onChart: (p: V5Position) => void;
}

function fmtPrice(n: number | null | undefined): string {
  if (n == null) return '—';
  if (Math.abs(n) >= 1000) return n.toFixed(2);
  if (Math.abs(n) >= 1) return n.toFixed(4);
  return n.toFixed(4);
}

function holdingMinutes(entryTime: string, now = Date.now()): number {
  return Math.round((now - new Date(entryTime).getTime()) / 60_000);
}

export function ActivePositionCard({ position, onClose, onChart }: Props) {
  const pnlPct = position.pnl_percent ?? 0;
  const pnlUsdt = position.pnl_usdt ?? 0;
  const isProfit = pnlPct > 0;
  const sideBadge = position.side === 'LONG' ? 'long' : 'short';
  const mins = holdingMinutes(position.entry_time);

  return (
    <div className="rounded-md border border-white/10 bg-bg-surface p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="text-base font-medium text-white">{position.symbol}</div>
          <Badge variant={sideBadge}>{position.side}</Badge>
          <span className="text-xs text-white/40 font-mono">×{position.leverage}</span>
          {position.strategy_id && (
            <Badge variant="neutral">
              {position.strategy_id === 'v5_manual' ? '手动' : '自动'}
            </Badge>
          )}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onClose(position)}
            className="rounded-sm border border-accent-short/40 px-2 py-1 text-xs text-accent-short hover:bg-accent-short/10"
          >
            立即平
          </button>
          <button
            type="button"
            onClick={() => onChart(position)}
            className="rounded-sm border border-white/15 px-2 py-1 text-xs text-white/70 hover:bg-white/5"
          >
            📈 图表
          </button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3 font-mono text-sm">
        <div><div className="text-xs text-white/40">入场</div><div className="text-white">{fmtPrice(position.entry_price)}</div></div>
        <div><div className="text-xs text-white/40">当前</div><div className="text-white">{fmtPrice(position.current_price)}</div></div>
        <div><div className="text-xs text-white/40">SL</div><div className="text-accent-short">{fmtPrice(position.stop_loss)}</div></div>
        <div><div className="text-xs text-white/40">TP</div><div className="text-accent-long">{fmtPrice(position.take_profit)}</div></div>
      </div>

      <div className="flex items-center justify-between text-sm">
        <div className={`font-mono ${isProfit ? 'text-accent-long' : 'text-accent-short'}`}>
          PnL: {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}% ({pnlUsdt >= 0 ? '+' : ''}{pnlUsdt.toFixed(2)} USDT)
        </div>
        <div className="text-xs text-white/50 font-mono">
          持仓 {mins}min · 续仓 {position.extension_count ?? 0}/3
        </div>
      </div>

      {position.ai_reason && (
        <div className="text-xs text-white/50">
          AI: {position.ai_reason.slice(0, 100)}{position.ai_reason.length > 100 ? '…' : ''}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/shared/IndicatorGauges.test.tsx tests/shared/ActivePositionCard.test.tsx 2>&1 | tail -10
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add "Rabbit Hunterfronted/components/shared" \
        "Rabbit Hunterfronted/tests/shared/IndicatorGauges.test.tsx" \
        "Rabbit Hunterfronted/tests/shared/ActivePositionCard.test.tsx"
git commit -m "feat(frontend): shared composites (gauges/kpi/funnel/decisions/position)

- IndicatorGauges: RSI arc + MACD hist deltas + 4h reference
- ActivePositionCard: entry/SL/TP/PnL + 立即平 + 图表
- SignalFunnel: clickable layers for Dashboard
- RecentAIDecisions: 5-col table consumed by AIStatusPage
- KpiCard: title + value + delta-vs-yesterday

7 RTL tests."
```

---

### Task 10: IndicatorOverlayChart (Lightweight Charts main + sub)

**Files:**
- Create: `Rabbit Hunterfronted/components/shared/IndicatorOverlayChart.tsx`
- Create: `Rabbit Hunterfronted/tests/shared/IndicatorOverlayChart.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IndicatorOverlayChart } from '@/components/shared/IndicatorOverlayChart';
import type { Kline, SymbolEvent } from '@/types';

// Lightweight Charts uses canvas; jsdom doesn't render it but we test props plumbing
vi.mock('lightweight-charts', () => {
  const series = {
    setData: vi.fn(),
    createPriceLine: vi.fn(),
    setMarkers: vi.fn(),
  };
  const chart = {
    addCandlestickSeries: vi.fn(() => series),
    addLineSeries: vi.fn(() => series),
    addHistogramSeries: vi.fn(() => series),
    timeScale: () => ({ subscribeVisibleLogicalRangeChange: vi.fn(), setVisibleLogicalRange: vi.fn(), fitContent: vi.fn() }),
    remove: vi.fn(),
    applyOptions: vi.fn(),
    resize: vi.fn(),
  };
  return { createChart: vi.fn(() => chart) };
});

const KLINES: Kline[] = Array.from({ length: 50 }, (_, i) => ({
  ts: 1717200000000 + i * 900_000,
  open: 0.165, high: 0.168, low: 0.164, close: 0.166, volume: 1000,
}));

describe('IndicatorOverlayChart', () => {
  it('renders interval selector', () => {
    const onChange = vi.fn();
    render(<IndicatorOverlayChart
      klines={KLINES} events={[]} interval="15m" onIntervalChange={onChange}
      currentPrice={0.166} indicators={{ rsi_15m: 70, macd_hist_15m: -0.001, macd_signal_15m: 0.001 }}
    />);
    expect(screen.getByText('15m')).toBeInTheDocument();
    expect(screen.getByText('1h')).toBeInTheDocument();
    expect(screen.getByText('4h')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect fail**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/shared/IndicatorOverlayChart.test.tsx 2>&1 | tail -10
```

- [ ] **Step 3: Write `Rabbit Hunterfronted/components/shared/IndicatorOverlayChart.tsx`**

```tsx
import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, LineStyle, type IChartApi, type ISeriesApi } from 'lightweight-charts';
import type { Kline, SymbolEvent, Interval } from '../../types';

interface Props {
  klines: Kline[];
  events: SymbolEvent[];
  interval: Interval;
  onIntervalChange: (i: Interval) => void;
  currentPrice: number | null;
  indicators?: {
    rsi_15m?: number;
    macd_hist_15m?: number;
    macd_signal_15m?: number;
  };
}

const INTERVALS: Interval[] = ['15m', '1h', '4h'];

function klineToSeriesData(klines: Kline[]) {
  return klines.map(k => ({
    time: Math.floor(k.ts / 1000) as any,
    open: k.open, high: k.high, low: k.low, close: k.close,
  }));
}

// Lightweight RSI calculator (Wilder)
function rsiSeries(klines: Kline[], period = 14) {
  const out: { time: number; value: number }[] = [];
  let gains = 0, losses = 0;
  for (let i = 1; i < klines.length; i++) {
    const diff = klines[i].close - klines[i - 1].close;
    if (i <= period) {
      if (diff > 0) gains += diff;
      else losses -= diff;
      if (i === period) {
        const avgG = gains / period;
        const avgL = losses / period;
        const rs = avgL === 0 ? 100 : avgG / avgL;
        out.push({ time: Math.floor(klines[i].ts / 1000), value: 100 - 100 / (1 + rs) });
      }
    } else {
      const prevAvgG = ((out.length > 0 ? gains : 0) * (period - 1) + (diff > 0 ? diff : 0)) / period;
      const prevAvgL = ((out.length > 0 ? losses : 0) * (period - 1) + (diff < 0 ? -diff : 0)) / period;
      gains = prevAvgG;
      losses = prevAvgL;
      const rs = losses === 0 ? 100 : gains / losses;
      out.push({ time: Math.floor(klines[i].ts / 1000), value: 100 - 100 / (1 + rs) });
    }
  }
  return out;
}

// Simple MACD histogram derived from closes
function macdHistSeries(klines: Kline[], fast = 12, slow = 26, signalP = 9) {
  if (klines.length < slow + signalP) return [];
  const closes = klines.map(k => k.close);
  const ema = (arr: number[], p: number) => {
    const k = 2 / (p + 1);
    const out: number[] = [];
    let prev = arr[0];
    out.push(prev);
    for (let i = 1; i < arr.length; i++) {
      prev = arr[i] * k + prev * (1 - k);
      out.push(prev);
    }
    return out;
  };
  const ef = ema(closes, fast);
  const es = ema(closes, slow);
  const macd = ef.map((v, i) => v - es[i]);
  const sig = ema(macd, signalP);
  return macd.map((v, i) => ({
    time: Math.floor(klines[i].ts / 1000),
    value: v - sig[i],
    color: v - sig[i] >= 0 ? '#10B981' : '#EF4444',
  }));
}

export function IndicatorOverlayChart({ klines, events, interval, onIntervalChange, currentPrice }: Props) {
  const mainRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const mainChartRef = useRef<IChartApi | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const macdChartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!mainRef.current || !rsiRef.current || !macdRef.current) return;

    const common = {
      layout: {
        background: { type: ColorType.Solid, color: '#0F1419' },
        textColor: 'rgba(255,255,255,0.7)',
      },
      grid: {
        horzLines: { color: 'rgba(255,255,255,0.04)' },
        vertLines: { color: 'rgba(255,255,255,0.04)' },
      },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.08)' },
    } as const;

    const main = createChart(mainRef.current, { ...common, height: 360 });
    const rsi = createChart(rsiRef.current, { ...common, height: 100 });
    const macd = createChart(macdRef.current, { ...common, height: 100 });
    mainChartRef.current = main;
    rsiChartRef.current = rsi;
    macdChartRef.current = macd;

    const candle = main.addCandlestickSeries({
      upColor: '#10B981', downColor: '#EF4444',
      borderUpColor: '#10B981', borderDownColor: '#EF4444',
      wickUpColor: '#10B981', wickDownColor: '#EF4444',
    });
    candle.setData(klineToSeriesData(klines));

    // Markers from events
    const sideToShape = (e: SymbolEvent) => {
      if (e.event_type === 'entry') return e.side === 'SHORT' ? 'arrowDown' : 'arrowUp';
      if (e.event_type === 'exit') return 'circle';
      return 'square';
    };
    const sideToColor = (e: SymbolEvent) => {
      if (e.event_type === 'exit') {
        if (e.exit_reason === 'TP_HIT') return '#10B981';
        if (e.exit_reason === 'SL_HIT') return '#EF4444';
        return '#F59E0B';
      }
      return e.side === 'SHORT' ? '#EF4444' : '#10B981';
    };
    const markers = events.map(e => ({
      time: Math.floor(new Date(e.timestamp).getTime() / 1000) as any,
      position: e.event_type === 'entry'
        ? (e.side === 'SHORT' ? 'aboveBar' : 'belowBar')
        : 'inBar',
      color: sideToColor(e),
      shape: sideToShape(e) as any,
      text: e.event_type === 'entry' ? `${e.side} ${e.price.toFixed(4)}` : (e.exit_reason || 'exit'),
    }));
    candle.setMarkers(markers as any);

    // SL/TP price lines from latest active entry
    const latestEntry = [...events].reverse().find(e => e.event_type === 'entry');
    if (latestEntry) {
      // try to find associated exit; if missing, draw current SL/TP from event reasoning skipped
    }

    // Current price horizontal line
    if (currentPrice != null) {
      candle.createPriceLine({
        price: currentPrice,
        color: '#3B82F6',
        lineStyle: LineStyle.Dashed,
        lineWidth: 1,
        axisLabelVisible: true,
        title: '现价',
      });
    }

    const rsiLine = rsi.addLineSeries({ color: '#F59E0B', lineWidth: 2 });
    rsiLine.setData(rsiSeries(klines) as any);
    rsi.applyOptions({ rightPriceScale: { autoScale: false, scaleMargins: { top: 0.1, bottom: 0.1 } } });
    rsiLine.createPriceLine({ price: 70, color: '#EF4444', lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: '70' });
    rsiLine.createPriceLine({ price: 30, color: '#10B981', lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: '30' });

    const histSeries = macd.addHistogramSeries({ priceFormat: { type: 'price', precision: 6, minMove: 0.000001 } });
    histSeries.setData(macdHistSeries(klines) as any);

    // Synchronize time scales
    const linkTimeScales = (a: IChartApi, b: IChartApi) => {
      a.timeScale().subscribeVisibleLogicalRangeChange(range => {
        if (range) b.timeScale().setVisibleLogicalRange(range);
      });
    };
    linkTimeScales(main, rsi);
    linkTimeScales(main, macd);
    linkTimeScales(rsi, main);
    linkTimeScales(macd, main);

    main.timeScale().fitContent();
    rsi.timeScale().fitContent();
    macd.timeScale().fitContent();

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (mainRef.current) main.resize(mainRef.current.clientWidth, 360);
      if (rsiRef.current) rsi.resize(rsiRef.current.clientWidth, 100);
      if (macdRef.current) macd.resize(macdRef.current.clientWidth, 100);
    });
    if (mainRef.current) ro.observe(mainRef.current);

    return () => {
      ro.disconnect();
      try { main.remove(); rsi.remove(); macd.remove(); } catch { /* ignore */ }
    };
  }, [klines, events, currentPrice]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-end gap-1 text-xs">
        {INTERVALS.map(i => (
          <button
            key={i}
            type="button"
            onClick={() => onIntervalChange(i)}
            className={`rounded-sm border px-2 py-1 font-mono ${
              interval === i
                ? 'border-accent-info bg-accent-info/10 text-accent-info'
                : 'border-white/10 text-white/60 hover:bg-white/5'
            }`}
          >
            {i}
          </button>
        ))}
      </div>
      <div ref={mainRef} className="w-full rounded-md border border-white/10" />
      <div className="grid grid-cols-2 gap-2">
        <div>
          <div className="text-xs text-white/50 mb-1 px-2">RSI 14</div>
          <div ref={rsiRef} className="w-full rounded-md border border-white/10" />
        </div>
        <div>
          <div className="text-xs text-white/50 mb-1 px-2">MACD hist (12/26/9)</div>
          <div ref={macdRef} className="w-full rounded-md border border-white/10" />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/shared/IndicatorOverlayChart.test.tsx 2>&1 | tail -10
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add "Rabbit Hunterfronted/components/shared/IndicatorOverlayChart.tsx" \
        "Rabbit Hunterfronted/tests/shared/IndicatorOverlayChart.test.tsx"
git commit -m "feat(frontend): IndicatorOverlayChart (Lightweight Charts main + RSI + MACD)

- Main: candle + entry/exit markers + current price horizontal
- Sub RSI: 70/30 threshold lines
- Sub MACD: histogram colored by sign
- Time-scale sync across all 3 panels via subscribeVisibleLogicalRangeChange
- Interval pills (15m/1h/4h) emit onIntervalChange

1 RTL test (lightweight-charts mocked)."
```

---

## Phase 4: Layout + Routing

### Task 11: AppShell + Sidebar + TopBar + App.tsx

**Files:**
- Create: `Rabbit Hunterfronted/components/layout/AppShell.tsx`
- Create: `Rabbit Hunterfronted/components/layout/Sidebar.tsx`
- Create: `Rabbit Hunterfronted/components/layout/TopBar.tsx`
- Create: `Rabbit Hunterfronted/App.tsx`
- Modify: `Rabbit Hunterfronted/index.tsx` (provider wiring)
- Create: `Rabbit Hunterfronted/tests/pages/AppShell.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell } from '@/components/layout/AppShell';

describe('AppShell', () => {
  it('renders sidebar groups + topbar', () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/v5/signals']}>
          <Routes>
            <Route path="/v5" element={<AppShell />}>
              <Route path="signals" element={<div>signals-page</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    expect(screen.getByText('猎兔者 V5')).toBeInTheDocument();
    expect(screen.getByText('交易')).toBeInTheDocument();
    expect(screen.getByText('智能')).toBeInTheDocument();
    expect(screen.getByText('系统')).toBeInTheDocument();
    expect(screen.getByText('signals-page')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Write `Rabbit Hunterfronted/components/layout/Sidebar.tsx`**

```tsx
import React from 'react';
import { NavLink } from 'react-router-dom';
import { useUIStore } from '../../services/store';
import {
  Activity, ListOrdered, Briefcase, BarChart3,
  Brain, History, SlidersHorizontal, Settings, Hand, LineChart,
  ChevronLeft, ChevronRight,
} from 'lucide-react';

interface NavItem { to: string; label: string; Icon: any }

const GROUPS: { name: string; items: NavItem[] }[] = [
  { name: '交易', items: [
    { to: '/v5/signals', label: '实时信号', Icon: Activity },
    { to: '/v5/active', label: '活仓监控', Icon: Briefcase },
    { to: '/v5/orders', label: '订单历史', Icon: ListOrdered },
    { to: '/v5/manual', label: '手动开单', Icon: Hand },
  ]},
  { name: '智能', items: [
    { to: '/v5/ai', label: 'AI 状态', Icon: Brain },
    { to: '/v5/history', label: '信号历史', Icon: History },
    { to: '/v5/config', label: '策略配置', Icon: SlidersHorizontal },
  ]},
  { name: '系统', items: [
    { to: '/v5/dashboard', label: 'Dashboard', Icon: BarChart3 },
    { to: '/v5/settings', label: '系统设置', Icon: Settings },
  ]},
];

export function Sidebar() {
  const collapsed = useUIStore(s => s.sidebarCollapsed);
  const toggle = useUIStore(s => s.toggleSidebar);
  return (
    <aside className={`flex h-full flex-col border-r border-white/10 bg-bg-surface ${collapsed ? 'w-14' : 'w-52'} transition-all duration-base`}>
      <div className="flex h-12 items-center justify-between px-3 border-b border-white/10">
        {!collapsed && <span className="text-sm font-medium text-white">猎兔者 V5</span>}
        <button type="button" onClick={toggle} className="text-white/50 hover:text-white">
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto py-3 space-y-4">
        {GROUPS.map(g => (
          <div key={g.name}>
            {!collapsed && <div className="px-3 pb-1 text-[10px] uppercase tracking-wider text-white/40">{g.name}</div>}
            {g.items.map(({ to, label, Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => `flex items-center gap-2 px-3 py-1.5 text-sm ${
                  isActive ? 'bg-accent-info/15 text-accent-info' : 'text-white/70 hover:bg-white/5'
                }`}
              >
                <Icon size={16} />
                {!collapsed && <span>{label}</span>}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
```

- [ ] **Step 3: Write `Rabbit Hunterfronted/components/layout/TopBar.tsx`**

```tsx
import React from 'react';
import { useUIStore } from '../../services/store';
import { useSystemMode } from '../../hooks/useSystemMode';
import { Badge } from '../primitives/Badge';
import { Wifi, WifiOff, Bell } from 'lucide-react';

interface Props {
  wsConnected: boolean;
}

export function TopBar({ wsConnected }: Props) {
  const { mode } = useSystemMode();
  const provider = useUIStore(s => s.effectiveAiProvider);
  const queueLen = useUIStore(s => s.recentWsEvents.length);
  return (
    <header className="flex h-12 items-center justify-between border-b border-white/10 bg-bg-surface px-4">
      <div className="flex items-center gap-3 text-xs text-white/60">
        <span className="font-mono">v5.0.0</span>
        {mode && (
          <Badge variant={mode === 'LIVE' ? 'short' : 'info'}>
            {mode === 'LIVE' ? '🔴 LIVE' : '🟡 SHADOW'}
          </Badge>
        )}
        {provider && <Badge variant="neutral">AI: {provider}</Badge>}
      </div>
      <div className="flex items-center gap-3">
        <span className={`flex items-center gap-1 text-xs ${wsConnected ? 'text-accent-long' : 'text-accent-short'}`}>
          {wsConnected ? <Wifi size={14} /> : <WifiOff size={14} />}
          {wsConnected ? 'WS 在线' : 'WS 离线'}
        </span>
        <button type="button" className="relative text-white/50 hover:text-white">
          <Bell size={16} />
          {queueLen > 0 && (
            <span className="absolute -right-1 -top-1 rounded-full bg-accent-info px-1 text-[10px] font-mono text-white">
              {queueLen}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
```

- [ ] **Step 4: Write `Rabbit Hunterfronted/components/layout/AppShell.tsx`**

```tsx
import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { ErrorBoundary } from '../primitives/ErrorBoundary';
import { useV5WebSocket } from '../../hooks/useV5WebSocket';

function wsUrl(): string {
  if (typeof window === 'undefined') return 'ws://localhost/ws/v5';
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/v5`;
}

export function AppShell() {
  const status = useV5WebSocket(wsUrl());
  return (
    <div className="flex h-screen bg-bg-base text-white">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <TopBar wsConnected={status.connected} />
        <main className="flex-1 overflow-y-auto p-6">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Write `Rabbit Hunterfronted/App.tsx`**

```tsx
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { V5SignalsPage } from './components/pages/V5SignalsPage';
import { V5ActivePositionsPage } from './components/pages/V5ActivePositionsPage';
import { V5OrderHistoryPage } from './components/pages/V5OrderHistoryPage';
import { V5DashboardPage } from './components/pages/V5DashboardPage';
import { V5AIStatusPage } from './components/pages/V5AIStatusPage';
import { V5SignalHistoryPage } from './components/pages/V5SignalHistoryPage';
import { V5StrategyConfigPage } from './components/pages/V5StrategyConfigPage';
import { V5SettingsPage } from './components/pages/V5SettingsPage';
import { V5ManualOrderPage } from './components/pages/V5ManualOrderPage';
import { V5ChartPage } from './components/pages/V5ChartPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/v5/signals" replace />} />
        <Route path="/v5" element={<AppShell />}>
          <Route index element={<Navigate to="signals" replace />} />
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
        <Route path="/signals"   element={<Navigate to="/v5/signals" replace />} />
        <Route path="/positions" element={<Navigate to="/v5/active" replace />} />
        <Route path="/dashboard" element={<Navigate to="/v5/dashboard" replace />} />
        <Route path="*"          element={<Navigate to="/v5/signals" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 6: Write/replace `Rabbit Hunterfronted/index.tsx`**

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 5_000,
    },
  },
});

const root = document.getElementById('root');
if (!root) throw new Error('#root not found');

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);
```

- [ ] **Step 7: Create placeholder pages (so App.tsx compiles)**

For now, every page is a one-line placeholder. Tasks 12-16 will fill them in. Create each of these files with the body:

```tsx
import React from 'react';
export function V5SignalsPage() { return <div>Signals coming soon</div>; }
```

Replace the export name per file (V5ActivePositionsPage, V5OrderHistoryPage, V5DashboardPage, V5AIStatusPage, V5SignalHistoryPage, V5StrategyConfigPage, V5SettingsPage, V5ManualOrderPage, V5ChartPage).

Use `for` loop in bash:

```bash
cd "Rabbit Hunterfronted/components/pages"
for name in V5SignalsPage V5ActivePositionsPage V5OrderHistoryPage V5DashboardPage \
            V5AIStatusPage V5SignalHistoryPage V5StrategyConfigPage V5SettingsPage \
            V5ManualOrderPage V5ChartPage; do
  cat > "${name}.tsx" <<EOF
import React from 'react';
export function ${name}() { return <div>${name} coming soon</div>; }
EOF
done
```

- [ ] **Step 8: Run AppShell test + vite build sanity**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/pages/AppShell.test.tsx 2>&1 | tail -10
npx vite build 2>&1 | tail -10
```

Expected: 1 test passes; build succeeds with no errors.

- [ ] **Step 9: Commit**

```bash
git add "Rabbit Hunterfronted/components/layout" "Rabbit Hunterfronted/components/pages" \
        "Rabbit Hunterfronted/App.tsx" "Rabbit Hunterfronted/index.tsx" \
        "Rabbit Hunterfronted/tests/pages/AppShell.test.tsx"
git commit -m "feat(frontend): AppShell + Sidebar + TopBar + routing + placeholders

- BrowserRouter with /v5/* routes + legacy /signals → /v5/signals redirects
- Sidebar 3 groups (交易/智能/系统) with collapse
- TopBar: mode badge + WS health + AI provider + bell-queue
- index.tsx wires QueryClientProvider + StrictMode
- 10 placeholder page components compile

1 AppShell render test."
```

---

## Phase 5: Pages

### Task 12: V5SignalsPage + V5SignalHistoryPage

**Files:**
- Modify: `Rabbit Hunterfronted/components/pages/V5SignalsPage.tsx` (replace placeholder)
- Modify: `Rabbit Hunterfronted/components/pages/V5SignalHistoryPage.tsx`
- Create: `Rabbit Hunterfronted/components/pages/_signal_helpers.ts` (shared formatting)
- Create: `Rabbit Hunterfronted/tests/pages/V5SignalsPage.test.tsx`

- [ ] **Step 1: Write failing test `Rabbit Hunterfronted/tests/pages/V5SignalsPage.test.tsx`**

```tsx
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { V5SignalsPage } from '@/components/pages/V5SignalsPage';

function wrap(qc: QueryClient) {
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <V5SignalsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('V5SignalsPage', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('renders empty state when 0 signals', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ signals: [], count: 0 }), { status: 200 }));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(wrap(qc));
    await waitFor(() => expect(screen.getByText(/等待行情/)).toBeInTheDocument());
  });

  it('shows a card per signal', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({
        signals: [{
          id: 1, symbol: 'H/USDT', created_at: '2026-06-12T09:48:00+00:00',
          delta_15m_pct: 0.0342, volume_24h_usdt: 5e7,
          rsi_15m: 72.1, rsi_4h: 68, macd_15m: 0, macd_signal_15m: 0,
          macd_hist_15m: -0.0012, macd_hist_prev_15m: 0.0008, macd_hist_4h: 0.003,
          atr_15m: 0.0015, current_price: 0.166,
          should_trade: true, side: 'SHORT',
          reasoning: 'RSI 超买 + 死叉拐点', block_reason: null,
          ai_confidence: 0.7, ai_sl_multiplier: 2.0, ai_tp_multiplier: 2.8,
          ai_size_multiplier: 1.0, ai_reasoning: 'good',
          entry_price: 0.166, sl_price: 0.169, tp_price: 0.162,
          size_usdt: 14.8, expected_rr: 1.4,
          executed: false, position_id: null,
        }], count: 1,
      }), { status: 200 }));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(wrap(qc));
    await waitFor(() => expect(screen.getByText('H/USDT')).toBeInTheDocument());
    expect(screen.getByText(/SHORT/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect fail**

- [ ] **Step 3: Write `Rabbit Hunterfronted/components/pages/_signal_helpers.ts`**

```ts
import type { V5Signal, Side } from '../../types';

export function signalScore(s: V5Signal): number {
  // Lightweight score: confidence×size + AND-pass bonus
  const conf = s.ai_confidence ?? 0;
  const sizeMult = s.ai_size_multiplier ?? 1;
  const andBonus = s.should_trade ? 20 : 0;
  return Math.round(conf * 100 * sizeMult * 0.5 + andBonus);
}

export function dotStateFor(s: V5Signal): '●●●' | '●●○' | '●○○' {
  if (s.executed) return '●●●';
  if (s.should_trade && (s.ai_confidence ?? 0) >= 0.6) return '●●○';
  return '●○○';
}

export function formatSideBadgeTone(side: Side | null): 'long' | 'short' | 'neutral' {
  if (side === 'LONG') return 'long';
  if (side === 'SHORT') return 'short';
  return 'neutral';
}

export function blockReasonZh(reason: string | null): string {
  if (!reason) return '';
  const MAP: Record<string, string> = {
    'NOT_RSI_AND_MACD': 'RSI 与 MACD 未合谋',
    'NOT_RSI_EXTREME': 'RSI 未到极端',
    'NOT_MACD_FLIP': 'MACD 无拐点',
    'NOT_DELTA_15M': 'ΔP15m 不足',
    'NOT_VOLUME': '成交额不足',
    'MAX_CONCURRENT_POSITIONS': '活仓上限',
    'AI_REJECTED': 'AI 否决',
    'AI_UNAVAILABLE_LIVE_FAIL_CLOSED': 'AI 不可用 (LIVE 拒绝)',
    'OPEN_FAILED': '开仓失败',
  };
  return MAP[reason] || reason;
}
```

- [ ] **Step 4: Write `Rabbit Hunterfronted/components/pages/V5SignalsPage.tsx`**

```tsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useV5Signals } from '../../hooks/api/useV5Signals';
import { useUIStore } from '../../services/store';
import type { V5Signal, Side } from '../../types';
import { Card } from '../primitives/Card';
import { Badge } from '../primitives/Badge';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Select } from '../primitives/Select';
import { IndicatorGauges } from '../shared/IndicatorGauges';
import { signalScore, dotStateFor, formatSideBadgeTone, blockReasonZh } from './_signal_helpers';
import { ChevronDown, ChevronUp, LineChart, Hand } from 'lucide-react';

export function V5SignalsPage() {
  const [side, setSide] = useState<Side | 'ALL'>('ALL');
  const [executedOnly, setExecutedOnly] = useState(false);
  const filter = {
    side: side === 'ALL' ? null : side,
    showExecutedOnly: executedOnly,
  };
  const q = useV5Signals(50, filter);
  const navigate = useNavigate();
  const expanded = useUIStore(s => s.expandedSignalIds);
  const toggle = useUIStore(s => s.toggleSignalExpanded);

  const signals = q.data?.signals ?? [];
  const passedAnd = signals.filter(s => s.should_trade).length;
  const executed = signals.filter(s => s.executed).length;

  return (
    <div className="space-y-4">
      <Card
        title={
          <div className="flex items-center gap-3">
            <span>实时信号</span>
            <span className="text-xs text-white/50 font-mono">
              过去窗口: {signals.length} 个扫到 → {passedAnd} 通过 AND → {executed} 入场
            </span>
          </div>
        }
        actions={
          <>
            <Select
              value={side}
              options={[
                { value: 'ALL', label: '方向: 全部' },
                { value: 'SHORT', label: '仅 SHORT' },
                { value: 'LONG', label: '仅 LONG' },
              ]}
              onChange={(v) => setSide(v as any)}
            />
            <label className="flex items-center gap-1 text-xs text-white/60">
              <input type="checkbox" checked={executedOnly} onChange={(e) => setExecutedOnly(e.target.checked)} />
              仅已入场
            </label>
            <button type="button" onClick={() => q.refetch()} className="rounded-sm border border-white/15 px-2 py-1 text-xs text-white/70 hover:bg-white/5">⟳</button>
          </>
        }
      >
        {q.isLoading && <LoadingSkeleton rows={4} />}
        {q.isError && <div className="text-accent-short text-sm">数据获取失败:{(q.error as any)?.detail || (q.error as any)?.message}</div>}
        {!q.isLoading && !q.isError && signals.length === 0 && (
          <div className="py-12 text-center text-white/40">等待行情出现 RSI/MACD 合谋信号...</div>
        )}
        <div className="space-y-2">
          {signals.map(s => {
            const isOpen = expanded.has(s.id);
            return (
              <div key={s.id} className="rounded-md border border-white/10 bg-bg-base">
                <button
                  type="button"
                  onClick={() => toggle(s.id)}
                  className="flex w-full items-center justify-between px-4 py-3 hover:bg-white/5"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-base font-medium text-white">{s.symbol}</span>
                    <Badge variant={formatSideBadgeTone(s.side)}>{s.side ?? '—'}</Badge>
                    <span className={`font-mono text-sm ${s.delta_15m_pct >= 0 ? 'text-accent-long' : 'text-accent-short'}`}>
                      ΔP15m: {s.delta_15m_pct >= 0 ? '+' : ''}{(s.delta_15m_pct * 100).toFixed(2)}%
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs font-mono text-white/60">
                    <span>score {signalScore(s)}</span>
                    <span className="text-base">{dotStateFor(s)}</span>
                    <span>{new Date(s.created_at).toLocaleTimeString('zh-CN', { hour12: false })}</span>
                    {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </div>
                </button>
                {isOpen && (
                  <div className="border-t border-white/10 px-4 py-4 space-y-3">
                    <IndicatorGauges
                      rsi_15m={s.rsi_15m} rsi_4h={s.rsi_4h}
                      macd_hist_15m={s.macd_hist_15m} macd_hist_prev_15m={s.macd_hist_prev_15m}
                      atr_15m={s.atr_15m}
                    />
                    {s.block_reason && (
                      <div className="text-sm text-accent-warn">拦截:{blockReasonZh(s.block_reason)}</div>
                    )}
                    {s.ai_reasoning && (
                      <div className="text-sm text-white/70">AI: {s.ai_reasoning}</div>
                    )}
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => navigate(`/v5/chart/${s.symbol.replace('/', '_')}`)}
                        className="flex items-center gap-1 rounded-sm border border-white/15 px-2 py-1 text-xs text-white/70 hover:bg-white/5"
                      >
                        <LineChart size={12} /> 查看图表
                      </button>
                      <button
                        type="button"
                        onClick={() => navigate(`/v5/manual?symbol=${encodeURIComponent(s.symbol)}&side=${s.side ?? ''}`)}
                        className="flex items-center gap-1 rounded-sm border border-accent-info/40 px-2 py-1 text-xs text-accent-info hover:bg-accent-info/10"
                      >
                        <Hand size={12} /> 此参数模拟开单
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Write `Rabbit Hunterfronted/components/pages/V5SignalHistoryPage.tsx`**

```tsx
import React, { useState } from 'react';
import { useV5Signals } from '../../hooks/api/useV5Signals';
import { Card } from '../primitives/Card';
import { Select } from '../primitives/Select';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Badge } from '../primitives/Badge';
import { formatSideBadgeTone, blockReasonZh } from './_signal_helpers';

const BLOCK_OPTIONS = [
  { value: 'ALL', label: '拦截: 全部' },
  { value: 'NOT_RSI_AND_MACD', label: 'RSI/MACD 未合谋' },
  { value: 'NOT_DELTA_15M', label: 'ΔP15m 不足' },
  { value: 'MAX_CONCURRENT_POSITIONS', label: '活仓上限' },
  { value: 'AI_REJECTED', label: 'AI 否决' },
  { value: 'EXECUTED', label: '✓ 已执行' },
];

export function V5SignalHistoryPage() {
  const [block, setBlock] = useState('ALL');
  const q = useV5Signals(200, { blockReason: block === 'ALL' || block === 'EXECUTED' ? null : block });
  const all = q.data?.signals ?? [];
  const rows = block === 'EXECUTED' ? all.filter(s => s.executed) : all;

  return (
    <div className="space-y-4">
      <Card
        title="信号历史"
        actions={
          <Select value={block} options={BLOCK_OPTIONS} onChange={setBlock} />
        }
      >
        {q.isLoading && <LoadingSkeleton rows={6} />}
        {!q.isLoading && rows.length === 0 && <div className="py-8 text-center text-white/40">无匹配记录</div>}
        <div className="overflow-hidden rounded-md border border-white/10">
          <table className="w-full text-xs">
            <thead className="bg-white/5">
              <tr className="text-left text-white/60">
                <th className="px-2 py-2">时间</th>
                <th className="px-2 py-2">币种</th>
                <th className="px-2 py-2">方向</th>
                <th className="px-2 py-2 text-right">ΔP15m</th>
                <th className="px-2 py-2 text-right">RSI</th>
                <th className="px-2 py-2 text-right">MACD hist</th>
                <th className="px-2 py-2">结果</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(s => (
                <tr key={s.id} className="border-t border-white/5">
                  <td className="px-2 py-1.5 font-mono text-white/70">
                    {new Date(s.created_at).toLocaleString('zh-CN', { hour12: false })}
                  </td>
                  <td className="px-2 py-1.5 text-white/90">{s.symbol}</td>
                  <td className="px-2 py-1.5"><Badge variant={formatSideBadgeTone(s.side)}>{s.side ?? '—'}</Badge></td>
                  <td className="px-2 py-1.5 text-right font-mono">{(s.delta_15m_pct * 100).toFixed(2)}%</td>
                  <td className="px-2 py-1.5 text-right font-mono">{s.rsi_15m.toFixed(1)}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{s.macd_hist_15m.toFixed(4)}</td>
                  <td className="px-2 py-1.5">
                    {s.executed
                      ? <Badge variant="long">✓ 执行</Badge>
                      : s.block_reason
                      ? <span className="text-accent-warn">{blockReasonZh(s.block_reason)}</span>
                      : <span className="text-white/40">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
```

- [ ] **Step 6: Run tests + commit**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/pages/V5SignalsPage.test.tsx 2>&1 | tail -10
```

Expected: 2 passed.

```bash
git add "Rabbit Hunterfronted/components/pages/V5SignalsPage.tsx" \
        "Rabbit Hunterfronted/components/pages/V5SignalHistoryPage.tsx" \
        "Rabbit Hunterfronted/components/pages/_signal_helpers.ts" \
        "Rabbit Hunterfronted/tests/pages/V5SignalsPage.test.tsx"
git commit -m "feat(frontend): V5SignalsPage + V5SignalHistoryPage

- Signals: 10s polling, side filter, executed-only, expand-on-click
- Expand: IndicatorGauges + reasoning + 'view chart' + 'manual order' deep-link
- History: 200-row table with block_reason filter

2 RTL tests."
```

---

### Task 13: V5ActivePositionsPage + V5OrderHistoryPage

**Files:**
- Modify: `V5ActivePositionsPage.tsx`
- Modify: `V5OrderHistoryPage.tsx`
- Create: `Rabbit Hunterfronted/tests/pages/V5ActivePositionsPage.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { V5ActivePositionsPage } from '@/components/pages/V5ActivePositionsPage';

const OPEN = {
  positions: [{
    id: 7, symbol: 'H/USDT', side: 'SHORT', status: 'OPEN',
    entry_price: 0.1665, current_price: 0.1641, stop_loss: 0.1715, take_profit: 0.1592,
    position_size_usdt: 15, leverage: 10,
    entry_time: new Date(Date.now() - 10 * 60_000).toISOString(),
    exit_time: null, exit_price: null, exit_reason: null,
    pnl_percent: 1.44, pnl_usdt: 0.22,
    entry_rsi_15m: 72, entry_macd_hist_15m: -0.0006,
    extension_count: 0, target_close_at: null, ai_reason: 'short setup',
    strategy_id: 'v5_rsi_macd',
  }],
  count: 1,
};
const EMPTY = { positions: [], count: 0 };

function wrap(qc: QueryClient) {
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter><V5ActivePositionsPage /></MemoryRouter>
    </QueryClientProvider>
  );
}

describe('V5ActivePositionsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/api/v5/paper-positions')) return new Response(JSON.stringify(OPEN), { status: 200 });
      return new Response(JSON.stringify(EMPTY), { status: 200 });
    }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('renders one ActivePositionCard', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(wrap(qc));
    await waitFor(() => expect(screen.getByText('H/USDT')).toBeInTheDocument());
  });

  it('立即平 opens confirm modal', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(wrap(qc));
    await waitFor(() => screen.getByText('H/USDT'));
    await user.click(screen.getByRole('button', { name: /立即平/ }));
    expect(screen.getByText(/确认立即平仓/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect fail**

- [ ] **Step 3: Write `Rabbit Hunterfronted/components/pages/V5ActivePositionsPage.tsx`**

```tsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useV5ActivePositions, useV5ClosePosition } from '../../hooks/api/useV5ActivePositions';
import { ActivePositionCard } from '../shared/ActivePositionCard';
import { Card } from '../primitives/Card';
import { Modal } from '../primitives/Modal';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import type { V5Position } from '../../types';

const MAX_SLOTS = 3;

export function V5ActivePositionsPage() {
  const q = useV5ActivePositions();
  const close = useV5ClosePosition();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState<V5Position | null>(null);

  const combined = q.data?.combined ?? [];
  const total = combined.length;

  return (
    <div className="space-y-4">
      <Card
        title={
          <div className="flex items-center gap-3">
            <span>活仓监控</span>
            <span className="text-sm font-mono text-white/60">{total} / {MAX_SLOTS}</span>
          </div>
        }
        actions={<span className="text-xs text-white/40">每 5s 自动刷新</span>}
      >
        {q.isLoading && <LoadingSkeleton rows={3} />}
        {!q.isLoading && total === 0 && (
          <div className="py-8 text-center text-white/40">当前无活仓</div>
        )}
        <div className="space-y-3">
          {combined.map(p => (
            <ActivePositionCard
              key={p.id}
              position={p}
              onClose={() => setConfirm(p)}
              onChart={() => navigate(`/v5/chart/${p.symbol.replace('/', '_')}`)}
            />
          ))}
          {total < MAX_SLOTS && (
            <div className="rounded-md border border-dashed border-white/15 p-6 text-center text-sm text-white/40">
              [+] 空闲槽位({MAX_SLOTS - total} 个)
            </div>
          )}
        </div>
      </Card>

      <Modal
        open={!!confirm}
        onClose={() => setConfirm(null)}
        title="确认立即平仓"
      >
        {confirm && (
          <div className="space-y-3 text-sm">
            <div>
              {confirm.symbol} · {confirm.side} · 入场 {confirm.entry_price.toFixed(4)} · 当前 {confirm.current_price?.toFixed(4) ?? '—'}
            </div>
            <div className="text-white/60">
              当前 PnL: {confirm.pnl_percent?.toFixed(2)}% / {confirm.pnl_usdt?.toFixed(2)} USDT
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setConfirm(null)} className="rounded-sm border border-white/15 px-3 py-1 text-xs">取消</button>
              <button
                type="button"
                disabled={close.isPending}
                onClick={async () => {
                  await close.mutateAsync({
                    id: confirm.id,
                    body: {
                      exit_price: confirm.current_price ?? confirm.entry_price,
                      exit_reason: 'MANUAL_USER',
                    },
                  });
                  setConfirm(null);
                }}
                className="rounded-sm border border-accent-short/40 bg-accent-short/10 px-3 py-1 text-xs text-accent-short hover:bg-accent-short/20 disabled:opacity-50"
              >
                {close.isPending ? '平仓中…' : '确认平仓'}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
```

- [ ] **Step 4: Write `Rabbit Hunterfronted/components/pages/V5OrderHistoryPage.tsx`**

```tsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useV5OrderHistory } from '../../hooks/api/useV5OrderHistory';
import { Card } from '../primitives/Card';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Badge } from '../primitives/Badge';
import { LineChart } from 'lucide-react';

export function V5OrderHistoryPage() {
  const q = useV5OrderHistory(200);
  const navigate = useNavigate();
  const rows = q.data ?? [];

  return (
    <div className="space-y-4">
      <Card title="订单历史" actions={<span className="text-xs text-white/40">每 30s 自动刷新 · 共 {rows.length} 条</span>}>
        {q.isLoading && <LoadingSkeleton rows={6} />}
        {!q.isLoading && rows.length === 0 && <div className="py-8 text-center text-white/40">暂无历史订单</div>}
        <div className="overflow-hidden rounded-md border border-white/10">
          <table className="w-full text-xs">
            <thead className="bg-white/5">
              <tr className="text-left text-white/60">
                <th className="px-2 py-2">平仓时间</th>
                <th className="px-2 py-2">币种</th>
                <th className="px-2 py-2">方向</th>
                <th className="px-2 py-2 text-right">入场</th>
                <th className="px-2 py-2 text-right">出场</th>
                <th className="px-2 py-2">原因</th>
                <th className="px-2 py-2 text-right">PnL$</th>
                <th className="px-2 py-2 text-right">PnL%</th>
                <th className="px-2 py-2 text-right">持仓min</th>
                <th className="px-2 py-2">策略</th>
                <th className="px-2 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(p => {
                const mins = p.entry_time && p.exit_time
                  ? Math.round((new Date(p.exit_time).getTime() - new Date(p.entry_time).getTime()) / 60_000)
                  : 0;
                const pnlPct = p.pnl_percent ?? 0;
                const pnlUsd = p.pnl_usdt ?? 0;
                return (
                  <tr key={`${p.strategy_id}-${p.id}`} className="border-t border-white/5 hover:bg-white/[0.02]">
                    <td className="px-2 py-1.5 font-mono text-white/70">
                      {p.exit_time ? new Date(p.exit_time).toLocaleString('zh-CN', { hour12: false }) : '—'}
                    </td>
                    <td className="px-2 py-1.5 text-white/90">{p.symbol}</td>
                    <td className="px-2 py-1.5"><Badge variant={p.side === 'LONG' ? 'long' : 'short'}>{p.side}</Badge></td>
                    <td className="px-2 py-1.5 text-right font-mono">{p.entry_price.toFixed(4)}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{p.exit_price?.toFixed(4) ?? '—'}</td>
                    <td className="px-2 py-1.5 text-white/70">{p.exit_reason ?? '—'}</td>
                    <td className={`px-2 py-1.5 text-right font-mono ${pnlUsd >= 0 ? 'text-accent-long' : 'text-accent-short'}`}>{pnlUsd >= 0 ? '+' : ''}{pnlUsd.toFixed(2)}</td>
                    <td className={`px-2 py-1.5 text-right font-mono ${pnlPct >= 0 ? 'text-accent-long' : 'text-accent-short'}`}>{pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%</td>
                    <td className="px-2 py-1.5 text-right font-mono">{mins}</td>
                    <td className="px-2 py-1.5"><Badge variant="neutral">{p.strategy_id === 'v5_manual' ? '手动' : '自动'}</Badge></td>
                    <td className="px-2 py-1.5">
                      <button
                        type="button"
                        onClick={() => navigate(`/v5/chart/${p.symbol.replace('/', '_')}?eventId=${p.id}`)}
                        className="flex items-center gap-1 rounded-sm border border-white/15 px-2 py-0.5 text-xs text-white/70 hover:bg-white/5"
                      >
                        <LineChart size={10} /> 图表
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Run tests + commit**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/pages/V5ActivePositionsPage.test.tsx 2>&1 | tail -10
```

Expected: 2 passed.

```bash
git add "Rabbit Hunterfronted/components/pages/V5ActivePositionsPage.tsx" \
        "Rabbit Hunterfronted/components/pages/V5OrderHistoryPage.tsx" \
        "Rabbit Hunterfronted/tests/pages/V5ActivePositionsPage.test.tsx"
git commit -m "feat(frontend): V5ActivePositionsPage + V5OrderHistoryPage

- Active: card grid + confirm modal for close
- History: 11-col table with strategy badge + chart deep-link

2 RTL tests."
```

---

### Task 14: V5DashboardPage + V5AIStatusPage

**Files:**
- Modify: `V5DashboardPage.tsx`
- Modify: `V5AIStatusPage.tsx`
- Create: `Rabbit Hunterfronted/tests/pages/V5DashboardPage.test.tsx`

- [ ] **Step 1: Write `Rabbit Hunterfronted/tests/pages/V5DashboardPage.test.tsx`**

```tsx
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { V5DashboardPage } from '@/components/pages/V5DashboardPage';

const FAKE_SIGNALS = { signals: [], count: 0 };
const FAKE_POS = { positions: [], count: 0 };

describe('V5DashboardPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('signals')) return new Response(JSON.stringify(FAKE_SIGNALS), { status: 200 });
      return new Response(JSON.stringify(FAKE_POS), { status: 200 });
    }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('renders KPI cards with zero values on empty data', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter><V5DashboardPage /></MemoryRouter>
      </QueryClientProvider>
    );
    await waitFor(() => expect(screen.getByText('胜率')).toBeInTheDocument());
    expect(screen.getByText('累计 PnL')).toBeInTheDocument();
    expect(screen.getByText('平均持仓')).toBeInTheDocument();
    expect(screen.getByText('活仓数')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Write `Rabbit Hunterfronted/components/pages/V5DashboardPage.tsx`**

```tsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useV5Dashboard } from '../../hooks/api/useV5Dashboard';
import { Card } from '../primitives/Card';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { KpiCard } from '../shared/KpiCard';
import { SignalFunnel } from '../shared/SignalFunnel';
import { LineChart as Lc, Line, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts';

export function V5DashboardPage() {
  const q = useV5Dashboard();
  const navigate = useNavigate();
  if (q.isLoading) return <LoadingSkeleton rows={6} />;
  const d = q.data;
  if (!d) return <div className="text-white/40">无数据</div>;

  const winRatePct = Math.round(d.win_rate_24h * 100);
  const pnlSeries = d.closed_24h
    .slice()
    .sort((a, b) => (a.exit_time || '').localeCompare(b.exit_time || ''))
    .reduce<{ time: string; cum: number }[]>((acc, p) => {
      const prev = acc.length > 0 ? acc[acc.length - 1].cum : 0;
      acc.push({
        time: p.exit_time ? new Date(p.exit_time).toLocaleTimeString('zh-CN', { hour12: false }) : '',
        cum: prev + (p.pnl_usdt ?? 0),
      });
      return acc;
    }, []);

  const funnelSteps = [
    { name: 'Scanner 扫到', count: d.signals_24h },
    { name: '通过 AND', count: d.signals_passed_and },
    { name: '实际开仓', count: d.signals_executed },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        <KpiCard title="胜率" value={`${winRatePct}%`} />
        <KpiCard title="累计 PnL" value={d.pnl_total_usdt.toFixed(2)} unit="USDT" />
        <KpiCard title="平均持仓" value={Math.round(d.avg_holding_minutes)} unit="min" />
        <KpiCard title="活仓数" value={`${d.active_count} / 3`} />
      </div>

      <Card title="24h 信号漏斗">
        <SignalFunnel steps={funnelSteps} onLayerClick={(s) => {
          if (s.name === '实际开仓') navigate('/v5/history?block_reason=EXECUTED');
          else navigate('/v5/history');
        }} />
      </Card>

      <Card title="24h PnL 曲线">
        {pnlSeries.length === 0 ? (
          <div className="py-8 text-center text-white/40">24h 内无平仓</div>
        ) : (
          <div className="h-48 w-full">
            <ResponsiveContainer>
              <Lc data={pnlSeries}>
                <XAxis dataKey="time" stroke="rgba(255,255,255,0.4)" fontSize={10} />
                <YAxis stroke="rgba(255,255,255,0.4)" fontSize={10} />
                <Tooltip contentStyle={{ background: '#1A2030', border: '1px solid rgba(255,255,255,0.1)' }} />
                <Line type="monotone" dataKey="cum" stroke="#3B82F6" strokeWidth={2} dot={false} />
              </Lc>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <Card title="拦截原因分布">
        <div className="space-y-1">
          {Object.entries(d.signals_block_counts)
            .sort((a, b) => b[1] - a[1])
            .map(([k, v]) => (
              <div key={k} className="flex items-center justify-between text-xs">
                <span className="text-white/70">{k}</span>
                <span className="font-mono text-white">{v}</span>
              </div>
            ))}
        </div>
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Write `Rabbit Hunterfronted/components/pages/V5AIStatusPage.tsx`**

```tsx
import React from 'react';
import { useV5AIStatus, useV5AIDecisions } from '../../hooks/api/useV5AIStatus';
import { Card } from '../primitives/Card';
import { KpiCard } from '../shared/KpiCard';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { RecentAIDecisions } from '../shared/RecentAIDecisions';

export function V5AIStatusPage() {
  const status = useV5AIStatus();
  const dec = useV5AIDecisions(20);
  if (status.isLoading) return <LoadingSkeleton rows={4} />;
  const s = status.data;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <KpiCard
          title="Provider"
          value={s?.provider ?? '未配置'}
          unit={s?.chat_model}
        />
        <KpiCard
          title="RAG 利用率 (24h)"
          value={`${Math.round((s?.rag_utilization_24h ?? 0) * 100)}%`}
          unit={`本地 ${s?.rag_cases_in_db ?? 0} cases`}
        />
        <KpiCard
          title="24h 决策数"
          value={s?.decisions_24h ?? 0}
          unit={s?.healthy ? '在线' : '离线'}
        />
      </div>

      <Card title="最近 20 笔 AI 决策">
        {dec.isLoading ? <LoadingSkeleton rows={5} /> : <RecentAIDecisions decisions={dec.data?.decisions ?? []} />}
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Run tests + commit**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/pages/V5DashboardPage.test.tsx 2>&1 | tail -10
```

Expected: 1 passed.

```bash
git add "Rabbit Hunterfronted/components/pages/V5DashboardPage.tsx" \
        "Rabbit Hunterfronted/components/pages/V5AIStatusPage.tsx" \
        "Rabbit Hunterfronted/tests/pages/V5DashboardPage.test.tsx"
git commit -m "feat(frontend): V5DashboardPage + V5AIStatusPage

- Dashboard: 4 KPI cards + funnel + PnL line (Recharts) + block-reason histogram
- AIStatus: provider/RAG/decisions tiles + recent 20 decisions table

1 RTL test."
```

---

### Task 15: V5StrategyConfigPage + V5SettingsPage

**Files:**
- Modify: `V5StrategyConfigPage.tsx`
- Modify: `V5SettingsPage.tsx`
- Create: `Rabbit Hunterfronted/tests/pages/V5StrategyConfigPage.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { V5StrategyConfigPage } from '@/components/pages/V5StrategyConfigPage';

const FAKE_CONFIG = {
  params: [
    { key: 'v5_rsi_overbought', value: 70, default: 70, min: 60, max: 80, unit: '', description: '开空 RSI' },
    { key: 'v5_rsi_oversold', value: 30, default: 30, min: 20, max: 40, unit: '', description: '开多 RSI' },
  ],
};

describe('V5StrategyConfigPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(FAKE_CONFIG), { status: 200 })));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('renders one row per param', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter><V5StrategyConfigPage /></MemoryRouter>
      </QueryClientProvider>
    );
    await waitFor(() => expect(screen.getByText('v5_rsi_overbought')).toBeInTheDocument());
    expect(screen.getByText('v5_rsi_oversold')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Write `Rabbit Hunterfronted/components/pages/V5StrategyConfigPage.tsx`**

```tsx
import React, { useState, useEffect } from 'react';
import { useV5StrategyConfig } from '../../hooks/api/useV5StrategyConfig';
import { Card } from '../primitives/Card';
import { Slider } from '../primitives/Slider';
import { NumberInput } from '../primitives/NumberInput';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';

export function V5StrategyConfigPage() {
  const { query, patch, preview } = useV5StrategyConfig();
  const [dirty, setDirty] = useState<Record<string, number>>({});
  const [previewMsg, setPreviewMsg] = useState<string | null>(null);

  useEffect(() => { setDirty({}); }, [query.data]);

  if (query.isLoading) return <LoadingSkeleton rows={8} />;
  const params = query.data?.params ?? [];

  const effectiveValue = (key: string, current: number) =>
    Object.prototype.hasOwnProperty.call(dirty, key) ? dirty[key] : current;

  const isDirty = Object.keys(dirty).length > 0;

  return (
    <div className="space-y-4">
      <Card
        title="策略配置"
        actions={
          <>
            <button
              type="button"
              disabled={!isDirty}
              onClick={() => setDirty({})}
              className="rounded-sm border border-white/15 px-3 py-1 text-xs disabled:opacity-40"
            >
              撤销修改
            </button>
            <button
              type="button"
              disabled={!isDirty || preview.isPending}
              onClick={async () => {
                const merged = params.reduce((acc, p) => {
                  acc[p.key] = effectiveValue(p.key, p.value);
                  return acc;
                }, {} as Record<string, number>);
                const res = await preview.mutateAsync(merged);
                setPreviewMsg(`预计每小时入场: ${res.estimated_entries_per_hour.toFixed(1)} · 胜率 ${(res.estimated_win_rate * 100).toFixed(0)}% · ${res.note}`);
              }}
              className="rounded-sm border border-accent-info/40 px-3 py-1 text-xs text-accent-info disabled:opacity-40"
            >
              预览效果
            </button>
            <button
              type="button"
              disabled={!isDirty || patch.isPending}
              onClick={() => patch.mutate(dirty)}
              className="rounded-sm border border-accent-long/40 bg-accent-long/10 px-3 py-1 text-xs text-accent-long disabled:opacity-40"
            >
              {patch.isPending ? '保存中…' : '保存修改'}
            </button>
          </>
        }
      >
        {previewMsg && <div className="mb-3 rounded-sm border border-accent-info/40 bg-accent-info/10 p-2 text-xs text-accent-info">{previewMsg}</div>}
        <div className="divide-y divide-white/5">
          {params.map(p => {
            const eff = effectiveValue(p.key, p.value);
            const isChanged = eff !== p.value;
            return (
              <div key={p.key} className="grid grid-cols-12 items-center gap-3 py-3">
                <div className="col-span-3">
                  <div className="text-sm text-white">{p.key}</div>
                  <div className="text-xs text-white/40">{p.description}</div>
                </div>
                <div className="col-span-6">
                  <Slider value={eff} min={p.min} max={p.max} step={(p.max - p.min) / 100}
                          onChange={(v) => setDirty(d => ({ ...d, [p.key]: v }))} />
                </div>
                <div className="col-span-2">
                  <NumberInput value={eff} min={p.min} max={p.max} step={(p.max - p.min) / 100}
                               onChange={(v) => setDirty(d => ({ ...d, [p.key]: v }))} />
                </div>
                <div className="col-span-1 text-right text-xs text-white/40">
                  {isChanged ? <span className="text-accent-warn">●</span> : ''}{p.unit}
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Write `Rabbit Hunterfronted/components/pages/V5SettingsPage.tsx`**

```tsx
import React, { useState } from 'react';
import { useV5Settings } from '../../hooks/api/useV5Settings';
import { Card } from '../primitives/Card';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Modal } from '../primitives/Modal';
import { Badge } from '../primitives/Badge';
import { Select } from '../primitives/Select';

export function V5SettingsPage() {
  const { query, patch } = useV5Settings();
  const [confirmLive, setConfirmLive] = useState(false);
  const [deepseekKey, setDeepseekKey] = useState('');
  const [openaiKey, setOpenaiKey] = useState('');

  if (query.isLoading) return <LoadingSkeleton rows={6} />;
  const s = query.data;
  if (!s) return <div className="text-white/40">无数据</div>;

  return (
    <div className="space-y-4">
      <Card title="交易所">
        <div className="text-sm">当前: <Badge variant="info">{s.exchange}</Badge></div>
      </Card>

      <Card title="AI 配置">
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-white/50 mb-1">DeepSeek API Key</div>
              <input
                type="password"
                placeholder={s.deepseek_api_key_masked || '未配置'}
                value={deepseekKey}
                onChange={(e) => setDeepseekKey(e.target.value)}
                className="w-full rounded-sm border border-white/10 bg-bg-base px-2 py-1 font-mono text-white"
              />
            </div>
            <div>
              <div className="text-xs text-white/50 mb-1">OpenAI API Key</div>
              <input
                type="password"
                placeholder={s.openai_api_key_masked || '未配置'}
                value={openaiKey}
                onChange={(e) => setOpenaiKey(e.target.value)}
                className="w-full rounded-sm border border-white/10 bg-bg-base px-2 py-1 font-mono text-white"
              />
            </div>
          </div>
          <div className="text-xs text-white/50">
            活跃: <Badge variant="info">{s.active_ai_provider ?? '无'}</Badge> · 模型 {s.active_chat_model}
          </div>
          <button
            type="button"
            disabled={patch.isPending || (!deepseekKey && !openaiKey)}
            onClick={() => patch.mutate({
              ...(deepseekKey ? { deepseek_api_key: deepseekKey } : {}),
              ...(openaiKey ? { openai_api_key: openaiKey } : {}),
            })}
            className="rounded-sm border border-accent-info/40 px-3 py-1 text-xs text-accent-info disabled:opacity-40"
          >
            保存 AI 配置
          </button>
        </div>
      </Card>

      <Card title="系统模式">
        <div className="flex items-center gap-3">
          <Badge variant={s.system_mode === 'LIVE' ? 'short' : 'info'}>
            {s.system_mode === 'LIVE' ? '🔴 LIVE' : '🟡 SHADOW'}
          </Badge>
          <button
            type="button"
            onClick={() => {
              if (s.system_mode === 'SHADOW') setConfirmLive(true);
              else patch.mutate({ system_mode: 'SHADOW' });
            }}
            className="rounded-sm border border-white/15 px-3 py-1 text-xs"
          >
            切换到 {s.system_mode === 'SHADOW' ? 'LIVE' : 'SHADOW'}
          </button>
        </div>
      </Card>

      <Card title="Fail-closed 旋钮">
        <div className="space-y-2 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={s.ai_fail_open} onChange={(e) => patch.mutate({ ai_fail_open: e.target.checked })} />
            <span>AI 不可用时 fail-open (LIVE 默认 fail-closed,勾选 = 允许跳过 AI)</span>
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={s.sl_tp_fail_open} onChange={(e) => patch.mutate({ sl_tp_fail_open: e.target.checked })} />
            <span>SL/TP 异常 fail-open</span>
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={s.enable_auto_trading} onChange={(e) => patch.mutate({ enable_auto_trading: e.target.checked })} />
            <span>启用自动交易</span>
          </label>
        </div>
      </Card>

      <Modal
        open={confirmLive}
        onClose={() => setConfirmLive(false)}
        title="切换到 LIVE 模式"
      >
        <div className="space-y-3 text-sm">
          <div className="text-accent-warn">
            ⚠️ LIVE 模式将使用真实资金开仓。请确认账户余额和当前活仓状态。
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setConfirmLive(false)} className="rounded-sm border border-white/15 px-3 py-1 text-xs">取消</button>
            <button
              type="button"
              onClick={() => { patch.mutate({ system_mode: 'LIVE' }); setConfirmLive(false); }}
              className="rounded-sm border border-accent-short/40 bg-accent-short/10 px-3 py-1 text-xs text-accent-short"
            >
              确认切到 LIVE
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 4: Run tests + commit**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/pages/V5StrategyConfigPage.test.tsx 2>&1 | tail -10
```

Expected: 1 passed.

```bash
git add "Rabbit Hunterfronted/components/pages/V5StrategyConfigPage.tsx" \
        "Rabbit Hunterfronted/components/pages/V5SettingsPage.tsx" \
        "Rabbit Hunterfronted/tests/pages/V5StrategyConfigPage.test.tsx"
git commit -m "feat(frontend): V5StrategyConfigPage + V5SettingsPage

- StrategyConfig: slider + number per param + dirty + preview + save
- Settings: exchange/AI keys/mode/fail-closed; LIVE switch confirms modal

1 RTL test."
```

---

### Task 16: V5ManualOrderPage (3-step) + V5ChartPage

**Files:**
- Modify: `V5ManualOrderPage.tsx`
- Modify: `V5ChartPage.tsx`
- Create: `Rabbit Hunterfronted/tests/pages/V5ManualOrderPage.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { V5ManualOrderPage } from '@/components/pages/V5ManualOrderPage';

const PREVIEW = {
  symbol: 'H/USDT', side: 'SHORT', current_price: 0.166,
  indicators: { rsi_15m: 72, macd_hist_15m: -0.001, macd_hist_prev_15m: 0.0008,
                atr_15m: 0.0015, rsi_4h: 68, macd_hist_4h: 0.003 },
  decision: { should_trade: true, side: 'SHORT', reasoning: 'RSI super', block_reason: null },
  risk_plan: { entry_price: 0.166, sl_price: 0.169, tp_price: 0.162, size_usdt: 15, leverage: 10, expected_rr: 1.5 },
  ai_result: { execute: true, sl_multiplier: 1.0, tp_multiplier: 1.0, size_multiplier: 1.0, confidence: 0.7, reasoning: 'ok' },
  rag_cases: [], rag_summary: null,
};

describe('V5ManualOrderPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('preview')) return new Response(JSON.stringify(PREVIEW), { status: 200 });
      return new Response(JSON.stringify({}), { status: 200 });
    }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('flows Step1 → Step2 on preview submit', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { mutations: { retry: false }, queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/v5/manual']}><V5ManualOrderPage /></MemoryRouter>
      </QueryClientProvider>
    );
    expect(screen.getByText(/Step 1/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /模拟评估/ }));
    await waitFor(() => expect(screen.getByText(/Step 2/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Write `Rabbit Hunterfronted/components/pages/V5ManualOrderPage.tsx`**

```tsx
import React, { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useV5ManualOrder } from '../../hooks/api/useV5ManualOrder';
import { useSystemMode } from '../../hooks/useSystemMode';
import { Card } from '../primitives/Card';
import { Select } from '../primitives/Select';
import { NumberInput } from '../primitives/NumberInput';
import { Badge } from '../primitives/Badge';
import { IndicatorGauges } from '../shared/IndicatorGauges';
import type { Side, ManualOrderPreviewResponse } from '../../types';

type Step = 1 | 2 | 3;

export function V5ManualOrderPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { mode } = useSystemMode();
  const { preview, execute } = useV5ManualOrder();

  const [step, setStep] = useState<Step>(1);
  const [symbol, setSymbol] = useState(params.get('symbol') ?? 'BTC/USDT');
  const [side, setSide] = useState<Side>((params.get('side') as Side) || 'SHORT');
  const [size, setSize] = useState(15);
  const [previewData, setPreviewData] = useState<ManualOrderPreviewResponse | null>(null);
  const [slMult, setSlMult] = useState(1);
  const [tpMult, setTpMult] = useState(1);
  const [sizeMult, setSizeMult] = useState(1);

  if (mode === 'LIVE') {
    return (
      <Card title="手动开单">
        <div className="text-accent-warn">手动开单仅在 SHADOW 模式可用。</div>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card title={`手动开单 — Step ${step}/3`}>
        {step === 1 && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <div>
                <div className="text-xs text-white/50 mb-1">Symbol</div>
                <input
                  className="w-full rounded-sm border border-white/10 bg-bg-base px-2 py-1 font-mono text-white"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                />
              </div>
              <div>
                <div className="text-xs text-white/50 mb-1">Side</div>
                <Select
                  value={side}
                  options={[{ value: 'SHORT', label: 'SHORT' }, { value: 'LONG', label: 'LONG' }]}
                  onChange={(v) => setSide(v as Side)}
                />
              </div>
              <div>
                <div className="text-xs text-white/50 mb-1">Size (USDT)</div>
                <NumberInput value={size} min={5} max={500} step={1} onChange={setSize} />
              </div>
            </div>
            <button
              type="button"
              disabled={preview.isPending || !symbol}
              onClick={async () => {
                const r = await preview.mutateAsync({ symbol, side, size_usdt: size });
                setPreviewData(r);
                setSlMult(r.ai_result.sl_multiplier);
                setTpMult(r.ai_result.tp_multiplier);
                setSizeMult(r.ai_result.size_multiplier);
                setStep(2);
              }}
              className="rounded-sm border border-accent-info/40 bg-accent-info/10 px-3 py-1 text-sm text-accent-info disabled:opacity-50"
            >
              {preview.isPending ? '评估中…' : '模拟评估 →'}
            </button>
            {preview.isError && (
              <div className="text-sm text-accent-short">评估失败:{(preview.error as any)?.detail ?? (preview.error as any)?.message}</div>
            )}
          </div>
        )}

        {step === 2 && previewData && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <Card title="当前指标">
                <IndicatorGauges
                  rsi_15m={previewData.indicators.rsi_15m}
                  rsi_4h={previewData.indicators.rsi_4h ?? null}
                  macd_hist_15m={previewData.indicators.macd_hist_15m}
                  macd_hist_prev_15m={previewData.indicators.macd_hist_prev_15m}
                  atr_15m={previewData.indicators.atr_15m}
                />
              </Card>
              <Card title="规则决策">
                <div className="text-sm space-y-1">
                  <div>
                    {previewData.decision.should_trade
                      ? <Badge variant="long">✓ {previewData.decision.side}</Badge>
                      : <Badge variant="short">✗ 不建议</Badge>}
                  </div>
                  <div className="text-xs text-white/60">{previewData.decision.reasoning}</div>
                  <div className="font-mono text-xs text-white/70">
                    SL ${previewData.risk_plan.sl_price.toFixed(4)} ·
                    TP ${previewData.risk_plan.tp_price.toFixed(4)}
                  </div>
                </div>
              </Card>
              <Card title="AI 二次审查">
                <div className="text-sm space-y-1">
                  <div>
                    {previewData.ai_result.execute
                      ? <Badge variant="long">✓ execute=true</Badge>
                      : <Badge variant="short">✗ 拒</Badge>}
                  </div>
                  <div className="text-xs text-white/60">{previewData.ai_result.reasoning}</div>
                  <div className="grid grid-cols-3 gap-2 text-xs font-mono">
                    <label>SL × <NumberInput value={slMult} min={0.5} max={3} step={0.1} onChange={setSlMult} /></label>
                    <label>TP × <NumberInput value={tpMult} min={0.5} max={5} step={0.1} onChange={setTpMult} /></label>
                    <label>Size × <NumberInput value={sizeMult} min={0.1} max={2} step={0.1} onChange={setSizeMult} /></label>
                  </div>
                </div>
              </Card>
            </div>

            <Card title={`RAG 历史相似 top-${previewData.rag_cases.length}`}>
              {previewData.rag_cases.length === 0 ? (
                <div className="text-xs text-white/40">RAG 冷启动期,无相似 case</div>
              ) : (
                <table className="w-full text-xs">
                  <thead><tr className="text-left text-white/50">
                    <th>RSI</th><th>MACD hist</th><th>结果</th><th className="text-right">PnL</th><th>原因</th><th className="text-right">距离</th>
                  </tr></thead>
                  <tbody>
                    {previewData.rag_cases.map((c, i) => (
                      <tr key={i} className="border-t border-white/5 font-mono">
                        <td>{c.entry_rsi_15m.toFixed(1)}</td>
                        <td>{c.entry_macd_hist_15m.toFixed(4)}</td>
                        <td className={c.outcome === 'WIN' ? 'text-accent-long' : c.outcome === 'LOSS' ? 'text-accent-short' : 'text-white/60'}>{c.outcome}</td>
                        <td className="text-right">{(c.pnl_pct * 100).toFixed(2)}%</td>
                        <td>{c.exit_reason ?? '—'}</td>
                        <td className="text-right">{c.distance.toFixed(3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {previewData.rag_summary && <div className="mt-2 text-xs text-white/60">{previewData.rag_summary}</div>}
            </Card>

            <div className="flex justify-between">
              <button type="button" onClick={() => setStep(1)} className="rounded-sm border border-white/15 px-3 py-1 text-xs">↩ 回到 Step 1</button>
              <button
                type="button"
                disabled={execute.isPending}
                onClick={async () => {
                  const out = await execute.mutateAsync({
                    symbol, side, size_usdt: size,
                    sl_multiplier: slMult, tp_multiplier: tpMult, size_multiplier: sizeMult,
                  });
                  setStep(3);
                  setTimeout(() => navigate(`/v5/active?just=${out.position_id}`), 800);
                }}
                className="rounded-sm border border-accent-long/40 bg-accent-long/10 px-3 py-1 text-xs text-accent-long disabled:opacity-50"
              >
                {execute.isPending ? '开仓中…' : '确认模拟开仓 →'}
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="py-12 text-center">
            <div className="text-accent-long text-xl">✓ 模拟开仓成功</div>
            <div className="text-xs text-white/50 mt-2">即将跳转到活仓监控…</div>
          </div>
        )}
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Write `Rabbit Hunterfronted/components/pages/V5ChartPage.tsx`**

```tsx
import React from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useV5Klines } from '../../hooks/api/useV5Klines';
import { useV5SymbolEvents } from '../../hooks/api/useV5SymbolEvents';
import { useUIStore } from '../../services/store';
import { Card } from '../primitives/Card';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { IndicatorOverlayChart } from '../shared/IndicatorOverlayChart';
import type { Interval } from '../../types';

export function V5ChartPage() {
  const { symbol: encoded } = useParams();
  const [search] = useSearchParams();
  const decoded = (encoded || '').replace('_', '/');
  const interval = useUIStore(s => s.klineInterval);
  const setInterval = useUIStore(s => s.setKlineInterval);

  const klines = useV5Klines(decoded, interval, 200);
  const events = useV5SymbolEvents(decoded, 50);
  const eventId = search.get('eventId');

  return (
    <div className="space-y-4">
      <Card
        title={
          <div className="flex items-baseline gap-3">
            <span className="text-base font-medium">{decoded || '—'}</span>
            <span className="font-mono text-xs text-white/50">
              {klines.data?.klines.at(-1)
                ? `现价 $${klines.data.klines.at(-1)!.close.toFixed(4)}`
                : '—'}
            </span>
          </div>
        }
        actions={
          eventId && <span className="text-xs text-accent-info">已定位事件 #{eventId}</span>
        }
      >
        {klines.isLoading || events.isLoading ? (
          <LoadingSkeleton rows={8} />
        ) : klines.isError ? (
          <div className="text-accent-short text-sm">K 线拉取失败:{(klines.error as any)?.detail}</div>
        ) : klines.data?.klines.length === 0 ? (
          <div className="py-8 text-center text-white/40">等待 K 线数据...</div>
        ) : (
          <IndicatorOverlayChart
            klines={klines.data?.klines ?? []}
            events={events.data?.events ?? []}
            interval={interval}
            onIntervalChange={(i: Interval) => setInterval(i)}
            currentPrice={klines.data?.klines.at(-1)?.close ?? null}
          />
        )}
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Run tests + commit**

```bash
cd "Rabbit Hunterfronted"
npx vitest run tests/pages/V5ManualOrderPage.test.tsx 2>&1 | tail -10
```

Expected: 1 passed.

```bash
git add "Rabbit Hunterfronted/components/pages/V5ManualOrderPage.tsx" \
        "Rabbit Hunterfronted/components/pages/V5ChartPage.tsx" \
        "Rabbit Hunterfronted/tests/pages/V5ManualOrderPage.test.tsx"
git commit -m "feat(frontend): V5ManualOrderPage + V5ChartPage

- ManualOrder: 3-step wizard (select → preview/RAG → execute → /v5/active)
  - SHADOW-only guard; LIVE shows warning
  - User-editable SL/TP/Size multipliers on top of AI suggestion
- ChartPage: /v5/chart/:symbol with K-line + RSI/MACD sub-panels + event markers
  - Symbol uses _ for / in URL; eventId query param surfaces in title

1 RTL test."
```

---

## Phase 6: Verification

### Task 17: Full test suite + vite build + docker rebuild + tag

**Files:**
- Modify: `scripts/verify_v5_acceptance.py` (extend with frontend build check)

- [ ] **Step 1: Full frontend test run**

```bash
cd "Rabbit Hunterfronted"
npm test 2>&1 | tail -15
```

Expected: all green. Roughly: 6 + 5 + 3 + 4 + 5 + 7 + 1 + 1 + 2 + 2 + 1 + 1 + 1 ≈ 35-40 frontend tests.

- [ ] **Step 2: Vite production build**

```bash
cd "Rabbit Hunterfronted"
npx vite build 2>&1 | tail -10
```

Expected: completes with `dist/` written; no errors. Output should mention chunks and total size.

- [ ] **Step 3: Backend tests still green**

```bash
cd /Users/lizhishaoniange/Documents/Rabbit-Hunter
python3 -m pytest tests/ -q 2>&1 | tail -3
```

Expected: 125 passed (no regressions from frontend work — backend untouched).

- [ ] **Step 4: Extend `scripts/verify_v5_acceptance.py`**

Append a `verify_plan_b_frontend(...)` function and update the `__main__` block:

```python
def verify_plan_b_frontend(repo_root: str = "/app") -> bool:
    """Frontend build artifact check. Looks for dist/index.html after vite build."""
    import os
    print("\n=== Plan B-2 前端 ===")
    candidates = [
        os.path.join(repo_root, "Rabbit Hunterfronted", "dist", "index.html"),
        os.path.join(os.path.dirname(repo_root), "Rabbit Hunterfronted", "dist", "index.html"),
    ]
    for path in candidates:
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"frontend dist/index.html OK ({size} bytes) at {path}")
            return True
    print(f"frontend dist/index.html 不存在 — 跑过 vite build 了吗?候选: {candidates}")
    return False


if __name__ == "__main__":
    db = os.environ.get("DB_PATH", "data/rabbit_hunter.db")
    ok_a = verify(db)
    ok_b = verify_plan_b_backend(db)
    ok_c = verify_plan_b_frontend()
    sys.exit(0 if (ok_a and ok_b and ok_c) else 1)
```

- [ ] **Step 5: Commit verify script extension**

```bash
git add scripts/verify_v5_acceptance.py
git commit -m "chore(v5): verify_v5_acceptance covers Plan B-2 frontend dist"
```

- [ ] **Step 6: Docker frontend image rebuild + restart**

```bash
cd /Users/lizhishaoniange/Documents/Rabbit-Hunter
docker compose build --no-cache frontend 2>&1 | tail -10
docker compose up -d frontend 2>&1 | tail -5
```

Expected: build completes; container starts.

- [ ] **Step 7: Wait for the frontend to come up + sanity probe**

```bash
until curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ | grep -qE "^(200|301|302)$"; do sleep 2; done && echo "frontend up"
curl -s http://localhost:5173/ | grep -E "<title>|root" | head -3
```

Expected: 200 + html includes `<div id="root">` and `猎兔者 V5` or matches the new title.

- [ ] **Step 8: Confirm key new routes are reachable through nginx proxy**

```bash
curl -s http://localhost:5173/v5/signals | head -3
curl -s http://localhost:5173/v5/chart/H_USDT | head -3
```

Expected: same `index.html` shell each time (SPA falls back to index.html for unknown paths via nginx try_files).

- [ ] **Step 9: Manual smoke test checklist**

Open browser http://localhost:5173. Verify:
- `/v5/signals` shows the realtime signal list (or empty state — depends on SHADOW activity)
- `/v5/active` shows 0/3 slots structure
- `/v5/dashboard` shows 4 KPI cards (zeroes ok)
- `/v5/ai` shows DeepSeek + 0 RAG cases
- `/v5/config` shows 13 sliders
- `/v5/settings` shows exchange/AI/mode rows
- `/v5/manual` Step 1 lets you input symbol → preview hits backend
- `/v5/chart/H_USDT` shows the IndicatorOverlayChart structure (K-line may be empty until backend has 50 klines for H/USDT)
- WS indicator in TopBar shows 在线 (●)
- Sidebar collapse works

Document any visual issues in the commit message. UI polish is acceptable as a follow-up; the gate is "no crash, no white screen, routes reachable".

- [ ] **Step 10: Tag + push**

```bash
cd /Users/lizhishaoniange/Documents/Rabbit-Hunter
git tag v5.0.0-plan-b-frontend-shipped
git push origin main
git push origin v5.0.0-plan-b-frontend-shipped
```

Expected: push succeeds; tag visible on GitHub.

- [ ] **Step 11: Final commit referencing manual smoke results**

If the manual checklist surfaced anything, fix in a follow-up. Otherwise no extra commit needed.

---

## Self-Review

### Spec coverage check

| Spec section | Task |
|---|---|
| §2.1 directory structure | T1 (scaffold) |
| §3.1 10 API hooks | T7 |
| §3.2 Zustand store | T5 |
| §3.3 WebSocket client | T6 |
| §3.4 design tokens | T3 |
| §3.5 router | T11 |
| §4.1 V5SignalsPage | T12 |
| §4.2 V5ActivePositionsPage | T13 |
| §4.3 V5OrderHistoryPage | T13 |
| §4.4 V5DashboardPage | T14 |
| §4.5 V5AIStatusPage | T14 |
| §4.6 V5SignalHistoryPage | T12 |
| §4.7 V5StrategyConfigPage | T15 |
| §4.8 V5SettingsPage | T15 |
| §4.9 V5ManualOrderPage | T16 |
| §4.10 V5ChartPage | T16 |
| §4.11 shared components | T9 |
| §4.12 AppShell | T11 |
| §5 backend RAG-lite | already shipped in Plan B-1 (T3) |
| §6 backend routes | already shipped in Plan B-1 |
| §7.1 error matrix | T4 (ApiError) + T7 (per-page handling) + T11 (ErrorBoundary) |
| §7.2 frontend tests | T4/T5/T6/T7/T8/T9/T10/T11/T12/T13/T14/T15/T16 each include their own |
| §8.1 deployment | T17 |
| §8.3 acceptance script | T17 step 4-5 |

No gaps.

### Type consistency check

- `Side`, `Mode`, `AIProvider`, `Interval`, `OutcomeLabel`, `EventType` defined in T2; all later tasks consume the same names.
- Hook return shape for `useV5ActivePositions` declared as `CombinedActive` in T7 and consumed by `V5ActivePositionsPage` (`q.data?.combined`) and dashboard via separate hook — consistent.
- `dirty` shape in T15 (`Record<string, number>`) matches `StrategyConfigPatchRequest` in T2.
- WS event types in T2 align with `dispatchInvalidate` in T6.
- Symbol URL encoding (`_` for `/`) used consistently in T7 (`useV5Klines` / `useV5SymbolEvents`), T12 (signal "view chart" deep link), T13 (order history "图表"), T16 (V5ChartPage `useParams().symbol.replace('_', '/')`).

### Placeholder check

Searched for: TBD, TODO, "implement later", "similar to Task". None found.

### Test count summary

- T4: 6 (api.ts)
- T5: 5 (store)
- T6: 3 (WS)
- T7: 4 (signals + manual-order hooks)
- T8: 5 (primitives)
- T9: 7 (IndicatorGauges + ActivePositionCard)
- T10: 1 (IndicatorOverlayChart smoke)
- T11: 1 (AppShell)
- T12: 2 (V5SignalsPage)
- T13: 2 (V5ActivePositionsPage)
- T14: 1 (V5DashboardPage)
- T15: 1 (V5StrategyConfigPage)
- T16: 1 (V5ManualOrderPage)

**Total: 39 frontend tests** (target was ~35, on track).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-12-v5-plan-b-frontend.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks (spec compliance → code quality), fast iteration, continuous execution.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.

Which approach?



