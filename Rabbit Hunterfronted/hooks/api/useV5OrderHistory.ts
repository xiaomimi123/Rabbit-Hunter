import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { V5PositionsResponse, V5Position } from '../../types';

export function useV5OrderHistory(limit = 200) {
  return useQuery<V5Position[]>({
    queryKey: ['v5', 'history', limit],
    queryFn: async () => {
      const [live, paper] = await Promise.all([
        apiGet<V5PositionsResponse>(`/api/v5/positions?status=CLOSED&limit=${limit}`),
        apiGet<V5PositionsResponse>(`/api/v5/paper-positions?status=CLOSED&limit=${limit}`),
      ]);
      const merged = [...live.positions, ...paper.positions];
      merged.sort((a, b) => (b.exit_time || '').localeCompare(a.exit_time || ''));
      return merged.slice(0, limit);
    },
    refetchInterval: 30_000,
  });
}
