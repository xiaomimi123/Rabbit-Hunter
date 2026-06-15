import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { V5ReflectionPage } from '@/components/pages/V5ReflectionPage';

const SAMPLE = {
  status: 'success',
  data: [{
    id: 1, paper_trade_id: 7, created_at: '2026-06-15T10:30:00+00:00',
    why_entered: 'RSI 72.1 overbought + MACD bearish cross',
    what_was_expected: 'Expected 1.5-2 ATR pullback then partial TP',
    what_actually_happened: 'Price dropped to TP quickly',
    correction_idea: 'Consider 4h alignment next time',
    failure_mode_key: null,
    setup_type: 'rsi_overbought_macd_bearish_short',
    outcome_class: 'WIN', realized_r: 1.0, holding_minutes: 30,
    confidence_at_entry: 0.7,
    self_assessed_prediction_accuracy: 0.85,
    is_in_predicted_failure_mode: false,
    ai_provider: 'deepseek', ai_model: 'deepseek-chat', ai_latency_ms: 4200,
    symbol: 'HUSDT', side: 'SHORT',
    entry_price: 0.166, exit_price: 0.162, exit_reason: 'TP_HIT', pnl_pct: 1.8,
  }],
};

function wrap(qc: QueryClient) {
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter><V5ReflectionPage /></MemoryRouter>
    </QueryClientProvider>
  );
}

describe('V5ReflectionPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify(SAMPLE), { status: 200 })));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('renders 3 tab buttons', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(wrap(qc));
    expect(screen.getByText('最近复盘流')).toBeInTheDocument();
    expect(screen.getByText('失败模式')).toBeInTheDocument();
    expect(screen.getByText('仓位建议')).toBeInTheDocument();
  });

  it('shows reflection card after data loads', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(wrap(qc));
    await waitFor(() => expect(screen.getByText('HUSDT')).toBeInTheDocument());
    expect(screen.getByText(/RSI 72\.1 overbought/)).toBeInTheDocument();
    expect(screen.getByText(/Consider 4h alignment/)).toBeInTheDocument();
  });
});
