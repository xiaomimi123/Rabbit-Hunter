/**
 * Tailwind config. Values mirror services/tokens.ts — keep in sync if changed.
 */
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
        bg: {
          base: '#0F1419',
          surface: '#1A2030',
          surfaceHover: '#222B3D',
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
      fontFamily: {
        mono: ['JetBrains Mono', 'IBM Plex Mono', 'monospace'],
        sans: ['PingFang SC', 'Noto Sans CJK SC', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        sm: '4px',
        md: '8px',
        lg: '12px',
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
