import React, { useMemo } from 'react';
import { useV5AIStatus, useV5AIDecisions } from '../../hooks/api/useV5AIStatus';
import { useV5Calibration } from '../../hooks/api/useV5Reflections';
import { useUIStore } from '../../services/store';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Sparkline } from '../primitives/Sparkline';
import { Activity, Cpu, Database, Radio } from 'lucide-react';

function HoloCard({ children, glow = false, className = '' }: { children: React.ReactNode; glow?: boolean; className?: string }) {
  return (
    <div className={`relative rounded-md bg-gradient-to-r from-cyan-500/40 via-violet-500/30 to-cyan-500/40 p-px ${glow ? 'neon-pulse' : ''} ${className}`}>
      <div className="rounded-md bg-bg-surface/95 backdrop-blur p-4">
        {children}
      </div>
    </div>
  );
}

export function V5AIStatusPage() {
  const status = useV5AIStatus();
  const dec = useV5AIDecisions(20);
  const wsEvents = useUIStore(s => s.recentWsEvents);

  const decisions = dec.data?.decisions ?? [];
  const sparkValues = useMemo(
    () => decisions.slice().reverse().map(d => (d.confidence ?? 0) * 100),
    [decisions]
  );

  // Latest ws ai_health event for "live" feel
  const lastAiEvent = useMemo(() => {
    for (let i = wsEvents.length - 1; i >= 0; i--) {
      if (wsEvents[i].type === 'ai_health') return wsEvents[i];
    }
    return null;
  }, [wsEvents]);

  if (status.isLoading) return <LoadingSkeleton rows={4} />;
  const s = status.data;
  const provider = s?.provider ?? '未配置';
  const healthy = s?.healthy ?? false;

  return (
    <div className="cyber-grid -m-6 p-6 min-h-full space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <HoloCard glow={healthy}>
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-cyan-300/80">
                <Cpu size={11} /> PROVIDER
              </div>
              <div className="mt-2 font-mono text-2xl text-white cyan-glow">
                ▶ {provider.toUpperCase()}
              </div>
              <div className="mt-1 text-xs text-white/50 font-mono">
                {s?.chat_model ?? '—'}
              </div>
            </div>
            <div className="flex items-center gap-1">
              <span className={`inline-block w-2 h-2 rounded-full ${healthy ? 'bg-accent-long animate-pulse' : 'bg-accent-short'}`} />
              <span className={`text-[10px] font-mono ${healthy ? 'text-accent-long' : 'text-accent-short'}`}>
                {healthy ? '[ONLINE]' : '[OFFLINE]'}
              </span>
            </div>
          </div>
        </HoloCard>

        <HoloCard>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-cyan-300/80">
            <Database size={11} /> RAG MEMORY
          </div>
          <div className="mt-2 flex items-baseline gap-3">
            <div className="font-mono text-2xl text-white cyan-glow">
              {Math.round((s?.rag_utilization_24h ?? 0) * 100)}<span className="text-white/40 text-base">%</span>
            </div>
            <div className="text-xs text-white/50">利用率 (24h)</div>
          </div>
          <div className="mt-2 text-[10px] font-mono text-cyan-300/60">
            ▌ {s?.rag_cases_in_db ?? 0} cases indexed
          </div>
          <div className="mt-2 h-1 w-full rounded-full bg-white/5 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan-400 to-violet-400"
              style={{ width: `${Math.round((s?.rag_utilization_24h ?? 0) * 100)}%` }}
            />
          </div>
        </HoloCard>

        <HoloCard>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-cyan-300/80">
            <Activity size={11} /> DECISIONS (24h)
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <div className="font-mono text-2xl text-white cyan-glow">
              {s?.decisions_24h ?? 0}
            </div>
            <div className="text-xs text-white/40">total</div>
          </div>
          <div className="mt-3">
            <Sparkline values={sparkValues.length > 1 ? sparkValues : [0, 0]} width={180} height={28} />
          </div>
          <div className="text-[10px] font-mono text-cyan-300/60 mt-1">
            ▌ confidence over recent {decisions.length} decisions
          </div>
        </HoloCard>
      </div>

      {lastAiEvent && (
        <div className="rounded-md border border-cyan-500/30 bg-cyan-500/5 px-3 py-2 text-xs font-mono text-cyan-200">
          ▌ Last AI health beacon: provider={(lastAiEvent as any).provider} healthy={String((lastAiEvent as any).healthy)} latency={(lastAiEvent as any).last_latency_ms ?? '—'}ms
        </div>
      )}

      <HoloCard>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-cyan-300/80">
            <Radio size={11} className="animate-pulse text-cyan-300" />
            DECISION STREAM <span className="text-white/30">— last {decisions.length} events</span>
          </div>
          <div className="text-[10px] font-mono text-cyan-300/40">
            ▌ tail -f /var/log/v5/ai/decisions
          </div>
        </div>
        {dec.isLoading ? (
          <LoadingSkeleton rows={5} />
        ) : decisions.length === 0 ? (
          <div className="py-8 text-center font-mono text-cyan-300/40 text-xs">
            ▌ awaiting next decision...
          </div>
        ) : (
          <div className="space-y-1 max-h-[480px] overflow-y-auto">
            {decisions.map((d) => (
              <div
                key={d.id}
                className="ticker-row grid grid-cols-12 gap-2 px-2 py-1.5 rounded-sm font-mono text-xs border-l-2 transition-colors hover:bg-cyan-500/5"
                style={{ borderLeftColor: d.execute ? 'rgba(16,185,129,0.6)' : 'rgba(239,68,68,0.6)' }}
              >
                <div className="col-span-2 text-cyan-300/70">
                  {new Date(d.created_at).toLocaleTimeString('zh-CN', { hour12: false })}
                </div>
                <div className="col-span-2 text-white">{d.symbol}</div>
                <div className="col-span-1">
                  <span className={d.execute ? 'text-accent-long' : 'text-accent-short'}>
                    {d.execute ? '✓ EXEC' : '✗ DENY'}
                  </span>
                </div>
                <div className="col-span-1 text-cyan-300/70">
                  c={d.confidence == null ? '—' : d.confidence.toFixed(2)}
                </div>
                <div className="col-span-1 text-violet-300/70">
                  {d.top1_distance == null ? '' : `d=${d.top1_distance.toFixed(2)}`}
                </div>
                <div className="col-span-1 text-cyan-300/40">
                  [{d.rag_case_count} cases]
                </div>
                <div className="col-span-4 text-white/60 truncate">
                  {d.reasoning.length > 70 ? d.reasoning.slice(0, 70) + '…' : d.reasoning}
                </div>
              </div>
            ))}
          </div>
        )}
      </HoloCard>

      <CalibrationCurveCard />
    </div>
  );
}

function CalibrationCurveCard() {
  const q = useV5Calibration();
  const points = q.data?.data ?? [];
  return (
    <HoloCard>
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-cyan-300/80 mb-3">
        ▌ CONFIDENCE CALIBRATION CURVE
      </div>
      {points.length === 0 ? (
        <div className="py-8 text-center font-mono text-cyan-300/40 text-xs">
          ▌ awaiting first 10 reflections per bucket...
        </div>
      ) : (
        <div className="space-y-1 font-mono text-xs">
          {points.map(p => {
            const drift = p.actual_win_rate - p.predicted_win_rate;
            const tone = Math.abs(drift) < 0.05 ? 'text-accent-long'
                       : Math.abs(drift) < 0.15 ? 'text-accent-warn'
                       : 'text-accent-short';
            return (
              <div key={`${p.ai_model}-${p.confidence_bucket}`}
                   className="grid grid-cols-12 gap-2 py-1 border-b border-white/5">
                <div className="col-span-2 text-cyan-300/70">{p.ai_model}</div>
                <div className="col-span-2 text-white">{(p.confidence_bucket * 100).toFixed(0)}%</div>
                <div className="col-span-3 text-white/60">
                  predicted → actual {(p.actual_win_rate * 100).toFixed(0)}%
                </div>
                <div className={`col-span-2 ${tone}`}>
                  Δ {drift >= 0 ? '+' : ''}{(drift * 100).toFixed(0)}pt
                </div>
                <div className="col-span-2 text-violet-300/70">
                  ×{p.calibration_multiplier.toFixed(2)}
                </div>
                <div className="col-span-1 text-white/40 text-right">
                  n={p.sample_count}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </HoloCard>
  );
}
