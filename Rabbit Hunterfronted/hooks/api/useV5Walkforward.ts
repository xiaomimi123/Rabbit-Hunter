import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';

export interface WFReportListItem {
  name: string;
  size_bytes: number;
  modified_at: string;
  n_oos_trades: number | null;
  net_avg_r: number | null;
  net_profit_factor: number | null;
  kpi_passes_doc_15_2: boolean | null;
  setup_filter: string | null;
  symbols: string[] | null;
  period_start: string | null;
  period_end: string | null;
}

export interface WFReportListResponse {
  reports: WFReportListItem[];
}

export interface WFSummaryView {
  n: number;
  win_rate: number;
  avg_r: number;
  total_r: number;
  median_r: number;
  best_r: number;
  worst_r: number;
  profit_factor: number | null;
  max_drawdown_r: number;
}

export interface WFWindow {
  train_start: string;
  train_end: string;
  oos_start: string;
  oos_end: string;
  n_entries: number;
  n_closed: number;
}

export interface WFReport {
  config: {
    start_iso: string;
    end_iso: string;
    symbols: string[];
    train_days: number;
    oos_days: number;
    step_days: number;
    setup_filter: string | null;
    cost_config: any;
  };
  windows: WFWindow[];
  oos_combined_entries: any[];
  oos_summary: WFSummaryView;
  oos_summary_net: WFSummaryView;
  pass_doc_kpi: {
    n_oos_trades: number;
    gross_avg_r: number;
    gross_profit_factor: number | null;
    net_avg_r: number;
    net_profit_factor: number | null;
    kpi_passes_doc_15_2: boolean;
  };
}

export function useWalkforwardReports() {
  return useQuery<WFReportListResponse>({
    queryKey: ['v5', 'wf', 'reports'],
    queryFn: () => apiGet<WFReportListResponse>('/api/v5/walkforward/reports'),
    refetchInterval: 30_000,
  });
}

export function useWalkforwardReport(name: string | null) {
  return useQuery<WFReport>({
    queryKey: ['v5', 'wf', 'report', name],
    queryFn: () => apiGet<WFReport>(`/api/v5/walkforward/reports/${name}`),
    enabled: !!name,
    staleTime: 5 * 60_000,
  });
}
