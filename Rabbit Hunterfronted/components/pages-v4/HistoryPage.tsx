import { useNavigate } from 'react-router-dom';
import { CheckCircle, LineChart as LineIcon } from 'lucide-react';
import { useV5OrderHistory } from '../../hooks/api/useV5OrderHistory';
import { useV5Signals } from '../../hooks/api/useV5Signals';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { blockReasonZh } from '../pages/_signal_helpers';
import { cn } from '../primitives-v3/cn';

export function HistoryPage() {
  const navigate = useNavigate();
  const orders = useV5OrderHistory(200);
  const signals = useV5Signals(200, { side: null, showExecutedOnly: false });
  const trades = orders.data ?? [];
  const sigRows = signals.data?.data ?? [];

  return (
    <div className="space-y-6">
      <SectionTitle
        title="交易历史"
        subtitle="本地已平仓交易记录和信号扫描历史"
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="本地交易历史" subtitle={`${trades.length} 条已平仓`} className="!p-0" bodyClassName="!p-0">
          {orders.isLoading ? <div className="p-6"><LoadingSkeleton message="拉取交易…" /></div> : trades.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-zinc-500">暂无历史交易</div>
          ) : (
            <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
              <table className="w-full text-sm min-w-[560px]">
                <thead className="sticky top-0 bg-zinc-900/95">
                  <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                    <th className="py-2.5 pl-5 pr-2">时间</th>
                    <th className="py-2.5 px-2">币种</th>
                    <th className="py-2.5 px-2">方向</th>
                    <th className="py-2.5 px-2">原因</th>
                    <th className="py-2.5 px-2 text-right">PnL$</th>
                    <th className="py-2.5 pl-2 pr-5"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {trades.map(p => (
                    <tr key={p.id} className="hover:bg-zinc-900/40">
                      <td className="py-2.5 pl-5 pr-2 font-mono text-xs text-zinc-400 whitespace-nowrap">
                        {p.exit_time ? new Date(p.exit_time).toLocaleString('zh-CN', { hour12: false }).slice(5) : '—'}
                      </td>
                      <td className="py-2.5 px-2 font-mono text-zinc-100">{p.symbol}</td>
                      <td className="py-2.5 px-2"><StatusPill tone={p.side === 'LONG' ? 'emerald' : 'rose'}>{p.side}</StatusPill></td>
                      <td className="py-2.5 px-2"><span className="text-xs text-zinc-400">{p.exit_reason ?? '—'}</span></td>
                      <td className={cn(
                        'py-2.5 px-2 text-right font-mono tabular-nums',
                        (p.pnl_usdt ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300',
                      )}>
                        {(p.pnl_usdt ?? 0) >= 0 ? '+' : ''}{(p.pnl_usdt ?? 0).toFixed(2)}
                      </td>
                      <td className="py-2.5 pl-2 pr-5">
                        <button
                          type="button"
                          onClick={() => navigate(`/chart/${p.symbol}?eventId=${p.id}`)}
                          className="rounded-lg border border-zinc-700 p-1.5 text-zinc-400 transition hover:border-indigo-500 hover:text-indigo-300"
                        >
                          <LineIcon className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="信号扫描历史" subtitle={`${sigRows.length} 条`} className="!p-0" bodyClassName="!p-0">
          {signals.isLoading ? <div className="p-6"><LoadingSkeleton message="拉取信号…" /></div> : sigRows.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-zinc-500">暂无信号</div>
          ) : (
            <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
              <table className="w-full text-sm min-w-[560px]">
                <thead className="sticky top-0 bg-zinc-900/95">
                  <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                    <th className="py-2.5 pl-5 pr-2">时间</th>
                    <th className="py-2.5 px-2">币种</th>
                    <th className="py-2.5 px-2">方向</th>
                    <th className="py-2.5 px-2 text-right">ΔP15m</th>
                    <th className="py-2.5 px-2 text-right">RSI</th>
                    <th className="py-2.5 pl-2 pr-5">结果</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {sigRows.map(s => (
                    <tr key={s.id} className="hover:bg-zinc-900/40">
                      <td className="py-2.5 pl-5 pr-2 font-mono text-xs text-zinc-400 whitespace-nowrap">
                        {new Date(s.created_at).toLocaleString('zh-CN', { hour12: false }).slice(5)}
                      </td>
                      <td className="py-2.5 px-2 font-mono text-zinc-100">{s.symbol}</td>
                      <td className="py-2.5 px-2"><StatusPill tone={s.side === 'LONG' ? 'emerald' : s.side === 'SHORT' ? 'rose' : 'zinc'}>{s.side ?? '—'}</StatusPill></td>
                      <td className={cn('py-2.5 px-2 text-right font-mono tabular-nums', s.delta_15m_pct >= 0 ? 'text-emerald-300' : 'text-rose-300')}>
                        {(s.delta_15m_pct * 100).toFixed(2)}%
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono tabular-nums text-zinc-300">{s.rsi_15m.toFixed(1)}</td>
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
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
