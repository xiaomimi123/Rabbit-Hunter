import { ReactNode } from 'react';
import { cn } from './cn';

type Tone = 'emerald' | 'rose' | 'amber' | 'indigo' | 'zinc';

const TONE_CLASSES: Record<Tone, string> = {
  emerald: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  rose: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  amber: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  indigo: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
  zinc: 'bg-zinc-800 text-zinc-300 border-zinc-700',
};

export function StatusPill({
  tone = 'zinc',
  children,
  icon,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide',
        TONE_CLASSES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}
