import { useQuery } from '@tanstack/react-query';
import { weightsAPI } from '../services/api';

export function useWeights() {
  return useQuery({
    queryKey: ['weights'],
    queryFn: () => weightsAPI.getCurrent(),
    staleTime: 30_000,
  });
}

export function useWeightHistory(limit = 50) {
  return useQuery({
    queryKey: ['weightHistory', limit],
    queryFn: () => weightsAPI.getHistory(limit),
    staleTime: 60_000,
  });
}
