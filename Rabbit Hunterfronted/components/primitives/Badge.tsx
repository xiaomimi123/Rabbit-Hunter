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
