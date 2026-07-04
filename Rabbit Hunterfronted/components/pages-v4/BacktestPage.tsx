/**
 * BacktestPage — v2 实验台 (2026-06-27)。
 *
 * 三块功能:
 *   1. 参数控制区(进场/出场/标的/期间/WF/成本下拉 + 运行按钮)
 *   2. 任务进度(轮询 /walkforward/jobs/{id} 直到 done/failed)
 *   3. 结果展示(判定横幅 + 收益区 + 风险区 + Setup 贡献区)
 */
import { useState, useMemo, useEffect } from 'react';
import { Play, CheckCircle, XCircle, FlaskConical, ShieldCheck, Loader2 } from 'lucide-react';
import {
  useWalkforwardReports,
  useWalkforwardReport,
  useRunWalkforward,
  useWalkforwardJob,
  useWalkforwardJobs,
} from '../../hooks/api/useV5Walkforward';
import type { WFRunRequest } from '../../hooks/api/useV5Walkforward';
import { Sparkline } from '../primitives/Sparkline';

// ─── 标的池 ────────────────────────────────────────────────
const PRESETS = {
  full_17: ['APTUSDT', 'ARBUSDT', 'ATOMUSDT', 'AVAXUSDT', 'BNBUSDT',
            'DOGEUSDT', 'DOTUSDT', 'FILUSDT', 'LINKUSDT', 'LTCUSDT',
            'NEARUSDT', 'PEPEUSDT', 'SOLUSDT', 'UNIUSDT', 'WLDUSDT',
            'XRPUSDT', 'ZECUSDT'],
  top_5: ['BNBUSDT', 'SOLUSDT', 'NEARUSDT', 'AVAXUSDT', 'ARBUSDT'],
  custom: [],
};

// ─── 小组件 ────────────────────────────────────────────────

function Card({ children, className = '', pad0 = false }: { children: React.ReactNode; className?: string; pad0?: boolean }) {
  return (
    <section className={`rounded-[10px] border border-line-soft bg-panel ${pad0 ? 'p-0 overflow-hidden' : 'p-4'} ${className}`}>{children}</section>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px] uppercase tracking-[0.07em] text-v3faint mb-1.5">{children}</div>;
}

function Select<T extends string>({ value, onChange, options, disabled }: {
  value: T; onChange: (v: T) => void;
  options: { value: T; label: string }[]; disabled?: boolean;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      disabled={disabled}
      className="w-full rounded-md border border-line bg-[#0E141A] px-2.5 py-1.5 font-mono text-[12px] text-v3text outline-none focus:border-amber transition disabled:opacity-50"
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

function NumInput({ value, onChange, disabled, min, max }: {
  value: number; onChange: (v: number) => void;
  disabled?: boolean; min?: number; max?: number;
}) {
  return (
    <input
      type="number"
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      disabled={disabled}
      min={min}
      max={max}
      className="w-full rounded-md border border-line bg-[#0E141A] px-2.5 py-1.5 font-mono text-[12px] text-v3text outline-none focus:border-amber transition disabled:opacity-50"
    />
  );
}

function DateInput({ value, onChange, disabled }: {
  value: string; onChange: (v: string) => void; disabled?: boolean;
}) {
  // value is ISO with Z, input takes YYYY-MM-DD
  const dateOnly = value.slice(0, 10);
  return (
    <input
      type="date"
      value={dateOnly}
      onChange={(e) => onChange(e.target.value + 'T00:00:00Z')}
      disabled={disabled}
      className="w-full rounded-md border border-line bg-[#0E141A] px-2.5 py-1.5 font-mono text-[12px] text-v3text outline-none focus:border-amber transition disabled:opacity-50"
    />
  );
}

function MetricCard({ label, value, sub, valueColor = 'text-v3text' }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; valueColor?: string;
}) {
  return (
    <div className="rounded-md border border-line-soft bg-[#0E141A] p-3">
      <div className="text-[10px] uppercase tracking-[0.07em] text-v3faint">{label}</div>
      <div className={`mt-1.5 font-semibold leading-none font-mono text-[20px] ${valueColor}`}>{value}</div>
      {sub && <div className="mt-1 text-[10.5px] text-v3muted">{sub}</div>}
    </div>
  );
}

function Pill({ tone, children }: { tone: 'ok' | 'fail' | 'amber' | 'mute'; children: React.ReactNode }) {
  const map = {
    ok:    'text-gain bg-gain/10 border-gain/30',
    fail:  'text-loss bg-loss/10 border-loss/30',
    amber: 'text-amber bg-amber-soft border-amber/30',
    mute:  'text-v3muted bg-[#1a232d] border-line',
  };
  return <span className={`text-[10.5px] px-1.5 py-0.5 rounded font-semibold tracking-[0.02em] border ${map[tone]}`}>{children}</span>;
}

// ─── 默认参数 ──────────────────────────────────────────────
const DEFAULT_PARAMS: WFRunRequest = {
  variant: 'B',
  start: '2026-01-01T00:00:00Z',
  end: '2026-03-31T23:59:59Z',
  symbols: PRESETS.full_17,
  train_days: 60,
  oos_days: 14,
  step_days: 14,
  exit_strategy: 'baseline',
  max_hold_minutes: 240,
  cost_preset: 'realistic',
  cross_threshold_pct: 0,
  a_proximity_pct: 0.20,
};

// ─── 主页 ──────────────────────────────────────────────────

export function BacktestPage() {
  const [params, setParams] = useState<WFRunRequest>(DEFAULT_PARAMS);
  const [symbolPreset, setSymbolPreset] = useState<keyof typeof PRESETS>('full_17');
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [selectedReport, setSelectedReport] = useState<string | null>(null);

  const runMutation = useRunWalkforward();
  const jobQuery = useWalkforwardJob(activeJobId);
  const jobsQuery = useWalkforwardJobs(10);
  const reports = useWalkforwardReports();
  const report = useWalkforwardReport(selectedReport);

  // 任务完成时自动选中报告
  // Finding 19: selectedReport 加入 deps 满足 exhaustive-deps lint。
  // 注:若用户在 job 完成前手动切换报告,该 effect 仍会 overwrite —— 属于设计层
  //     问题(需引入"已手动选择过"flag),不在本 P2 fix 范围。
  useEffect(() => {
    if (jobQuery.data?.status === 'done' && jobQuery.data?.report_name && selectedReport !== jobQuery.data.report_name) {
      setSelectedReport(jobQuery.data.report_name);
      reports.refetch();
    }
  }, [jobQuery.data?.status, jobQuery.data?.report_name, selectedReport]);

  const isRunning = jobQuery.data?.status === 'queued' || jobQuery.data?.status === 'running';

  const handleRun = async () => {
    try {
      const res = await runMutation.mutateAsync(params);
      setActiveJobId(res.job_id);
    } catch (e: any) {
      alert(`运行失败: ${e?.message || e}`);
    }
  };

  // 当 symbol preset 切换时同步 params.symbols
  useEffect(() => {
    if (symbolPreset !== 'custom') {
      setParams(p => ({ ...p, symbols: PRESETS[symbolPreset] }));
    }
  }, [symbolPreset]);

  return (
    <div className="px-6 pb-10 pt-5">
      {/* ── 1. 参数控制区 ───────────────────────────────────── */}
      <Card className="mb-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-medium text-v3muted uppercase tracking-[0.06em]">
            <FlaskConical className="inline h-3.5 w-3.5 mr-1.5 text-amber" />
            实验参数
          </h3>
          <div className="flex items-center gap-2.5">
            <Pill tone="ok"><ShieldCheck className="inline h-3 w-3 mr-1" />扣真实成本</Pill>
            <Pill tone="ok"><ShieldCheck className="inline h-3 w-3 mr-1" />样本外验证</Pill>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div>
            <Label>进场变体</Label>
            <Select<'A' | 'B' | 'C'>
              value={params.variant}
              onChange={(v) => setParams(p => ({ ...p, variant: v }))}
              disabled={isRunning}
              options={[
                { value: 'A', label: 'A 埋伏 (DIF/DEA gap 收窄)' },
                { value: 'B', label: 'B 金叉 (4h 零轴下,推荐)' },
                { value: 'C', label: 'C 早金叉 (含强度阈值)' },
              ]}
            />
          </div>
          <div>
            <Label>出场策略</Label>
            <Select<'baseline' | 'vegas_full' | 'vegas_sl_only'>
              value={params.exit_strategy}
              onChange={(v) => setParams(p => ({ ...p, exit_strategy: v }))}
              disabled={isRunning}
              options={[
                { value: 'baseline', label: 'baseline (1.5/2.5×ATR)' },
                { value: 'vegas_full', label: 'vegas_full (通道)' },
                { value: 'vegas_sl_only', label: 'vegas_sl_only (混合)' },
              ]}
            />
          </div>
          <div>
            <Label>最长持仓 (分钟)</Label>
            <NumInput
              value={params.max_hold_minutes}
              onChange={(v) => setParams(p => ({ ...p, max_hold_minutes: v }))}
              disabled={isRunning}
              min={15} max={1440}
            />
          </div>
          <div>
            <Label>成本模型</Label>
            <Select<'realistic' | 'optimistic' | 'pessimistic'>
              value={params.cost_preset}
              onChange={(v) => setParams(p => ({ ...p, cost_preset: v }))}
              disabled={isRunning}
              options={[
                { value: 'realistic', label: 'realistic (OKX 0.17%)' },
                { value: 'optimistic', label: 'optimistic' },
                { value: 'pessimistic', label: 'pessimistic' },
              ]}
            />
          </div>

          <div>
            <Label>标的池</Label>
            <Select<keyof typeof PRESETS>
              value={symbolPreset}
              onChange={setSymbolPreset}
              disabled={isRunning}
              options={[
                { value: 'full_17', label: '完整 17 (验证池)' },
                { value: 'top_5', label: 'Top 5 (BNB/SOL/NEAR/AVAX/ARB)' },
                { value: 'custom', label: '自定义' },
              ]}
            />
          </div>
          <div>
            <Label>开始日期</Label>
            <DateInput value={params.start} onChange={(v) => setParams(p => ({ ...p, start: v }))} disabled={isRunning} />
          </div>
          <div>
            <Label>结束日期</Label>
            <DateInput value={params.end} onChange={(v) => setParams(p => ({ ...p, end: v }))} disabled={isRunning} />
          </div>
          <div>
            <Label>Train / OOS / Step (天)</Label>
            <div className="flex gap-1.5">
              <NumInput value={params.train_days} onChange={(v) => setParams(p => ({ ...p, train_days: v }))} disabled={isRunning} min={1} />
              <NumInput value={params.oos_days} onChange={(v) => setParams(p => ({ ...p, oos_days: v }))} disabled={isRunning} min={1} />
              <NumInput value={params.step_days} onChange={(v) => setParams(p => ({ ...p, step_days: v }))} disabled={isRunning} min={1} />
            </div>
          </div>
        </div>

        {symbolPreset === 'custom' && (
          <div className="mb-3">
            <Label>自定义标的池 (逗号分隔,e.g. NEARUSDT,ARBUSDT)</Label>
            <input
              type="text"
              value={params.symbols.join(',')}
              onChange={(e) => setParams(p => ({ ...p, symbols: e.target.value.split(',').map(s => s.trim()).filter(Boolean) }))}
              disabled={isRunning}
              className="w-full rounded-md border border-line bg-[#0E141A] px-2.5 py-1.5 font-mono text-[12px] text-v3text outline-none focus:border-amber transition disabled:opacity-50"
            />
          </div>
        )}

        <div className="flex items-center justify-between border-t border-line-soft pt-3 mt-2">
          <div className="text-[11px] text-v3muted font-mono">
            {params.symbols.length} 标的 · {params.start.slice(0,10)} → {params.end.slice(0,10)}
          </div>
          <button
            type="button"
            onClick={handleRun}
            disabled={isRunning || runMutation.isPending}
            className={`inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-semibold transition ${
              isRunning
                ? 'bg-amber/20 text-amber cursor-wait'
                : 'bg-amber text-ink hover:bg-amber-dim'
            }`}
          >
            {isRunning ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> {jobQuery.data?.status === 'queued' ? '排队中' : '运行中...'}</>
            ) : (
              <><Play className="h-4 w-4" /> 运行 Walk-Forward</>
            )}
          </button>
        </div>
      </Card>

      {/* ── 2. 任务进度 (运行中显示) ────────────────────────── */}
      {activeJobId && jobQuery.data && (
        <Card className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-medium text-v3muted uppercase tracking-[0.06em]">任务状态</h3>
            <Pill tone={jobQuery.data.status === 'done' ? 'ok' : jobQuery.data.status === 'failed' ? 'fail' : 'amber'}>
              {jobQuery.data.status.toUpperCase()}
            </Pill>
          </div>
          <div className="text-[11px] text-v3faint font-mono">
            job_id: {activeJobId.slice(0, 8)}... | started {jobQuery.data.started_at || '—'} | finished {jobQuery.data.finished_at || '—'}
          </div>
          {jobQuery.data.error && (
            <div className="mt-2 text-[12px] text-loss font-mono">错误: {jobQuery.data.error}</div>
          )}
          {jobQuery.data.stdout_tail && (
            <details className="mt-2">
              <summary className="cursor-pointer text-[11px] text-v3muted">stdout (最近 4KB)</summary>
              <pre className="mt-2 text-[10.5px] text-v3faint font-mono bg-ink rounded p-2 max-h-[200px] overflow-y-auto">{jobQuery.data.stdout_tail}</pre>
            </details>
          )}
        </Card>
      )}

      {/* ── 3. 结果展示 ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
        {/* 报告列表 sidebar */}
        <Card pad0>
          <div className="px-4 pt-4 pb-2">
            <h3 className="text-xs font-medium text-v3muted uppercase tracking-[0.06em]">
              历史报告 <span className="text-v3faint">({reports.data?.reports.length ?? 0})</span>
            </h3>
          </div>
          <div className="max-h-[640px] overflow-y-auto">
            {(reports.data?.reports ?? []).map(r => {
              const isActive = r.name === selectedReport;
              const pf = r.net_profit_factor;
              const passed = r.kpi_passes_doc_15_2;
              return (
                <button
                  key={r.name}
                  onClick={() => setSelectedReport(r.name)}
                  className={`w-full text-left px-4 py-2.5 border-b border-line-soft transition hover:bg-raised ${isActive ? 'bg-raised' : ''}`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="font-mono text-[11px] text-v3text truncate flex-1">{r.name}</span>
                    {passed === true && <Pill tone="ok">PASS</Pill>}
                    {passed === false && <Pill tone="fail">FAIL</Pill>}
                  </div>
                  <div className="text-[10px] text-v3muted font-mono">
                    n={r.n_oos_trades ?? '—'} · PF {pf != null ? pf.toFixed(2) : '—'}
                  </div>
                </button>
              );
            })}
          </div>
        </Card>

        {/* 选中报告详情 */}
        <div>
          {!selectedReport ? (
            <Card className="py-16 text-center">
              <FlaskConical className="h-10 w-10 text-v3faint mx-auto mb-3" />
              <div className="text-sm text-v3muted">运行新实验 或 从左侧选历史报告</div>
            </Card>
          ) : !report.data ? (
            <Card className="py-16 text-center text-sm text-v3faint">报告加载中…</Card>
          ) : (
            <ReportDetail data={report.data} />
          )}
        </div>
      </div>
    </div>
  );
}

// ─── 报告详情:判定横幅 + 收益区 + 风险区 + Setup 贡献区 ─────

function ReportDetail({ data }: { data: any }) {
  const summary = data.oos_summary_net || data.summary_net || data.oos_net || data.summary_gross || {};
  const passed = data.pass_doc_kpi?.kpi_passes_doc_15_2;
  const pf = summary.profit_factor ?? summary.pf;
  const n = summary.n;
  const winR = summary.win_rate;
  const avgR = summary.avg_r;
  const maxDD = summary.max_drawdown_r ?? summary.max_dd_r;

  const entries = data.oos_combined_entries ?? data.oos_entries ?? [];

  // exit reason 分布 + R
  const exitDist = useMemo(() => {
    const c: Record<string, { n: number; netR: number; wins: number }> = {};
    for (const e of entries as any[]) {
      const r = e.net_r ?? e.net_realized_r ?? 0;
      const k = e.exit_reason ?? 'UNKNOWN';
      if (!c[k]) c[k] = { n: 0, netR: 0, wins: 0 };
      c[k].n++;
      c[k].netR += r;
      if (r > 0) c[k].wins++;
    }
    return c;
  }, [entries]);

  const tpHitPct = entries.length > 0 ? (exitDist['TP_HIT']?.n ?? 0) / entries.length * 100 : 0;

  // 累计 R 曲线 + 水下曲线
  const { equityCurve, underwaterCurve, maxDDFromCurve, longestLossStreak } = useMemo(() => {
    const sorted = [...entries].sort((a, b) => (a.entry_ts ?? 0) - (b.entry_ts ?? 0));
    let cum = 0;
    let peak = 0;
    let maxDD_local = 0;
    let lossStreak = 0;
    let curStreak = 0;
    const eq: number[] = [0];
    const uw: number[] = [0];
    for (const e of sorted) {
      const r = e.net_r ?? e.net_realized_r ?? 0;
      cum += r;
      peak = Math.max(peak, cum);
      const dd = cum - peak;
      eq.push(cum);
      uw.push(dd);
      maxDD_local = Math.min(maxDD_local, dd);
      if (r < 0) { curStreak++; lossStreak = Math.max(lossStreak, curStreak); }
      else curStreak = 0;
    }
    return { equityCurve: eq, underwaterCurve: uw, maxDDFromCurve: maxDD_local, longestLossStreak: lossStreak };
  }, [entries]);

  // 收益回撤比
  const totalR = equityCurve[equityCurve.length - 1] ?? 0;
  const rrRatio = maxDDFromCurve < 0 ? totalR / Math.abs(maxDDFromCurve) : 0;

  // Setup 贡献
  const setupContrib = useMemo(() => {
    const m: Record<string, { n: number; netR: number; wins: number }> = {};
    for (const e of entries as any[]) {
      const s = e.setup_type ?? 'unknown';
      if (!m[s]) m[s] = { n: 0, netR: 0, wins: 0 };
      m[s].n++;
      m[s].netR += (e.net_r ?? e.net_realized_r ?? 0);
      if ((e.net_r ?? e.net_realized_r ?? 0) > 0) m[s].wins++;
    }
    return Object.entries(m).map(([k, v]) => ({ setup: k, ...v, winR: v.wins / v.n })).sort((a, b) => b.netR - a.netR);
  }, [entries]);

  // 判定文案
  const verdict = (() => {
    if (passed === true) return { tone: 'ok' as const, title: 'KPI PASS', sub: '通过宪法 §15.2 验收,可考虑切实战' };
    if (passed === false) return { tone: 'fail' as const, title: 'KPI FAIL', sub: '未通过验收,不建议切实战' };
    if (pf != null && pf >= 1.3 && n >= 30 && maxDDFromCurve > -20) return { tone: 'ok' as const, title: 'PF 达标 + 样本足', sub: `PF ${pf.toFixed(2)} · n=${n} · maxDD ${maxDDFromCurve.toFixed(1)}R` };
    if (pf != null && pf < 1.0) return { tone: 'fail' as const, title: 'PF 不达标', sub: `Net PF ${pf.toFixed(2)} < 1.0,扣成本后亏损` };
    return { tone: 'amber' as const, title: '边界水平', sub: `PF ${pf?.toFixed(2) ?? '—'} · n=${n}`};
  })();

  return (
    <div className="flex flex-col gap-4">
      {/* 判定横幅 */}
      <div className={`rounded-[10px] border p-4 ${
        verdict.tone === 'ok' ? 'border-gain/40 bg-gain/5' :
        verdict.tone === 'fail' ? 'border-loss/40 bg-loss/5' :
        'border-amber/40 bg-amber-soft'
      }`}>
        <div className="flex items-center gap-2">
          {verdict.tone === 'ok' && <CheckCircle className="h-5 w-5 text-gain" />}
          {verdict.tone === 'fail' && <XCircle className="h-5 w-5 text-loss" />}
          {verdict.tone === 'amber' && <FlaskConical className="h-5 w-5 text-amber" />}
          <span className={`text-sm font-semibold ${
            verdict.tone === 'ok' ? 'text-gain' : verdict.tone === 'fail' ? 'text-loss' : 'text-amber'
          }`}>{verdict.title}</span>
        </div>
        <div className="text-[11.5px] text-v3muted mt-1.5">{verdict.sub}</div>
      </div>

      {/* 收益区 */}
      <Card>
        <h3 className="text-xs font-medium text-v3muted uppercase tracking-[0.06em] mb-3">📈 收益区</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <MetricCard label="Net PF" value={pf != null ? pf.toFixed(2) : '—'} valueColor={pf >= 1.5 ? 'text-gain' : pf >= 1.0 ? 'text-amber' : 'text-loss'} />
          <MetricCard label="样本 n" value={n ?? '—'} />
          <MetricCard label="胜率" value={winR != null ? `${(winR * 100).toFixed(0)}%` : '—'} />
          <MetricCard label="TP 命中率" value={`${tpHitPct.toFixed(0)}%`} valueColor="text-gain" sub={`${exitDist['TP_HIT']?.n ?? 0} / ${entries.length} 笔`} />
        </div>
        <div className="text-[11px] text-v3muted mb-2">累计 R 曲线</div>
        {equityCurve.length > 1 ? (
          <Sparkline values={equityCurve} width={800} height={120} />
        ) : (
          <div className="text-[11px] text-v3faint">无数据</div>
        )}
      </Card>

      {/* 风险区 */}
      <Card>
        <h3 className="text-xs font-medium text-v3muted uppercase tracking-[0.06em] mb-3">🛡 风险区</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <MetricCard label="最大回撤 (R)" value={maxDDFromCurve.toFixed(2)} valueColor="text-loss" />
          <MetricCard label="收益回撤比" value={rrRatio.toFixed(2)} sub="总R / maxDD" />
          <MetricCard label="最长连亏 (笔)" value={longestLossStreak} valueColor={longestLossStreak >= 5 ? 'text-loss' : 'text-v3text'} />
          <MetricCard label="平均 R" value={avgR != null ? `${avgR >= 0 ? '+' : ''}${avgR.toFixed(3)}` : '—'} valueColor={avgR >= 0 ? 'text-gain' : 'text-loss'} />
        </div>
        <div className="text-[11px] text-v3muted mb-2">水下曲线 (距 peak R 距离,越下越糟)</div>
        {underwaterCurve.length > 1 ? (
          <Sparkline values={underwaterCurve} width={800} height={100} />
        ) : (
          <div className="text-[11px] text-v3faint">无数据</div>
        )}
      </Card>

      {/* Setup 贡献区 */}
      <Card pad0>
        <h3 className="px-4 pt-4 pb-2 text-xs font-medium text-v3muted uppercase tracking-[0.06em]">🧩 Setup 贡献</h3>
        {setupContrib.length === 0 ? (
          <div className="py-6 text-center text-sm text-v3faint">无数据</div>
        ) : (
          <table className="w-full font-mono text-[12px]">
            <thead className="text-[10px] uppercase tracking-[0.06em] text-v3faint">
              <tr className="border-b border-line-soft">
                <th className="px-4 py-2 text-left font-normal">Setup</th>
                <th className="px-4 py-2 text-right font-normal">笔数</th>
                <th className="px-4 py-2 text-right font-normal">胜率</th>
                <th className="px-4 py-2 text-right font-normal">总 Net R</th>
                <th className="px-4 py-2 text-right font-normal">avg R</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {setupContrib.map(s => (
                <tr key={s.setup} className="text-v3text">
                  <td className="px-4 py-2 text-v3muted truncate max-w-[280px]">{s.setup}</td>
                  <td className="px-4 py-2 text-right">{s.n}</td>
                  <td className="px-4 py-2 text-right">{(s.winR * 100).toFixed(0)}%</td>
                  <td className={`px-4 py-2 text-right ${s.netR >= 0 ? 'text-gain' : 'text-loss'}`}>
                    {s.netR >= 0 ? '+' : ''}{s.netR.toFixed(2)}
                  </td>
                  <td className={`px-4 py-2 text-right ${s.netR / s.n >= 0 ? 'text-gain' : 'text-loss'}`}>
                    {(s.netR / s.n).toFixed(3)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
