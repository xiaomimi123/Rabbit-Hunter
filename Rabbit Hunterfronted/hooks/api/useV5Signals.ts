import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { V5SignalsResponse, Side } from '../../types';

interface Filter {
  side?: Side | null;
  showExecutedOnly?: boolean;
  blockReason?: string | null;
  since?: string | null;
}

export function useV5Signals(limit = 50, filter: Filter = {}) {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  if (filter.side) params.set('side', filter.side);
  if (filter.showExecutedOnly) params.set('executed_only', 'true');
  if (filter.blockReason) params.set('block_reason', filter.blockReason);
  if (filter.since) params.set('since', filter.since);
  const qs = params.toString();
  return useQuery<V5SignalsResponse>({
    queryKey: ['v5', 'signals', filter, limit],
    queryFn: () => apiGet<V5SignalsResponse>(`/api/v5/signals?${qs}`),
    refetchInterval: 10_000,
    staleTime: 5_000,
  });
}
