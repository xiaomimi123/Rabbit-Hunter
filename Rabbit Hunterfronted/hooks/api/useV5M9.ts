import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '../../services/api';

export interface BookOut {
  id: number;
  title: string;
  author: string | null;
  source_type: string;
  content_length: number | null;
  notes: string | null;
  uploaded_at: string;
  n_candidates: number;
}

export interface CandidateOut {
  id: number;
  book_id: number | null;
  name: string;
  description: string | null;
  rule_spec_json: string;
  source_quote: string | null;
  extracted_by: string;
  status: 'pending' | 'validated' | 'approved' | 'rejected' | 'broken';
  wf_report_path: string | null;
  kpi_passes: number | null;
  reject_reason: string | null;
  created_at: string;
  validated_at: string | null;
  approved_at: string | null;
  approved_by: string | null;
}

export interface ValidationResult {
  wf_report_path: string;
  kpi_passes: boolean;
  n_oos_trades: number;
  net_avg_r: number;
  net_profit_factor: number | null;
}

export function useM9Books() {
  return useQuery<{ books: BookOut[] }>({
    queryKey: ['m9', 'books'],
    queryFn: () => apiGet('/api/v5/m9/books'),
    refetchInterval: 60_000,
  });
}

export function useM9AddBook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      title: string; author?: string; source_type?: string;
      content_text?: string; notes?: string;
    }) => apiPost<BookOut>('/api/v5/m9/books', payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['m9', 'books'] }),
  });
}

export function useM9Candidates(status?: string) {
  return useQuery<{ candidates: CandidateOut[] }>({
    queryKey: ['m9', 'candidates', status ?? null],
    queryFn: () => apiGet(`/api/v5/m9/candidates${status ? `?status=${status}` : ''}`),
    refetchInterval: 30_000,
  });
}

export function useM9AddCandidate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      name: string; rule_spec: any;
      book_id?: number | null; description?: string;
      source_quote?: string; extracted_by?: string;
    }) => apiPost<CandidateOut>('/api/v5/m9/candidates', payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['m9', 'candidates'] }),
  });
}

export function useM9ValidateCandidate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }: {
      id: number; start_iso: string; end_iso: string; symbols: string[];
      train_days?: number; oos_days?: number; step_days?: number;
    }) => apiPost<ValidationResult>(`/api/v5/m9/candidates/${id}/validate`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['m9', 'candidates'] }),
  });
}

export function useM9ApproveCandidate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, approver }: { id: number; approver: string }) =>
      apiPost(`/api/v5/m9/candidates/${id}/approve`, { approver }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['m9', 'candidates'] }),
  });
}

export function useM9RejectCandidate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      apiPost(`/api/v5/m9/candidates/${id}/reject`, { reason }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['m9', 'candidates'] }),
  });
}
