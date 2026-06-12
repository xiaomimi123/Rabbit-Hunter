import React, { useState, useEffect } from 'react';
import { useV5StrategyConfig } from '../../hooks/api/useV5StrategyConfig';
import { Card } from '../primitives/Card';
import { Slider } from '../primitives/Slider';
import { NumberInput } from '../primitives/NumberInput';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';

export function V5StrategyConfigPage() {
  const { query, patch, preview } = useV5StrategyConfig();
  const [dirty, setDirty] = useState<Record<string, number>>({});
  const [previewMsg, setPreviewMsg] = useState<string | null>(null);

  useEffect(() => { setDirty({}); }, [query.data]);

  if (query.isLoading) return <LoadingSkeleton rows={8} />;
  const params = query.data?.params ?? [];

  const effectiveValue = (key: string, current: number) =>
    Object.prototype.hasOwnProperty.call(dirty, key) ? dirty[key] : current;

  const isDirty = Object.keys(dirty).length > 0;

  return (
    <div className="space-y-4">
      <Card
        title="策略配置"
        actions={
          <>
            <button
              type="button"
              disabled={!isDirty}
              onClick={() => setDirty({})}
              className="rounded-sm border border-white/15 px-3 py-1 text-xs disabled:opacity-40"
            >
              撤销修改
            </button>
            <button
              type="button"
              disabled={!isDirty || preview.isPending}
              onClick={async () => {
                const merged = params.reduce((acc, p) => {
                  acc[p.key] = effectiveValue(p.key, p.value);
                  return acc;
                }, {} as Record<string, number>);
                const res = await preview.mutateAsync(merged);
                setPreviewMsg(`预计每小时入场: ${res.estimated_entries_per_hour.toFixed(1)} · 胜率 ${(res.estimated_win_rate * 100).toFixed(0)}% · ${res.note}`);
              }}
              className="rounded-sm border border-accent-info/40 px-3 py-1 text-xs text-accent-info disabled:opacity-40"
            >
              预览效果
            </button>
            <button
              type="button"
              disabled={!isDirty || patch.isPending}
              onClick={() => patch.mutate(dirty)}
              className="rounded-sm border border-accent-long/40 bg-accent-long/10 px-3 py-1 text-xs text-accent-long disabled:opacity-40"
            >
              {patch.isPending ? '保存中…' : '保存修改'}
            </button>
          </>
        }
      >
        {previewMsg && <div className="mb-3 rounded-sm border border-accent-info/40 bg-accent-info/10 p-2 text-xs text-accent-info">{previewMsg}</div>}
        <div className="divide-y divide-white/5">
          {params.map(p => {
            const eff = effectiveValue(p.key, p.value);
            const isChanged = eff !== p.value;
            return (
              <div key={p.key} className="grid grid-cols-12 items-center gap-3 py-3">
                <div className="col-span-3">
                  <div className="text-sm text-white">{p.key}</div>
                  <div className="text-xs text-white/40">{p.description}</div>
                </div>
                <div className="col-span-6">
                  <Slider value={eff} min={p.min} max={p.max} step={(p.max - p.min) / 100}
                          onChange={(v) => setDirty(d => ({ ...d, [p.key]: v }))} />
                </div>
                <div className="col-span-2">
                  <NumberInput value={eff} min={p.min} max={p.max} step={(p.max - p.min) / 100}
                               onChange={(v) => setDirty(d => ({ ...d, [p.key]: v }))} />
                </div>
                <div className="col-span-1 text-right text-xs text-white/40">
                  {isChanged ? <span className="text-accent-warn">●</span> : ''}{p.unit}
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
