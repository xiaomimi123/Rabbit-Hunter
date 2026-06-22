import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, FlaskConical, Terminal, FileJson } from 'lucide-react';
import {
  useWalkforwardReports, useWalkforwardReport, WFReportListItem,
} from '../../hooks/api/useV5Walkforward';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { MetricCard } from '../primitives-v3/MetricCard';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { Alert } from '../primitives-v3/Alert';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { cn } from '../primitives-v3/cn';

export function BacktestPage() {
  const list = useWalkforwardReports();
  const [selected, setSelected] = useState<string | null>(null);
  const report = useWalkforwardReport(selected);

  useEffect(() => {
    const r = list.data?.reports[0]?.name;
    if (r && !selected) setSelected(r);
  }, [list.data, selected]);

  const reports = list.data?.reports ?? [];

  return (
    <div className="space-y-6">
      <SectionTitle
        title="策略验证"
        subtitle="M6 walk-forward 报告 · 扣成本 net 视图 · 文档 §15 KPI 判定"
      />

      <Alert tone="info">
        <div className="text-sm leading-6">
          报告生成走 CLI:<code className="font-mono text-indigo-200">
            python -m scripts.walkforward --start 2026-01-01 --end 2026-06-01 --symbols BTC/USDT,ETH/USDT --out reports/wf_btc_eth.json
          </code>
          。可选参数:<code className="font-mono text-indigo-200">--setup-filter</code>(两个核心 setup 各自验证)、<code className="font-mono text-indigo-200">--cost-preset realistic|optimistic|pessimistic</code>。
        </div>
      </Alert>

      {list.isLoading && <LoadingSkeleton message="拉取报告列表…" />}
      {!list.isLoading && reports.length === 0 && (
        <Card>
          <div className="py-10 text-center">
            <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-zinc-800">
              <FileJson className="h-5 w-5 text-zinc-500" />
            </div>
            <div className="text-sm text-zinc-400">还没有 walk-forward 报告</div>
            <div className="mt-1 text-xs text-zinc-500">先用上面的命令生成第一份</div>
          </div>
        </Card>
      )}

      {reports.length > 0 && (
        <Card title="可用报告" subtitle={`共 ${reports.length} 份`}>
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {reports.map(r => (
              <ReportCard
                key={r.name}
                r={r}
                active={selected === r.name}
                onClick={() => setSelected(r.name)}
              />
            ))}
          </div>
        </Card>
      )}

      {report.data && (
        <ReportDetail report={report.data} />
      )}
    </div>
  );
}

function ReportCard({ r, active, onClick }: {
  r: WFReportListItem; active: boolean; onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-2xl border px-4 py-3 text-left transition',
        active
          ? 'border-indigo-500 bg-indigo-500/10'
          : 'border-zinc-800 bg-zinc-950/60 hover:border-zinc-700',
      )}
    >
      <div className="flex items-center gap-2 mb-2">
        <div className="font-mono text-sm text-zinc-100 truncate flex-1">{r.name}</div>
        {r.kpi_passes_doc_15_2 === true && <StatusPill tone="emerald" icon={<CheckCircle className="h-2.5 w-2.5" />}>PASS</StatusPill>}
        {r.kpi_passes_doc_15_2 === false && <StatusPill tone="rose" icon={<XCircle className="h-2.5 w-2.5" />}>FAIL</StatusPill>}
      </div>
      <div className="text-xs text-zinc-500 space-y-0.5">
        <div>{r.symbols?.join(', ') ?? '—'}</div>
        <div>{r.period_start?.slice(0, 10)} → {r.period_end?.slice(0, 10)}</div>
        {r.setup_filter && <div>setup: <span className="text-indigo-300">{r.setup_filter}</span></div>}
        <div>
          n={r.n_oos_trades ?? '—'} · net avg R=<span className={cn(
            (r.net_avg_r ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300',
          )}>{r.net_avg_r?.toFixed(3) ?? '—'}</span>
          {' · '}PF=<span className={cn(
            (r.net_profit_factor ?? 0) > 1 ? 'text-emerald-300' : 'text-rose-300',
          )}>{r.net_profit_factor?.toFixed(2) ?? '∞'}</span>
        </div>
      </div>
    </button>
  );
}

function ReportDetail({ report }: { report: any }) {
  const kpi = report.pass_doc_kpi;
  const gross = report.oos_summary;
  const net = report.oos_summary_net;

  return (
    <>
      <SectionTitle
        title={`报告详情:${(report.config.symbols ?? []).join(' / ')}${report.config.setup_filter ? ' · ' + report.config.setup_filter : ''}`}
        subtitle={`${report.config.start_iso?.slice(0, 10)} → ${report.config.end_iso?.slice(0, 10)} · ${report.windows.length} 窗口`}
        action={
          kpi.kpi_passes_doc_15_2
            ? <StatusPill tone="emerald" icon={<CheckCircle className="h-3 w-3" />}>文档 §15 KPI #2 PASS</StatusPill>
            : <StatusPill tone="rose" icon={<XCircle className="h-3 w-3" />}>FAIL</StatusPill>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="OOS 笔数" value={String(kpi.n_oos_trades)} hint="纯样本外" />
        <MetricCard
          label="net avg R"
          value={kpi.net_avg_r.toFixed(3)}
          trend={kpi.net_avg_r > 0 ? 'up' : 'down'}
          hint={`gross ${kpi.gross_avg_r.toFixed(3)}`}
        />
        <MetricCard
          label="net PF"
          value={kpi.net_profit_factor != null ? kpi.net_profit_factor.toFixed(2) : '∞'}
          trend={(kpi.net_profit_factor ?? 9) > 1 ? 'up' : 'down'}
          hint={kpi.gross_profit_factor != null ? `gross ${kpi.gross_profit_factor.toFixed(2)}` : 'gross ∞'}
        />
        <MetricCard
          label="net MaxDD"
          value={`${(net.max_drawdown_r ?? 0).toFixed(2)} R`}
          hint={`win rate ${Math.round((net.win_rate ?? 0) * 100)}%`}
        />
      </div>

      <Card title="扣前 / 扣后对照" subtitle="文档 §8 写实成本表">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                <th className="py-2 px-2"></th>
                <th className="py-2 px-2 text-right">n</th>
                <th className="py-2 px-2 text-right">win rate</th>
                <th className="py-2 px-2 text-right">avg R</th>
                <th className="py-2 px-2 text-right">total R</th>
                <th className="py-2 px-2 text-right">PF</th>
                <th className="py-2 px-2 text-right">MaxDD</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              <Row label="Gross(扣前)" s={gross} />
              <Row label="Net(扣成本后)" s={net} highlight />
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="窗口明细" subtitle={`${report.windows.length} 个滚动窗口`}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                <th className="py-2 px-2">#</th>
                <th className="py-2 px-2">训练段</th>
                <th className="py-2 px-2">OOS 段</th>
                <th className="py-2 px-2 text-right">入场</th>
                <th className="py-2 px-2 text-right">平仓</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {report.windows.map((w: any, i: number) => (
                <tr key={i} className="hover:bg-zinc-900/40">
                  <td className="py-2 px-2 font-mono text-xs text-zinc-500">{i + 1}</td>
                  <td className="py-2 px-2 font-mono text-xs text-zinc-400">
                    {w.train_start.slice(0, 10)} → {w.train_end.slice(0, 10)}
                  </td>
                  <td className="py-2 px-2 font-mono text-xs text-zinc-300">
                    {w.oos_start.slice(0, 10)} → {w.oos_end.slice(0, 10)}
                  </td>
                  <td className="py-2 px-2 text-right font-mono tabular-nums">{w.n_entries}</td>
                  <td className="py-2 px-2 text-right font-mono tabular-nums">{w.n_closed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        <FeatureCard
          icon={<FlaskConical className="h-5 w-5 text-indigo-300" />}
          title="窗口策略"
          desc={`训练 ${report.config.train_days}d · OOS ${report.config.oos_days}d · 步长 ${report.config.step_days}d`}
        />
        <FeatureCard
          icon={<Terminal className="h-5 w-5 text-emerald-300" />}
          title="成本档位"
          desc={
            report.config.cost_config
              ? `fee ${(report.config.cost_config.maker_fee_rate * 100).toFixed(3)}% maker / ${(report.config.cost_config.taker_fee_rate * 100).toFixed(3)}% taker · slip ${(report.config.cost_config.slippage_pct * 100).toFixed(3)}%`
              : '—'
          }
        />
        <FeatureCard
          icon={<FileJson className="h-5 w-5 text-amber-300" />}
          title="setup filter"
          desc={report.config.setup_filter ? `仅统计 ${report.config.setup_filter}` : '全部 setup 混合'}
        />
      </div>
    </>
  );
}

function Row({ label, s, highlight }: { label: string; s: any; highlight?: boolean }) {
  // 后端在没 net 数据时返回 {} — s 不是 null 但所有字段是 undefined。
  // 必须 require s.n 是个正整数才能渲染数字行。
  if (!s || typeof s.n !== 'number' || s.n === 0) {
    return <tr><td colSpan={7} className="py-3 text-center text-zinc-500 text-sm">{label}: 无数据</td></tr>;
  }
  const fix = (v: any, d: number) => (typeof v === 'number' ? v.toFixed(d) : '—');
  return (
    <tr className={highlight ? 'bg-indigo-500/[0.06]' : ''}>
      <td className="py-2.5 px-2 font-medium text-zinc-100">{label}</td>
      <td className="py-2.5 px-2 text-right font-mono tabular-nums">{s.n}</td>
      <td className="py-2.5 px-2 text-right font-mono tabular-nums">{fix((s.win_rate ?? 0) * 100, 0)}%</td>
      <td className={cn(
        'py-2.5 px-2 text-right font-mono tabular-nums',
        (s.avg_r ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300',
      )}>{fix(s.avg_r, 3)}</td>
      <td className={cn(
        'py-2.5 px-2 text-right font-mono tabular-nums',
        (s.total_r ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300',
      )}>{fix(s.total_r, 2)}</td>
      <td className="py-2.5 px-2 text-right font-mono tabular-nums">
        {s.profit_factor != null ? s.profit_factor.toFixed(2) : '∞'}
      </td>
      <td className="py-2.5 px-2 text-right font-mono tabular-nums text-rose-300">
        {fix(s.max_drawdown_r, 2)}
      </td>
    </tr>
  );
}

function FeatureCard({ icon, title, desc }: { icon: React.ReactNode; title: string; desc: string }) {
  return (
    <div className="rounded-3xl border border-zinc-800 bg-zinc-900/70 p-5 shadow-[0_24px_80px_rgba(0,0,0,0.25)]">
      <div className="flex items-center gap-2 mb-3">{icon}<div className="font-medium text-zinc-100">{title}</div></div>
      <div className="text-sm text-zinc-400 leading-relaxed">{desc}</div>
    </div>
  );
}
