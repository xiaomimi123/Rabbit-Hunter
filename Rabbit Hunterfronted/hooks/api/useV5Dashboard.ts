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
}

export function useV5Dashboard() {
  return useQuery<DashboardData>({
    queryKey: ['v5', 'dashboard'],
    queryFn: async () => {
      const [signals, history, active] = await Promise.all([
        apiGet<V5SignalsResponse>('/api/v5/signals?limit=2000'),
        apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=CLOSED&limit=500'),
        apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=OPEN'),
      ]);

      const cutoff = Date.now() - 24 * 60 * 60 * 1000;
      const in24 = (iso: string | null) => iso ? new Date(iso).getTime() >= cutoff : false;

      const s24 = signals.signals.filter(s => in24(s.created_at));
      const passedAnd = s24.filter(s => s.should_trade);
      const executed = s24.filter(s => s.executed);

      const blockCounts: Record<string, number> = {};
      for (const s of s24) {
        const k = s.block_reason || (s.executed ? 'EXECUTED' : (s.should_trade ? 'NONE' : 'OTHER'));
        blockCounts[k] = (blockCounts[k] ?? 0) + 1;
      }

      const closed24 = history.positions.filter(p => in24(p.exit_time));
      const wins = closed24.filter(p => (p.pnl_percent ?? 0) > 0).length;
      const winRate = closed24.length > 0 ? wins / closed24.length : 0;
      const pnlSum = closed24.reduce((acc, p) => acc + (p.pnl_usdt ?? 0), 0);
      const pnlPctSum = closed24.reduce((acc, p) => acc + (p.pnl_percent ?? 0), 0);
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
        active_count: active.count,
        closed_24h: closed24,
      };
    },
    refetchInterval: 30_000,
  });
}
