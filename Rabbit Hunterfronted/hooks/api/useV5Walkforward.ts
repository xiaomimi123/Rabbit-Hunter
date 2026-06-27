import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '../../services/api';

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


// ─── 实验台: 触发 + 跟踪任务 ────────────────────────────────

export interface WFRunRequest {
  variant: 'A' | 'B' | 'C';
  start: string;            // ISO
  end: string;
  symbols: string[];
  train_days: number;
  oos_days: number;
  step_days: number;
  exit_strategy: 'baseline' | 'vegas_full' | 'vegas_sl_only';
  max_hold_minutes: number;
  cost_preset: 'realistic' | 'optimistic' | 'pessimistic';
  cross_threshold_pct?: number;
  a_proximity_pct?: number;
}

export interface WFJob {
  job_id: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  params: WFRunRequest;
  report_name: string | null;
  error: string | null;
  stdout_tail: string | null;
}

export function useRunWalkforward() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WFRunRequest) =>
      apiPost<{ job_id: string; status: string }>('/api/v5/walkforward/run', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['v5', 'wf', 'jobs'] });
    },
  });
}

export function useWalkforwardJob(jobId: string | null, opts?: { pollInterval?: number }) {
  return useQuery<WFJob>({
    queryKey: ['v5', 'wf', 'job', jobId],
    queryFn: () => apiGet<WFJob>(`/api/v5/walkforward/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!d) return 2000;
      if (d.status === 'queued' || d.status === 'running') return opts?.pollInterval ?? 2000;
      return false; // done / failed → stop polling
    },
  });
}

export function useWalkforwardJobs(limit = 20) {
  return useQuery<{ jobs: WFJob[] }>({
    queryKey: ['v5', 'wf', 'jobs', limit],
    queryFn: () => apiGet<{ jobs: WFJob[] }>(`/api/v5/walkforward/jobs?limit=${limit}`),
    refetchInterval: 5000,
  });
}
