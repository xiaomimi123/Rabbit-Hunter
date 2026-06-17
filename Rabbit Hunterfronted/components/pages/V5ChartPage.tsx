import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useV5Klines } from '../../hooks/api/useV5Klines';
import { useV5SymbolEvents } from '../../hooks/api/useV5SymbolEvents';
import { useUIStore } from '../../services/store';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { IndicatorOverlayChart } from '../shared/IndicatorOverlayChart';
import { Aperture } from '../primitives/Aperture';
import type { Interval } from '../../types';

export function V5ChartPage() {
  const { symbol: encoded } = useParams();
  const [search] = useSearchParams();
  const decoded = (encoded || '');
  const interval = useUIStore(s => s.klineInterval);
  const setKlineInterval = useUIStore(s => s.setKlineInterval);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(t);
  }, []);

  const klines = useV5Klines(decoded, interval, 200);
  const events = useV5SymbolEvents(decoded, 50);
  const eventId = search.get('eventId');
  const lastClose = klines.data?.klines.at(-1)?.close;

  return (
    <div className="px-8 py-7 pb-16 flex flex-col gap-7 max-w-[1400px]">
      <header className="grid grid-cols-[1fr_auto] items-end gap-6 pb-4 border-b border-hairline-strong">
        <div className="flex items-center gap-4">
          <Aperture size={34} rotate className="text-brass" />
          <div>
            <h1 className="font-display text-[2.6rem] leading-none tracking-tight">
              {decoded || '—'}
            </h1>
            <p className="font-cn text-ivory-40 text-[0.85rem] mt-1.5">
              K线图 · indicator overlay · {eventId && <span className="text-brass">已定位事件 #{eventId}</span>}
            </p>
          </div>
        </div>
        <div className="text-right font-mono text-[0.72rem] text-ivory-40 leading-relaxed">
          <div className="tracking-wider2 uppercase">Current Price</div>
          <div className="font-mono text-[1.4rem] text-ivory tabular-nums">
            {lastClose != null ? lastClose.toFixed(Math.abs(lastClose) >= 1 ? 4 : 6) : '—'}
          </div>
          <div className="font-mono text-[0.7rem] text-ivory-40">{now.toLocaleTimeString('zh-CN', { hour12: false })} · UTC+8</div>
        </div>
      </header>

      {klines.isLoading || events.isLoading ? (
        <LoadingSkeleton message="拉取 K 线数据…" />
      ) : klines.isError ? (
        <div className="border border-oxblood-soft bg-oxblood-soft px-4 py-3 font-mono text-[0.85rem] text-oxblood">
          K 线拉取失败:{(klines.error as any)?.detail}
        </div>
      ) : klines.data?.klines.length === 0 ? (
        <div className="py-14 text-center font-body italic text-ivory-40">
          <Aperture size={42} rotate="slow" className="text-ivory-25 mx-auto block mb-3" />
          <span className="opacity-60 mr-2">▌</span>等待 K 线数据...
        </div>
      ) : (
        <IndicatorOverlayChart
          klines={klines.data?.klines ?? []}
          events={events.data?.events ?? []}
          interval={interval}
          onIntervalChange={(i: Interval) => setKlineInterval(i)}
          currentPrice={klines.data?.klines.at(-1)?.close ?? null}
        />
      )}
    </div>
  );
}
