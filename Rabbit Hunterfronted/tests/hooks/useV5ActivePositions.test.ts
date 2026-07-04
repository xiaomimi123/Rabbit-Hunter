import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useV5ActivePositions } from '@/hooks/api/useV5ActivePositions';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    qc,
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  };
}

const mkPos = (id: number, kind: 'LIVE' | 'PAPER') =>
  ({ id, symbol: `SYM${id}/USDT`, side: 'LONG', status: 'OPEN', _kind: kind } as any);

describe('useV5ActivePositions', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('merges live + paper when both succeed', async () => {
    (fetch as any)
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkPos(1, 'LIVE')] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkPos(2, 'PAPER'), mkPos(3, 'PAPER')] }), { status: 200 }));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5ActivePositions(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(result.current.data!.total).toBe(3);
    expect(result.current.data!.live).toHaveLength(1);
    expect(result.current.data!.paper).toHaveLength(2);
    expect(result.current.data!.live_error).toBeUndefined();
    expect(result.current.data!.paper_error).toBeUndefined();
  });

  it('degrades gracefully when live fails, paper succeeds', async () => {
    (fetch as any)
      .mockRejectedValueOnce(new Error('503 Service Unavailable'))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkPos(1, 'PAPER')] }), { status: 200 }));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5ActivePositions(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(result.current.data!.live).toEqual([]);
    expect(result.current.data!.paper).toHaveLength(1);
    expect(result.current.data!.total).toBe(1);
    expect(result.current.data!.live_error).toContain('503');
    expect(result.current.data!.paper_error).toBeUndefined();
    expect(result.current.isError).toBe(false);
  });

  it('degrades gracefully when paper fails, live succeeds', async () => {
    (fetch as any)
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkPos(1, 'LIVE')] }), { status: 200 }))
      .mockRejectedValueOnce(new Error('timeout'));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5ActivePositions(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(result.current.data!.live).toHaveLength(1);
    expect(result.current.data!.paper).toEqual([]);
    expect(result.current.data!.total).toBe(1);
    expect(result.current.data!.live_error).toBeUndefined();
    expect(result.current.data!.paper_error).toContain('timeout');
  });
});
