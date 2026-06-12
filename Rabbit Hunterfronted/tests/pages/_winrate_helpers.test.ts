import { describe, it, expect } from 'vitest';
import { winRateOf, bySide, byStrategy, profitFactor, streaks } from '@/components/pages/_winrate_helpers';
import type { V5Position } from '@/types';

const mk = (over: Partial<V5Position>): V5Position => ({
  id: 0, symbol: 'X', side: 'LONG', status: 'CLOSED',
  entry_price: 100, entry_time: '2026-01-01T00:00:00Z',
  sl_price: 90, tp_price: 110, size_usdt: 10, position_size_coins: 0.1,
  leverage: 10, target_close_at: null, extension_count: 0,
  entry_rsi_15m: null, entry_macd_hist_15m: null, entry_rsi_4h: null, entry_atr_15m: null,
  exit_price: 110, exit_time: '2026-01-01T01:00:00Z', exit_reason: 'TP_HIT',
  pnl_usdt: 1, pnl_pct: 1, holding_minutes: 60,
  created_at: '2026-01-01T00:00:00Z', updated_at: null,
  strategy_id: 'v5_rsi_macd',
  ...over,
});

describe('winrate helpers', () => {
  it('winRateOf counts wins and losses', () => {
    const out = winRateOf([
      mk({ pnl_pct: 1, pnl_usdt: 1 }),
      mk({ pnl_pct: 1, pnl_usdt: 1 }),
      mk({ pnl_pct: -1, pnl_usdt: -1 }),
    ]);
    expect(out.wins).toBe(2);
    expect(out.losses).toBe(1);
    expect(out.win_rate).toBeCloseTo(2 / 3);
    expect(out.total_pnl_usdt).toBe(1);
  });

  it('bySide separates LONG / SHORT', () => {
    const out = bySide([
      mk({ side: 'LONG', pnl_pct: 1, pnl_usdt: 1 }),
      mk({ side: 'SHORT', pnl_pct: -1, pnl_usdt: -1 }),
    ]);
    expect(out.long.count).toBe(1);
    expect(out.short.count).toBe(1);
  });

  it('byStrategy separates manual / auto', () => {
    const out = byStrategy([
      mk({ strategy_id: 'v5_manual', pnl_pct: 1, pnl_usdt: 1 }),
      mk({ strategy_id: 'v5_rsi_macd', pnl_pct: -1, pnl_usdt: -1 }),
    ]);
    expect(out.manual.count).toBe(1);
    expect(out.auto.count).toBe(1);
  });

  it('profitFactor returns ratio or null when no losses', () => {
    expect(profitFactor([mk({ pnl_usdt: 2 }), mk({ pnl_usdt: -1 })])).toBe(2);
    expect(profitFactor([mk({ pnl_usdt: 2 })])).toBe(null);   // ∞
  });

  it('streaks tracks max W / L runs', () => {
    const data = [
      mk({ exit_time: '2026-01-01T00:00:00Z', pnl_pct: 1 }),
      mk({ exit_time: '2026-01-01T01:00:00Z', pnl_pct: 1 }),
      mk({ exit_time: '2026-01-01T02:00:00Z', pnl_pct: -1 }),
      mk({ exit_time: '2026-01-01T03:00:00Z', pnl_pct: -1 }),
      mk({ exit_time: '2026-01-01T04:00:00Z', pnl_pct: -1 }),
      mk({ exit_time: '2026-01-01T05:00:00Z', pnl_pct: 1 }),
    ];
    const out = streaks(data);
    expect(out.maxWin).toBe(2);
    expect(out.maxLoss).toBe(3);
    expect(out.current.side).toBe('W');
    expect(out.current.len).toBe(1);
  });
});
