import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '../../services/api';
import type { V5PositionsResponse, V5Position, ClosePositionRequest, ClosePositionResponse } from '../../types';

interface CombinedActive {
  live: V5Position[];
  paper: V5Position[];
  combined: V5Position[];
  total: number;
}

export function useV5ActivePositions() {
  return useQuery<CombinedActive>({
    queryKey: ['v5', 'active'],
    queryFn: async () => {
      const [live, paper] = await Promise.all([
        apiGet<V5PositionsResponse>('/api/v5/positions?status=OPEN'),
        apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=OPEN'),
      ]);
      return {
        live: live.data,
        paper: paper.data,
        combined: [...live.data, ...paper.data],
        total: live.data.length + paper.data.length,
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
