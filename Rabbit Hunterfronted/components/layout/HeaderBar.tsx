import { RefreshCw, Wifi, WifiOff } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useUIStore } from '../../services/store';
import { useV5Klines } from '../../hooks/api/useV5Klines';
import { ConstitutionStrip } from './ConstitutionStrip';
import { cn } from '../primitives-v3/cn';

const SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'DOGE/USDT'];
const SYMBOL_AWARE_ROUTES = ['/dashboard', '/portfolio', '/market', '/diagnostics', '/chart'];

// 路径 → 标题 + 副标
const ROUTE_TITLES: Record<string, [string, string]> = {
  '/overview':    ['总览',       '实时 · OKX 永续 · 17 标的池'],
  '/market':      ['市场数据',   '4H · MACD 反转信号监控'],
  '/learning':    ['AI 学习',    '反思闭环 · 决策归因'],
  '/settings':    ['设置',       '接入 · 风控 · 模式'],
  '/dashboard':   ['中控仪表',   'V2 风控宪法实时面板'],
  '/portfolio':   ['投资组合',   '持仓 / 历史 / 收益分析'],
  '/history':     ['交易历史',   '本地交易记录与信号扫描'],
  '/backtest':    ['策略验证',   'M6 walk-forward 回测'],
  '/knowledge':   ['知识层',     'M9 候选规则 / 书籍'],
  '/audit':       ['反思审计',   '平仓后 LLM 反思'],
  '/diagnostics': ['AI 诊断',    'AI 决策日志与置信度'],
  '/reliability': ['执行可靠性', '挂单 / 滑点 / 网络'],
  '/collect':     ['数据采集',   'OKX 行情 / 资金费率'],
  '/manual':      ['手动开单',   'paper-trade 3 步向导'],
  '/glossary':    ['术语词典',   '系统专有词解释'],
};

interface Props {
  wsConnected: boolean;
}

export function HeaderBar({ wsConnected }: Props) {
  const selectedSymbol = useUIStore(s => s.selectedSymbol);
  const setSelectedSymbol = useUIStore(s => s.setSelectedSymbol);
  const location = useLocation();
  const symbolAware = SYMBOL_AWARE_ROUTES.some(p => location.pathname.startsWith(p));
  const klines = useV5Klines(symbolAware ? selectedSymbol : null, '15m', 10);
  const qc = useQueryClient();

  const lastBar = klines.data?.klines.at(-1);
  const prevBar = klines.data?.klines.at(-2);
  const lastPrice = lastBar?.close ?? 0;
  const pct = (lastBar && prevBar)
    ? ((lastBar.close - prevBar.close) / prevBar.close) * 100
    : 0;

  // 找匹配前缀的标题
  const [title, crumb] = (() => {
    for (const [path, t] of Object.entries(ROUTE_TITLES)) {
      if (location.pathname.startsWith(path)) return t;
    }
    return ['仪表盘', ''];
  })();

  return (
    <header className="sticky top-0 z-20 h-[54px] border-b border-line-soft bg-ink/90 px-6 backdrop-blur-md flex items-center justify-between">
      {/* 左:页面标题 + 副标 */}
      <div className="flex items-center gap-5 min-w-0">
        <div className="min-w-0">
          <h1 className="text-base font-semibold text-v3text truncate">{title}</h1>
          {crumb && (
            <div className="text-[11px] tracking-[0.04em] text-v3faint font-mono mt-px truncate">
              {crumb}
            </div>
          )}
        </div>

        {/* symbol-aware 路由才显示价格 */}
        {symbolAware && lastPrice > 0 && (
          <>
            <select
              value={selectedSymbol}
              onChange={(e) => setSelectedSymbol(e.target.value)}
              className="rounded-md border border-line bg-panel2 px-2.5 py-1 text-[12px] font-mono text-v3text outline-none focus:border-amber transition"
            >
              {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <span className="font-mono text-sm text-v3text">
              {lastPrice.toFixed(lastPrice >= 1 ? 2 : 6)}
            </span>
            <span className={cn('font-mono text-xs', pct >= 0 ? 'text-gain' : 'text-loss')}>
              {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
            </span>
          </>
        )}
      </div>

      {/* 右:风控宪法签名条 + WS + 刷新 */}
      <div className="flex items-center gap-4">
        <ConstitutionStrip />
        <div
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px]',
            wsConnected
              ? 'border-gain/40 bg-gain/10 text-gain'
              : 'border-loss/40 bg-loss/10 text-loss',
          )}
          title={wsConnected ? 'WebSocket 已连接' : 'WebSocket 离线'}
        >
          {wsConnected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
          {wsConnected ? 'WS' : 'OFF'}
        </div>
        <button
          type="button"
          onClick={() => qc.invalidateQueries()}
          title="刷新所有数据"
          className="rounded-md border border-line p-1.5 text-v3muted transition hover:border-amber hover:text-amber"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}
