import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useV5Dashboard } from '@/hooks/api/useV5Dashboard';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    qc,
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  };
}

describe('useV5Dashboard', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('fetches /api/v5/dashboard/summary?hours=24', async () => {
    (fetch as any).mockResolvedValueOnce(new Response(JSON.stringify({
      signals_24h: 5, signals_passed_and: 2, signals_executed: 1,
      signals_block_counts: { NONE: 2, OTHER: 3 },
      win_rate_24h: 0.75, pnl_total_usdt: 11, pnl_total_pct: 0.05,
      avg_holding_minutes: 30, active_count: 3, closed_24h: [], errors: null,
    }), { status: 200 }));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5Dashboard(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect((fetch as any).mock.calls[0][0]).toContain('/api/v5/dashboard/summary?hours=24');
    expect(result.current.data!.pnl_total_usdt).toBe(11);
    expect(result.current.data!.active_count).toBe(3);
  });

  it('passes through errors object from backend', async () => {
    (fetch as any).mockResolvedValueOnce(new Response(JSON.stringify({
      signals_24h: 0, signals_passed_and: 0, signals_executed: 0,
      signals_block_counts: {},
      win_rate_24h: 0, pnl_total_usdt: 0, pnl_total_pct: 0,
      avg_holding_minutes: 0, active_count: 0, closed_24h: [],
      errors: { live_history: 'sqlite: no such table' },
    }), { status: 200 }));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5Dashboard(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(result.current.data!.errors?.live_history).toContain('sqlite');
  });

  it('propagates API 5xx as query error', async () => {
    (fetch as any).mockResolvedValueOnce(new Response('server broken', { status: 500 }));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5Dashboard(), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
