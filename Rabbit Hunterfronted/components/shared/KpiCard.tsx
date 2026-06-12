import React from 'react';

interface Props {
  title: string;
  value: React.ReactNode;
  unit?: string;
  deltaVsYesterday?: { value: number; positiveIsGood?: boolean };
  sparkLine?: number[];
}

export function KpiCard({ title, value, unit, deltaVsYesterday }: Props) {
  let deltaColor = 'text-white/40';
  let deltaSign = '';
  if (deltaVsYesterday) {
    const isUp = deltaVsYesterday.value > 0;
    const good = deltaVsYesterday.positiveIsGood ?? true;
    deltaColor = isUp === good ? 'text-accent-long' : 'text-accent-short';
    deltaSign = isUp ? '▴' : (deltaVsYesterday.value < 0 ? '▾' : '─');
  }
  return (
    <div className="rounded-md border border-white/10 bg-bg-surface p-4">
      <div className="text-xs text-white/50">{title}</div>
      <div className="mt-2 flex items-baseline gap-2">
        <div className="text-2xl font-mono text-white">{value}</div>
        {unit && <div className="text-xs text-white/40">{unit}</div>}
      </div>
      {deltaVsYesterday && (
        <div className={`mt-2 text-xs font-mono ${deltaColor}`}>
          {deltaSign} {Math.abs(deltaVsYesterday.value).toFixed(2)} vs 昨天
        </div>
      )}
    </div>
  );
}
