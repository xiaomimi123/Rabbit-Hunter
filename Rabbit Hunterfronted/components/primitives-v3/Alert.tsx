import { ReactNode } from 'react';
import { cn } from './cn';

type Tone = 'success' | 'error' | 'warning' | 'info';

const TONE: Record<Tone, string> = {
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  error: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-100',
  info: 'border-indigo-500/30 bg-indigo-500/10 text-indigo-200',
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
        'rounded-2xl border px-4 py-3 text-sm leading-6',
        TONE[tone],
        className,
      )}
    >
      {children}
    </div>
  );
}
