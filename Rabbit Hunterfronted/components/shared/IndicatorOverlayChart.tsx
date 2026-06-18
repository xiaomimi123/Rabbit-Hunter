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
    color: v - sig[i] >= 0 ? '#6B8568' : '#A53E32',
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
        background: { type: ColorType.Solid, color: '#0F1115' },
        textColor: 'rgba(241,236,221,0.72)',
        fontFamily: '"Fira Code", monospace',
      },
      grid: {
        horzLines: { color: 'rgba(241,236,221,0.04)' },
        vertLines: { color: 'rgba(241,236,221,0.04)' },
      },
      rightPriceScale: { borderColor: 'rgba(241,236,221,0.10)' },
      timeScale: { borderColor: 'rgba(241,236,221,0.10)' },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: 'rgba(201,161,75,0.65)', width: 1 as const, style: LineStyle.Solid, labelVisible: true },
        horzLine: { color: 'rgba(201,161,75,0.45)', width: 1 as const, style: LineStyle.Solid, labelVisible: true },
      },
    } as const;

    const main: IChartApi = createChart(mainRef.current, { ...common, height: 360 });
    const rsi: IChartApi = createChart(rsiRef.current, { ...common, height: 120 });
    const macd: IChartApi = createChart(macdRef.current, { ...common, height: 120 });

    const candle = main.addCandlestickSeries({
      upColor: '#6B8568', downColor: '#A53E32',
      borderUpColor: '#6B8568', borderDownColor: '#A53E32',
      wickUpColor: '#6B8568', wickDownColor: '#A53E32',
    });
    candle.setData(klineToSeriesData(klines));

    const sideToShape = (e: SymbolEvent) => {
      if (e.event_type === '入场') return e.side === 'SHORT' ? 'arrowDown' : 'arrowUp';
      if (e.event_type === '出场') return 'circle';
      return 'square';
    };
    const sideToColor = (e: SymbolEvent) => {
      if (e.event_type === '出场') {
        if (e.exit_reason === 'TP_HIT') return '#6B8568';
        if (e.exit_reason === 'SL_HIT') return '#A53E32';
        return '#C9A14B';
      }
      return e.side === 'SHORT' ? '#A53E32' : '#6B8568';
    };
    const markers = events.map(e => ({
      time: Math.floor(new Date(e.timestamp).getTime() / 1000) as any,
      position: e.event_type === '入场'
        ? (e.side === 'SHORT' ? 'aboveBar' : 'belowBar')
        : 'inBar',
      color: sideToColor(e),
      shape: sideToShape(e) as any,
      text: e.event_type === '入场' ? `${e.side} ${e.price.toFixed(4)}` : (e.exit_reason || '出场'),
    }));
    candle.setMarkers(markers as any);

    if (currentPrice != null) {
      candle.createPriceLine({
        price: currentPrice,
        color: '#C9A14B',
        lineStyle: LineStyle.Dashed,
        lineWidth: 1,
        axisLabelVisible: true,
        title: '现价',
      });
    }

    const rsiLine = rsi.addLineSeries({ color: '#C9A14B', lineWidth: 2 });
    const rsiData = rsiSeries(klines);
    rsiLine.setData(rsiData as any);
    rsi.applyOptions({ rightPriceScale: { autoScale: false, scaleMargins: { top: 0.1, bottom: 0.1 } } });
    rsiLine.createPriceLine({ price: 70, color: '#A53E32', lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: '70' });
    rsiLine.createPriceLine({ price: 30, color: '#6B8568', lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: '30' });

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
    ? 'text-ivory-40'
    : hover.rsi >= 70 ? 'text-oxblood'
    : hover.rsi <= 30 ? 'text-sage'
    : 'text-ivory-70';

  const macdTone = hover.macd_hist == null
    ? 'text-ivory-40'
    : hover.macd_hist >= 0 ? 'text-sage' : 'text-oxblood';

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3 px-3 py-2 border border-hairline bg-bg-base">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.78rem] font-mono">
          <span className="text-brass">
            ▌ {hover.time != null ? fmtTime(hover.time) : '移动鼠标查看历史时点'}
          </span>
          {hover.ohlc && (
            <>
              <span className="text-ivory-40">O <span className="text-ivory">{fmtPrice(hover.ohlc.open)}</span></span>
              <span className="text-ivory-40">H <span className="text-ivory">{fmtPrice(hover.ohlc.high)}</span></span>
              <span className="text-ivory-40">L <span className="text-ivory">{fmtPrice(hover.ohlc.low)}</span></span>
              <span className="text-ivory-40">C <span className="text-ivory">{fmtPrice(hover.ohlc.close)}</span></span>
            </>
          )}
          <span className="text-ivory-40">RSI <span className={`${rsiTone} font-medium`}>{hover.rsi == null ? '—' : hover.rsi.toFixed(1)}</span></span>
          <span className="text-ivory-40">MACD hist <span className={`${macdTone} font-medium`}>{hover.macd_hist == null ? '—' : hover.macd_hist.toFixed(4)}</span></span>
        </div>
        <div className="inline-flex border border-hairline-strong">
          {INTERVALS.map(i => (
            <button
              key={i}
              type="button"
              onClick={() => onIntervalChange(i)}
              className={`font-mono text-[0.7rem] tracking-wider2 px-3 py-1 border-r border-hairline-strong last:border-r-0 ${
                interval === i
                  ? 'bg-brass-soft text-brass'
                  : 'text-ivory-70 hover:bg-white/[0.04]'
              }`}
            >
              {i}
            </button>
          ))}
        </div>
      </div>
      <div ref={mainRef} className="w-full border border-hairline" />
      <div className="grid grid-cols-2 max-[640px]:grid-cols-1 gap-2">
        <div>
          <div className="font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase mb-1 px-2">RSI 14</div>
          <div ref={rsiRef} className="w-full border border-hairline" />
        </div>
        <div>
          <div className="font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase mb-1 px-2">MACD hist (12/26/9)</div>
          <div ref={macdRef} className="w-full border border-hairline" />
        </div>
      </div>
    </div>
  );
}
