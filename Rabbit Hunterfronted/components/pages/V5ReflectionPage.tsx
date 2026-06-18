import { ReactNode, useEffect, useState } from 'react';
import {
  useV5Reflections, useV5FailureTaxonomy,
  useV5SizingRecommendations, useV5DecideSizing,
} from '../../hooks/api/useV5Reflections';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Aperture } from '../primitives/Aperture';
import { Term } from '../shared/Term';
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
    <div className="px-8 py-7 pb-16 flex flex-col gap-7 max-w-[1400px]">
      <PageHead now={now} />

      <div className="flex items-center gap-0 border-b border-hairline-strong">
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

function PageHead({ now }: { now: Date }) {
  const t = now.toLocaleTimeString('zh-CN', { hour12: false });
  return (
    <header className="grid grid-cols-[1fr_auto] items-end gap-6 pb-4 border-b border-hairline-strong">
      <div className="flex items-center gap-4">
        <Aperture size={34} rotate className="text-brass" />
        <div>
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight">复盘</h1>
          <p className="font-cn text-ivory-40 text-[0.85rem] mt-1.5">复盘工作台 · field debrief</p>
        </div>
      </div>
      <div className="text-right font-mono text-[0.72rem] text-ivory-40 leading-relaxed">
        <div className="tracking-wider2 uppercase">观测时间</div>
        <div><strong className="text-ivory font-medium">{t}</strong> · UTC+8</div>
      </div>
    </header>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`font-cn text-[0.95rem] px-5 py-3 border-b-2 transition-colors ${
        active
          ? 'text-brass border-brass'
          : 'text-ivory-70 border-transparent hover:text-ivory hover:bg-white/[0.02]'
      }`}
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
    <div className="flex flex-col gap-4">
      {rows.map(r => <ReflectionCard key={r.id} r={r} />)}
    </div>
  );
}

function ReflectionCard({ r }: { r: ReflectionRecord }) {
  const outcomeCls =
    r.outcome_class === 'WIN'  ? 'text-sage border-sage bg-sage-soft' :
    r.outcome_class === 'LOSS' ? 'text-oxblood border-oxblood bg-oxblood-soft' :
                                 'text-ivory-70 border-hairline-strong';
  const rTone = r.realized_r >= 0 ? 'text-sage' : 'text-oxblood';
  const fundingExtreme = r.funding_z_score_at_entry != null && Math.abs(r.funding_z_score_at_entry) >= 2.0;

  return (
    <article className="border border-hairline bg-bg-base">
      <header className="flex items-center gap-3 pb-3 px-5 pt-4 border-b border-hairline">
        <span className="font-mono text-[0.7rem] text-ivory-40 tracking-wider">━━━ pos {r.paper_trade_id}</span>
        <span className="font-display text-[1.2rem] text-ivory">{r.symbol ?? '—'}</span>
        {r.side && (
          <span className={`font-mono text-[0.7rem] tracking-wider2 px-2 py-0.5 border ${
            r.side === 'LONG' ? 'text-sage border-sage bg-sage-soft' : 'text-oxblood border-oxblood bg-oxblood-soft'
          }`}>
            {r.side}
          </span>
        )}
        <span className={`font-mono text-[0.85rem] tabular-nums ${rTone}`}>
          R {r.realized_r >= 0 ? '+' : ''}{r.realized_r.toFixed(2)}
        </span>
        <span className={`ml-auto font-mono text-[0.66rem] tracking-wider2 px-2 py-0.5 border uppercase ${outcomeCls}`}>
          {r.outcome_class}
        </span>
      </header>

      <div className="px-5 pt-3 pb-3 border-b border-hairline flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[0.78rem] text-ivory-70">
        <span><span className="text-ivory-40">setup:</span> {r.setup_type}</span>
        <span><span className="text-ivory-40">hold:</span> {r.holding_minutes}min</span>
        <span><span className="text-ivory-40">AI:</span> {r.ai_model ?? '—'} ({r.ai_latency_ms ?? '—'}ms)</span>
      </div>

      {r.funding_z_score_at_entry != null && (
        <div className={`px-5 py-2.5 border-b border-hairline font-mono text-[0.78rem] ${fundingExtreme ? 'text-brass bg-brass-soft' : 'text-ivory-70'}`}>
          {fundingExtreme && <span className="mr-1.5">✦</span>}
          funding @ entry: {((r.funding_rate_at_entry ?? 0) * 100).toFixed(4)}%/8h · z={r.funding_z_score_at_entry.toFixed(2)}
          {fundingExtreme && <span className="ml-2 uppercase tracking-wider2">extreme</span>}
        </div>
      )}

      <div className="grid grid-cols-2 max-[640px]:grid-cols-1 gap-px bg-hairline">
        <Question label="为什么开仓">{r.why_entered}</Question>
        <Question label="当时怎么想">{r.what_was_expected}</Question>
        <Question label="实际怎么走">{r.what_actually_happened}</Question>
        <Question label="下次怎么改" star>{r.correction_idea}</Question>
      </div>

      <footer className="px-5 py-3 flex items-center justify-between text-[0.7rem] font-mono">
        <div>
          {r.failure_mode_key && (
            <span className="inline-block px-2 py-0.5 border border-brass text-brass bg-brass-soft tracking-wider2">
              <Term k="failure_mode">failure_mode</Term>: {r.failure_mode_key}
            </span>
          )}
        </div>
        <div className="text-ivory-40">
          {r.self_assessed_prediction_accuracy != null
            ? <>self · <span className="text-ivory">{(r.self_assessed_prediction_accuracy * 100).toFixed(0)}%</span></>
            : null}
        </div>
      </footer>
    </article>
  );
}

function Question({ label, children, star }: { label: string; children: ReactNode; star?: boolean }) {
  return (
    <div className="bg-bg-base p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="font-mono text-brass text-[0.78rem]">▶</span>
        <span className="font-cn text-[0.78rem] text-ivory-70">{label}</span>
        {star && <span className="text-brass font-mono text-[0.78rem]">★</span>}
      </div>
      <div className="font-body text-[0.85rem] text-ivory leading-relaxed">{children}</div>
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
    <table className="w-full text-[0.78rem] border-collapse">
      <thead>
        <tr>
          <Th>key</Th>
          <Th>中文标签</Th>
          <Th align="right">命中次数</Th>
          <Th>detection_rule</Th>
          <Th>来源</Th>
          <Th align="right">激活</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map(m => (
          <tr key={m.key} className="border-b border-hairline hover:bg-brass/[0.04]">
            <Td className="text-ivory-70">{m.key}</Td>
            <Td className="text-ivory font-cn">{m.label_zh}</Td>
            <Td align="right" className={m.sample_count > 0 ? 'text-brass' : 'text-ivory-25'}>
              {m.sample_count}
            </Td>
            <Td className="text-ivory-40 max-w-md truncate">{m.detection_rule ?? '—'}</Td>
            <Td>
              <span className={`inline-block px-2 py-0.5 border font-mono text-[0.65rem] tracking-wider2 uppercase ${
                m.seeded
                  ? 'text-ink border-ink bg-ink-soft'
                  : 'text-brass border-brass bg-brass-soft'
              }`}>
                {m.seeded ? '预置' : 'AI 提案'}
              </span>
            </Td>
            <Td align="right" className={m.is_active ? 'text-sage' : 'text-ivory-25'}>
              {m.is_active ? '●' : '○'}
            </Td>
          </tr>
        ))}
      </tbody>
    </table>
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
    <div className="flex flex-col gap-4">
      {rows.map(r => <SizingCard key={r.id} r={r} onDecide={decide.mutate} />)}
    </div>
  );
}

function SizingCard({ r, onDecide }: { r: any; onDecide: (args: any) => void }) {
  const [modValue, setModValue] = useState<number | ''>('');
  const deltaPct = ((r.recommended_size_multiplier - r.current_size_multiplier) / r.current_size_multiplier) * 100;
  const tone = deltaPct >= 0 ? 'text-sage' : 'text-oxblood';

  return (
    <article className="border border-hairline bg-bg-base p-5 flex flex-col gap-4">
      <header className="flex items-baseline justify-between">
        <div className="font-mono text-[0.85rem] text-ivory">
          <span className="text-ivory-40 mr-1">setup_type:</span>{r.setup_type}
        </div>
        <div className="font-mono text-[0.78rem] text-ivory-40">
          confidence · <span className="text-brass">{(r.confidence_score * 100).toFixed(0)}%</span>
        </div>
      </header>

      <div className="grid grid-cols-3 max-[640px]:grid-cols-1 gap-px bg-hairline border border-hairline">
        <div className="bg-bg-base p-3.5">
          <div className="font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase mb-1.5">当前</div>
          <div className="font-mono text-[1.5rem] text-ivory tabular-nums">{r.current_size_multiplier.toFixed(3)}</div>
        </div>
        <div className="bg-bg-base p-3.5">
          <div className="font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase mb-1.5">Recommended</div>
          <div className={`font-mono text-[1.5rem] tabular-nums ${tone}`}>
            {r.recommended_size_multiplier.toFixed(3)}
            <span className="text-[0.85rem] ml-2">({deltaPct >= 0 ? '+' : ''}{deltaPct.toFixed(0)}%)</span>
          </div>
        </div>
        <div className="bg-bg-base p-3.5">
          <div className="font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase mb-1.5">Kelly 30/60/90d</div>
          <div className="font-mono text-[0.9rem] text-ivory-70 tabular-nums">
            {r.kelly_f_30d?.toFixed(3) ?? '—'} / {r.kelly_f_60d?.toFixed(3) ?? '—'} / {r.kelly_f_90d?.toFixed(3) ?? '—'}
          </div>
        </div>
      </div>

      <div className="font-body italic text-[0.85rem] text-ivory-70 leading-relaxed">{r.rationale}</div>

      <div className="flex items-center gap-3 pt-3 border-t border-hairline flex-wrap">
        <SizingBtn variant="approve" onClick={() => onDecide({ id: r.id, decision: 'approve' })}>批准 ✓</SizingBtn>
        <SizingBtn variant="拒绝" onClick={() => onDecide({ id: r.id, decision: '拒绝' })}>拒绝 ✗</SizingBtn>
        <div className="flex items-center gap-2 ml-auto">
          <input
            type="number"
            step="0.001"
            value={modValue}
            onChange={(e) => setModValue(e.target.value === '' ? '' : Number(e.target.value))}
            placeholder="改值"
            className="w-24 font-mono text-[0.78rem] bg-bg-base border border-hairline-strong px-2 py-1 text-ivory focus:border-brass focus:outline-none"
          />
          <SizingBtn
            variant="modify"
            disabled={modValue === ''}
            onClick={() => onDecide({ id: r.id, decision: 'modify', modified_value: Number(modValue) })}
          >
            修改后批准
          </SizingBtn>
        </div>
      </div>
    </article>
  );
}

function SizingBtn({ variant, onClick, children, disabled }: { variant: 'approve' | '拒绝' | 'modify'; onClick: () => void; children: ReactNode; disabled?: boolean }) {
  const cls = {
    approve: 'border-sage text-sage bg-sage-soft hover:bg-sage hover:text-bg-base',
    reject:  'border-oxblood text-oxblood bg-oxblood-soft hover:bg-oxblood hover:text-ivory',
    modify:  'border-ink text-ink bg-ink-soft hover:bg-ink hover:text-ivory',
  }[variant];
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`font-mono text-[0.78rem] tracking-wider px-3.5 py-1.5 border bg-transparent uppercase transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed ${cls}`}
    >
      {children}
    </button>
  );
}

/* ─────────────── shared ─────────────── */

function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="py-14 text-center font-body italic text-ivory-40">
      <Aperture size={42} rotate="slow" className="text-ivory-25 mx-auto block mb-3" />
      <span className="opacity-60 mr-2">▌</span>{children}
    </div>
  );
}

function Th({ children, align = 'left' }: { children: ReactNode; align?: 'left' | 'right' }) {
  return (
    <th className={`text-${align} font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase font-normal px-3.5 py-2.5 border-b border-hairline`}>
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
