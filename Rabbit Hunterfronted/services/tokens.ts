// V2 "Field Instrument" — 字体已调到正常系统栈(原先 Instrument Serif 太戏剧化)
// 调色板保留 brass/sage/oxblood — 那是设计的灵魂。

export const tokens = {
  color: {
    bg: {
      base: '#0F1115',
      surface: '#171A20',
      elevated: '#22272F',
      deep: '#0A0C0F',
      hairline: 'rgba(241, 236, 221, 0.10)',
      hairlineStrong: 'rgba(241, 236, 221, 0.18)',
    },
    text: {
      ivory: '#F1ECDD',
      secondary: 'rgba(241, 236, 221, 0.72)',
      muted: 'rgba(241, 236, 221, 0.42)',
      dim: 'rgba(241, 236, 221, 0.26)',
    },
    accent: {
      sage: '#6B8568',
      sageSoft: 'rgba(107, 133, 104, 0.18)',
      oxblood: '#A53E32',
      oxbloodSoft: 'rgba(165, 62, 50, 0.18)',
      brass: '#C9A14B',
      brassSoft: 'rgba(201, 161, 75, 0.14)',
      ink: '#5A7691',
      inkSoft: 'rgba(90, 118, 145, 0.18)',
      ash: '#7B8590',
      alarm: '#D03B30',
    },
  },
  font: {
    // 用系统字体栈 — macOS 默认 PingFang SC,Win 用 Microsoft YaHei,Linux 用 Noto Sans CJK
    display: 'system-ui, -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", "Microsoft YaHei", "Noto Sans SC", sans-serif',
    body: 'system-ui, -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", "Microsoft YaHei", "Noto Sans SC", sans-serif',
    mono: '"Fira Code", "JetBrains Mono", ui-monospace, monospace',
    cn: '"PingFang SC", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif',
  },
  space: { 1: 4, 2: 8, 3: 12, 4: 16, 6: 24, 8: 32, 12: 48 },
  radius: { sm: 4, md: 8, lg: 12, full: 9999 },
  motion: {
    fast: '120ms cubic-bezier(0.4, 0, 0.2, 1)',
    base: '200ms cubic-bezier(0.4, 0, 0.2, 1)',
    slow: '400ms cubic-bezier(0.4, 0, 0.2, 1)',
    aperture: '6s linear infinite',
  },
} as const;

export type Tokens = typeof tokens;
