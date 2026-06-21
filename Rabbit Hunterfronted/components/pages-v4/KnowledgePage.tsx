import { useState } from 'react';
import {
  BookOpen, Plus, FlaskConical, CheckCircle, XCircle,
  Hourglass, AlertTriangle,
} from 'lucide-react';
import {
  useM9Books, useM9AddBook, useM9Candidates, useM9AddCandidate,
  useM9ValidateCandidate, useM9ApproveCandidate, useM9RejectCandidate,
  CandidateOut,
} from '../../hooks/api/useV5M9';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { MetricCard } from '../primitives-v3/MetricCard';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { Alert } from '../primitives-v3/Alert';
import {
  FormField, TextInput, PrimaryButton, SecondaryButton, DangerButton,
} from '../primitives-v3/FormField';
import { Modal } from '../primitives/Modal';
import { cn } from '../primitives-v3/cn';

const STATUS_TONES = {
  pending: 'amber',
  validated: 'indigo',
  approved: 'emerald',
  rejected: 'rose',
  broken: 'zinc',
} as const;

const STATUS_LABELS = {
  pending: '待验证',
  validated: '已验证',
  approved: '已批准',
  rejected: '已拒绝',
  broken: '失效',
} as const;

export function KnowledgePage() {
  const books = useM9Books();
  const candidates = useM9Candidates();
  const allBooks = books.data?.books ?? [];
  const allCandidates = candidates.data?.candidates ?? [];

  const counts = {
    pending: allCandidates.filter(c => c.status === 'pending').length,
    validated: allCandidates.filter(c => c.status === 'validated').length,
    approved: allCandidates.filter(c => c.status === 'approved').length,
    rejected: allCandidates.filter(c => c.status === 'rejected').length,
  };

  const [showBookModal, setShowBookModal] = useState(false);
  const [showCandidateModal, setShowCandidateModal] = useState(false);
  const [validating, setValidating] = useState<CandidateOut | null>(null);

  return (
    <div className="space-y-6">
      <SectionTitle
        title="知识层 · 候选规则"
        subtitle="M9 — 书籍只产候选,WF 验证 + 人审才进 setup 列表(文档 §11)"
        action={
          <div className="flex gap-2">
            <SecondaryButton onClick={() => setShowBookModal(true)}>
              <BookOpen className="h-4 w-4 inline mr-1.5" /> 加书
            </SecondaryButton>
            <PrimaryButton onClick={() => setShowCandidateModal(true)}>
              <Plus className="h-4 w-4 inline mr-1.5" /> 加候选规则
            </PrimaryButton>
          </div>
        }
      />

      <Alert tone="warning">
        <div className="flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 mt-0.5" />
          <div className="text-sm leading-6">
            <strong>边界提醒(文档 §11)</strong>:书籍只产出"候选规则",**不能直接改实盘逻辑**。
            候选必须 walk-forward 验证 + 你本人批准,才能加入 M2。模糊的、不可量化的理念只作为阅读材料,不进管线。
          </div>
        </div>
      </Alert>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="书籍" value={String(allBooks.length)} hint="已上传 / 录入" />
        <MetricCard label="待验证候选" value={String(counts.pending)} trend={counts.pending > 0 ? 'up' : 'neutral'} hint="pending — 等 WF 验证" />
        <MetricCard label="待审核候选" value={String(counts.validated)} trend={counts.validated > 0 ? 'up' : 'neutral'} hint="validated — 等你批准" />
        <MetricCard label="已批准" value={String(counts.approved)} hint="approved — 可作为新 setup" />
      </div>

      <Card title="书籍" subtitle={`${allBooks.length} 本`} className="!p-0" bodyClassName="!p-0">
        {allBooks.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-zinc-500">
            还没上传任何书。先加 1 本 Ernest Chan《Quantitative Trading》或 Carver《Systematic Trading》作为开端。
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                  <th className="py-3 pl-5 pr-2">标题</th>
                  <th className="py-3 px-2">作者</th>
                  <th className="py-3 px-2">来源</th>
                  <th className="py-3 px-2 text-right">字符</th>
                  <th className="py-3 px-2 text-right">候选数</th>
                  <th className="py-3 pl-2 pr-5">上传时间</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {allBooks.map(b => (
                  <tr key={b.id} className="hover:bg-zinc-900/40">
                    <td className="py-2.5 pl-5 pr-2 text-zinc-100">{b.title}</td>
                    <td className="py-2.5 px-2 text-zinc-400">{b.author ?? '—'}</td>
                    <td className="py-2.5 px-2"><StatusPill tone="zinc">{b.source_type}</StatusPill></td>
                    <td className="py-2.5 px-2 text-right font-mono tabular-nums text-zinc-400">
                      {b.content_length?.toLocaleString() ?? '—'}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono tabular-nums text-indigo-300">
                      {b.n_candidates}
                    </td>
                    <td className="py-2.5 pl-2 pr-5 font-mono text-xs text-zinc-500">
                      {new Date(b.uploaded_at).toLocaleString('zh-CN', { hour12: false }).slice(0, 16)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="候选规则审核工作台" subtitle={`${allCandidates.length} 条规则 · 文档 §11 第 3、4 步`}>
        {allCandidates.length === 0 ? (
          <div className="py-10 text-center text-sm text-zinc-500">
            还没有候选规则。先从书里手动提一条,或者后续接入 AI 自动提取。
          </div>
        ) : (
          <div className="space-y-3">
            {allCandidates.map(c => (
              <CandidateRow
                key={c.id}
                c={c}
                onValidate={() => setValidating(c)}
              />
            ))}
          </div>
        )}
      </Card>

      <AddBookModal open={showBookModal} onClose={() => setShowBookModal(false)} />
      <AddCandidateModal
        open={showCandidateModal}
        onClose={() => setShowCandidateModal(false)}
        books={allBooks}
      />
      <ValidateModal
        candidate={validating}
        onClose={() => setValidating(null)}
      />
    </div>
  );
}

function CandidateRow({ c, onValidate }: { c: CandidateOut; onValidate: () => void }) {
  const approve = useM9ApproveCandidate();
  const reject = useM9RejectCandidate();
  const tone = STATUS_TONES[c.status];
  const label = STATUS_LABELS[c.status];

  let icon = <Hourglass className="h-2.5 w-2.5" />;
  if (c.status === 'approved') icon = <CheckCircle className="h-2.5 w-2.5" />;
  else if (c.status === 'rejected') icon = <XCircle className="h-2.5 w-2.5" />;
  else if (c.status === 'validated') icon = <FlaskConical className="h-2.5 w-2.5" />;

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 p-4">
      <div className="flex items-center gap-3 flex-wrap mb-2">
        <div className="font-mono text-sm text-zinc-100 flex-1 min-w-0">
          <span className="text-zinc-500 mr-1">#{c.id}</span>
          {c.name}
        </div>
        <StatusPill tone={tone} icon={icon}>{label}</StatusPill>
        {c.kpi_passes != null && (
          c.kpi_passes === 1
            ? <StatusPill tone="emerald">KPI PASS</StatusPill>
            : <StatusPill tone="rose">KPI FAIL</StatusPill>
        )}
        <span className="text-xs text-zinc-500">{c.extracted_by}</span>
      </div>

      {c.description && (
        <div className="text-sm text-zinc-300 leading-relaxed mb-2">{c.description}</div>
      )}

      <details className="text-xs">
        <summary className="cursor-pointer text-zinc-500 hover:text-zinc-300">规则规格</summary>
        <pre className="mt-2 rounded-xl border border-zinc-800 bg-zinc-950 p-3 overflow-x-auto text-zinc-400">
          {JSON.stringify(JSON.parse(c.rule_spec_json), null, 2)}
        </pre>
      </details>

      {c.source_quote && (
        <details className="text-xs mt-1">
          <summary className="cursor-pointer text-zinc-500 hover:text-zinc-300">书中原文</summary>
          <div className="mt-2 rounded-xl border-l-2 border-indigo-500 bg-indigo-500/[0.06] px-3 py-2 text-zinc-300 italic">
            {c.source_quote}
          </div>
        </details>
      )}

      {c.reject_reason && (
        <div className="mt-2 text-xs text-rose-300">拒绝原因:{c.reject_reason}</div>
      )}

      {c.wf_report_path && (
        <div className="mt-2 text-xs text-zinc-500">
          WF 报告:<span className="text-indigo-300 font-mono">{c.wf_report_path}</span>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2 pt-3 border-t border-zinc-800">
        {(c.status === 'pending' || c.status === 'validated') && (
          <SecondaryButton onClick={onValidate}>
            <FlaskConical className="h-4 w-4 inline mr-1.5" /> 重新跑 WF 验证
          </SecondaryButton>
        )}
        {c.status === 'validated' && c.kpi_passes === 1 && (
          <PrimaryButton
            onClick={() => approve.mutate({ id: c.id, approver: 'user' })}
            disabled={approve.isPending}
          >
            批准
          </PrimaryButton>
        )}
        {c.status === 'validated' && (
          <DangerButton
            onClick={() => {
              const r = prompt('拒绝原因:');
              if (r) reject.mutate({ id: c.id, reason: r });
            }}
          >
            拒绝
          </DangerButton>
        )}
      </div>
    </div>
  );
}

function AddBookModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const add = useM9AddBook();
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [content, setContent] = useState('');
  const [notes, setNotes] = useState('');

  return (
    <Modal open={open} onClose={onClose} title="添加书籍">
      <div className="space-y-3">
        <FormField label="标题"><TextInput value={title} onChange={e => setTitle(e.target.value)} /></FormField>
        <FormField label="作者"><TextInput value={author} onChange={e => setAuthor(e.target.value)} placeholder="可空" /></FormField>
        <FormField label="正文(可选,贴段落或全文)">
          <textarea
            value={content}
            onChange={e => setContent(e.target.value)}
            rows={6}
            placeholder="贴粘后会自动切块到 knowledge_chunks 表"
            className="rounded-2xl border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-indigo-500 focus:outline-none"
          />
        </FormField>
        <FormField label="备注(可选)"><TextInput value={notes} onChange={e => setNotes(e.target.value)} /></FormField>
        <div className="flex justify-end gap-2 pt-3 border-t border-zinc-800">
          <SecondaryButton onClick={onClose}>取消</SecondaryButton>
          <PrimaryButton
            disabled={!title || add.isPending}
            onClick={async () => {
              await add.mutateAsync({
                title, author: author || undefined,
                content_text: content || undefined,
                notes: notes || undefined,
              });
              setTitle(''); setAuthor(''); setContent(''); setNotes('');
              onClose();
            }}
          >
            {add.isPending ? '保存中…' : '加入'}
          </PrimaryButton>
        </div>
      </div>
    </Modal>
  );
}

function AddCandidateModal({
  open, onClose, books,
}: { open: boolean; onClose: () => void; books: { id: number; title: string }[] }) {
  const add = useM9AddCandidate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [bookId, setBookId] = useState<number | ''>('');
  const [sourceQuote, setSourceQuote] = useState('');
  const [specJson, setSpecJson] = useState('{\n  "setup_type_name": "price_action_double_bottom_long",\n  "side": "LONG",\n  "indicator_overrides": {},\n  "min_holding_minutes": 60\n}');
  const [parseError, setParseError] = useState<string | null>(null);

  return (
    <Modal open={open} onClose={onClose} title="添加候选规则">
      <div className="space-y-3">
        <FormField label="规则名"><TextInput value={name} onChange={e => setName(e.target.value)} placeholder="如:double_bottom_long" /></FormField>
        <FormField label="描述"><TextInput value={description} onChange={e => setDescription(e.target.value)} placeholder="一句话总结这条规则在做什么" /></FormField>
        <FormField label="来自哪本书">
          <select
            value={bookId}
            onChange={e => setBookId(e.target.value === '' ? '' : Number(e.target.value))}
            className="rounded-2xl border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-indigo-500"
          >
            <option value="">— 纯人工提案 —</option>
            {books.map(b => <option key={b.id} value={b.id}>#{b.id} {b.title}</option>)}
          </select>
        </FormField>
        <FormField label="书中原文(可选)">
          <textarea
            value={sourceQuote}
            onChange={e => setSourceQuote(e.target.value)}
            rows={3}
            className="rounded-2xl border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 placeholder:text-zinc-600 focus:border-indigo-500 focus:outline-none"
          />
        </FormField>
        <FormField label="规则规格(JSON)">
          <textarea
            value={specJson}
            onChange={e => { setSpecJson(e.target.value); setParseError(null); }}
            rows={8}
            className="rounded-2xl border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 focus:border-indigo-500 focus:outline-none"
          />
        </FormField>
        {parseError && <Alert tone="error">{parseError}</Alert>}
        <div className="flex justify-end gap-2 pt-3 border-t border-zinc-800">
          <SecondaryButton onClick={onClose}>取消</SecondaryButton>
          <PrimaryButton
            disabled={!name || add.isPending}
            onClick={async () => {
              let spec: any;
              try { spec = JSON.parse(specJson); }
              catch (e: any) { setParseError('JSON 格式错: ' + e.message); return; }
              await add.mutateAsync({
                name, description: description || undefined,
                book_id: bookId === '' ? null : bookId,
                source_quote: sourceQuote || undefined,
                rule_spec: spec,
              });
              setName(''); setDescription(''); setSourceQuote('');
              onClose();
            }}
          >
            {add.isPending ? '保存中…' : '加入'}
          </PrimaryButton>
        </div>
      </div>
    </Modal>
  );
}

function ValidateModal({
  candidate, onClose,
}: { candidate: CandidateOut | null; onClose: () => void }) {
  const validate = useM9ValidateCandidate();
  const [startIso, setStartIso] = useState('2026-05-19');
  const [endIso, setEndIso] = useState('2026-06-18');
  const [symbols, setSymbols] = useState('BTC/USDT,ETH/USDT,SOL/USDT');
  const [trainDays, setTrainDays] = useState(15);
  const [oosDays, setOosDays] = useState(7);
  const [stepDays, setStepDays] = useState(7);
  const [result, setResult] = useState<{ kpi_passes: boolean; n_oos_trades: number; net_avg_r: number; net_profit_factor: number | null; wf_report_path: string } | null>(null);

  if (!candidate) return null;

  return (
    <Modal open={true} onClose={onClose} title={`跑 WF 验证 — ${candidate.name}`}>
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <FormField label="开始日期"><TextInput value={startIso} onChange={e => setStartIso(e.target.value)} /></FormField>
          <FormField label="结束日期"><TextInput value={endIso} onChange={e => setEndIso(e.target.value)} /></FormField>
        </div>
        <FormField label="symbols(CSV)">
          <TextInput value={symbols} onChange={e => setSymbols(e.target.value)} />
        </FormField>
        <div className="grid grid-cols-3 gap-3">
          <FormField label="train days">
            <TextInput type="number" value={trainDays} onChange={e => setTrainDays(Number(e.target.value))} />
          </FormField>
          <FormField label="OOS days">
            <TextInput type="number" value={oosDays} onChange={e => setOosDays(Number(e.target.value))} />
          </FormField>
          <FormField label="step days">
            <TextInput type="number" value={stepDays} onChange={e => setStepDays(Number(e.target.value))} />
          </FormField>
        </div>

        {result && (
          <Alert tone={result.kpi_passes ? 'success' : 'error'}>
            <div className="text-sm">
              <div className="flex items-center gap-2 mb-1">
                {result.kpi_passes ? <CheckCircle className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
                <span className="font-medium">{result.kpi_passes ? 'KPI PASS' : 'KPI FAIL'}</span>
              </div>
              <div className="space-y-0.5 font-mono text-xs">
                <div>OOS n = <span className="text-zinc-100">{result.n_oos_trades}</span></div>
                <div>net avg R = <span className={cn(result.net_avg_r >= 0 ? 'text-emerald-300' : 'text-rose-300')}>{result.net_avg_r.toFixed(3)}</span></div>
                <div>net PF = <span className={cn((result.net_profit_factor ?? 0) > 1 ? 'text-emerald-300' : 'text-rose-300')}>{result.net_profit_factor != null ? result.net_profit_factor.toFixed(2) : '∞'}</span></div>
                <div>报告:<span className="text-indigo-300">{result.wf_report_path}</span></div>
              </div>
            </div>
          </Alert>
        )}

        <div className="flex justify-end gap-2 pt-3 border-t border-zinc-800">
          <SecondaryButton onClick={onClose}>关闭</SecondaryButton>
          <PrimaryButton
            disabled={validate.isPending}
            onClick={async () => {
              const r = await validate.mutateAsync({
                id: candidate.id,
                start_iso: startIso, end_iso: endIso,
                symbols: symbols.split(',').map(s => s.trim()).filter(Boolean),
                train_days: trainDays, oos_days: oosDays, step_days: stepDays,
              });
              setResult(r);
            }}
          >
            {validate.isPending ? '跑 WF 中…' : '开始验证'}
          </PrimaryButton>
        </div>
      </div>
    </Modal>
  );
}
