import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPatch } from '../../services/api';
import type {
  ReflectionsResponse, FailureTaxonomyResponse,
  SizingRecommendationsResponse, SetupPerformanceResponse, CalibrationResponse,
} from '../../types';

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

export function useV5SizingRecommendations() {
  return useQuery<SizingRecommendationsResponse>({
    queryKey: ['v5', 'sizing-recommendations'],
    queryFn: () => apiGet<SizingRecommendationsResponse>('/api/v5/sizing-recommendations?status=pending'),
    refetchInterval: 60_000,
  });
}

export function useV5DecideSizing() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, modified_value, note }: {
      id: number; decision: 'approve' | 'reject' | 'modify';
      modified_value?: number; note?: string;
    }) => apiPatch(`/api/v5/sizing-recommendations/${id}`,
                    { decision, modified_value, note }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['v5', 'sizing-recommendations'] }),
  });
}

export function useV5SetupPerformance(days = 7) {
  return useQuery<SetupPerformanceResponse>({
    queryKey: ['v5', 'setup-performance', days],
    queryFn: () => apiGet<SetupPerformanceResponse>(`/api/v5/setup-performance?days=${days}`),
    refetchInterval: 120_000,
  });
}

export function useV5Calibration() {
  return useQuery<CalibrationResponse>({
    queryKey: ['v5', 'confidence-calibration'],
    queryFn: () => apiGet<CalibrationResponse>('/api/v5/confidence-calibration'),
    refetchInterval: 60_000,
  });
}
