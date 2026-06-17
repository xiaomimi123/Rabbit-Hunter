import { useEffect, useState } from 'react';
import { useV5StrategyConfig } from '../../hooks/api/useV5StrategyConfig';
import { Slider } from '../primitives/Slider';
import { NumberInput } from '../primitives/NumberInput';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Aperture } from '../primitives/Aperture';

export function V5StrategyConfigPage() {
  const { query, patch, preview } = useV5StrategyConfig();
  const [dirty, setDirty] = useState<Record<string, number>>({});
  const [previewMsg, setPreviewMsg] = useState<string | null>(null);

  useEffect(() => { setDirty({}); }, [query.data]);

  if (query.isLoading) return <LoadingSkeleton message="拉取策略参数…" />;
  const params = query.data?.params ?? [];

  const effectiveValue = (key: string, current: number) =>
    Object.prototype.hasOwnProperty.call(dirty, key) ? dirty[key] : current;

  const isDirty = Object.keys(dirty).length > 0;

  return (
    <div className="px-8 py-7 pb-16 flex flex-col gap-7 max-w-[1400px]">
      <PageHead dirtyCount={Object.keys(dirty).length} />

      <ActionBar
        dirty={isDirty}
        onUndo={() => setDirty({})}
        onPreview={async () => {
          const merged = params.reduce((acc, p) => {
            acc[p.key] = effectiveValue(p.key, p.value);
            return acc;
          }, {} as Record<string, number>);
          const res = await preview.mutateAsync(merged);
          setPreviewMsg(`预计每小时入场: ${res.estimated_entries_per_hour.toFixed(1)} · 胜率 ${(res.estimated_win_rate * 100).toFixed(0)}% · ${res.note}`);
        }}
        previewBusy={preview.isPending}
        onSave={() => patch.mutate(dirty)}
        saveBusy={patch.isPending}
      />

      {previewMsg && (
        <div className="border border-brass-soft bg-brass-soft px-4 py-3 font-mono text-[0.85rem] text-brass">
          <span className="mr-2">▌</span>{previewMsg}
        </div>
      )}

      <div>
        {params.map(p => {
          const eff = effectiveValue(p.key, p.value);
          const isChanged = eff !== p.value;
          return (
            <div key={p.key} className="grid grid-cols-12 max-[768px]:grid-cols-1 items-center gap-4 py-4 border-b border-hairline">
              <div className="col-span-3 max-[768px]:col-span-1">
                <div className="font-mono text-[0.85rem] text-ivory">{p.key}</div>
                <div className="font-body italic text-[0.78rem] text-ivory-40 leading-snug mt-0.5">{p.description}</div>
              </div>
              <div className="col-span-6 max-[768px]:col-span-1">
                <Slider value={eff} min={p.min} max={p.max} step={(p.max - p.min) / 100}
                        onChange={(v) => setDirty(d => ({ ...d, [p.key]: v }))} />
              </div>
              <div className="col-span-2 max-[768px]:col-span-1">
                <NumberInput value={eff} min={p.min} max={p.max} step={(p.max - p.min) / 100}
                             onChange={(v) => setDirty(d => ({ ...d, [p.key]: v }))} />
              </div>
              <div className="col-span-1 text-right font-mono text-[0.72rem] text-ivory-40">
                {isChanged ? <span className="text-brass mr-1">●</span> : ''}{p.unit}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PageHead({ dirtyCount }: { dirtyCount: number }) {
  return (
    <header className="grid grid-cols-[1fr_auto] items-end gap-6 pb-4 border-b border-hairline-strong">
      <div className="flex items-center gap-4">
        <Aperture size={34} rotate className="text-brass" />
        <div>
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight">Strategy Config</h1>
          <p className="font-cn text-ivory-40 text-[0.85rem] mt-1.5">参数调校 · field calibration</p>
        </div>
      </div>
      <div className="text-right font-mono text-[0.72rem] text-ivory-40 leading-relaxed">
        <div className="tracking-wider2 uppercase">Dirty Changes</div>
        <div className={`font-mono text-[1.4rem] tabular-nums ${dirtyCount > 0 ? 'text-brass' : 'text-ivory-40'}`}>
          {dirtyCount}
        </div>
      </div>
    </header>
  );
}

function ActionBar({ dirty, onUndo, onPreview, previewBusy, onSave, saveBusy }: {
  dirty: boolean;
  onUndo: () => void;
  onPreview: () => void;
  previewBusy: boolean;
  onSave: () => void;
  saveBusy: boolean;
}) {
  return (
    <div className="flex items-center gap-3 py-3 px-4 border border-hairline bg-bg-base">
      <ActionBtn variant="neutral" onClick={onUndo} disabled={!dirty}>撤销修改</ActionBtn>
      <ActionBtn variant="info" onClick={onPreview} disabled={!dirty || previewBusy}>
        {previewBusy ? '预测中…' : '预览效果'}
      </ActionBtn>
      <ActionBtn variant="primary" onClick={onSave} disabled={!dirty || saveBusy}>
        {saveBusy ? '保存中…' : '保存修改'}
      </ActionBtn>
    </div>
  );
}

function ActionBtn({ variant, onClick, disabled, children }: { variant: 'neutral' | 'info' | 'primary'; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  const cls = {
    neutral: 'border-hairline-strong text-ivory-70 hover:border-ivory hover:text-ivory',
    info:    'border-ink text-ink bg-ink-soft hover:bg-ink hover:text-ivory',
    primary: 'border-brass text-brass bg-brass-soft hover:bg-brass hover:text-bg-base',
  }[variant];
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`font-mono text-[0.78rem] tracking-wider px-4 py-1.5 border bg-transparent uppercase transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed ${cls}`}
    >
      {children}
    </button>
  );
}
