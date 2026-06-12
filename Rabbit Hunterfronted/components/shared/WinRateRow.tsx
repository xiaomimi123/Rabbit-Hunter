import React from 'react';
import type { WinRateBreakdown } from '../pages/_winrate_helpers';

interface Props {
  label: string;
  data: WinRateBreakdown;
}

export function WinRateRow({ label, data }: Props) {
  const rate = data.count > 0 ? Math.round(data.win_rate * 100) : 0;
  const tone = data.total_pnl_usdt >= 0 ? 'text-accent-long' : 'text-accent-short';
  return (
    <div className="flex items-center gap-3 py-1 text-xs">
      <div className="w-32 text-white/70">{label}</div>
      <div className="flex-1">
        <div className="relative h-4 rounded-sm bg-white/5 overflow-hidden">
          {data.count > 0 && (
            <div
              className="absolute inset-y-0 left-0 bg-accent-long/30"
              style={{ width: `${rate}%` }}
            />
          )}
          <div className="absolute inset-0 flex items-center justify-center font-mono text-[10px] text-white">
            {data.count > 0 ? `${rate}% (${data.wins}W ${data.losses}L)` : '—'}
          </div>
        </div>
      </div>
      <div className={`w-20 text-right font-mono ${tone}`}>
        {data.count > 0 ? `${data.total_pnl_usdt >= 0 ? '+' : ''}${data.total_pnl_usdt.toFixed(2)}` : '—'}
      </div>
    </div>
  );
}
