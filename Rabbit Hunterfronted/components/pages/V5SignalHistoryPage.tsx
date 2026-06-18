import { ReactNode, useEffect, useState } from 'react';
import { useV5Signals } from '../../hooks/api/useV5Signals';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Aperture } from '../primitives/Aperture';
import { blockReasonZh } from './_signal_helpers';
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
    <div className="px-8 py-7 pb-16 flex flex-col gap-7 max-w-[1400px]">
      <PageHead now={now} count={rows.length} />

      <FilterRow block={block} onBlockChange={setBlock} />

      {q.isLoading && <LoadingSkeleton message="拉取信号历史…" />}
      {!q.isLoading && rows.length === 0 && (
        <EmptyState>无匹配记录</EmptyState>
      )}

      {rows.length > 0 && (
        <table className="w-full text-[0.78rem] border-collapse">
          <thead>
            <tr>
              <Th>时间</Th>
              <Th>币种</Th>
              <Th>方向</Th>
              <Th align="right">ΔP15m</Th>
              <Th align="right">RSI</Th>
              <Th align="right">MACD hist</Th>
              <Th>结果</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map(s => <Row key={s.id} s={s} />)}
          </tbody>
        </table>
      )}
    </div>
  );
}

function PageHead({ now, count }: { now: Date; count: number }) {
  const t = now.toLocaleTimeString('zh-CN', { hour12: false });
  return (
    <header className="grid grid-cols-[1fr_auto] items-end gap-6 pb-4 border-b border-hairline-strong">
      <div className="flex items-center gap-4">
        <Aperture size={34} rotate className="text-brass" />
        <div>
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight">信号历史</h1>
          <p className="font-cn text-ivory-40 text-[0.85rem] mt-1.5">扫描历史 · {count} 条记录</p>
        </div>
      </div>
      <div className="text-right font-mono text-[0.72rem] text-ivory-40 leading-relaxed">
        <div className="tracking-wider2 uppercase">观测时间</div>
        <div><strong className="text-ivory font-medium">{t}</strong> · UTC+8</div>
      </div>
    </header>
  );
}

function FilterRow({ block, onBlockChange }: { block: string; onBlockChange: (b: string) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-6 py-4 border border-hairline bg-gradient-to-b from-bg-base to-bg-surface">
      <div className="flex flex-col gap-1">
        <div className="font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase">结果筛选</div>
        <div className="inline-flex flex-wrap border border-hairline-strong">
          {BLOCK_OPTIONS.map(o => (
            <button
              key={o.value}
              type="button"
              onClick={() => onBlockChange(o.value)}
              className={`font-mono text-[0.7rem] tracking-wider2 px-3 py-1 border-r border-hairline-strong last:border-r-0 ${
                block === o.value
                  ? 'bg-brass-soft text-brass'
                  : 'text-ivory-70 hover:bg-white/[0.04]'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Row({ s }: { s: V5Signal }) {
  const sideCls = s.side === 'LONG'
    ? 'text-sage border-sage bg-sage-soft'
    : s.side === 'SHORT'
    ? 'text-oxblood border-oxblood bg-oxblood-soft'
    : 'text-ivory-40 border-hairline-strong';
  const deltaCls = s.delta_15m_pct >= 0 ? 'text-sage' : 'text-oxblood';

  return (
    <tr className="border-b border-hairline hover:bg-brass/[0.04]">
      <Td className="text-ivory-70">{new Date(s.created_at).toLocaleString('zh-CN', { hour12: false })}</Td>
      <Td className="text-ivory font-medium">{s.symbol}</Td>
      <Td>
        <span className={`inline-block font-mono text-[0.7rem] tracking-wider2 px-2 py-0.5 border ${sideCls}`}>{s.side ?? '—'}</span>
      </Td>
      <Td align="right" className={deltaCls}>{(s.delta_15m_pct * 100).toFixed(2)}%</Td>
      <Td align="right">{s.rsi_15m.toFixed(1)}</Td>
      <Td align="right">{s.macd_hist_15m.toFixed(4)}</Td>
      <Td>
        {s.executed
          ? <span className="inline-block font-mono text-[0.66rem] tracking-wider2 px-2 py-0.5 border border-sage text-sage bg-sage-soft uppercase">✓ 执行</span>
          : s.block_reason
          ? <span className="font-mono text-[0.78rem] text-brass">{blockReasonZh(s.block_reason)}</span>
          : <span className="text-ivory-40">—</span>}
      </Td>
    </tr>
  );
}

function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="py-14 text-center font-body italic text-ivory-40">
      <Aperture size={42} rotate="slow" className="text-ivory-25 mx-auto block mb-3" />
      <span className="opacity-60 mr-2">▌</span>{children}
    </div>
  );
}

function Th({ children, align = 'left' }: { children: ReactNode; align?: 'left' | 'right' }) {
  return (
    <th className={`text-${align} font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase font-normal px-3.5 py-2.5 border-b border-hairline`}>
      {children}
    </th>
  );
}

function Td({ children, align = 'left', className = '' }: { children: ReactNode; align?: 'left' | 'right'; className?: string }) {
  return (
    <td className={`px-3.5 py-2.5 font-mono text-[0.78rem] tabular-nums ${align === 'right' ? 'text-right' : ''} ${className}`}>
      {children}
    </td>
  );
}
