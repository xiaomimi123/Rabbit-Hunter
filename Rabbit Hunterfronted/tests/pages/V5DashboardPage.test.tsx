import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { V5DashboardPage } from '@/components/pages/V5DashboardPage';

const FAKE_SIGNALS = { status: 'success', data: [] };
const FAKE_POS = { status: 'success', data: [] };

describe('V5DashboardPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('signals')) return new Response(JSON.stringify(FAKE_SIGNALS), { status: 200 });
      return new Response(JSON.stringify(FAKE_POS), { status: 200 });
    }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('renders KPI cards with zero values on empty data', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter><V5DashboardPage /></MemoryRouter>
      </QueryClientProvider>
    );
    await waitFor(() => expect(screen.getByText(/胜率/)).toBeInTheDocument());
    expect(screen.getByText('累计盈亏')).toBeInTheDocument();
    expect(screen.getByText('平均持仓')).toBeInTheDocument();
    expect(screen.getByText('活仓数')).toBeInTheDocument();
  });
});
