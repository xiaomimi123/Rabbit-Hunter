import { useQuery } from '@tanstack/react-query';
import { systemAPI } from '../services/api';

/**
 * v0.5.2: 当前 active exchange（OKX / Binance）。
 * 后端 EXCHANGE env 决定；前端只读，60s 刷新（用户改 env 后需重启 docker，无热更需求）。
 */
export function useExchange() {
  return useQuery<{ exchange: string; label: string; testnet: boolean }>({
    queryKey: ['activeExchange'],
    queryFn: () => systemAPI.getExchange(),
    refetchInterval: 60_000,
    staleTime: 50_000,
  });
}
