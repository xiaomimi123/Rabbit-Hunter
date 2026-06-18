import { ReactNode, useEffect, useMemo, useState } from 'react';
import { useV5AIStatus, useV5AIDecisions } from '../../hooks/api/useV5AIStatus';
import { useV5Calibration } from '../../hooks/api/useV5Reflections';
import { useV5FundingStatus } from '../../hooks/api/useV5Funding';
import { useUIStore } from '../../services/store';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Sparkline } from '../primitives/Sparkline';
import { Aperture } from '../primitives/Aperture';

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

  return (
    <div className="px-8 py-7 pb-16 flex flex-col gap-7 max-w-[1400px]">
      <PageHead now={now} latencyMs={lastLatency} />

      {/* Triplet */}
      <section className="grid grid-cols-3 max-[1100px]:grid-cols-1 gap-px bg-hairline border border-hairline">
        <Triplet label="模型" status={healthy ? '在线' : '离线'}>
          <div className="font-display text-[2.6rem] leading-none tracking-tight">
            {provider.toLowerCase()}<span className="text-brass">·</span>{(s?.chat_model ?? 'chat').replace(/^[^-]+-/, '')}
          </div>
          <div className="font-body italic text-[0.78rem] text-ivory-40 mt-2">
            primary model · {s?.healthy_ratio_24h != null ? `${Math.round(s.healthy_ratio_24h * 100)}% healthy 24h` : 'no health record'}
          </div>
          <div className="mt-4 h-8">
            <Sparkline values={sparkValues.length > 1 ? sparkValues : [0, 0]} width={220} height={28} />
          </div>
          <div className="mt-2 flex justify-between font-mono text-[0.65rem] text-ivory-40 tracking-wide">
            <span>confidence · recent {decisions.length}</span>
            <span>avg{' '}
              <strong className="text-ivory font-medium">
                {decisions.length > 0
                  ? Math.round(decisions.reduce((a, d) => a + (d.confidence ?? 0) * 100, 0) / decisions.length)
                  : 0}%
              </strong>
            </span>
          </div>
        </Triplet>

        <Triplet label="RAG 记忆" status="已索引" tone="brass">
          <div className="font-display text-[2.6rem] leading-none tracking-tight">
            {s?.rag_cases_in_db ?? 0}
            <span className="font-mono text-ivory-40 text-[1.2rem] ml-2"> cases</span>
          </div>
          <div className="font-body italic text-[0.78rem] text-ivory-40 mt-2">
            {Math.round((s?.rag_utilization_24h ?? 0) * 100)}% utilized · last 24h
          </div>
          <div className="mt-4 h-1.5 bg-white/[0.04]">
            <div
              className="h-full bg-brass"
              style={{ width: `${Math.round((s?.rag_utilization_24h ?? 0) * 100)}%` }}
            />
          </div>
          <div className="mt-2 flex justify-between font-mono text-[0.65rem] text-ivory-40 tracking-wide">
            <span>utilization</span>
            <span>{s?.rag_cases_in_db ?? 0} indexed</span>
          </div>
        </Triplet>

        <Triplet label="24h 决策数" status={healthy ? '健康' : '静默'}>
          <div className="font-display text-[2.6rem] leading-none tracking-tight">
            {s?.decisions_24h ?? 0}
          </div>
          <div className="font-body italic text-[0.78rem] text-ivory-40 mt-2">
            {decisions.filter(d => d.execute).length} executed · {decisions.filter(d => !d.execute).length} rejected
          </div>
          <div className="mt-4 h-8">
            <Sparkline values={sparkValues.length > 1 ? sparkValues : [0, 0]} width={220} height={28} />
          </div>
          <div className="mt-2 flex justify-between font-mono text-[0.65rem] text-ivory-40 tracking-wide">
            <span>confidence trend</span>
            <span>last <strong className="text-ivory font-medium">{decisions.length}</strong></span>
          </div>
        </Triplet>
      </section>

      {/* Health beacon banner */}
      {lastAiEvent && (
        <div className="border border-hairline px-4 py-2.5 font-mono text-[0.78rem] text-brass bg-brass-soft">
          <span className="mr-2">▌</span>
          last health beacon · provider={lastAiEvent.provider} healthy={String(lastAiEvent.healthy)} latency={lastLatency ?? '—'}ms
        </div>
      )}

      <Section title="决策流" meta={`last ${decisions.length} events · live`}>
        {dec.isLoading ? (
          <LoadingSkeleton message="拉取决策流中…" />
        ) : decisions.length === 0 ? (
          <EmptyState message="等待下一条决策…" />
        ) : (
          <table className="w-full text-[0.78rem] border-collapse">
            <thead>
              <tr>
                <Th>时间</Th>
                <Th>币种</Th>
                <Th>结果</Th>
                <Th align="right">置信</Th>
                <Th align="right">顶 1 距</Th>
                <Th align="right">RAG</Th>
                <Th>分析</Th>
              </tr>
            </thead>
            <tbody>
              {decisions.map(d => (
                <tr
                  key={d.id}
                  className={`ticker-row border-b border-hairline hover:bg-brass/[0.04] ${
                    d.execute ? 'border-l-2 border-l-sage' : 'border-l-2 border-l-oxblood'
                  }`}
                >
                  <Td className="text-ivory-70">{new Date(d.created_at).toLocaleTimeString('zh-CN', { hour12: false })}</Td>
                  <Td className="text-ivory text-[0.85rem]">{d.symbol}</Td>
                  <Td>
                    <VerdictBadge execute={d.execute} />
                  </Td>
                  <Td align="right" className={d.execute ? 'text-sage' : 'text-oxblood'}>
                    {d.confidence == null ? '—' : `${Math.round(d.confidence * 100)}%`}
                  </Td>
                  <Td align="right">{d.top1_distance == null ? '—' : d.top1_distance.toFixed(2)}</Td>
                  <Td align="right" className="text-ivory-40">{d.rag_case_count}</Td>
                  <Td className="text-ivory-70 font-body italic max-w-[420px] leading-relaxed">
                    {d.reasoning.length > 100 ? d.reasoning.slice(0, 100) + '…' : d.reasoning}
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title="置信度校准" meta="预测对比实际 · 30d">
        <CalibrationTable />
      </Section>

      <Section title="Funding 拥挤度 · top 20" meta="|z| ≥ 2.0 为极端 · 按 |z| 降序">
        <FundingHeatmap />
      </Section>
    </div>
  );
}

/* ─────────────── helpers ─────────────── */

function PageHead({ now, latencyMs }: { now: Date; latencyMs: number | null }) {
  const t = now.toLocaleTimeString('zh-CN', { hour12: false });
  return (
    <header className="grid grid-cols-[1fr_auto] items-end gap-6 pb-4 border-b border-hairline-strong">
      <div className="flex items-center gap-4">
        <Aperture size={34} rotate className="text-brass" />
        <div>
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight">AI 状态</h1>
          <p className="font-cn text-ivory-40 text-[0.85rem] mt-1.5">决策头脑 · 校准 · 拥挤侦测</p>
        </div>
      </div>
      <div className="text-right font-mono text-[0.72rem] text-ivory-40 leading-relaxed">
        <div className="tracking-wider2 uppercase">上次心跳</div>
        <div><strong className="text-ivory font-medium">{t}</strong></div>
        <div>latency · <strong className="text-ivory font-medium">{latencyMs ?? '—'}{latencyMs != null && 'ms'}</strong></div>
      </div>
    </header>
  );
}

function Triplet({ label, status, tone = 'sage', children }: { label: string; status: string; tone?: 'sage' | 'brass'; children: ReactNode }) {
  const statusCls = tone === 'brass'
    ? 'text-brass border-brass bg-brass-soft'
    : 'text-sage border-sage bg-sage-soft';
  return (
    <div className="bg-bg-base p-6">
      <div className="flex items-center gap-2.5 mb-4.5">
        <Aperture size={16} className="text-brass" />
        <span className="font-mono text-[0.66rem] tracking-wider4 text-ivory-40 uppercase">{label}</span>
        <span className={`ml-auto font-mono text-[0.65rem] tracking-wider2 uppercase px-2 py-0.5 border ${statusCls}`}>
          {status}
        </span>
      </div>
      {children}
    </div>
  );
}

function Section({ title, meta, children }: { title: ReactNode; meta?: ReactNode; children: ReactNode }) {
  return (
    <section className="grid grid-cols-[1fr_200px] gap-7 items-start max-[1100px]:grid-cols-1">
      <div>
        <header className="flex items-center gap-3.5 pb-4 border-b border-hairline mb-5">
          <Aperture size={18} className="text-brass" />
          <h2 className="font-display text-[1.4rem] tracking-tight leading-none">{title}</h2>
          {meta && <span className="ml-auto font-mono text-[0.7rem] text-ivory-40 tracking-wide">{meta}</span>}
        </header>
        {children}
      </div>
      <aside className="font-body italic text-[0.78rem] text-ivory-40 leading-snug pt-[50px] border-l border-hairline pl-4 max-[1100px]:hidden">
        {/* placeholder for future annotations */}
      </aside>
    </section>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="py-8 text-center font-body italic text-ivory-40">
      <span className="opacity-60 mr-2">▌</span>{message}
    </div>
  );
}

function Th({ children, align = 'left' }: { children: ReactNode; align?: 'left' | 'right' }) {
  return (
    <th
      className={`text-${align} font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase font-normal px-3.5 py-2.5 border-b border-hairline`}
    >
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

function VerdictBadge({ execute }: { execute: boolean }) {
  const cls = execute
    ? 'text-sage border-sage bg-sage-soft'
    : 'text-oxblood border-oxblood bg-oxblood-soft';
  return (
    <span className={`inline-block px-2 py-0.5 border font-mono text-[0.66rem] tracking-wider2 uppercase ${cls}`}>
      {execute ? '通过' : '拒绝'}
    </span>
  );
}

function CalibrationTable() {
  const q = useV5Calibration();
  const points = q.data?.data ?? [];
  if (points.length === 0) return <EmptyState message="等待每桶至少 10 条 reflection…" />;

  return (
    <table className="w-full text-[0.78rem] border-collapse">
      <thead>
        <tr>
          <Th>模型 · 区间</Th>
          <Th align="right">n</Th>
          <Th align="right">预测</Th>
          <Th align="right">实际</Th>
          <Th align="right">偏差</Th>
          <Th align="right">校准倍数</Th>
        </tr>
      </thead>
      <tbody>
        {points.map(p => {
          const drift = p.actual_win_rate - p.predicted_win_rate;
          const driftCls =
            Math.abs(drift) < 0.05 ? 'text-sage'
            : Math.abs(drift) < 0.15 ? 'text-brass'
            : 'text-oxblood';
          return (
            <tr key={`${p.ai_model}-${p.confidence_bucket}`} className="border-b border-hairline hover:bg-brass/[0.04]">
              <Td className="text-ivory-70">{p.ai_model} · {(p.confidence_bucket * 100).toFixed(0)}%</Td>
              <Td align="right">{p.sample_count}</Td>
              <Td align="right">{(p.predicted_win_rate * 100).toFixed(1)}%</Td>
              <Td align="right" className={drift >= 0 ? 'text-sage' : 'text-oxblood'}>
                {(p.actual_win_rate * 100).toFixed(1)}%
              </Td>
              <Td align="right" className={driftCls}>
                {drift >= 0 ? '+' : ''}{(drift * 100).toFixed(1)}pt
              </Td>
              <Td align="right" className="text-ivory font-medium">×{p.calibration_multiplier.toFixed(2)}</Td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function FundingHeatmap() {
  const q = useV5FundingStatus();
  const rows = q.data?.data ?? [];
  if (rows.length === 0) return <EmptyState message="等待 funding 缓存刷新…" />;

  // sort by |z| desc (the preview shows extremes at top)
  const sorted = rows.slice().sort((a, b) => Math.abs(b.zscore_30d ?? 0) - Math.abs(a.zscore_30d ?? 0));

  return (
    <div className="font-mono text-[0.78rem]">
      {sorted.map(r => {
        const z = r.zscore_30d ?? 0;
        const absZ = Math.abs(z);
        const extreme = r.is_extreme;
        const zCls = extreme
          ? (z > 0 ? 'text-oxblood' : 'text-sage')
          : absZ >= 1 ? 'text-brass'
          : 'text-ivory-70';
        const labelText = r.extreme_direction === 'long_crowded'
          ? 'LONGS✦CROWDED'
          : r.extreme_direction === 'short_crowded'
          ? 'SHORTS✦CROWDED'
          : absZ >= 1 ? (z > 0 ? '多头偏强' : '空头偏强')
          : '中性';
        const labelCls = r.extreme_direction === 'long_crowded'
          ? 'text-oxblood'
          : r.extreme_direction === 'short_crowded'
          ? 'text-sage'
          : absZ >= 1 ? 'text-brass'
          : 'text-ivory-40';

        // Bipolar bar — half-width either side of center
        const widthPct = Math.min(50, absZ * 18);   // 18% per z-unit, cap 50

        return (
          <div
            key={r.symbol}
            className={`grid grid-cols-[100px_110px_80px_1fr_180px_60px] items-center gap-3.5 py-2 border-b border-hairline ${
              extreme ? 'bg-brass-soft -mx-3 px-3' : ''
            }`}
          >
            <div className="text-ivory">
              {extreme && <span className="text-brass mr-1">✦</span>}
              {r.symbol}
            </div>
            <div className="text-right text-ivory-70">
              {(r.current_funding_rate * 100).toFixed(4)}%
            </div>
            <div className={`text-right text-[0.85rem] ${zCls}`}>
              {z >= 0 ? '+' : ''}{z.toFixed(2)}
            </div>
            <div className="h-3 bg-white/[0.03] relative">
              <span className="absolute left-1/2 -top-0.5 -bottom-0.5 w-px bg-ivory-40" />
              {z > 0 && (
                <span
                  className={`absolute top-0 h-full ${extreme ? 'bg-brass-soft border-r border-oxblood' : 'bg-oxblood-soft border-r border-oxblood'}`}
                  style={{ left: '50%', width: `${widthPct}%` }}
                />
              )}
              {z < 0 && (
                <span
                  className={`absolute top-0 h-full ${extreme ? 'bg-brass-soft border-l border-sage' : 'bg-sage-soft border-l border-sage'}`}
                  style={{ right: '50%', width: `${widthPct}%` }}
                />
              )}
            </div>
            <div className={`text-[0.7rem] tracking-wide ${labelCls}`}>{labelText}</div>
            <div className="text-right text-[0.7rem] text-ivory-40">n={r.sample_size_30d}</div>
          </div>
        );
      })}
    </div>
  );
}
