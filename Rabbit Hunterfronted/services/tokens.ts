// V2 "Field Instrument" — 字体已调到正常系统栈(原先 Instrument Serif 太戏剧化)
// 调色板保留 brass/sage/oxblood — 那是设计的灵魂。
//
// V3 (2026-06-27 UI 原型落地) — 加 ink/panel/amber 一套新名,与旧名共存:
//   旧名仍服务 12 个 pages-v4 + 8 个 primitives + 3 个 layout
//   新名 (.color.v3) 服务新 4 个页面 (OverviewPage/MarketPage/AILearningPage/SettingsPage v3)
//   字体全局切到 Space Grotesk + JetBrains Mono(显式 import 在 index.css)

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
    // V3 — 2026 UI 原型: 更冷的蓝黑 + 三档 panel + 柔和 gain/loss + amber 签名
    v3: {
      ink: '#0F141B',
      panel: '#161D27',
      panel2: '#1C2530',
      raised: '#212C39',
      line: '#28333F',
      lineSoft: '#202A35',
      text: '#E8EBF0',
      muted: '#8B95A6',
      faint: '#5A6473',
      amber: '#E0A23C',
      amberDim: '#9C7330',
      amberSoft: 'rgba(224, 162, 60, 0.10)',
      gain: '#46B98A',
      gainSoft: 'rgba(70, 185, 138, 0.12)',
      loss: '#E06A52',
      lossSoft: 'rgba(224, 106, 82, 0.12)',
      info: '#5B9BD5',
      infoSoft: 'rgba(91, 155, 213, 0.12)',
      violet: '#9B7EDE',
      violetSoft: 'rgba(155, 126, 222, 0.12)',
    },
  },
  font: {
    // V3 (2026 原型): Space Grotesk 主, JetBrains Mono 数据
    display: '"Space Grotesk", system-ui, -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", "Microsoft YaHei", "Noto Sans SC", sans-serif',
    body: '"Space Grotesk", system-ui, -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", "Microsoft YaHei", "Noto Sans SC", sans-serif',
    mono: '"JetBrains Mono", "Fira Code", ui-monospace, monospace',
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
