import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { TrendingUp, TrendingDown, Hand, LineChart as LineIcon } from 'lucide-react';
import { useV5ActivePositions } from '../../hooks/api/useV5ActivePositions';
import { useV5OrderHistory } from '../../hooks/api/useV5OrderHistory';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { MetricCard } from '../primitives-v3/MetricCard';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { SegmentButton } from '../primitives-v3/SegmentButton';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Sparkline } from '../primitives/Sparkline';
import { cn } from '../primitives-v3/cn';

type Tab = 'overview' | 'history';

export function PortfolioPage() {
  const navigate = useNavigate();
  const active = useV5ActivePositions();
  const history = useV5OrderHistory(200);
  const [tab, setTab] = useState<Tab>('overview');

  const positions = active.data?.combined ?? [];
  const closed = history.data ?? [];
  const unrealized = positions.reduce((a, p) => a + (p.pnl_usdt ?? 0), 0);
  const realized = closed.reduce((a, p) => a + (p.pnl_usdt ?? 0), 0);
  const wins = closed.filter(p => (p.pnl_pct ?? 0) > 0).length;
  const winRate = closed.length ? wins / closed.length : 0;

  const equityCurve = (() => {
    let cum = 0;
    return closed.slice().reverse().map(p => { cum += (p.pnl_usdt ?? 0); return cum; });
  })();

  return (
    <div className="space-y-6">
      <SectionTitle
        title="投资组合"
        subtitle="持仓风险、未实现/已实现盈亏、整体表现"
        action={
          <button
            type="button"
            onClick={() => navigate('/manual')}
            className="inline-flex items-center gap-1.5 rounded-2xl bg-brass px-4 py-2 text-sm font-medium text-white transition hover:bg-brass"
          >
            <Hand className="h-4 w-4" /> 手动开单
          </button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="活仓数" value={String(positions.length)} hint={`${positions.filter(p => p.side === 'LONG').length} 多 · ${positions.filter(p => p.side === 'SHORT').length} 空`} />
        <MetricCard label="未实现 PnL" value={`${unrealized >= 0 ? '+' : ''}${unrealized.toFixed(2)}`} trend={unrealized >= 0 ? 'up' : 'down'} hint="USDT" />
        <MetricCard label="累计已实现" value={`${realized >= 0 ? '+' : ''}${realized.toFixed(2)}`} trend={realized >= 0 ? 'up' : 'down'} hint={`${closed.length} 笔交易`} />
        <MetricCard label="胜率" value={`${(winRate * 100).toFixed(0)}%`} hint={`${wins} W / ${closed.length - wins} L`} />
        <MetricCard label="最近一笔" value={closed[0]?.pnl_usdt != null ? `${closed[0].pnl_usdt >= 0 ? '+' : ''}${closed[0].pnl_usdt.toFixed(2)}` : '—'} trend={(closed[0]?.pnl_usdt ?? 0) >= 0 ? 'up' : 'down'} hint={closed[0]?.symbol} />
        <MetricCard label="平均 R" value={closed.length ? `${(closed.reduce((a, p) => a + (p.pnl_pct ?? 0), 0) / closed.length).toFixed(2)}%` : '—'} hint="跨所有平仓" />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="当前持仓" subtitle={`${positions.length} 个`} className="!p-0" bodyClassName="!p-0">
          {active.isLoading ? <div className="p-6"><LoadingSkeleton message="拉取持仓…" /></div> : positions.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-ivory-40">当前无持仓</div>
          ) : (
            <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-bg-surface/95">
                  <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wider text-ivory-40">
                    <th className="py-2.5 pl-5 pr-2">币种</th>
                    <th className="py-2.5 px-2">方向</th>
                    <th className="py-2.5 px-2 text-right">入场</th>
                    <th className="py-2.5 px-2 text-right">SL</th>
                    <th className="py-2.5 px-2 text-right">TP</th>
                    <th className="py-2.5 pl-2 pr-5 text-right">PnL</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline/60">
                  {positions.map(p => (
                    <tr key={p.id} className="hover:bg-bg-surface/40 cursor-pointer" onClick={() => navigate(`/chart/${p.symbol}`)}>
                      <td className="py-2.5 pl-5 pr-2 font-mono font-medium text-ivory">{p.symbol}</td>
                      <td className="py-2.5 px-2">
                        <StatusPill tone={p.side === 'LONG' ? 'emerald' : 'rose'} icon={p.side === 'LONG' ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}>{p.side}</StatusPill>
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono tabular-nums text-ivory-70">{p.entry_price?.toFixed(4)}</td>
                      <td className="py-2.5 px-2 text-right font-mono tabular-nums text-oxblood">{p.sl_price?.toFixed(4)}</td>
                      <td className="py-2.5 px-2 text-right font-mono tabular-nums text-sage">{p.tp_price?.toFixed(4)}</td>
                      <td className={cn(
                        'py-2.5 pl-2 pr-5 text-right font-mono tabular-nums',
                        (p.pnl_pct ?? 0) >= 0 ? 'text-sage' : 'text-oxblood',
                      )}>
                        {(p.pnl_pct ?? 0) >= 0 ? '+' : ''}{(p.pnl_pct ?? 0).toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="最近已实现 PnL" subtitle={`最近 ${Math.min(closed.length, 20)} 笔`} className="!p-0" bodyClassName="!p-0">
          {closed.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-ivory-40">暂无已平仓订单</div>
          ) : (
            <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-bg-surface/95">
                  <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wider text-ivory-40">
                    <th className="py-2.5 pl-5 pr-2">时间</th>
                    <th className="py-2.5 px-2">币种</th>
                    <th className="py-2.5 px-2">原因</th>
                    <th className="py-2.5 px-2 text-right">PnL %</th>
                    <th className="py-2.5 pl-2 pr-5 text-right">USDT</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline/60">
                  {closed.slice(0, 20).map(p => (
                    <tr key={p.id} className="hover:bg-bg-surface/40">
                      <td className="py-2.5 pl-5 pr-2 font-mono text-xs text-ivory-70">
                        {p.exit_time ? new Date(p.exit_time).toLocaleString('zh-CN', { hour12: false }).slice(5) : '—'}
                      </td>
                      <td className="py-2.5 px-2 font-mono text-ivory">{p.symbol}</td>
                      <td className="py-2.5 px-2"><span className="text-xs text-ivory-70">{p.exit_reason ?? '—'}</span></td>
                      <td className={cn(
                        'py-2.5 px-2 text-right font-mono tabular-nums',
                        (p.pnl_pct ?? 0) >= 0 ? 'text-sage' : 'text-oxblood',
                      )}>
                        {(p.pnl_pct ?? 0) >= 0 ? '+' : ''}{(p.pnl_pct ?? 0).toFixed(2)}%
                      </td>
                      <td className={cn(
                        'py-2.5 pl-2 pr-5 text-right font-mono tabular-nums',
                        (p.pnl_usdt ?? 0) >= 0 ? 'text-sage' : 'text-oxblood',
                      )}>
                        {(p.pnl_usdt ?? 0) >= 0 ? '+' : ''}{(p.pnl_usdt ?? 0).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <Card
        title="收益分析"
        subtitle="累计权益曲线 + 历史明细"
        actions={
          <div className="flex gap-1 rounded-xl border border-hairline p-0.5">
            {(['overview', 'history'] as Tab[]).map(t => (
              <SegmentButton key={t} active={tab === t} onClick={() => setTab(t)}>
                {t === 'overview' ? '概览' : '历史'}
              </SegmentButton>
            ))}
          </div>
        }
      >
        {tab === 'overview' ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MiniMetric label="累计 PnL" value={`${realized >= 0 ? '+' : ''}${realized.toFixed(2)} USDT`} tone={realized >= 0 ? 'emerald' : 'rose'} />
              <MiniMetric label="平均 R" value={closed.length ? `${(closed.reduce((a, p) => a + (p.pnl_pct ?? 0), 0) / closed.length).toFixed(2)}%` : '—'} />
              <MiniMetric label="最大单笔盈" value={`+${Math.max(...closed.map(p => p.pnl_pct ?? 0), 0).toFixed(2)}%`} tone="emerald" />
              <MiniMetric label="最大单笔亏" value={`${Math.min(...closed.map(p => p.pnl_pct ?? 0), 0).toFixed(2)}%`} tone="rose" />
            </div>
            <div>
              <div className="text-xs uppercase tracking-wider text-ivory-40 mb-2">权益曲线</div>
              {equityCurve.length > 1 ? (
                <Sparkline values={equityCurve} width={900} height={180} />
              ) : (
                <div className="py-10 text-center text-sm text-ivory-40">数据不足以绘制曲线</div>
              )}
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-bg-surface/95">
                <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wider text-ivory-40">
                  <th className="py-2 px-2">时间</th>
                  <th className="py-2 px-2">币种</th>
                  <th className="py-2 px-2">方向</th>
                  <th className="py-2 px-2 text-right">入场</th>
                  <th className="py-2 px-2 text-right">出场</th>
                  <th className="py-2 px-2 text-right">PnL%</th>
                  <th className="py-2 px-2 text-right">USDT</th>
                  <th className="py-2 px-2 text-right">持仓</th>
                  <th className="py-2 px-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline/60">
                {closed.map(p => {
                  const mins = p.entry_time && p.exit_time ? Math.round((new Date(p.exit_time).getTime() - new Date(p.entry_time).getTime()) / 60_000) : 0;
                  return (
                    <tr key={p.id} className="hover:bg-bg-surface/40">
                      <td className="py-2 px-2 font-mono text-xs text-ivory-70">{p.exit_time ? new Date(p.exit_time).toLocaleString('zh-CN', { hour12: false }) : '—'}</td>
                      <td className="py-2 px-2 font-mono text-ivory">{p.symbol}</td>
                      <td className="py-2 px-2"><StatusPill tone={p.side === 'LONG' ? 'emerald' : 'rose'}>{p.side}</StatusPill></td>
                      <td className="py-2 px-2 text-right font-mono tabular-nums text-ivory-70">{p.entry_price?.toFixed(4)}</td>
                      <td className="py-2 px-2 text-right font-mono tabular-nums text-ivory-70">{p.exit_price?.toFixed(4)}</td>
                      <td className={cn('py-2 px-2 text-right font-mono tabular-nums', (p.pnl_pct ?? 0) >= 0 ? 'text-sage' : 'text-oxblood')}>{(p.pnl_pct ?? 0) >= 0 ? '+' : ''}{(p.pnl_pct ?? 0).toFixed(2)}%</td>
                      <td className={cn('py-2 px-2 text-right font-mono tabular-nums', (p.pnl_usdt ?? 0) >= 0 ? 'text-sage' : 'text-oxblood')}>{(p.pnl_usdt ?? 0) >= 0 ? '+' : ''}{(p.pnl_usdt ?? 0).toFixed(2)}</td>
                      <td className="py-2 px-2 text-right font-mono tabular-nums text-ivory-70">{mins}min</td>
                      <td className="py-2 px-2">
                        <button
                          type="button"
                          onClick={() => navigate(`/chart/${p.symbol}?eventId=${p.id}`)}
                          className="rounded-lg border border-hairline-strong p-1.5 text-ivory-70 transition hover:border-brass hover:text-brass"
                        >
                          <LineIcon className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function MiniMetric({ label, value, tone }: { label: string; value: string; tone?: 'emerald' | 'rose' }) {
  return (
    <div className="rounded-2xl border border-hairline bg-bg-base/60 px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wider text-ivory-40">{label}</div>
      <div className={cn('mt-1 font-mono text-lg font-semibold tabular-nums', tone === 'emerald' ? 'text-sage' : tone === 'rose' ? 'text-oxblood' : 'text-ivory')}>{value}</div>
    </div>
  );
}
