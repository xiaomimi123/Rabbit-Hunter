import { ReactNode } from 'react';
import { cn, cardClassName } from './cn';

interface Props {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  className?: string;
}

export function MetricCard({ label, value, hint, trend, className }: Props) {
  return (
    <div className={cardClassName(cn('p-4', className))}>
      <div className="text-sm text-zinc-400">{label}</div>
      <div
        className={cn(
          'mt-3 text-2xl font-semibold tabular-nums',
          trend === 'up' && 'text-emerald-400',
          trend === 'down' && 'text-rose-400',
          (!trend || trend === 'neutral') && 'text-zinc-50',
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-2 text-xs text-zinc-500">{hint}</div>}
    </div>
  );
}
