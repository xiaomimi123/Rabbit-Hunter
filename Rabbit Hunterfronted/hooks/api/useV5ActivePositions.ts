import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '../../services/api';
import type { V5PositionsResponse, V5Position, ClosePositionRequest, ClosePositionResponse } from '../../types';

interface CombinedActive {
  live: V5Position[];
  paper: V5Position[];
  combined: V5Position[];
  total: number;
  live_error?: string;
  paper_error?: string;
}

export function useV5ActivePositions() {
  return useQuery<CombinedActive>({
    queryKey: ['v5', 'active'],
    queryFn: async () => {
      const [liveResult, paperResult] = await Promise.allSettled([
        apiGet<V5PositionsResponse>('/api/v5/positions?status=OPEN'),
        apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=OPEN'),
      ]);
      const live = liveResult.status === 'fulfilled' ? liveResult.value.data : [];
      const paper = paperResult.status === 'fulfilled' ? paperResult.value.data : [];
      const live_error = liveResult.status === 'rejected'
        ? String((liveResult.reason as any)?.message ?? liveResult.reason ?? 'unknown')
        : undefined;
      const paper_error = paperResult.status === 'rejected'
        ? String((paperResult.reason as any)?.message ?? paperResult.reason ?? 'unknown')
        : undefined;
      return {
        live,
        paper,
        combined: [...live, ...paper],
        total: live.length + paper.length,
        live_error,
        paper_error,
      };
    },
    refetchInterval: 5_000,
  });
}

export function useV5ClosePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: ClosePositionRequest }) =>
      apiPost<ClosePositionResponse>(`/api/v5/positions/${id}/close`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['v5', 'active'] });
      qc.invalidateQueries({ queryKey: ['v5', 'history'] });
    },
  });
}
