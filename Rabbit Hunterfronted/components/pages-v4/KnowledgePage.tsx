/**
 * KnowledgePage — V3 (2026-06-27)。
 *
 * M9 知识层: 4 KPI + 书籍列表 (导入入口) + 候选规则列表 (状态过滤)。
 * 2026-06-28: 加"导入书籍" Modal — POST /api/v5/m9/books 后端早就有,UI 缺。
 */
import { useState, useMemo } from 'react';
import { Plus, X, BookOpen, Loader2 } from 'lucide-react';
import { useM9Books, useM9Candidates, useM9AddBook } from '../../hooks/api/useV5M9';
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
  const [showImport, setShowImport] = useState(false);
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
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-v3faint font-mono">{bookList.length}</span>
              <button
                type="button"
                onClick={() => setShowImport(true)}
                title="导入新书籍/笔记"
                className="inline-flex items-center gap-1 rounded-md border border-amber/40 bg-amber-soft px-2 py-1 text-[11px] font-semibold text-amber hover:bg-amber/20 transition"
              >
                <Plus className="h-3 w-3" />
                导入
              </button>
            </div>
          </div>
          {bookList.length === 0 ? (
            <div className="py-10 px-4 text-center">
              <BookOpen className="h-7 w-7 text-v3faint mx-auto mb-3" />
              <div className="text-sm text-v3muted mb-1">尚无书籍</div>
              <div className="text-[11px] text-v3faint">点击右上 <span className="text-amber font-semibold">导入</span> 按钮添加交易书籍/笔记</div>
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
                    {b.content_length != null && b.content_length > 0 && (
                      <> · {b.content_length.toLocaleString()} 字</>
                    )}
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

      {showImport && (
        <ImportBookModal onClose={() => setShowImport(false)} />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// ImportBookModal — 导入书籍/笔记 (POST /api/v5/m9/books)
// ─────────────────────────────────────────────────────────────

function ImportBookModal({ onClose }: { onClose: () => void }) {
  const addBook = useM9AddBook();
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [sourceType, setSourceType] = useState<'book' | 'note' | 'paper' | 'article'>('book');
  const [contentText, setContentText] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);

  const canSubmit = title.trim().length > 0 && !addBook.isPending;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setError(null);
    try {
      await addBook.mutateAsync({
        title: title.trim(),
        author: author.trim() || undefined,
        source_type: sourceType,
        content_text: contentText.trim() || undefined,
        notes: notes.trim() || undefined,
      });
      onClose();
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  };

  // 估算预计切分的 chunk 数 (M9 默认 ~1500 字/chunk)
  const chunkEstimate = Math.max(1, Math.ceil(contentText.length / 1500));

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl mx-6 rounded-lg border border-line bg-panel2 shadow-2xl overflow-hidden max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-line-soft">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-amber" />
            <h3 className="text-sm font-semibold text-v3text">导入书籍 / 笔记</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-v3muted hover:text-v3text transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 表单 */}
        <div className="px-5 py-4 overflow-y-auto flex-1">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
            <div>
              <label className="text-[11px] uppercase tracking-[0.07em] text-v3faint">
                标题 <span className="text-loss">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. 短线交易大师"
                autoFocus
                className="mt-1 w-full rounded-md border border-line bg-ink px-3 py-2 text-[13px] text-v3text outline-none focus:border-amber transition"
              />
            </div>
            <div>
              <label className="text-[11px] uppercase tracking-[0.07em] text-v3faint">作者</label>
              <input
                type="text"
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
                placeholder="e.g. Linda Raschke"
                className="mt-1 w-full rounded-md border border-line bg-ink px-3 py-2 text-[13px] text-v3text outline-none focus:border-amber transition"
              />
            </div>
          </div>

          <div className="mb-3">
            <label className="text-[11px] uppercase tracking-[0.07em] text-v3faint">类型</label>
            <select
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value as any)}
              className="mt-1 w-full rounded-md border border-line bg-ink px-3 py-2 text-[13px] text-v3text outline-none focus:border-amber transition"
            >
              <option value="book">书籍 (book)</option>
              <option value="note">笔记 (note)</option>
              <option value="paper">论文 (paper)</option>
              <option value="article">文章 (article)</option>
            </select>
          </div>

          <div className="mb-3">
            <label className="text-[11px] uppercase tracking-[0.07em] text-v3faint flex items-center justify-between">
              <span>正文内容 (可选)</span>
              {contentText.length > 0 && (
                <span className="font-mono text-amber">
                  {contentText.length.toLocaleString()} 字 → ~{chunkEstimate} chunk
                </span>
              )}
            </label>
            <textarea
              value={contentText}
              onChange={(e) => setContentText(e.target.value)}
              placeholder="粘贴书籍正文,会自动切块进 M9 知识库供 AI 提取候选规则。&#10;留空只创建条目(后续可手动添加候选规则)。"
              rows={8}
              className="mt-1 w-full rounded-md border border-line bg-ink px-3 py-2 text-[12px] font-mono text-v3text outline-none focus:border-amber transition resize-none"
            />
          </div>

          <div className="mb-3">
            <label className="text-[11px] uppercase tracking-[0.07em] text-v3faint">备注 (可选)</label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. 来源, 读后感, ISBN"
              className="mt-1 w-full rounded-md border border-line bg-ink px-3 py-2 text-[13px] text-v3text outline-none focus:border-amber transition"
            />
          </div>

          {error && (
            <div className="mb-3 rounded-md border border-loss/40 bg-loss/10 px-3 py-2 text-[12px] text-loss">
              导入失败: {error}
            </div>
          )}

          <div className="text-[11px] text-v3faint border-t border-line-soft pt-3">
            导入后会自动切块入 M9 知识库 (scripts/m9_knowledge.py)。
            候选规则可在右侧"候选规则"列表里追加或由 M9 自动抽取。
          </div>
        </div>

        {/* 底部按钮 */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-line-soft bg-[#10161D]">
          <button
            type="button"
            onClick={onClose}
            disabled={addBook.isPending}
            className="px-4 py-2 rounded-md border border-line text-[13px] text-v3muted hover:border-v3text hover:text-v3text transition disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-md text-[13px] font-semibold transition ${
              canSubmit
                ? 'bg-amber text-ink hover:bg-amber-dim'
                : 'bg-amber/30 text-v3faint cursor-not-allowed'
            }`}
          >
            {addBook.isPending ? (
              <><Loader2 className="h-3.5 w-3.5 animate-spin" /> 导入中...</>
            ) : (
              <><Plus className="h-3.5 w-3.5" /> 导入</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
