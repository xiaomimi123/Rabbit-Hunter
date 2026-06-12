import React from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useV5Klines } from '../../hooks/api/useV5Klines';
import { useV5SymbolEvents } from '../../hooks/api/useV5SymbolEvents';
import { useUIStore } from '../../services/store';
import { Card } from '../primitives/Card';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { IndicatorOverlayChart } from '../shared/IndicatorOverlayChart';
import type { Interval } from '../../types';

export function V5ChartPage() {
  const { symbol: encoded } = useParams();
  const [search] = useSearchParams();
  const decoded = (encoded || '');
  const interval = useUIStore(s => s.klineInterval);
  const setInterval = useUIStore(s => s.setKlineInterval);

  const klines = useV5Klines(decoded, interval, 200);
  const events = useV5SymbolEvents(decoded, 50);
  const eventId = search.get('eventId');

  return (
    <div className="space-y-4">
      <Card
        title={
          <div className="flex items-baseline gap-3">
            <span className="text-base font-medium">{decoded || '—'}</span>
            <span className="font-mono text-xs text-white/50">
              {klines.data?.klines.at(-1)
                ? `现价 $${klines.data.klines.at(-1)!.close.toFixed(4)}`
                : '—'}
            </span>
          </div>
        }
        actions={
          eventId && <span className="text-xs text-accent-info">已定位事件 #{eventId}</span>
        }
      >
        {klines.isLoading || events.isLoading ? (
          <LoadingSkeleton rows={8} />
        ) : klines.isError ? (
          <div className="text-accent-short text-sm">K 线拉取失败:{(klines.error as any)?.detail}</div>
        ) : klines.data?.klines.length === 0 ? (
          <div className="py-8 text-center text-white/40">等待 K 线数据...</div>
        ) : (
          <IndicatorOverlayChart
            klines={klines.data?.klines ?? []}
            events={events.data?.events ?? []}
            interval={interval}
            onIntervalChange={(i: Interval) => setInterval(i)}
            currentPrice={klines.data?.klines.at(-1)?.close ?? null}
          />
        )}
      </Card>
    </div>
  );
}
