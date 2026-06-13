import React from 'react';
import type { V5Position } from '../../types';
import { Badge } from '../primitives/Badge';
import { Term } from './Term';

interface Props {
  position: V5Position;
  onClose: (p: V5Position) => void;
  onChart: (p: V5Position) => void;
}

function fmtPrice(n: number | null | undefined): string {
  if (n == null) return '—';
  if (Math.abs(n) >= 1000) return n.toFixed(2);
  if (Math.abs(n) >= 1) return n.toFixed(4);
  return n.toFixed(4);
}

function holdingMinutes(entryTime: string, now = Date.now()): number {
  return Math.round((now - new Date(entryTime).getTime()) / 60_000);
}

export function ActivePositionCard({ position, onClose, onChart }: Props) {
  const pnlPct = position.pnl_pct ?? 0;
  const pnlUsdt = position.pnl_usdt ?? 0;
  const isProfit = pnlPct > 0;
  const sideBadge = position.side === 'LONG' ? 'long' : 'short';
  const mins = position.entry_time ? holdingMinutes(position.entry_time) : 0;

  return (
    <div className="rounded-md border border-white/10 bg-bg-surface p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="text-base font-medium text-white">{position.symbol}</div>
          <Badge variant={sideBadge}>{position.side}</Badge>
          <span className="text-xs text-white/40 font-mono">×<Term k="Leverage">{position.leverage}</Term></span>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onClose(position)}
            className="rounded-sm border border-accent-short/40 px-2 py-1 text-xs text-accent-short hover:bg-accent-short/10"
          >
            立即平
          </button>
          <button
            type="button"
            onClick={() => onChart(position)}
            className="rounded-sm border border-white/15 px-2 py-1 text-xs text-white/70 hover:bg-white/5"
          >
            📈 图表
          </button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 font-mono text-sm">
        <div><div className="text-xs text-white/40">入场</div><div className="text-white">{fmtPrice(position.entry_price)}</div></div>
        <div><div className="text-xs text-white/40"><Term k="SL">SL</Term></div><div className="text-accent-short">{fmtPrice(position.sl_price)}</div></div>
        <div><div className="text-xs text-white/40"><Term k="TP">TP</Term></div><div className="text-accent-long">{fmtPrice(position.tp_price)}</div></div>
      </div>

      <div className="flex items-center justify-between text-sm">
        <div className={`font-mono ${isProfit ? 'text-accent-long' : 'text-accent-short'}`}>
          <Term k="PnL">PnL</Term>: {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}% ({pnlUsdt >= 0 ? '+' : ''}{pnlUsdt.toFixed(2)} USDT)
        </div>
        <div className="text-xs text-white/50 font-mono">
          持仓 {mins}min · <Term k="Extension">续仓</Term> {position.extension_count ?? 0}/3
        </div>
      </div>
    </div>
  );
}
