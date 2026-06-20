import {
  TrendingUp, TrendingDown, LineChart as LineChartIcon, X, Clock, Layers,
} from 'lucide-react';
import type { V5Position } from '../../types';
import { cn, cardClassName } from '../primitives-v3/cn';

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
  const cur = position.entry_price != null
    ? position.entry_price * (isShort ? 1 - pnlPct / 100 : 1 + pnlPct / 100)
    : null;

  const sideBadge = isShort
    ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
    : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
  const pnlTone = isProfit ? 'text-emerald-300' : pnlPct < 0 ? 'text-rose-300' : 'text-zinc-300';
  const accent = isShort ? 'before:bg-rose-500/60' : 'before:bg-emerald-500/60';

  return (
    <article className={cn(
      cardClassName(),
      'relative overflow-hidden !p-0',
      'before:absolute before:left-0 before:top-0 before:bottom-0 before:w-1',
      accent,
    )}>
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_220px]">
        <div className="p-5 pl-7">
          {/* head */}
          <div className="flex flex-wrap items-center gap-3 pb-4 border-b border-zinc-800">
            <h3 className="font-mono text-2xl font-semibold tracking-tight text-zinc-50">{position.symbol}</h3>
            <span className={cn('inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wide', sideBadge)}>
              {isShort ? <TrendingDown className="h-3 w-3" /> : <TrendingUp className="h-3 w-3" />}
              {position.side}
            </span>
            <span className="font-mono text-sm text-zinc-400">×{position.leverage}</span>
            <span className="rounded-full border border-zinc-700 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-zinc-500">
              {position.strategy_id || 'v5_rsi_macd'}
            </span>
            <div className="ml-auto flex items-center gap-3 text-[11px] text-zinc-500">
              <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {mins}min</span>
              <span className="flex items-center gap-1"><Layers className="h-3 w-3" /> {position.extension_count ?? 0}/3</span>
            </div>
          </div>

          {/* price grid */}
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Cell label="入场" value={fmtPrice(position.entry_price)} sub={position.entry_time?.slice(11, 19)} />
            <Cell
              label="当前"
              value={fmtPrice(cur)}
              sub={pctChange(position.entry_price, cur)}
              subClass={isProfit ? 'text-emerald-300' : pnlPct < 0 ? 'text-rose-300' : ''}
            />
            <Cell label="止损" value={fmtPrice(position.sl_price)} valueClass="text-rose-300" sub={pctChange(position.entry_price, position.sl_price)} />
            <Cell label="止盈" value={fmtPrice(position.tp_price)} valueClass="text-emerald-300" sub={pctChange(position.entry_price, position.tp_price)} />
          </div>

          {/* PnL */}
          <div className="mt-5 flex flex-wrap items-baseline gap-x-6 gap-y-2 border-t border-zinc-800 pt-4">
            <div className={cn('font-mono text-4xl font-semibold tracking-tight tabular-nums', pnlTone)}>
              {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
            </div>
            <div className={cn('font-mono text-base tabular-nums', pnlTone)}>
              {pnlUsdt >= 0 ? '+' : ''}{pnlUsdt.toFixed(2)} USDT
            </div>
          </div>
        </div>

        {/* side actions */}
        <div className="flex flex-col gap-2 border-t border-zinc-800 bg-zinc-950/40 p-5 xl:border-l xl:border-t-0">
          <button
            type="button"
            onClick={() => onChart(position)}
            className="flex items-center gap-2 rounded-2xl border border-zinc-700 px-3 py-2 text-sm text-zinc-200 transition hover:border-indigo-500 hover:text-indigo-200"
          >
            <LineChartIcon className="h-4 w-4" /> 查看图表
          </button>
          <button
            type="button"
            onClick={() => onClose(position)}
            className="flex items-center gap-2 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300 transition hover:border-rose-500 hover:bg-rose-500/20"
          >
            <X className="h-4 w-4" /> 立即平仓
          </button>
        </div>
      </div>
    </article>
  );
}

function Cell({ label, value, valueClass = '', sub, subClass = '' }: { label: string; value: string; valueClass?: string; sub?: string; subClass?: string }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 p-3">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={cn('mt-1 font-mono text-lg font-medium tabular-nums text-zinc-100', valueClass)}>{value}</div>
      {sub && <div className={cn('mt-0.5 font-mono text-[11px] text-zinc-500', subClass)}>{sub}</div>}
    </div>
  );
}
