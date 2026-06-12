import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { KlinesResponse, Interval } from '../../types';

function encodeSymbol(sym: string): string {
  return sym;
}

export function useV5Klines(symbol: string | null, interval: Interval = '15m', limit = 200) {
  return useQuery<KlinesResponse>({
    queryKey: ['v5', 'klines', symbol, interval, limit],
    queryFn: () => apiGet<KlinesResponse>(
      `/api/v5/klines/${encodeSymbol(symbol!)}?interval=${interval}&limit=${limit}`),
    enabled: !!symbol,
    refetchInterval: 15_000,
  });
}
