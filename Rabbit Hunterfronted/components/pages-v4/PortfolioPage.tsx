/**
 * PortfolioPage — V3 重写,作为 V3 主导航增项 (2026-06-27)。
 *
 * 持仓详情 + 累计收益曲线 + 已平仓历史 + 4 KPI。
 */
import { useMemo } from 'react';
import { useV5ActivePositions } from '../../hooks/api/useV5ActivePositions';
import { useV5OrderHistory } from '../../hooks/api/useV5OrderHistory';
import { useAccountBalance } from '../../hooks/api/useV5Account';
import { Sparkline } from '../primitives/Sparkline';

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
      <div className={`mt-2 font-semibold leading-none font-mono text-[26px] ${valueColor}`}>{value}</div>
      {sub && <div className="mt-1.5 text-[11.5px] text-v3muted">{sub}</div>}
    </Card>
  );
}

function Badge({ tone, children }: { tone: 'long' | 'short' | 'amber'; children: React.ReactNode }) {
  const map = {
    long:  'text-gain bg-gain/10 border border-gain/30',
    short: 'text-loss bg-loss/10 border border-loss/30',
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
      <span className="w-[22px] h-[22px] rounded-md bg-raised grid place-items-center text-[10px] font-bold text-v3muted">{base}</span>
      {symbol.replace('USDT', '').replace('/', '')}
    </div>
  );
}

export function PortfolioPage() {
  const active = useV5ActivePositions();
  const history = useV5OrderHistory(200);
  const balance = useAccountBalance();

  const positions = active.data?.combined ?? [];
  const closed = useMemo(() => (history.data ?? []).filter((o: any) => o.exit_time), [history.data]);

  const b = balance.data;
  const initial = b?.paper_initial_balance_usdt ?? 10000;
  const realizedPnl = b?.paper_realized_pnl_usdt ?? 0;
  const unrealizedPnl = useMemo(
    () => positions.reduce((acc, p: any) => acc + (p.unrealized_usdt ?? 0), 0),
    [positions],
  );
  const totalEquity = initial + realizedPnl + unrealizedPnl;
  const totalPnl = realizedPnl + unrealizedPnl;
  const totalPnlPct = (totalPnl / initial) * 100;
  const closedN = closed.length;
  const wins = closed.filter((c: any) => (c.pnl_pct ?? 0) > 0).length;
  const winRate = closedN > 0 ? (wins / closedN) * 100 : 0;
  const avgPct = closedN > 0 ? closed.reduce((a: number, c: any) => a + (c.pnl_pct ?? 0), 0) / closedN : 0;

  const equityPoints = useMemo(() => {
    const sorted = closed.slice().reverse();
    let cum = initial;
    const pts = [initial];
    for (const o of sorted as any[]) {
      cum += (o.pnl_usdt ?? 0);
      pts.push(cum);
    }
    return pts;
  }, [closed, initial]);

  return (
    <div className="px-6 pb-10 pt-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mb-5">
        <MetricCard
          label="账户权益"
          value={<>${Math.floor(totalEquity).toLocaleString()}<span className="text-[14px] text-v3faint">.{(totalEquity % 1).toFixed(2).slice(2)}</span></>}
          sub={<span className={totalPnl >= 0 ? 'text-gain' : 'text-loss'}>
            {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)} ({totalPnlPct >= 0 ? '+' : ''}{totalPnlPct.toFixed(2)}%)
          </span>}
        />
        <MetricCard
          label="未实现 PnL"
          value={<>{unrealizedPnl >= 0 ? '+' : ''}${unrealizedPnl.toFixed(2)}</>}
          valueColor={unrealizedPnl >= 0 ? 'text-gain' : 'text-loss'}
          sub={<span className="font-mono text-v3faint">{positions.length} 活仓位</span>}
        />
        <MetricCard
          label="胜率"
          value={<>{winRate.toFixed(0)}<span className="text-[13px] text-v3faint">%</span></>}
          sub={<span className="font-mono">{wins} W / {closedN - wins} L · {closedN} 笔</span>}
        />
        <MetricCard
          label="平均盈亏"
          value={<>{avgPct >= 0 ? '+' : ''}{avgPct.toFixed(2)}<span className="text-[13px] text-v3faint">%</span></>}
          valueColor={avgPct >= 0 ? 'text-gain' : 'text-loss'}
          sub={<span className="text-v3faint">单笔均值</span>}
        />
      </div>

      <Card className="mb-5">
        <div className="flex items-end justify-between mb-3">
          <div>
            <h3 className="text-xs font-medium text-v3muted mb-1.5">权益曲线 · 累计 PnL</h3>
            <div className="text-[11px] text-v3faint">
              {closedN} 笔已结算 · 起始 ${initial.toLocaleString()}
            </div>
          </div>
        </div>
        {equityPoints.length > 1 ? (
          <Sparkline values={equityPoints} width={1000} height={140} />
        ) : (
          <div className="py-10 text-center text-sm text-v3faint">无足够数据绘制曲线</div>
        )}
      </Card>

      <div className="mb-2 text-[11px] uppercase tracking-[0.08em] text-v3muted">
        当前持仓 · <span className="font-mono text-v3faint">{positions.length} / 3 仓位</span>
      </div>
      <Card pad0 className="mb-5">
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
                <th className="px-4 py-2.5 text-right font-normal">SL / TP</th>
                <th className="px-4 py-2.5 text-right font-normal">杠杆</th>
                <th className="px-4 py-2.5 text-right font-normal">仓位</th>
                <th className="px-4 py-2.5 text-right font-normal">未实现 R</th>
                <th className="px-4 py-2.5 text-right font-normal">持仓</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {positions.map((p: any) => {
                const ent = p.entry_price ?? 0;
                const now = p.current_price ?? ent;
                const sl = p.sl_price ?? p.stop_loss ?? 0;
                const tp = p.tp_price ?? p.take_profit ?? 0;
                const size = p.size_usdt ?? p.position_size_usdt ?? 0;
                const lev = p.leverage ?? 5;
                const unrealR = ent && sl ? ((now - ent) / Math.abs(ent - sl)) * (p.side === 'LONG' ? 1 : -1) : 0;
                const holdMin = p.entry_time ? Math.round((Date.now() - new Date(p.entry_time).getTime()) / 60000) : 0;
                // HIGH-1+2: sl/tp_attached=0 表示挂单失败但保留主仓 — 高风险
                const slMissing = p.sl_attached === 0;
                const tpMissing = p.tp_attached === 0;
                const isDegraded = slMissing || tpMissing;
                return (
                  <tr key={p.id ?? p.position_id} className={isDegraded ? 'text-v3text bg-loss/5' : 'text-v3text'}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <SymbolCell symbol={p.symbol} />
                        {isDegraded && (
                          <span title={`保护单缺: ${slMissing ? 'SL' : ''}${slMissing && tpMissing ? '+' : ''}${tpMissing ? 'TP' : ''}`}
                                className="text-[11px] text-loss font-bold animate-pulse">⚠</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={p.side === 'LONG' ? 'long' : 'short'}>
                        {p.side === 'LONG' ? '做多' : '做空'}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-right">{ent.toFixed(ent >= 1 ? 4 : 6)}</td>
                    <td className="px-4 py-3 text-right">{now.toFixed(now >= 1 ? 4 : 6)}</td>
                    <td className="px-4 py-3 text-right text-v3muted">
                      <span className="text-loss">{sl.toFixed(sl >= 1 ? 4 : 6)}</span>
                      <span className="text-v3faint"> / </span>
                      <span className="text-gain">{tp.toFixed(tp >= 1 ? 4 : 6)}</span>
                    </td>
                    <td className="px-4 py-3 text-right text-v3faint">{lev}x</td>
                    <td className="px-4 py-3 text-right text-v3muted">{size.toFixed(2)}</td>
                    <td className={`px-4 py-3 text-right ${unrealR >= 0 ? 'text-gain' : 'text-loss'}`}>
                      {unrealR >= 0 ? '+' : ''}{unrealR.toFixed(2)}R
                    </td>
                    <td className="px-4 py-3 text-right text-v3faint">
                      {Math.floor(holdMin / 60)}h{(holdMin % 60).toString().padStart(2, '0')}m
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>

      <div className="mb-2 text-[11px] uppercase tracking-[0.08em] text-v3muted">
        已平仓 · <span className="font-mono text-v3faint">最近 20 笔 · 共 {closedN}</span>
      </div>
      <Card pad0>
        {closed.length === 0 ? (
          <div className="py-10 text-center text-sm text-v3faint">无已平仓记录</div>
        ) : (
          <table className="w-full font-mono text-sm">
            <thead className="text-[10px] uppercase tracking-[0.08em] text-v3faint">
              <tr className="border-b border-line-soft">
                <th className="px-4 py-2.5 text-left font-normal">时间</th>
                <th className="px-4 py-2.5 text-left font-normal">标的</th>
                <th className="px-4 py-2.5 text-left font-normal">方向</th>
                <th className="px-4 py-2.5 text-left font-normal">出场</th>
                <th className="px-4 py-2.5 text-right font-normal">入/出场价</th>
                <th className="px-4 py-2.5 text-right font-normal">PnL %</th>
                <th className="px-4 py-2.5 text-right font-normal">PnL USDT</th>
                <th className="px-4 py-2.5 text-right font-normal">持仓</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {closed.slice(0, 20).map((o: any) => {
                const pnlPct = o.pnl_pct ?? 0;
                const pnlUsdt = o.pnl_usdt ?? 0;
                const isWin = pnlPct > 0;
                return (
                  <tr key={o.id} className="text-v3text">
                    <td className="px-4 py-2.5 text-v3faint text-xs">
                      {o.exit_time ? new Date(o.exit_time).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}
                    </td>
                    <td className="px-4 py-2.5"><SymbolCell symbol={o.symbol} /></td>
                    <td className="px-4 py-2.5">
                      <Badge tone={o.side === 'LONG' ? 'long' : 'short'}>
                        {o.side === 'LONG' ? '做多' : '做空'}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5 text-v3faint">{o.exit_reason ?? '—'}</td>
                    <td className="px-4 py-2.5 text-right text-v3muted">
                      {(o.entry_price ?? 0).toFixed(4)} / {(o.exit_price ?? 0).toFixed(4)}
                    </td>
                    <td className={`px-4 py-2.5 text-right ${isWin ? 'text-gain' : 'text-loss'}`}>
                      {isWin ? '+' : ''}{pnlPct.toFixed(2)}%
                    </td>
                    <td className={`px-4 py-2.5 text-right ${isWin ? 'text-gain' : 'text-loss'}`}>
                      {pnlUsdt >= 0 ? '+' : ''}{pnlUsdt.toFixed(2)}
                    </td>
                    <td className="px-4 py-2.5 text-right text-v3faint">
                      {o.holding_hours != null ? `${o.holding_hours.toFixed(1)}h` : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
