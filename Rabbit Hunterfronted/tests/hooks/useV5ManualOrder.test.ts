import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useV5ManualOrder } from '@/hooks/api/useV5ManualOrder';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useV5ManualOrder', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('preview hits /preview with body and returns response', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({
        symbol: 'H/USDT', side: 'SHORT', current_price: 0.166,
        indicators: {}, decision: { should_trade: true, side: 'SHORT', reasoning: '', block_reason: null },
        risk_plan: {}, ai_result: { execute: true, sl_multiplier: 1, tp_multiplier: 1,
          size_multiplier: 1, confidence: 0.7, reasoning: 'ok' },
        rag_cases: [], rag_summary: null,
      }), { status: 200 })
    );
    const { result } = renderHook(() => useV5ManualOrder(), { wrapper: makeWrapper() });
    let preview: any;
    await act(async () => {
      preview = await result.current.preview.mutateAsync({ symbol: 'H/USDT', side: 'SHORT', size_usdt: 15 });
    });
    expect(preview.symbol).toBe('H/USDT');
    expect((fetch as any).mock.calls[0][0]).toContain('/manual-order/preview');
    expect((fetch as any).mock.calls[0][1].method).toBe('POST');
  });

  it('execute hits /execute and returns position_id', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({
        position_id: 42, symbol: 'H/USDT', side: 'SHORT',
        entry_price: 0.166, sl_price: 0.169, tp_price: 0.162,
        size_usdt: 15, strategy_id: 'v5_manual',
      }), { status: 200 })
    );
    const { result } = renderHook(() => useV5ManualOrder(), { wrapper: makeWrapper() });
    let out: any;
    await act(async () => {
      out = await result.current.execute.mutateAsync({
        symbol: 'H/USDT', side: 'SHORT', size_usdt: 15,
        sl_multiplier: 1, tp_multiplier: 1, size_multiplier: 1,
      });
    });
    expect(out.position_id).toBe(42);
    expect((fetch as any).mock.calls[0][0]).toContain('/manual-order/execute');
  });
});
