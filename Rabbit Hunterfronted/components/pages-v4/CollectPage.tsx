import { useState } from 'react';
import { Database, Activity, AlertCircle } from 'lucide-react';
import { useV5Signals } from '../../hooks/api/useV5Signals';
import { useV5FundingStatus } from '../../hooks/api/useV5Funding';
import { useV5Dashboard } from '../../hooks/api/useV5Dashboard';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { MetricCard } from '../primitives-v3/MetricCard';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { SegmentButton } from '../primitives-v3/SegmentButton';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { MarketPage } from './MarketPage';
import { blockReasonZh } from '../pages/_signal_helpers';
import { cn } from '../primitives-v3/cn';

type Tab = 'overview' | 'market';

export function CollectPage() {
  const [tab, setTab] = useState<Tab>('overview');
  const dash = useV5Dashboard();
  const signals = useV5Signals(100, { side: null, showExecutedOnly: false });
  const funding = useV5FundingStatus();
  const fundingExtremes = (funding.data?.data ?? []).filter(f => f.is_extreme);

  const d = dash.data;
  const recentSignals = (signals.data?.data ?? []).slice(0, 30);

  return (
    <div className="space-y-6">
      <SectionTitle
        title="采集数据"
        subtitle="实时扫描 · 信号过滤 · 资金费率拥挤侦测"
        action={
          <div className="flex gap-1 rounded-2xl border border-zinc-800 bg-zinc-900/40 p-1">
            <SegmentButton active={tab === 'overview'} onClick={() => setTab('overview')}>采集概览</SegmentButton>
            <SegmentButton active={tab === 'market'} onClick={() => setTab('market')}>行情详情</SegmentButton>
          </div>
        }
      />

      {tab === 'overview' && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="24h 扫描" value={String(d?.signals_24h ?? 0)} hint="trade_scores 写入" />
            <MetricCard
              label="规则通过"
              value={String(d?.signals_passed_and ?? 0)}
              hint={d && d.signals_24h ? `${Math.round((d.signals_passed_and / d.signals_24h) * 100)}%` : '—'}
              trend={(d?.signals_passed_and ?? 0) > 0 ? 'up' : 'neutral'}
            />
            <MetricCard
              label="已开仓"
              value={String(d?.signals_executed ?? 0)}
              hint="进入 paper trades"
              trend={(d?.signals_executed ?? 0) > 0 ? 'up' : 'neutral'}
            />
            <MetricCard
              label="资金极端 (|z|≥2)"
              value={String(fundingExtremes.length)}
              hint="long/short crowded"
              trend={fundingExtremes.length > 0 ? 'down' : 'neutral'}
            />
          </div>

          <Card title="阻断原因分布" subtitle="哪些过滤器在过滤信号">
            {d ? (
              <div className="space-y-1.5">
                {Object.entries(d.signals_block_counts)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 10)
                  .map(([k, n]) => {
                    const max = Math.max(...Object.values(d.signals_block_counts));
                    const pct = max ? (n / max) * 100 : 0;
                    return (
                      <div key={k} className="flex items-center gap-3 text-xs">
                        <span className="w-44 font-mono text-zinc-400 truncate" title={k}>{k}</span>
                        <div className="flex-1 h-2 rounded-full bg-zinc-900 overflow-hidden">
                          <div className="h-full bg-rose-500/60" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="font-mono tabular-nums text-zinc-300 w-10 text-right">{n}</span>
                      </div>
                    );
                  })}
              </div>
            ) : <div className="py-6 text-center text-sm text-zinc-500">加载中…</div>}
          </Card>

          <Card title="最近 30 次扫描" subtitle="按时间倒序" className="!p-0" bodyClassName="!p-0">
            {signals.isLoading ? <div className="p-6"><LoadingSkeleton message="拉信号…" /></div> : recentSignals.length === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-zinc-500">无信号</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                      <th className="py-3 pl-5 pr-2">时间</th>
                      <th className="py-3 px-2">币种</th>
                      <th className="py-3 px-2">方向</th>
                      <th className="py-3 px-2 text-right">RSI 15m</th>
                      <th className="py-3 px-2 text-right">MACD hist</th>
                      <th className="py-3 px-2 text-right">ΔP15m</th>
                      <th className="py-3 pl-2 pr-5">状态</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60">
                    {recentSignals.map(s => (
                      <tr key={s.id} className={cn(
                        'hover:bg-zinc-900/40',
                        s.executed === 1 && 'bg-emerald-500/[0.03]',
                      )}>
                        <td className="py-2.5 pl-5 pr-2 font-mono text-xs text-zinc-400">
                          {new Date(s.created_at).toLocaleTimeString('zh-CN', { hour12: false })}
                        </td>
                        <td className="py-2.5 px-2 font-mono text-zinc-100">{s.symbol}</td>
                        <td className="py-2.5 px-2">
                          <StatusPill tone={s.side === 'LONG' ? 'emerald' : s.side === 'SHORT' ? 'rose' : 'zinc'}>
                            {s.side ?? '—'}
                          </StatusPill>
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono tabular-nums text-zinc-300">
                          {s.rsi_15m.toFixed(1)}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono tabular-nums text-zinc-300">
                          {s.macd_hist_15m.toFixed(4)}
                        </td>
                        <td className={cn(
                          'py-2.5 px-2 text-right font-mono tabular-nums',
                          s.delta_15m_pct >= 0 ? 'text-emerald-300' : 'text-rose-300',
                        )}>
                          {(s.delta_15m_pct * 100).toFixed(2)}%
                        </td>
                        <td className="py-2.5 pl-2 pr-5 text-xs">
                          {s.executed === 1 ? (
                            <StatusPill tone="emerald">已入仓</StatusPill>
                          ) : s.block_reason ? (
                            <span className="text-zinc-400">{blockReasonZh(s.block_reason)}</span>
                          ) : (
                            <StatusPill tone="indigo">通过</StatusPill>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      {tab === 'market' && <MarketPage />}
    </div>
  );
}
