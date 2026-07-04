import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { V5Position } from '../../types';

export interface DashboardData {
  signals_24h: number;
  signals_passed_and: number;
  signals_executed: number;
  signals_block_counts: Record<string, number>;
  win_rate_24h: number;
  pnl_total_usdt: number;
  pnl_total_pct: number;
  avg_holding_minutes: number;
  active_count: number;
  closed_24h: V5Position[];
  errors?: {
    signals?: string;
    paper_history?: string;
    live_history?: string;
    paper_active?: string;
    live_active?: string;
  };
}

export function useV5Dashboard() {
  return useQuery<DashboardData>({
    queryKey: ['v5', 'dashboard'],
    queryFn: () => apiGet<DashboardData>('/api/v5/dashboard/summary?hours=24'),
    refetchInterval: 30_000,
  });
}
