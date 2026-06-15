import React, { useState } from 'react';
import { useV5Reflections } from '../../hooks/api/useV5Reflections';
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
      {tab === 'taxonomy' && <Card title="失败模式"><div className="text-white/40 text-sm">阶段 2 上线后启用</div></Card>}
      {tab === 'sizing' && <Card title="仓位建议"><div className="text-white/40 text-sm">阶段 3 上线后启用</div></Card>}
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
