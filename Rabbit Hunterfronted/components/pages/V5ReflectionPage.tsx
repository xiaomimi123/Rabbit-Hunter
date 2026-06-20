import { ReactNode, useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Star, AlertCircle } from 'lucide-react';
import {
  useV5Reflections, useV5FailureTaxonomy,
  useV5SizingRecommendations, useV5DecideSizing,
} from '../../hooks/api/useV5Reflections';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Term } from '../shared/Term';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { TextInput, PrimaryButton, SecondaryButton, DangerButton } from '../primitives-v3/FormField';
import { cardClassName, cn } from '../primitives-v3/cn';
import type { ReflectionRecord } from '../../types';

type Tab = 'recent' | 'taxonomy' | 'sizing';

export function V5ReflectionPage() {
  const [tab, setTab] = useState<Tab>('recent');
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-6 space-y-6">
      <SectionTitle
        title="复盘工作台"
        subtitle={`field debrief · ${now.toLocaleTimeString('zh-CN', { hour12: false })}`}
      />

      <div className="flex gap-1 rounded-2xl border border-zinc-800 bg-zinc-900/40 p-1 w-fit">
        <TabButton active={tab === 'recent'}   onClick={() => setTab('recent')}>最近复盘流</TabButton>
        <TabButton active={tab === 'taxonomy'} onClick={() => setTab('taxonomy')}>失败模式</TabButton>
        <TabButton active={tab === 'sizing'}   onClick={() => setTab('sizing')}>仓位建议</TabButton>
      </div>

      {tab === 'recent'   && <RecentReflectionsTab />}
      {tab === 'taxonomy' && <TaxonomyTab />}
      {tab === 'sizing'   && <SizingTab />}
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-xl px-4 py-2 text-sm transition',
        active
          ? 'bg-indigo-500 text-white shadow-md shadow-indigo-500/20'
          : 'text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900/60',
      )}
    >
      {children}
    </button>
  );
}

/* ─────────────── tab 1: recent ─────────────── */

function RecentReflectionsTab() {
  const q = useV5Reflections(20);
  if (q.isLoading) return <LoadingSkeleton message="拉取最近复盘…" />;
  const rows = q.data?.data ?? [];

  if (rows.length === 0) {
    return (
      <EmptyState>
        等待第一笔关仓后,reflection worker 自动生成
      </EmptyState>
    );
  }

  return (
    <div className="space-y-4">
      {rows.map(r => <ReflectionCard key={r.id} r={r} />)}
    </div>
  );
}

function ReflectionCard({ r }: { r: ReflectionRecord }) {
  const outcomeTone: 'emerald' | 'rose' | 'zinc' =
    r.outcome_class === 'WIN' ? 'emerald' :
    r.outcome_class === 'LOSS' ? 'rose' : 'zinc';
  const rTone = r.realized_r >= 0 ? 'text-emerald-300' : 'text-rose-300';
  const fundingExtreme = r.funding_z_score_at_entry != null && Math.abs(r.funding_z_score_at_entry) >= 2.0;

  return (
    <article className={cardClassName('!p-0 overflow-hidden')}>
      <header className="flex flex-wrap items-center gap-3 px-5 pt-4 pb-3 border-b border-zinc-800">
        <span className="font-mono text-[11px] text-zinc-500">pos #{r.paper_trade_id}</span>
        <span className="font-mono text-base font-semibold text-zinc-50">{r.symbol ?? '—'}</span>
        {r.side && (
          <StatusPill tone={r.side === 'LONG' ? 'emerald' : 'rose'} icon={r.side === 'LONG' ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}>
            {r.side}
          </StatusPill>
        )}
        <span className={cn('font-mono text-sm tabular-nums', rTone)}>
          R {r.realized_r >= 0 ? '+' : ''}{r.realized_r.toFixed(2)}
        </span>
        <StatusPill tone={outcomeTone} className="ml-auto">
          {r.outcome_class}
        </StatusPill>
      </header>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 px-5 py-3 border-b border-zinc-800 text-xs text-zinc-400">
        <span><span className="text-zinc-500">setup:</span> {r.setup_type}</span>
        <span><span className="text-zinc-500">hold:</span> {r.holding_minutes}min</span>
        <span><span className="text-zinc-500">AI:</span> {r.ai_model ?? '—'} ({r.ai_latency_ms ?? '—'}ms)</span>
      </div>

      {r.funding_z_score_at_entry != null && (
        <div className={cn(
          'px-5 py-2 border-b border-zinc-800 text-xs font-mono',
          fundingExtreme ? 'bg-indigo-500/[0.06] text-indigo-200' : 'text-zinc-400',
        )}>
          {fundingExtreme && <span className="mr-1.5">✦</span>}
          funding @ entry: {((r.funding_rate_at_entry ?? 0) * 100).toFixed(4)}%/8h · z={r.funding_z_score_at_entry.toFixed(2)}
          {fundingExtreme && <span className="ml-2 uppercase tracking-wide text-[10px]">extreme</span>}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-zinc-800">
        <Question label="为什么开仓">{r.why_entered}</Question>
        <Question label="当时怎么想">{r.what_was_expected}</Question>
        <Question label="实际怎么走">{r.what_actually_happened}</Question>
        <Question label="下次怎么改" star>{r.correction_idea}</Question>
      </div>

      <footer className="flex items-center justify-between px-5 py-3 text-xs">
        <div>
          {r.failure_mode_key && (
            <StatusPill tone="indigo">
              <Term k="failure_mode">failure_mode</Term>: {r.failure_mode_key}
            </StatusPill>
          )}
        </div>
        <div className="text-zinc-500">
          {r.self_assessed_prediction_accuracy != null && (
            <>self · <span className="text-zinc-200">{(r.self_assessed_prediction_accuracy * 100).toFixed(0)}%</span></>
          )}
        </div>
      </footer>
    </article>
  );
}

function Question({ label, children, star }: { label: string; children: ReactNode; star?: boolean }) {
  return (
    <div className="bg-zinc-900/70 p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-indigo-400 text-xs">▶</span>
        <span className="text-xs text-zinc-400">{label}</span>
        {star && <Star className="h-3 w-3 text-indigo-300 fill-indigo-300" />}
      </div>
      <div className="text-sm text-zinc-200 leading-relaxed">{children}</div>
    </div>
  );
}

/* ─────────────── tab 2: taxonomy ─────────────── */

function TaxonomyTab() {
  const q = useV5FailureTaxonomy();
  if (q.isLoading) return <LoadingSkeleton message="拉取失败模式分类…" />;
  const rows = q.data?.data ?? [];

  if (rows.length === 0) return <EmptyState>暂无失败模式记录</EmptyState>;

  return (
    <Card className="!p-0" bodyClassName="!p-0">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
              <th className="py-3 pl-5 pr-2 font-medium">key</th>
              <th className="py-3 px-2 font-medium">中文标签</th>
              <th className="py-3 px-2 font-medium text-right">命中</th>
              <th className="py-3 px-2 font-medium">detection_rule</th>
              <th className="py-3 px-2 font-medium">来源</th>
              <th className="py-3 pl-2 pr-5 font-medium text-right">激活</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {rows.map(m => (
              <tr key={m.key} className="hover:bg-zinc-900/40">
                <td className="py-2.5 pl-5 pr-2 font-mono text-xs text-zinc-300">{m.key}</td>
                <td className="py-2.5 px-2 text-zinc-100">{m.label_zh}</td>
                <td className={cn('py-2.5 px-2 text-right font-mono tabular-nums', m.sample_count > 0 ? 'text-indigo-300' : 'text-zinc-600')}>
                  {m.sample_count}
                </td>
                <td className="py-2.5 px-2 text-xs text-zinc-500 max-w-md truncate">{m.detection_rule ?? '—'}</td>
                <td className="py-2.5 px-2">
                  <StatusPill tone={m.seeded ? 'zinc' : 'indigo'}>
                    {m.seeded ? '预置' : 'AI 提案'}
                  </StatusPill>
                </td>
                <td className={cn('py-2.5 pl-2 pr-5 text-right', m.is_active ? 'text-emerald-300' : 'text-zinc-600')}>
                  {m.is_active ? '●' : '○'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/* ─────────────── tab 3: sizing ─────────────── */

function SizingTab() {
  const q = useV5SizingRecommendations();
  const decide = useV5DecideSizing();
  if (q.isLoading) return <LoadingSkeleton message="拉取仓位建议…" />;
  const rows = q.data?.data ?? [];

  if (rows.length === 0) {
    return <EmptyState>还没有 pending 的仓位建议 — 每周日 04:00 UTC 自动生成</EmptyState>;
  }

  return (
    <div className="space-y-4">
      {rows.map(r => <SizingCard key={r.id} r={r} onDecide={decide.mutate} />)}
    </div>
  );
}

function SizingCard({ r, onDecide }: { r: any; onDecide: (args: any) => void }) {
  const [modValue, setModValue] = useState<number | ''>('');
  const deltaPct = ((r.recommended_size_multiplier - r.current_size_multiplier) / r.current_size_multiplier) * 100;
  const tone = deltaPct >= 0 ? 'text-emerald-300' : 'text-rose-300';

  return (
    <article className={cardClassName('space-y-4')}>
      <header className="flex items-baseline justify-between flex-wrap gap-2">
        <div className="font-mono text-sm text-zinc-100">
          <span className="text-zinc-500 mr-1">setup_type:</span>{r.setup_type}
        </div>
        <div className="text-xs text-zinc-400">
          置信度 · <span className="text-indigo-300">{(r.confidence_score * 100).toFixed(0)}%</span>
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 p-3">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">当前</div>
          <div className="font-mono text-xl text-zinc-100 tabular-nums">{r.current_size_multiplier.toFixed(3)}</div>
        </div>
        <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 p-3">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Recommended</div>
          <div className={cn('font-mono text-xl tabular-nums', tone)}>
            {r.recommended_size_multiplier.toFixed(3)}
            <span className="text-xs ml-2">({deltaPct >= 0 ? '+' : ''}{deltaPct.toFixed(0)}%)</span>
          </div>
        </div>
        <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 p-3">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Kelly 30/60/90d</div>
          <div className="font-mono text-xs text-zinc-300 tabular-nums">
            {r.kelly_f_30d?.toFixed(3) ?? '—'} / {r.kelly_f_60d?.toFixed(3) ?? '—'} / {r.kelly_f_90d?.toFixed(3) ?? '—'}
          </div>
        </div>
      </div>

      <div className="text-sm text-zinc-300 leading-relaxed">{r.rationale}</div>

      <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-zinc-800">
        <PrimaryButton
          className="bg-emerald-500 hover:bg-emerald-400"
          onClick={() => onDecide({ id: r.id, decision: 'approve' })}
        >
          批准 ✓
        </PrimaryButton>
        <DangerButton onClick={() => onDecide({ id: r.id, decision: 'reject' })}>
          拒绝 ✗
        </DangerButton>
        <div className="ml-auto flex items-center gap-2">
          <TextInput
            type="number"
            step="0.001"
            value={modValue}
            onChange={(e) => setModValue(e.target.value === '' ? '' : Number(e.target.value))}
            placeholder="改值"
            className="w-28"
          />
          <SecondaryButton
            disabled={modValue === ''}
            onClick={() => onDecide({ id: r.id, decision: 'modify', modified_value: Number(modValue) })}
          >
            修改后批准
          </SecondaryButton>
        </div>
      </div>
    </article>
  );
}

/* ─────────────── shared ─────────────── */

function EmptyState({ children }: { children: ReactNode }) {
  return (
    <Card>
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-zinc-800">
          <AlertCircle className="h-5 w-5 text-zinc-500" />
        </div>
        <div className="text-sm text-zinc-400">{children}</div>
      </div>
    </Card>
  );
}
