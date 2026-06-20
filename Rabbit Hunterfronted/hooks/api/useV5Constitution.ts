import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';

export interface ConstitutionSnapshot {
  max_per_trade_risk_pct: number;
  daily_drawdown_limit_pct: number;
  min_rr: number;
  min_liq_to_sl_distance_ratio: number;
  final_sl_atr_ratio_min: number;
  final_sl_atr_ratio_max: number;
  evolution_ai_sl_mult_min: number;
  evolution_ai_sl_mult_max: number;
  evolution_size_mult_min: number;
  evolution_size_mult_max: number;
  min_sample_size_for_decision: number;
  default_disabled_setups: string[];
}

export interface IronlawLiveState {
  today_realized_pnl: number;
  daily_dd_remaining_usdt: number;
  daily_dd_triggered: boolean;
  open_positions: number;
  max_concurrent: number;
}

export interface SetupPerfRow {
  setup_type: string;
  sample_count: number;
  win_count: number;
  loss_count: number;
  scratch_count: number;
  avg_realized_r: number | null;
  total_realized_r: number | null;
  status: 'noisy' | 'active' | 'disabled';
  disabled_reason: string | null;
  updated_at: string;
}

export interface SetupPerfResponse { rows: SetupPerfRow[] }

export function useConstitution() {
  return useQuery<ConstitutionSnapshot>({
    queryKey: ['v5', 'constitution'],
    queryFn: () => apiGet<ConstitutionSnapshot>('/api/v5/constitution'),
    staleTime: 5 * 60_000,
  });
}

export function useIronlawState() {
  return useQuery<IronlawLiveState>({
    queryKey: ['v5', 'ironlaw-state'],
    queryFn: () => apiGet<IronlawLiveState>('/api/v5/ironlaw-state'),
    refetchInterval: 15_000,
  });
}

export function useSetupPerformance() {
  return useQuery<SetupPerfResponse>({
    queryKey: ['v5', 'setup-performance'],
    queryFn: () => apiGet<SetupPerfResponse>('/api/v5/setup-performance'),
    refetchInterval: 60_000,
  });
}
