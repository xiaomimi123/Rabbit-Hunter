import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { HeaderBar } from './HeaderBar';
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
    <div className="min-h-screen bg-bg-base text-ivory">
      <div className="grid min-h-screen lg:grid-cols-[240px_1fr]">
        <Sidebar />
        <main className="min-w-0">
          <HeaderBar wsConnected={status.connected} />
          <div className="p-6">
            <ErrorBoundary>
              <Outlet />
            </ErrorBoundary>
          </div>
        </main>
      </div>
    </div>
  );
}
