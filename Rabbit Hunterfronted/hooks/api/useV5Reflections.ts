import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { ReflectionsResponse, FailureTaxonomyResponse } from '../../types';

export function useV5Reflections(limit = 20) {
  return useQuery<ReflectionsResponse>({
    queryKey: ['v5', 'reflections', limit],
    queryFn: () => apiGet<ReflectionsResponse>(`/api/v5/reflections?limit=${limit}`),
    refetchInterval: 30_000,
  });
}

export function useV5FailureTaxonomy() {
  return useQuery<FailureTaxonomyResponse>({
    queryKey: ['v5', 'failure-taxonomy'],
    queryFn: () => apiGet<FailureTaxonomyResponse>('/api/v5/failure-taxonomy'),
    refetchInterval: 60_000,
  });
}
