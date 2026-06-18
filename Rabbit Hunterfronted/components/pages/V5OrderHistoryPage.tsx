import { ReactNode, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useV5OrderHistory } from '../../hooks/api/useV5OrderHistory';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Aperture } from '../primitives/Aperture';
import { Term } from '../shared/Term';
import type { V5Position } from '../../types';

const EXIT_BADGE: Record<string, string> = {
  TP_HIT:         'text-sage border-sage bg-sage-soft',
  SL_HIT:         'text-oxblood border-oxblood bg-oxblood-soft',
  SOFT_TARGET:    'text-brass border-brass bg-brass-soft',
  SIGNAL_REVERSE: 'text-brass border-brass bg-brass-soft',
  MANUAL_USER:    'text-ink border-ink bg-ink-soft',
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
    <div className="px-8 py-7 pb-16 flex flex-col gap-7 max-w-[1400px]">
      <PageHead now={now} count={rows.length} />

      {q.isLoading && <LoadingSkeleton message="拉取订单历史…" />}
      {!q.isLoading && rows.length === 0 && (
        <EmptyState>暂无历史订单</EmptyState>
      )}

      {rows.length > 0 && (
        <table className="w-full text-[0.78rem] border-collapse">
          <thead>
            <tr>
              <Th>平仓时间</Th>
              <Th>币种</Th>
              <Th>方向</Th>
              <Th align="right">入场</Th>
              <Th align="right">出场</Th>
              <Th>原因</Th>
              <Th align="right"><Term k="PnL">盈亏 $</Term></Th>
              <Th align="right">盈亏%</Th>
              <Th align="right">持仓</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {rows.map(p => (
              <Row
                key={p.id}
                p={p}
                onChart={() => navigate(`/v5/chart/${p.symbol}?eventId=${p.id}`)}
              />
            ))}
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
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight">订单历史</h1>
          <p className="font-cn text-ivory-40 text-[0.85rem] mt-1.5">已平仓订单 · {count} 条记录</p>
        </div>
      </div>
      <div className="text-right font-mono text-[0.72rem] text-ivory-40 leading-relaxed">
        <div className="tracking-wider2 uppercase">观测时间</div>
        <div><strong className="text-ivory font-medium">{t}</strong> · UTC+8</div>
        <div>refresh · <strong className="text-ivory font-medium">30s</strong></div>
      </div>
    </header>
  );
}

function Row({ p, onChart }: { p: V5Position; onChart: () => void }) {
  const pnlPct = p.pnl_pct ?? 0;
  const pnlUsd = p.pnl_usdt ?? 0;
  const mins = p.entry_time && p.exit_time
    ? Math.round((new Date(p.exit_time).getTime() - new Date(p.entry_time).getTime()) / 60_000)
    : 0;
  const sideCls = p.side === 'LONG'
    ? 'text-sage border-sage bg-sage-soft'
    : 'text-oxblood border-oxblood bg-oxblood-soft';
  const exitCls = p.exit_reason ? (EXIT_BADGE[p.exit_reason] || 'text-ivory-70 border-hairline-strong') : 'text-ivory-40 border-hairline';
  const pnlPctCls = pnlPct >= 0 ? 'text-sage' : 'text-oxblood';
  const pnlUsdCls = pnlUsd >= 0 ? 'text-sage' : 'text-oxblood';

  return (
    <tr className="border-b border-hairline hover:bg-brass/[0.04]">
      <Td className="text-ivory-70">{p.exit_time ? new Date(p.exit_time).toLocaleString('zh-CN', { hour12: false }) : '—'}</Td>
      <Td className="text-ivory font-medium">{p.symbol}</Td>
      <Td>
        <span className={`inline-block font-mono text-[0.7rem] tracking-wider2 px-2 py-0.5 border ${sideCls}`}>{p.side}</span>
      </Td>
      <Td align="right">{p.entry_price?.toFixed(4) ?? '—'}</Td>
      <Td align="right">{p.exit_price?.toFixed(4) ?? '—'}</Td>
      <Td>
        <span className={`inline-block font-mono text-[0.66rem] tracking-wider2 px-2 py-0.5 border uppercase ${exitCls}`}>
          {p.exit_reason ?? '—'}
        </span>
      </Td>
      <Td align="right" className={pnlUsdCls}>{pnlUsd >= 0 ? '+' : ''}{pnlUsd.toFixed(2)}</Td>
      <Td align="right" className={pnlPctCls}>{pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%</Td>
      <Td align="right" className="text-ivory-70">{mins}</Td>
      <Td>
        <button
          type="button"
          onClick={onChart}
          className="font-mono text-[0.7rem] text-brass hover:underline"
        >
          → chart
        </button>
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
