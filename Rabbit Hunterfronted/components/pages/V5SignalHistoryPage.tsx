import { ReactNode, useEffect, useState } from 'react';
import { CheckCircle, TrendingUp, TrendingDown, AlertCircle, Filter } from 'lucide-react';
import { useV5Signals } from '../../hooks/api/useV5Signals';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { blockReasonZh } from './_signal_helpers';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { cn } from '../primitives-v3/cn';
import type { V5Signal } from '../../types';

const BLOCK_OPTIONS = [
  { value: 'ALL', label: '全部' },
  { value: 'EXECUTED', label: '✓ 已执行' },
  { value: 'NOT_RSI_AND_MACD', label: 'RSI/MACD 未合谋' },
  { value: 'NOT_DELTA_15M', label: 'ΔP15m 不足' },
  { value: 'MAX_CONCURRENT_POSITIONS', label: '活仓上限' },
  { value: 'AI_REJECTED', label: 'AI 否决' },
];

export function V5SignalHistoryPage() {
  const [block, setBlock] = useState('ALL');
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const q = useV5Signals(200, { blockReason: block === 'ALL' || block === 'EXECUTED' ? null : block });
  const all = q.data?.data ?? [];
  const rows = block === 'EXECUTED' ? all.filter(s => s.executed === 1) : all;

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-6 space-y-6">
      <SectionTitle
        title="信号历史"
        subtitle={`扫描历史 · ${rows.length} 条记录 · ${now.toLocaleTimeString('zh-CN', { hour12: false })}`}
      />

      <Card className="!p-3" bodyClassName="flex flex-wrap items-center gap-2">
        <Filter className="h-4 w-4 text-zinc-500 ml-1" />
        <span className="text-xs text-zinc-500 mr-1">结果筛选</span>
        {BLOCK_OPTIONS.map(o => (
          <button
            key={o.value}
            type="button"
            onClick={() => setBlock(o.value)}
            className={cn(
              'rounded-full px-3 py-1 text-xs transition',
              block === o.value
                ? 'bg-indigo-500/15 text-indigo-300 border border-indigo-500/30'
                : 'text-zinc-400 hover:text-zinc-100 border border-transparent',
            )}
          >
            {o.label}
          </button>
        ))}
      </Card>

      {q.isLoading && <LoadingSkeleton message="拉取信号历史…" />}
      {!q.isLoading && rows.length === 0 && <EmptyState>无匹配记录</EmptyState>}

      {rows.length > 0 && (
        <Card className="!p-0" bodyClassName="!p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                  <th className="py-3 pl-5 pr-2 font-medium">时间</th>
                  <th className="py-3 px-2 font-medium">币种</th>
                  <th className="py-3 px-2 font-medium">方向</th>
                  <th className="py-3 px-2 font-medium text-right">ΔP15m</th>
                  <th className="py-3 px-2 font-medium text-right">RSI</th>
                  <th className="py-3 px-2 font-medium text-right">MACD hist</th>
                  <th className="py-3 pl-2 pr-5 font-medium">结果</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {rows.map(s => <Row key={s.id} s={s} />)}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function Row({ s }: { s: V5Signal }) {
  const sideTone: 'emerald' | 'rose' | 'zinc' = s.side === 'LONG' ? 'emerald' : s.side === 'SHORT' ? 'rose' : 'zinc';
  const deltaCls = s.delta_15m_pct >= 0 ? 'text-emerald-300' : 'text-rose-300';

  return (
    <tr className="hover:bg-zinc-900/40">
      <td className="py-2.5 pl-5 pr-2 font-mono text-xs text-zinc-400 whitespace-nowrap">
        {new Date(s.created_at).toLocaleString('zh-CN', { hour12: false })}
      </td>
      <td className="py-2.5 px-2 font-mono font-medium text-zinc-100">{s.symbol}</td>
      <td className="py-2.5 px-2">
        <StatusPill tone={sideTone} icon={s.side === 'LONG' ? <TrendingUp className="h-2.5 w-2.5" /> : s.side === 'SHORT' ? <TrendingDown className="h-2.5 w-2.5" /> : undefined}>
          {s.side ?? '—'}
        </StatusPill>
      </td>
      <td className={cn('py-2.5 px-2 text-right font-mono tabular-nums', deltaCls)}>
        {(s.delta_15m_pct * 100).toFixed(2)}%
      </td>
      <td className="py-2.5 px-2 text-right font-mono tabular-nums text-zinc-300">{s.rsi_15m.toFixed(1)}</td>
      <td className="py-2.5 px-2 text-right font-mono tabular-nums text-zinc-300">{s.macd_hist_15m.toFixed(4)}</td>
      <td className="py-2.5 pl-2 pr-5">
        {s.executed === 1 ? (
          <StatusPill tone="emerald" icon={<CheckCircle className="h-2.5 w-2.5" />}>执行</StatusPill>
        ) : s.block_reason ? (
          <span className="text-xs text-zinc-400">{blockReasonZh(s.block_reason)}</span>
        ) : (
          <span className="text-xs text-zinc-600">—</span>
        )}
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
