import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPatch } from '../../services/api';
import type { SettingsResponse, SettingsPatchRequest } from '../../types';

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
  return { query, patch };
}
