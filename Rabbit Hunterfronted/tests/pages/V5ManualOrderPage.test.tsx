import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { V5ManualOrderPage } from '@/components/pages/V5ManualOrderPage';

const PREVIEW = {
  symbol: 'H/USDT', side: 'SHORT', current_price: 0.166,
  indicators: { rsi_15m: 72, macd_hist_15m: -0.001, macd_hist_prev_15m: 0.0008,
                atr_15m: 0.0015, rsi_4h: 68, macd_hist_4h: 0.003 },
  decision: { should_trade: true, side: 'SHORT', reasoning: 'RSI super', block_reason: null },
  risk_plan: { entry_price: 0.166, sl_price: 0.169, tp_price: 0.162, size_usdt: 15, leverage: 10, expected_rr: 1.5 },
  ai_result: { execute: true, sl_multiplier: 1.0, tp_multiplier: 1.0, size_multiplier: 1.0, confidence: 0.7, reasoning: 'ok' },
  rag_cases: [], rag_summary: null,
};

const SETTINGS_SHADOW = {
  exchange: 'okx', openai_api_key_masked: '', openai_assistant_id: null,
  openai_vector_store_id: null, deepseek_api_key_masked: '',
  deepseek_enabled: true, active_ai_provider: 'deepseek', active_chat_model: 'deepseek-chat',
  system_mode: 'SHADOW', enable_auto_trading: false,
  ai_fail_open: false, sl_tp_fail_open: false,
};

describe('V5ManualOrderPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/api/v5/settings')) return new Response(JSON.stringify(SETTINGS_SHADOW), { status: 200 });
      if (url.includes('preview')) return new Response(JSON.stringify(PREVIEW), { status: 200 });
      return new Response(JSON.stringify({}), { status: 200 });
    }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('flows Step1 → Step2 on preview submit', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { mutations: { retry: false }, queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/v5/manual']}><V5ManualOrderPage /></MemoryRouter>
      </QueryClientProvider>
    );
    expect(screen.getByText(/Step 1/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /模拟评估/ }));
    await waitFor(() => expect(screen.getByText(/Step 2/)).toBeInTheDocument());
  });
});
