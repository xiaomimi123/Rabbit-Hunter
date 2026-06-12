import type { V5Signal, Side } from '../../types';

export function signalScore(s: V5Signal): number {
  const conf = s.ai_confidence ?? 0;
  const sizeMult = s.ai_size_multiplier ?? 1;
  const andBonus = s.should_trade === 1 ? 20 : 0;
  return Math.round(conf * 100 * sizeMult * 0.5 + andBonus);
}

export function dotStateFor(s: V5Signal): '●●●' | '●●○' | '●○○' {
  if (s.executed === 1) return '●●●';
  if (s.should_trade === 1 && (s.ai_confidence ?? 0) >= 0.6) return '●●○';
  return '●○○';
}

export function formatSideBadgeTone(side: Side | null): 'long' | 'short' | 'neutral' {
  if (side === 'LONG') return 'long';
  if (side === 'SHORT') return 'short';
  return 'neutral';
}

export function blockReasonZh(reason: string | null): string {
  if (!reason) return '';
  const MAP: Record<string, string> = {
    'NOT_RSI_AND_MACD': 'RSI 与 MACD 未合谋',
    'NOT_RSI_EXTREME': 'RSI 未到极端',
    'NOT_MACD_FLIP': 'MACD 无拐点',
    'NOT_DELTA_15M': 'ΔP15m 不足',
    'NOT_VOLUME': '成交额不足',
    'MAX_CONCURRENT_POSITIONS': '活仓上限',
    'AI_REJECTED': 'AI 否决',
    'AI_UNAVAILABLE_LIVE_FAIL_CLOSED': 'AI 不可用 (LIVE 拒绝)',
    'OPEN_FAILED': '开仓失败',
  };
  return MAP[reason] || reason;
}
