import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useV5ActivePositions, useV5ClosePosition } from '../../hooks/api/useV5ActivePositions';
import { ActivePositionCard } from '../shared/ActivePositionCard';
import { Card } from '../primitives/Card';
import { Modal } from '../primitives/Modal';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import type { V5Position } from '../../types';

const MAX_SLOTS = 3;

export function V5ActivePositionsPage() {
  const q = useV5ActivePositions();
  const close = useV5ClosePosition();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState<V5Position | null>(null);

  const combined = q.data?.combined ?? [];
  const total = combined.length;

  return (
    <div className="space-y-4">
      <Card
        title={
          <div className="flex items-center gap-3">
            <span>活仓监控</span>
            <span className="text-sm font-mono text-white/60">{total} / {MAX_SLOTS}</span>
          </div>
        }
        actions={<span className="text-xs text-white/40">每 5s 自动刷新</span>}
      >
        {q.isLoading && <LoadingSkeleton rows={3} />}
        {!q.isLoading && total === 0 && (
          <div className="py-8 text-center text-white/40">当前无活仓</div>
        )}
        <div className="space-y-3">
          {combined.map(p => (
            <ActivePositionCard
              key={p.id}
              position={p}
              onClose={() => setConfirm(p)}
              onChart={() => navigate(`/v5/chart/${p.symbol.replace('/', '_')}`)}
            />
          ))}
          {total < MAX_SLOTS && (
            <div className="rounded-md border border-dashed border-white/15 p-6 text-center text-sm text-white/40">
              [+] 空闲槽位({MAX_SLOTS - total} 个)
            </div>
          )}
        </div>
      </Card>

      <Modal
        open={!!confirm}
        onClose={() => setConfirm(null)}
        title="确认立即平仓"
      >
        {confirm && (
          <div className="space-y-3 text-sm">
            <div>
              {confirm.symbol} · {confirm.side} · 入场 {confirm.entry_price.toFixed(4)} · 当前 {confirm.current_price?.toFixed(4) ?? '—'}
            </div>
            <div className="text-white/60">
              当前 PnL: {confirm.pnl_percent?.toFixed(2)}% / {confirm.pnl_usdt?.toFixed(2)} USDT
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setConfirm(null)} className="rounded-sm border border-white/15 px-3 py-1 text-xs">取消</button>
              <button
                type="button"
                disabled={close.isPending}
                onClick={async () => {
                  await close.mutateAsync({
                    id: confirm.id,
                    body: {
                      exit_price: confirm.current_price ?? confirm.entry_price,
                      exit_reason: 'MANUAL_USER',
                    },
                  });
                  setConfirm(null);
                }}
                className="rounded-sm border border-accent-short/40 bg-accent-short/10 px-3 py-1 text-xs text-accent-short hover:bg-accent-short/20 disabled:opacity-50"
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
