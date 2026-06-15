import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { ReflectionsResponse } from '../../types';

export function useV5Reflections(limit = 20) {
  return useQuery<ReflectionsResponse>({
    queryKey: ['v5', 'reflections', limit],
    queryFn: () => apiGet<ReflectionsResponse>(`/api/v5/reflections?limit=${limit}`),
    refetchInterval: 30_000,
  });
}
