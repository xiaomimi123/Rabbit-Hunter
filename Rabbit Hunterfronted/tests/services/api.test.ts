import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { apiGet, apiPost, apiPatch, ApiError } from '@/services/api';

describe('api client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('apiGet returns parsed JSON on 200', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    const out = await apiGet<{ ok: boolean }>('/api/v5/signals');
    expect(out).toEqual({ ok: true });
  });

  it('apiGet throws ApiError on 4xx with detail', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'nope' }), { status: 404 }),
    );
    await expect(apiGet('/api/v5/x')).rejects.toMatchObject({
      status: 404,
      detail: 'nope',
    });
  });

  it('apiPost sends JSON body and parses response', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ id: 42 }), { status: 200 }),
    );
    const out = await apiPost<{ id: number }>('/api/v5/x', { side: 'SHORT' });
    expect(out.id).toBe(42);
    const call = (fetch as any).mock.calls[0];
    expect(call[1].method).toBe('POST');
    expect(JSON.parse(call[1].body)).toEqual({ side: 'SHORT' });
    expect(call[1].headers['Content-Type']).toBe('application/json');
  });

  it('apiPatch uses PATCH method', async () => {
    (fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({}), { status: 200 }),
    );
    await apiPatch('/api/v5/strategy-config', { v5_rsi_overbought: 68 });
    expect((fetch as any).mock.calls[0][1].method).toBe('PATCH');
  });

  it('attaches Authorization header when API_BEARER_TOKEN is set', async () => {
    (fetch as any).mockResolvedValueOnce(new Response('{}', { status: 200 }));
    (window as any).__API_BEARER_TOKEN__ = 'tok123';
    await apiGet('/api/v5/x');
    expect((fetch as any).mock.calls[0][1].headers.Authorization).toBe('Bearer tok123');
    delete (window as any).__API_BEARER_TOKEN__;
  });

  it('5xx without body raises with generic detail', async () => {
    (fetch as any).mockResolvedValueOnce(new Response('', { status: 503 }));
    await expect(apiGet('/api/v5/x')).rejects.toMatchObject({
      status: 503,
    });
  });
});
