import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../../services/api';
import type {
  ManualOrderPreviewRequest, ManualOrderPreviewResponse,
  ManualOrderExecuteRequest, ManualOrderExecuteResponse,
} from '../../types';

export function useV5ManualOrder() {
  const qc = useQueryClient();
  const preview = useMutation({
    mutationFn: (body: ManualOrderPreviewRequest) =>
      apiPost<ManualOrderPreviewResponse>('/api/v5/manual-order/preview', body),
  });
  const execute = useMutation({
    mutationFn: (body: ManualOrderExecuteRequest) =>
      apiPost<ManualOrderExecuteResponse>('/api/v5/manual-order/execute', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['v5', 'active'] });
      qc.invalidateQueries({ queryKey: ['v5', 'history'] });
    },
  });
  return { preview, execute };
}
