import React from 'react';

interface Props {
  value: number;
  max?: number;
  label?: React.ReactNode;
  tone?: 'long' | 'short' | 'warn' | 'info';
}

const TONE: Record<NonNullable<Props['tone']>, string> = {
  long: 'bg-accent-long',
  short: 'bg-accent-short',
  warn: 'bg-accent-warn',
  info: 'bg-accent-info',
};

export function ProgressBar({ value, max = 100, label, tone = 'info' }: Props) {
  const clamped = Math.max(0, Math.min(max, value));
  const pct = max > 0 ? (clamped / max) * 100 : 0;
  return (
    <div className="w-full">
      {label && <div className="mb-1 flex justify-between text-xs text-white/60">
        <span>{label}</span><span className="font-mono">{Math.round(pct)}%</span>
      </div>}
      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={max}
        className="h-2 w-full overflow-hidden rounded-sm bg-white/5"
      >
        <div
          className={`h-full ${TONE[tone]} transition-all duration-base`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
