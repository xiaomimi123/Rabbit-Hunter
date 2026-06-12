import React from 'react';

interface Step {
  name: string;
  count: number;
  hint?: string;
}

interface Props {
  steps: Step[];
  onLayerClick?: (step: Step) => void;
}

export function SignalFunnel({ steps, onLayerClick }: Props) {
  const maxCount = steps.reduce((a, b) => Math.max(a, b.count), 0) || 1;
  return (
    <div className="space-y-1">
      {steps.map((s) => {
        const pct = (s.count / maxCount) * 100;
        return (
          <button
            key={s.name}
            type="button"
            onClick={() => onLayerClick?.(s)}
            className="flex w-full items-center gap-3 rounded-sm px-2 py-1 text-left hover:bg-white/5"
          >
            <div className="w-32 text-xs text-white/80">{s.name}</div>
            <div className="flex-1">
              <div className="h-3 rounded-sm bg-white/5">
                <div
                  className="h-full rounded-sm bg-accent-info"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
            <div className="w-14 text-right font-mono text-sm text-white">{s.count}</div>
          </button>
        );
      })}
    </div>
  );
}
