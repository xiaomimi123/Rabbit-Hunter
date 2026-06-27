/**
 * KnowledgePage — V3 重写 (2026-06-27)。
 *
 * M9 知识层: 4 KPI + 书籍列表 + 候选规则列表 (状态过滤)。
 * 高级操作 (验证/添加) 后续单独迁移。
 */
import { useState, useMemo } from 'react';
import { useM9Books, useM9Candidates } from '../../hooks/api/useV5M9';
import type { CandidateOut } from '../../hooks/api/useV5M9';

function Card({ children, className = '', pad0 = false }: { children: React.ReactNode; className?: string; pad0?: boolean }) {
  return (
    <section className={`rounded-[10px] border border-line-soft bg-panel ${pad0 ? 'p-0 overflow-hidden' : 'p-4'} ${className}`}>
      {children}
    </section>
  );
}

function MetricCard({ label, value, sub, valueColor = 'text-v3text' }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; valueColor?: string;
}) {
  return (
    <Card>
      <div className="text-[11px] uppercase tracking-[0.07em] text-v3faint">{label}</div>
      <div className={`mt-2 font-semibold leading-none font-mono text-[22px] ${valueColor}`}>{value}</div>
      {sub && <div className="mt-1.5 text-[11px] text-v3muted">{sub}</div>}
    </Card>
  );
}

function StatusBadge({ status }: { status: CandidateOut['status'] }) {
  const map: Record<CandidateOut['status'], { tone: string; label: string }> = {
    pending:    { tone: 'text-v3muted bg-[#1a232d] border-line',     label: '待验证' },
    validating: { tone: 'text-amber bg-amber-soft border-amber/30',  label: '验证中' },
    validated:  { tone: 'text-info bg-info/10 border-info/30',       label: '已验证' },
    approved:   { tone: 'text-gain bg-gain/10 border-gain/30',       label: '已采纳' },
    rejected:   { tone: 'text-loss bg-loss/10 border-loss/30',       label: '已拒绝' },
    broken:     { tone: 'text-loss bg-loss/10 border-loss/30',       label: '失效' },
  };
  const s = map[status] ?? map.pending;
  return (
    <span className={`text-[10.5px] px-1.5 py-0.5 rounded font-semibold tracking-[0.02em] border ${s.tone}`}>
      {s.label}
    </span>
  );
}

const STATUS_TABS = [
  { key: '',           label: '全部' },
  { key: 'pending',    label: '待验证' },
  { key: 'validated',  label: '已验证' },
  { key: 'approved',   label: '已采纳' },
  { key: 'rejected',   label: '已拒绝' },
] as const;

export function KnowledgePage() {
  const books = useM9Books();
  const [statusFilter, setStatusFilter] = useState<string>('');
  const candidates = useM9Candidates(statusFilter || undefined);

  const bookList = books.data?.books ?? [];
  const candList = candidates.data?.candidates ?? [];

  const stats = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const c of candList) counts[c.status] = (counts[c.status] ?? 0) + 1;
    return counts;
  }, [candList]);

  return (
    <div className="px-6 pb-10 pt-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mb-5">
        <MetricCard label="书籍 / 笔记" value={bookList.length}
          sub={<span className="text-v3faint">已导入的知识源</span>} />
        <MetricCard label="候选规则总数" value={candList.length}
          sub={<span className="font-mono text-v3faint">M9 提取/录入</span>} />
        <MetricCard label="已验证" value={(stats.validated ?? 0) + (stats.approved ?? 0)}
          valueColor="text-info" sub={<span className="text-v3faint">通过 WF KPI</span>} />
        <MetricCard label="已采纳" value={stats.approved ?? 0}
          valueColor="text-gain" sub={<span className="text-v3faint">合入主策略</span>} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_2fr] gap-3.5">
        <Card pad0>
          <div className="flex items-center justify-between px-4 pt-4 pb-2">
            <h3 className="text-xs font-medium text-v3muted uppercase tracking-[0.06em]">书籍 / 笔记</h3>
            <span className="text-[10px] text-v3faint font-mono">{bookList.length}</span>
          </div>
          {bookList.length === 0 ? (
            <div className="py-10 text-center text-sm text-v3faint">
              无书籍 (用 <span className="font-mono text-amber">m9_knowledge.py</span> 导入)
            </div>
          ) : (
            <div className="max-h-[640px] overflow-y-auto">
              {bookList.map((b) => (
                <div key={b.id} className="px-4 py-3 border-b border-line-soft">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="font-semibold text-[13px] text-v3text truncate">{b.title}</span>
                    <span className="text-[10px] font-mono text-amber shrink-0">{b.n_candidates} 规则</span>
                  </div>
                  {b.author && <div className="text-[11px] text-v3muted">{b.author}</div>}
                  <div className="text-[10px] text-v3faint mt-0.5 font-mono">
                    {b.source_type} · {new Date(b.uploaded_at).toLocaleDateString('zh-CN')}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card pad0>
          <div className="flex items-center justify-between px-4 pt-4 pb-3">
            <h3 className="text-xs font-medium text-v3muted uppercase tracking-[0.06em]">候选规则</h3>
            <div className="inline-flex gap-0.5 rounded-md border border-line bg-ink p-0.5">
              {STATUS_TABS.map((t) => (
                <button
                  key={t.key || 'all'}
                  onClick={() => setStatusFilter(t.key)}
                  className={`text-[11px] px-2.5 py-1 rounded-[4px] transition ${
                    statusFilter === t.key ? 'bg-raised text-v3text' : 'text-v3muted hover:text-v3text'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          {candList.length === 0 ? (
            <div className="py-10 text-center text-sm text-v3faint">无候选规则</div>
          ) : (
            <div className="max-h-[600px] overflow-y-auto">
              <table className="w-full font-mono text-[12px]">
                <thead className="text-[10px] uppercase tracking-[0.06em] text-v3faint sticky top-0 bg-panel">
                  <tr className="border-b border-line-soft">
                    <th className="px-3 py-2 text-left font-normal">名称</th>
                    <th className="px-3 py-2 text-left font-normal">状态</th>
                    <th className="px-3 py-2 text-right font-normal">KPI</th>
                    <th className="px-3 py-2 text-left font-normal">创建</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line-soft">
                  {candList.map((c) => (
                    <tr key={c.id} className="text-v3text">
                      <td className="px-3 py-2.5">
                        <div className="text-[12px] text-v3text truncate max-w-[280px]">{c.name}</div>
                        {c.description && (
                          <div className="text-[10px] text-v3faint truncate max-w-[280px] mt-0.5">{c.description}</div>
                        )}
                      </td>
                      <td className="px-3 py-2.5"><StatusBadge status={c.status} /></td>
                      <td className={`px-3 py-2.5 text-right ${c.kpi_passes ? 'text-gain' : c.kpi_passes === 0 ? 'text-loss' : 'text-v3faint'}`}>
                        {c.kpi_passes == null ? '—' : (c.kpi_passes ? 'PASS' : 'FAIL')}
                      </td>
                      <td className="px-3 py-2.5 text-v3faint text-[11px]">
                        {new Date(c.created_at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
