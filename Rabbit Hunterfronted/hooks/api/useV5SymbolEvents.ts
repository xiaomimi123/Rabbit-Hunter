import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { SymbolEventsResponse } from '../../types';

function encodeSymbol(sym: string): string {
  return sym;
}

export function useV5SymbolEvents(symbol: string | null, limit = 50) {
  return useQuery<SymbolEventsResponse>({
    queryKey: ['v5', 'events', symbol, limit],
    queryFn: () => apiGet<SymbolEventsResponse>(
      `/api/v5/events/${encodeSymbol(symbol!)}?limit=${limit}`),
    enabled: !!symbol,
    refetchInterval: 15_000,
  });
}
