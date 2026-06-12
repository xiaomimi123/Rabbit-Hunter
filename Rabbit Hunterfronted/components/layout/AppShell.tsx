import React from 'react';
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
    <div className="flex h-screen bg-bg-base text-white">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <TopBar wsConnected={status.connected} />
        <main className="flex-1 overflow-y-auto p-6">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
