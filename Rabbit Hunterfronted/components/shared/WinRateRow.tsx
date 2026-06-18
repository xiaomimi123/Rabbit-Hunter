import type { WinRateBreakdown } from '../pages/_winrate_helpers';

interface Props {
  label: string;
  data: WinRateBreakdown;
}

export function WinRateRow({ label, data }: Props) {
  const rate = data.count > 0 ? Math.round(data.win_rate * 100) : 0;
  const tone = data.total_pnl_usdt >= 0 ? 'text-sage' : 'text-oxblood';
  return (
    <div className="grid grid-cols-[110px_1fr_80px] items-center py-2 gap-3.5 text-[0.78rem] border-b border-hairline">
      <span className="font-cn text-ivory-70">{label}</span>
      <div className="relative h-2.5 bg-white/[0.04] overflow-hidden">
        {data.count > 0 && (
          <span
            className="absolute inset-y-0 left-0 bg-sage-soft border-r border-sage"
            style={{ width: `${rate}%` }}
          />
        )}
      </div>
      <div className="font-mono tabular-nums text-right text-[0.78rem] text-ivory-70">
        {data.count > 0
          ? <>{rate}% · <span className={tone}>{data.total_pnl_usdt >= 0 ? '+' : ''}{data.total_pnl_usdt.toFixed(1)}</span></>
          : '—'}
      </div>
    </div>
  );
}
