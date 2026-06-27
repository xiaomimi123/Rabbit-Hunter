import { useState } from 'react';
import { Play, Square, AlertCircle, Wallet, AlertTriangle, Activity } from 'lucide-react';
import { useV5Dashboard } from '../../hooks/api/useV5Dashboard';
import { useV5ActivePositions } from '../../hooks/api/useV5ActivePositions';
import { useV5AIDecisions } from '../../hooks/api/useV5AIStatus';
import { useV5Klines } from '../../hooks/api/useV5Klines';
import { useAccountBalance } from '../../hooks/api/useV5Account';
import { useV5TraderKpi } from '../../hooks/api/useV5TraderKpi';
import type { ConstitutionStatus, RollingKpi, AIHealth } from '../../hooks/api/useV5TraderKpi';
import { useUIStore } from '../../services/store';
import { useSystemMode } from '../../hooks/useSystemMode';
import { useV5Settings } from '../../hooks/api/useV5Settings';
import { Card } from '../primitives-v3/Card';
import { SegmentButton } from '../primitives-v3/SegmentButton';
import { Sparkline } from '../primitives/Sparkline';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { cn } from '../primitives-v3/cn';
import type { Interval } from '../../types';

// ─────────────────────────────────────────────────────────────
// 小工具
// ─────────────────────────────────────────────────────────────

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] uppercase tracking-wider2 text-ivory-40">{children}</div>
  );
}

function StatGlyph({ ok, watch }: { ok: boolean; watch?: boolean }) {
  if (!ok) return <span className="text-oxblood">●</span>;
  if (watch) return <span className="text-brass">◐</span>;
  return <span className="text-sage">◯</span>;
}

function fmtR(r: number): string {
  return `${r >= 0 ? '+' : ''}${r.toFixed(2)}R`;
}

function fmtUsdt(u: number, withSign = false): string {
  return `${withSign && u >= 0 ? '+' : ''}${u.toFixed(2)}`;
}

function fmtPct(p: number, withSign = true): string {
  return `${withSign && p >= 0 ? '+' : ''}${(p * 100).toFixed(2)}%`;
}

// ─────────────────────────────────────────────────────────────
// 主页
// ─────────────────────────────────────────────────────────────

export function DashboardPage() {
  const dash = useV5Dashboard();
  const active = useV5ActivePositions();
  const decisions = useV5AIDecisions(10);
  const kpi = useV5TraderKpi(30, 24);
  const { mode } = useSystemMode();
  const { patch } = useV5Settings();
  const selectedSymbol = useUIStore(s => s.selectedSymbol);
  const [timeframe, setTimeframe] = useState<Interval>('15m');
  const klines = useV5Klines(selectedSymbol, timeframe, 50);
  const balance = useAccountBalance();

  const d = dash.data;
  const positions = active.data?.combined ?? [];
  const decisionList = decisions.data?.decisions ?? [];
  const klineData = klines.data?.klines ?? [];
  const closes = klineData.map(k => k.close);
  const b = balance.data;
  const k = kpi.data;

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between border-b border-hairline pb-3">
        <div>
          <div className="text-[10px] uppercase tracking-wider3 text-ivory-40">Trader Console</div>
          <h1 className="mt-1 text-2xl font-semibold text-ivory">交易员中控台</h1>
        </div>
        <div className="text-xs text-ivory-40 font-mono">
          {k ? `KPI · ${k.window_days}d 滚动 · 更新于 ${new Date(k.generated_at).toLocaleTimeString('zh-CN', { hour12: false })}` : 'KPI 加载中…'}
        </div>
      </header>

      {/* 1. 上层 3 列指标条 ─────────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr_1.4fr]">
        <AccountPanel b={b} />
        <TodayPanel d24={d} />
        <RollingPanel kpi={k} />
      </div>

      {/* 2. 风控宪法 Hero ───────────────────────────────────── */}
      <ConstitutionDashboard c={k?.constitution} />

      {/* 3. 活仓位 ──────────────────────────────────────────── */}
      <ActivePositionsTable positions={positions} />

      {/* 4. 下段两栏:控制 + AI 健康/日志 + K 线 ─────────────── */}
      <div className="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
        <div className="space-y-4">
          <ControlsPanel mode={mode} patch={patch} />
          <AIHealthAndLog ai={k?.ai_health} decisionList={decisionList} />
        </div>

        <Card title={`${selectedSymbol} 走势`} subtitle="切换时间帧" actions={
          <div className="flex gap-1 rounded-md border border-hairline p-0.5">
            {(['15m', '1h'] as Interval[]).map(tf => (
              <SegmentButton key={tf} active={timeframe === tf} onClick={() => setTimeframe(tf)}>{tf}</SegmentButton>
            ))}
          </div>
        }>
          {klines.isLoading ? (
            <LoadingSkeleton message="拉取 K 线…" />
          ) : closes.length === 0 ? (
            <div className="py-12 text-center text-sm text-ivory-40">无 K 线数据</div>
          ) : (
            <div>
              <div className="font-mono text-3xl font-semibold tabular-nums text-ivory">
                {closes.at(-1)?.toFixed(closes.at(-1)! >= 1 ? 2 : 6)}
              </div>
              <div className={cn(
                'font-mono text-sm tabular-nums',
                closes.at(-1)! >= closes[0] ? 'text-sage' : 'text-oxblood',
              )}>
                {((closes.at(-1)! / closes[0] - 1) * 100).toFixed(2)}%
              </div>
              <div className="mt-4"><Sparkline values={closes} width={500} height={160} /></div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Panels
// ─────────────────────────────────────────────────────────────

function AccountPanel({ b }: { b: any }) {
  const okxOk = b?.status === 'ok';
  return (
    <Card title="账户" subtitle={okxOk ? `${b.exchange.toUpperCase()} ${b.testnet ? '模拟' : '实盘'}` : 'SHADOW only'}>
      <div className="space-y-3">
        {okxOk ? (
          <div className="rounded-md border border-hairline bg-bg-deep px-3 py-2.5">
            <div className="flex items-center gap-1.5">
              <Wallet className="h-3 w-3 text-brass" />
              <Eyebrow>OKX 总资产</Eyebrow>
            </div>
            <div className="mt-1 font-mono text-2xl font-semibold tabular-nums text-ivory">
              {b.total_usdt.toFixed(2)} <span className="text-sm text-ivory-40">USDT</span>
            </div>
            <div className="mt-0.5 font-mono text-xs text-ivory-40">可用 {b.available_usdt.toFixed(2)}</div>
          </div>
        ) : b?.status === 'not_configured' ? (
          <div className="rounded-md border border-brass/30 bg-brass-soft px-3 py-2.5">
            <div className="flex items-center gap-1.5"><AlertTriangle className="h-3 w-3 text-brass" /><Eyebrow>OKX 未绑定</Eyebrow></div>
            <div className="mt-1 text-sm text-brass">去 <span className="font-mono">/settings</span> 填 key</div>
          </div>
        ) : (
          <div className="rounded-md border border-oxblood/30 bg-oxblood-soft px-3 py-2.5">
            <div className="flex items-center gap-1.5"><AlertCircle className="h-3 w-3 text-oxblood" /><Eyebrow>OKX 拉取失败</Eyebrow></div>
            <div className="mt-1 font-mono text-xs text-oxblood truncate" title={b?.error ?? ''}>{(b?.error ?? '').slice(0, 80)}</div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-md border border-hairline bg-bg-deep px-3 py-2">
            <Eyebrow>Paper PnL</Eyebrow>
            <div className={cn('mt-1 font-mono text-lg font-semibold tabular-nums', (b?.paper_realized_pnl_usdt ?? 0) >= 0 ? 'text-sage' : 'text-oxblood')}>
              {fmtUsdt(b?.paper_realized_pnl_usdt ?? 0, true)}
            </div>
          </div>
          <div className="rounded-md border border-hairline bg-bg-deep px-3 py-2">
            <Eyebrow>活仓 / 上限</Eyebrow>
            <div className="mt-1 font-mono text-lg font-semibold tabular-nums text-ivory">
              {b?.paper_open_count ?? 0} <span className="text-sm text-ivory-40">/ 3</span>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}

function TodayPanel({ d24 }: { d24: any }) {
  const pnl = d24?.pnl_total_usdt ?? 0;
  const wr = d24?.win_rate_24h ?? 0;
  const exec = d24?.signals_executed ?? 0;
  const sigs = d24?.signals_24h ?? 0;
  const passed = d24?.signals_passed_and ?? 0;

  return (
    <Card title="今日 (24h)" subtitle="信号 → 执行 → 兑现">
      <div className="space-y-3">
        <div className="rounded-md border border-hairline bg-bg-deep px-3 py-2.5">
          <Eyebrow>24h 实现 PnL</Eyebrow>
          <div className={cn('mt-1 font-mono text-2xl font-semibold tabular-nums', pnl >= 0 ? 'text-sage' : 'text-oxblood')}>
            {fmtUsdt(pnl, true)} <span className="text-sm text-ivory-40">USDT</span>
          </div>
          <div className="mt-0.5 font-mono text-xs text-ivory-40">胜率 {(wr * 100).toFixed(0)}% · {d24?.closed_24h?.length ?? 0} 笔</div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-md border border-hairline bg-bg-deep px-3 py-2">
            <Eyebrow>信号 / 通过</Eyebrow>
            <div className="mt-1 font-mono text-lg font-semibold tabular-nums text-ivory">{passed} / {sigs}</div>
            <div className="font-mono text-xs text-ivory-40">{sigs ? Math.round(passed / sigs * 100) : 0}%</div>
          </div>
          <div className="rounded-md border border-hairline bg-bg-deep px-3 py-2">
            <Eyebrow>已入仓</Eyebrow>
            <div className="mt-1 font-mono text-lg font-semibold tabular-nums text-ivory">{exec}</div>
            <div className="font-mono text-xs text-ivory-40">{Math.round(d24?.avg_holding_minutes ?? 0)} min 均持</div>
          </div>
        </div>
      </div>
    </Card>
  );
}

function RollingPanel({ kpi }: { kpi: { window_days: number; rolling: RollingKpi } | undefined }) {
  const r = kpi?.rolling;
  const pf = r?.profit_factor;
  return (
    <Card title={`${kpi?.window_days ?? 30}d 滚动`} subtitle="扣 OKX 真实成本">
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Profit Factor" value={pf != null ? pf.toFixed(2) : '—'} tone={pf == null ? 'mute' : pf >= 1.5 ? 'good' : pf >= 1.0 ? 'watch' : 'bad'} />
        <Stat label="Sharpe" value={r?.sharpe != null ? r.sharpe.toFixed(2) : '—'} tone={r?.sharpe == null ? 'mute' : r.sharpe >= 1 ? 'good' : r.sharpe >= 0 ? 'watch' : 'bad'} />
        <Stat label="Max DD" value={r ? fmtR(r.max_dd_r) : '—'} tone={r ? (r.max_dd_r > -3 ? 'good' : r.max_dd_r > -8 ? 'watch' : 'bad') : 'mute'} />
        <Stat label="Win Rate" value={r ? `${(r.win_rate * 100).toFixed(0)}%` : '—'} tone={r ? (r.win_rate >= 0.55 ? 'good' : r.win_rate >= 0.45 ? 'watch' : 'bad') : 'mute'} />
        <Stat label="Avg R" value={r ? fmtR(r.avg_r) : '—'} tone={r ? (r.avg_r > 0.1 ? 'good' : r.avg_r > 0 ? 'watch' : 'bad') : 'mute'} />
        <Stat label="N 笔" value={r ? String(r.n_trades) : '—'} tone={r && r.n_trades >= 30 ? 'good' : r && r.n_trades >= 10 ? 'watch' : 'mute'} />
      </div>
      <div className="mt-3 border-t border-hairline pt-2 font-mono text-xs text-ivory-40">
        <span>累计 R </span>
        <span className={cn(r && r.total_r >= 0 ? 'text-sage' : 'text-oxblood')}>
          {r ? fmtR(r.total_r) : '—'}
        </span>
        {r && r.n_trades < 30 && <span className="ml-2 text-brass">· n&lt;30 样本仍小</span>}
      </div>
    </Card>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: 'good' | 'watch' | 'bad' | 'mute' }) {
  const color = {
    good: 'text-sage',
    watch: 'text-brass',
    bad: 'text-oxblood',
    mute: 'text-ivory-70',
  }[tone];
  return (
    <div className="rounded-md border border-hairline bg-bg-deep px-2.5 py-2">
      <div className="text-[10px] uppercase tracking-wider2 text-ivory-40">{label}</div>
      <div className={cn('mt-1 font-mono text-base font-semibold tabular-nums', color)}>{value}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// HERO: Constitution Dashboard
// ─────────────────────────────────────────────────────────────

function ConstitutionDashboard({ c }: { c: ConstitutionStatus | undefined }) {
  return (
    <Card
      title="风控宪法 / 实时仪表"
      subtitle="七条铁律 — 任何一条违反 = 系统拒单 / 锁仓"
    >
      {!c ? (
        <LoadingSkeleton message="拉取宪法状态…" />
      ) : (
        <ul className="divide-y divide-hairline font-mono text-sm">
          <RuleRow num="1" name="单笔风险 ≤ 1%" ok={c.rule_1_risk_cap_ok}
            detail={c.rule_1_risk_cap_ok ? 'config.risk_per_trade 在宪法 tier 上限内' : 'config.risk_per_trade 超 1% — 立即修'} />
          <RuleRow num="2" name="进场必挂止损" ok={c.rule_2_sl_attached.ok}
            detail={`今日开仓 ${c.rule_2_sl_attached.today_opens} 单 · 实挂 ${c.rule_2_sl_attached.today_sl_attached}`} />
          <RuleRow num="3" name="日内 -3% 锁仓" ok={!c.rule_3_daily_dd.lockdown_triggered}
            watch={!c.rule_3_daily_dd.lockdown_triggered && c.rule_3_daily_dd.distance_pct < 0.01}
            detail={`今日 ${fmtPct(c.rule_3_daily_dd.today_pnl_pct)} · 距阈值 ${fmtPct(c.rule_3_daily_dd.distance_pct, false)}`} />
          <RuleRow num="4" name="杠杆 3-5x 反推" ok={c.rule_4_leverage_in_range}
            detail={`当前 leverage_cap=${c.rule_4_leverage_value} · derive_safe_leverage 按 SL 实时降压`} />
          <RuleRow num="5" name="SL/ATR ∈ [1.5, 2.2]" ok={c.rule_5_sl_atr_ratio.ok}
            detail={`今日开仓 ${c.rule_5_sl_atr_ratio.today_opens} 单 · ${c.rule_5_sl_atr_ratio.today_in_range} 落区间`} />
          <RuleRow num="6" name="SHORT 默认关" ok={c.rule_6_short_disabled}
            detail={`ENABLE_SHORT_TRADING=${c.rule_6_short_disabled ? 'false' : 'TRUE ⚠'} · 今日拦截 ${c.rule_6_today_blocked} 单`} />
          <RuleRow num="7" name="杀手 setup 禁用" ok={c.rule_7_killer_disabled}
            detail={`DEFAULT_DISABLED_SETUPS 静态保证 · 今日拦截 ${c.rule_7_today_blocked} 单`} />
        </ul>
      )}
    </Card>
  );
}

function RuleRow({ num, name, ok, watch, detail }: { num: string; name: string; ok: boolean; watch?: boolean; detail: string }) {
  return (
    <li className="grid grid-cols-[2rem_2rem_minmax(10rem,auto)_1fr] items-center gap-2 py-2">
      <span className="text-ivory-40 tabular-nums">[{num}]</span>
      <span className="text-base"><StatGlyph ok={ok} watch={watch} /></span>
      <span className={cn(ok ? 'text-ivory' : 'text-oxblood')}>{name}</span>
      <span className="truncate text-ivory-70">{detail}</span>
    </li>
  );
}

// ─────────────────────────────────────────────────────────────
// Active Positions Table
// ─────────────────────────────────────────────────────────────

function ActivePositionsTable({ positions }: { positions: any[] }) {
  return (
    <Card title="活仓位" subtitle={`当前 ${positions.length} / 3 仓位`}>
      {positions.length === 0 ? (
        <div className="py-8 text-center font-mono text-sm text-ivory-40">空仓 · 等待信号</div>
      ) : (
        <table className="w-full font-mono text-sm">
          <thead className="text-[10px] uppercase tracking-wider2 text-ivory-40">
            <tr className="border-b border-hairline">
              <Th>Symbol</Th>
              <Th>Side</Th>
              <Th align="right">Entry</Th>
              <Th align="right">Now</Th>
              <Th align="right">SL %</Th>
              <Th align="right">TP %</Th>
              <Th align="right">Unreal</Th>
              <Th align="right">已持</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {positions.map((p: any) => {
              const sideClass = p.side === 'LONG' ? 'text-sage' : 'text-oxblood';
              const ent = p.entry_price ?? 0;
              const now = p.current_price ?? ent;
              const sl = p.sl_price ?? p.stop_loss ?? 0;
              const tp = p.tp_price ?? p.take_profit ?? 0;
              const slDistPct = ent ? ((sl - ent) / ent) * 100 : 0;
              const tpDistPct = ent ? ((tp - ent) / ent) * 100 : 0;
              const unrealPct = p.unrealized_pct ?? (ent ? ((now - ent) / ent) * 100 * (p.side === 'LONG' ? 1 : -1) : 0);
              const holdMin = p.entry_time ? Math.round((Date.now() - new Date(p.entry_time).getTime()) / 60000) : 0;
              const hoursMin = `${Math.floor(holdMin / 60)}h${(holdMin % 60).toString().padStart(2, '0')}`;
              return (
                <tr key={p.id ?? p.position_id} className="text-ivory">
                  <Td>{p.symbol}</Td>
                  <Td><span className={sideClass}>{p.side}</span></Td>
                  <Td align="right">{ent.toFixed(ent >= 1 ? 2 : 6)}</Td>
                  <Td align="right">{now.toFixed(now >= 1 ? 2 : 6)}</Td>
                  <Td align="right" className="text-oxblood">{slDistPct.toFixed(2)}%</Td>
                  <Td align="right" className="text-sage">{tpDistPct >= 0 ? '+' : ''}{tpDistPct.toFixed(2)}%</Td>
                  <Td align="right" className={unrealPct >= 0 ? 'text-sage' : 'text-oxblood'}>
                    {unrealPct >= 0 ? '+' : ''}{unrealPct.toFixed(2)}%
                  </Td>
                  <Td align="right" className="text-ivory-70">{hoursMin}</Td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function Th({ children, align }: { children: React.ReactNode; align?: 'right' | 'left' }) {
  return <th className={cn('px-2 py-2 font-normal', align === 'right' ? 'text-right' : 'text-left')}>{children}</th>;
}
function Td({ children, align, className }: { children: React.ReactNode; align?: 'right' | 'left'; className?: string }) {
  return <td className={cn('px-2 py-2 tabular-nums', align === 'right' ? 'text-right' : 'text-left', className)}>{children}</td>;
}

// ─────────────────────────────────────────────────────────────
// Controls + AI Health & Log
// ─────────────────────────────────────────────────────────────

function ControlsPanel({ mode, patch }: { mode: string | null | undefined; patch: any }) {
  return (
    <Card title="运行控制" subtitle="启停扫描 · 切系统模式">
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => patch.mutate({ enable_auto_trading: true })}
          className="inline-flex items-center justify-center gap-1.5 rounded-md border border-sage bg-sage-soft px-4 py-2 text-sm font-medium text-sage transition hover:bg-sage hover:text-ivory"
        >
          <Play className="h-4 w-4" /> 启动扫描
        </button>
        <button
          type="button"
          onClick={() => patch.mutate({ enable_auto_trading: false })}
          className="inline-flex items-center justify-center gap-1.5 rounded-md border border-hairline-strong px-4 py-2 text-sm text-ivory-70 transition hover:border-oxblood hover:text-oxblood"
        >
          <Square className="h-4 w-4" /> 暂停扫描
        </button>
      </div>
      <div className="mt-3 flex items-center justify-between border-t border-hairline pt-3 text-xs">
        <Eyebrow>当前系统</Eyebrow>
        <span className={cn('font-mono', mode === 'LIVE' ? 'text-oxblood' : 'text-brass')}>
          {mode === 'LIVE' ? '● LIVE' : '◐ SHADOW'}
        </span>
      </div>
    </Card>
  );
}

function AIHealthAndLog({ ai, decisionList }: { ai: AIHealth | undefined; decisionList: any[] }) {
  return (
    <Card title="AI 健康度 & 决策日志" subtitle={ai ? `最近 ${ai.window_hours}h` : '最近 24h'}>
      {ai && (
        <div className="grid grid-cols-3 gap-2 border-b border-hairline pb-3 mb-3">
          <Stat label="真实推理" value={String(ai.real_responses)} tone={ai.real_responses > 0 ? 'good' : 'mute'} />
          <Stat label="兜底放行" value={String(ai.fallback_passthrough)} tone={ai.fallback_passthrough === 0 ? 'good' : 'watch'} />
          <Stat label="taxonomy 拒" value={String(ai.failure_taxonomy_rejects)} tone={ai.failure_taxonomy_rejects === 0 ? 'good' : 'watch'} />
        </div>
      )}
      <div className="font-mono text-xs">
        <div className="flex items-center gap-1.5 mb-2 text-ivory-40">
          <Activity className="h-3 w-3" /> <Eyebrow>最近 10 条决策</Eyebrow>
        </div>
        {decisionList.length === 0 ? (
          <div className="py-4 text-center text-ivory-40 italic">暂无决策记录</div>
        ) : (
          <ul className="space-y-1.5 max-h-72 overflow-y-auto">
            {decisionList.map((d: any) => (
              <li key={d.id} className="flex items-center gap-2 text-xs">
                <span className="text-ivory-40 tabular-nums">
                  {new Date(d.created_at).toLocaleTimeString('zh-CN', { hour12: false })}
                </span>
                <span className={cn(
                  'px-1.5 py-0.5 rounded-sm border text-[10px] uppercase tracking-wider2',
                  d.execute
                    ? 'border-sage/40 bg-sage-soft text-sage'
                    : 'border-oxblood/40 bg-oxblood-soft text-oxblood',
                )}>
                  {d.execute ? '通过' : '拒'}
                </span>
                <span className="text-ivory tabular-nums">{d.symbol}</span>
                <span className="text-ivory-70 truncate">
                  {(d.reasoning ?? '').length > 60 ? (d.reasoning ?? '').slice(0, 60) + '…' : (d.reasoning ?? '')}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
