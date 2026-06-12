import React from 'react';
import type { AIDecisionItem } from '../../types';
import { Badge } from '../primitives/Badge';

interface Props {
  decisions: AIDecisionItem[];
  limit?: number;
}

export function RecentAIDecisions({ decisions, limit = 20 }: Props) {
  const items = decisions.slice(0, limit);
  return (
    <div className="overflow-hidden rounded-md border border-white/10">
      <table className="w-full text-xs">
        <thead className="bg-white/5">
          <tr className="text-left text-white/60">
            <th className="px-2 py-2">时间</th>
            <th className="px-2 py-2">币种</th>
            <th className="px-2 py-2">决定</th>
            <th className="px-2 py-2">Top-1 相似</th>
            <th className="px-2 py-2">推理摘要</th>
          </tr>
        </thead>
        <tbody>
          {items.map(d => (
            <tr key={d.id} className="border-t border-white/5 hover:bg-white/[0.02]">
              <td className="px-2 py-1.5 font-mono text-white/70">
                {new Date(d.created_at).toLocaleTimeString('zh-CN', { hour12: false })}
              </td>
              <td className="px-2 py-1.5 text-white/90">{d.symbol}</td>
              <td className="px-2 py-1.5">
                <Badge variant={d.execute ? 'long' : 'short'}>
                  {d.execute ? '✓ 批准' : '✗ 拒'}
                </Badge>
              </td>
              <td className="px-2 py-1.5 font-mono text-white/70">
                {d.top1_distance == null ? '—' : `d=${d.top1_distance.toFixed(2)}`}
              </td>
              <td className="px-2 py-1.5 text-white/60">
                {d.reasoning.length > 60 ? d.reasoning.slice(0, 60) + '…' : d.reasoning}
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan={5} className="px-2 py-6 text-center text-white/40">暂无决策记录</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
