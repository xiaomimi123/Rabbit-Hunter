import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';

export interface AccountBalance {
  status: 'not_configured' | 'ok' | 'error';
  exchange: string;
  testnet: boolean;
  total_usdt: number;
  available_usdt: number;
  error?: string | null;
  paper_initial_balance_usdt: number;
  paper_realized_pnl_usdt: number;
  paper_open_count: number;
}

export function useAccountBalance() {
  return useQuery<AccountBalance>({
    queryKey: ['v5', 'account', 'balance'],
    queryFn: () => apiGet<AccountBalance>('/api/v5/account/balance'),
    refetchInterval: 30_000,
  });
}
