import { useEffect, useMemo, useState } from 'react';
import { Brain, Database, Zap, Heart, CheckCircle, XCircle } from 'lucide-react';
import { useV5AIStatus, useV5AIDecisions } from '../../hooks/api/useV5AIStatus';
import { useV5Calibration } from '../../hooks/api/useV5Reflections';
import { useV5FundingStatus } from '../../hooks/api/useV5Funding';
import { useUIStore } from '../../services/store';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Sparkline } from '../primitives/Sparkline';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { MetricCard } from '../primitives-v3/MetricCard';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { Alert } from '../primitives-v3/Alert';
import { cn } from '../primitives-v3/cn';

export function V5AIStatusPage() {
  const status = useV5AIStatus();
  const dec = useV5AIDecisions(20);
  const wsEvents = useUIStore(s => s.recentWsEvents);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const decisions = dec.data?.decisions ?? [];
  const sparkValues = useMemo(
    () => decisions.slice().reverse().map(d => (d.confidence ?? 0) * 100),
    [decisions]
  );

  const lastAiEvent = useMemo(() => {
    for (let i = wsEvents.length - 1; i >= 0; i--) {
      if (wsEvents[i].type === 'ai_health') return wsEvents[i] as any;
    }
    return null;
  }, [wsEvents]);

  if (status.isLoading) return <LoadingSkeleton message="拉取 AI 头脑状态中…" />;
  const s = status.data;
  const provider = s?.provider ?? 'unconfigured';
  const healthy = s?.healthy ?? false;
  const lastLatency = (lastAiEvent && typeof lastAiEvent.last_latency_ms === 'number')
    ? lastAiEvent.last_latency_ms
    : null;

  const avgConf = decisions.length > 0
    ? Math.round(decisions.reduce((a, d) => a + (d.confidence ?? 0) * 100, 0) / decisions.length)
    : 0;
  const executedN = decisions.filter(d => d.execute).length;
  const rejectedN = decisions.filter(d => !d.execute).length;

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-6 space-y-6">
      <SectionTitle
        title="AI 状态"
        subtitle={`决策头脑 · 校准 · 拥挤侦测 · ${now.toLocaleTimeString('zh-CN', { hour12: false })}`}
        action={
          <StatusPill tone={healthy ? 'emerald' : 'rose'} icon={healthy ? <Heart className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}>
            {healthy ? '在线' : '离线'}
          </StatusPill>
        }
      />

      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-3">
        <Card>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-zinc-500">
            <Brain className="h-3.5 w-3.5 text-indigo-400" />
            <span>模型</span>
            <StatusPill tone={healthy ? 'emerald' : 'rose'} className="ml-auto">
              {healthy ? '在线' : '离线'}
            </StatusPill>
          </div>
          <div className="mt-3 font-mono text-2xl font-semibold text-zinc-50 truncate">
            {provider.toLowerCase()}
            <span className="text-indigo-400">·</span>
            {(s?.chat_model ?? 'chat').replace(/^[^-]+-/, '')}
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            primary model · {s?.healthy_ratio_24h != null ? `${Math.round(s.healthy_ratio_24h * 100)}% healthy 24h` : '无健康记录'}
          </div>
          <div className="mt-4 h-8">
            <Sparkline values={sparkValues.length > 1 ? sparkValues : [0, 0]} width={220} height={28} />
          </div>
          <div className="mt-2 flex justify-between text-[11px] text-zinc-500">
            <span>近 {decisions.length} 次置信度</span>
            <span>均值 <span className="text-zinc-200">{avgConf}%</span></span>
          </div>
        </Card>

        <Card>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-zinc-500">
            <Database className="h-3.5 w-3.5 text-amber-400" />
            <span>RAG 记忆</span>
            <StatusPill tone="amber" className="ml-auto">已索引</StatusPill>
          </div>
          <div className="mt-3 font-mono text-2xl font-semibold text-zinc-50">
            {s?.rag_cases_in_db ?? 0}
            <span className="text-base text-zinc-400 ml-2">cases</span>
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            {Math.round((s?.rag_utilization_24h ?? 0) * 100)}% 利用率 · 近 24h
          </div>
          <div className="mt-4 h-2 rounded-full bg-zinc-900 overflow-hidden">
            <div
              className="h-full bg-amber-500 transition-all"
              style={{ width: `${Math.round((s?.rag_utilization_24h ?? 0) * 100)}%` }}
            />
          </div>
          <div className="mt-2 flex justify-between text-[11px] text-zinc-500">
            <span>utilization</span>
            <span>{s?.rag_cases_in_db ?? 0} indexed</span>
          </div>
        </Card>

        <Card>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-zinc-500">
            <Zap className="h-3.5 w-3.5 text-emerald-400" />
            <span>24h 决策</span>
            <StatusPill tone={healthy ? 'emerald' : 'zinc'} className="ml-auto">
              {healthy ? '健康' : '静默'}
            </StatusPill>
          </div>
          <div className="mt-3 font-mono text-2xl font-semibold text-zinc-50">
            {s?.decisions_24h ?? 0}
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            {executedN} 通过 · {rejectedN} 拒绝
          </div>
          <div className="mt-4 h-8">
            <Sparkline values={sparkValues.length > 1 ? sparkValues : [0, 0]} width={220} height={28} />
          </div>
          <div className="mt-2 flex justify-between text-[11px] text-zinc-500">
            <span>置信度走势</span>
            <span>last <span className="text-zinc-200">{decisions.length}</span></span>
          </div>
        </Card>
      </div>

      {lastAiEvent && (
        <Alert tone="info">
          last health beacon · provider={lastAiEvent.provider} · healthy={String(lastAiEvent.healthy)} · latency={lastLatency ?? '—'}ms
        </Alert>
      )}

      <Card title="决策流" subtitle={`最近 ${decisions.length} 条事件 · live`} className="!p-0" bodyClassName="!p-0">
        {dec.isLoading ? (
          <div className="p-6"><LoadingSkeleton message="拉取决策流中…" /></div>
        ) : decisions.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-zinc-500">等待下一条决策…</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                  <th className="py-3 pl-5 pr-2 font-medium">时间</th>
                  <th className="py-3 px-2 font-medium">币种</th>
                  <th className="py-3 px-2 font-medium">结果</th>
                  <th className="py-3 px-2 font-medium text-right">置信</th>
                  <th className="py-3 px-2 font-medium text-right">顶 1 距</th>
                  <th className="py-3 px-2 font-medium text-right">RAG</th>
                  <th className="py-3 pl-2 pr-5 font-medium">分析</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {decisions.map(d => (
                  <tr
                    key={d.id}
                    className={cn(
                      'ticker-row hover:bg-zinc-900/40',
                      d.execute && 'bg-emerald-500/[0.03]',
                      !d.execute && 'bg-rose-500/[0.03]',
                    )}
                  >
                    <td className="py-2.5 pl-5 pr-2 font-mono text-xs text-zinc-400">
                      {new Date(d.created_at).toLocaleTimeString('zh-CN', { hour12: false })}
                    </td>
                    <td className="py-2.5 px-2 font-mono font-medium text-zinc-100">{d.symbol}</td>
                    <td className="py-2.5 px-2">
                      <StatusPill tone={d.execute ? 'emerald' : 'rose'} icon={d.execute ? <CheckCircle className="h-2.5 w-2.5" /> : <XCircle className="h-2.5 w-2.5" />}>
                        {d.execute ? '通过' : '拒绝'}
                      </StatusPill>
                    </td>
                    <td className={cn('py-2.5 px-2 text-right font-mono tabular-nums', d.execute ? 'text-emerald-300' : 'text-rose-300')}>
                      {d.confidence == null ? '—' : `${Math.round(d.confidence * 100)}%`}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono tabular-nums text-zinc-400">{d.top1_distance == null ? '—' : d.top1_distance.toFixed(2)}</td>
                    <td className="py-2.5 px-2 text-right font-mono tabular-nums text-zinc-500">{d.rag_case_count}</td>
                    <td className="py-2.5 pl-2 pr-5 text-zinc-400 max-w-[420px] truncate" title={d.reasoning}>
                      {d.reasoning.length > 100 ? d.reasoning.slice(0, 100) + '…' : d.reasoning}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="置信度校准" subtitle="预测对比实际 · 30d">
        <CalibrationTable />
      </Card>

      <Card title="Funding 拥挤度 · top 20" subtitle="|z| ≥ 2.0 为极端 · 按 |z| 降序">
        <FundingHeatmap />
      </Card>
    </div>
  );
}

function CalibrationTable() {
  const q = useV5Calibration();
  const points = q.data?.data ?? [];
  if (points.length === 0) return <div className="py-8 text-center text-sm text-zinc-500">等待每桶至少 10 条 reflection…</div>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
            <th className="py-2 pr-2 font-medium">模型 · 区间</th>
            <th className="py-2 px-2 font-medium text-right">n</th>
            <th className="py-2 px-2 font-medium text-right">预测</th>
            <th className="py-2 px-2 font-medium text-right">实际</th>
            <th className="py-2 px-2 font-medium text-right">偏差</th>
            <th className="py-2 pl-2 font-medium text-right">校准倍数</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/60">
          {points.map(p => {
            const drift = p.actual_win_rate - p.predicted_win_rate;
            const driftCls =
              Math.abs(drift) < 0.05 ? 'text-emerald-300'
              : Math.abs(drift) < 0.15 ? 'text-amber-300'
              : 'text-rose-300';
            return (
              <tr key={`${p.ai_model}-${p.confidence_bucket}`} className="hover:bg-zinc-900/40">
                <td className="py-2 pr-2 font-mono text-xs text-zinc-300">{p.ai_model} · {(p.confidence_bucket * 100).toFixed(0)}%</td>
                <td className="py-2 px-2 text-right font-mono tabular-nums text-zinc-400">{p.sample_count}</td>
                <td className="py-2 px-2 text-right font-mono tabular-nums">{(p.predicted_win_rate * 100).toFixed(1)}%</td>
                <td className={cn('py-2 px-2 text-right font-mono tabular-nums', drift >= 0 ? 'text-emerald-300' : 'text-rose-300')}>
                  {(p.actual_win_rate * 100).toFixed(1)}%
                </td>
                <td className={cn('py-2 px-2 text-right font-mono tabular-nums', driftCls)}>
                  {drift >= 0 ? '+' : ''}{(drift * 100).toFixed(1)}pt
                </td>
                <td className="py-2 pl-2 text-right font-mono tabular-nums text-zinc-100">×{p.calibration_multiplier.toFixed(2)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FundingHeatmap() {
  const q = useV5FundingStatus();
  const rows = q.data?.data ?? [];
  if (rows.length === 0) return <div className="py-8 text-center text-sm text-zinc-500">等待 funding 缓存刷新…</div>;

  const sorted = rows.slice().sort((a, b) => Math.abs(b.zscore_30d ?? 0) - Math.abs(a.zscore_30d ?? 0));

  return (
    <div className="space-y-1">
      {sorted.map(r => {
        const z = r.zscore_30d ?? 0;
        const absZ = Math.abs(z);
        const extreme = r.is_extreme;
        const zCls = extreme
          ? (z > 0 ? 'text-rose-300' : 'text-emerald-300')
          : absZ >= 1 ? 'text-amber-300'
          : 'text-zinc-300';
        const labelText = r.extreme_direction === 'long_crowded'
          ? '多头拥挤'
          : r.extreme_direction === 'short_crowded'
          ? '空头拥挤'
          : absZ >= 1 ? (z > 0 ? '多头偏强' : '空头偏强')
          : '中性';
        const widthPct = Math.min(50, absZ * 18);

        return (
          <div
            key={r.symbol}
            className={cn(
              'grid grid-cols-[100px_110px_70px_1fr_120px_60px] items-center gap-3 rounded-xl px-3 py-2 text-sm',
              extreme ? 'bg-indigo-500/[0.06]' : 'hover:bg-zinc-900/40',
            )}
          >
            <div className="font-mono text-zinc-100">
              {extreme && <span className="text-indigo-300 mr-1">✦</span>}
              {r.symbol}
            </div>
            <div className="text-right font-mono tabular-nums text-zinc-400 text-xs">
              {(r.current_funding_rate * 100).toFixed(4)}%
            </div>
            <div className={cn('text-right font-mono tabular-nums', zCls)}>
              {z >= 0 ? '+' : ''}{z.toFixed(2)}
            </div>
            <div className="relative h-2 rounded-full bg-zinc-900 overflow-hidden">
              <span className="absolute left-1/2 -top-0.5 -bottom-0.5 w-px bg-zinc-700" />
              {z > 0 && (
                <span
                  className={cn('absolute top-0 h-full rounded-r-full', extreme ? 'bg-rose-500' : 'bg-rose-500/60')}
                  style={{ left: '50%', width: `${widthPct}%` }}
                />
              )}
              {z < 0 && (
                <span
                  className={cn('absolute top-0 h-full rounded-l-full', extreme ? 'bg-emerald-500' : 'bg-emerald-500/60')}
                  style={{ right: '50%', width: `${widthPct}%` }}
                />
              )}
            </div>
            <div className="text-xs text-zinc-400">{labelText}</div>
            <div className="text-right text-xs text-zinc-600">n={r.sample_size_30d}</div>
          </div>
        );
      })}
    </div>
  );
}
