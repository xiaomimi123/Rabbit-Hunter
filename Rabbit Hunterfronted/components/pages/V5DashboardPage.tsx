import { ReactNode, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useV5Dashboard } from '../../hooks/api/useV5Dashboard';
import { useV5SetupPerformance } from '../../hooks/api/useV5Reflections';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { KpiCard } from '../shared/KpiCard';
import { Aperture } from '../primitives/Aperture';
import { winRateOf, bySide, byStrategy, byExitReason, bestAndWorst, profitFactor, streaks } from './_winrate_helpers';
import { Term } from '../shared/Term';

const MAX_CONCURRENT = 3;

export function V5DashboardPage() {
  const q = useV5Dashboard();
  const navigate = useNavigate();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  if (q.isLoading) return <LoadingSkeleton message="拉取 24h 观测数据中…" />;
  const d = q.data;
  if (!d) return <PageWrap><EmptyState message="无数据" /></PageWrap>;

  const winRatePct = Math.round(d.win_rate_24h * 100);
  const pnlSeries = d.closed_24h
    .slice()
    .sort((a, b) => (a.exit_time || '').localeCompare(b.exit_time || ''))
    .reduce<{ time: string; cum: number; ts: number }[]>((acc, p) => {
      const prev = acc.length > 0 ? acc[acc.length - 1].cum : 0;
      const ts = p.exit_time ? new Date(p.exit_time).getTime() : 0;
      acc.push({
        time: p.exit_time ? new Date(p.exit_time).toLocaleTimeString('zh-CN', { hour12: false }) : '',
        cum: prev + (p.pnl_usdt ?? 0),
        ts,
      });
      return acc;
    }, []);

  const closed = d.closed_24h;
  const overall = winRateOf(closed);
  const sideStats = bySide(closed);
  const stratStats = byStrategy(closed);
  const reasonsStats = byExitReason(closed);
  const bw = bestAndWorst(closed);
  const pf = profitFactor(closed);
  const sk = streaks(closed);

  return (
    <PageWrap>
      <PageHead now={now} />

      {/* KPI 行 1.7:1:1:1 */}
      <section className="grid grid-cols-[1.7fr_1fr_1fr_1fr] max-[1100px]:grid-cols-[1.6fr_1fr] gap-px bg-hairline border border-hairline">
        <KpiCard
          hero
          title="胜率 · 7d"
          value={closed.length === 0 ? '—' : `${winRatePct}%`}
          foot={closed.length === 0 ? <NextCandleHint now={now} /> : `${closed.length} 笔已观测`}
        />
        <KpiCard
          title="累计盈亏"
          value={closed.length === 0 ? '—' : `${d.pnl_total_usdt >= 0 ? '+' : ''}${d.pnl_total_usdt.toFixed(2)}`}
          unit={closed.length === 0 ? '' : 'USDT'}
        />
        <KpiCard
          title="平均持仓"
          value={closed.length === 0 ? '—' : Math.round(d.avg_holding_minutes)}
          unit={closed.length === 0 ? '' : '分钟'}
        />
        <KpiCard
          title="活仓数"
          value={d.active_count}
          unit={`/ ${MAX_CONCURRENT}`}
          foot={<SlotStrip active={d.active_count} total={MAX_CONCURRENT} />}
        />
      </section>

      <Section
        title="Signal Funnel"
        meta="24h · 点击展开"
        marginalia={
          <>
            漏斗每层都可点。<em>{d.signals_24h > 0 ? Math.round((1 - d.signals_passed_and / d.signals_24h) * 100) : 0}%</em> 在合谋判断处被丢弃 — 这是引擎不浪费 LLM 算力的关键阀门。
          </>
        }
      >
        <Funnel
          steps={[
            { name: '扫描检测', count: d.signals_24h, scale: 1 },
            { name: '合谋通过', count: d.signals_passed_and, scale: d.signals_24h > 0 ? d.signals_passed_and / d.signals_24h : 0 },
            { name: '实际开仓', count: d.signals_executed, scale: d.signals_24h > 0 ? d.signals_executed / d.signals_24h : 0 },
          ]}
          onLayerClick={(name) => navigate(name === '实际开仓' ? '/v5/history?block_reason=EXECUTED' : '/v5/history')}
        />
      </Section>

      <Section
        title="PnL Trajectory"
        meta="累计 · 24h"
        marginalia={
          pnlSeries.length === 0
            ? <>当前 24h 内无平仓 — 一切静止,等待信号。</>
            : <>最近一笔平仓 <em>{pnlSeries[pnlSeries.length - 1].time}</em>,累计 <em>{pnlSeries[pnlSeries.length - 1].cum.toFixed(2)}</em> USDT。</>
        }
      >
        {pnlSeries.length === 0 ? (
          <EmptyState message="24h 内无平仓" />
        ) : (
          <PnlSparkline data={pnlSeries} />
        )}
      </Section>

      <Section
        title={`Outcome Breakdown · 24h (n=${closed.length})`}
        meta="按方向 / 策略 / 平仓"
        marginalia={
          closed.length > 0 && stratStats.auto && stratStats.manual && stratStats.auto.win_rate < stratStats.manual.win_rate
            ? <>自动比手动低 <em>{Math.round((stratStats.manual.win_rate - stratStats.auto.win_rate) * 100)}pt</em>。AI 卫门在做功 — 但还是手动入场的更耐看。</>
            : <>样本不足以判别策略差。</>
        }
      >
        {closed.length === 0 ? (
          <EmptyState message="24h 内无平仓样本" />
        ) : (
          <div className="grid grid-cols-[1.6fr_1fr] gap-9 max-[1100px]:grid-cols-1">
            <div>
              <BdGroup label="By side">
                <BdRow label="LONG · 做多" data={sideStats.long} />
                <BdRow label="SHORT · 做空" data={sideStats.short} />
              </BdGroup>
              <BdGroup label="By strategy">
                <BdRow label="Auto · 自动 (v5_rsi_macd)" data={stratStats.auto} />
                <BdRow label="Manual · 手动 (v5_manual)" data={stratStats.manual} />
              </BdGroup>
              <BdGroup label="By exit reason">
                {Object.entries(reasonsStats)
                  .sort((a, b) => b[1].count - a[1].count)
                  .map(([reason, br]) => (
                    <BdRow key={reason} label={reason} data={br} />
                  ))}
              </BdGroup>
            </div>
            <div>
              <BdGroup label="总览">
                <Stat label="样本">
                  <span className="text-sage">{overall.wins}W</span>
                  <span className="text-ivory-40 mx-1.5">/</span>
                  <span className="text-oxblood">{overall.losses}L</span>
                  <span className="text-ivory-40 text-[0.78rem] ml-2">{Math.round(overall.win_rate * 100)}% across all setups</span>
                </Stat>
                <Stat label={<><Term k="盈亏比">盈亏比</Term></>}>
                  {pf === null ? '∞' : pf.toFixed(2)}
                  <span className="text-ivory-40 text-[0.78rem] ml-2">gross win / gross loss</span>
                </Stat>
                <Stat label="最佳交易">
                  {bw.best && (bw.best.pnl_pct ?? 0) > 0
                    ? <span className="text-sage">{bw.best.symbol} <span className="text-[0.85rem]">+{(bw.best.pnl_pct ?? 0).toFixed(2)}%</span></span>
                    : <span className="text-ivory-40">—</span>}
                </Stat>
                <Stat label="最差交易">
                  {bw.worst && (bw.worst.pnl_pct ?? 0) < 0
                    ? <span className="text-oxblood">{bw.worst.symbol} <span className="text-[0.85rem]">{(bw.worst.pnl_pct ?? 0).toFixed(2)}%</span></span>
                    : <span className="text-ivory-40">—</span>}
                </Stat>
                <Stat label="连续胜负 · 当前 / 最大">
                  <span className="text-sage">{sk.maxWin}W</span>
                  <span className="text-ivory-40 mx-1.5">/</span>
                  <span className="text-oxblood">{sk.maxLoss}L</span>
                  {sk.current.side && (
                    <span className="text-ivory-40 text-[0.78rem] ml-2">
                      cur · {sk.current.len} {sk.current.side === 'W' ? '胜' : '败'}
                    </span>
                  )}
                </Stat>
              </BdGroup>
            </div>
          </div>
        )}
      </Section>

      <Section
        title="Setup Type · 7d"
        meta="funding 维度高亮"
        marginalia={<><em>funding_extreme_*</em> 是 V6 新接入的 alpha 维度 — 紫色 ✦ 标记,优先 watch。</>}
      >
        <SetupBreakdownTable />
      </Section>

      <Section
        title="Block Reason Distribution"
        meta="扫描未触发原因"
        marginalia={<>每个拒绝都是省下来的 GPT 调用。理想情况下 <em>≥90%</em> 的扫描在 AI 之前已经被规则拒绝。</>}
      >
        <BlockRows reasons={d.signals_block_counts} />
      </Section>
    </PageWrap>
  );
}

/* ─────────────── helpers ─────────────── */

function PageWrap({ children }: { children: ReactNode }) {
  return (
    <div className="px-8 py-7 pb-16 flex flex-col gap-7 max-w-[1400px]">{children}</div>
  );
}

function PageHead({ now }: { now: Date }) {
  const t = now.toLocaleTimeString('zh-CN', { hour12: false });
  return (
    <header className="grid grid-cols-[1fr_auto] items-end gap-6 pb-4 border-b border-hairline-strong">
      <div className="flex items-center gap-4">
        <Aperture size={34} rotate className="text-brass" />
        <div>
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight">概览</h1>
          <p className="font-cn text-ivory-40 text-[0.85rem] mt-1.5">24 小时观测日志</p>
        </div>
      </div>
      <div className="text-right font-mono text-[0.72rem] text-ivory-40 leading-relaxed">
        <div className="tracking-wider2">观测时间</div>
        <div><strong className="text-ivory font-medium">{t}</strong> · UTC+8</div>
        <div>自动刷新 · <strong className="text-ivory font-medium">15s</strong></div>
      </div>
    </header>
  );
}

function nextCandleMinutes(now: Date): number {
  const mins = now.getMinutes();
  const nextBoundary = Math.ceil((mins + 1) / 15) * 15;
  return nextBoundary - mins;
}

function NextCandleHint({ now, prefix = '下一根 15m K 线' }: { now: Date; prefix?: string }) {
  const m = nextCandleMinutes(now);
  return <>{prefix} <em className="not-italic text-brass">{m}</em> 分钟后</>;
}

function Section({ title, meta, marginalia, children }: { title: ReactNode; meta?: ReactNode; marginalia?: ReactNode; children: ReactNode }) {
  return (
    <section className="grid grid-cols-[1fr_200px] gap-7 items-start max-[1100px]:grid-cols-1">
      <div>
        <header className="flex items-center gap-3.5 pb-4 border-b border-hairline mb-5">
          <Aperture size={18} className="text-brass" />
          <h2 className="font-display text-[1.4rem] tracking-tight leading-none">{title}</h2>
          {meta && <span className="ml-auto font-mono text-[0.7rem] text-ivory-40 tracking-wide">{meta}</span>}
        </header>
        {children}
      </div>
      {marginalia && (
        <aside className="font-body italic text-[0.78rem] text-ivory-40 leading-snug pt-[50px] border-l border-hairline pl-4 max-[1100px]:border-l-0 max-[1100px]:border-t max-[1100px]:pt-3.5 max-[1100px]:pl-0 [&_em]:not-italic [&_em]:text-brass">
          {marginalia}
        </aside>
      )}
    </section>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="py-8 text-center font-body italic text-ivory-40">
      <span className="opacity-60 mr-2">▌</span>{message}
    </div>
  );
}

function SlotStrip({ active, total }: { active: number; total: number }) {
  return (
    <span className="inline-flex gap-1 mt-1">
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className={`w-2.5 h-2.5 inline-block ${i < active ? 'bg-sage' : 'border border-ivory-25'}`}
        />
      ))}
    </span>
  );
}

function Funnel({ steps, onLayerClick }: { steps: { name: string; count: number; scale: number }[]; onLayerClick: (n: string) => void }) {
  const colors = ['bg-ink', 'bg-brass-soft border-r-2 border-brass', 'bg-sage-soft border-r-2 border-sage'];
  return (
    <div className="flex flex-col gap-2">
      {steps.map((s, i) => (
        <button
          key={s.name}
          onClick={() => onLayerClick(s.name)}
          className="grid grid-cols-[180px_1fr_70px] items-center gap-3.5 py-1.5 px-1 border-b border-hairline text-left hover:bg-brass/[0.04] hover:border-brass transition-colors"
        >
          <span className="font-cn text-[0.85rem] text-ivory-70">{s.name}</span>
          <span className="h-3 bg-white/[0.04] relative">
            <span className={`absolute inset-y-0 left-0 ${colors[i] || 'bg-ink'}`} style={{ width: `${Math.max(2, s.scale * 100)}%` }} />
          </span>
          <span className="font-mono tabular-nums text-right text-ivory">{s.count}</span>
        </button>
      ))}
    </div>
  );
}

function PnlSparkline({ data }: { data: { time: string; cum: number; ts: number }[] }) {
  if (data.length === 0) return null;
  const w = 800;
  const h = 220;
  const padTop = 12, padBot = 30, padL = 30, padR = 90;
  const innerW = w - padL - padR;
  const innerH = h - padTop - padBot;
  const xs = data.map((_, i) => padL + (i / Math.max(1, data.length - 1)) * innerW);
  const cums = data.map(d => d.cum);
  const minY = Math.min(0, ...cums);
  const maxY = Math.max(0, ...cums);
  const range = maxY - minY || 1;
  const ys = cums.map(v => padTop + (1 - (v - minY) / range) * innerH);
  const zeroY = padTop + (1 - (0 - minY) / range) * innerH;
  const linePath = xs.map((x, i) => `${i === 0 ? 'M' : 'L'} ${x} ${ys[i]}`).join(' ');
  const fillPath = `${linePath} L ${xs[xs.length - 1]} ${zeroY} L ${xs[0]} ${zeroY} Z`;
  const last = data[data.length - 1];
  const finalColor = last.cum >= 0 ? 'var(--sage,#6B8568)' : 'var(--oxblood,#A53E32)';
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full h-[220px]">
      <line x1={padL} y1={zeroY} x2={w - padR} y2={zeroY} stroke="rgba(241,236,221,0.16)" />
      <text x={4} y={padTop + 10} fontSize={11} fill="rgba(241,236,221,0.42)" fontFamily="Fira Code" letterSpacing="0.06em">{maxY.toFixed(0)}</text>
      <text x={4} y={zeroY + 4} fontSize={11} fill="rgba(241,236,221,0.42)" fontFamily="Fira Code">0</text>
      {minY < 0 && <text x={4} y={padTop + innerH - 2} fontSize={11} fill="rgba(241,236,221,0.42)" fontFamily="Fira Code">{minY.toFixed(0)}</text>}
      <path d={fillPath} fill="rgba(107,133,104,0.10)" />
      <path d={linePath} stroke="#6B8568" strokeWidth="1.5" fill="none" />
      <circle cx={xs[xs.length - 1]} cy={ys[ys.length - 1]} r="3" fill="#C9A14B" />
      <text x={xs[xs.length - 1] + 10} y={ys[ys.length - 1] + 4} fontSize={11} fill="#C9A14B" fontFamily="Fira Code">
        {last.cum >= 0 ? '+' : ''}{last.cum.toFixed(2)} USDT
      </text>
      <text x={padL} y={h - 8} fontSize={11} fill="rgba(241,236,221,0.42)" fontFamily="Fira Code">{data[0].time}</text>
      <text x={(padL + w - padR) / 2 - 30} y={h - 8} fontSize={11} fill="rgba(241,236,221,0.42)" fontFamily="Fira Code">·</text>
      <text x={w - padR - 30} y={h - 8} fontSize={11} fill="rgba(241,236,221,0.42)" fontFamily="Fira Code">{last.time}</text>
    </svg>
  );
}

function BdGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mt-5 first:mt-0">
      <h4 className="font-mono text-[0.66rem] tracking-wider3 text-ivory-40 uppercase mb-3 pb-2 border-b border-hairline">{label}</h4>
      {children}
    </div>
  );
}

function BdRow({ label, data }: { label: string; data?: { count: number; win_rate: number; pnl_total: number } }) {
  if (!data || data.count === 0) {
    return (
      <div className="grid grid-cols-[110px_1fr_80px] items-center py-2 gap-3.5 text-[0.78rem] border-b border-hairline">
        <span className="font-cn text-ivory-40">{label}</span>
        <div className="h-2.5 bg-white/[0.04]" />
        <span className="font-mono text-right text-ivory-40">—</span>
      </div>
    );
  }
  const pct = Math.round(data.win_rate * 100);
  const pnl = data.pnl_total ?? 0;
  return (
    <div className="grid grid-cols-[110px_1fr_80px] items-center py-2 gap-3.5 text-[0.78rem] border-b border-hairline">
      <span className="font-cn text-ivory-70">{label}</span>
      <div className="h-2.5 bg-white/[0.04] relative">
        <span className="absolute inset-y-0 left-0 bg-sage-soft border-r border-sage" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-right text-[0.78rem] text-ivory-70">
        {pct}% · <span className={pnl >= 0 ? 'text-sage' : 'text-oxblood'}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(1)}</span>
      </span>
    </div>
  );
}

function Stat({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="mt-4 first:mt-0 pt-3 first:pt-0 border-t border-hairline first:border-t-0">
      <div className="font-mono text-[0.66rem] tracking-wider2 text-ivory-40 uppercase mb-1">{label}</div>
      <div className="font-mono text-[1.4rem] tracking-tight text-ivory tabular-nums leading-tight">{children}</div>
    </div>
  );
}

function BlockRows({ reasons }: { reasons: Record<string, number> }) {
  const entries = Object.entries(reasons).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return <EmptyState message="无拦截记录" />;
  const max = Math.max(...entries.map(e => e[1]), 1);
  return (
    <div className="flex flex-col gap-1.5">
      {entries.map(([k, v]) => (
        <div key={k} className="grid grid-cols-[200px_1fr_50px] items-center gap-3 py-1 text-[0.75rem]">
          <span className="font-mono text-[0.7rem] tracking-wide text-ivory-70">{k}</span>
          <span className="h-1 bg-white/[0.04] relative">
            <span className="absolute inset-y-0 left-0 bg-oxblood-soft border-r border-oxblood" style={{ width: `${(v / max) * 100}%` }} />
          </span>
          <span className="text-right font-mono text-ivory">{v}</span>
        </div>
      ))}
    </div>
  );
}

function SetupBreakdownTable() {
  const q = useV5SetupPerformance(7);
  const rows = q.data?.data ?? [];
  const byType = new Map<string, { n: number; w: number; sumR: number }>();
  for (const r of rows) {
    const cur = byType.get(r.setup_type) ?? { n: 0, w: 0, sumR: 0 };
    cur.n += r.sample_count;
    cur.w += r.win_count;
    cur.sumR += r.avg_realized_r * r.sample_count;
    byType.set(r.setup_type, cur);
  }
  const sorted = Array.from(byType.entries())
    .map(([t, v]) => ({
      setup_type: t,
      n: v.n,
      win_rate: v.n > 0 ? v.w / v.n : 0,
      avg_r: v.n > 0 ? v.sumR / v.n : 0,
      is_funding: t.startsWith('funding_extreme'),
    }))
    .sort((a, b) => b.n - a.n);
  if (sorted.length === 0) return <EmptyState message="7d 内无 reflection 样本" />;
  const totalN = sorted.reduce((a, x) => a + x.n, 0);
  return (
    <table className="w-full text-[0.78rem] border-collapse">
      <thead>
        <tr>
          <th className="text-left font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase font-normal px-3.5 py-2.5 border-b border-hairline">setup_type</th>
          <th className="text-right font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase font-normal px-3.5 py-2.5 border-b border-hairline">n</th>
          <th className="text-right font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase font-normal px-3.5 py-2.5 border-b border-hairline">win rate</th>
          <th className="text-right font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase font-normal px-3.5 py-2.5 border-b border-hairline">avg R</th>
          <th className="text-right font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase font-normal px-3.5 py-2.5 border-b border-hairline">share</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map(r => (
          <tr key={r.setup_type} className={`border-b border-hairline hover:bg-brass/[0.04] ${r.is_funding ? 'bg-brass-soft' : ''}`}>
            <td className={`px-3.5 py-2.5 font-mono text-[0.8rem] ${r.is_funding ? 'text-brass' : 'text-ivory-70'}`}>
              {r.is_funding && <span className="text-brass mr-1">✦</span>}
              {r.setup_type}
            </td>
            <td className="px-3.5 py-2.5 text-right font-mono tabular-nums">{r.n}</td>
            <td className={`px-3.5 py-2.5 text-right font-mono tabular-nums ${r.win_rate >= 0.5 ? 'text-sage' : 'text-oxblood'}`}>
              {(r.win_rate * 100).toFixed(0)}%
            </td>
            <td className={`px-3.5 py-2.5 text-right font-mono tabular-nums ${r.avg_r >= 0 ? 'text-sage' : 'text-oxblood'}`}>
              {r.avg_r >= 0 ? '+' : ''}{r.avg_r.toFixed(2)}
            </td>
            <td className="px-3.5 py-2.5 text-right font-mono tabular-nums text-ivory-70">{totalN > 0 ? Math.round((r.n / totalN) * 100) : 0}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
