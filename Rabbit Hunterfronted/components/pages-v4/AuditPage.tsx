import { useState } from 'react';
import {
  useV5Reflections, useV5FailureTaxonomy, useV5Calibration,
} from '../../hooks/api/useV5Reflections';
import { useV5AIDecisions } from '../../hooks/api/useV5AIStatus';
import { Drawer } from '../primitives-v3/Drawer';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { MetricCard } from '../primitives-v3/MetricCard';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { cn } from '../primitives-v3/cn';
import type { ReflectionRecord } from '../../types';

export function AuditPage() {
  const refl = useV5Reflections(50);
  const taxonomy = useV5FailureTaxonomy();
  const calib = useV5Calibration();
  const decisions = useV5AIDecisions(50);

  const [drillKey, setDrillKey] = useState<{ mode: 'mode' | 'symbol'; key: string } | null>(null);

  const reflections = refl.data?.data ?? [];
  const modes = taxonomy.data?.data ?? [];
  const calibPoints = calib.data?.data ?? [];
  const decisionList = decisions.data?.decisions ?? [];

  // Group reflections by setup_type as "regime"
  const byRegime: Record<string, ReflectionRecord[]> = {};
  for (const r of reflections) {
    const k = r.setup_type ?? 'unknown';
    if (!byRegime[k]) byRegime[k] = [];
    byRegime[k].push(r);
  }
  const bySymbol: Record<string, ReflectionRecord[]> = {};
  for (const r of reflections) {
    const k = r.symbol ?? 'unknown';
    if (!bySymbol[k]) bySymbol[k] = [];
    bySymbol[k].push(r);
  }

  const totalRefl = reflections.length;
  const wins = reflections.filter(r => r.outcome_class === 'WIN').length;
  const avgR = totalRefl ? reflections.reduce((a, r) => a + r.realized_r, 0) / totalRefl : 0;

  const drillRows = drillKey
    ? (drillKey.mode === 'mode' ? byRegime[drillKey.key] : bySymbol[drillKey.key]) ?? []
    : [];

  return (
    <div className="space-y-6">
      <SectionTitle
        title="监控审计"
        subtitle="复盘记录、失败模式分类、AI 置信度校准"
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="总复盘数" value={String(totalRefl)} hint={`${wins} 胜 / ${totalRefl - wins} 败`} />
        <MetricCard label="胜率" value={`${totalRefl ? Math.round(wins / totalRefl * 100) : 0}%`} />
        <MetricCard label="平均 R" value={`${avgR.toFixed(2)}`} trend={avgR >= 0 ? 'up' : 'down'} hint="across all reflections" />
        <MetricCard label="失败模式库" value={String(modes.length)} hint={`${modes.filter(m => m.is_active).length} 激活`} />
        <MetricCard label="校准点" value={String(calibPoints.length)} hint="按 model × 区间" />
        <MetricCard label="近 AI 决策" value={String(decisionList.length)} hint={`通过 ${decisionList.filter(d => d.execute).length}`} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="按 setup_type 分类" subtitle="点击查看明细">
          {Object.keys(byRegime).length === 0 ? (
            <div className="py-6 text-center text-sm text-zinc-500">无数据</div>
          ) : (
            <div className="space-y-2">
              {Object.entries(byRegime).sort((a, b) => b[1].length - a[1].length).map(([key, items]) => {
                const w = items.filter(r => r.outcome_class === 'WIN').length;
                const wr = items.length ? w / items.length : 0;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setDrillKey({ mode: 'mode', key })}
                    className="w-full flex items-center gap-3 rounded-2xl border border-zinc-800 bg-zinc-950/60 px-4 py-3 text-left hover:border-indigo-500 transition"
                  >
                    <div className="flex-1">
                      <div className="font-mono text-sm text-zinc-100">{key}</div>
                      <div className="text-xs text-zinc-500 mt-0.5">{items.length} 条 · 胜率 {(wr * 100).toFixed(0)}%</div>
                    </div>
                    <StatusPill tone={wr >= 0.5 ? 'emerald' : wr >= 0.4 ? 'amber' : 'rose'}>{(wr * 100).toFixed(0)}%</StatusPill>
                  </button>
                );
              })}
            </div>
          )}
        </Card>

        <Card title="按 symbol 分类" subtitle="点击查看明细">
          {Object.keys(bySymbol).length === 0 ? (
            <div className="py-6 text-center text-sm text-zinc-500">无数据</div>
          ) : (
            <div className="space-y-2">
              {Object.entries(bySymbol).sort((a, b) => b[1].length - a[1].length).map(([key, items]) => {
                const w = items.filter(r => r.outcome_class === 'WIN').length;
                const wr = items.length ? w / items.length : 0;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setDrillKey({ mode: 'symbol', key })}
                    className="w-full flex items-center gap-3 rounded-2xl border border-zinc-800 bg-zinc-950/60 px-4 py-3 text-left hover:border-indigo-500 transition"
                  >
                    <div className="flex-1">
                      <div className="font-mono text-sm text-zinc-100">{key}</div>
                      <div className="text-xs text-zinc-500 mt-0.5">{items.length} 条 · 胜率 {(wr * 100).toFixed(0)}%</div>
                    </div>
                    <StatusPill tone={wr >= 0.5 ? 'emerald' : wr >= 0.4 ? 'amber' : 'rose'}>{(wr * 100).toFixed(0)}%</StatusPill>
                  </button>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      <Card title="失败模式分类" subtitle={`${modes.length} 项 · ${modes.filter(m => m.is_active).length} 激活`} className="!p-0" bodyClassName="!p-0">
        {modes.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-zinc-500">无失败模式数据</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                  <th className="py-3 pl-5 pr-2">key</th>
                  <th className="py-3 px-2">中文标签</th>
                  <th className="py-3 px-2 text-right">命中</th>
                  <th className="py-3 px-2">来源</th>
                  <th className="py-3 pl-2 pr-5 text-right">激活</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {modes.map(m => (
                  <tr key={m.key} className="hover:bg-zinc-900/40">
                    <td className="py-2.5 pl-5 pr-2 font-mono text-xs text-zinc-300">{m.key}</td>
                    <td className="py-2.5 px-2 text-zinc-100">{m.label_zh}</td>
                    <td className={cn('py-2.5 px-2 text-right font-mono tabular-nums', m.sample_count > 0 ? 'text-indigo-300' : 'text-zinc-600')}>{m.sample_count}</td>
                    <td className="py-2.5 px-2"><StatusPill tone={m.seeded ? 'zinc' : 'indigo'}>{m.seeded ? '预置' : 'AI 提案'}</StatusPill></td>
                    <td className={cn('py-2.5 pl-2 pr-5 text-right', m.is_active ? 'text-emerald-300' : 'text-zinc-600')}>{m.is_active ? '●' : '○'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Drawer
        open={!!drillKey}
        title={drillKey ? `${drillKey.mode === 'mode' ? 'setup' : 'symbol'}: ${drillKey.key}` : ''}
        subtitle={`${drillRows.length} 条复盘`}
        onClose={() => setDrillKey(null)}
      >
        <div className="space-y-3">
          {drillRows.map(r => (
            <div key={r.id} className="rounded-2xl border border-zinc-800 bg-zinc-950/60 p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="font-mono text-zinc-100">{r.symbol}</span>
                <StatusPill tone={r.side === 'LONG' ? 'emerald' : 'rose'}>{r.side}</StatusPill>
                <StatusPill tone={r.outcome_class === 'WIN' ? 'emerald' : r.outcome_class === 'LOSS' ? 'rose' : 'zinc'}>{r.outcome_class}</StatusPill>
                <span className={cn('ml-auto font-mono text-sm', r.realized_r >= 0 ? 'text-emerald-300' : 'text-rose-300')}>R {r.realized_r >= 0 ? '+' : ''}{r.realized_r.toFixed(2)}</span>
              </div>
              <div className="text-xs text-zinc-400 leading-relaxed line-clamp-3">
                {r.correction_idea || r.what_actually_happened}
              </div>
            </div>
          ))}
        </div>
      </Drawer>
    </div>
  );
}
