import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPatch, apiPost } from '../../services/api';
import type {
  SettingsResponse,
  SettingsPatchRequest,
  TestAIRequest,
  TestAIResponse,
} from '../../types';

export function useV5Settings() {
  const qc = useQueryClient();
  const query = useQuery<SettingsResponse>({
    queryKey: ['v5', 'settings'],
    queryFn: () => apiGet<SettingsResponse>('/api/v5/settings'),
  });
  const patch = useMutation({
    mutationFn: (body: SettingsPatchRequest) =>
      apiPatch<SettingsResponse>('/api/v5/settings', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['v5', 'settings'] }),
  });
  const testAi = useMutation({
    mutationFn: (body: TestAIRequest) =>
      apiPost<TestAIResponse>('/api/v5/settings/test-ai', body),
  });
  return { query, patch, testAi };
}
