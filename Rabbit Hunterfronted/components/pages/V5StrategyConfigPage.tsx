import { useEffect, useState } from 'react';
import { useV5StrategyConfig } from '../../hooks/api/useV5StrategyConfig';
import { Slider } from '../primitives/Slider';
import { NumberInput } from '../primitives/NumberInput';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { Alert } from '../primitives-v3/Alert';
import { PrimaryButton, SecondaryButton } from '../primitives-v3/FormField';
import { cn } from '../primitives-v3/cn';

export function V5StrategyConfigPage() {
  const { query, patch, preview } = useV5StrategyConfig();
  const [dirty, setDirty] = useState<Record<string, number>>({});
  const [previewMsg, setPreviewMsg] = useState<string | null>(null);

  useEffect(() => { setDirty({}); }, [query.data]);

  if (query.isLoading) return <LoadingSkeleton message="拉取策略参数…" />;
  const params = query.data?.params ?? [];

  const effectiveValue = (key: string, current: number) =>
    Object.prototype.hasOwnProperty.call(dirty, key) ? dirty[key] : current;

  const dirtyCount = Object.keys(dirty).length;
  const isDirty = dirtyCount > 0;

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-6 space-y-6">
      <SectionTitle
        title="策略配置"
        subtitle="参数调校 · 实时预览"
        action={
          isDirty ? (
            <StatusPill tone="indigo">{dirtyCount} 项待保存</StatusPill>
          ) : (
            <StatusPill tone="zinc">已同步</StatusPill>
          )
        }
      />

      <Card className="!p-3" bodyClassName="flex flex-wrap items-center gap-2">
        <SecondaryButton onClick={() => setDirty({})} disabled={!isDirty}>撤销修改</SecondaryButton>
        <SecondaryButton
          disabled={!isDirty || preview.isPending}
          onClick={async () => {
            const merged = params.reduce((acc, p) => {
              acc[p.key] = effectiveValue(p.key, p.value);
              return acc;
            }, {} as Record<string, number>);
            const res = await preview.mutateAsync(merged);
            setPreviewMsg(`预计每小时入场: ${res.estimated_entries_per_hour.toFixed(1)} · 胜率 ${(res.estimated_win_rate * 100).toFixed(0)}% · ${res.note}`);
          }}
        >
          {preview.isPending ? '预测中…' : '预览效果'}
        </SecondaryButton>
        <PrimaryButton
          disabled={!isDirty || patch.isPending}
          onClick={() => patch.mutate(dirty)}
        >
          {patch.isPending ? '保存中…' : '保存修改'}
        </PrimaryButton>
      </Card>

      {previewMsg && <Alert tone="info">{previewMsg}</Alert>}

      <Card title="参数列表" subtitle="拖动滑条或直接输入,带 ● 标记为本次修改">
        <div className="divide-y divide-zinc-800/60">
          {params.map(p => {
            const eff = effectiveValue(p.key, p.value);
            const isChanged = eff !== p.value;
            return (
              <div key={p.key} className="grid grid-cols-1 md:grid-cols-12 items-center gap-4 py-4">
                <div className="md:col-span-3">
                  <div className="font-mono text-sm text-zinc-100 flex items-center gap-1.5">
                    {isChanged && <span className="text-indigo-400">●</span>}
                    {p.key}
                  </div>
                  <div className="text-xs text-zinc-500 mt-0.5 leading-relaxed">{p.description}</div>
                </div>
                <div className="md:col-span-6">
                  <Slider value={eff} min={p.min} max={p.max} step={(p.max - p.min) / 100}
                          onChange={(v) => setDirty(d => ({ ...d, [p.key]: v }))} />
                </div>
                <div className="md:col-span-2">
                  <NumberInput value={eff} min={p.min} max={p.max} step={(p.max - p.min) / 100}
                               onChange={(v) => setDirty(d => ({ ...d, [p.key]: v }))} />
                </div>
                <div className={cn('md:col-span-1 text-right text-xs', isChanged ? 'text-indigo-300' : 'text-zinc-500')}>
                  {p.unit}
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
