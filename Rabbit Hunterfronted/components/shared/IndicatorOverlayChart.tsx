import React, { useEffect, useRef, useState } from 'react';
import {
  createChart, ColorType, LineStyle, CrosshairMode,
  type IChartApi, type ISeriesApi, type MouseEventParams, type Time,
} from 'lightweight-charts';
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

interface HoverState {
  time: number | null;          // seconds epoch
  ohlc: { open: number; high: number; low: number; close: number } | null;
  rsi: number | null;
  macd_hist: number | null;
}

const EMPTY_HOVER: HoverState = { time: null, ohlc: null, rsi: null, macd_hist: null };

function fmtTime(timeSec: number | null): string {
  if (timeSec == null) return '—';
  return new Date(timeSec * 1000).toLocaleString('zh-CN', { hour12: false });
}

function fmtPrice(n: number | null | undefined): string {
  if (n == null) return '—';
  if (Math.abs(n) >= 1000) return n.toFixed(2);
  if (Math.abs(n) >= 1) return n.toFixed(4);
  return n.toFixed(6);
}

export function IndicatorOverlayChart({ klines, events, interval, onIntervalChange, currentPrice }: Props) {
  const mainRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<HoverState>(EMPTY_HOVER);

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
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: 'rgba(34,211,238,0.6)', width: 1 as const, style: LineStyle.Solid, labelVisible: true },
        horzLine: { color: 'rgba(34,211,238,0.4)', width: 1 as const, style: LineStyle.Solid, labelVisible: true },
      },
    } as const;

    const main: IChartApi = createChart(mainRef.current, { ...common, height: 360 });
    const rsi: IChartApi = createChart(rsiRef.current, { ...common, height: 120 });
    const macd: IChartApi = createChart(macdRef.current, { ...common, height: 120 });

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
    const rsiData = rsiSeries(klines);
    rsiLine.setData(rsiData as any);
    rsi.applyOptions({ rightPriceScale: { autoScale: false, scaleMargins: { top: 0.1, bottom: 0.1 } } });
    rsiLine.createPriceLine({ price: 70, color: '#EF4444', lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: '70' });
    rsiLine.createPriceLine({ price: 30, color: '#10B981', lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: '30' });

    const histSeries = macd.addHistogramSeries({ priceFormat: { type: 'price', precision: 6, minMove: 0.000001 } });
    const macdData = macdHistSeries(klines);
    histSeries.setData(macdData as any);

    const linkTimeScales = (a: IChartApi, b: IChartApi) => {
      a.timeScale().subscribeVisibleLogicalRangeChange((range: any) => {
        if (range) b.timeScale().setVisibleLogicalRange(range);
      });
    };
    linkTimeScales(main, rsi);
    linkTimeScales(main, macd);
    linkTimeScales(rsi, main);
    linkTimeScales(macd, main);

    // --- Crosshair sync + hover readout ---
    const syncing = { v: false };

    const lookupRsi = (timeSec: number): number | null => {
      // rsiData is ordered; binary search would be nicer but linear is fine for 200 points
      for (let i = 0; i < rsiData.length; i++) {
        if (rsiData[i].time === timeSec) return rsiData[i].value;
      }
      // fallback: closest <= timeSec
      let last: number | null = null;
      for (const p of rsiData) {
        if (p.time <= timeSec) last = p.value;
        else break;
      }
      return last;
    };
    const lookupMacd = (timeSec: number): number | null => {
      for (let i = 0; i < macdData.length; i++) {
        if (macdData[i].time === timeSec) return macdData[i].value;
      }
      let last: number | null = null;
      for (const p of macdData) {
        if (p.time <= timeSec) last = p.value;
        else break;
      }
      return last;
    };
    const lookupCandle = (timeSec: number) => {
      for (const k of klines) {
        if (Math.floor(k.ts / 1000) === timeSec) {
          return { open: k.open, high: k.high, low: k.low, close: k.close };
        }
      }
      return null;
    };

    const onMainMove = (param: MouseEventParams) => {
      if (syncing.v) return;
      if (param.time == null || param.point == null) {
        setHover(EMPTY_HOVER);
        syncing.v = true;
        try { rsi.clearCrosshairPosition(); macd.clearCrosshairPosition(); } catch { /* ignore */ }
        syncing.v = false;
        return;
      }
      const t = param.time as number;
      const rsiVal = lookupRsi(t);
      const macdVal = lookupMacd(t);
      const ohlc = lookupCandle(t);
      setHover({ time: t, ohlc, rsi: rsiVal, macd_hist: macdVal });
      syncing.v = true;
      try {
        if (rsiVal != null) rsi.setCrosshairPosition(rsiVal, t as Time, rsiLine);
        if (macdVal != null) macd.setCrosshairPosition(macdVal, t as Time, histSeries);
      } catch { /* ignore — series may not have data point at that exact time */ }
      syncing.v = false;
    };
    const onRsiMove = (param: MouseEventParams) => {
      if (syncing.v) return;
      if (param.time == null) { setHover(EMPTY_HOVER); return; }
      const t = param.time as number;
      const rsiVal = lookupRsi(t);
      const macdVal = lookupMacd(t);
      const ohlc = lookupCandle(t);
      setHover({ time: t, ohlc, rsi: rsiVal, macd_hist: macdVal });
      syncing.v = true;
      try {
        if (ohlc) main.setCrosshairPosition(ohlc.close, t as Time, candle);
        if (macdVal != null) macd.setCrosshairPosition(macdVal, t as Time, histSeries);
      } catch { /* ignore */ }
      syncing.v = false;
    };
    const onMacdMove = (param: MouseEventParams) => {
      if (syncing.v) return;
      if (param.time == null) { setHover(EMPTY_HOVER); return; }
      const t = param.time as number;
      const rsiVal = lookupRsi(t);
      const macdVal = lookupMacd(t);
      const ohlc = lookupCandle(t);
      setHover({ time: t, ohlc, rsi: rsiVal, macd_hist: macdVal });
      syncing.v = true;
      try {
        if (ohlc) main.setCrosshairPosition(ohlc.close, t as Time, candle);
        if (rsiVal != null) rsi.setCrosshairPosition(rsiVal, t as Time, rsiLine);
      } catch { /* ignore */ }
      syncing.v = false;
    };

    main.subscribeCrosshairMove(onMainMove);
    rsi.subscribeCrosshairMove(onRsiMove);
    macd.subscribeCrosshairMove(onMacdMove);

    main.timeScale().fitContent();
    rsi.timeScale().fitContent();
    macd.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (mainRef.current) main.resize(mainRef.current.clientWidth, 360);
      if (rsiRef.current) rsi.resize(rsiRef.current.clientWidth, 120);
      if (macdRef.current) macd.resize(macdRef.current.clientWidth, 120);
    });
    if (mainRef.current) ro.observe(mainRef.current);

    return () => {
      ro.disconnect();
      try { main.remove(); rsi.remove(); macd.remove(); } catch { /* ignore */ }
    };
  }, [klines, events, currentPrice]);

  const rsiTone = hover.rsi == null
    ? 'text-white/40'
    : hover.rsi >= 70 ? 'text-accent-short'
    : hover.rsi <= 30 ? 'text-accent-long'
    : 'text-white/70';

  const macdTone = hover.macd_hist == null
    ? 'text-white/40'
    : hover.macd_hist >= 0 ? 'text-accent-long' : 'text-accent-short';

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono">
          <span className="text-cyan-300/80">
            ▌ {hover.time != null ? fmtTime(hover.time) : '移动鼠标查看历史时点'}
          </span>
          {hover.ohlc && (
            <>
              <span className="text-white/60">O <span className="text-white">{fmtPrice(hover.ohlc.open)}</span></span>
              <span className="text-white/60">H <span className="text-white">{fmtPrice(hover.ohlc.high)}</span></span>
              <span className="text-white/60">L <span className="text-white">{fmtPrice(hover.ohlc.low)}</span></span>
              <span className="text-white/60">C <span className="text-white">{fmtPrice(hover.ohlc.close)}</span></span>
            </>
          )}
          <span className="text-white/60">RSI <span className={`${rsiTone} font-bold`}>{hover.rsi == null ? '—' : hover.rsi.toFixed(1)}</span></span>
          <span className="text-white/60">MACD hist <span className={`${macdTone} font-bold`}>{hover.macd_hist == null ? '—' : hover.macd_hist.toFixed(4)}</span></span>
        </div>
        <div className="flex items-center gap-1 text-xs">
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
