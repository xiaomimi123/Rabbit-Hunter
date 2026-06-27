/**
 * BacktestPage — V3 重写 (2026-06-27)。
 *
 * Walk-forward 报告列表 + 选中报告的 KPI 摘要 + entries 展开。
 */
import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, FlaskConical } from 'lucide-react';
import {
  useWalkforwardReports,
  useWalkforwardReport,
} from '../../hooks/api/useV5Walkforward';

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

function Badge({ tone, children }: { tone: 'ok' | 'fail' | 'mute' | 'amber'; children: React.ReactNode }) {
  const map = {
    ok:    'text-gain bg-gain/10 border border-gain/30',
    fail:  'text-loss bg-loss/10 border border-loss/30',
    amber: 'text-amber bg-amber-soft border border-amber/30',
    mute:  'text-v3muted bg-[#1a232d] border border-line',
  };
  return (
    <span className={`text-[10.5px] px-1.5 py-0.5 rounded font-semibold tracking-[0.02em] ${map[tone]}`}>
      {children}
    </span>
  );
}

export function BacktestPage() {
  const list = useWalkforwardReports();
  const [selected, setSelected] = useState<string | null>(null);
  const report = useWalkforwardReport(selected);

  // 首次自动选第一个
  useEffect(() => {
    if (!selected && list.data?.reports?.length) {
      setSelected(list.data.reports[0].name);
    }
  }, [list.data, selected]);

  const reports = list.data?.reports ?? [];

  return (
    <div className="px-6 pb-10 pt-5">
      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-3.5">
        {/* ── 报告列表 ─────────────────────────────────────── */}
        <Card pad0>
          <div className="flex items-center justify-between px-4 pt-4 pb-2">
            <h3 className="text-xs font-medium text-v3muted uppercase tracking-[0.06em]">报告列表</h3>
            <span className="text-[10px] text-v3faint font-mono">{reports.length}</span>
          </div>
          {reports.length === 0 ? (
            <div className="py-10 text-center text-sm text-v3faint">无报告 (尝试跑 scripts/walkforward.py)</div>
          ) : (
            <div className="max-h-[700px] overflow-y-auto">
              {reports.map((r) => {
                const isActive = r.name === selected;
                const pf = r.net_profit_factor;
                const passed = r.kpi_passes_doc_15_2;
                return (
                  <button
                    key={r.name}
                    onClick={() => setSelected(r.name)}
                    className={`w-full text-left px-4 py-3 border-b border-line-soft transition hover:bg-raised ${isActive ? 'bg-raised' : ''}`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="font-mono text-[12px] text-v3text truncate flex-1">{r.name.replace(/\.json$/, '')}</span>
                      {passed === true && <Badge tone="ok">PASS</Badge>}
                      {passed === false && <Badge tone="fail">FAIL</Badge>}
                      {passed == null && <Badge tone="mute">—</Badge>}
                    </div>
                    <div className="flex items-center gap-3 text-[11px] font-mono text-v3muted">
                      <span>n={r.n_oos_trades ?? '—'}</span>
                      <span className={pf != null && pf >= 1.5 ? 'text-gain' : pf != null && pf >= 1 ? 'text-amber' : 'text-loss'}>
                        PF {pf != null ? pf.toFixed(2) : '—'}
                      </span>
                    </div>
                    {(r.period_start || r.setup_filter) && (
                      <div className="mt-1 text-[10px] text-v3faint truncate">
                        {r.period_start?.slice(0, 10)} → {r.period_end?.slice(0, 10)}
                        {r.setup_filter && <> · {r.setup_filter}</>}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </Card>

        {/* ── 选中报告详情 ─────────────────────────────────── */}
        <div>
          {!selected ? (
            <Card className="py-20 text-center">
              <FlaskConical className="h-8 w-8 text-v3faint mx-auto mb-3" />
              <div className="text-sm text-v3muted">从左侧选一份报告查看</div>
            </Card>
          ) : !report.data ? (
            <Card className="py-20 text-center text-sm text-v3faint">加载中…</Card>
          ) : (
            <ReportDetail data={report.data} />
          )}
        </div>
      </div>
    </div>
  );
}

function ReportDetail({ data }: { data: any }) {
  const summary = data.summary_net ?? data.summary_gross ?? {};
  const passed = data.pass_doc_kpi?.kpi_passes_doc_15_2;
  const pf = summary.profit_factor;
  const entries = data.oos_combined_entries ?? data.entries ?? [];

  return (
    <div>
      {/* 4 KPI */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3.5">
        <MetricCard
          label="Profit Factor"
          value={pf != null ? pf.toFixed(2) : '—'}
          valueColor={pf != null && pf >= 1.5 ? 'text-gain' : pf != null && pf >= 1 ? 'text-amber' : 'text-loss'}
          sub={passed === true ? <span className="text-gain">KPI PASS</span> : passed === false ? <span className="text-loss">KPI FAIL</span> : null}
        />
        <MetricCard
          label="样本数 n"
          value={summary.n ?? '—'}
          sub={<span className="text-v3faint">OOS only</span>}
        />
        <MetricCard
          label="平均 R"
          value={summary.avg_r != null ? `${summary.avg_r >= 0 ? '+' : ''}${summary.avg_r.toFixed(3)}` : '—'}
          valueColor={summary.avg_r >= 0 ? 'text-gain' : 'text-loss'}
        />
        <MetricCard
          label="胜率"
          value={summary.win_rate != null ? `${Math.round(summary.win_rate * 100)}%` : '—'}
        />
      </div>

      {/* 配置信息 */}
      <Card className="mb-3.5">
        <h3 className="text-xs font-medium text-v3muted uppercase tracking-[0.06em] mb-3">配置</h3>
        <div className="grid grid-cols-2 gap-y-2 gap-x-6 text-[12px]">
          <div className="flex justify-between border-b border-line-soft pb-1.5">
            <span className="text-v3muted">期间</span>
            <span className="font-mono text-v3text text-[11px]">
              {(data.config?.period_start ?? data.period_start)?.slice(0, 10)} → {(data.config?.period_end ?? data.period_end)?.slice(0, 10)}
            </span>
          </div>
          <div className="flex justify-between border-b border-line-soft pb-1.5">
            <span className="text-v3muted">Train/OOS/Step</span>
            <span className="font-mono text-v3text">
              {data.config?.train_days ?? '—'}/{data.config?.oos_days ?? '—'}/{data.config?.step_days ?? '—'}
            </span>
          </div>
          <div className="flex justify-between border-b border-line-soft pb-1.5">
            <span className="text-v3muted">Symbols</span>
            <span className="font-mono text-v3text text-[11px]">
              {(data.config?.symbols ?? []).length} 个
            </span>
          </div>
          <div className="flex justify-between border-b border-line-soft pb-1.5">
            <span className="text-v3muted">Setup filter</span>
            <span className="font-mono text-v3text text-[11px]">
              {data.config?.setup_filter ?? '所有'}
            </span>
          </div>
        </div>
      </Card>

      {/* Entries 列表 */}
      <Card pad0>
        <div className="flex items-center justify-between px-4 pt-4 pb-2">
          <h3 className="text-xs font-medium text-v3muted uppercase tracking-[0.06em]">
            OOS Trade Entries
          </h3>
          <span className="text-[10px] text-v3faint font-mono">{entries.length} 笔</span>
        </div>
        {entries.length === 0 ? (
          <div className="py-8 text-center text-sm text-v3faint">无 entries</div>
        ) : (
          <div className="max-h-[400px] overflow-y-auto">
            <table className="w-full font-mono text-[12px]">
              <thead className="text-[10px] uppercase tracking-[0.06em] text-v3faint sticky top-0 bg-panel">
                <tr className="border-b border-line-soft">
                  <th className="px-3 py-2 text-left font-normal">入场</th>
                  <th className="px-3 py-2 text-left font-normal">标的</th>
                  <th className="px-3 py-2 text-left font-normal">Setup</th>
                  <th className="px-3 py-2 text-right font-normal">Net R</th>
                  <th className="px-3 py-2 text-left font-normal">出场</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {entries.slice(0, 200).map((e: any, i: number) => {
                  const r = e.net_realized_r ?? e.realized_r ?? 0;
                  const isWin = r > 0;
                  return (
                    <tr key={i} className="text-v3text">
                      <td className="px-3 py-2 text-v3faint text-[11px]">
                        {e.entry_ts ? new Date(e.entry_ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}
                      </td>
                      <td className="px-3 py-2">{(e.symbol ?? '').replace('USDT', '')}</td>
                      <td className="px-3 py-2 text-v3muted text-[11px] truncate max-w-[200px]">
                        {e.setup_type ?? '—'}
                      </td>
                      <td className={`px-3 py-2 text-right ${isWin ? 'text-gain' : 'text-loss'}`}>
                        {isWin ? '+' : ''}{r.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-v3faint text-[11px]">{e.exit_reason ?? '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
