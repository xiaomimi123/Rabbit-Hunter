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
    <header className="sticky top-0 z-20 border-b border-zinc-800 bg-zinc-950/90 px-6 py-4 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-4">
        {symbolAware ? (
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={selectedSymbol}
            onChange={(e) => setSelectedSymbol(e.target.value)}
            className="rounded-2xl border border-zinc-700 bg-zinc-950 px-4 py-2 text-sm text-zinc-100 outline-none focus:border-indigo-500"
          >
            {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 px-4 py-2">
            <div className="text-xs text-zinc-500">当前价格</div>
            <div className="text-lg font-semibold text-zinc-50 tabular-nums">
              {lastPrice > 0 ? lastPrice.toFixed(lastPrice >= 1 ? 2 : 6) : '—'}
            </div>
          </div>
          <div
            className={cn(
              'rounded-2xl border px-4 py-2',
              pct >= 0
                ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300'
                : 'border-rose-500/20 bg-rose-500/10 text-rose-300',
            )}
          >
            <div className="text-xs text-zinc-500">15m</div>
            <div className="text-lg font-semibold tabular-nums">
              {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
            </div>
          </div>
        </div>
        ) : <div />}

        <div className="flex flex-wrap items-center gap-3">
          {mode && (
            <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 px-4 py-2">
              <div className="text-xs text-zinc-500">系统模式</div>
              <div className={cn(
                'font-medium',
                mode === 'LIVE' ? 'text-rose-300' : 'text-amber-300',
              )}>
                {mode === 'LIVE' ? '⬤ LIVE' : '◐ SHADOW'}
              </div>
            </div>
          )}
          {provider && (
            <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 px-4 py-2">
              <div className="text-xs text-zinc-500">AI 提供方</div>
              <div className="font-medium text-indigo-300">{provider}</div>
            </div>
          )}
          <div
            className={cn(
              'rounded-2xl border px-4 py-2',
              wsConnected
                ? 'border-emerald-500/20 bg-emerald-500/10'
                : 'border-rose-500/20 bg-rose-500/10',
            )}
            title={wsConnected ? 'WebSocket 已连接' : 'WebSocket 离线'}
          >
            <div className="text-xs text-zinc-500">WS</div>
            <div className={cn(
              'font-medium inline-flex items-center gap-1.5',
              wsConnected ? 'text-emerald-300' : 'text-rose-300',
            )}>
              {wsConnected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
              {wsConnected ? '在线' : '离线'}
            </div>
          </div>
          <button
            type="button"
            onClick={() => qc.invalidateQueries()}
            title="刷新所有数据"
            className="rounded-2xl border border-zinc-700 p-2 text-zinc-300 transition hover:border-indigo-500 hover:text-white"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
