import React, { useState } from 'react';
import { useV5Reflections, useV5FailureTaxonomy,
         useV5SizingRecommendations, useV5DecideSizing } from '../../hooks/api/useV5Reflections';
import { Card } from '../primitives/Card';
import { Badge } from '../primitives/Badge';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Term } from '../shared/Term';
import type { ReflectionRecord } from '../../types';
import { Brain, AlertTriangle, Scale } from 'lucide-react';

type Tab = 'recent' | 'taxonomy' | 'sizing';

export function V5ReflectionPage() {
  const [tab, setTab] = useState<Tab>('recent');

  return (
    <div className="space-y-4">
      <div className="flex gap-2 text-xs">
        <TabButton active={tab === 'recent'} onClick={() => setTab('recent')} icon={<Brain size={14} />}>
          最近复盘流
        </TabButton>
        <TabButton active={tab === 'taxonomy'} onClick={() => setTab('taxonomy')} icon={<AlertTriangle size={14} />}>
          失败模式
        </TabButton>
        <TabButton active={tab === 'sizing'} onClick={() => setTab('sizing')} icon={<Scale size={14} />}>
          仓位建议
        </TabButton>
      </div>

      {tab === 'recent' && <RecentReflectionsTab />}
      {tab === 'taxonomy' && <TaxonomyTab />}
      {tab === 'sizing' && <SizingTab />}
    </div>
  );
}

function TabButton({ active, onClick, icon, children }:
                   { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-1 rounded-sm border px-3 py-1.5 font-mono transition-colors ${
        active
          ? 'border-accent-info bg-accent-info/10 text-accent-info'
          : 'border-white/10 text-white/60 hover:bg-white/5'
      }`}
    >
      {icon}{children}
    </button>
  );
}

function RecentReflectionsTab() {
  const q = useV5Reflections(20);
  if (q.isLoading) return <LoadingSkeleton rows={6} />;
  const rows = q.data?.data ?? [];

  if (rows.length === 0) {
    return (
      <Card title="最近复盘流">
        <div className="py-12 text-center text-white/40">
          ▌ 等待第一笔关仓后,reflection worker 自动生成
        </div>
      </Card>
    );
  }

  return (
    <Card title={`最近复盘流 (n=${rows.length})`}>
      <div className="space-y-3">
        {rows.map(r => <ReflectionCard key={r.id} r={r} />)}
      </div>
    </Card>
  );
}

function TaxonomyTab() {
  const q = useV5FailureTaxonomy();
  if (q.isLoading) return <LoadingSkeleton rows={5} />;
  const rows = q.data?.data ?? [];

  return (
    <Card title={`失败模式分布 (n=${rows.length})`}>
      <div className="overflow-hidden rounded-md border border-white/10">
        <table className="w-full text-xs">
          <thead className="bg-white/5">
            <tr className="text-left text-white/60">
              <th className="px-2 py-2">key</th>
              <th className="px-2 py-2">中文标签</th>
              <th className="px-2 py-2 text-right">命中次数</th>
              <th className="px-2 py-2">detection_rule</th>
              <th className="px-2 py-2">来源</th>
              <th className="px-2 py-2 text-right">激活</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(m => (
              <tr key={m.key} className="border-t border-white/5 hover:bg-white/[0.02]">
                <td className="px-2 py-1.5 font-mono text-white/80">{m.key}</td>
                <td className="px-2 py-1.5 text-white">{m.label_zh}</td>
                <td className="px-2 py-1.5 text-right font-mono">
                  {m.sample_count > 0
                    ? <span className="text-accent-warn">{m.sample_count}</span>
                    : <span className="text-white/30">0</span>}
                </td>
                <td className="px-2 py-1.5 font-mono text-white/50 truncate max-w-xs">
                  {m.detection_rule ?? '—'}
                </td>
                <td className="px-2 py-1.5">
                  {m.seeded
                    ? <Badge variant="info">预置</Badge>
                    : <Badge variant="warn">AI 提案</Badge>}
                </td>
                <td className="px-2 py-1.5 text-right">
                  {m.is_active
                    ? <span className="text-accent-long">●</span>
                    : <span className="text-white/30">○</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function SizingTab() {
  const q = useV5SizingRecommendations();
  const decide = useV5DecideSizing();
  if (q.isLoading) return <LoadingSkeleton rows={4} />;
  const rows = q.data?.data ?? [];

  if (rows.length === 0) {
    return (
      <Card title="仓位建议(等审批)">
        <div className="py-12 text-center text-white/40">
          ▌ 还没有 pending 的仓位建议。每周日 04:00 UTC 自动生成
        </div>
      </Card>
    );
  }

  return (
    <Card title={`仓位建议 — 待审批 (${rows.length})`}>
      <div className="space-y-3">
        {rows.map(r => <SizingCard key={r.id} r={r} onDecide={decide.mutate} />)}
      </div>
    </Card>
  );
}

function SizingCard({ r, onDecide }: {
  r: any; onDecide: (args: any) => void;
}) {
  const [modValue, setModValue] = useState<number | ''>('');
  const deltaPct = ((r.recommended_size_multiplier - r.current_size_multiplier)
                    / r.current_size_multiplier) * 100;
  const tone = deltaPct >= 0 ? 'text-accent-long' : 'text-accent-short';
  return (
    <div className="rounded-md border border-white/10 bg-bg-base p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="font-mono text-sm text-white">setup_type: {r.setup_type}</div>
        <div className="text-xs text-white/50 font-mono">
          confidence {(r.confidence_score * 100).toFixed(0)}%
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 text-xs font-mono">
        <div>
          <div className="text-white/50">当前 size 倍数</div>
          <div className="text-white text-base">{r.current_size_multiplier.toFixed(3)}</div>
        </div>
        <div>
          <div className="text-white/50">推荐 size 倍数</div>
          <div className={`${tone} text-base`}>
            {r.recommended_size_multiplier.toFixed(3)}
            <span className="text-xs ml-2">({deltaPct >= 0 ? '+' : ''}{deltaPct.toFixed(0)}%)</span>
          </div>
        </div>
        <div>
          <div className="text-white/50">Kelly 30/60/90d</div>
          <div className="text-white/80 text-xs">
            {r.kelly_f_30d?.toFixed(3) ?? '—'} / {r.kelly_f_60d?.toFixed(3) ?? '—'} / {r.kelly_f_90d?.toFixed(3) ?? '—'}
          </div>
        </div>
      </div>
      <div className="text-xs text-white/60">{r.rationale}</div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onDecide({ id: r.id, decision: 'approve' })}
          className="rounded-sm border border-accent-long/40 bg-accent-long/10 px-3 py-1 text-xs text-accent-long"
        >
          批准
        </button>
        <button
          type="button"
          onClick={() => onDecide({ id: r.id, decision: 'reject' })}
          className="rounded-sm border border-accent-short/40 bg-accent-short/10 px-3 py-1 text-xs text-accent-short"
        >
          拒绝
        </button>
        <input
          type="number"
          step="0.001"
          value={modValue}
          onChange={(e) => setModValue(e.target.value === '' ? '' : Number(e.target.value))}
          placeholder="改值"
          className="w-24 rounded-sm border border-white/15 bg-bg-base px-2 py-1 text-xs text-white"
        />
        <button
          type="button"
          disabled={modValue === ''}
          onClick={() => onDecide({ id: r.id, decision: 'modify',
                                     modified_value: Number(modValue) })}
          className="rounded-sm border border-accent-info/40 bg-accent-info/10 px-3 py-1 text-xs text-accent-info disabled:opacity-40"
        >
          修改后批准
        </button>
      </div>
    </div>
  );
}

function ReflectionCard({ r }: { r: ReflectionRecord }) {
  const outcomeTone =
    r.outcome_class === 'WIN' ? 'long' :
    r.outcome_class === 'LOSS' ? 'short' : 'neutral';
  const rTone = r.realized_r >= 0 ? 'text-accent-long' : 'text-accent-short';

  return (
    <div className="rounded-md border border-white/10 bg-bg-base p-3 space-y-2">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="font-medium text-white">{r.symbol ?? '—'}</span>
          {r.side && <Badge variant={r.side === 'LONG' ? 'long' : 'short'}>{r.side}</Badge>}
          <Badge variant={outcomeTone as any}>{r.outcome_class}</Badge>
          <span className="font-mono text-white/50">setup: {r.setup_type}</span>
        </div>
        <div className="flex items-center gap-3 font-mono text-white/60">
          <span className={rTone}>R {r.realized_r >= 0 ? '+' : ''}{r.realized_r.toFixed(2)}</span>
          <span>{r.holding_minutes}min</span>
          <span>{new Date(r.created_at).toLocaleTimeString('zh-CN', { hour12: false })}</span>
        </div>
      </div>

      {r.funding_z_score_at_entry != null && (
        <div className="text-[11px] font-mono text-violet-300/70">
          funding @ entry: {((r.funding_rate_at_entry ?? 0) * 100).toFixed(4)}%/8h
          {' • '}z={r.funding_z_score_at_entry.toFixed(2)}
          {Math.abs(r.funding_z_score_at_entry) >= 2.0 && (
            <span className="ml-2 text-accent-warn">★ extreme</span>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <div className="text-cyan-300/70 mb-1">▶ 为什么开仓</div>
          <div className="text-white/80">{r.why_entered}</div>
        </div>
        <div>
          <div className="text-cyan-300/70 mb-1">▶ 当时怎么想</div>
          <div className="text-white/80">{r.what_was_expected}</div>
        </div>
        <div>
          <div className="text-cyan-300/70 mb-1">▶ 实际怎么走</div>
          <div className="text-white/80">{r.what_actually_happened}</div>
        </div>
        <div>
          <div className="text-cyan-300/70 mb-1">▶ 下次怎么改</div>
          <div className="text-white/80">{r.correction_idea}</div>
        </div>
      </div>

      <div className="flex items-center justify-between text-[11px] font-mono text-white/40">
        <div>
          {r.failure_mode_key && (
            <Badge variant="warn">
              <Term k="failure_mode">失败模式</Term>: {r.failure_mode_key}
            </Badge>
          )}
        </div>
        <div className="flex gap-3">
          <span>AI: {r.ai_model ?? '—'} ({r.ai_latency_ms ?? '—'}ms)</span>
          {r.self_assessed_prediction_accuracy != null && (
            <span>自评 {(r.self_assessed_prediction_accuracy * 100).toFixed(0)}%</span>
          )}
        </div>
      </div>
    </div>
  );
}
