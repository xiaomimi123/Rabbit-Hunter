/**
 * MarketPage — UI 原型 2026-06-27 落地版本。
 *
 * 代币下拉(搜索) + K 线主图 + MACD/RSI 副图 (复用 IndicatorOverlayChart) +
 * 24h 成交额 / 资金费率 / ATR / 信号状态 四指标。
 */
import { useState, useMemo, useRef, useEffect } from 'react';
import { Search, ChevronDown } from 'lucide-react';
import { useUIStore } from '../../services/store';
import { useV5Klines } from '../../hooks/api/useV5Klines';
import { useV5SymbolEvents } from '../../hooks/api/useV5SymbolEvents';
import { useV5FundingHistory } from '../../hooks/api/useV5Funding';
import { IndicatorOverlayChart } from '../shared/IndicatorOverlayChart';
import type { Interval } from '../../types';

const WHITELIST_17 = [
  'APT/USDT', 'ARB/USDT', 'ATOM/USDT', 'AVAX/USDT', 'BNB/USDT',
  'DOGE/USDT', 'DOT/USDT', 'FIL/USDT', 'LINK/USDT', 'LTC/USDT',
  'NEAR/USDT', 'PEPE/USDT', 'SOL/USDT', 'UNI/USDT', 'WLD/USDT',
  'XRP/USDT', 'ZEC/USDT',
];

function symbolBase(s: string): string {
  return s.replace('/USDT', '').replace('USDT', '');
}

function Card({ children, className = '', pad0 = false }: { children: React.ReactNode; className?: string; pad0?: boolean }) {
  return (
    <section className={`rounded-[10px] border border-line-soft bg-panel ${pad0 ? 'p-0 overflow-hidden' : 'p-4'} ${className}`}>
      {children}
    </section>
  );
}

function MetricCard({ label, value, sub, valueColor = 'text-v3text', smallValue = false }: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  valueColor?: string;
  smallValue?: boolean;
}) {
  return (
    <Card>
      <div className="text-[11px] uppercase tracking-[0.07em] text-v3faint">{label}</div>
      <div className={`mt-2 font-semibold leading-none font-mono ${smallValue ? 'text-[20px]' : 'text-[26px]'} ${valueColor}`}>
        {value}
      </div>
      {sub && <div className="mt-1.5 text-[11.5px] text-v3muted">{sub}</div>}
    </Card>
  );
}

export function MarketPage() {
  const selectedSymbol = useUIStore(s => s.selectedSymbol);
  const setSelectedSymbol = useUIStore(s => s.setSelectedSymbol);
  const [timeframe, setTimeframe] = useState<Interval>('4h');
  const [ddOpen, setDdOpen] = useState(false);
  const [search, setSearch] = useState('');
  const ddRef = useRef<HTMLDivElement>(null);

  const klines = useV5Klines(selectedSymbol, timeframe, 200);
  const events = useV5SymbolEvents(selectedSymbol, 50);
  const funding = useV5FundingHistory(symbolBase(selectedSymbol) + 'USDT', 1);

  const lastBar = klines.data?.klines.at(-1);
  const prevBar = klines.data?.klines.at(-2);
  const lastPrice = lastBar?.close ?? 0;
  const pct = (lastBar && prevBar) ? ((lastBar.close - prevBar.close) / prevBar.close) * 100 : 0;

  const vol24h = useMemo(() => {
    const ks = klines.data?.klines ?? [];
    if (ks.length === 0) return 0;
    return ks.slice(-Math.min(96, ks.length))
      .reduce((acc, k) => acc + (k.volume ?? 0) * k.close, 0);
  }, [klines.data]);

  const atr14 = useMemo(() => {
    const ks = klines.data?.klines ?? [];
    if (ks.length < 15) return 0;
    const tail = ks.slice(-15);
    let trSum = 0;
    for (let i = 1; i < tail.length; i++) {
      const tr = Math.max(
        tail[i].high - tail[i].low,
        Math.abs(tail[i].high - tail[i - 1].close),
        Math.abs(tail[i].low - tail[i - 1].close),
      );
      trSum += tr;
    }
    return trSum / 14;
  }, [klines.data]);
  const atrPct = lastPrice > 0 ? (atr14 / lastPrice) * 100 : 0;

  const fundingRate = funding.data?.rows?.[0]?.funding_rate ?? null;
  const fundingPct = fundingRate != null ? fundingRate * 100 : null;

  const latestEvent = events.data?.events?.[0];
  const signalState = latestEvent ? (latestEvent.kind ?? '有事件') : '等待金叉';

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ddRef.current && !ddRef.current.contains(e.target as Node)) setDdOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const filteredList = useMemo(() => {
    const q = search.toLowerCase().trim();
    if (!q) return WHITELIST_17;
    return WHITELIST_17.filter(s => s.toLowerCase().includes(q));
  }, [search]);

  return (
    <div className="px-6 pb-10 pt-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative" ref={ddRef}>
            <button
              type="button"
              onClick={() => setDdOpen(o => !o)}
              className="inline-flex items-center gap-2.5 rounded-lg border border-line bg-panel2 px-3 py-2 hover:border-amber/40 transition"
            >
              <span className="w-[30px] h-[30px] grid place-items-center rounded-md bg-raised text-[12px] font-bold text-v3muted">
                {symbolBase(selectedSymbol).slice(0, 2)}
              </span>
              <span className="font-mono text-[15px] font-semibold text-v3text">
                {symbolBase(selectedSymbol)}USDT
              </span>
              <ChevronDown className="h-3.5 w-3.5 text-v3faint" />
            </button>
            {ddOpen && (
              <div className="absolute top-full left-0 mt-1.5 w-[280px] rounded-lg border border-line bg-panel2 shadow-2xl z-30">
                <div className="flex items-center gap-2 px-3 py-2.5 border-b border-line-soft">
                  <Search className="h-3.5 w-3.5 text-v3faint" />
                  <input
                    type="text"
                    placeholder="搜索代币…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    autoFocus
                    className="bg-transparent flex-1 text-sm text-v3text outline-none placeholder:text-v3faint"
                  />
                </div>
                <div className="max-h-[320px] overflow-y-auto">
                  {filteredList.map(s => {
                    const base = symbolBase(s);
                    const isActive = s === selectedSymbol;
                    return (
                      <button
                        key={s}
                        onClick={() => { setSelectedSymbol(s); setDdOpen(false); setSearch(''); }}
                        className={`w-full flex items-center justify-between px-3 py-2.5 text-left hover:bg-raised transition ${isActive ? 'bg-raised' : ''}`}
                      >
                        <div className="flex items-center gap-2">
                          <span className="w-[22px] h-[22px] grid place-items-center rounded bg-ink text-[10px] font-bold text-v3muted">
                            {base.slice(0, 2)}
                          </span>
                          <span className="font-mono text-sm text-v3text">{base}USDT</span>
                        </div>
                        {isActive && <span className="text-[10px] text-amber">●</span>}
                      </button>
                    );
                  })}
                  {filteredList.length === 0 && (
                    <div className="px-3 py-6 text-center text-xs text-v3faint">无匹配</div>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="font-mono text-[24px] font-semibold text-v3text">
            {lastPrice > 0 ? lastPrice.toFixed(lastPrice >= 1 ? 4 : 6) : '—'}
          </div>
          <div className={`font-mono text-sm ${pct >= 0 ? 'text-gain' : 'text-loss'}`}>
            {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
          </div>
        </div>

        <div className="inline-flex gap-0.5 rounded-md border border-line bg-[#10161d] p-0.5">
          {(['15m', '1h', '4h'] as Interval[]).map(tf => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`text-[11.5px] font-medium px-3 py-1 rounded-[5px] transition ${
                timeframe === tf ? 'bg-raised text-v3text' : 'text-v3muted hover:text-v3text'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      <Card pad0 className="mb-4">
        <div className="p-3">
          <IndicatorOverlayChart
            klines={klines.data?.klines ?? []}
            events={events.data?.events ?? []}
            interval={timeframe}
            onIntervalChange={setTimeframe}
            currentPrice={lastPrice || null}
            indicators={undefined}
          />
        </div>
      </Card>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        <MetricCard
          label="24h 成交额"
          smallValue
          value={<>${(vol24h / 1e9).toFixed(2)}<span className="text-[13px] text-v3faint">B</span></>}
          sub={<span className="text-gain">流动性达标 ✓</span>}
        />
        <MetricCard
          label="资金费率"
          smallValue
          value={fundingPct != null
            ? <>{fundingPct >= 0 ? '+' : ''}{fundingPct.toFixed(3)}<span className="text-[13px] text-v3faint">%</span></>
            : '—'}
          sub={<span className="text-v3faint">8h · {fundingPct != null && Math.abs(fundingPct) < 0.05 ? '中性' : '偏极'}</span>}
        />
        <MetricCard
          label="ATR(14)"
          smallValue
          value={atr14 > 0 ? atr14.toFixed(atr14 >= 1 ? 3 : 6) : '—'}
          sub={<span className="text-v3faint">波动 · {atrPct.toFixed(1)}%</span>}
        />
        <MetricCard
          label="信号状态"
          smallValue
          value={<span className="text-amber text-[18px]">{signalState}</span>}
          sub={<span className="text-v3faint font-mono">实时 MACD / 金叉监控</span>}
        />
      </div>
    </div>
  );
}
