/** @type {import('tailwindcss').Config} */
/**
 * v45 design tokens — "简约高级" 路线
 *
 * 原则：
 *   - 单一色调家族（zinc，近黑暖灰）+ 单一 accent（warm amber）
 *   - bull / bear 降饱和到 emerald / rose 500，去掉 glow
 *   - 单层 surface（不再有 card 嵌 card）
 *   - 字体：Inter 文本，JetBrains Mono 数字
 *   - 极少动效，无 neon、无 gradient text、无 blur card
 *
 * 旧 token 名（terminal-*, primary, bull, bear, text-*）保留兼容，
 * 只是把背后的 hex 值换了 — 几乎不用改组件 class。
 */
export default {
  content: [
    './index.html',
    './index.tsx',
    './App.tsx',
    './components/**/*.{js,ts,jsx,tsx}',
    './services/**/*.{js,ts,jsx,tsx}',
    './hooks/**/*.{js,ts,jsx,tsx}',
    './ui/**/*.{js,ts,jsx,tsx}',
    './layouts/**/*.{js,ts,jsx,tsx}',
    './features/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // ── 表面 ─────────────────────────────────────────
        // 旧 terminal-bg/card/border/hover 改成低色调 zinc
        'terminal-bg':     '#0a0a0a', // 画布
        'terminal-card':   '#111111', // 一级 surface
        'terminal-border': '#262626', // hairline 1px
        'terminal-hover':  '#171717',
        // ── 涨跌 ─────────────────────────────────────────
        // 降饱和 emerald / rose（不再用 binance 风格高饱和绿红）
        'bull':     '#10b981',
        'bull-dim': 'rgba(16,185,129,0.10)',
        'bear':     '#f43f5e',
        'bear-dim': 'rgba(244,63,94,0.10)',
        // ── 唯一 accent — 暖琥珀色（金属感、不刺眼）─────
        // 旧 primary 是亮紫，这里改成 amber 替换它
        'primary':     '#d4a256', // soft amber
        'primary-dim': 'rgba(212,162,86,0.10)',
        // ── 文字层级 ─────────────────────────────────────
        'text-primary':   '#fafafa',
        'text-secondary': '#a1a1aa',
        'text-muted':     '#52525b',
        // ── 状态色（保留）────────────────────────────────
        'warn': '#eab308',
        'info': '#60a5fa',
      },
      fontFamily: {
        // Inter 文本，JetBrains Mono 数字；fallback 到系统
        'mono': ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
        'sans': ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
      },
      // 极轻盈的 shadow（取代原来的彩色 glow）
      boxShadow: {
        // 旧 *-glow token 仍可被 class 引用，但都退化成几乎不可见的层级感
        'bull-glow':    'none',
        'bear-glow':    'none',
        'primary-glow': 'none',
        // 新的 elevation token
        'elev-1': '0 1px 0 0 rgba(255,255,255,0.04) inset',
        'elev-2': '0 0 0 1px rgba(255,255,255,0.06) inset',
      },
      letterSpacing: {
        'micro': '0.06em',
      },
      animation: {
        'fade-in':    'fadeIn 0.18s ease-out',
        'slide-down': 'slideDown 0.22s ease-out',
        // 去掉 pulse-bull（"心跳" 视觉太喧闹），保留但退化为缓慢淡入
        'pulse-bull': 'fadeIn 0.4s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0', transform: 'translateY(-2px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideDown: {
          '0%':   { opacity: '0', transform: 'scaleY(0.96)' },
          '100%': { opacity: '1', transform: 'scaleY(1)' },
        },
      },
    },
  },
  plugins: [],
}
