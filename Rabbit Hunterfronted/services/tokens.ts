// V2 "Field Instrument" design tokens.
// Replaces V1 cyber palette (cyan + violet + JetBrains Mono).
// Rationale: docs/visual-design-v2/design-system.md

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
      sage: '#6B8568',         // LONG / WIN / healthy
      sageSoft: 'rgba(107, 133, 104, 0.18)',
      oxblood: '#A53E32',      // SHORT / LOSS
      oxbloodSoft: 'rgba(165, 62, 50, 0.18)',
      brass: '#C9A14B',        // highlight / brand / active
      brassSoft: 'rgba(201, 161, 75, 0.14)',
      ink: '#5A7691',          // info / cool neutral
      inkSoft: 'rgba(90, 118, 145, 0.18)',
      ash: '#7B8590',          // neutral data
      alarm: '#D03B30',        // LIVE switch confirm only
    },
  },
  font: {
    display: '"Instrument Serif", "Source Han Serif SC", "Noto Serif SC", serif',
    body: '"Source Serif 4", "Noto Serif SC", serif',
    mono: '"Fira Code", ui-monospace, monospace',
    cn: '"Noto Serif SC", serif',
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
