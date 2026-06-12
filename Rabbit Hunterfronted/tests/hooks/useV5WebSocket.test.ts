import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { Server, WebSocket as MockWS } from 'mock-socket';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useV5WebSocket } from '@/hooks/useV5WebSocket';
import { useUIStore } from '@/services/store';

const WS_URL = 'ws://localhost/ws/v5';

function wrapper(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

describe('useV5WebSocket', () => {
  let server: Server;
  let originalWS: typeof WebSocket;

  beforeEach(() => {
    originalWS = globalThis.WebSocket;
    (globalThis as any).WebSocket = MockWS;
    server = new Server(WS_URL);
    useUIStore.setState({ recentWsEvents: [] });
  });

  afterEach(() => {
    server.stop();
    (globalThis as any).WebSocket = originalWS;
  });

  it('connects and reports healthy after open', async () => {
    const qc = new QueryClient();
    const { result } = renderHook(() => useV5WebSocket(WS_URL), { wrapper: wrapper(qc) });
    await waitFor(() => expect(result.current.connected).toBe(true), { timeout: 1000 });
  });

  it('pushes received event into UI store', async () => {
    const qc = new QueryClient();
    server.on('connection', (sock) => {
      sock.send(JSON.stringify({
        type: 'position_opened', symbol: 'H/USDT', side: 'SHORT',
        entry: 0.166, sl: 0.169, tp: 0.162, size_usdt: 15,
        position_id: 7, strategy_id: 'v5_rsi_macd', mode: 'SHADOW',
      }));
    });
    renderHook(() => useV5WebSocket(WS_URL), { wrapper: wrapper(qc) });
    await waitFor(() =>
      expect(useUIStore.getState().recentWsEvents.length).toBeGreaterThan(0)
    , { timeout: 1000 });
    expect(useUIStore.getState().recentWsEvents[0].type).toBe('position_opened');
  });

  it('invalidates positions query on position_opened', async () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    server.on('connection', (sock) => {
      sock.send(JSON.stringify({
        type: 'position_opened', symbol: 'H/USDT', side: 'SHORT',
        entry: 0.166, sl: 0.169, tp: 0.162, size_usdt: 15,
        position_id: 7, strategy_id: 'v5_rsi_macd', mode: 'SHADOW',
      }));
    });
    renderHook(() => useV5WebSocket(WS_URL), { wrapper: wrapper(qc) });
    await waitFor(() => expect(spy).toHaveBeenCalled(), { timeout: 1000 });
    const calls = spy.mock.calls.map(c => (c[0] as any).queryKey?.[1]);
    expect(calls).toContain('active');
  });
});
