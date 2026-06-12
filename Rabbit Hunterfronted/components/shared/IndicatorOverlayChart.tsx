import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, LineStyle, type IChartApi } from 'lightweight-charts';
import type { Kline, SymbolEvent, Interval } from '../../types';

interface Props {
  klines: Kline[];
  events: SymbolEvent[];
  interval: Interval;
  onIntervalChange: (i: Interval) => void;
  currentPrice: number | null;
  indicators?: {
    rsi_15m?: number;
    macd_hist_15m?: number;
    macd_signal_15m?: number;
  };
}

const INTERVALS: Interval[] = ['15m', '1h', '4h'];

function klineToSeriesData(klines: Kline[]) {
  return klines.map(k => ({
    time: Math.floor(k.ts / 1000) as any,
    open: k.open, high: k.high, low: k.low, close: k.close,
  }));
}

function rsiSeries(klines: Kline[], period = 14) {
  const out: { time: number; value: number }[] = [];
  if (klines.length < period + 1) return out;
  let gains = 0, losses = 0;
  for (let i = 1; i <= period; i++) {
    const diff = klines[i].close - klines[i - 1].close;
    if (diff > 0) gains += diff;
    else losses -= diff;
  }
  let avgG = gains / period;
  let avgL = losses / period;
  let rs = avgL === 0 ? 100 : avgG / avgL;
  out.push({ time: Math.floor(klines[period].ts / 1000), value: 100 - 100 / (1 + rs) });
  for (let i = period + 1; i < klines.length; i++) {
    const diff = klines[i].close - klines[i - 1].close;
    const g = diff > 0 ? diff : 0;
    const l = diff < 0 ? -diff : 0;
    avgG = (avgG * (period - 1) + g) / period;
    avgL = (avgL * (period - 1) + l) / period;
    rs = avgL === 0 ? 100 : avgG / avgL;
    out.push({ time: Math.floor(klines[i].ts / 1000), value: 100 - 100 / (1 + rs) });
  }
  return out;
}

function macdHistSeries(klines: Kline[], fast = 12, slow = 26, signalP = 9) {
  if (klines.length < slow + signalP) return [];
  const closes = klines.map(k => k.close);
  const ema = (arr: number[], p: number) => {
    const k = 2 / (p + 1);
    const out: number[] = [];
    let prev = arr[0];
    out.push(prev);
    for (let i = 1; i < arr.length; i++) {
      prev = arr[i] * k + prev * (1 - k);
      out.push(prev);
    }
    return out;
  };
  const ef = ema(closes, fast);
  const es = ema(closes, slow);
  const macd = ef.map((v, i) => v - es[i]);
  const sig = ema(macd, signalP);
  return macd.map((v, i) => ({
    time: Math.floor(klines[i].ts / 1000),
    value: v - sig[i],
    color: v - sig[i] >= 0 ? '#10B981' : '#EF4444',
  }));
}

export function IndicatorOverlayChart({ klines, events, interval, onIntervalChange, currentPrice }: Props) {
  const mainRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mainRef.current || !rsiRef.current || !macdRef.current) return;

    const common = {
      layout: {
        background: { type: ColorType.Solid, color: '#0F1419' },
        textColor: 'rgba(255,255,255,0.7)',
      },
      grid: {
        horzLines: { color: 'rgba(255,255,255,0.04)' },
        vertLines: { color: 'rgba(255,255,255,0.04)' },
      },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.08)' },
    } as const;

    const main: IChartApi = createChart(mainRef.current, { ...common, height: 360 });
    const rsi: IChartApi = createChart(rsiRef.current, { ...common, height: 100 });
    const macd: IChartApi = createChart(macdRef.current, { ...common, height: 100 });

    const candle = main.addCandlestickSeries({
      upColor: '#10B981', downColor: '#EF4444',
      borderUpColor: '#10B981', borderDownColor: '#EF4444',
      wickUpColor: '#10B981', wickDownColor: '#EF4444',
    });
    candle.setData(klineToSeriesData(klines));

    const sideToShape = (e: SymbolEvent) => {
      if (e.event_type === 'entry') return e.side === 'SHORT' ? 'arrowDown' : 'arrowUp';
      if (e.event_type === 'exit') return 'circle';
      return 'square';
    };
    const sideToColor = (e: SymbolEvent) => {
      if (e.event_type === 'exit') {
        if (e.exit_reason === 'TP_HIT') return '#10B981';
        if (e.exit_reason === 'SL_HIT') return '#EF4444';
        return '#F59E0B';
      }
      return e.side === 'SHORT' ? '#EF4444' : '#10B981';
    };
    const markers = events.map(e => ({
      time: Math.floor(new Date(e.timestamp).getTime() / 1000) as any,
      position: e.event_type === 'entry'
        ? (e.side === 'SHORT' ? 'aboveBar' : 'belowBar')
        : 'inBar',
      color: sideToColor(e),
      shape: sideToShape(e) as any,
      text: e.event_type === 'entry' ? `${e.side} ${e.price.toFixed(4)}` : (e.exit_reason || 'exit'),
    }));
    candle.setMarkers(markers as any);

    if (currentPrice != null) {
      candle.createPriceLine({
        price: currentPrice,
        color: '#3B82F6',
        lineStyle: LineStyle.Dashed,
        lineWidth: 1,
        axisLabelVisible: true,
        title: '现价',
      });
    }

    const rsiLine = rsi.addLineSeries({ color: '#F59E0B', lineWidth: 2 });
    rsiLine.setData(rsiSeries(klines) as any);
    rsi.applyOptions({ rightPriceScale: { autoScale: false, scaleMargins: { top: 0.1, bottom: 0.1 } } });
    rsiLine.createPriceLine({ price: 70, color: '#EF4444', lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: '70' });
    rsiLine.createPriceLine({ price: 30, color: '#10B981', lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: '30' });

    const histSeries = macd.addHistogramSeries({ priceFormat: { type: 'price', precision: 6, minMove: 0.000001 } });
    histSeries.setData(macdHistSeries(klines) as any);

    const linkTimeScales = (a: IChartApi, b: IChartApi) => {
      a.timeScale().subscribeVisibleLogicalRangeChange((range: any) => {
        if (range) b.timeScale().setVisibleLogicalRange(range);
      });
    };
    linkTimeScales(main, rsi);
    linkTimeScales(main, macd);
    linkTimeScales(rsi, main);
    linkTimeScales(macd, main);

    main.timeScale().fitContent();
    rsi.timeScale().fitContent();
    macd.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (mainRef.current) main.resize(mainRef.current.clientWidth, 360);
      if (rsiRef.current) rsi.resize(rsiRef.current.clientWidth, 100);
      if (macdRef.current) macd.resize(macdRef.current.clientWidth, 100);
    });
    if (mainRef.current) ro.observe(mainRef.current);

    return () => {
      ro.disconnect();
      try { main.remove(); rsi.remove(); macd.remove(); } catch { /* ignore */ }
    };
  }, [klines, events, currentPrice]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-end gap-1 text-xs">
        {INTERVALS.map(i => (
          <button
            key={i}
            type="button"
            onClick={() => onIntervalChange(i)}
            className={`rounded-sm border px-2 py-1 font-mono ${
              interval === i
                ? 'border-accent-info bg-accent-info/10 text-accent-info'
                : 'border-white/10 text-white/60 hover:bg-white/5'
            }`}
          >
            {i}
          </button>
        ))}
      </div>
      <div ref={mainRef} className="w-full rounded-md border border-white/10" />
      <div className="grid grid-cols-2 gap-2">
        <div>
          <div className="text-xs text-white/50 mb-1 px-2">RSI 14</div>
          <div ref={rsiRef} className="w-full rounded-md border border-white/10" />
        </div>
        <div>
          <div className="text-xs text-white/50 mb-1 px-2">MACD hist (12/26/9)</div>
          <div ref={macdRef} className="w-full rounded-md border border-white/10" />
        </div>
      </div>
    </div>
  );
}
