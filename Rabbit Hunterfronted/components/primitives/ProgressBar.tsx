import { ReactNode } from 'react';

interface Props {
  value: number;
  max?: number;
  label?: ReactNode;
  tone?: 'long' | 'short' | 'warn' | 'info' | 'brass' | 'sage' | 'oxblood' | 'ink';
}

const TONE: Record<NonNullable<Props['tone']>, string> = {
  long:    'bg-sage',
  short:   'bg-oxblood',
  warn:    'bg-brass',
  info:    'bg-ink',
  brass:   'bg-brass',
  sage:    'bg-sage',
  oxblood: 'bg-oxblood',
  ink:     'bg-ink',
};

export function ProgressBar({ value, max = 100, label, tone = 'brass' }: Props) {
  const clamped = Math.max(0, Math.min(max, value));
  const pct = max > 0 ? (clamped / max) * 100 : 0;
  return (
    <div className="w-full">
      {label && (
        <div className="mb-1 flex justify-between font-mono text-[0.7rem] text-ivory-70">
          <span>{label}</span>
          <span>{Math.round(pct)}%</span>
        </div>
      )}
      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={max}
        className="h-1.5 w-full bg-white/[0.04] overflow-hidden"
      >
        <div className={`h-full ${TONE[tone]} transition-all duration-base`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
