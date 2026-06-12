import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { V5SignalsPage } from '@/components/pages/V5SignalsPage';

function wrap(qc: QueryClient) {
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <V5SignalsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('V5SignalsPage', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('renders empty state when 0 signals', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ signals: [], count: 0 }), { status: 200 }));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(wrap(qc));
    await waitFor(() => expect(screen.getByText(/等待行情/)).toBeInTheDocument());
  });

  it('shows a card per signal', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({
        signals: [{
          id: 1, symbol: 'H/USDT', created_at: '2026-06-12T09:48:00+00:00',
          delta_15m_pct: 0.0342, volume_24h_usdt: 5e7,
          rsi_15m: 72.1, rsi_4h: 68, macd_15m: 0, macd_signal_15m: 0,
          macd_hist_15m: -0.0012, macd_hist_prev_15m: 0.0008, macd_hist_4h: 0.003,
          atr_15m: 0.0015, current_price: 0.166,
          should_trade: true, side: 'SHORT',
          reasoning: 'RSI 超买 + 死叉拐点', block_reason: null,
          ai_confidence: 0.7, ai_sl_multiplier: 2.0, ai_tp_multiplier: 2.8,
          ai_size_multiplier: 1.0, ai_reasoning: 'good',
          entry_price: 0.166, sl_price: 0.169, tp_price: 0.162,
          size_usdt: 14.8, expected_rr: 1.4,
          executed: false, position_id: null,
        }], count: 1,
      }), { status: 200 }));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(wrap(qc));
    await waitFor(() => expect(screen.getByText('H/USDT')).toBeInTheDocument());
    expect(screen.getByText(/SHORT/)).toBeInTheDocument();
  });
});
