import { ReactNode } from 'react';

interface Props {
  title: string;
  value: ReactNode;
  unit?: string;
  deltaVsYesterday?: { value: number; positiveIsGood?: boolean };
  /** Hero variant: Display Serif (Instrument Serif) at 4rem, instead of mono 3.1rem. */
  hero?: boolean;
  foot?: ReactNode;
  sparkLine?: number[];
  className?: string;
}

export function KpiCard({ title, value, unit, deltaVsYesterday, hero = false, foot, className = '' }: Props) {
  let deltaColor = 'text-ivory-40';
  let deltaSign = '─';
  if (deltaVsYesterday) {
    const isUp = deltaVsYesterday.value > 0;
    const isDown = deltaVsYesterday.value < 0;
    const positiveIsGood = deltaVsYesterday.positiveIsGood ?? true;
    if (isUp) {
      deltaSign = '▲';
      deltaColor = positiveIsGood ? 'text-sage' : 'text-oxblood';
    } else if (isDown) {
      deltaSign = '▼';
      deltaColor = positiveIsGood ? 'text-oxblood' : 'text-sage';
    }
  }

  const valueClass = hero
    ? 'font-display text-[4rem] leading-[0.92] tracking-tight'
    : 'font-mono text-[3.1rem] leading-[0.92] tracking-tight tabular-nums';

  return (
    <div className={`bg-bg-base p-[22px_24px_20px] relative ${className}`}>
      <div className="font-mono text-[0.66rem] tracking-wider3 text-ivory-40 uppercase mb-3">
        {title}
      </div>
      <div className="flex items-baseline gap-2">
        <div className={valueClass}>{value}</div>
        {unit && <span className="font-mono text-[0.7rem] text-ivory-40 tracking-wider">{unit}</span>}
      </div>
      {deltaVsYesterday && (
        <div className={`mt-3 font-mono text-[0.72rem] flex items-center gap-1.5 ${deltaColor}`}>
          <span>{deltaSign}</span>
          {Math.abs(deltaVsYesterday.value).toFixed(2)} vs 昨天
        </div>
      )}
      {foot && <div className="mt-1.5 font-cn text-[0.7rem] text-ivory-40">{foot}</div>}
    </div>
  );
}
