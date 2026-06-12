// Single source of truth for V5 colors / spacing / radius / motion / fonts.

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
