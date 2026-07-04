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

const nowIso = () => new Date().toISOString();

const mkClosed = (id: number, pnlUsdt: number, pnlPct: number) => ({
  id,
  symbol: `SYM${id}/USDT`,
  side: 'LONG',
  status: 'CLOSED',
  entry_price: 100,
  entry_time: nowIso(),
  exit_price: 105,
  exit_time: nowIso(),
  pnl_usdt: pnlUsdt,
  pnl_pct: pnlPct,
  extension_count: 0,
} as any);

const mkOpen = (id: number) => ({
  id,
  symbol: `SYM${id}/USDT`,
  side: 'LONG',
  status: 'OPEN',
  extension_count: 0,
} as any);

describe('useV5Dashboard', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('merges paper + live for 24h stats and active_count', async () => {
    (fetch as any)
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkClosed(1, 5, 0.02), mkClosed(2, 3, 0.01)] }),
        { status: 200 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkOpen(10)] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkClosed(3, -2, -0.01), mkClosed(4, 4, 0.03)] }),
        { status: 200 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkOpen(11), mkOpen(12)] }), { status: 200 }));

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5Dashboard(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    const d = result.current.data!;
    expect(d.closed_24h.length).toBe(4);
    expect(d.pnl_total_usdt).toBe(10);
    expect(d.active_count).toBe(3);
    expect(d.win_rate_24h).toBeCloseTo(3 / 4);
    expect(d.errors).toBeUndefined();
  });

  it('degrades gracefully when live endpoints fail', async () => {
    (fetch as any)
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkClosed(1, 5, 0.02)] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkOpen(10)] }), { status: 200 }))
      .mockRejectedValueOnce(new Error('503 live history'))
      .mockRejectedValueOnce(new Error('503 live active'));

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5Dashboard(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    const d = result.current.data!;
    expect(d.closed_24h.length).toBe(1);
    expect(d.pnl_total_usdt).toBe(5);
    expect(d.active_count).toBe(1);
    expect(d.errors?.live_history).toContain('503');
    expect(d.errors?.live_active).toContain('503');
    expect(d.errors?.paper_history).toBeUndefined();
    expect(result.current.isError).toBe(false);
  });

  it('degrades gracefully when paper endpoints fail', async () => {
    (fetch as any)
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [] }), { status: 200 }))
      .mockRejectedValueOnce(new Error('timeout paper history'))
      .mockRejectedValueOnce(new Error('timeout paper active'))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkClosed(1, 7, 0.05)] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkOpen(20), mkOpen(21)] }), { status: 200 }));

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5Dashboard(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    const d = result.current.data!;
    expect(d.closed_24h.length).toBe(1);
    expect(d.pnl_total_usdt).toBe(7);
    expect(d.active_count).toBe(2);
    expect(d.errors?.paper_history).toContain('timeout');
    expect(d.errors?.paper_active).toContain('timeout');
    expect(d.errors?.live_history).toBeUndefined();
  });
});
