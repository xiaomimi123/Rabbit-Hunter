import { ReactNode, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useV5ActivePositions, useV5ClosePosition } from '../../hooks/api/useV5ActivePositions';
import { ActivePositionCard } from '../shared/ActivePositionCard';
import { Modal } from '../primitives/Modal';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Aperture } from '../primitives/Aperture';
import type { V5Position } from '../../types';

const MAX_SLOTS = 3;

export function V5ActivePositionsPage() {
  const q = useV5ActivePositions();
  const close = useV5ClosePosition();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState<V5Position | null>(null);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const combined = q.data?.combined ?? [];
  const total = combined.length;
  const longCount = combined.filter(p => p.side === 'LONG').length;
  const shortCount = combined.filter(p => p.side === 'SHORT').length;
  const unrealized = combined.reduce((a, p) => a + (p.pnl_usdt ?? 0), 0);
  const unrealizedPct = combined.reduce((a, p) => a + (p.pnl_pct ?? 0), 0) / Math.max(1, total);
  const avgHold = combined.reduce((a, p) => {
    if (!p.entry_time) return a;
    return a + Math.round((Date.now() - new Date(p.entry_time).getTime()) / 60_000);
  }, 0) / Math.max(1, total);

  return (
    <div className="px-8 py-7 pb-16 flex flex-col gap-7 max-w-[1400px]">
      <PageHead now={now} />

      <CounterStrip
        total={total}
        longCount={longCount}
        shortCount={shortCount}
        unrealized={unrealized}
        unrealizedPct={unrealizedPct}
        avgHold={avgHold}
      />

      {q.isLoading && <LoadingSkeleton message="拉取活仓状态中…" />}

      <div className="flex flex-col gap-4">
        {combined.map(p => (
          <ActivePositionCard
            key={p.id}
            position={p}
            onClose={() => setConfirm(p)}
            onChart={() => navigate(`/v5/chart/${p.symbol}`)}
          />
        ))}
        {!q.isLoading && total === 0 && <EmptySlot index={1} />}
        {!q.isLoading && total < MAX_SLOTS && total > 0 && <EmptySlot index={total + 1} />}
      </div>

      <Modal open={!!confirm} onClose={() => setConfirm(null)} title="确认立即平仓">
        {confirm && (
          <div className="flex flex-col gap-4 font-cn">
            <div className="font-mono text-[0.85rem] text-ivory-70">
              {confirm.symbol} · {confirm.side} · 入场 {confirm.entry_price?.toFixed(4) ?? '—'}
            </div>
            <div className="font-mono text-[0.85rem]">
              当前 PnL:
              <span className={`ml-2 ${(confirm.pnl_pct ?? 0) >= 0 ? 'text-sage' : 'text-oxblood'}`}>
                {(confirm.pnl_pct ?? 0) >= 0 ? '+' : ''}{(confirm.pnl_pct ?? 0).toFixed(2)}%
                {' · '}
                {(confirm.pnl_usdt ?? 0) >= 0 ? '+' : ''}{(confirm.pnl_usdt ?? 0).toFixed(2)} USDT
              </span>
            </div>
            <div className="flex justify-end gap-3 pt-3 border-t border-hairline">
              <button
                type="button"
                onClick={() => setConfirm(null)}
                className="font-mono text-[0.78rem] tracking-wider px-4 py-2 border border-hairline-strong text-ivory-70 hover:border-ivory hover:text-ivory uppercase"
              >
                取消
              </button>
              <button
                type="button"
                disabled={close.isPending}
                onClick={async () => {
                  await close.mutateAsync({
                    id: confirm.id,
                    body: {
                      exit_price: confirm.entry_price ?? 0,
                      exit_reason: 'MANUAL_USER',
                    },
                  });
                  setConfirm(null);
                }}
                className="font-mono text-[0.78rem] tracking-wider px-4 py-2 border border-oxblood-soft bg-oxblood-soft text-oxblood hover:border-oxblood disabled:opacity-50 uppercase"
              >
                {close.isPending ? '平仓中…' : '确认平仓'}
              </button>
            </div>
          </div>
        )}
      </Modal>
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
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight">Active Positions</h1>
          <p className="font-cn text-ivory-40 text-[0.85rem] mt-1.5">实时持仓监控 · 5s 自动校准 · live</p>
        </div>
      </div>
      <div className="text-right font-mono text-[0.72rem] text-ivory-40 leading-relaxed">
        <div className="tracking-wider2 uppercase">Observation Time</div>
        <div><strong className="text-ivory font-medium">{t}</strong> · UTC+8</div>
        <div>next refresh · <strong className="text-ivory font-medium">5s</strong></div>
      </div>
    </header>
  );
}

function CounterStrip({ total, longCount, shortCount, unrealized, unrealizedPct, avgHold }: {
  total: number; longCount: number; shortCount: number;
  unrealized: number; unrealizedPct: number; avgHold: number;
}) {
  return (
    <div className="flex items-center gap-8 px-6 py-4 border border-hairline bg-gradient-to-b from-bg-base to-bg-surface">
      <Counter label="Occupied · slots">
        <span className="font-mono text-[1.5rem] text-ivory tabular-nums">{total}</span>
        <span className="font-mono text-[0.95rem] text-ivory-40"> / {MAX_SLOTS}</span>
        <span className="font-mono text-[0.78rem] text-ivory-40 ml-1.5 tracking-wide">slots used</span>
      </Counter>
      <Counter label="Distribution">
        <span className="inline-flex gap-1.5 items-center mr-3">
          {Array.from({ length: MAX_SLOTS }).map((_, i) => {
            let cls = 'bg-transparent';
            if (i < longCount) cls = 'bg-sage-soft border-sage';
            else if (i < longCount + shortCount) cls = 'bg-oxblood-soft border-oxblood';
            else cls = 'border-hairline-strong';
            return <span key={i} className={`w-3.5 h-3.5 inline-block border ${cls}`} />;
          })}
        </span>
        <span className="font-mono text-[0.78rem] text-ivory-40">{longCount} long · {shortCount} short · {MAX_SLOTS - total} idle</span>
      </Counter>
      <Counter label="Unrealized · net">
        <span className={`font-mono text-[1.5rem] tabular-nums ${unrealized >= 0 ? 'text-sage' : 'text-oxblood'}`}>
          {unrealized >= 0 ? '+' : ''}{unrealized.toFixed(2)}
        </span>
        <span className="font-mono text-[0.78rem] text-ivory-40 ml-2 tracking-wide">
          USDT ({unrealizedPct >= 0 ? '+' : ''}{unrealizedPct.toFixed(2)}%)
        </span>
      </Counter>
      <Counter label="Hold · avg">
        <span className="font-mono text-[1.5rem] text-ivory tabular-nums">{Math.round(avgHold)}</span>
        <span className="font-mono text-[0.78rem] text-ivory-40 ml-1.5">min</span>
      </Counter>
    </div>
  );
}

function Counter({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 first:pl-0 pl-8 first:border-l-0 border-l border-hairline">
      <div className="font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase">{label}</div>
      <div>{children}</div>
    </div>
  );
}

function EmptySlot({ index }: { index: number }) {
  return (
    <div className="border border-dashed border-hairline-strong p-9 text-center bg-white/[0.015]">
      <Aperture size={32} rotate="slow" className="text-ivory-25 mx-auto block mb-3" />
      <p className="font-body italic text-[0.85rem] text-ivory-40">
        slot {index} — idle, awaiting next conjunction
      </p>
    </div>
  );
}
