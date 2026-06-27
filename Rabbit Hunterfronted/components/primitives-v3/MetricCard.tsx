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
      <div className="text-[10px] uppercase tracking-wider2 text-ivory-40">{label}</div>
      <div
        className={cn(
          'mt-3 font-mono text-2xl font-semibold tabular-nums',
          trend === 'up' && 'text-sage',
          trend === 'down' && 'text-oxblood',
          (!trend || trend === 'neutral') && 'text-ivory',
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-2 text-xs text-ivory-40 font-mono">{hint}</div>}
    </div>
  );
}
