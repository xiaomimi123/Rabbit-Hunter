import React, { useState } from 'react';
import { useV5Signals } from '../../hooks/api/useV5Signals';
import { Card } from '../primitives/Card';
import { Select } from '../primitives/Select';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Badge } from '../primitives/Badge';
import { formatSideBadgeTone, blockReasonZh } from './_signal_helpers';

const BLOCK_OPTIONS = [
  { value: 'ALL', label: '拦截: 全部' },
  { value: 'NOT_RSI_AND_MACD', label: 'RSI/MACD 未合谋' },
  { value: 'NOT_DELTA_15M', label: 'ΔP15m 不足' },
  { value: 'MAX_CONCURRENT_POSITIONS', label: '活仓上限' },
  { value: 'AI_REJECTED', label: 'AI 否决' },
  { value: 'EXECUTED', label: '✓ 已执行' },
];

export function V5SignalHistoryPage() {
  const [block, setBlock] = useState('ALL');
  const q = useV5Signals(200, { blockReason: block === 'ALL' || block === 'EXECUTED' ? null : block });
  const all = q.data?.signals ?? [];
  const rows = block === 'EXECUTED' ? all.filter(s => s.executed) : all;

  return (
    <div className="space-y-4">
      <Card
        title="信号历史"
        actions={
          <Select value={block} options={BLOCK_OPTIONS} onChange={setBlock} />
        }
      >
        {q.isLoading && <LoadingSkeleton rows={6} />}
        {!q.isLoading && rows.length === 0 && <div className="py-8 text-center text-white/40">无匹配记录</div>}
        <div className="overflow-hidden rounded-md border border-white/10">
          <table className="w-full text-xs">
            <thead className="bg-white/5">
              <tr className="text-left text-white/60">
                <th className="px-2 py-2">时间</th>
                <th className="px-2 py-2">币种</th>
                <th className="px-2 py-2">方向</th>
                <th className="px-2 py-2 text-right">ΔP15m</th>
                <th className="px-2 py-2 text-right">RSI</th>
                <th className="px-2 py-2 text-right">MACD hist</th>
                <th className="px-2 py-2">结果</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(s => (
                <tr key={s.id} className="border-t border-white/5">
                  <td className="px-2 py-1.5 font-mono text-white/70">
                    {new Date(s.created_at).toLocaleString('zh-CN', { hour12: false })}
                  </td>
                  <td className="px-2 py-1.5 text-white/90">{s.symbol}</td>
                  <td className="px-2 py-1.5"><Badge variant={formatSideBadgeTone(s.side)}>{s.side ?? '—'}</Badge></td>
                  <td className="px-2 py-1.5 text-right font-mono">{(s.delta_15m_pct * 100).toFixed(2)}%</td>
                  <td className="px-2 py-1.5 text-right font-mono">{s.rsi_15m.toFixed(1)}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{s.macd_hist_15m.toFixed(4)}</td>
                  <td className="px-2 py-1.5">
                    {s.executed
                      ? <Badge variant="long">✓ 执行</Badge>
                      : s.block_reason
                      ? <span className="text-accent-warn">{blockReasonZh(s.block_reason)}</span>
                      : <span className="text-white/40">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
