import { useQuery, useQueryClient } from '@tanstack/react-query';
import { positionsAPI } from '../services/api';
import { Position } from '../types';

export function usePositions() {
  return useQuery<Position[]>({
    queryKey: ['positions'],
    queryFn: async () => {
      const result = await positionsAPI.getActive();
      const raw = result?.data?.active ?? result?.data ?? result ?? [];
      return Array.isArray(raw) ? raw : [];
    },
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}

/** Call this from WebSocket handlers to force a positions refresh. */
export function useInvalidatePositions() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ['positions'] });
}
