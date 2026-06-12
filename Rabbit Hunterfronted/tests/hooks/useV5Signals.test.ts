import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useV5Signals } from '@/hooks/api/useV5Signals';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { qc, wrapper: ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children) };
}

describe('useV5Signals', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('fetches /api/v5/signals?limit=50 by default', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ status: 'success', data: [] }), { status: 200 })
    );
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5Signals(50), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect((fetch as any).mock.calls[0][0]).toContain('/api/v5/signals?limit=50');
  });

  it('passes side filter through', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ status: 'success', data: [] }), { status: 200 })
    );
    const { wrapper } = makeWrapper();
    renderHook(() => useV5Signals(50, { side: 'SHORT' }), { wrapper });
    await waitFor(() => expect((fetch as any).mock.calls.length).toBeGreaterThan(0));
    expect((fetch as any).mock.calls[0][0]).toContain('side=SHORT');
  });
});
