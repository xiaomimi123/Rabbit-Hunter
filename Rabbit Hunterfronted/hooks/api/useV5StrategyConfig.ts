import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPatch, apiPost } from '../../services/api';
import type {
  StrategyConfigResponse, StrategyConfigPatchRequest, StrategyConfigPreviewResponse,
} from '../../types';

export function useV5StrategyConfig() {
  const qc = useQueryClient();
  const query = useQuery<StrategyConfigResponse>({
    queryKey: ['v5', 'config'],
    queryFn: () => apiGet<StrategyConfigResponse>('/api/v5/strategy-config'),
  });
  const patch = useMutation({
    mutationFn: (body: StrategyConfigPatchRequest) =>
      apiPatch<StrategyConfigResponse>('/api/v5/strategy-config', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['v5', 'config'] }),
  });
  const preview = useMutation({
    mutationFn: (body: StrategyConfigPatchRequest) =>
      apiPost<StrategyConfigPreviewResponse>('/api/v5/strategy-config/preview', body),
  });
  return { query, patch, preview };
}
