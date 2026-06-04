import { useQuery } from '@tanstack/react-query';
import { systemAPI } from '../services/api';

export function useSystemStatus() {
  return useQuery({
    queryKey: ['systemStatus'],
    queryFn: () => systemAPI.getState(),
    refetchInterval: 30_000,
    staleTime: 20_000,
  });
}
