# UI V2 "Field Instrument" Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing V1 "cyber" visual language (cyan + violet + cyber-grid + JetBrains Mono — flagged by frontend-design skill as AI-default) with the V2 "Field Instrument" design system (brass + sage + oxblood + Aperture mark + Instrument Serif + Fira Code) across all 12 V5 pages, while keeping all existing functionality and tests green.

**Architecture:**
- **Foundation layer** rewritten first (`tokens.ts`, `index.css`, `tailwind.config.js`, `index.html` fonts, new `Aperture.tsx` component). All downstream changes derive from these.
- **Shell** (`AppShell.tsx`, `Sidebar.tsx`, `TopBar.tsx`) rewritten next — touches every page but doesn't redesign page bodies.
- **Primitives** (`Card`, `Badge`, `KpiCard`, `ProgressBar`, `Modal`, `Tooltip`, `LoadingSkeleton`, `GaugeArc`) updated to new tokens. `HoloCard` (inline in V5AIStatusPage) gets deleted entirely.
- **Pages** migrated in priority order, each one matching the corresponding `docs/visual-design-v2/*-preview.html` reference. Flagship first to validate React translation, then hot pages, then tail pages.
- **Cleanup** drops dead CSS (`neonPulse`, `cyber-grid`, `cyan-glow`) and runs final lint/build/test.

**Tech Stack:** React 19 / TypeScript 5.8 / Vite 6 / Tailwind 3.4 / Google Fonts CDN (Instrument Serif, Source Serif 4, Fira Code, Noto Serif SC) / vitest 1 / lucide-react.

**Visual references:**
- `docs/visual-design-v2/design-system.md` — token system + rationale
- `docs/visual-design-v2/dashboard-preview.html` — Dashboard exact target
- `docs/visual-design-v2/active-positions-preview.html` — Active Positions exact target
- `docs/visual-design-v2/ai-status-preview.html` — AI Status exact target

**Working assumption:** The 12 existing `.test.tsx` files test DATA behavior, not pixel exactness. They should mostly continue passing. Any test that asserts a specific Tailwind class string (e.g. `bg-bg-surface`) is allowed to break — fix it to the new class name in that task's commit.

---

## Phase 1 — Foundation (5 tasks)

### Task 1: Add Google Fonts to index.html

**Files:**
- Modify: `Rabbit Hunterfronted/index.html`

- [ ] **Step 1:** Add `<link>` tag in `<head>` after existing meta tags:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Source+Serif+4:ital,opsz,wght@0,8..60,300..700;1,8..60,300..700&family=Fira+Code:wght@300;400;500;600&family=Noto+Serif+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
```

- [ ] **Step 2:** Verify dev server boots and fonts load without 404:

```bash
cd "Rabbit Hunterfronted" && npm run dev
```
Expected: no font-loading errors in browser console.

- [ ] **Step 3:** Commit:
```bash
git add "Rabbit Hunterfronted/index.html"
git commit -m "ui(v2): add Instrument Serif + Fira Code + Source Serif 4 + Noto Serif SC fonts"
```

---

### Task 2: Rewrite `services/tokens.ts` with V2 palette

**Files:**
- Modify: `Rabbit Hunterfronted/services/tokens.ts`

- [ ] **Step 1:** Replace entire file with:

```ts
// V2 "Field Instrument" design tokens.
// Replaces V1 cyber palette (cyan + violet + JetBrains Mono).
// Rationale: docs/visual-design-v2/design-system.md
export const tokens = {
  color: {
    bg: {
      base:        '#0F1115',
      surface:     '#171A20',
      elevated:    '#22272F',
      deep:        '#0A0C0F',
      hairline:        'rgba(241, 236, 221, 0.10)',
      hairlineStrong:  'rgba(241, 236, 221, 0.18)',
    },
    text: {
      ivory:     '#F1ECDD',
      secondary: 'rgba(241, 236, 221, 0.72)',
      muted:     'rgba(241, 236, 221, 0.42)',
      dim:       'rgba(241, 236, 221, 0.26)',
    },
    accent: {
      sage:        '#6B8568',  // LONG / WIN
      sageSoft:    'rgba(107, 133, 104, 0.18)',
      oxblood:     '#A53E32',  // SHORT / LOSS
      oxbloodSoft: 'rgba(165, 62, 50, 0.18)',
      brass:       '#C9A14B',  // highlight / brand / active
      brassSoft:   'rgba(201, 161, 75, 0.14)',
      ink:         '#5A7691',  // info
      inkSoft:     'rgba(90, 118, 145, 0.18)',
      ash:         '#7B8590',  // neutral data
      alarm:       '#D03B30',  // LIVE switch only
    },
  },
  font: {
    display: '"Instrument Serif", "Source Han Serif SC", "Noto Serif SC", serif',
    body:    '"Source Serif 4", "Noto Serif SC", serif',
    mono:    '"Fira Code", ui-monospace, monospace',
    cn:      '"Noto Serif SC", serif',
  },
  space:  { 1: 4, 2: 8, 3: 12, 4: 16, 6: 24, 8: 32, 12: 48 },
  radius: { sm: 4, md: 8, lg: 12, full: 9999 },
  motion: {
    fast:     '120ms cubic-bezier(0.4, 0, 0.2, 1)',
    base:     '200ms cubic-bezier(0.4, 0, 0.2, 1)',
    slow:     '400ms cubic-bezier(0.4, 0, 0.2, 1)',
    aperture: '6s linear infinite',
  },
} as const;
```

- [ ] **Step 2:** Grep for any code that imports `tokens.color.accent.long` / `tokens.color.accent.short` / `tokens.color.accent.warn` / `tokens.color.accent.info` / `tokens.color.accent.primary` to know what TS errors to expect:

```bash
grep -rn 'tokens\.color\.accent\.' "Rabbit Hunterfronted/" | grep -v node_modules
```

Note results — they'll be fixed in Task 3 via Tailwind, and individual references will surface as TS errors during page migration tasks. Don't fix them yet.

- [ ] **Step 3:** Commit:
```bash
git add "Rabbit Hunterfronted/services/tokens.ts"
git commit -m "ui(v2): rewrite design tokens with Field Instrument palette"
```

---

### Task 3: Rewrite `tailwind.config.js` to expose V2 tokens

**Files:**
- Modify: `Rabbit Hunterfronted/tailwind.config.js`

- [ ] **Step 1:** Replace `theme.extend` with V2 mappings. Full file:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: {
          base:      '#0F1115',
          surface:   '#171A20',
          elevated:  '#22272F',
          deep:      '#0A0C0F',
        },
        ivory: {
          DEFAULT: '#F1ECDD',
          70:      'rgba(241, 236, 221, 0.72)',
          40:      'rgba(241, 236, 221, 0.42)',
          25:      'rgba(241, 236, 221, 0.26)',
        },
        hairline: {
          DEFAULT: 'rgba(241, 236, 221, 0.10)',
          strong:  'rgba(241, 236, 221, 0.18)',
        },
        sage:    { DEFAULT: '#6B8568', soft: 'rgba(107, 133, 104, 0.18)' },
        oxblood: { DEFAULT: '#A53E32', soft: 'rgba(165, 62, 50, 0.18)' },
        brass:   { DEFAULT: '#C9A14B', soft: 'rgba(201, 161, 75, 0.14)' },
        ink:     { DEFAULT: '#5A7691', soft: 'rgba(90, 118, 145, 0.18)' },
        ash:     '#7B8590',
        alarm:   '#D03B30',
      },
      fontFamily: {
        display: ['"Instrument Serif"', '"Source Han Serif SC"', '"Noto Serif SC"', 'serif'],
        body:    ['"Source Serif 4"', '"Noto Serif SC"', 'serif'],
        mono:    ['"Fira Code"', 'ui-monospace', 'monospace'],
        cn:      ['"Noto Serif SC"', 'serif'],
      },
      letterSpacing: {
        wider2: '0.18em',
        wider3: '0.22em',
        wider4: '0.26em',
      },
      keyframes: {
        'aperture-sweep': {
          from: { transform: 'rotate(0deg)' },
          to:   { transform: 'rotate(360deg)' },
        },
        'slot-flip': {
          '0%':   { transform: 'translateY(0)', opacity: '1' },
          '50%':  { transform: 'translateY(-8px)', opacity: '0' },
          '51%':  { transform: 'translateY(8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
      animation: {
        'aperture-sweep-fast': 'aperture-sweep 6s linear infinite',
        'aperture-sweep-slow': 'aperture-sweep 12s linear infinite',
        'slot-flip': 'slot-flip 220ms cubic-bezier(0.4, 0, 0.2, 1)',
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 2:** Run build to ensure no Tailwind config syntax errors:

```bash
cd "Rabbit Hunterfronted" && npm run build 2>&1 | tail -30
```

Expected: build succeeds (existing pages may show stale colors, but compile passes).

- [ ] **Step 3:** Commit:
```bash
git add "Rabbit Hunterfronted/tailwind.config.js"
git commit -m "ui(v2): expose Field Instrument tokens via Tailwind config"
```

---

### Task 4: Rewrite `index.css` with V2 globals

**Files:**
- Modify: `Rabbit Hunterfronted/index.css`

- [ ] **Step 1:** Replace entire file with:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color-scheme: dark;
}

html, body {
  background-color: #0F1115;
  color: #F1ECDD;
  font-family: '"Source Serif 4"', '"Noto Serif SC"', serif;
  font-feature-settings: "tnum" on, "lnum" on;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  min-height: 100vh;
}

/* paper-grain — diagonal hatch at 1.2% opacity, replaces cyber-grid */
body {
  background-image:
    repeating-linear-gradient(
      45deg,
      rgba(241, 236, 221, 0.012) 0,
      rgba(241, 236, 221, 0.012) 1px,
      transparent 1px,
      transparent 6px
    );
}

/* tabular numbers — sacred */
.num, .mono {
  font-family: '"Fira Code"', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}

/* legacy ticker animation kept (used by AI page row reveal) */
@keyframes ticker-slide {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}
.ticker-row { animation: ticker-slide 200ms cubic-bezier(0.4, 0, 0.2, 1); }

/* selection */
::selection { background: rgba(201, 161, 75, 0.4); color: #F1ECDD; }

/* hairline utility (Tailwind border 1px is too thick visually for hairlines on dark) */
.hairline { border-color: rgba(241, 236, 221, 0.10); }
.hairline-strong { border-color: rgba(241, 236, 221, 0.18); }
```

- [ ] **Step 2:** Confirm dev server still hot-reloads:

```bash
cd "Rabbit Hunterfronted" && npm run build 2>&1 | tail -10
```

Expected: build succeeds.

- [ ] **Step 3:** Commit:
```bash
git add "Rabbit Hunterfronted/index.css"
git commit -m "ui(v2): replace cyber-grid + neon-pulse with paper-grain + clean base"
```

---

### Task 5: Create `Aperture` component (the signature element)

**Files:**
- Create: `Rabbit Hunterfronted/components/primitives/Aperture.tsx`
- Test: `Rabbit Hunterfronted/tests/primitives/Aperture.test.tsx`

- [ ] **Step 1:** Write the test:

```tsx
// Rabbit Hunterfronted/tests/primitives/Aperture.test.tsx
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Aperture } from '../../components/primitives/Aperture';

describe('Aperture', () => {
  it('renders an svg with concentric circles + crosshair', () => {
    const { container } = render(<Aperture size={32} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeTruthy();
    expect(svg?.getAttribute('width')).toBe('32');
    expect(container.querySelectorAll('circle').length).toBe(3);
    expect(container.querySelectorAll('line').length).toBe(4);
  });

  it('applies sweep animation class when rotate=true', () => {
    const { container } = render(<Aperture size={24} rotate />);
    expect(container.querySelector('svg')?.className.baseVal).toContain('animate-aperture-sweep');
  });

  it('passes through className', () => {
    const { container } = render(<Aperture size={20} className="text-brass" />);
    expect(container.querySelector('svg')?.className.baseVal).toContain('text-brass');
  });
});
```

- [ ] **Step 2:** Run test, expect FAIL (component not defined):

```bash
cd "Rabbit Hunterfronted" && npx vitest run tests/primitives/Aperture.test.tsx
```

- [ ] **Step 3:** Create the component:

```tsx
// Rabbit Hunterfronted/components/primitives/Aperture.tsx
import { CSSProperties } from 'react';

interface ApertureProps {
  size?: number;
  rotate?: boolean | 'slow';
  className?: string;
  style?: CSSProperties;
}

export function Aperture({ size = 24, rotate = false, className = '', style }: ApertureProps) {
  const sweep =
    rotate === 'slow'
      ? 'animate-aperture-sweep-slow'
      : rotate
        ? 'animate-aperture-sweep-fast'
        : '';

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      stroke="currentColor"
      strokeWidth="0.7"
      className={`${sweep} ${className}`.trim()}
      style={style}
      aria-hidden="true"
    >
      <circle cx="20" cy="20" r="18" />
      <circle cx="20" cy="20" r="12" />
      <circle cx="20" cy="20" r="6" />
      <line x1="20" y1="0" x2="20" y2="6" strokeWidth="1.2" />
      <line x1="20" y1="34" x2="20" y2="40" strokeWidth="1.2" />
      <line x1="0" y1="20" x2="6" y2="20" strokeWidth="1.2" />
      <line x1="34" y1="20" x2="40" y2="20" strokeWidth="1.2" />
    </svg>
  );
}
```

- [ ] **Step 4:** Re-run test, expect PASS:

```bash
cd "Rabbit Hunterfronted" && npx vitest run tests/primitives/Aperture.test.tsx
```

- [ ] **Step 5:** Commit:
```bash
git add "Rabbit Hunterfronted/components/primitives/Aperture.tsx" "Rabbit Hunterfronted/tests/primitives/Aperture.test.tsx"
git commit -m "ui(v2): add Aperture signature component (concentric crosshair)"
```

---

## Phase 2 — Shell (2 tasks)

### Task 6: Rewrite `Sidebar.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/layout/Sidebar.tsx`

- [ ] **Step 1:** Read the current file first to understand its props/structure:

```bash
cat "Rabbit Hunterfronted/components/layout/Sidebar.tsx"
```

- [ ] **Step 2:** Rewrite preserving the existing nav routes but using the V2 visual language. Match the HTML preview at `docs/visual-design-v2/dashboard-preview.html` (lines containing `class="sidebar"`).

Replace with:

```tsx
import { NavLink } from 'react-router-dom';
import { Aperture } from '../primitives/Aperture';

interface NavLinkItem {
  to: string;
  label: string;
  glyph: string;
}
interface NavGroup {
  label: string;
  items: NavLinkItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: '交易',
    items: [
      { to: '/v5/signals',   label: '实时信号', glyph: '●' },
      { to: '/v5/active',    label: '活仓监控', glyph: '●' },
      { to: '/v5/orders',    label: '订单历史', glyph: '●' },
      { to: '/v5/manual',    label: '手动开单', glyph: '●' },
    ],
  },
  {
    label: '智能',
    items: [
      { to: '/v5/ai',         label: 'AI 状态',    glyph: '◆' },
      { to: '/v5/history',    label: '信号历史',   glyph: '◆' },
      { to: '/v5/config',     label: '策略配置',   glyph: '◆' },
      { to: '/v5/reflection', label: '复盘工作台', glyph: '◆' },
    ],
  },
  {
    label: '系统',
    items: [
      { to: '/v5/dashboard', label: 'Dashboard',  glyph: '⊕' },
      { to: '/v5/settings',  label: '系统设置',   glyph: '○' },
      { to: '/v5/glossary',  label: '术语词典',   glyph: '○' },
    ],
  },
];

export function Sidebar() {
  return (
    <aside className="w-[232px] border-r border-hairline bg-bg-base py-5 flex flex-col sticky top-0 h-screen overflow-y-auto">
      <div className="px-5 pb-6 border-b border-hairline flex items-center gap-3">
        <Aperture size={28} className="text-brass" />
        <div>
          <div className="font-display text-[1.4rem] leading-none">
            猎兔者<em className="not-italic text-brass">·</em>R
          </div>
          <div className="font-mono text-[0.65rem] text-ivory-40 tracking-wider2 mt-1">
            v6.0 · FIELD
          </div>
        </div>
      </div>
      {NAV_GROUPS.map((group) => (
        <div key={group.label} className="pt-[18px] pb-[6px]">
          <div className="font-mono text-[0.62rem] tracking-wider4 text-ivory-40 px-5 pb-2 uppercase">
            {group.label}
          </div>
          {group.items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 py-1.5 px-5 font-cn text-sm border-l-2 transition-all duration-200 ${
                  isActive
                    ? 'text-brass border-brass bg-brass-soft'
                    : 'text-ivory-70 border-transparent hover:text-ivory hover:bg-white/[0.02]'
                }`
              }
            >
              <span className="font-mono text-[0.7rem] w-4 opacity-60">{item.glyph}</span>
              {item.label}
            </NavLink>
          ))}
        </div>
      ))}
    </aside>
  );
}
```

- [ ] **Step 3:** Run frontend tests:
```bash
cd "Rabbit Hunterfronted" && npx vitest run
```
Fix any sidebar-related test that asserts specific class names.

- [ ] **Step 4:** Commit:
```bash
git add "Rabbit Hunterfronted/components/layout/Sidebar.tsx"
git commit -m "ui(v2): redesign Sidebar with Aperture brand + brass active state"
```

---

### Task 7: Rewrite `TopBar.tsx` + `AppShell.tsx` tweaks

**Files:**
- Modify: `Rabbit Hunterfronted/components/layout/TopBar.tsx`
- Modify: `Rabbit Hunterfronted/components/layout/AppShell.tsx`

- [ ] **Step 1:** Read both files:

```bash
cat "Rabbit Hunterfronted/components/layout/TopBar.tsx" "Rabbit Hunterfronted/components/layout/AppShell.tsx"
```

- [ ] **Step 2:** Rewrite `TopBar.tsx` to match the HTML preview header bar. Keep its existing data hooks (mode, AI provider, WS status) — just update visuals.

Visual structure (match `docs/visual-design-v2/dashboard-preview.html` `.topbar` block):

```tsx
// Keep existing imports + hooks for mode + ws + ai status
// Visual structure:
<header className="h-14 border-b border-hairline flex items-center justify-between px-8 bg-bg-base sticky top-0 z-10">
  <div className="flex items-center gap-[18px]">
    <span className="font-mono text-[0.7rem] tracking-wider text-ivory-70">v6.0.0</span>
    {/* mode badge — shadow=brass, live=alarm */}
    <span className={`inline-flex items-center gap-1.5 font-mono text-[0.7rem] tracking-wide px-2.5 py-0.5 border ${
      mode === 'LIVE'
        ? 'border-alarm/40 text-alarm bg-alarm/10'
        : 'border-brass-soft text-brass bg-brass-soft'
    }`}>
      {mode === 'LIVE' ? '⬤' : '◐'} {mode}
    </span>
    <span className="inline-flex items-center gap-1.5 font-mono text-[0.7rem] tracking-wide px-2.5 py-0.5 border border-ink-soft text-ink bg-ink-soft">
      AI · {aiProvider}
    </span>
  </div>
  <div className="flex items-center gap-[18px]">
    <span className="inline-flex gap-2 items-center text-ivory-70 font-mono text-[0.72rem]">
      <span className={`w-1.5 h-1.5 rounded-full ${wsOnline ? 'bg-sage shadow-[0_0_6px_rgba(107,133,104,0.6)]' : 'bg-oxblood'}`}></span>
      WS · {wsOnline ? '在线' : '离线'} · {wsLatencyMs}ms
    </span>
    <span className="font-mono text-[0.7rem] tracking-wider text-ivory-70">↗ {eventCount} events</span>
  </div>
</header>
```

(Adapt the actual hook names + variable names to whatever the existing TopBar uses.)

- [ ] **Step 3:** Update `AppShell.tsx` to ensure the grid wraps Sidebar + Main correctly:

```tsx
<div className="grid grid-cols-[232px_1fr] min-h-screen bg-bg-base">
  <Sidebar />
  <div className="flex flex-col">
    <TopBar />
    <main className="flex-1 overflow-y-auto">
      <Outlet />
    </main>
  </div>
</div>
```

(Mobile: skip sidebar collapse for now — page-level responsiveness later.)

- [ ] **Step 4:** Run tests + build:
```bash
cd "Rabbit Hunterfronted" && npx vitest run && npm run build
```

- [ ] **Step 5:** Commit:
```bash
git add "Rabbit Hunterfronted/components/layout/"
git commit -m "ui(v2): redesign TopBar + AppShell grid for V2 language"
```

---

## Phase 3 — Primitives (5 tasks)

### Task 8: Rewrite `Card.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/primitives/Card.tsx`

- [ ] **Step 1:** Read current Card to understand its prop API.

- [ ] **Step 2:** Update visual to V2 — replace rounded-md + bg-bg-surface with hairline borders. Keep the existing prop API.

```tsx
import { ReactNode } from 'react';
import { Aperture } from './Aperture';

interface CardProps {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Renders an Aperture marker before the title (default true if title given). */
  withAperture?: boolean;
}

export function Card({ title, actions, children, className = '', withAperture = !!title }: CardProps) {
  return (
    <section className={`bg-bg-base ${className}`}>
      {(title || actions) && (
        <header className="flex items-center gap-3.5 pb-4 border-b border-hairline mb-5">
          {withAperture && <Aperture size={18} className="text-brass" />}
          <h3 className="font-display text-[1.4rem] tracking-tight">{title}</h3>
          {actions && (
            <div className="ml-auto font-mono text-[0.7rem] text-ivory-40 tracking-wide">
              {actions}
            </div>
          )}
        </header>
      )}
      {children}
    </section>
  );
}
```

- [ ] **Step 3:** Run all tests + build:
```bash
cd "Rabbit Hunterfronted" && npx vitest run && npm run build
```

- [ ] **Step 4:** Commit.

---

### Task 9: Rewrite `Badge.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/primitives/Badge.tsx`

- [ ] **Step 1:** Map old variants (long/short/warn/info/neutral) to V2:

```tsx
import { ReactNode } from 'react';

type Variant = 'long' | 'short' | 'warn' | 'info' | 'neutral' | 'brass' | 'alarm';
interface BadgeProps {
  variant?: Variant;
  children: ReactNode;
  className?: string;
}

const VARIANT_MAP: Record<Variant, string> = {
  long:    'text-sage border-sage bg-sage-soft',
  short:   'text-oxblood border-oxblood bg-oxblood-soft',
  warn:    'text-brass border-brass bg-brass-soft',
  info:    'text-ink border-ink bg-ink-soft',
  neutral: 'text-ivory-70 border-hairline-strong bg-transparent',
  brass:   'text-brass border-brass bg-brass-soft',
  alarm:   'text-alarm border-alarm bg-alarm/10',
};

export function Badge({ variant = 'neutral', children, className = '' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center gap-1.5 font-mono text-[0.7rem] tracking-wider2 px-2.5 py-0.5 border ${VARIANT_MAP[variant]} ${className}`}>
      {children}
    </span>
  );
}
```

- [ ] **Step 2:** Fix any tests that asserted old class strings.
- [ ] **Step 3:** Commit.

---

### Task 10: Rewrite `KpiCard.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/shared/KpiCard.tsx`

- [ ] **Step 1:** Add a `hero` variant for the Dashboard's 1.7fr-wide first KPI (uses Display Serif font). Default variant uses Fira Code mono. Match preview HTML `.kpi` and `.kpi-value.big` styles.

```tsx
import { ReactNode } from 'react';

interface KpiCardProps {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  /** Direction & magnitude of change; positiveIsGood flips coloring. */
  delta?: { value: string; positiveIsGood?: boolean; direction: 'up' | 'down' | 'flat' };
  foot?: ReactNode;
  /** Hero variant uses Display Serif at 4rem instead of Fira Code 3.1rem. */
  hero?: boolean;
  className?: string;
}

export function KpiCard({ label, value, unit, delta, foot, hero, className = '' }: KpiCardProps) {
  const valueClass = hero
    ? 'font-display text-[4rem] leading-[0.92] tracking-tight'
    : 'font-mono text-[3.1rem] leading-[0.92] tracking-tight tabular-nums';

  let deltaClass = 'text-ivory-40';
  let arrow = '─';
  if (delta) {
    if (delta.direction === 'up')   { arrow = '▲'; deltaClass = delta.positiveIsGood === false ? 'text-oxblood' : 'text-sage'; }
    if (delta.direction === 'down') { arrow = '▼'; deltaClass = delta.positiveIsGood === false ? 'text-sage' : 'text-oxblood'; }
  }

  return (
    <div className={`p-[22px_24px_20px] bg-bg-base relative ${className}`}>
      <div className="font-mono text-[0.66rem] tracking-wider3 text-ivory-40 uppercase mb-3">{label}</div>
      <div className={valueClass}>
        {value}
        {unit && <span className="font-mono text-[0.7rem] text-ivory-40 ml-2 tracking-wider">{unit}</span>}
      </div>
      {delta && (
        <div className={`mt-3 font-mono text-[0.72rem] flex items-center gap-1.5 ${deltaClass}`}>
          <span>{arrow}</span> {delta.value}
        </div>
      )}
      {foot && <div className="mt-1.5 font-cn text-[0.7rem] text-ivory-40">{foot}</div>}
    </div>
  );
}
```

- [ ] **Step 2:** Fix tests; commit.

---

### Task 11: Rewrite `ProgressBar.tsx` + `LoadingSkeleton.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/primitives/ProgressBar.tsx`
- Modify: `Rabbit Hunterfronted/components/primitives/LoadingSkeleton.tsx`

- [ ] **Step 1:** ProgressBar — replace gradient fills with solid accent fills + thin track:

```tsx
interface ProgressBarProps {
  value: number;          // 0..1
  variant?: 'brass' | 'sage' | 'ink' | 'oxblood';
  height?: number;        // px, default 6
  className?: string;
}
const VARIANT_FILL: Record<NonNullable<ProgressBarProps['variant']>, string> = {
  brass: 'bg-brass', sage: 'bg-sage', ink: 'bg-ink', oxblood: 'bg-oxblood',
};
export function ProgressBar({ value, variant = 'brass', height = 6, className = '' }: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, value * 100));
  return (
    <div className={`bg-white/[0.04] relative ${className}`} style={{ height }}>
      <div className={`absolute inset-y-0 left-0 ${VARIANT_FILL[variant]}`} style={{ width: `${pct}%` }} />
    </div>
  );
}
```

- [ ] **Step 2:** LoadingSkeleton — use Aperture-sweep wireframe instead of pulsing gray bars:

```tsx
import { Aperture } from './Aperture';
export function LoadingSkeleton({ message = '加载中…' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-ivory-40">
      <Aperture size={42} rotate className="text-ivory-25 mb-3" />
      <div className="font-body italic text-[0.85rem]">{message}</div>
    </div>
  );
}
```

- [ ] **Step 3:** Commit both as one task.

---

### Task 12: Update `Modal.tsx`, `Tooltip.tsx`, `GaugeArc.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/primitives/Modal.tsx`
- Modify: `Rabbit Hunterfronted/components/primitives/Tooltip.tsx`
- Modify: `Rabbit Hunterfronted/components/primitives/GaugeArc.tsx`

- [ ] **Step 1:** Modal — replace rounded-lg + drop-shadow with hairline frame; backdrop stays dark:

```tsx
// Body wrapper
<div className="fixed inset-0 z-50 bg-black/72 backdrop-blur-sm grid place-items-center" onClick={onClose}>
  <div onClick={(e) => e.stopPropagation()}
       className="bg-bg-base border border-hairline-strong min-w-[400px] max-w-[600px] p-6 flex flex-col gap-4">
    {title && (
      <div className="flex items-center gap-3 pb-3 border-b border-hairline">
        <Aperture size={18} className="text-brass" />
        <h3 className="font-display text-[1.4rem]">{title}</h3>
      </div>
    )}
    {children}
  </div>
</div>
```

- [ ] **Step 2:** Tooltip — change background to `bg-bg-elevated`, border to `hairline-strong`, text serif body 0.78rem.

- [ ] **Step 3:** GaugeArc — change track color to `rgba(241,236,221,0.06)`, fill arc to `var(--sage)` if value in healthy range, `var(--oxblood)` if extreme. Keep SVG geometry, change colors only.

- [ ] **Step 4:** Run tests + build. Fix breakage. Commit.

---

## Phase 4 — Flagship Page (1 task)

### Task 13: Rewrite `V5DashboardPage.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/pages/V5DashboardPage.tsx`

- [ ] **Step 1:** Read current page to understand its hooks + data flow. Document them.

- [ ] **Step 2:** Rewrite the page body to match `docs/visual-design-v2/dashboard-preview.html` 1:1 in visual structure, but using:
  - existing data hooks (`useDashboard24h`, `useSetupPerformance`, etc.)
  - the new `Aperture`, `Card`, `KpiCard` (hero variant for win rate), `Badge`, `ProgressBar` primitives

Structure (page outline):

```tsx
return (
  <div className="px-8 py-7 pb-16 flex flex-col gap-7 max-w-[1400px]">

    {/* page-head */}
    <header className="grid grid-cols-[1fr_auto] items-end gap-6 pb-4.5 border-b border-hairline-strong">
      <div className="flex items-center gap-4">
        <Aperture size={34} rotate className="text-brass" />
        <div>
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight">Dashboard</h1>
          <p className="font-cn text-ivory-40 text-[0.85rem] mt-1.5">24 小时观测日志 · field journal</p>
        </div>
      </div>
      <div className="text-right font-mono text-[0.72rem] text-ivory-40 leading-relaxed">
        <div>OBSERVATION TIME</div>
        <div><strong className="text-ivory font-medium">{currentTime}</strong> · UTC+8</div>
        <div>data refresh in <strong className="text-ivory font-medium">{secondsUntilRefresh}s</strong></div>
      </div>
    </header>

    {/* KPI row 1.7:1:1:1 */}
    <section className="grid grid-cols-[1.7fr_1fr_1fr_1fr] gap-px bg-hairline border border-hairline">
      <KpiCard hero label="Win Rate · 7d" value={`${winRate}%`} delta={...} foot={`${trades} trades observed`} />
      <KpiCard label="Net PnL" value={netPnl} unit="USDT" delta={...} />
      <KpiCard label="Hold · avg" value={avgHoldMin} unit="min" delta={...} />
      <KpiCard label="Active · slots" value={activeCount} unit={`/ ${MAX_CONCURRENT}`} foot={<SlotStrip />} />
    </section>

    {/* Each section: 1fr + 200px marginalia grid */}
    <Section title="Signal Funnel" meta="24h · click to drill" marginalia={<>78% washed at conjunction. ...</>}>
      <FunnelRows data={funnel} />
    </Section>
    <Section title="Outcome Breakdown" meta={`7d window · n=${n}`} marginalia={...}>
      <BreakdownGrid bySide={...} byStrategy={...} byExit={...} aggregate={...} />
    </Section>
    <Section title="PnL Trajectory" meta="cumulative · 24h" marginalia={...}>
      <PnlSparkSvg data={pnlSeries} />
    </Section>
    <Section title="Setup Type · 7d Performance" meta="funding dimension highlighted" marginalia={...}>
      <SetupBreakdownTable rows={setupRows} />
    </Section>
    <Section title="Block Reason Distribution" meta="why scans didn't trade" marginalia={...}>
      <BlockRows data={blockReasons} />
    </Section>

  </div>
);
```

Where `Section` is a reusable inline component for the marginalia layout:

```tsx
function Section({ title, meta, marginalia, children }: ...) {
  return (
    <section className="grid grid-cols-[1fr_200px] gap-7 items-start max-[1100px]:grid-cols-1">
      <div>
        <header className="flex items-center gap-3.5 pb-4 border-b border-hairline mb-5">
          <Aperture size={18} className="text-brass" />
          <h2 className="font-display text-[1.4rem] tracking-tight">{title}</h2>
          {meta && <span className="ml-auto font-mono text-[0.7rem] text-ivory-40 tracking-wide">{meta}</span>}
        </header>
        {children}
      </div>
      <aside className="font-body italic text-[0.78rem] text-ivory-40 leading-snug pt-[50px] border-l border-hairline pl-4.5 max-[1100px]:border-l-0 max-[1100px]:border-t max-[1100px]:pt-3.5 max-[1100px]:pl-0">
        {marginalia}
      </aside>
    </section>
  );
}
```

Sub-components (`FunnelRows`, `BreakdownGrid`, `PnlSparkSvg`, `SetupBreakdownTable`, `BlockRows`, `SlotStrip`) live inline at the bottom of the page file — each is small and not reused.

The implementer should reference the preview HTML for exact CSS class equivalents — every CSS class in the preview has a Tailwind counterpart in the new config.

- [ ] **Step 3:** Run tests + dev server. Visit `http://localhost:3000/v5/dashboard`. Verify visual matches `docs/visual-design-v2/dashboard-preview.html` (open both side-by-side in browser tabs).

- [ ] **Step 4:** Commit.

---

## Phase 5 — Hot Pages (3 tasks)

### Task 14: Rewrite `V5ActivePositionsPage.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/pages/V5ActivePositionsPage.tsx`

Reference: `docs/visual-design-v2/active-positions-preview.html`

- [ ] **Step 1:** Read current page.
- [ ] **Step 2:** Build the counter-strip + per-position card matching the HTML preview. Position card structure:
  - 3px left border (sage for LONG, oxblood for SHORT)
  - header row (symbol display serif + side badge + lev + strategy + slow-rotating aperture)
  - 4-col price-grid (Entry / Current / SL / TP) with sage/oxblood for SL+TP
  - SL→entry→now→TP track bar with brass now-marker
  - PnL row: Display Serif pct + Fira Code USDT + meta right
  - Side panel: 3 buttons (View Chart / Extend SL / Close Now) + AI/Manual note
  - Empty slot: dashed border with slow-rotating Aperture + italic message

- [ ] **Step 3:** Confirm close-position modal still works.
- [ ] **Step 4:** Test + commit.

---

### Task 15: Rewrite `V5AIStatusPage.tsx` (DELETE HoloCard)

**Files:**
- Modify: `Rabbit Hunterfronted/components/pages/V5AIStatusPage.tsx`

Reference: `docs/visual-design-v2/ai-status-preview.html`

- [ ] **Step 1:** Read current page; locate the inline `HoloCard` component definition. It will be deleted entirely.
- [ ] **Step 2:** Remove ALL cyber styling references:
  - `cyber-grid` class
  - `neon-pulse` class
  - `cyan-glow` class
  - `HoloCard` component (delete its definition + replace usages with new Triplet card)
- [ ] **Step 3:** Build the new page per HTML preview:
  - **Triplet** (Provider / RAG / Decisions) — single bordered grid, status pill (sage=online, brass=indexed), Display Serif value + sparkline at bottom
  - **Decision Stream** — table with exec=sage / rej=oxblood 2px left border via tr::before, verdict badge using `Badge` primitive
  - **Calibration** — table with drift cells colored sage/brass/oxblood
  - **Funding Heatmap** — bipolar bar (oxblood right of center for positive z, sage left of center for negative z), extreme rows brass-tinted with `✦` prefix
- [ ] **Step 4:** Verify all FundingZScoreItem and AIDecisionItem data shapes still work.
- [ ] **Step 5:** Test + commit. Commit message MUST include "remove HoloCard, neon-pulse, cyber-grid".

---

### Task 16: Rewrite `V5SignalsPage.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/pages/V5SignalsPage.tsx`

No HTML preview — design by extension of the established language. Match patterns:

- [ ] **Step 1:** Page-head with Aperture + "Signals" title + sub copy ("实时信号流 · scanning at 10s cadence")
- [ ] **Step 2:** Filter strip (replacing existing filter bar): use `counter-strip` style — chips for Side filter + "仅已入场" checkbox + summary line `过去窗口: 47 扫到 → 8 通过 AND → 2 入场`
- [ ] **Step 3:** Signal list — each row collapsed is one line in a thin-border table; expanded version reveals IndicatorGauges + ai_reasoning + actions
- [ ] **Step 4:** Empty state: Aperture sweep + italic "等待行情出现 RSI/MACD 合谋信号..."
- [ ] **Step 5:** Test + commit.

---

## Phase 6 — Mid Pages (4 tasks)

### Task 17: Rewrite `V5ReflectionPage.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/pages/V5ReflectionPage.tsx`

Three-tab page. For each:

- [ ] **Step 1:** Tab nav: brass underline for active tab, Fira Code label
- [ ] **Step 2:** ReflectionCard rebuild:
  - hairline framed
  - header: `pos ID — SYMBOL SIDE — R±X — outcome` in Fira Code, outcome=Badge
  - `setup_type:` row in mono
  - **funding row** (if z-score present): violet color V1 → **brass** color V2, prefixed with Aperture or `✦`
  - 5 questions grid 2×2+1 with `▶` markers in brass
  - footer: AI provenance + latency
- [ ] **Step 3:** Tab 2 (failure modes): table styled like calibration table
- [ ] **Step 4:** Tab 3 (sizing recs): each rec card matches the spec — current/recommended/Kelly columns + approve/reject/modify buttons
- [ ] **Step 5:** Test + commit.

---

### Task 18: Rewrite `V5OrderHistoryPage.tsx` + `V5SignalHistoryPage.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/pages/V5OrderHistoryPage.tsx`
- Modify: `Rabbit Hunterfronted/components/pages/V5SignalHistoryPage.tsx`

Both are dense tables. Apply Field Instrument table style (matches Setup Type table in dashboard preview):

- [ ] **Step 1:** Headers: Fira Code 0.62rem tracking-wider3 uppercase, hairline bottom border
- [ ] **Step 2:** Rows: Fira Code tabular-nums, hairline-divided, hover bg brass-soft/4
- [ ] **Step 3:** PnL/result columns: green=sage, red=oxblood
- [ ] **Step 4:** Exit reason badges: TP_HIT (sage Badge), SL_HIT (oxblood Badge), SIGNAL_REVERSE (brass Badge), MANUAL_USER (ink Badge)
- [ ] **Step 5:** Last column action buttons: simple text "→ chart" link in brass, no full button styling
- [ ] **Step 6:** Test + commit (one commit covers both pages).

---

### Task 19: Rewrite `V5ChartPage.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/pages/V5ChartPage.tsx`

- [ ] **Step 1:** Update Lightweight Charts colors to V2:
  - Background `#0F1115`
  - Grid lines `rgba(241, 236, 221, 0.04)`
  - Crosshair `var(--brass)` (instead of cyan)
  - Candles: up `#6B8568` (sage), down `#A53E32` (oxblood)
  - SL line: dashed oxblood, TP line: dashed sage, current price line: solid brass
  - Entry markers: brass arrow up/down (instead of green/red — preserves semantic via direction not color)
- [ ] **Step 2:** Hover data row above chart: Fira Code, hairline framed
- [ ] **Step 3:** RSI sub-panel: 70/30 reference lines in `var(--ivory-25)`, RSI curve `var(--brass)`
- [ ] **Step 4:** MACD sub-panel: histogram with sage/oxblood per bar
- [ ] **Step 5:** Test + commit.

---

### Task 20: Rewrite `V5StrategyConfigPage.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/pages/V5StrategyConfigPage.tsx`

- [ ] **Step 1:** Action bar: 3 buttons (撤销 / 预览 / 保存) in mono uppercase, brass border on hover, alarm tint for 保存 when dirty
- [ ] **Step 2:** Parameter rows: 12-col grid kept; slider track `bg-white/[0.04]`, fill `bg-brass`, thumb `bg-ivory border-brass`
- [ ] **Step 3:** NumberInput: Fira Code, hairline border, focus border brass
- [ ] **Step 4:** Changed marker: brass dot (1px circle) instead of orange
- [ ] **Step 5:** Test + commit.

---

## Phase 7 — Tail Pages (2 tasks)

### Task 21: Rewrite `V5SettingsPage.tsx` + `V5ManualOrderPage.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/pages/V5SettingsPage.tsx`
- Modify: `Rabbit Hunterfronted/components/pages/V5ManualOrderPage.tsx`

- [ ] **Step 1:** Settings — keep stacked Cards. The LIVE switch modal uses `variant='alarm'` Badge + alarm color for the confirm button (only place alarm color appears in the app).
- [ ] **Step 2:** ManualOrder — 3-step wizard. Step indicator at top: 3 circles connected by hairlines, current = brass-filled, past = sage-filled. Step 2 RAG cases table matches the Setup Type table style.
- [ ] **Step 3:** Test + commit both.

---

### Task 22: Rewrite `V5GlossaryPage.tsx`

**Files:**
- Modify: `Rabbit Hunterfronted/components/pages/V5GlossaryPage.tsx`

- [ ] **Step 1:** Page-head per pattern.
- [ ] **Step 2:** Search input: hairline border, font body italic placeholder, brass focus border.
- [ ] **Step 3:** Category sections: each title with Aperture + Display Serif. Grid of term cards: `key` in mono brass, `label` in Display Serif 1rem, `description` in body italic.
- [ ] **Step 4:** Test + commit.

---

## Phase 8 — Cleanup (1 task)

### Task 23: Final sweep + verification

- [ ] **Step 1:** Grep for any remaining cyber references and confirm none survive:

```bash
grep -rn 'neon-pulse\|cyber-grid\|cyan-glow\|holo-card\|HoloCard\|JetBrains Mono\|#22D3EE\|#A78BFA' "Rabbit Hunterfronted/" --include='*.tsx' --include='*.ts' --include='*.css' --include='*.html' | grep -v node_modules
```

Expected: zero matches. If any survive, delete them in this task.

- [ ] **Step 2:** Grep for legacy color names in `tokens.color.accent`:
```bash
grep -rn 'accent\.long\|accent\.short\|accent\.warn\|accent\.info\|accent\.primary' "Rabbit Hunterfronted/" --include='*.tsx' --include='*.ts' | grep -v node_modules
```
Expected: zero. Fix any that survived to use new keys (`sage`, `oxblood`, `brass`, `ink`).

- [ ] **Step 3:** Run full test suite:
```bash
cd "Rabbit Hunterfronted" && npx vitest run
```
Expected: all pass.

- [ ] **Step 4:** Run full build:
```bash
cd "Rabbit Hunterfronted" && npm run build
```
Expected: succeeds with no errors.

- [ ] **Step 5:** Manual smoke test in browser — click through all 12 pages, confirm:
  - No console errors
  - Sidebar Aperture brand mark renders
  - Each page has a rotating Aperture in its header
  - Numbers are Fira Code tabular
  - Headings are Instrument Serif
  - No cyan or violet anywhere
  - Brass highlights on hover/active/extreme rows

- [ ] **Step 6:** Final commit + push:
```bash
git add -A
git commit -m "ui(v2): final cleanup — drop all cyber refs, full V2 active"
git push origin main
```

---

## Self-Review

- ✓ All 12 pages covered (Tasks 13–22)
- ✓ Foundation (tokens / fonts / CSS / Aperture) covered Tasks 1–5
- ✓ Shell covered Tasks 6–7
- ✓ All 8 primitives covered Tasks 8–12 (Card, Badge, KpiCard, ProgressBar, LoadingSkeleton, Modal, Tooltip, GaugeArc)
- ✓ HoloCard deletion explicit in Task 15
- ✓ Cleanup verification explicit in Task 23
- ✓ Each task has concrete file paths
- ✓ Code blocks for new primitives/components
- ✓ Visual references point to existing HTML preview files for pages
- ✓ TDD applied to Aperture (Task 5); other tasks use build+test verification (UI refactor doesn't need new tests beyond what exists)

**Known limitation:** Tasks 14, 16–22 reference the HTML preview pattern rather than including full TSX code. This is intentional — the design system is fully specified in Phase 1–4 by code; subsequent pages just compose primitives. The implementer can match patterns by reading the HTML.

**Open question:** Mobile responsive breakpoints not detailed per page. Defer mobile polish to a follow-up plan after V2 desktop is solid.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-06-18-ui-v2-field-instrument-migration.md`. Recommended execution: **Subagent-Driven Development** (fresh implementer per task + two-stage review). 23 tasks, estimated 4-6 hours of agent time depending on review loops.

Sequencing: Phases 1→8 strictly sequential. Within a phase, tasks are sequential (each task may import primitives from earlier tasks).
