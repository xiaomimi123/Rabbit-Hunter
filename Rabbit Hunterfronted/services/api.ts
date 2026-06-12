// V5 fetch wrapper. Adds Authorization header if window.__API_BEARER_TOKEN__ set.
// Throws ApiError on 4xx/5xx so React Query treats them as errors.

export class ApiError extends Error {
  status: number;
  detail: string;
  url: string;
  constructor(status: number, detail: string, url: string) {
    super(`[${status}] ${detail} (${url})`);
    this.status = status;
    this.detail = detail;
    this.url = url;
  }
}

const BASE = '';

function buildHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...extra };
  const token = (typeof window !== 'undefined' && (window as any).__API_BEARER_TOKEN__) || null;
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function parseOrThrow<T>(res: Response, url: string): Promise<T> {
  if (res.ok) {
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }
  let detail = res.statusText || `HTTP ${res.status}`;
  try {
    const body = await res.json();
    if (body && typeof body.detail === 'string') detail = body.detail;
  } catch {
    // body not JSON — keep statusText
  }
  throw new ApiError(res.status, detail, url);
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE}${path}`;
  const res = await fetch(url, { method: 'GET', headers: buildHeaders(), ...init });
  return parseOrThrow<T>(res, url);
}

export async function apiPost<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
  const url = `${BASE}${path}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: buildHeaders(),
    body: body == null ? undefined : JSON.stringify(body),
    ...init,
  });
  return parseOrThrow<T>(res, url);
}

export async function apiPatch<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
  const url = `${BASE}${path}`;
  const res = await fetch(url, {
    method: 'PATCH',
    headers: buildHeaders(),
    body: body == null ? undefined : JSON.stringify(body),
    ...init,
  });
  return parseOrThrow<T>(res, url);
}

export async function apiDelete<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE}${path}`;
  const res = await fetch(url, { method: 'DELETE', headers: buildHeaders(), ...init });
  return parseOrThrow<T>(res, url);
}
