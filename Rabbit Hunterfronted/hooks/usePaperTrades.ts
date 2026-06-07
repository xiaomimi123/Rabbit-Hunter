import { useQuery } from '@tanstack/react-query';
import { paperTradesAPI } from '../services/api';

/**
 * v0.5.4: SHADOW 模式下的虚拟仓位 — PositionsPage Paper tab 用。
 *
 * 返回 paper_trades 行 + 聚合 KPI（总笔数 / 胜率 / 累计虚拟 PnL / 平均持仓）。
 * 15 秒刷新一次，跟实盘持仓刷新节奏一致。
 */
export function usePaperTrades(statusFilter: 'all' | 'open' | 'closed' = 'all', limit = 200) {
  return useQuery({
    queryKey:        ['paperTrades', statusFilter, limit],
    queryFn:         () => paperTradesAPI.list(statusFilter, limit),
    refetchInterval: 15_000,
    staleTime:       10_000,
  });
}
