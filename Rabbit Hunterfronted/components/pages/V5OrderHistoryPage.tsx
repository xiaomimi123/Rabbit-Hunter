import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useV5OrderHistory } from '../../hooks/api/useV5OrderHistory';
import { Card } from '../primitives/Card';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Badge } from '../primitives/Badge';
import { LineChart } from 'lucide-react';
import { Term } from '../shared/Term';

export function V5OrderHistoryPage() {
  const q = useV5OrderHistory(200);
  const navigate = useNavigate();
  const rows = q.data ?? [];

  return (
    <div className="space-y-4">
      <Card title="订单历史" actions={<span className="text-xs text-white/40">每 30s 自动刷新 · 共 {rows.length} 条</span>}>
        {q.isLoading && <LoadingSkeleton rows={6} />}
        {!q.isLoading && rows.length === 0 && <div className="py-8 text-center text-white/40">暂无历史订单</div>}
        <div className="overflow-hidden rounded-md border border-white/10">
          <table className="w-full text-xs">
            <thead className="bg-white/5">
              <tr className="text-left text-white/60">
                <th className="px-2 py-2">平仓时间</th>
                <th className="px-2 py-2">币种</th>
                <th className="px-2 py-2">方向</th>
                <th className="px-2 py-2 text-right">入场</th>
                <th className="px-2 py-2 text-right">出场</th>
                <th className="px-2 py-2">原因</th>
                <th className="px-2 py-2 text-right"><Term k="PnL">PnL$</Term></th>
                <th className="px-2 py-2 text-right"><Term k="PnL">PnL%</Term></th>
                <th className="px-2 py-2 text-right">持仓min</th>
                <th className="px-2 py-2">策略</th>
                <th className="px-2 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(p => {
                const mins = p.entry_time && p.exit_time
                  ? Math.round((new Date(p.exit_time).getTime() - new Date(p.entry_time).getTime()) / 60_000)
                  : 0;
                const pnlPct = p.pnl_pct ?? 0;
                const pnlUsd = p.pnl_usdt ?? 0;
                return (
                  <tr key={p.id} className="border-t border-white/5 hover:bg-white/[0.02]">
                    <td className="px-2 py-1.5 font-mono text-white/70">
                      {p.exit_time ? new Date(p.exit_time).toLocaleString('zh-CN', { hour12: false }) : '—'}
                    </td>
                    <td className="px-2 py-1.5 text-white/90">{p.symbol}</td>
                    <td className="px-2 py-1.5"><Badge variant={p.side === 'LONG' ? 'long' : 'short'}>{p.side}</Badge></td>
                    <td className="px-2 py-1.5 text-right font-mono">{p.entry_price?.toFixed(4) ?? '—'}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{p.exit_price?.toFixed(4) ?? '—'}</td>
                    <td className="px-2 py-1.5 text-white/70"><Term k={p.exit_reason || ''}>{p.exit_reason ?? '—'}</Term></td>
                    <td className={`px-2 py-1.5 text-right font-mono ${pnlUsd >= 0 ? 'text-accent-long' : 'text-accent-short'}`}>{pnlUsd >= 0 ? '+' : ''}{pnlUsd.toFixed(2)}</td>
                    <td className={`px-2 py-1.5 text-right font-mono ${pnlPct >= 0 ? 'text-accent-long' : 'text-accent-short'}`}>{pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%</td>
                    <td className="px-2 py-1.5 text-right font-mono">{mins}</td>
                    <td className="px-2 py-1.5"><Badge variant="neutral">自动</Badge></td>
                    <td className="px-2 py-1.5">
                      <button
                        type="button"
                        onClick={() => navigate(`/v5/chart/${p.symbol}?eventId=${p.id}`)}
                        className="flex items-center gap-1 rounded-sm border border-white/15 px-2 py-0.5 text-xs text-white/70 hover:bg-white/5"
                      >
                        <LineChart size={10} /> 图表
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
