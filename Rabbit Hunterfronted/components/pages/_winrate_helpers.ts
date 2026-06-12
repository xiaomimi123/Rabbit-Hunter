import type { V5Position } from '../../types';

export interface WinRateBreakdown {
  count: number;
  wins: number;
  losses: number;
  win_rate: number;       // 0-1
  total_pnl_usdt: number;
}

const isWin = (p: V5Position) => (p.pnl_pct ?? 0) > 0;

export function winRateOf(positions: V5Position[]): WinRateBreakdown {
  const wins = positions.filter(isWin).length;
  const losses = positions.length - wins;
  const total = positions.reduce((acc, p) => acc + (p.pnl_usdt ?? 0), 0);
  return {
    count: positions.length,
    wins,
    losses,
    win_rate: positions.length > 0 ? wins / positions.length : 0,
    total_pnl_usdt: total,
  };
}

export function bySide(positions: V5Position[]): { long: WinRateBreakdown; short: WinRateBreakdown } {
  return {
    long: winRateOf(positions.filter(p => p.side === 'LONG')),
    short: winRateOf(positions.filter(p => p.side === 'SHORT')),
  };
}

export function byStrategy(positions: V5Position[]): { manual: WinRateBreakdown; auto: WinRateBreakdown } {
  return {
    manual: winRateOf(positions.filter(p => p.strategy_id === 'v5_manual')),
    auto: winRateOf(positions.filter(p => p.strategy_id !== 'v5_manual')),
  };
}

export function byExitReason(positions: V5Position[]): Record<string, WinRateBreakdown> {
  const groups: Record<string, V5Position[]> = {};
  for (const p of positions) {
    const k = p.exit_reason || 'UNKNOWN';
    (groups[k] = groups[k] || []).push(p);
  }
  const out: Record<string, WinRateBreakdown> = {};
  for (const k of Object.keys(groups)) {
    out[k] = winRateOf(groups[k]);
  }
  return out;
}

export function bestAndWorst(positions: V5Position[]): { best: V5Position | null; worst: V5Position | null } {
  if (positions.length === 0) return { best: null, worst: null };
  let best = positions[0], worst = positions[0];
  for (const p of positions) {
    if ((p.pnl_pct ?? 0) > (best.pnl_pct ?? 0)) best = p;
    if ((p.pnl_pct ?? 0) < (worst.pnl_pct ?? 0)) worst = p;
  }
  return { best, worst };
}

export function profitFactor(positions: V5Position[]): number | null {
  let grossW = 0, grossL = 0;
  for (const p of positions) {
    const v = p.pnl_usdt ?? 0;
    if (v > 0) grossW += v;
    else grossL += -v;
  }
  if (grossL === 0) return grossW > 0 ? null : 0;   // null = ∞ (no losses)
  return grossW / grossL;
}

export function streaks(positions: V5Position[]): { maxWin: number; maxLoss: number; current: { side: 'W' | 'L' | null; len: number } } {
  // chronological order (oldest first)
  const sorted = positions.slice().sort((a, b) => (a.exit_time || '').localeCompare(b.exit_time || ''));
  let maxW = 0, maxL = 0, curW = 0, curL = 0;
  for (const p of sorted) {
    if (isWin(p)) { curW++; curL = 0; maxW = Math.max(maxW, curW); }
    else { curL++; curW = 0; maxL = Math.max(maxL, curL); }
  }
  const last = sorted.length === 0 ? null : (isWin(sorted[sorted.length - 1]) ? 'W' as const : 'L' as const);
  const lastLen = last === 'W' ? curW : last === 'L' ? curL : 0;
  return { maxWin: maxW, maxLoss: maxL, current: { side: last, len: lastLen } };
}
