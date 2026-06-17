import { ReactNode } from 'react';

type Variant = 'long' | 'short' | 'warn' | 'info' | 'neutral' | 'brass' | 'alarm';

const STYLE: Record<Variant, string> = {
  long:    'text-sage border-sage bg-sage-soft',
  short:   'text-oxblood border-oxblood bg-oxblood-soft',
  warn:    'text-brass border-brass bg-brass-soft',
  info:    'text-ink border-ink bg-ink-soft',
  neutral: 'text-ivory-70 border-hairline-strong bg-transparent',
  brass:   'text-brass border-brass bg-brass-soft',
  alarm:   'text-alarm border-alarm bg-alarm/10',
};

interface BadgeProps {
  variant?: Variant;
  children: ReactNode;
  className?: string;
}

export function Badge({ variant = 'neutral', children, className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono text-[0.7rem] tracking-wider2 px-2.5 py-0.5 border ${STYLE[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
