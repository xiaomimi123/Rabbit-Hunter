interface Step {
  name: string;
  count: number;
  hint?: string;
}

interface Props {
  steps: Step[];
  onLayerClick?: (step: Step) => void;
}

const TONE = ['bg-ink', 'bg-brass-soft border-r border-brass', 'bg-sage-soft border-r border-sage'];

export function SignalFunnel({ steps, onLayerClick }: Props) {
  const maxCount = steps.reduce((a, b) => Math.max(a, b.count), 0) || 1;
  return (
    <div className="flex flex-col gap-2">
      {steps.map((s, i) => {
        const pct = (s.count / maxCount) * 100;
        return (
          <button
            key={s.name}
            type="button"
            onClick={() => onLayerClick?.(s)}
            className="grid grid-cols-[180px_1fr_70px] items-center gap-3.5 py-1.5 px-1 border-b border-hairline text-left hover:bg-brass/[0.04] hover:border-brass transition-colors"
          >
            <span className="font-cn text-[0.85rem] text-ivory-70">{s.name}</span>
            <span className="h-3 bg-white/[0.04] relative">
              <span className={`absolute inset-y-0 left-0 ${TONE[i] || 'bg-ink'}`} style={{ width: `${Math.max(2, pct)}%` }} />
            </span>
            <span className="font-mono tabular-nums text-right text-ivory">{s.count}</span>
          </button>
        );
      })}
    </div>
  );
}
