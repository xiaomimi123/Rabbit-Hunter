import { useState } from 'react';
import { useUIStore } from '../../services/store';
import { useV5Klines } from '../../hooks/api/useV5Klines';
import { useV5FundingStatus } from '../../hooks/api/useV5Funding';
import { useV5Signals } from '../../hooks/api/useV5Signals';
import { useV5SymbolEvents } from '../../hooks/api/useV5SymbolEvents';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { Card } from '../primitives-v3/Card';
import { SegmentButton } from '../primitives-v3/SegmentButton';
import { StatusPill } from '../primitives-v3/StatusPill';
import { IndicatorOverlayChart } from '../shared/IndicatorOverlayChart';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { cn } from '../primitives-v3/cn';
import type { Interval } from '../../types';

export function MarketPage() {
  const selectedSymbol = useUIStore(s => s.selectedSymbol);
  const setKlineInterval = useUIStore(s => s.setKlineInterval);
  const interval = useUIStore(s => s.klineInterval);
  const klines = useV5Klines(selectedSymbol, interval, 200);
  const events = useV5SymbolEvents(selectedSymbol, 50);
  const funding = useV5FundingStatus();
  const signals = useV5Signals(20, { side: null, showExecutedOnly: false });

  // 后端 symbol 可能是 'BTCUSDT' 无斜杠,前端 selectedSymbol 带斜杠 'BTC/USDT'。
  // 归一化后再比对。
  const normalize = (s: string | null | undefined) => (s ?? '').replace(/\//g, '').toUpperCase();
  const target = normalize(selectedSymbol);
  const symbolFunding = funding.data?.data?.find(f => normalize(f.symbol) === target);
  const symbolSignals = (signals.data?.data ?? [])
    .filter(s => normalize(s.symbol) === target)
    .slice(0, 5);

  return (
    <div className="space-y-6">
      <SectionTitle
        title="市场分析"
        subtitle="行情、资金费率拥挤度、本币最近信号"
      />

      <div className="grid gap-6 xl:grid-cols-[1.35fr_1fr]">
        <Card title={selectedSymbol} subtitle={`${interval} K 线 · 指标叠加`}>
          {klines.isLoading || events.isLoading ? (
            <LoadingSkeleton message="拉取 K 线…" />
          ) : (klines.data?.klines.length ?? 0) === 0 ? (
            <div className="py-10 text-center text-sm text-zinc-500">无 K 线</div>
          ) : (
            <IndicatorOverlayChart
              klines={klines.data?.klines ?? []}
              events={events.data?.events ?? []}
              interval={interval}
              onIntervalChange={(i: Interval) => setKlineInterval(i)}
              currentPrice={klines.data?.klines.at(-1)?.close ?? null}
            />
          )}
        </Card>

        <div className="space-y-6">
          <Card title="资金费率拥挤度" subtitle={symbolFunding ? `${selectedSymbol}` : '—'}>
            {symbolFunding ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <Metric label="当前费率" value={`${(symbolFunding.current_funding_rate * 100).toFixed(4)}%`} />
                  <Metric label="z-score 30d" value={(symbolFunding.zscore_30d ?? 0).toFixed(2)} tone={Math.abs(symbolFunding.zscore_30d ?? 0) >= 2 ? 'rose' : 'zinc'} />
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">拥挤状态</div>
                  <StatusPill tone={
                    symbolFunding.extreme_direction === 'long_crowded' ? 'rose' :
                    symbolFunding.extreme_direction === 'short_crowded' ? 'emerald' :
                    'zinc'
                  }>
                    {symbolFunding.extreme_direction === 'long_crowded' ? '多头拥挤'
                      : symbolFunding.extreme_direction === 'short_crowded' ? '空头拥挤'
                      : '中性'}
                  </StatusPill>
                </div>
                <div className="text-xs text-zinc-500">
                  样本 n={symbolFunding.sample_size_30d} · 极端阈值 |z|≥2
                </div>
              </div>
            ) : (
              <div className="py-6 text-center text-sm text-zinc-500">{selectedSymbol} 无 funding 数据</div>
            )}
          </Card>

          <Card title="本币最近信号" subtitle={`最近 ${symbolSignals.length} 条`}>
            {symbolSignals.length === 0 ? (
              <div className="py-6 text-center text-sm text-zinc-500">{selectedSymbol} 无信号</div>
            ) : (
              <div className="space-y-2">
                {symbolSignals.map(s => (
                  <div key={s.id} className="flex items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-950/60 px-3 py-2">
                    <span className="font-mono text-xs text-zinc-400">{new Date(s.created_at).toLocaleTimeString('zh-CN', { hour12: false })}</span>
                    <StatusPill tone={s.side === 'LONG' ? 'emerald' : s.side === 'SHORT' ? 'rose' : 'zinc'}>{s.side ?? '—'}</StatusPill>
                    <span className={cn('font-mono text-xs tabular-nums ml-auto', s.delta_15m_pct >= 0 ? 'text-emerald-300' : 'text-rose-300')}>
                      {(s.delta_15m_pct * 100).toFixed(2)}%
                    </span>
                    {s.executed === 1 && <StatusPill tone="emerald">已入仓</StatusPill>}
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'emerald' | 'rose' | 'zinc' }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={cn('mt-1 font-mono text-lg font-semibold tabular-nums',
        tone === 'emerald' && 'text-emerald-300',
        tone === 'rose' && 'text-rose-300',
        (!tone || tone === 'zinc') && 'text-zinc-100',
      )}>{value}</div>
    </div>
  );
}
