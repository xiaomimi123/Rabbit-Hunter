import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useV5Dashboard } from '../../hooks/api/useV5Dashboard';
import { Card } from '../primitives/Card';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { KpiCard } from '../shared/KpiCard';
import { SignalFunnel } from '../shared/SignalFunnel';
import { WinRateRow } from '../shared/WinRateRow';
import { LineChart as Lc, Line, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts';
import { winRateOf, bySide, byStrategy, byExitReason, bestAndWorst, profitFactor, streaks } from './_winrate_helpers';

export function V5DashboardPage() {
  const q = useV5Dashboard();
  const navigate = useNavigate();
  if (q.isLoading) return <LoadingSkeleton rows={6} />;
  const d = q.data;
  if (!d) return <div className="text-white/40">无数据</div>;

  const winRatePct = Math.round(d.win_rate_24h * 100);
  const pnlSeries = d.closed_24h
    .slice()
    .sort((a, b) => (a.exit_time || '').localeCompare(b.exit_time || ''))
    .reduce<{ time: string; cum: number }[]>((acc, p) => {
      const prev = acc.length > 0 ? acc[acc.length - 1].cum : 0;
      acc.push({
        time: p.exit_time ? new Date(p.exit_time).toLocaleTimeString('zh-CN', { hour12: false }) : '',
        cum: prev + (p.pnl_usdt ?? 0),
      });
      return acc;
    }, []);

  const funnelSteps = [
    { name: 'Scanner 扫到', count: d.signals_24h },
    { name: '通过 AND', count: d.signals_passed_and },
    { name: '实际开仓', count: d.signals_executed },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        <KpiCard title="胜率" value={`${winRatePct}%`} />
        <KpiCard title="累计 PnL" value={d.pnl_total_usdt.toFixed(2)} unit="USDT" />
        <KpiCard title="平均持仓" value={Math.round(d.avg_holding_minutes)} unit="min" />
        <KpiCard title="活仓数" value={`${d.active_count} / 3`} />
      </div>

      <Card title="24h 信号漏斗">
        <SignalFunnel steps={funnelSteps} onLayerClick={(s) => {
          if (s.name === '实际开仓') navigate('/v5/history?block_reason=EXECUTED');
          else navigate('/v5/history');
        }} />
      </Card>

      <Card title="24h PnL 曲线">
        {pnlSeries.length === 0 ? (
          <div className="py-8 text-center text-white/40">24h 内无平仓</div>
        ) : (
          <div className="h-48 w-full">
            <ResponsiveContainer>
              <Lc data={pnlSeries}>
                <XAxis dataKey="time" stroke="rgba(255,255,255,0.4)" fontSize={10} />
                <YAxis stroke="rgba(255,255,255,0.4)" fontSize={10} />
                <Tooltip contentStyle={{ background: '#1A2030', border: '1px solid rgba(255,255,255,0.1)' }} />
                <Line type="monotone" dataKey="cum" stroke="#3B82F6" strokeWidth={2} dot={false} />
              </Lc>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      {(() => {
        const closed = d.closed_24h;
        const overall = winRateOf(closed);
        const side = bySide(closed);
        const strat = byStrategy(closed);
        const reasons = byExitReason(closed);
        const bw = bestAndWorst(closed);
        const pf = profitFactor(closed);
        const sk = streaks(closed);
        return (
          <Card title={`24h 胜率总览 (n=${closed.length})`}>
            {closed.length === 0 ? (
              <div className="py-6 text-center text-white/40">24h 内无平仓样本</div>
            ) : (
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-1">
                  <div className="text-xs text-white/50 mb-2">按方向</div>
                  <WinRateRow label="LONG" data={side.long} />
                  <WinRateRow label="SHORT" data={side.short} />
                  <div className="text-xs text-white/50 mt-3 mb-2">按策略</div>
                  <WinRateRow label="自动 (v5_rsi_macd)" data={strat.auto} />
                  <WinRateRow label="手动 (v5_manual)" data={strat.manual} />
                  <div className="text-xs text-white/50 mt-3 mb-2">按平仓原因</div>
                  {Object.entries(reasons)
                    .sort((a, b) => b[1].count - a[1].count)
                    .map(([reason, br]) => (
                      <WinRateRow key={reason} label={reason} data={br} />
                    ))}
                </div>

                <div className="space-y-3 text-xs">
                  <div>
                    <div className="text-white/50 mb-1">总样本</div>
                    <div className="font-mono text-base text-white">
                      {overall.wins}W <span className="text-white/40">/</span> {overall.losses}L
                      <span className="text-white/40 ml-2">= {Math.round(overall.win_rate * 100)}%</span>
                    </div>
                  </div>
                  <div>
                    <div className="text-white/50 mb-1">Profit Factor</div>
                    <div className="font-mono text-base text-white">
                      {pf === null ? '∞' : pf.toFixed(2)}
                      <span className="text-white/40 text-xs ml-2">gross win / gross loss</span>
                    </div>
                  </div>
                  <div>
                    <div className="text-white/50 mb-1">最佳单</div>
                    {bw.best && (bw.best.pnl_pct ?? 0) > 0
                      ? <div className="font-mono text-accent-long">{bw.best.symbol} +{(bw.best.pnl_pct ?? 0).toFixed(2)}% ({(bw.best.pnl_usdt ?? 0).toFixed(2)} USDT)</div>
                      : <div className="font-mono text-white/40">—</div>}
                  </div>
                  <div>
                    <div className="text-white/50 mb-1">最差单</div>
                    {bw.worst && (bw.worst.pnl_pct ?? 0) < 0
                      ? <div className="font-mono text-accent-short">{bw.worst.symbol} {(bw.worst.pnl_pct ?? 0).toFixed(2)}% ({(bw.worst.pnl_usdt ?? 0).toFixed(2)} USDT)</div>
                      : <div className="font-mono text-white/40">—</div>}
                  </div>
                  <div>
                    <div className="text-white/50 mb-1">最大连胜 / 连败</div>
                    <div className="font-mono text-white">
                      <span className="text-accent-long">{sk.maxWin}W</span>
                      <span className="text-white/40 mx-2">/</span>
                      <span className="text-accent-short">{sk.maxLoss}L</span>
                      {sk.current.side && (
                        <span className="text-white/40 ml-3 text-[11px]">
                          当前连续 {sk.current.len} 笔 {sk.current.side === 'W' ? '胜' : '败'}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </Card>
        );
      })()}

      <Card title="拦截原因分布">
        <div className="space-y-1">
          {Object.entries(d.signals_block_counts)
            .sort((a, b) => b[1] - a[1])
            .map(([k, v]) => (
              <div key={k} className="flex items-center justify-between text-xs">
                <span className="text-white/70">{k}</span>
                <span className="font-mono text-white">{v}</span>
              </div>
            ))}
        </div>
      </Card>
    </div>
  );
}
