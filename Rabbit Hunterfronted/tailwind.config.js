/** @type {import('tailwindcss').Config} */
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
        // Trading terminal theme
        'terminal-bg': '#0a0e1a',
        'terminal-card': '#111827',
        'terminal-border': '#1f2937',
        'terminal-hover': '#1a2235',
        // Bull / Bear
        'bull': '#00d395',
        'bull-dim': 'rgba(0,211,149,0.12)',
        'bear': '#f6465d',
        'bear-dim': 'rgba(246,70,93,0.12)',
        // Primary accent
        'primary': '#7b61ff',
        'primary-dim': 'rgba(123,97,255,0.15)',
        // Text
        'text-primary': '#e5e7eb',
        'text-secondary': '#9ca3af',
        'text-muted': '#4b5563',
        // Status
        'warn': '#f59e0b',
        'info': '#3b82f6',
      },
      fontFamily: {
        'mono': ['JetBrains Mono', 'Consolas', 'monospace'],
        'sans': ['Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'bull-glow': '0 0 12px rgba(0,211,149,0.25)',
        'bear-glow': '0 0 12px rgba(246,70,93,0.25)',
        'primary-glow': '0 0 12px rgba(123,97,255,0.25)',
      },
      animation: {
        'fade-in': 'fadeIn 0.15s ease-out',
        'slide-down': 'slideDown 0.2s ease-out',
        'pulse-bull': 'pulseBull 2s cubic-bezier(0.4,0,0.6,1) infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(-4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideDown: {
          '0%': { opacity: '0', transform: 'scaleY(0.95)' },
          '100%': { opacity: '1', transform: 'scaleY(1)' },
        },
        pulseBull: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.6' },
        },
      },
    },
  },
  plugins: [],
}
