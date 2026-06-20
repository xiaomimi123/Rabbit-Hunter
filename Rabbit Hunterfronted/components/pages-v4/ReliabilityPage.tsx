import { useV5AIStatus } from '../../hooks/api/useV5AIStatus';
import { useV5ActivePositions } from '../../hooks/api/useV5ActivePositions';
import { useV5OrderHistory } from '../../hooks/api/useV5OrderHistory';
import { useV5FundingStatus } from '../../hooks/api/useV5Funding';
import { useUIStore } from '../../services/store';
import { useSystemMode } from '../../hooks/useSystemMode';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { MetricCard } from '../primitives-v3/MetricCard';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { cn } from '../primitives-v3/cn';

export function ReliabilityPage() {
  const ai = useV5AIStatus();
  const active = useV5ActivePositions();
  const orders = useV5OrderHistory(50);
  const funding = useV5FundingStatus();
  const { mode } = useSystemMode();
  const wsEvents = useUIStore(s => s.recentWsEvents);

  const aiHealthy = ai.data?.healthy ?? false;
  const positions = active.data?.combined ?? [];
  const recent = orders.data ?? [];
  const fundingExtremes = (funding.data?.data ?? []).filter(f => f.is_extreme);

  const lifecycleRows = [
    ...positions.map(p => ({ id: `o-${p.id}`, time: p.entry_time, symbol: p.symbol, side: p.side, action: 'OPEN', source: 'auto' as const })),
    ...recent.slice(0, 30).map(p => ({ id: `c-${p.id}`, time: p.exit_time, symbol: p.symbol, side: p.side, action: p.exit_reason ?? 'CLOSE', source: (p.exit_reason === 'MANUAL_USER' ? 'manual' : 'auto') as 'auto' | 'manual' })),
  ].filter(r => r.time).sort((a, b) => new Date(b.time!).getTime() - new Date(a.time!).getTime()).slice(0, 30);

  return (
    <div className="space-y-6">
      <SectionTitle
        title="执行可靠性"
        subtitle="系统状态、风险闸门、订单生命周期和安全事件"
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <MetricCard label="系统模式" value={mode ?? '—'} trend={mode === 'LIVE' ? 'down' : 'neutral'} hint={mode === 'LIVE' ? '实盘 — 真实资金' : '影子盘 — 仅记录'} />
        <MetricCard label="AI 健康" value={aiHealthy ? '在线' : '离线'} trend={aiHealthy ? 'up' : 'down'} hint={ai.data?.healthy_ratio_24h != null ? `24h ${Math.round(ai.data.healthy_ratio_24h * 100)}% healthy` : '—'} />
        <MetricCard label="活仓 / 槽位" value={`${positions.length} / 3`} hint={positions.length === 3 ? '满仓' : `${3 - positions.length} 空闲`} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="订单生命周期" subtitle={`最近 ${lifecycleRows.length} 个事件`} className="!p-0" bodyClassName="!p-0">
          {lifecycleRows.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-zinc-500">无订单事件</div>
          ) : (
            <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-zinc-900/95">
                  <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                    <th className="py-2.5 pl-5 pr-2">时间</th>
                    <th className="py-2.5 px-2">币种</th>
                    <th className="py-2.5 px-2">方向</th>
                    <th className="py-2.5 px-2">事件</th>
                    <th className="py-2.5 pl-2 pr-5">来源</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {lifecycleRows.map(r => (
                    <tr key={r.id} className="hover:bg-zinc-900/40">
                      <td className="py-2.5 pl-5 pr-2 font-mono text-xs text-zinc-400 whitespace-nowrap">
                        {r.time ? new Date(r.time).toLocaleString('zh-CN', { hour12: false }).slice(5) : '—'}
                      </td>
                      <td className="py-2.5 px-2 font-mono text-zinc-100">{r.symbol}</td>
                      <td className="py-2.5 px-2"><StatusPill tone={r.side === 'LONG' ? 'emerald' : 'rose'}>{r.side}</StatusPill></td>
                      <td className="py-2.5 px-2">
                        <span className={cn(
                          'text-xs',
                          r.action === 'OPEN' ? 'text-indigo-300' :
                          r.action === 'TP_HIT' ? 'text-emerald-300' :
                          r.action === 'SL_HIT' ? 'text-rose-300' :
                          'text-amber-300',
                        )}>{r.action}</span>
                      </td>
                      <td className="py-2.5 pl-2 pr-5">
                        <StatusPill tone={r.source === 'manual' ? 'indigo' : 'zinc'}>
                          {r.source === 'manual' ? '手动' : '自动'}
                        </StatusPill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="安全事件 / 风险信号" subtitle={`funding 极端 + WS 队列`} className="!p-0" bodyClassName="!p-0">
          <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-zinc-900/95">
                <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                  <th className="py-2.5 pl-5 pr-2">类型</th>
                  <th className="py-2.5 px-2">对象</th>
                  <th className="py-2.5 px-2">值</th>
                  <th className="py-2.5 pl-2 pr-5">严重性</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {fundingExtremes.length === 0 && wsEvents.length === 0 ? (
                  <tr><td colSpan={4} className="px-4 py-10 text-center text-sm text-zinc-500">无安全事件</td></tr>
                ) : (
                  <>
                    {fundingExtremes.slice(0, 20).map(f => (
                      <tr key={f.symbol} className="hover:bg-zinc-900/40">
                        <td className="py-2.5 pl-5 pr-2 text-xs text-amber-300">FUNDING_EXTREME</td>
                        <td className="py-2.5 px-2 font-mono text-zinc-100">{f.symbol}</td>
                        <td className="py-2.5 px-2 font-mono text-xs text-zinc-400">
                          z={(f.zscore_30d ?? 0).toFixed(2)} · {f.extreme_direction === 'long_crowded' ? '多头拥挤' : '空头拥挤'}
                        </td>
                        <td className="py-2.5 pl-2 pr-5">
                          <StatusPill tone={Math.abs(f.zscore_30d ?? 0) >= 3 ? 'rose' : 'amber'}>
                            {Math.abs(f.zscore_30d ?? 0) >= 3 ? 'HIGH' : 'MED'}
                          </StatusPill>
                        </td>
                      </tr>
                    ))}
                    {wsEvents.slice(-10).reverse().map((e, i) => (
                      <tr key={`ws-${i}`} className="hover:bg-zinc-900/40">
                        <td className="py-2.5 pl-5 pr-2 text-xs text-indigo-300">{e.type}</td>
                        <td className="py-2.5 px-2 font-mono text-zinc-100">{(e as any).symbol ?? '—'}</td>
                        <td className="py-2.5 px-2 font-mono text-xs text-zinc-400 truncate max-w-[200px]">{JSON.stringify(e).slice(0, 80)}</td>
                        <td className="py-2.5 pl-2 pr-5"><StatusPill tone="zinc">INFO</StatusPill></td>
                      </tr>
                    ))}
                  </>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
