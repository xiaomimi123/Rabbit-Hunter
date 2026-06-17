import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { FundingStatusResponse, FundingHistoryResponse } from '../../types';

export function useV5FundingStatus() {
  return useQuery<FundingStatusResponse>({
    queryKey: ['v5', 'funding', 'status'],
    queryFn: () => apiGet<FundingStatusResponse>('/api/v5/funding/status'),
    refetchInterval: 60_000,
  });
}

export function useV5FundingHistory(symbol: string | null, limit = 50) {
  return useQuery<FundingHistoryResponse>({
    queryKey: ['v5', 'funding', 'history', symbol, limit],
    queryFn: () => apiGet<FundingHistoryResponse>(
      `/api/v5/funding/history/${symbol}?limit=${limit}`),
    enabled: !!symbol,
    refetchInterval: 60_000,
  });
}
