import React from 'react';
import { useV5AIStatus, useV5AIDecisions } from '../../hooks/api/useV5AIStatus';
import { Card } from '../primitives/Card';
import { KpiCard } from '../shared/KpiCard';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { RecentAIDecisions } from '../shared/RecentAIDecisions';

export function V5AIStatusPage() {
  const status = useV5AIStatus();
  const dec = useV5AIDecisions(20);
  if (status.isLoading) return <LoadingSkeleton rows={4} />;
  const s = status.data;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <KpiCard
          title="Provider"
          value={s?.provider ?? '未配置'}
          unit={s?.chat_model}
        />
        <KpiCard
          title="RAG 利用率 (24h)"
          value={`${Math.round((s?.rag_utilization_24h ?? 0) * 100)}%`}
          unit={`本地 ${s?.rag_cases_in_db ?? 0} cases`}
        />
        <KpiCard
          title="24h 决策数"
          value={s?.decisions_24h ?? 0}
          unit={s?.healthy ? '在线' : '离线'}
        />
      </div>

      <Card title="最近 20 笔 AI 决策">
        {dec.isLoading ? <LoadingSkeleton rows={5} /> : <RecentAIDecisions decisions={dec.data?.decisions ?? []} />}
      </Card>
    </div>
  );
}
