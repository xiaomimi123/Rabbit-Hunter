import React from 'react';
import { GaugeArc } from '../primitives/GaugeArc';
import { Badge } from '../primitives/Badge';

interface Props {
  rsi_15m: number;
  rsi_4h: number | null;
  macd_hist_15m: number;
  macd_hist_prev_15m: number;
  atr_15m: number;
}

export function IndicatorGauges({ rsi_15m, rsi_4h, macd_hist_15m, macd_hist_prev_15m, atr_15m }: Props) {
  const rsiTone = rsi_15m >= 70 ? '超买' : rsi_15m <= 30 ? '超卖' : '中性';
  const rsiBadge: 'short' | 'long' | 'neutral' = rsi_15m >= 70 ? 'short' : rsi_15m <= 30 ? 'long' : 'neutral';

  const flipped = (macd_hist_prev_15m < 0 && macd_hist_15m > 0)
    ? '金叉'
    : (macd_hist_prev_15m > 0 && macd_hist_15m < 0)
    ? '死叉'
    : null;

  return (
    <div className="flex gap-4">
      <div className="flex flex-col items-center">
        <GaugeArc value={rsi_15m} min={0} max={100} thresholds={{ warn: 70, danger: 80 }} label="RSI 15m" size={120} />
        <Badge variant={rsiBadge}>{rsiTone}</Badge>
      </div>
      <div className="flex flex-col items-center justify-center text-xs font-mono">
        <div className="text-white/60">MACD hist 15m</div>
        <div className="text-base text-white">{macd_hist_15m.toFixed(4)}</div>
        <div className="text-white/50">prev {macd_hist_prev_15m.toFixed(4)}</div>
        {flipped && <Badge variant={flipped === '金叉' ? 'long' : 'short'}>{flipped}拐点</Badge>}
      </div>
      <div className="flex flex-col items-center justify-center text-xs font-mono">
        <div className="text-white/60">4h 参考</div>
        <div className="text-base text-white">RSI {rsi_4h?.toFixed(1) ?? '—'}</div>
        <div className="text-white/50">ATR {atr_15m.toFixed(4)}</div>
      </div>
    </div>
  );
}
