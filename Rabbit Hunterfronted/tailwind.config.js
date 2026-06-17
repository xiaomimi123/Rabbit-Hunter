/**
 * Tailwind config — V2 "Field Instrument".
 * Mirrors services/tokens.ts. Keep in sync if changed.
 */
export default {
  content: [
    './index.html',
    './App.tsx',
    './components/**/*.{ts,tsx}',
    './hooks/**/*.{ts,tsx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: {
          base: '#0F1115',
          surface: '#171A20',
          elevated: '#22272F',
          deep: '#0A0C0F',
        },
        ivory: {
          DEFAULT: '#F1ECDD',
          70: 'rgba(241, 236, 221, 0.72)',
          40: 'rgba(241, 236, 221, 0.42)',
          25: 'rgba(241, 236, 221, 0.26)',
        },
        hairline: {
          DEFAULT: 'rgba(241, 236, 221, 0.10)',
          strong: 'rgba(241, 236, 221, 0.18)',
        },
        sage: {
          DEFAULT: '#6B8568',
          soft: 'rgba(107, 133, 104, 0.18)',
        },
        oxblood: {
          DEFAULT: '#A53E32',
          soft: 'rgba(165, 62, 50, 0.18)',
        },
        brass: {
          DEFAULT: '#C9A14B',
          soft: 'rgba(201, 161, 75, 0.14)',
        },
        ink: {
          DEFAULT: '#5A7691',
          soft: 'rgba(90, 118, 145, 0.18)',
        },
        ash: '#7B8590',
        alarm: '#D03B30',
        // Legacy alias accent.long/short/warn/info kept as new semantic colors
        // so legacy class references still resolve during migration.
        accent: {
          long: '#6B8568',
          short: '#A53E32',
          warn: '#C9A14B',
          info: '#5A7691',
          primary: '#C9A14B',
        },
        risk: {
          block: '#A53E32',
          watch: '#C9A14B',
          trade: '#6B8568',
        },
      },
      fontFamily: {
        display: ['"Instrument Serif"', '"Source Han Serif SC"', '"Noto Serif SC"', 'serif'],
        body: ['"Source Serif 4"', '"Noto Serif SC"', 'serif'],
        mono: ['"Fira Code"', 'ui-monospace', 'monospace'],
        cn: ['"Noto Serif SC"', 'serif'],
        // legacy alias for any unmigrated component
        sans: ['"Source Serif 4"', '"Noto Serif SC"', 'serif'],
      },
      letterSpacing: {
        wider2: '0.18em',
        wider3: '0.22em',
        wider4: '0.26em',
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
      keyframes: {
        'aperture-sweep': {
          from: { transform: 'rotate(0deg)' },
          to: { transform: 'rotate(360deg)' },
        },
        'slot-flip': {
          '0%': { transform: 'translateY(0)', opacity: '1' },
          '50%': { transform: 'translateY(-8px)', opacity: '0' },
          '51%': { transform: 'translateY(8px)', opacity: '0' },
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
