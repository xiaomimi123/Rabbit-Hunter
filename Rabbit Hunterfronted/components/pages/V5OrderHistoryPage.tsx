import { ReactNode, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LineChart as LineChartIcon, TrendingUp, TrendingDown, AlertCircle } from 'lucide-react';
import { useV5OrderHistory } from '../../hooks/api/useV5OrderHistory';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Term } from '../shared/Term';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { cn } from '../primitives-v3/cn';
import type { V5Position } from '../../types';

type ExitTone = 'emerald' | 'rose' | 'amber' | 'indigo' | 'zinc';
const EXIT_TONE: Record<string, ExitTone> = {
  TP_HIT: 'emerald',
  SL_HIT: 'rose',
  SOFT_TARGET: 'amber',
  SIGNAL_REVERSE: 'amber',
  MANUAL_USER: 'indigo',
};

export function V5OrderHistoryPage() {
  const q = useV5OrderHistory(200);
  const navigate = useNavigate();
  const [now, setNow] = useState(() => new Date());
  const rows = q.data ?? [];

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-6 space-y-6">
      <SectionTitle
        title="订单历史"
        subtitle={`已平仓订单 · ${rows.length} 条记录 · ${now.toLocaleTimeString('zh-CN', { hour12: false })}`}
      />

      {q.isLoading && <LoadingSkeleton message="拉取订单历史…" />}
      {!q.isLoading && rows.length === 0 && (
        <EmptyState>暂无历史订单</EmptyState>
      )}

      {rows.length > 0 && (
        <Card className="!p-0" bodyClassName="!p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                  <th className="py-3 pl-5 pr-2 font-medium">平仓时间</th>
                  <th className="py-3 px-2 font-medium">币种</th>
                  <th className="py-3 px-2 font-medium">方向</th>
                  <th className="py-3 px-2 font-medium text-right">入场</th>
                  <th className="py-3 px-2 font-medium text-right">出场</th>
                  <th className="py-3 px-2 font-medium">原因</th>
                  <th className="py-3 px-2 font-medium text-right"><Term k="PnL">盈亏 $</Term></th>
                  <th className="py-3 px-2 font-medium text-right">盈亏%</th>
                  <th className="py-3 px-2 font-medium text-right">持仓</th>
                  <th className="py-3 pl-2 pr-5"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {rows.map(p => (
                  <Row
                    key={p.id}
                    p={p}
                    onChart={() => navigate(`/v5/chart/${p.symbol}?eventId=${p.id}`)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function Row({ p, onChart }: { p: V5Position; onChart: () => void }) {
  const pnlPct = p.pnl_pct ?? 0;
  const pnlUsd = p.pnl_usdt ?? 0;
  const mins = p.entry_time && p.exit_time
    ? Math.round((new Date(p.exit_time).getTime() - new Date(p.entry_time).getTime()) / 60_000)
    : 0;
  const sideTone = p.side === 'LONG' ? 'emerald' : 'rose';
  const exitTone = p.exit_reason ? (EXIT_TONE[p.exit_reason] || 'zinc') : 'zinc';
  const pnlCls = pnlPct >= 0 ? 'text-emerald-300' : 'text-rose-300';
  const pnlUsdCls = pnlUsd >= 0 ? 'text-emerald-300' : 'text-rose-300';

  return (
    <tr className={cn(
      'hover:bg-zinc-900/40 transition',
      pnlPct >= 0 && 'bg-emerald-500/[0.02]',
      pnlPct < 0 && 'bg-rose-500/[0.02]',
    )}>
      <td className="py-2.5 pl-5 pr-2 font-mono text-xs text-zinc-400 whitespace-nowrap">
        {p.exit_time ? new Date(p.exit_time).toLocaleString('zh-CN', { hour12: false }) : '—'}
      </td>
      <td className="py-2.5 px-2 font-mono font-medium text-zinc-100">{p.symbol}</td>
      <td className="py-2.5 px-2">
        <StatusPill tone={sideTone} icon={p.side === 'LONG' ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}>
          {p.side}
        </StatusPill>
      </td>
      <td className="py-2.5 px-2 text-right font-mono tabular-nums text-zinc-300">{p.entry_price?.toFixed(4) ?? '—'}</td>
      <td className="py-2.5 px-2 text-right font-mono tabular-nums text-zinc-300">{p.exit_price?.toFixed(4) ?? '—'}</td>
      <td className="py-2.5 px-2">
        {p.exit_reason
          ? <StatusPill tone={exitTone}>{p.exit_reason}</StatusPill>
          : <span className="text-zinc-600 text-xs">—</span>
        }
      </td>
      <td className={cn('py-2.5 px-2 text-right font-mono tabular-nums', pnlUsdCls)}>
        {pnlUsd >= 0 ? '+' : ''}{pnlUsd.toFixed(2)}
      </td>
      <td className={cn('py-2.5 px-2 text-right font-mono tabular-nums', pnlCls)}>
        {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
      </td>
      <td className="py-2.5 px-2 text-right font-mono tabular-nums text-zinc-400">{mins}min</td>
      <td className="py-2.5 pl-2 pr-5">
        <button
          type="button"
          onClick={onChart}
          title="查看图表"
          className="rounded-lg border border-zinc-700 p-1.5 text-zinc-400 transition hover:border-indigo-500 hover:text-indigo-300"
        >
          <LineChartIcon className="h-3.5 w-3.5" />
        </button>
      </td>
    </tr>
  );
}

function EmptyState({ children }: { children: ReactNode }) {
  return (
    <Card>
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-zinc-800">
          <AlertCircle className="h-5 w-5 text-zinc-500" />
        </div>
        <div className="text-sm text-zinc-400">{children}</div>
      </div>
    </Card>
  );
}
