import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { V5ActivePositionsPage } from '@/components/pages/V5ActivePositionsPage';

const OPEN = {
  positions: [{
    id: 7, symbol: 'H/USDT', side: 'SHORT', status: 'OPEN',
    entry_price: 0.1665, current_price: 0.1641, stop_loss: 0.1715, take_profit: 0.1592,
    position_size_usdt: 15, leverage: 10,
    entry_time: new Date(Date.now() - 10 * 60_000).toISOString(),
    exit_time: null, exit_price: null, exit_reason: null,
    pnl_percent: 1.44, pnl_usdt: 0.22,
    entry_rsi_15m: 72, entry_macd_hist_15m: -0.0006,
    extension_count: 0, target_close_at: null, ai_reason: 'short setup',
    strategy_id: 'v5_rsi_macd',
  }],
  count: 1,
};
const EMPTY = { positions: [], count: 0 };

function wrap(qc: QueryClient) {
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter><V5ActivePositionsPage /></MemoryRouter>
    </QueryClientProvider>
  );
}

describe('V5ActivePositionsPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/api/v5/paper-positions')) return new Response(JSON.stringify(OPEN), { status: 200 });
      return new Response(JSON.stringify(EMPTY), { status: 200 });
    }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('renders one ActivePositionCard', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(wrap(qc));
    await waitFor(() => expect(screen.getByText('H/USDT')).toBeInTheDocument());
  });

  it('立即平 opens confirm modal', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(wrap(qc));
    await waitFor(() => screen.getByText('H/USDT'));
    await user.click(screen.getByRole('button', { name: /立即平/ }));
    expect(screen.getByText(/确认立即平仓/)).toBeInTheDocument();
  });
});
