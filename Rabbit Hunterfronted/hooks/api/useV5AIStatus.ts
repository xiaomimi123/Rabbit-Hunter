import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { AIStatusResponse, AIDecisionsResponse } from '../../types';

export function useV5AIStatus() {
  return useQuery<AIStatusResponse>({
    queryKey: ['v5', 'ai'],
    queryFn: () => apiGet<AIStatusResponse>('/api/v5/ai/status'),
    refetchInterval: 60_000,
  });
}

export function useV5AIDecisions(limit = 20) {
  return useQuery<AIDecisionsResponse>({
    queryKey: ['v5', 'ai', 'decisions', limit],
    queryFn: () => apiGet<AIDecisionsResponse>(`/api/v5/ai/decisions?limit=${limit}`),
    refetchInterval: 30_000,
  });
}
