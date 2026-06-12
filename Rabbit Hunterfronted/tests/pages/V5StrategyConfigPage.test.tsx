import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { V5StrategyConfigPage } from '@/components/pages/V5StrategyConfigPage';

const FAKE_CONFIG = {
  params: [
    { key: 'v5_rsi_overbought', value: 70, default: 70, min: 60, max: 80, unit: '', description: '开空 RSI' },
    { key: 'v5_rsi_oversold', value: 30, default: 30, min: 20, max: 40, unit: '', description: '开多 RSI' },
  ],
};

describe('V5StrategyConfigPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(FAKE_CONFIG), { status: 200 })));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('renders one row per param', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter><V5StrategyConfigPage /></MemoryRouter>
      </QueryClientProvider>
    );
    await waitFor(() => expect(screen.getByText('v5_rsi_overbought')).toBeInTheDocument());
    expect(screen.getByText('v5_rsi_oversold')).toBeInTheDocument();
  });
});
