import { ReactNode, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, TrendingUp, TrendingDown, Minus, ArrowRight, AlertTriangle } from 'lucide-react';
import { useV5Dashboard } from '../../hooks/api/useV5Dashboard';
import { useV5SetupPerformance } from '../../hooks/api/useV5Reflections';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { MetricCard } from '../primitives-v3/MetricCard';
import { Card } from '../primitives-v3/Card';
import { cn } from '../primitives-v3/cn';
import { winRateOf, bySide, byStrategy, byExitReason, bestAndWorst, profitFactor, streaks } from './_winrate_helpers';

const MAX_CONCURRENT = 3;

export function V5DashboardPage() {
  const q = useV5Dashboard();
  const navigate = useNavigate();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  if (q.isLoading) return <LoadingSkeleton message="拉取 24h 观测数据中…" />;
  const d = q.data;
  if (!d) {
    return (
      <div className="px-6 py-6">
        <SectionTitle title="仪表盘" subtitle="无数据" />
      </div>
    );
  }

  const winRatePct = Math.round(d.win_rate_24h * 100);
  const pnlSeries = d.closed_24h
    .slice()
    .sort((a, b) => (a.exit_time || '').localeCompare(b.exit_time || ''))
    .reduce<{ time: string; cum: number }[]>((acc, p) => {
      const prev = acc.length > 0 ? acc[acc.length - 1].cum : 0;
      acc.push({
        time: p.exit_time ? new Date(p.exit_time).toLocaleTimeString('zh-CN', { hour12: false }) : '',
        cum: prev + (p.pnl_usdt ?? 0),
      });
      return acc;
    }, []);

  const closed = d.closed_24h;
  const overall = winRateOf(closed);
  const sideStats = bySide(closed);
  const stratStats = byStrategy(closed);
  const reasonsStats = byExitReason(closed);
  const bw = bestAndWorst(closed);
  const pf = profitFactor(closed);
  const sk = streaks(closed);

  const pnlTrend = closed.length === 0 ? 'neutral' : d.pnl_total_usdt > 0 ? 'up' : d.pnl_total_usdt < 0 ? 'down' : 'neutral';

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-6 space-y-6">
      <SectionTitle
        title="仪表盘"
        subtitle={`24 小时观测日志 · ${now.toLocaleTimeString('zh-CN', { hour12: false })}`}
        action={
          <span className="rounded-full border border-zinc-700 bg-zinc-900/70 px-3 py-1 text-xs text-zinc-300">
            自动刷新 · 15s
          </span>
        }
      />

      {/* KPI metrics */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="胜率 · 7d"
          value={closed.length === 0 ? '—' : `${winRatePct}%`}
          hint={closed.length === 0 ? <NextCandleHint now={now} /> : `${closed.length} 笔已观测`}
        />
        <MetricCard
          label="累计盈亏"
          value={closed.length === 0 ? '—' : `${d.pnl_total_usdt >= 0 ? '+' : ''}${d.pnl_total_usdt.toFixed(2)} USDT`}
          trend={pnlTrend as 'up' | 'down' | 'neutral'}
          hint={closed.length === 0 ? null : `${closed.length} 笔结算 · 24h`}
        />
        <MetricCard
          label="平均持仓"
          value={closed.length === 0 ? '—' : `${Math.round(d.avg_holding_minutes)} 分钟`}
          hint={closed.length === 0 ? null : '24h 内已平仓样本'}
        />
        <MetricCard
          label="活仓数"
          value={`${d.active_count} / ${MAX_CONCURRENT}`}
          hint={
            <SlotStrip active={d.active_count} total={MAX_CONCURRENT} />
          }
        />
      </div>

      {/* Signal funnel */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="信号漏斗"
          subtitle="24h 范围 · 点击层级跳转历史"
          className="lg:col-span-2"
        >
          <Funnel
            steps={[
              { name: '扫描检测', count: d.signals_24h, color: 'indigo' },
              { name: '合谋通过', count: d.signals_passed_and, color: 'amber' },
              { name: '实际开仓', count: d.signals_executed, color: 'emerald' },
            ]}
            onLayerClick={(name) => navigate(name === '实际开仓' ? '/v5/history?block_reason=EXECUTED' : '/v5/history')}
          />
        </Card>

        <Card title="拦截原因 · top 5" subtitle="规则引擎阀门">
          <BlockRows reasons={d.signals_block_counts} />
        </Card>
      </div>

      {/* PnL trajectory */}
      <Card
        title="盈亏曲线"
        subtitle="累计 · 24h"
        actions={
          pnlSeries.length > 0 ? (
            <span
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs',
                pnlSeries[pnlSeries.length - 1].cum > 0
                  ? 'bg-emerald-500/10 text-emerald-300'
                  : pnlSeries[pnlSeries.length - 1].cum < 0
                  ? 'bg-rose-500/10 text-rose-300'
                  : 'bg-zinc-800 text-zinc-400',
              )}
            >
              最近平仓 {pnlSeries[pnlSeries.length - 1].time}
            </span>
          ) : null
        }
      >
        {pnlSeries.length === 0 ? (
          <EmptyState
            icon={<TrendingUp className="h-5 w-5 text-zinc-500" />}
            title="24h 内无平仓"
            description={<NextCandleHint now={now} prefix="下一根 15m K 线" />}
          />
        ) : (
          <PnlSparkline data={pnlSeries} />
        )}
      </Card>

      {/* Outcome breakdown */}
      <Card title={`结果拆解 · 24h (n=${closed.length})`} subtitle="按方向 / 策略 / 平仓原因">
        {closed.length === 0 ? (
          <EmptyState
            icon={<Activity className="h-5 w-5 text-zinc-500" />}
            title="24h 内无平仓样本"
            description="自动开仓后会在这里看到分布"
          />
        ) : (
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="space-y-5">
              <BdGroup label="按方向">
                <BdRow label="做多 (LONG)" data={sideStats.long} />
                <BdRow label="做空 (SHORT)" data={sideStats.short} />
              </BdGroup>
              <BdGroup label="按策略">
                <BdRow label="自动 (v5_rsi_macd)" data={stratStats.auto} />
                <BdRow label="手动 (v5_manual)" data={stratStats.manual} />
              </BdGroup>
              <BdGroup label="按平仓原因">
                {Object.entries(reasonsStats)
                  .sort((a, b) => b[1].count - a[1].count)
                  .map(([reason, br]) => (
                    <BdRow key={reason} label={reason} data={br} />
                  ))}
              </BdGroup>
            </div>
            <div className="space-y-3">
              <Stat label="样本">
                <span className="text-emerald-400">{overall.wins} 胜</span>
                <span className="text-zinc-600 mx-2">/</span>
                <span className="text-rose-400">{overall.losses} 败</span>
                <span className="ml-3 text-xs text-zinc-500">{Math.round(overall.win_rate * 100)}% 整体胜率</span>
              </Stat>
              <Stat label="盈亏比 (Profit Factor)">
                {pf === null ? '∞' : pf.toFixed(2)}
                <span className="ml-2 text-xs text-zinc-500">总盈 / 总亏</span>
              </Stat>
              <Stat label="最佳交易">
                {bw.best && (bw.best.pnl_pct ?? 0) > 0 ? (
                  <span className="text-emerald-400">
                    {bw.best.symbol} <span className="text-xs">+{(bw.best.pnl_pct ?? 0).toFixed(2)}%</span>
                  </span>
                ) : <span className="text-zinc-500">—</span>}
              </Stat>
              <Stat label="最差交易">
                {bw.worst && (bw.worst.pnl_pct ?? 0) < 0 ? (
                  <span className="text-rose-400">
                    {bw.worst.symbol} <span className="text-xs">{(bw.worst.pnl_pct ?? 0).toFixed(2)}%</span>
                  </span>
                ) : <span className="text-zinc-500">—</span>}
              </Stat>
              <Stat label="连续胜负 (最大)">
                <span className="text-emerald-400">{sk.maxWin} 连胜</span>
                <span className="text-zinc-600 mx-2">/</span>
                <span className="text-rose-400">{sk.maxLoss} 连败</span>
                {sk.current.side && (
                  <span className="ml-3 text-xs text-zinc-500">
                    当前 {sk.current.len} {sk.current.side === 'W' ? '连胜' : '连败'}
                  </span>
                )}
              </Stat>
            </div>
          </div>
        )}
      </Card>

      {/* Setup performance */}
      <Card
        title="Setup 类型 · 7d"
        subtitle="funding 维度高亮"
        actions={
          <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-500/10 px-3 py-1 text-xs text-indigo-300">
            <AlertTriangle className="h-3 w-3" />
            ✦ funding extreme
          </span>
        }
      >
        <SetupBreakdownTable />
      </Card>
    </div>
  );
}

/* ─────────────── helpers ─────────────── */

function nextCandleMinutes(now: Date): number {
  const mins = now.getMinutes();
  const nextBoundary = Math.ceil((mins + 1) / 15) * 15;
  return nextBoundary - mins;
}

function NextCandleHint({ now, prefix = '下一根 K 线' }: { now: Date; prefix?: string }) {
  const m = nextCandleMinutes(now);
  return (
    <span>
      {prefix} <span className="text-indigo-300 font-medium">{m}</span> 分钟后
    </span>
  );
}

function EmptyState({ icon, title, description }: { icon: ReactNode; title: string; description: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-zinc-800">
        {icon}
      </div>
      <div className="text-sm font-medium text-zinc-300">{title}</div>
      <div className="mt-1 text-xs text-zinc-500">{description}</div>
    </div>
  );
}

function SlotStrip({ active, total }: { active: number; total: number }) {
  return (
    <span className="inline-flex gap-1 items-center">
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className={cn(
            'h-2 w-6 rounded-full',
            i < active ? 'bg-indigo-400' : 'bg-zinc-800',
          )}
        />
      ))}
      <span className="ml-2 text-xs text-zinc-500">{active === 0 ? '空闲' : `${active} 持仓`}</span>
    </span>
  );
}

function Funnel({ steps, onLayerClick }: { steps: { name: string; count: number; color: 'indigo' | 'amber' | 'emerald' }[]; onLayerClick: (n: string) => void }) {
  const max = Math.max(...steps.map(s => s.count), 1);
  return (
    <div className="space-y-3">
      {steps.map((s) => {
        const pct = Math.max(2, (s.count / max) * 100);
        return (
          <button
            key={s.name}
            onClick={() => onLayerClick(s.name)}
            className="group block w-full text-left"
          >
            <div className="mb-1.5 flex items-center justify-between text-sm">
              <span className="text-zinc-300 group-hover:text-zinc-100">{s.name}</span>
              <span className="font-mono tabular-nums text-zinc-200">{s.count.toLocaleString()}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-zinc-900">
              <div
                className={cn(
                  'h-full rounded-full transition-all',
                  s.color === 'indigo' && 'bg-indigo-500',
                  s.color === 'amber' && 'bg-amber-500',
                  s.color === 'emerald' && 'bg-emerald-500',
                )}
                style={{ width: `${pct}%` }}
              />
            </div>
          </button>
        );
      })}
    </div>
  );
}

function BlockRows({ reasons }: { reasons: Record<string, number> }) {
  const entries = Object.entries(reasons).sort((a, b) => b[1] - a[1]).slice(0, 5);
  if (entries.length === 0) {
    return <div className="text-sm text-zinc-500">无拦截记录</div>;
  }
  const max = Math.max(...entries.map(e => e[1]), 1);
  return (
    <div className="space-y-2.5">
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-center gap-3 text-sm">
          <span className="w-44 truncate text-zinc-400" title={k}>{k}</span>
          <div className="flex-1 h-1.5 overflow-hidden rounded-full bg-zinc-900">
            <div className="h-full rounded-full bg-rose-500/60" style={{ width: `${(v / max) * 100}%` }} />
          </div>
          <span className="w-12 text-right font-mono text-xs text-zinc-300">{v}</span>
        </div>
      ))}
    </div>
  );
}

function PnlSparkline({ data }: { data: { time: string; cum: number }[] }) {
  if (data.length === 0) return null;
  const w = 800, h = 220, padL = 40, padR = 60, padT = 16, padB = 28;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;
  const xs = data.map((_, i) => padL + (i / Math.max(1, data.length - 1)) * innerW);
  const cums = data.map(d => d.cum);
  const minY = Math.min(0, ...cums);
  const maxY = Math.max(0, ...cums);
  const range = maxY - minY || 1;
  const ys = cums.map(v => padT + (1 - (v - minY) / range) * innerH);
  const zeroY = padT + (1 - (0 - minY) / range) * innerH;
  const linePath = xs.map((x, i) => `${i === 0 ? 'M' : 'L'} ${x} ${ys[i]}`).join(' ');
  const fillPath = `${linePath} L ${xs[xs.length - 1]} ${zeroY} L ${xs[0]} ${zeroY} Z`;
  const last = data[data.length - 1];
  const isUp = last.cum >= 0;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full h-[220px]">
      <line x1={padL} y1={zeroY} x2={w - padR} y2={zeroY} stroke="rgba(244,244,245,0.08)" />
      <text x={4} y={padT + 10} fontSize="11" fill="#71717a">{maxY.toFixed(0)}</text>
      <text x={4} y={zeroY + 4} fontSize="11" fill="#71717a">0</text>
      {minY < 0 && <text x={4} y={padT + innerH - 2} fontSize="11" fill="#71717a">{minY.toFixed(0)}</text>}
      <path d={fillPath} fill={isUp ? 'rgba(52,211,153,0.10)' : 'rgba(244,63,94,0.10)'} />
      <path d={linePath} stroke={isUp ? '#34d399' : '#fb7185'} strokeWidth="2" fill="none" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={xs[xs.length - 1]} cy={ys[ys.length - 1]} r="4" fill="#a5b4fc" />
      <text x={xs[xs.length - 1] + 10} y={ys[ys.length - 1] + 4} fontSize="11" fill="#a5b4fc" fontFamily="JetBrains Mono">
        {last.cum >= 0 ? '+' : ''}{last.cum.toFixed(2)} USDT
      </text>
      <text x={padL} y={h - 8} fontSize="11" fill="#52525b">{data[0].time}</text>
      <text x={w - padR - 50} y={h - 8} fontSize="11" fill="#52525b">{last.time}</text>
    </svg>
  );
}

function BdGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-2.5 text-xs uppercase tracking-[0.18em] text-zinc-500">{label}</div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function BdRow({ label, data }: { label: string; data?: { count: number; win_rate: number; pnl_total: number } }) {
  if (!data || data.count === 0) {
    return (
      <div className="flex items-center gap-3 text-sm">
        <span className="w-40 text-zinc-400">{label}</span>
        <span className="text-xs text-zinc-600">—</span>
      </div>
    );
  }
  const pct = Math.round(data.win_rate * 100);
  const pnl = data.pnl_total ?? 0;
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-40 text-zinc-300">{label}</span>
      <div className="flex-1 h-1.5 overflow-hidden rounded-full bg-zinc-900">
        <div className="h-full rounded-full bg-emerald-500/50" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono tabular-nums text-xs text-zinc-300 w-24 text-right">
        {pct}% · <span className={pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(1)}</span>
      </span>
    </div>
  );
}

function Stat({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 p-4">
      <div className="text-xs uppercase tracking-[0.18em] text-zinc-500 mb-1">{label}</div>
      <div className="text-base font-semibold tabular-nums text-zinc-50">{children}</div>
    </div>
  );
}

function SetupBreakdownTable() {
  const q = useV5SetupPerformance(7);
  const rows = q.data?.data ?? [];
  const byType = new Map<string, { n: number; w: number; sumR: number }>();
  for (const r of rows) {
    const cur = byType.get(r.setup_type) ?? { n: 0, w: 0, sumR: 0 };
    cur.n += r.sample_count;
    cur.w += r.win_count;
    cur.sumR += r.avg_realized_r * r.sample_count;
    byType.set(r.setup_type, cur);
  }
  const sorted = Array.from(byType.entries())
    .map(([t, v]) => ({
      setup_type: t,
      n: v.n,
      win_rate: v.n > 0 ? v.w / v.n : 0,
      avg_r: v.n > 0 ? v.sumR / v.n : 0,
      is_funding: t.startsWith('funding_extreme'),
    }))
    .sort((a, b) => b.n - a.n);

  if (sorted.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-zinc-500">
        7d 内无 reflection 样本 — 首笔自动开仓关仓后将在这里出现
      </div>
    );
  }

  const totalN = sorted.reduce((a, x) => a + x.n, 0);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-left text-xs uppercase tracking-wider text-zinc-500">
            <th className="pb-3 pr-3 font-medium">Setup 类型</th>
            <th className="pb-3 px-3 text-right font-medium">n</th>
            <th className="pb-3 px-3 text-right font-medium">胜率</th>
            <th className="pb-3 px-3 text-right font-medium">avg R</th>
            <th className="pb-3 pl-3 text-right font-medium">占比</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/60">
          {sorted.map(r => (
            <tr
              key={r.setup_type}
              className={cn('group', r.is_funding && 'bg-indigo-500/[0.06]')}
            >
              <td className={cn('py-2.5 pr-3 font-mono text-xs', r.is_funding ? 'text-indigo-300' : 'text-zinc-300')}>
                {r.is_funding && <span className="mr-1.5">✦</span>}
                {r.setup_type}
              </td>
              <td className="py-2.5 px-3 text-right tabular-nums text-zinc-400">{r.n}</td>
              <td className={cn('py-2.5 px-3 text-right tabular-nums', r.win_rate >= 0.5 ? 'text-emerald-400' : 'text-rose-400')}>
                {(r.win_rate * 100).toFixed(0)}%
              </td>
              <td className={cn('py-2.5 px-3 text-right tabular-nums', r.avg_r >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
                {r.avg_r >= 0 ? '+' : ''}{r.avg_r.toFixed(2)}
              </td>
              <td className="py-2.5 pl-3 text-right tabular-nums text-zinc-500">
                {totalN > 0 ? Math.round((r.n / totalN) * 100) : 0}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
