import type { V5Position } from '../../types';
import { Aperture } from '../primitives/Aperture';

interface Props {
  position: V5Position;
  onClose: (p: V5Position) => void;
  onChart: (p: V5Position) => void;
}

function fmtPrice(n: number | null | undefined): string {
  if (n == null) return '—';
  if (Math.abs(n) >= 1000) return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n.toFixed(4);
}

function holdingMinutes(entryTime: string, now = Date.now()): number {
  return Math.max(0, Math.round((now - new Date(entryTime).getTime()) / 60_000));
}

function pctChange(entry: number | null | undefined, current: number | null | undefined): string {
  if (!entry || !current) return '—';
  return ((current - entry) / entry * 100).toFixed(2) + '%';
}

export function ActivePositionCard({ position, onClose, onChart }: Props) {
  const pnlPct = position.pnl_pct ?? 0;
  const pnlUsdt = position.pnl_usdt ?? 0;
  const isProfit = pnlPct > 0;
  const isShort = position.side === 'SHORT';
  const mins = position.entry_time ? holdingMinutes(position.entry_time) : 0;

  // current price estimation: entry * (1 + pnl_pct%) for LONG; entry * (1 - pnl_pct%) for SHORT
  const cur = position.entry_price != null
    ? position.entry_price * (isShort ? 1 - pnlPct / 100 : 1 + pnlPct / 100)
    : null;

  const accentBorder = isShort ? 'before:bg-oxblood' : 'before:bg-sage';
  const sideBadge = isShort
    ? 'text-oxblood border-oxblood bg-oxblood-soft'
    : 'text-sage border-sage bg-sage-soft';

  return (
    <article className={`grid grid-cols-[1fr_220px] max-[1100px]:grid-cols-1 bg-bg-base border border-hairline relative before:content-[''] before:absolute before:left-0 before:top-0 before:bottom-0 before:w-[3px] ${accentBorder}`}>
      <div className="p-5 pl-7">
        {/* head */}
        <div className="flex items-baseline gap-3.5 pb-3.5 border-b border-hairline mb-4.5">
          <h3 className="font-display text-[1.9rem] leading-none tracking-tight text-ivory">{position.symbol}</h3>
          <span className={`font-mono text-[0.7rem] tracking-wider2 px-2.5 py-0.5 border ${sideBadge}`}>
            {position.side}
          </span>
          <span className="font-mono text-[0.85rem] text-ivory-70 tracking-wide">×{position.leverage}</span>
          <span className="font-mono text-[0.7rem] text-ivory-40 tracking-wider2 px-2 py-0.5 border border-dashed border-hairline-strong">
            {position.strategy_id || 'v5_rsi_macd'}
          </span>
          <Aperture size={18} rotate="slow" className="ml-auto text-brass opacity-60" />
        </div>

        {/* price 4-col grid */}
        <div className="grid grid-cols-4 max-[640px]:grid-cols-2 gap-px bg-hairline border border-hairline mb-4">
          <Cell label="入场" value={fmtPrice(position.entry_price)} sub={position.entry_time?.slice(11, 19)} />
          <Cell
            label="当前"
            value={fmtPrice(cur)}
            sub={pctChange(position.entry_price, cur)}
            subClass={isProfit ? 'text-sage' : pnlPct < 0 ? 'text-oxblood' : ''}
          />
          <Cell label="止损" value={fmtPrice(position.sl_price)} valueClass="text-oxblood" sub={pctChange(position.entry_price, position.sl_price)} />
          <Cell label="止盈" value={fmtPrice(position.tp_price)} valueClass="text-sage" sub={pctChange(position.entry_price, position.tp_price)} />
        </div>

        {/* PnL row */}
        <div className="flex items-baseline gap-6 pt-3.5 border-t border-hairline">
          <div className={`font-display text-[2.4rem] leading-none tracking-tight ${isProfit ? 'text-sage' : pnlPct < 0 ? 'text-oxblood' : 'text-ivory-40'}`}>
            {`${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%`}
          </div>
          <div className={`font-mono text-[1.05rem] ${isProfit ? 'text-sage' : pnlPct < 0 ? 'text-oxblood' : 'text-ivory-70'}`}>
            {pnlUsdt >= 0 ? '+' : ''}{pnlUsdt.toFixed(2)} USDT
          </div>
          <div className="ml-auto text-right font-mono text-[0.75rem] text-ivory-40 leading-relaxed">
            hold · <strong className="text-ivory font-medium">{mins} min</strong><br />
            extensions · <strong className="text-ivory font-medium">{position.extension_count ?? 0} / 3</strong>
          </div>
        </div>
      </div>

      {/* side panel */}
      <div className="p-5 border-l max-[1100px]:border-l-0 max-[1100px]:border-t border-hairline bg-white/[0.015] flex flex-col gap-3.5 justify-between">
        <div className="flex flex-col gap-2.5">
          <ActionButton onClick={() => onChart(position)} glyph="⊕" label="查看图表" />
          <ActionButton onClick={() => onClose(position)} glyph="×" label="立即平仓" danger />
        </div>
      </div>
    </article>
  );
}

function Cell({ label, value, valueClass = '', sub, subClass = '' }: { label: string; value: string; valueClass?: string; sub?: string; subClass?: string }) {
  return (
    <div className="bg-bg-base p-3.5">
      <div className="font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase mb-1.5">{label}</div>
      <div className={`font-mono text-[1.25rem] tracking-tight tabular-nums text-ivory ${valueClass}`}>{value}</div>
      {sub && <div className={`font-mono text-[0.7rem] text-ivory-40 mt-1 ${subClass}`}>{sub}</div>}
    </div>
  );
}

function ActionButton({ onClick, glyph, label, danger }: { onClick: () => void; glyph: string; label: string; danger?: boolean }) {
  const baseCls = 'font-mono text-[0.78rem] tracking-wider px-4 py-2.5 border bg-transparent text-left flex items-center gap-2.5 uppercase transition-all duration-200';
  const variantCls = danger
    ? 'border-oxblood-soft text-oxblood hover:bg-oxblood-soft hover:border-oxblood'
    : 'border-hairline-strong text-ivory hover:border-brass hover:text-brass';
  return (
    <button type="button" onClick={onClick} className={`${baseCls} ${variantCls}`}>
      <span className={danger ? 'text-oxblood' : 'text-brass'}>{glyph}</span>
      <span>{label}</span>
    </button>
  );
}
