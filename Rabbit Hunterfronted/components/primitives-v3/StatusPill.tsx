import { ReactNode } from 'react';
import { cn } from './cn';

// Legacy 名称保留 (大量 callsite 用),映射到 Field Instrument tokens。
// emerald → sage (LONG / 守)、rose → oxblood (SHORT / 违)、
// amber → brass (WATCH / 注意)、indigo → ink (INFO)、zinc → neutral hairline。
type Tone = 'emerald' | 'rose' | 'amber' | 'indigo' | 'zinc';

const TONE_CLASSES: Record<Tone, string> = {
  emerald: 'bg-sage-soft text-sage border-sage/40',
  rose:    'bg-oxblood-soft text-oxblood border-oxblood/40',
  amber:   'bg-brass-soft text-brass border-brass/40',
  indigo:  'bg-ink-soft text-ink border-ink/40',
  zinc:    'bg-bg-deep text-ivory-70 border-hairline-strong',
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
        'inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider2',
        TONE_CLASSES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}
