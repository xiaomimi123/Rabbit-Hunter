import { useEffect, useState } from 'react';
import { RefreshCw, Wifi, WifiOff } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useUIStore } from '../../services/store';
import { useSystemMode } from '../../hooks/useSystemMode';
import { useV5Klines } from '../../hooks/api/useV5Klines';
import { cn } from '../primitives-v3/cn';

const SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'DOGE/USDT'];

// 只有跟当前 symbol 强相关的页面才展示左侧 symbol 选择 + 价格 + 15m。
// 其他页面(history/backtest/audit/knowledge/reliability/settings)隐藏左半部分。
const SYMBOL_AWARE_ROUTES = ['/dashboard', '/portfolio', '/market', '/diagnostics', '/chart'];

interface Props {
  wsConnected: boolean;
}

export function HeaderBar({ wsConnected }: Props) {
  const { mode } = useSystemMode();
  const provider = useUIStore(s => s.effectiveAiProvider);
  const selectedSymbol = useUIStore(s => s.selectedSymbol);
  const setSelectedSymbol = useUIStore(s => s.setSelectedSymbol);
  const location = useLocation();
  const symbolAware = SYMBOL_AWARE_ROUTES.some(p => location.pathname.startsWith(p));
  // 仅在 symbol-aware 路由才拉 K 线,省去无意义请求。
  const klines = useV5Klines(symbolAware ? selectedSymbol : null, '15m', 10);
  const qc = useQueryClient();
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setTick(x => x + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const lastBar = klines.data?.klines.at(-1);
  const prevBar = klines.data?.klines.at(-2);
  const lastPrice = lastBar?.close ?? 0;
  const pct = (lastBar && prevBar)
    ? ((lastBar.close - prevBar.close) / prevBar.close) * 100
    : 0;

  return (
    <header className="sticky top-0 z-20 border-b border-hairline bg-bg-base/90 px-6 py-4 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-4">
        {symbolAware ? (
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={selectedSymbol}
            onChange={(e) => setSelectedSymbol(e.target.value)}
            className="rounded-sm border border-hairline-strong bg-bg-deep px-4 py-2 text-sm font-mono text-ivory outline-none focus:border-brass transition"
          >
            {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <div className="rounded-sm border border-hairline bg-bg-surface px-4 py-2">
            <div className="text-[10px] uppercase tracking-wider2 text-ivory-40">当前价格</div>
            <div className="font-mono text-lg font-semibold text-ivory tabular-nums">
              {lastPrice > 0 ? lastPrice.toFixed(lastPrice >= 1 ? 2 : 6) : '—'}
            </div>
          </div>
          <div
            className={cn(
              'rounded-sm border px-4 py-2',
              pct >= 0
                ? 'border-sage/40 bg-sage-soft text-sage'
                : 'border-oxblood/40 bg-oxblood-soft text-oxblood',
            )}
          >
            <div className="text-[10px] uppercase tracking-wider2 text-ivory-40">15m</div>
            <div className="font-mono text-lg font-semibold tabular-nums">
              {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
            </div>
          </div>
        </div>
        ) : <div />}

        <div className="flex flex-wrap items-center gap-3">
          {mode && (
            <div className="rounded-sm border border-hairline bg-bg-surface px-4 py-2">
              <div className="text-[10px] uppercase tracking-wider2 text-ivory-40">系统模式</div>
              <div className={cn(
                'font-mono font-medium',
                mode === 'LIVE' ? 'text-oxblood' : 'text-brass',
              )}>
                {mode === 'LIVE' ? '● LIVE' : '◐ SHADOW'}
              </div>
            </div>
          )}
          {provider && (
            <div className="rounded-sm border border-hairline bg-bg-surface px-4 py-2">
              <div className="text-[10px] uppercase tracking-wider2 text-ivory-40">AI 提供方</div>
              <div className="font-mono font-medium text-ink">{provider}</div>
            </div>
          )}
          <div
            className={cn(
              'rounded-sm border px-4 py-2',
              wsConnected
                ? 'border-sage/40 bg-sage-soft'
                : 'border-oxblood/40 bg-oxblood-soft',
            )}
            title={wsConnected ? 'WebSocket 已连接' : 'WebSocket 离线'}
          >
            <div className="text-[10px] uppercase tracking-wider2 text-ivory-40">WS</div>
            <div className={cn(
              'font-mono font-medium inline-flex items-center gap-1.5',
              wsConnected ? 'text-sage' : 'text-oxblood',
            )}>
              {wsConnected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
              {wsConnected ? '在线' : '离线'}
            </div>
          </div>
          <button
            type="button"
            onClick={() => qc.invalidateQueries()}
            title="刷新所有数据"
            className="rounded-sm border border-hairline-strong p-2 text-ivory-70 transition hover:border-brass hover:text-ivory"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
