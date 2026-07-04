import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../services/api';
import type { V5SignalsResponse, V5PositionsResponse, V5Position } from '../../types';

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
    queryFn: async () => {
      const [
        signalsRes,
        paperHistoryRes,
        paperActiveRes,
        liveHistoryRes,
        liveActiveRes,
      ] = await Promise.allSettled([
        apiGet<V5SignalsResponse>('/api/v5/signals?limit=2000'),
        apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=CLOSED&limit=500'),
        apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=OPEN'),
        apiGet<V5PositionsResponse>('/api/v5/positions?status=CLOSED&limit=500'),
        apiGet<V5PositionsResponse>('/api/v5/positions?status=OPEN'),
      ]);

      const signalsData = signalsRes.status === 'fulfilled' ? signalsRes.value.data : [];
      const paperHistoryData = paperHistoryRes.status === 'fulfilled' ? paperHistoryRes.value.data : [];
      const paperActiveData = paperActiveRes.status === 'fulfilled' ? paperActiveRes.value.data : [];
      const liveHistoryData = liveHistoryRes.status === 'fulfilled' ? liveHistoryRes.value.data : [];
      const liveActiveData = liveActiveRes.status === 'fulfilled' ? liveActiveRes.value.data : [];

      const errMsg = (r: PromiseSettledResult<unknown>) =>
        r.status === 'rejected'
          ? String((r.reason as any)?.message ?? r.reason ?? 'unknown')
          : undefined;
      const errors: DashboardData['errors'] = {
        signals: errMsg(signalsRes),
        paper_history: errMsg(paperHistoryRes),
        live_history: errMsg(liveHistoryRes),
        paper_active: errMsg(paperActiveRes),
        live_active: errMsg(liveActiveRes),
      };
      const hasAnyError = Object.values(errors).some(v => v !== undefined);

      const cutoff = Date.now() - 24 * 60 * 60 * 1000;
      const in24 = (iso: string | null) => iso ? new Date(iso).getTime() >= cutoff : false;

      const s24 = signalsData.filter(s => in24(s.created_at));
      const passedAnd = s24.filter(s => s.should_trade === 1);
      const executed = s24.filter(s => s.executed === 1);

      const blockCounts: Record<string, number> = {};
      for (const s of s24) {
        const k = s.block_reason || (s.executed === 1 ? 'EXECUTED' : (s.should_trade === 1 ? 'NONE' : 'OTHER'));
        blockCounts[k] = (blockCounts[k] ?? 0) + 1;
      }

      // F16: paper + live 合并 24h CLOSED
      const closed24 = [...paperHistoryData, ...liveHistoryData].filter(p => in24(p.exit_time));

      const wins = closed24.filter(p => (p.pnl_pct ?? 0) > 0).length;
      const winRate = closed24.length > 0 ? wins / closed24.length : 0;
      const pnlSum = closed24.reduce((acc, p) => acc + (p.pnl_usdt ?? 0), 0);
      const pnlPctSum = closed24.reduce((acc, p) => acc + (p.pnl_pct ?? 0), 0);
      const avgHold = closed24.length > 0
        ? closed24.reduce((acc, p) => {
            if (!p.entry_time || !p.exit_time) return acc;
            const mins = (new Date(p.exit_time).getTime() - new Date(p.entry_time).getTime()) / 60_000;
            return acc + mins;
          }, 0) / closed24.length
        : 0;

      return {
        signals_24h: s24.length,
        signals_passed_and: passedAnd.length,
        signals_executed: executed.length,
        signals_block_counts: blockCounts,
        win_rate_24h: winRate,
        pnl_total_usdt: pnlSum,
        pnl_total_pct: pnlPctSum,
        avg_holding_minutes: avgHold,
        active_count: paperActiveData.length + liveActiveData.length,
        closed_24h: closed24,
        errors: hasAnyError ? errors : undefined,
      };
    },
    refetchInterval: 30_000,
  });
}
