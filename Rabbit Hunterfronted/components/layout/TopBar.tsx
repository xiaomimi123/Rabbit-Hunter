import { Wifi, WifiOff, Activity, Bell } from 'lucide-react';
import { useUIStore } from '../../services/store';
import { useSystemMode } from '../../hooks/useSystemMode';
import { cn } from '../primitives-v3/cn';

interface Props {
  wsConnected: boolean;
}

export function TopBar({ wsConnected }: Props) {
  const { mode } = useSystemMode();
  const provider = useUIStore(s => s.effectiveAiProvider);
  const queueLen = useUIStore(s => s.recentWsEvents.length);

  return (
    <header className="flex items-center justify-between h-14 border-b border-zinc-800 bg-zinc-950/95 px-6 sticky top-0 z-10 backdrop-blur">
      <div className="flex items-center gap-3 text-sm">
        <span className="text-xs text-zinc-500">v6.0.0</span>
        {mode && (
          <span
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs',
              mode === 'LIVE'
                ? 'border-rose-500/30 bg-rose-500/10 text-rose-200'
                : 'border-amber-500/30 bg-amber-500/10 text-amber-200',
            )}
          >
            <Activity className="h-3 w-3" />
            {mode}
          </span>
        )}
        {provider && (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs text-indigo-200">
            AI · {provider}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span
          className={cn(
            'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs',
            wsConnected
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
              : 'border-rose-500/30 bg-rose-500/10 text-rose-200',
          )}
        >
          {wsConnected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
          WS · {wsConnected ? '在线' : '离线'}
        </span>
        {queueLen > 0 && (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-300">
            <Bell className="h-3 w-3" />
            {queueLen}
          </span>
        )}
      </div>
    </header>
  );
}
