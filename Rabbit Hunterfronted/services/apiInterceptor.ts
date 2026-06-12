import type { ApiError } from './api';

type Listener = (err: ApiError) => void;
const listeners: Listener[] = [];

export function onApiError(fn: Listener): () => void {
  listeners.push(fn);
  return () => {
    const i = listeners.indexOf(fn);
    if (i >= 0) listeners.splice(i, 1);
  };
}

export function reportApiError(err: ApiError): void {
  for (const fn of listeners) {
    try { fn(err); } catch { /* swallow */ }
  }
}

export function withInterceptor<T>(p: Promise<T>): Promise<T> {
  return p.catch((err) => {
    if (err && typeof err === 'object' && 'status' in err) {
      reportApiError(err as ApiError);
    }
    throw err;
  });
}
