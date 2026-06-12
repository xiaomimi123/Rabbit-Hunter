import React from 'react';
import { useUIStore } from '../../services/store';
import { useSystemMode } from '../../hooks/useSystemMode';
import { Badge } from '../primitives/Badge';
import { Wifi, WifiOff, Bell } from 'lucide-react';

interface Props {
  wsConnected: boolean;
}

export function TopBar({ wsConnected }: Props) {
  const { mode } = useSystemMode();
  const provider = useUIStore(s => s.effectiveAiProvider);
  const queueLen = useUIStore(s => s.recentWsEvents.length);
  return (
    <header className="flex h-12 items-center justify-between border-b border-white/10 bg-bg-surface px-4">
      <div className="flex items-center gap-3 text-xs text-white/60">
        <span className="font-mono">v5.0.0</span>
        {mode && (
          <Badge variant={mode === 'LIVE' ? 'short' : 'info'}>
            {mode === 'LIVE' ? '🔴 LIVE' : '🟡 SHADOW'}
          </Badge>
        )}
        {provider && <Badge variant="neutral">AI: {provider}</Badge>}
      </div>
      <div className="flex items-center gap-3">
        <span className={`flex items-center gap-1 text-xs ${wsConnected ? 'text-accent-long' : 'text-accent-short'}`}>
          {wsConnected ? <Wifi size={14} /> : <WifiOff size={14} />}
          {wsConnected ? 'WS 在线' : 'WS 离线'}
        </span>
        <button type="button" className="relative text-white/50 hover:text-white">
          <Bell size={16} />
          {queueLen > 0 && (
            <span className="absolute -right-1 -top-1 rounded-full bg-accent-info px-1 text-[10px] font-mono text-white">
              {queueLen}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
