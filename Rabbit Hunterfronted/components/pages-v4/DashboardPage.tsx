import { useState } from 'react';
import { Play, Square, Activity as ActivityIcon, AlertCircle } from 'lucide-react';
import { useV5Dashboard } from '../../hooks/api/useV5Dashboard';
import { useV5ActivePositions } from '../../hooks/api/useV5ActivePositions';
import { useV5AIDecisions } from '../../hooks/api/useV5AIStatus';
import { useV5Klines } from '../../hooks/api/useV5Klines';
import { useUIStore } from '../../services/store';
import { useSystemMode } from '../../hooks/useSystemMode';
import { useV5Settings } from '../../hooks/api/useV5Settings';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { MetricCard } from '../primitives-v3/MetricCard';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { SegmentButton } from '../primitives-v3/SegmentButton';
import { Sparkline } from '../primitives/Sparkline';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { cn } from '../primitives-v3/cn';
import type { Interval } from '../../types';

export function DashboardPage() {
  const dash = useV5Dashboard();
  const active = useV5ActivePositions();
  const decisions = useV5AIDecisions(10);
  const { mode } = useSystemMode();
  const { patch } = useV5Settings();
  const selectedSymbol = useUIStore(s => s.selectedSymbol);
  const [timeframe, setTimeframe] = useState<Interval>('15m');
  const klines = useV5Klines(selectedSymbol, timeframe, 50);

  const d = dash.data;
  const positions = active.data?.combined ?? [];
  const decisionList = decisions.data?.decisions ?? [];
  const klineData = klines.data?.klines ?? [];
  const closes = klineData.map(k => k.close);

  return (
    <div className="space-y-6">
      <SectionTitle
        title="仪表盘"
        subtitle="账户摘要、运行控制和最近 24h 信号扫描配置。"
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="24h PnL" value={`${(d?.pnl_total_usdt ?? 0) >= 0 ? '+' : ''}${(d?.pnl_total_usdt ?? 0).toFixed(2)} USDT`} trend={d && d.pnl_total_usdt >= 0 ? 'up' : 'down'} hint={d ? `胜率 ${(d.win_rate_24h * 100).toFixed(0)}% · ${d.closed_24h.length} 笔` : '—'} />
        <MetricCard label="活仓数" value={String(d?.active_count ?? 0)} hint={positions.length ? `${positions.filter(p => p.side === 'LONG').length} 多 / ${positions.filter(p => p.side === 'SHORT').length} 空` : '当前空仓'} />
        <MetricCard label="24h 信号通过" value={`${d?.signals_passed_and ?? 0} / ${d?.signals_24h ?? 0}`} hint={d && d.signals_24h ? `通过率 ${Math.round(d.signals_passed_and / d.signals_24h * 100)}%` : '—'} />
        <MetricCard label="24h 已入仓" value={String(d?.signals_executed ?? 0)} hint={d ? `平均持仓 ${Math.round(d.avg_holding_minutes)} min` : '—'} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Card title="运行控制" subtitle="自动交易状态与日志">
          <div className="grid grid-cols-3 gap-3 mb-4">
            <ConnectionCard label="系统模式" value={mode ?? '—'} tone={mode === 'LIVE' ? 'rose' : 'amber'} />
            <ConnectionCard label="自动交易" value="运行中" tone="emerald" />
            <ConnectionCard label="WebSocket" value="在线" tone="emerald" />
          </div>

          <div className="flex flex-wrap gap-2 mb-4">
            <button
              type="button"
              onClick={() => patch.mutate({ enable_auto_trading: true })}
              className="inline-flex items-center gap-1.5 rounded-2xl bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-400"
            >
              <Play className="h-4 w-4" /> 启动扫描
            </button>
            <button
              type="button"
              onClick={() => patch.mutate({ enable_auto_trading: false })}
              className="inline-flex items-center gap-1.5 rounded-2xl border border-zinc-700 px-4 py-2 text-sm text-zinc-200 transition hover:border-rose-500 hover:text-rose-300"
            >
              <Square className="h-4 w-4" /> 暂停扫描
            </button>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-4">
            <MiniMetric label="近 10 决策" value={String(decisionList.length)} />
            <MiniMetric label="平均置信" value={`${decisionList.length ? Math.round(decisionList.reduce((a, x) => a + (x.confidence ?? 0) * 100, 0) / decisionList.length) : 0}%`} />
            <MiniMetric label="通过率" value={`${decisionList.length ? Math.round(decisionList.filter(x => x.execute).length / decisionList.length * 100) : 0}%`} />
          </div>

          <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 p-3 max-h-72 overflow-y-auto">
            <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">活动日志</div>
            <div className="space-y-1.5">
              {decisionList.length === 0 ? (
                <div className="text-xs text-zinc-500 italic">暂无决策记录</div>
              ) : decisionList.map(d => (
                <div key={d.id} className="flex items-center gap-2 text-xs">
                  <span className="font-mono text-zinc-500 tabular-nums">
                    {new Date(d.created_at).toLocaleTimeString('zh-CN', { hour12: false })}
                  </span>
                  <StatusPill tone={d.execute ? 'emerald' : 'rose'}>
                    {d.execute ? '通过' : '拒'}
                  </StatusPill>
                  <span className="font-mono text-zinc-200">{d.symbol}</span>
                  <span className="text-zinc-400 truncate">
                    {d.reasoning.length > 60 ? d.reasoning.slice(0, 60) + '…' : d.reasoning}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <Card
          title={`${selectedSymbol} 走势`}
          subtitle="切换时间帧"
          actions={
            <div className="flex gap-1 rounded-xl border border-zinc-800 p-0.5">
              {(['15m', '1h'] as Interval[]).map(tf => (
                <SegmentButton key={tf} active={timeframe === tf} onClick={() => setTimeframe(tf)}>{tf}</SegmentButton>
              ))}
            </div>
          }
        >
          {klines.isLoading ? (
            <LoadingSkeleton message="拉取 K 线…" />
          ) : closes.length === 0 ? (
            <div className="py-12 text-center text-sm text-zinc-500">无 K 线数据</div>
          ) : (
            <div>
              <div className="text-3xl font-semibold text-zinc-50 tabular-nums">
                {closes.at(-1)?.toFixed(closes.at(-1)! >= 1 ? 2 : 6)}
              </div>
              <div className={cn(
                'text-sm tabular-nums',
                (closes.at(-1)! >= closes[0]) ? 'text-emerald-400' : 'text-rose-400',
              )}>
                {((closes.at(-1)! / closes[0] - 1) * 100).toFixed(2)}%
              </div>
              <div className="mt-4">
                <Sparkline values={closes} width={500} height={160} />
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function ConnectionCard({ label, value, tone }: { label: string; value: string; tone: 'emerald' | 'rose' | 'amber' | 'zinc' }) {
  const cls = {
    emerald: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300',
    rose: 'border-rose-500/20 bg-rose-500/10 text-rose-300',
    amber: 'border-amber-500/20 bg-amber-500/10 text-amber-300',
    zinc: 'border-zinc-800 bg-zinc-900/70 text-zinc-300',
  }[tone];
  return (
    <div className={cn('rounded-2xl border px-4 py-3', cls)}>
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="mt-1 font-medium">{value}</div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="mt-0.5 font-mono text-base font-semibold tabular-nums text-zinc-100">{value}</div>
    </div>
  );
}
