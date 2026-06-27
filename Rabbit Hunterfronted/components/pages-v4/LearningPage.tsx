import { useState } from 'react';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { SegmentButton } from '../primitives-v3/SegmentButton';
import { AuditPage } from './AuditPage';
import { DiagnosticsPage } from './DiagnosticsPage';

type Tab = 'audit' | 'diagnostics';

export function LearningPage() {
  const [tab, setTab] = useState<Tab>('audit');

  return (
    <div className="space-y-6">
      <SectionTitle
        title="AI 学习"
        subtitle="复盘归因 · setup_performance · AI 决策追踪 · 失败模式"
        action={
          <div className="flex gap-1 rounded-2xl border border-hairline bg-bg-surface/40 p-1">
            <SegmentButton active={tab === 'audit'} onClick={() => setTab('audit')}>复盘 / setup</SegmentButton>
            <SegmentButton active={tab === 'diagnostics'} onClick={() => setTab('diagnostics')}>诊断追踪</SegmentButton>
          </div>
        }
      />

      {tab === 'audit' && <AuditPage />}
      {tab === 'diagnostics' && <DiagnosticsPage />}
    </div>
  );
}
