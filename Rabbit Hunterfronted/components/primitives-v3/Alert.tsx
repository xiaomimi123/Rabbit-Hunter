import { ReactNode } from 'react';
import { cn } from './cn';

type Tone = 'success' | 'error' | 'warning' | 'info';

const TONE: Record<Tone, string> = {
  success: 'border-sage/40 bg-sage-soft text-sage',
  error:   'border-oxblood/40 bg-oxblood-soft text-oxblood',
  warning: 'border-brass/40 bg-brass-soft text-brass',
  info:    'border-ink/40 bg-ink-soft text-ink',
};

export function Alert({
  tone = 'info',
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'rounded-md border px-4 py-3 text-sm leading-6',
        TONE[tone],
        className,
      )}
    >
      {children}
    </div>
  );
}
