import { useUIStore } from '../../services/store';
import { useSystemMode } from '../../hooks/useSystemMode';

interface Props {
  wsConnected: boolean;
}

export function TopBar({ wsConnected }: Props) {
  const { mode } = useSystemMode();
  const provider = useUIStore(s => s.effectiveAiProvider);
  const queueLen = useUIStore(s => s.recentWsEvents.length);

  const modeBadgeClass = mode === 'LIVE'
    ? 'border-alarm/40 text-alarm bg-alarm/10'
    : 'border-brass-soft text-brass bg-brass-soft';

  return (
    <header className="flex items-center justify-between h-14 border-b border-hairline bg-bg-base px-8 sticky top-0 z-10">
      <div className="flex items-center gap-[18px]">
        <span className="font-mono text-[0.7rem] tracking-wider text-ivory-70">v6.0.0</span>
        {mode && (
          <span className={`inline-flex items-center gap-1.5 font-mono text-[0.7rem] tracking-wide px-2.5 py-0.5 border ${modeBadgeClass}`}>
            {mode === 'LIVE' ? '⬤' : '◐'} {mode}
          </span>
        )}
        {provider && (
          <span className="inline-flex items-center gap-1.5 font-mono text-[0.7rem] tracking-wide px-2.5 py-0.5 border border-ink-soft text-ink bg-ink-soft">
            AI · {provider}
          </span>
        )}
      </div>
      <div className="flex items-center gap-[18px]">
        <span className="inline-flex gap-2 items-center font-mono text-[0.72rem] text-ivory-70">
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              wsConnected
                ? 'bg-sage shadow-[0_0_6px_rgba(107,133,104,0.6)]'
                : 'bg-oxblood'
            }`}
          />
          WS · {wsConnected ? '在线' : '离线'}
        </span>
        {queueLen > 0 && (
          <span className="font-mono text-[0.7rem] tracking-wider text-brass">
            ↗ {queueLen} events
          </span>
        )}
      </div>
    </header>
  );
}
