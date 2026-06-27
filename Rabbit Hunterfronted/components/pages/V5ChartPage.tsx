import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { AlertCircle, LineChart as LineChartIcon } from 'lucide-react';
import { useV5Klines } from '../../hooks/api/useV5Klines';
import { useV5SymbolEvents } from '../../hooks/api/useV5SymbolEvents';
import { useUIStore } from '../../services/store';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { IndicatorOverlayChart } from '../shared/IndicatorOverlayChart';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { Alert } from '../primitives-v3/Alert';
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
    <div className="mx-auto w-full max-w-7xl px-6 py-6 space-y-6">
      <SectionTitle
        title={decoded || '—'}
        subtitle={
          eventId
            ? `K线图 · 已定位事件 #${eventId}`
            : 'K线图 · indicator overlay'
        }
        action={
          <div className="text-right">
            <div className="font-mono text-2xl font-semibold tabular-nums text-ivory">
              {lastClose != null ? lastClose.toFixed(Math.abs(lastClose) >= 1 ? 4 : 6) : '—'}
            </div>
            <div className="text-xs text-ivory-40">
              {now.toLocaleTimeString('zh-CN', { hour12: false })} · UTC+8
            </div>
          </div>
        }
      />

      {klines.isLoading || events.isLoading ? (
        <LoadingSkeleton message="拉取 K 线数据…" />
      ) : klines.isError ? (
        <Alert tone="error">K 线拉取失败:{(klines.error as any)?.detail}</Alert>
      ) : klines.data?.klines.length === 0 ? (
        <Card>
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-bg-elevated">
              <LineChartIcon className="h-5 w-5 text-ivory-40" />
            </div>
            <div className="text-sm text-ivory-70">等待 K 线数据…</div>
          </div>
        </Card>
      ) : (
        <Card className="!p-3">
          <IndicatorOverlayChart
            klines={klines.data?.klines ?? []}
            events={events.data?.events ?? []}
            interval={interval}
            onIntervalChange={(i: Interval) => setKlineInterval(i)}
            currentPrice={klines.data?.klines.at(-1)?.close ?? null}
          />
        </Card>
      )}
    </div>
  );
}
