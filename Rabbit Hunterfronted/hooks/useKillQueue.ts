import { useQuery } from '@tanstack/react-query';
import { killQueueAPI } from '../services/api';
import { KillBoardItem } from '../types';

/**
 * Dedup by symbol, keep highest score.
 * The KillBoard transform step happens inside the component (useMemo).
 * Here we just return the raw deduped API rows.
 */
function deduplicateBySymbol(items: any[]): any[] {
  const seen = new Map<string, any>();
  for (const item of items) {
    const sym = item.symbol;
    if (!sym) continue;
    const existing = seen.get(sym);
    // Keep the one with higher final_score (or higher timestamp)
    if (!existing || (item.final_score ?? 0) >= (existing.final_score ?? 0)) {
      seen.set(sym, item);
    }
  }
  return Array.from(seen.values()).sort(
    (a, b) => (b.final_score ?? 0) - (a.final_score ?? 0)
  );
}

export function useKillQueue(limit = 50, minScore = 0) {
  return useQuery<any[]>({
    queryKey: ['killQueue', limit, minScore],
    queryFn: async () => {
      const result = await killQueueAPI.getQueue(limit, minScore);
      const raw: any[] = result?.data ?? (Array.isArray(result) ? result : []);
      return deduplicateBySymbol(Array.isArray(raw) ? raw : []);
    },
    refetchInterval: 10_000,
    staleTime: 8_000,
  });
}
