import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';

export interface RollingKpi {
  n_trades: number;
  win_rate: number;
  profit_factor: number | null;
  total_r: number;
  avg_r: number;
  max_dd_r: number;
  sharpe: number | null;
}

export interface Rule2SLAttached {
  today_opens: number;
  today_sl_attached: number;
  ok: boolean;
}

export interface Rule3DailyDrawdown {
  today_pnl_usdt: number;
  today_pnl_pct: number;
  limit_pct: number;
  lockdown_triggered: boolean;
  distance_pct: number;
}

export interface Rule5SLRatio {
  today_opens: number;
  today_in_range: number;
  ok: boolean;
}

export interface ConstitutionStatus {
  rule_1_risk_cap_ok: boolean;
  rule_2_sl_attached: Rule2SLAttached;
  rule_3_daily_dd: Rule3DailyDrawdown;
  rule_4_leverage_in_range: boolean;
  rule_4_leverage_value: number;
  rule_5_sl_atr_ratio: Rule5SLRatio;
  rule_6_short_disabled: boolean;
  rule_6_today_blocked: number;
  rule_7_killer_disabled: boolean;
  rule_7_today_blocked: number;
}

export interface AIHealth {
  window_hours: number;
  total_ai_calls: number;
  real_responses: number;
  fallback_passthrough: number;
  failure_taxonomy_rejects: number;
}

export interface TraderKpi {
  window_days: number;
  generated_at: string;
  rolling: RollingKpi;
  constitution: ConstitutionStatus;
  ai_health: AIHealth;
}

export function useV5TraderKpi(windowDays = 30, aiWindowHours = 24) {
  return useQuery<TraderKpi>({
    queryKey: ['v5', 'trader-kpi', windowDays, aiWindowHours],
    queryFn: () =>
      apiGet<TraderKpi>(
        `/api/v5/dashboard/trader-kpi?window_days=${windowDays}&ai_window_hours=${aiWindowHours}`,
      ),
    refetchInterval: 30_000,
  });
}
