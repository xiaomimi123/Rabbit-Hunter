import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell } from '@/components/layout/AppShell';

describe('AppShell', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({
        exchange: 'okx', openai_api_key_masked: '', openai_assistant_id: null,
        openai_vector_store_id: null, deepseek_api_key_masked: '',
        deepseek_enabled: true, active_ai_provider: 'deepseek', active_chat_model: 'deepseek-chat',
        system_mode: 'SHADOW', enable_auto_trading: false,
        ai_fail_open: false, sl_tp_fail_open: false,
      }), { status: 200 })));
    // Stub WebSocket so AppShell's useV5WebSocket doesn't actually open one
    (globalThis as any).WebSocket = class {
      onopen: any; onmessage: any; onclose: any; onerror: any;
      send() {}
      close() {}
      constructor() { setTimeout(() => this.onopen && this.onopen(), 0); }
    };
  });
  afterEach(() => vi.unstubAllGlobals());

  it('renders sidebar groups + topbar', () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/v5/signals']}>
          <Routes>
            <Route path="/v5" element={<AppShell />}>
              <Route path="signals" element={<div>signals-page</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    expect(screen.getByText(/猎兔者/)).toBeInTheDocument();
    expect(screen.getByText('交易')).toBeInTheDocument();
    expect(screen.getByText('智能')).toBeInTheDocument();
    expect(screen.getByText('系统')).toBeInTheDocument();
    expect(screen.getByText('signals-page')).toBeInTheDocument();
  });
});
