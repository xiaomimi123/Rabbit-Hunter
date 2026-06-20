import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { ErrorBoundary } from '../primitives/ErrorBoundary';
import { useV5WebSocket } from '../../hooks/useV5WebSocket';

function wsUrl(): string {
  if (typeof window === 'undefined') return 'ws://localhost/ws/v5';
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/v5`;
}

export function AppShell() {
  const status = useV5WebSocket(wsUrl());
  return (
    <div className="grid grid-cols-[240px_1fr] min-h-screen bg-zinc-950 text-zinc-100">
      <Sidebar />
      <div className="flex flex-col min-w-0">
        <TopBar wsConnected={status.connected} />
        <main className="flex-1 overflow-y-auto">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
