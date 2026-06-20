import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, TrendingUp, TrendingDown } from 'lucide-react';
import { useV5ActivePositions, useV5ClosePosition } from '../../hooks/api/useV5ActivePositions';
import { ActivePositionCard } from '../shared/ActivePositionCard';
import { Modal } from '../primitives/Modal';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { MetricCard } from '../primitives-v3/MetricCard';
import { Card } from '../primitives-v3/Card';
import { SecondaryButton, DangerButton } from '../primitives-v3/FormField';
import { cn } from '../primitives-v3/cn';
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
    <div className="mx-auto w-full max-w-7xl px-6 py-6 space-y-6">
      <SectionTitle
        title="活仓监控"
        subtitle={`实时持仓 · 5s 自动校准 · ${now.toLocaleTimeString('zh-CN', { hour12: false })}`}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="槽位使用"
          value={`${total} / ${MAX_SLOTS}`}
          hint={`${longCount} long · ${shortCount} short · ${MAX_SLOTS - total} idle`}
        />
        <MetricCard
          label="方向分布"
          value={(
            <span className="inline-flex gap-1.5">
              {Array.from({ length: MAX_SLOTS }).map((_, i) => {
                let cls = 'border-zinc-700';
                if (i < longCount) cls = 'bg-emerald-500/40 border-emerald-500';
                else if (i < longCount + shortCount) cls = 'bg-rose-500/40 border-rose-500';
                return <span key={i} className={cn('inline-block h-5 w-5 rounded-md border', cls)} />;
              })}
            </span>
          )}
          hint={`${longCount} 多 · ${shortCount} 空`}
        />
        <MetricCard
          label="未实现 PnL"
          value={`${unrealized >= 0 ? '+' : ''}${unrealized.toFixed(2)} USDT`}
          hint={`${unrealizedPct >= 0 ? '+' : ''}${unrealizedPct.toFixed(2)}% 平均`}
          trend={unrealized > 0 ? 'up' : unrealized < 0 ? 'down' : 'neutral'}
        />
        <MetricCard
          label="平均持仓"
          value={`${Math.round(avgHold)} min`}
          hint={total ? `跨 ${total} 个仓` : '—'}
        />
      </div>

      {q.isLoading && <LoadingSkeleton message="拉取活仓状态中…" />}

      <div className="space-y-4">
        {combined.map(p => (
          <ActivePositionCard
            key={p.id}
            position={p}
            onClose={() => setConfirm(p)}
            onChart={() => navigate(`/v5/chart/${p.symbol}`)}
          />
        ))}
        {!q.isLoading && total === 0 && <EmptySlot index={1} />}
        {!q.isLoading && total > 0 && total < MAX_SLOTS && <EmptySlot index={total + 1} />}
      </div>

      <Modal open={!!confirm} onClose={() => setConfirm(null)} title="确认立即平仓">
        {confirm && (
          <div className="flex flex-col gap-4">
            <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 px-4 py-3">
              <div className="flex items-center gap-2 font-mono text-sm">
                <span className="text-zinc-100 font-medium">{confirm.symbol}</span>
                <span className={cn(
                  'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase',
                  confirm.side === 'LONG'
                    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                    : 'bg-rose-500/15 text-rose-300 border-rose-500/30',
                )}>
                  {confirm.side === 'LONG' ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}
                  {confirm.side}
                </span>
                <span className="text-zinc-400">入场 {confirm.entry_price?.toFixed(4) ?? '—'}</span>
              </div>
              <div className="mt-2 font-mono text-sm">
                <span className="text-zinc-500">当前 PnL: </span>
                <span className={(confirm.pnl_pct ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300'}>
                  {(confirm.pnl_pct ?? 0) >= 0 ? '+' : ''}{(confirm.pnl_pct ?? 0).toFixed(2)}%
                  {' · '}
                  {(confirm.pnl_usdt ?? 0) >= 0 ? '+' : ''}{(confirm.pnl_usdt ?? 0).toFixed(2)} USDT
                </span>
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <SecondaryButton onClick={() => setConfirm(null)}>取消</SecondaryButton>
              <DangerButton
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
              >
                {close.isPending ? '平仓中…' : '确认平仓'}
              </DangerButton>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

function EmptySlot({ index }: { index: number }) {
  return (
    <Card>
      <div className="flex flex-col items-center justify-center py-8 text-center">
        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-zinc-800">
          <Activity className="h-5 w-5 text-zinc-500" />
        </div>
        <div className="text-sm font-medium text-zinc-300">槽位 {index} · 空闲</div>
        <div className="mt-1 text-xs text-zinc-500">等待下一次合谋信号触发</div>
      </div>
    </Card>
  );
}
