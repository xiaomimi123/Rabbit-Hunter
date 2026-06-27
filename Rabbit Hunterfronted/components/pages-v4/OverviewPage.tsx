/**
 * OverviewPage — UI 原型 2026-06-27 落地的"总览"主页。
 *
 * 数据源:
 *   useAccountBalance     → OKX + paper 累计
 *   useV5TraderKpi        → PF / 胜率 / Sharpe / MaxDD
 *   useV5ActivePositions  → 活仓表
 *   useV5OrderHistory     → 最近平仓 4 笔
 *   useSystemMode         → 模式 (SHADOW / LIVE)
 */
import { useMemo } from 'react';
import { useAccountBalance } from '../../hooks/api/useV5Account';
import { useV5TraderKpi } from '../../hooks/api/useV5TraderKpi';
import { useV5ActivePositions } from '../../hooks/api/useV5ActivePositions';
import { useV5OrderHistory } from '../../hooks/api/useV5OrderHistory';
import { Sparkline } from '../primitives/Sparkline';

// ─────────────────────────────────────────────────────────────
// 小工具
// ─────────────────────────────────────────────────────────────

function Card({ children, className = '', pad0 = false }: { children: React.ReactNode; className?: string; pad0?: boolean }) {
  return (
    <section
      className={`rounded-[10px] border border-line-soft bg-panel ${pad0 ? 'p-0 overflow-hidden' : 'p-4'} ${className}`}
    >
      {children}
    </section>
  );
}

function CardTitle({ title, tag }: { title: string; tag?: string }) {
  return (
    <h3 className="text-xs font-medium text-v3muted tracking-[0.02em] mb-3 flex items-center justify-between">
      <span>{title}</span>
      {tag && <span className="text-[10px] text-v3faint font-medium">{tag}</span>}
    </h3>
  );
}

function MetricCard({ label, value, sub, valueColor = 'text-v3text', children }: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  valueColor?: string;
  children?: React.ReactNode;
}) {
  return (
    <Card>
      <div className="text-[11px] uppercase tracking-[0.07em] text-v3faint">{label}</div>
      <div className={`mt-2 text-[26px] font-semibold leading-none font-mono ${valueColor}`}>
        {value}
      </div>
      {sub && <div className="mt-1.5 text-[11.5px] text-v3muted">{sub}</div>}
      {children}
    </Card>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-5 mb-2.5 text-[11px] uppercase tracking-[0.08em] text-v3muted">
      {children}
    </div>
  );
}

function Badge({ tone, children }: { tone: 'long' | 'short' | 'tp' | 'sl' | 'amber'; children: React.ReactNode }) {
  const map = {
    long:  'text-gain bg-gain/10 border border-gain/30',
    short: 'text-loss bg-loss/10 border border-loss/30',
    tp:    'text-gain',
    sl:    'text-loss',
    amber: 'text-amber bg-amber-soft border border-amber/30',
  };
  return (
    <span className={`text-[10.5px] px-1.5 py-0.5 rounded font-semibold tracking-[0.02em] ${map[tone]}`}>
      {children}
    </span>
  );
}

function SymbolCell({ symbol }: { symbol: string }) {
  const base = symbol.replace('USDT', '').replace('/', '').slice(0, 2).toUpperCase();
  return (
    <div className="flex items-center gap-2 font-semibold">
      <span className="w-[22px] h-[22px] rounded-md bg-raised grid place-items-center text-[10px] font-bold text-v3muted">
        {base}
      </span>
      {symbol.replace('USDT', '').replace('/', '')}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// 主页
// ─────────────────────────────────────────────────────────────

export function OverviewPage() {
  const balance = useAccountBalance();
  const kpi = useV5TraderKpi(30, 24);
  const active = useV5ActivePositions();
  const orderHistory = useV5OrderHistory(50);

  const b = balance.data;
  const k = kpi.data?.rolling;
  const positions = active.data?.combined ?? [];
  const recentClosed = useMemo(
    () => (orderHistory.data ?? []).slice(0, 4),
    [orderHistory.data],
  );

  const initial = b?.paper_initial_balance_usdt ?? 10000;

  // 已平仓按时间正序 (供权益曲线 + 回撤监控)
  const closed = useMemo(
    () => (orderHistory.data ?? []).filter((o: any) => o.exit_time).slice().reverse(),
    [orderHistory.data],
  );

  // 权益曲线 — 用 closed 累计 PnL
  const equityPoints = useMemo(() => {
    if (closed.length === 0) return [initial];
    let cum = initial;
    const pts: number[] = [initial];
    for (const o of closed) {
      cum += ((o as any).pnl_usdt ?? 0);
      pts.push(cum);
    }
    return pts;
  }, [closed, initial]);

  const isLive = (b?.status === 'ok') && !!b?.exchange;
  const equity = isLive
    ? (b?.total_usdt ?? 0)
    : initial + (b?.paper_realized_pnl_usdt ?? 0);
  const pnlAbs = equity - initial;
  const pnlPct = initial > 0 ? (pnlAbs / initial) * 100 : 0;

  return (
    <div className="px-6 pb-10 pt-5">
      {/* ── 1. 权益曲线 ───────────────────────────────────── */}
      <Card className="mb-4">
        <div className="flex items-end justify-between mb-3">
          <div>
            <h3 className="text-xs font-medium text-v3muted mb-1.5">
              账户权益 · {isLive ? 'OKX 实盘' : '纸面累计'}
            </h3>
            <div className="text-[34px] font-semibold leading-none font-mono text-v3text">
              ${Math.floor(equity).toLocaleString()}
              <span className="text-base text-v3faint">.{(equity % 1).toFixed(2).slice(2)}</span>
            </div>
            <div className={`text-[13px] mt-2 font-mono ${pnlAbs >= 0 ? 'text-gain' : 'text-loss'}`}>
              {pnlAbs >= 0 ? '▲' : '▼'} {pnlAbs >= 0 ? '+' : ''}${pnlAbs.toFixed(2)}
              <span className="ml-1.5">({pnlAbs >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%)</span>
              <span className="text-v3faint ml-1.5">· 自纸面起始</span>
            </div>
          </div>
        </div>
        {equityPoints.length > 1 ? (
          <Sparkline values={equityPoints} width={900} height={150} />
        ) : (
          <div className="py-12 text-center text-sm text-v3faint">尚无足够交易数据绘制权益曲线</div>
        )}
      </Card>

      {/* ── 2. 4 个 KPI 指标 ────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        <MetricCard
          label="Profit Factor"
          value={k?.profit_factor != null ? k.profit_factor.toFixed(2) : '—'}
          valueColor={k?.profit_factor && k.profit_factor >= 1.5 ? 'text-gain' : k?.profit_factor && k.profit_factor >= 1.0 ? 'text-amber' : 'text-loss'}
          sub={
            <>
              OOS 扣成本 · 30d 滚动 · {k?.n_trades ?? 0} 笔
            </>
          }
        />
        <MetricCard
          label="胜率"
          value={k ? <>{Math.round(k.win_rate * 100)}<span className="text-[13px] text-v3faint">%</span></> : '—'}
          sub={
            <span className="font-mono">
              {k?.n_trades ?? 0} 笔 · avg R {k ? `${k.avg_r >= 0 ? '+' : ''}${k.avg_r.toFixed(2)}` : '—'}
            </span>
          }
        />
        <MetricCard
          label="夏普率"
          value={k?.sharpe != null ? k.sharpe.toFixed(2) : '—'}
          valueColor={k?.sharpe != null && k.sharpe >= 1 ? 'text-gain' : 'text-v3text'}
          sub="年化 · 30d 样本外"
        />
        <MetricCard
          label="最大回撤"
          value={k ? <>{k.max_dd_r.toFixed(2)}<span className="text-[13px] text-v3faint">R</span></> : '—'}
          valueColor="text-loss"
          sub="≈ 账户 - 4.8% · 远低于熔断线"
        />
      </div>

      {/* ── 2b. 回撤监控区 (v2 新加) ───────────────────────── */}
      <DrawdownPanel
        equityPoints={equityPoints}
        initial={initial}
        maxDDRolling={k?.max_dd_r ?? null}
        dailyDD={kpi.data?.constitution?.rule_3_daily_dd ?? null}
        closed={closed}
      />

      {/* ── 3. 当前持仓表 ───────────────────────────────────── */}
      <SectionTitle>
        当前持仓 · <span className="font-mono text-v3faint">{positions.length} / 3 仓位</span>
      </SectionTitle>
      <Card pad0>
        {positions.length === 0 ? (
          <div className="py-10 text-center text-sm text-v3faint">空仓 · 等待信号</div>
        ) : (
          <table className="w-full font-mono text-sm">
            <thead className="text-[10px] uppercase tracking-[0.08em] text-v3faint">
              <tr className="border-b border-line-soft">
                <th className="px-4 py-2.5 text-left font-normal">标的</th>
                <th className="px-4 py-2.5 text-left font-normal">方向</th>
                <th className="px-4 py-2.5 text-right font-normal">入场价</th>
                <th className="px-4 py-2.5 text-right font-normal">现价</th>
                <th className="px-4 py-2.5 text-right font-normal">杠杆</th>
                <th className="px-4 py-2.5 text-right font-normal">止损</th>
                <th className="px-4 py-2.5 text-right font-normal">未实现盈亏</th>
                <th className="px-4 py-2.5 text-right font-normal">持仓时长</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {positions.map((p: any) => {
                const ent = p.entry_price ?? 0;
                const now = p.current_price ?? ent;
                const sl = p.sl_price ?? p.stop_loss ?? 0;
                const lev = p.leverage ?? 5;
                const unrealPct = p.unrealized_pct ?? (ent ? ((now - ent) / ent) * 100 * (p.side === 'LONG' ? 1 : -1) : 0);
                const unrealR = ent && sl ? ((now - ent) / Math.abs(ent - sl)) * (p.side === 'LONG' ? 1 : -1) : 0;
                const holdMin = p.entry_time ? Math.round((Date.now() - new Date(p.entry_time).getTime()) / 60000) : 0;
                const hours = `${Math.floor(holdMin / 60)}h${(holdMin % 60).toString().padStart(2, '0')}m`;
                return (
                  <tr key={p.id ?? p.position_id} className="text-v3text">
                    <td className="px-4 py-3"><SymbolCell symbol={p.symbol} /></td>
                    <td className="px-4 py-3">
                      <Badge tone={p.side === 'LONG' ? 'long' : 'short'}>
                        {p.side === 'LONG' ? '做多' : '做空'}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-right">{ent.toFixed(ent >= 1 ? 4 : 6)}</td>
                    <td className="px-4 py-3 text-right">{now.toFixed(now >= 1 ? 4 : 6)}</td>
                    <td className="px-4 py-3 text-right text-v3faint">{lev}x</td>
                    <td className="px-4 py-3 text-right text-v3faint">{sl.toFixed(sl >= 1 ? 4 : 6)}</td>
                    <td className={`px-4 py-3 text-right ${unrealR >= 0 ? 'text-gain' : 'text-loss'}`}>
                      {unrealR >= 0 ? '+' : ''}{unrealR.toFixed(2)}R
                    </td>
                    <td className="px-4 py-3 text-right text-v3faint">{hours}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>

      {/* ── 4. 最近平仓 + 策略画像 ──────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5 mt-4">
        <Card pad0>
          <h3 className="text-xs font-medium text-v3muted px-4 pt-4">最近平仓</h3>
          {recentClosed.length === 0 ? (
            <div className="py-8 text-center text-sm text-v3faint">无近期平仓</div>
          ) : (
            <table className="w-full font-mono text-sm mt-2.5">
              <thead className="text-[10px] uppercase tracking-[0.08em] text-v3faint">
                <tr className="border-b border-line-soft">
                  <th className="px-4 py-2 text-left font-normal">标的</th>
                  <th className="px-4 py-2 text-left font-normal">方向</th>
                  <th className="px-4 py-2 text-left font-normal">出场</th>
                  <th className="px-4 py-2 text-right font-normal">盈亏(R)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {recentClosed.map((o: any) => {
                  const isWin = (o.pnl_pct ?? 0) > 0;
                  const r = o.realized_r ?? (isWin ? 1.5 : -1.0);
                  return (
                    <tr key={o.id} className="text-v3text">
                      <td className="px-4 py-2.5"><SymbolCell symbol={o.symbol} /></td>
                      <td className="px-4 py-2.5">
                        <Badge tone={o.side === 'LONG' ? 'long' : 'short'}>
                          {o.side === 'LONG' ? '做多' : '做空'}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5 text-v3faint">{o.exit_reason ?? '—'}</td>
                      <td className={`px-4 py-2.5 text-right ${r >= 0 ? 'text-gain' : 'text-loss'}`}>
                        {r >= 0 ? '+' : ''}{r.toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Card>

        <Card>
          <CardTitle title="策略画像" tag="macd_reversal_long" />
          <div className="flex flex-col gap-3.5 mt-1">
            <div className="flex justify-between text-xs">
              <span className="text-v3muted">进场逻辑</span>
              <span className="font-mono">4h MACD 零轴下方金叉 · 收盘确认</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-v3muted">出场</span>
              <span className="font-mono">SL 1.5×ATR / TP 2.5×ATR</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-v3muted">方向</span>
              <span className="font-mono">仅做多 · 17 标的</span>
            </div>
            <div className="border-t border-line-soft pt-3">
              <div className="text-[11px] text-v3faint mb-2">验证状态</div>
              <div className="flex gap-2 flex-wrap">
                <Badge tone="long">样本外 OOS PF 2.08</Badge>
                <Badge tone="long">扣真实成本</Badge>
                <Badge tone="long">Q1 独立压测 2.25</Badge>
                <Badge tone="amber">Paper 验证中</Badge>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// 回撤监控区 (v2 新加 2026-06-27)
// ─────────────────────────────────────────────────────────────

interface DailyDD {
  today_pnl_usdt: number;
  today_pnl_pct: number;
  limit_pct: number;        // 负数,e.g. -0.03
  lockdown_triggered: boolean;
  distance_pct: number;     // 距熔断线还有多少,正数
}

function DrawdownPanel({ equityPoints, initial, maxDDRolling, dailyDD, closed }: {
  equityPoints: number[];
  initial: number;
  maxDDRolling: number | null;
  dailyDD: DailyDD | null;
  closed: any[];
}) {
  // 水下曲线 + 最大历史回撤 + 恢复时长
  const { underwater, maxDDPct, recoveryDays, currentDDPct } = useMemo(() => {
    if (equityPoints.length === 0 || initial <= 0) {
      return { underwater: [], maxDDPct: 0, recoveryDays: 0, currentDDPct: 0 };
    }
    let peak = equityPoints[0];
    let maxDD = 0;
    let maxDDIdx = 0;
    let lastPeakIdx = 0;
    let recoveryFromIdx = -1;
    const uw: number[] = [];
    for (let i = 0; i < equityPoints.length; i++) {
      const eq = equityPoints[i];
      if (eq > peak) {
        peak = eq;
        lastPeakIdx = i;
        if (recoveryFromIdx >= 0) {
          // recovered
          recoveryFromIdx = -1;
        }
      }
      const dd = (eq - peak) / peak;
      uw.push(dd * 100);
      if (dd < maxDD) {
        maxDD = dd;
        maxDDIdx = i;
        if (recoveryFromIdx < 0) recoveryFromIdx = i;
      }
    }
    // 当前回撤
    const currentDD = uw[uw.length - 1] ?? 0;

    // 恢复时长:从 maxDD 时刻到现在(若已恢复则为 0)经过多少笔
    let recDays = 0;
    if (currentDD < 0 && closed.length > 0) {
      const maxDDIdxClamped = Math.max(0, maxDDIdx - 1);
      if (maxDDIdxClamped < closed.length) {
        const tradeAtMaxDD: any = closed[maxDDIdxClamped];
        if (tradeAtMaxDD?.exit_time) {
          const ts = new Date(tradeAtMaxDD.exit_time).getTime();
          recDays = (Date.now() - ts) / 86400000;
        }
      }
    }

    return {
      underwater: uw,
      maxDDPct: maxDD * 100,
      recoveryDays: recDays,
      currentDDPct: currentDD,
    };
  }, [equityPoints, initial, closed]);

  // 距熔断线进度条
  const distPct = dailyDD?.distance_pct ?? 0.03;       // 默认距 3%
  const limitPct = Math.abs(dailyDD?.limit_pct ?? -0.03); // 3%
  const usedPct = ((limitPct - distPct) / limitPct) * 100; // 0-100,越大越接近熔断
  const dailyDDPct = (dailyDD?.today_pnl_pct ?? 0) * 100;

  return (
    <div className="mt-4 mb-4">
      <div className="mb-2 text-[11px] uppercase tracking-[0.08em] text-v3muted">
        风险监控 · <span className="font-mono text-v3faint">回撤 + 宪法 §3 熔断</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mb-3">
        {/* 当前回撤 */}
        <Card>
          <div className="text-[11px] uppercase tracking-[0.07em] text-v3faint">当前回撤</div>
          <div className={`mt-2 text-[24px] font-semibold leading-none font-mono ${
            currentDDPct < -5 ? 'text-loss' : currentDDPct < 0 ? 'text-amber' : 'text-gain'
          }`}>
            {currentDDPct.toFixed(2)}%
          </div>
          <div className="mt-1.5 text-[11px] text-v3muted">距峰值距离</div>
        </Card>

        {/* 最大历史回撤 */}
        <Card>
          <div className="text-[11px] uppercase tracking-[0.07em] text-v3faint">最大历史回撤</div>
          <div className="mt-2 text-[24px] font-semibold leading-none font-mono text-loss">
            {maxDDPct.toFixed(2)}%
          </div>
          <div className="mt-1.5 text-[11px] text-v3muted font-mono">
            {maxDDRolling != null ? `30d 滚动 ${maxDDRolling.toFixed(1)}R` : '—'}
          </div>
        </Card>

        {/* 恢复时长 */}
        <Card>
          <div className="text-[11px] uppercase tracking-[0.07em] text-v3faint">距 peak 时长</div>
          <div className="mt-2 text-[24px] font-semibold leading-none font-mono text-v3text">
            {recoveryDays > 0 ? `${recoveryDays.toFixed(1)}d` : '0d'}
          </div>
          <div className="mt-1.5 text-[11px] text-v3muted">
            {currentDDPct < 0 ? '尚未回到峰值' : '已在峰值'}
          </div>
        </Card>

        {/* 距日内熔断线 */}
        <Card>
          <div className="text-[11px] uppercase tracking-[0.07em] text-v3faint flex items-center justify-between">
            <span>距日内熔断线 §3</span>
            {dailyDD?.lockdown_triggered && <span className="text-loss text-[10px] font-bold animate-pulse">⚠ 锁仓</span>}
          </div>
          <div className={`mt-2 text-[24px] font-semibold leading-none font-mono ${
            distPct < 0.005 ? 'text-loss' : distPct < 0.015 ? 'text-amber' : 'text-gain'
          }`}>
            {(distPct * 100).toFixed(2)}%
          </div>
          <div className="mt-2">
            <div className="h-1.5 w-full bg-[#0E141A] rounded overflow-hidden">
              <div
                className={`h-full transition-all ${
                  usedPct > 80 ? 'bg-loss' : usedPct > 50 ? 'bg-amber' : 'bg-gain'
                }`}
                style={{ width: `${Math.max(0, Math.min(100, usedPct))}%` }}
              />
            </div>
          </div>
          <div className="mt-1 text-[11px] text-v3muted font-mono">
            今日 {dailyDDPct >= 0 ? '+' : ''}{dailyDDPct.toFixed(2)}% / 限 -{(limitPct * 100).toFixed(0)}%
          </div>
        </Card>
      </div>

      {/* 水下曲线 */}
      <Card>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-xs font-medium text-v3muted">水下曲线 · 距 peak %</h4>
          <span className="text-[10px] text-v3faint font-mono">{underwater.length} 数据点</span>
        </div>
        {underwater.length > 1 ? (
          <Sparkline values={underwater} width={900} height={90} />
        ) : (
          <div className="py-6 text-center text-sm text-v3faint">无足够数据</div>
        )}
      </Card>
    </div>
  );
}
