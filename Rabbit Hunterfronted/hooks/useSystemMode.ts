import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { apiGet } from '../services/api';
import { useUIStore } from '../services/store';
import type { SettingsResponse, Mode } from '../types';

export function useSystemMode(): { mode: Mode | null; isLoading: boolean } {
  const q = useQuery<SettingsResponse>({
    queryKey: ['v5', 'settings'],
    queryFn: () => apiGet<SettingsResponse>('/api/v5/settings'),
    staleTime: 60_000,
  });
  const setSystemMode = useUIStore((s) => s.setSystemMode);

  useEffect(() => {
    if (q.data?.system_mode) setSystemMode(q.data.system_mode);
  }, [q.data?.system_mode, setSystemMode]);

  return {
    mode: q.data?.system_mode ?? null,
    isLoading: q.isLoading,
  };
}
