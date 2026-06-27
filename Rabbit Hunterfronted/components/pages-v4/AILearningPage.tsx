/**
 * AILearningPage — UI 原型 2026-06-27 落地版本。
 *
 * 4 指标 (反思样本/AI 否决率/记忆库/AI 健康) +
 * 反思日志 (赢/亏/跳过 + 归因 + 标签) +
 * Setup 表现表 + 失败模式分布。
 */
import { useMemo } from 'react';
import {
  useV5Reflections,
  useV5FailureTaxonomy,
  useV5SetupPerformance,
} from '../../hooks/api/useV5Reflections';
import { useV5TraderKpi } from '../../hooks/api/useV5TraderKpi';

function Card({ children, className = '', pad0 = false }: { children: React.ReactNode; className?: string; pad0?: boolean }) {
  return (
    <section className={`rounded-[10px] border border-line-soft bg-panel ${pad0 ? 'p-0 overflow-hidden' : 'p-4'} ${className}`}>
      {children}
    </section>
  );
}

function MetricCard({ label, value, sub, valueColor = 'text-v3text', smallValue = false }: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  valueColor?: string;
  smallValue?: boolean;
}) {
  return (
    <Card>
      <div className="text-[11px] uppercase tracking-[0.07em] text-v3faint">{label}</div>
      <div className={`mt-2 font-semibold leading-none font-mono ${smallValue ? 'text-[18px]' : 'text-[26px]'} ${valueColor}`}>
        {value}
      </div>
      {sub && <div className="mt-1.5 text-[11.5px] text-v3muted">{sub}</div>}
    </Card>
  );
}

function Verdict({ outcome, r }: { outcome?: string; r?: number | null }) {
  if (outcome === 'WIN' || (r != null && r > 0)) {
    return <span className="text-[10.5px] px-1.5 py-0.5 rounded font-semibold text-gain bg-gain/10 border border-gain/30">赢单 {r != null ? `${r >= 0 ? '+' : ''}${r.toFixed(2)}R` : ''}</span>;
  }
  if (outcome === 'LOSS' || (r != null && r < -0.3)) {
    return <span className="text-[10.5px] px-1.5 py-0.5 rounded font-semibold text-loss bg-loss/10 border border-loss/30">亏单 {r != null ? `${r.toFixed(2)}R` : ''}</span>;
  }
  return <span className="text-[10.5px] px-1.5 py-0.5 rounded font-semibold text-v3muted bg-v3muted/10 border border-v3muted/30">{outcome === 'SCRATCH' ? '微亏' : '跳过'} {r != null ? `${r.toFixed(2)}R` : ''}</span>;
}

function MiniTag({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded border border-line-soft text-v3muted bg-[#0E141A]">
      {children}
    </span>
  );
}

export function AILearningPage() {
  const reflections = useV5Reflections(20);
  const taxonomy = useV5FailureTaxonomy();
  const setupPerf = useV5SetupPerformance();
  const kpi = useV5TraderKpi(30, 24);

  const reflList = reflections.data?.data ?? [];

  // 计算 4 指标
  const totalReflections = reflList.length;
  const aiVetos = useMemo(() => {
    // 估计:reflections 里 outcome=SKIP 或 AI 否决相关
    return reflList.filter((r: any) => r.outcome_class === 'SKIP' || /AI否决|AI_REJECT/.test(r.why_entered ?? '')).length;
  }, [reflList]);
  const vetosPct = totalReflections > 0 ? Math.round((aiVetos / totalReflections) * 100) : 0;

  // 记忆库数 — 用 reflections 总数兜底 (实际是 Vector Store 条目,需要专 endpoint)
  const memoryCount = totalReflections;

  // AI 健康
  const aiHealth = kpi.data?.ai_health;
  const aiOnline = (aiHealth?.real_responses ?? 0) > 0 && (aiHealth?.fallback_passthrough ?? 0) === 0;

  // setup 表现 — 按 total_r 降序
  const setups = useMemo(() => {
    const arr = (setupPerf.data?.data ?? []).slice();
    arr.sort((a: any, b: any) => (b.total_realized_r ?? 0) - (a.total_realized_r ?? 0));
    return arr;
  }, [setupPerf.data]);

  // 失败模式分布 — 用 reflections 聚合
  const failureDistribution = useMemo(() => {
    const m: Record<string, number> = {};
    for (const r of reflList as any[]) {
      if (r.failure_mode_key) {
        m[r.failure_mode_key] = (m[r.failure_mode_key] ?? 0) + 1;
      }
    }
    const total = Object.values(m).reduce((a, b) => a + b, 0) || 1;
    return Object.entries(m)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([key, count]) => ({ key, count, pct: Math.round((count / total) * 100) }));
  }, [reflList]);

  const failureLabels: Record<string, string> = {
    late_entry_signal_decay: '入场迟 信号衰减',
    macd_false_cross: '假反转 接飞刀',
    against_4h_trend_no_funding_filter: '逆 4h 趋势 无 funding 滤',
    chase_after_3pct_move: '追 3% 涨幅',
    sl_too_tight_in_high_atr: '高 ATR 下 SL 太紧',
  };

  // setup 最大 |R| 用于横条 width
  const maxAbsR = useMemo(() => {
    return Math.max(0.01, ...setups.map((s: any) => Math.abs(s.total_realized_r ?? 0)));
  }, [setups]);

  return (
    <div className="px-6 pb-10 pt-5">
      {/* ── 4 指标 ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mb-5">
        <MetricCard
          label="反思样本"
          value={totalReflections}
          sub={<span className="text-v3faint">平仓后自动归因</span>}
        />
        <MetricCard
          label="AI 二次否决率"
          value={<>{vetosPct}<span className="text-[13px] text-v3faint">%</span></>}
          valueColor="text-info"
          sub={<span className="text-v3faint">规则放行后再筛</span>}
        />
        <MetricCard
          label="记忆库"
          value={memoryCount}
          sub={<span className="text-v3faint">反思条目 (Vector Store 待接)</span>}
        />
        <MetricCard
          label="AI 健康"
          smallValue
          value={<span className={aiOnline ? 'text-gain' : 'text-loss'}>{aiOnline ? '在线' : '降级'}</span>}
          sub={
            <span className="text-v3faint font-mono">
              {aiHealth ? `真实 ${aiHealth.real_responses}/${aiHealth.total_ai_calls}` : '加载…'}
            </span>
          }
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
        {/* ── 反思日志 ────────────────────────────────────── */}
        <Card pad0>
          <h3 className="px-4 pt-4 pb-1 text-xs font-medium text-v3muted flex items-center justify-between">
            <span>反思日志</span>
            <span className="text-[10px] text-v3faint">AI 在想什么</span>
          </h3>
          <div className="px-2 pb-2 max-h-[640px] overflow-y-auto">
            {reflList.length === 0 ? (
              <div className="py-12 text-center text-sm text-v3faint">尚无反思记录</div>
            ) : reflList.slice(0, 10).map((r: any) => {
              const when = r.created_at ? new Date(r.created_at).toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' }) : '—';
              return (
                <div key={r.id} className="flex gap-3 px-2 py-3 border-b border-line-soft last:border-b-0">
                  <div className="font-mono text-[11px] text-v3faint min-w-[36px] pt-0.5">{when}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <Verdict outcome={r.outcome_class} r={r.realized_r} />
                      <span className="font-mono text-[12px] font-semibold text-v3text">{r.symbol}</span>
                    </div>
                    <p className="text-[12.5px] leading-[1.55] text-v3text">
                      {r.correction_idea ?? r.what_actually_happened ?? r.why_entered ?? '—'}
                    </p>
                    <div className="flex gap-1.5 mt-2 flex-wrap">
                      {r.setup_type && <MiniTag>setup: {r.setup_type.slice(0, 20)}</MiniTag>}
                      {r.failure_mode_key && <MiniTag>{failureLabels[r.failure_mode_key] ?? r.failure_mode_key}</MiniTag>}
                      {r.ai_provider && <MiniTag>{r.ai_provider}</MiniTag>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        {/* ── Setup 表现 + 失败模式 ──────────────────────────── */}
        <div className="flex flex-col gap-3.5">
          <Card>
            <h3 className="text-xs font-medium text-v3muted mb-3 flex items-center justify-between">
              <span>Setup 类型表现</span>
              <span className="text-[10px] text-v3faint">扣成本 net</span>
            </h3>
            {setups.length === 0 ? (
              <div className="py-8 text-center text-sm text-v3faint">无数据</div>
            ) : (
              <div className="flex flex-col gap-2.5">
                {setups.slice(0, 8).map((s: any) => {
                  const r = s.total_realized_r ?? 0;
                  const isWin = r >= 0;
                  const isDisabled = s.status === 'disabled';
                  const barWidth = (Math.abs(r) / maxAbsR) * 100;
                  return (
                    <div key={s.setup_type} className="flex items-center justify-between gap-3 text-[12px]">
                      <span className={`truncate ${isDisabled ? 'text-v3faint' : 'text-v3text'}`}>
                        {s.setup_type} {isDisabled && '⊘'}
                      </span>
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`font-mono text-[12px] ${isWin ? 'text-gain' : 'text-loss'}`}>
                          {isWin ? '+' : ''}{r.toFixed(2)}R
                        </span>
                        <div className="w-[90px] h-1.5 rounded bg-[#0E141A] overflow-hidden">
                          <div
                            className={`h-full ${isWin ? 'bg-gain' : 'bg-loss'}`}
                            style={{ width: `${barWidth}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          <Card>
            <h3 className="text-xs font-medium text-v3muted mb-3">失败模式分布</h3>
            {failureDistribution.length === 0 ? (
              <div className="py-6 text-center text-sm text-v3faint">无失败模式数据</div>
            ) : (
              <div className="flex flex-col gap-2.5">
                {failureDistribution.map((f) => (
                  <div key={f.key} className="flex items-center justify-between text-[12px]">
                    <span className="text-v3text">{failureLabels[f.key] ?? f.key}</span>
                    <span className="font-mono text-v3muted">{f.pct}%</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
