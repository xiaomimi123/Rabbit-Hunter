import { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity, Filter, RefreshCw, TrendingUp, TrendingDown, Check, X, AlertCircle,
  ChevronDown, ChevronRight, LineChart as LineChartIcon, Hand,
} from 'lucide-react';
import { useV5Signals } from '../../hooks/api/useV5Signals';
import { useUIStore } from '../../services/store';
import type { Side, V5Signal } from '../../types';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { MetricCard } from '../primitives-v3/MetricCard';
import { Card } from '../primitives-v3/Card';
import { cn } from '../primitives-v3/cn';
import { signalScore, blockReasonZh } from './_signal_helpers';

export function V5SignalsPage() {
  const [side, setSide] = useState<Side | 'ALL'>('ALL');
  const [executedOnly, setExecutedOnly] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const filter = {
    side: side === 'ALL' ? null : side,
    showExecutedOnly: executedOnly,
  };
  const q = useV5Signals(50, filter);
  const navigate = useNavigate();
  const expanded = useUIStore(s => s.expandedSignalIds);
  const toggle = useUIStore(s => s.toggleSignalExpanded);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const signals = q.data?.data ?? [];
  const passedAnd = useMemo(() => signals.filter(s => s.should_trade === 1).length, [signals]);
  const executedN = useMemo(() => signals.filter(s => s.executed === 1).length, [signals]);
  const rejectedAi = useMemo(() => signals.filter(s => s.block_reason === 'AI_REJECTED').length, [signals]);
  const longCount = useMemo(() => signals.filter(s => s.side === 'LONG').length, [signals]);
  const shortCount = useMemo(() => signals.filter(s => s.side === 'SHORT').length, [signals]);

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-6 space-y-6">
      <SectionTitle
        title="实时信号"
        subtitle={`扫描节拍 10s · ${now.toLocaleTimeString('zh-CN', { hour12: false })}`}
        action={
          <button
            type="button"
            onClick={() => q.refetch()}
            className="inline-flex items-center gap-2 rounded-full border border-zinc-700 bg-zinc-900/70 px-3 py-1.5 text-xs text-zinc-300 transition hover:border-indigo-500 hover:text-indigo-200"
          >
            <RefreshCw className="h-3 w-3" />
            刷新
          </button>
        }
      />

      {/* Top metrics */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="窗口扫到"
          value={String(signals.length)}
          hint={`做多 ${longCount} · 做空 ${shortCount}`}
        />
        <MetricCard
          label="合谋通过"
          value={String(passedAnd)}
          hint={signals.length ? `${Math.round(passedAnd * 100 / signals.length)}% 通过率` : '—'}
          trend={passedAnd > 0 ? 'up' : 'neutral'}
        />
        <MetricCard
          label="AI 拒"
          value={String(rejectedAi)}
          hint={passedAnd ? `${Math.round(rejectedAi * 100 / Math.max(passedAnd, 1))}% / 通过` : '—'}
          trend={rejectedAi > 0 ? 'down' : 'neutral'}
        />
        <MetricCard
          label="入仓"
          value={String(executedN)}
          hint="进入 paper trades"
          trend={executedN > 0 ? 'up' : 'neutral'}
        />
      </div>

      {/* Filter strip */}
      <Card className="!p-3" bodyClassName="flex flex-wrap items-center gap-3">
        <Filter className="h-4 w-4 text-zinc-500 ml-1" />
        <span className="text-xs text-zinc-500">方向</span>
        <div className="flex rounded-full bg-zinc-900 p-1">
          {(['ALL', 'LONG', 'SHORT'] as const).map(opt => (
            <button
              key={opt}
              onClick={() => setSide(opt as Side | 'ALL')}
              className={cn(
                'rounded-full px-3 py-1 text-xs transition',
                side === opt
                  ? opt === 'LONG'
                    ? 'bg-emerald-500/15 text-emerald-300'
                    : opt === 'SHORT'
                    ? 'bg-rose-500/15 text-rose-300'
                    : 'bg-indigo-500/15 text-indigo-300'
                  : 'text-zinc-400 hover:text-zinc-200',
              )}
            >
              {opt === 'ALL' ? '全部' : opt === 'LONG' ? '做多' : '做空'}
            </button>
          ))}
        </div>
        <label className="ml-2 flex items-center gap-2 text-xs text-zinc-400">
          <input
            type="checkbox"
            checked={executedOnly}
            onChange={e => setExecutedOnly(e.target.checked)}
            className="accent-indigo-500"
          />
          仅已入仓
        </label>
      </Card>

      {/* Signal list */}
      {q.isLoading && <LoadingSkeleton message="拉取最新信号中…" />}
      {q.isError && (
        <Card>
          <div className="flex items-center gap-2 text-rose-300">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm">数据获取失败:{(q.error as any)?.detail || (q.error as any)?.message}</span>
          </div>
        </Card>
      )}
      {!q.isLoading && !q.isError && signals.length === 0 && (
        <Card>
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-zinc-800">
              <Activity className="h-5 w-5 text-zinc-500" />
            </div>
            <div className="text-sm font-medium text-zinc-300">等待行情</div>
            <div className="mt-1 text-xs text-zinc-500">出现 RSI/MACD 合谋信号时会在此显示</div>
          </div>
        </Card>
      )}

      {signals.length > 0 && (
        <Card title="信号流" subtitle="点击行查看详细指标 / AI 推理" className="!p-0" bodyClassName="!p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                  <th className="py-3 pl-5 pr-2 font-medium w-10"></th>
                  <th className="py-3 px-2 font-medium">时间</th>
                  <th className="py-3 px-2 font-medium">币种</th>
                  <th className="py-3 px-2 font-medium">方向</th>
                  <th className="py-3 px-2 font-medium text-right">ΔP15m</th>
                  <th className="py-3 px-2 font-medium">RSI 15m</th>
                  <th className="py-3 px-2 font-medium text-right">MACD hist</th>
                  <th className="py-3 px-2 font-medium text-right">score</th>
                  <th className="py-3 px-2 font-medium">状态</th>
                  <th className="py-3 pl-2 pr-5 font-medium w-10"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {signals.map(s => (
                  <SignalRow
                    key={s.id}
                    signal={s}
                    isOpen={expanded.has(s.id)}
                    onToggle={() => toggle(s.id)}
                    onChart={() => navigate(`/v5/chart/${s.symbol}`)}
                    onManual={() => navigate(`/v5/manual?symbol=${encodeURIComponent(s.symbol)}&side=${s.side ?? ''}`)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

/* ─────────────── Signal row ─────────────── */

function SignalRow({
  signal, isOpen, onToggle, onChart, onManual,
}: {
  signal: V5Signal;
  isOpen: boolean;
  onToggle: () => void;
  onChart: () => void;
  onManual: () => void;
}) {
  const sideBadge = signal.side === 'LONG'
    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
    : signal.side === 'SHORT'
    ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
    : 'bg-zinc-800 text-zinc-500 border-zinc-700';

  const deltaPct = signal.delta_15m_pct * 100;
  const deltaClass = deltaPct > 0 ? 'text-emerald-400' : deltaPct < 0 ? 'text-rose-400' : 'text-zinc-400';

  const score = signalScore(signal);

  return (
    <>
      <tr
        onClick={onToggle}
        className={cn(
          'cursor-pointer transition-colors hover:bg-zinc-900/40',
          signal.executed === 1 && 'bg-emerald-500/[0.04]',
          signal.block_reason === 'AI_REJECTED' && 'bg-rose-500/[0.04]',
        )}
      >
        <td className="py-2.5 pl-5 pr-2 text-zinc-500">
          {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </td>
        <td className="py-2.5 px-2 font-mono text-xs text-zinc-400 whitespace-nowrap">
          {new Date(signal.created_at).toLocaleTimeString('zh-CN', { hour12: false })}
        </td>
        <td className="py-2.5 px-2 font-mono text-sm font-medium text-zinc-100 whitespace-nowrap">
          {signal.symbol}
        </td>
        <td className="py-2.5 px-2">
          <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium', sideBadge)}>
            {signal.side === 'LONG' ? <TrendingUp className="h-2.5 w-2.5" /> : signal.side === 'SHORT' ? <TrendingDown className="h-2.5 w-2.5" /> : null}
            {signal.side ?? '—'}
          </span>
        </td>
        <td className={cn('py-2.5 px-2 text-right font-mono tabular-nums text-sm', deltaClass)}>
          {deltaPct > 0 ? '+' : ''}{deltaPct.toFixed(2)}%
        </td>
        <td className="py-2.5 px-2 min-w-[140px]">
          <RsiBar value={signal.rsi_15m} />
        </td>
        <td className="py-2.5 px-2 text-right font-mono tabular-nums text-xs">
          <span className={signal.macd_hist_15m >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
            {signal.macd_hist_15m.toFixed(4)}
          </span>
        </td>
        <td className="py-2.5 px-2 text-right">
          <ScorePill score={score} />
        </td>
        <td className="py-2.5 px-2">
          <StatusBadge signal={signal} />
        </td>
        <td className="py-2.5 pl-2 pr-5">
          <div className="flex justify-end gap-1" onClick={e => e.stopPropagation()}>
            <button
              onClick={onChart}
              title="查看图表"
              className="rounded-lg border border-zinc-700 p-1.5 text-zinc-400 transition hover:border-indigo-500 hover:text-indigo-300"
            >
              <LineChartIcon className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={onManual}
              title="此参数模拟开单"
              className="rounded-lg border border-zinc-700 p-1.5 text-zinc-400 transition hover:border-amber-500 hover:text-amber-300"
            >
              <Hand className="h-3.5 w-3.5" />
            </button>
          </div>
        </td>
      </tr>
      {isOpen && (
        <tr className="bg-zinc-950/60">
          <td colSpan={10} className="py-4 px-5">
            <SignalDetail signal={signal} />
          </td>
        </tr>
      )}
    </>
  );
}

/* ─────────────── Visual primitives ─────────────── */

function RsiBar({ value }: { value: number }) {
  // RSI 范围 0-100,绿区 < 30 (oversold) 红区 > 70 (overbought)
  const v = Math.max(0, Math.min(100, value));
  const isOversold = v <= 30;
  const isOverbought = v >= 70;
  const colorClass = isOverbought
    ? 'bg-rose-500'
    : isOversold
    ? 'bg-emerald-500'
    : 'bg-indigo-500';
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-900">
        <div
          className={cn('absolute inset-y-0 left-0 rounded-full transition-all', colorClass)}
          style={{ width: `${v}%` }}
        />
        {/* 30 / 70 markers */}
        <div className="absolute inset-y-0 w-px bg-zinc-700" style={{ left: '30%' }} />
        <div className="absolute inset-y-0 w-px bg-zinc-700" style={{ left: '70%' }} />
      </div>
      <span className={cn(
        'font-mono tabular-nums text-xs w-9 text-right',
        isOverbought && 'text-rose-400',
        isOversold && 'text-emerald-400',
        !isOverbought && !isOversold && 'text-zinc-400',
      )}>
        {v.toFixed(1)}
      </span>
    </div>
  );
}

function ScorePill({ score }: { score: number }) {
  let cls = 'bg-zinc-800 text-zinc-400';
  if (score >= 80) cls = 'bg-emerald-500/15 text-emerald-300';
  else if (score >= 60) cls = 'bg-amber-500/15 text-amber-300';
  else if (score >= 40) cls = 'bg-zinc-700/40 text-zinc-300';
  return (
    <span className={cn('inline-block rounded-full px-2 py-0.5 font-mono tabular-nums text-xs', cls)}>
      {score}
    </span>
  );
}

function StatusBadge({ signal }: { signal: V5Signal }) {
  if (signal.executed === 1) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300">
        <Check className="h-2.5 w-2.5" />
        已入仓
      </span>
    );
  }
  if (signal.block_reason) {
    const isAi = signal.block_reason.startsWith('AI_');
    return (
      <span className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px]',
        isAi ? 'bg-rose-500/15 text-rose-300' : 'bg-amber-500/15 text-amber-300',
      )}>
        <X className="h-2.5 w-2.5" />
        <span className="max-w-[100px] truncate" title={signal.block_reason}>
          {blockReasonZh(signal.block_reason)}
        </span>
      </span>
    );
  }
  if (signal.should_trade === 1) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] text-indigo-300">
        通过 AND
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-500">
      未触发
    </span>
  );
}

function SignalDetail({ signal }: { signal: V5Signal }) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div className="space-y-3">
        <div className="text-xs uppercase tracking-[0.18em] text-zinc-500">指标详情</div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <DetailItem label="RSI 4h" value={signal.rsi_4h?.toFixed(1) ?? '—'} />
          <DetailItem
            label="MACD hist prev"
            value={signal.macd_hist_prev_15m.toFixed(4)}
          />
          <DetailItem
            label="MACD hist 4h"
            value={signal.macd_hist_4h?.toFixed(4) ?? '—'}
          />
          <DetailItem label="ATR 15m" value={signal.atr_15m.toFixed(4)} />
          <DetailItem
            label="入场价"
            value={signal.current_price.toFixed(4)}
            mono
          />
          <DetailItem
            label="24h 成交"
            value={`${(signal.volume_24h_usdt / 1_000_000).toFixed(0)} M USDT`}
          />
        </div>
      </div>
      <div className="space-y-3">
        {signal.reasoning && (
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-zinc-500 mb-1.5">规则推理</div>
            <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-sm text-zinc-300">
              {signal.reasoning}
            </div>
          </div>
        )}
        {signal.ai_reasoning && (
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-zinc-500 mb-1.5">
              AI 推理 {signal.ai_confidence != null && (
                <span className="ml-2 text-indigo-300 normal-case">
                  置信 {Math.round(signal.ai_confidence * 100)}%
                </span>
              )}
            </div>
            <div className="rounded-2xl border border-indigo-500/20 bg-indigo-500/[0.04] px-3 py-2 text-sm text-zinc-300">
              {signal.ai_reasoning}
            </div>
          </div>
        )}
        {signal.executed === 1 && signal.entry_price && (
          <div className="grid grid-cols-3 gap-2">
            <PriceCard label="入场" price={signal.entry_price} />
            {signal.sl_price && <PriceCard label="止损" price={signal.sl_price} className="text-rose-300" />}
            {signal.tp_price && <PriceCard label="止盈" price={signal.tp_price} className="text-emerald-300" />}
          </div>
        )}
      </div>
    </div>
  );
}

function DetailItem({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={cn('mt-0.5 text-sm font-medium tabular-nums text-zinc-100', mono && 'font-mono')}>
        {value}
      </div>
    </div>
  );
}

function PriceCard({ label, price, className }: { label: string; price: number; className?: string }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={cn('mt-0.5 font-mono tabular-nums text-sm', className ?? 'text-zinc-100')}>
        {price.toFixed(4)}
      </div>
    </div>
  );
}
