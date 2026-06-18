import { ReactNode, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useV5Signals } from '../../hooks/api/useV5Signals';
import { useUIStore } from '../../services/store';
import type { Side, V5Signal } from '../../types';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { IndicatorGauges } from '../shared/IndicatorGauges';
import { Aperture } from '../primitives/Aperture';
import { signalScore, blockReasonZh } from './_signal_helpers';
import { Term } from '../shared/Term';

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
  const passedAnd = signals.filter(s => s.should_trade === 1).length;
  const executed = signals.filter(s => s.executed === 1).length;

  return (
    <div className="px-8 py-7 pb-16 flex flex-col gap-7 max-w-[1400px]">
      <PageHead now={now} />

      <FilterStrip
        side={side}
        onSideChange={setSide}
        executedOnly={executedOnly}
        onExecutedOnlyChange={setExecutedOnly}
        scanned={signals.length}
        passedAnd={passedAnd}
        executed={executed}
        onRefresh={() => q.refetch()}
      />

      {q.isLoading && <LoadingSkeleton message="拉取最新信号中…" />}
      {q.isError && (
        <div className="border border-oxblood-soft bg-oxblood-soft px-4 py-3 font-mono text-[0.85rem] text-oxblood">
          数据获取失败:{(q.error as any)?.detail || (q.error as any)?.message}
        </div>
      )}
      {!q.isLoading && !q.isError && signals.length === 0 && <EmptyState />}

      <div className="flex flex-col gap-2">
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
      </div>
    </div>
  );
}

function PageHead({ now }: { now: Date }) {
  const t = now.toLocaleTimeString('zh-CN', { hour12: false });
  return (
    <header className="grid grid-cols-[1fr_auto] items-end gap-6 pb-4 border-b border-hairline-strong">
      <div className="flex items-center gap-4">
        <Aperture size={34} rotate className="text-brass" />
        <div>
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight">实时信号</h1>
          <p className="font-cn text-ivory-40 text-[0.85rem] mt-1.5">实时扫描流 · scanning at 10s cadence</p>
        </div>
      </div>
      <div className="text-right font-mono text-[0.72rem] text-ivory-40 leading-relaxed">
        <div className="tracking-wider2 uppercase">观测时间</div>
        <div><strong className="text-ivory font-medium">{t}</strong> · UTC+8</div>
        <div>next scan · <strong className="text-ivory font-medium">10s</strong></div>
      </div>
    </header>
  );
}

function FilterStrip({ side, onSideChange, executedOnly, onExecutedOnlyChange, scanned, passedAnd, executed, onRefresh }: {
  side: Side | 'ALL';
  onSideChange: (s: Side | 'ALL') => void;
  executedOnly: boolean;
  onExecutedOnlyChange: (b: boolean) => void;
  scanned: number;
  passedAnd: number;
  executed: number;
  onRefresh: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-8 gap-y-3 px-6 py-4 border border-hairline bg-gradient-to-b from-bg-base to-bg-surface">
      <FilterCell label="方向">
        <SidePicker value={side} onChange={onSideChange} />
      </FilterCell>
      <FilterCell label="已开仓">
        <label className="inline-flex items-center gap-2 font-mono text-[0.78rem] text-ivory-70 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={executedOnly}
            onChange={e => onExecutedOnlyChange(e.target.checked)}
            className="accent-brass"
          />
          仅已入场
        </label>
      </FilterCell>
      <FilterCell label="漏斗 · 当前窗口">
        <span className="font-mono text-[0.85rem] text-ivory-70 tabular-nums">
          {scanned} 扫到
          <span className="text-ivory-40 mx-2">→</span>
          <strong className="text-brass">{passedAnd}</strong> 通过 AND
          <span className="text-ivory-40 mx-2">→</span>
          <strong className="text-sage">{executed}</strong> 入场
        </span>
      </FilterCell>
      <button
        type="button"
        onClick={onRefresh}
        className="ml-auto font-mono text-[0.78rem] tracking-wider px-3 py-1.5 border border-hairline-strong text-ivory-70 hover:border-brass hover:text-brass uppercase"
      >
        ⟳ refresh
      </button>
    </div>
  );
}

function FilterCell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase">{label}</div>
      <div>{children}</div>
    </div>
  );
}

function SidePicker({ value, onChange }: { value: Side | 'ALL'; onChange: (s: Side | 'ALL') => void }) {
  const opts: { v: Side | 'ALL'; label: string }[] = [
    { v: 'ALL', label: '全部' },
    { v: 'LONG', label: '做多' },
    { v: 'SHORT', label: '做空' },
  ];
  return (
    <div className="inline-flex border border-hairline-strong">
      {opts.map(o => (
        <button
          key={o.v}
          type="button"
          onClick={() => onChange(o.v)}
          className={`font-mono text-[0.7rem] tracking-wider2 px-3 py-1 border-r border-hairline-strong last:border-r-0 uppercase ${
            value === o.v
              ? o.v === 'LONG' ? 'bg-sage-soft text-sage'
                : o.v === 'SHORT' ? 'bg-oxblood-soft text-oxblood'
                : 'bg-brass-soft text-brass'
              : 'text-ivory-70 hover:bg-white/[0.04]'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="py-14 text-center">
      <Aperture size={48} rotate="slow" className="text-ivory-25 mx-auto block mb-3" />
      <p className="font-body italic text-[0.85rem] text-ivory-40">等待行情出现 RSI/MACD 合谋信号…</p>
    </div>
  );
}

function SignalRow({ signal, isOpen, onToggle, onChart, onManual }: {
  signal: V5Signal;
  isOpen: boolean;
  onToggle: () => void;
  onChart: () => void;
  onManual: () => void;
}) {
  const sideCls = signal.side === 'LONG'
    ? 'text-sage border-sage bg-sage-soft'
    : signal.side === 'SHORT'
    ? 'text-oxblood border-oxblood bg-oxblood-soft'
    : 'text-ivory-40 border-hairline-strong bg-transparent';

  const deltaCls = signal.delta_15m_pct >= 0 ? 'text-sage' : 'text-oxblood';
  const accentBorder = signal.executed === 1
    ? 'before:bg-sage'
    : signal.should_trade === 1
    ? 'before:bg-brass'
    : 'before:bg-hairline';

  return (
    <article className={`bg-bg-base border border-hairline relative before:content-[''] before:absolute before:left-0 before:top-0 before:bottom-0 before:w-[3px] ${accentBorder}`}>
      <button
        type="button"
        onClick={onToggle}
        className="grid grid-cols-[180px_100px_1fr_auto_auto_auto] items-center gap-4 w-full text-left px-5 pl-7 py-3.5 hover:bg-brass/[0.04]"
      >
        <span className="font-display text-[1.3rem] leading-none text-ivory">{signal.symbol}</span>
        <span className={`inline-flex justify-center font-mono text-[0.7rem] tracking-wider2 px-2 py-0.5 border ${sideCls}`}>
          {signal.side ?? '—'}
        </span>
        <span className={`font-mono text-[0.85rem] tabular-nums ${deltaCls}`}>
          <Term k="ΔP15m">ΔP15m</Term>: {signal.delta_15m_pct >= 0 ? '+' : ''}{(signal.delta_15m_pct * 100).toFixed(2)}%
        </span>
        <span className="font-mono text-[0.78rem] text-ivory-70 tabular-nums">
          <span className="text-ivory-40 mr-1">score</span>
          {signalScore(signal)}
        </span>
        <span className="font-mono text-[0.78rem] text-ivory-40">
          {new Date(signal.created_at).toLocaleTimeString('zh-CN', { hour12: false })}
        </span>
        <span className="font-mono text-[0.75rem] text-brass tracking-wide">
          {isOpen ? '▾' : '▸'}
        </span>
      </button>
      {isOpen && (
        <div className="border-t border-hairline px-5 pl-7 py-4 flex flex-col gap-3.5">
          <IndicatorGauges
            rsi_15m={signal.rsi_15m}
            rsi_4h={signal.rsi_4h}
            macd_hist_15m={signal.macd_hist_15m}
            macd_hist_prev_15m={signal.macd_hist_prev_15m}
            atr_15m={signal.atr_15m}
          />
          {signal.block_reason && (
            <div className="font-mono text-[0.85rem] text-brass">
              ▌ 拦截:{blockReasonZh(signal.block_reason)}
            </div>
          )}
          {signal.ai_reasoning && (
            <div className="font-body italic text-[0.85rem] text-ivory-70 leading-relaxed">
              <span className="font-mono not-italic text-brass mr-2 tracking-wider2 text-[0.65rem] uppercase">AI</span>
              {signal.ai_reasoning}
            </div>
          )}
          <div className="flex gap-3 pt-2 border-t border-hairline">
            <ActionBtn onClick={onChart} glyph="⊕" label="查看图表" />
            <ActionBtn onClick={onManual} glyph="▶" label="此参数模拟开单" tone="brass" />
          </div>
        </div>
      )}
    </article>
  );
}

function ActionBtn({ onClick, glyph, label, tone = '中性' }: { onClick: () => void; glyph: string; label: string; tone?: '中性' | 'brass' }) {
  const cls = tone === 'brass'
    ? 'border-brass-soft text-brass hover:border-brass hover:bg-brass-soft'
    : 'border-hairline-strong text-ivory-70 hover:border-brass hover:text-brass';
  return (
    <button
      type="button"
      onClick={onClick}
      className={`font-mono text-[0.78rem] tracking-wider px-3.5 py-1.5 border bg-transparent flex items-center gap-2 uppercase transition-all duration-200 ${cls}`}
    >
      <span className="text-brass">{glyph}</span>
      {label}
    </button>
  );
}
