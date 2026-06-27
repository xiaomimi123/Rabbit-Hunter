import { Shield, AlertTriangle, CheckCircle } from 'lucide-react';
import { useV5AIStatus } from '../../hooks/api/useV5AIStatus';
import { useV5ActivePositions } from '../../hooks/api/useV5ActivePositions';
import { useV5OrderHistory } from '../../hooks/api/useV5OrderHistory';
import { useV5FundingStatus } from '../../hooks/api/useV5Funding';
import { useConstitution, useIronlawState } from '../../hooks/api/useV5Constitution';
import { useUIStore } from '../../services/store';
import { useSystemMode } from '../../hooks/useSystemMode';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { MetricCard } from '../primitives-v3/MetricCard';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { Alert } from '../primitives-v3/Alert';
import { cn } from '../primitives-v3/cn';

export function ReliabilityPage() {
  const ai = useV5AIStatus();
  const active = useV5ActivePositions();
  const orders = useV5OrderHistory(50);
  const funding = useV5FundingStatus();
  const { mode } = useSystemMode();
  const wsEvents = useUIStore(s => s.recentWsEvents);

  const aiHealthy = ai.data?.healthy ?? false;
  const positions = active.data?.combined ?? [];
  const recent = orders.data ?? [];
  const fundingExtremes = (funding.data?.data ?? []).filter(f => f.is_extreme);

  const lifecycleRows = [
    ...positions.map(p => ({ id: `o-${p.id}`, time: p.entry_time, symbol: p.symbol, side: p.side, action: 'OPEN', source: 'auto' as const })),
    ...recent.slice(0, 30).map(p => ({ id: `c-${p.id}`, time: p.exit_time, symbol: p.symbol, side: p.side, action: p.exit_reason ?? 'CLOSE', source: (p.exit_reason === 'MANUAL_USER' ? 'manual' : 'auto') as 'auto' | 'manual' })),
  ].filter(r => r.time).sort((a, b) => new Date(b.time!).getTime() - new Date(a.time!).getTime()).slice(0, 30);

  const constitution = useConstitution();
  const ironlaw = useIronlawState();
  const c = constitution.data;
  const ils = ironlaw.data;

  return (
    <div className="space-y-6">
      <SectionTitle
        title="执行可靠性"
        subtitle="M3 铁律层 + 系统状态 + 订单生命周期 + 安全事件"
      />

      {ils?.daily_dd_triggered && (
        <Alert tone="error">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            <span>日熔断已触发 — 今日已实现 {ils.today_realized_pnl.toFixed(2)} USDT,新单已锁。</span>
          </div>
        </Alert>
      )}

      <Card
        title="M3 铁律层 · 宪法"
        subtitle="任何模块违规直接 raise IronlawViolation,Fail-closed 拒单"
        actions={
          <StatusPill tone={ils?.daily_dd_triggered ? 'rose' : 'emerald'} icon={ils?.daily_dd_triggered ? <AlertTriangle className="h-3 w-3" /> : <Shield className="h-3 w-3" />}>
            {ils?.daily_dd_triggered ? '熔断中' : '生效'}
          </StatusPill>
        }
      >
        {c ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Iron label="单笔风险上限" value={`${(c.max_per_trade_risk_pct * 100).toFixed(1)}%`} hint="of equity" />
            <Iron label="日熔断阈值" value={`${(c.daily_drawdown_limit_pct * 100).toFixed(1)}%`} hint="today realized ≤" />
            <Iron label="盈亏比下限" value={`${c.min_rr.toFixed(2)}`} hint="TP / SL ≥" />
            <Iron label="强平距 / SL" value={`≥ ${c.min_liq_to_sl_distance_ratio.toFixed(1)}×`} hint="LIQ_TOO_CLOSE 拒" />
            <Iron label="SL/ATR 落地区间" value={`[${c.final_sl_atr_ratio_min}, ${c.final_sl_atr_ratio_max}]`} hint="窄区间 evolution" />
            <Iron label="进化 SL 修正器" value={`[${c.evolution_ai_sl_mult_min}, ${c.evolution_ai_sl_mult_max}]`} hint="AI 修正窗口" />
            <Iron label="进化仓位系数" value={`[${c.evolution_size_mult_min}, ${c.evolution_size_mult_max}]`} hint="AI 修正窗口" />
            <Iron label="M8 决策门槛" value={`n ≥ ${c.min_sample_size_for_decision}`} hint="setup 可信样本数" />
          </div>
        ) : <div className="text-sm text-ivory-40">拉取宪法中…</div>}
      </Card>

      {ils && (
        <Card title="运行时风控状态" subtitle="今日已实现 + 日 DD 剩余 + 活仓占用">
          <div className="grid gap-3 sm:grid-cols-3">
            <Iron
              label="今日已实现 PnL"
              value={`${ils.today_realized_pnl >= 0 ? '+' : ''}${ils.today_realized_pnl.toFixed(2)} USDT`}
              tone={ils.today_realized_pnl >= 0 ? 'emerald' : 'rose'}
            />
            <Iron
              label="日 DD 剩余预算"
              value={`${ils.daily_dd_remaining_usdt.toFixed(2)} USDT`}
              hint={ils.daily_dd_triggered ? '已耗尽 — 新单锁' : '可继续开仓'}
              tone={ils.daily_dd_triggered ? 'rose' : 'emerald'}
            />
            <Iron
              label="槽位"
              value={`${ils.open_positions} / ${ils.max_concurrent}`}
              hint={ils.open_positions >= ils.max_concurrent ? '满仓' : `${ils.max_concurrent - ils.open_positions} 空闲`}
            />
          </div>
          {c && c.default_disabled_setups.length > 0 && (
            <div className="mt-4">
              <div className="text-xs uppercase tracking-wider text-ivory-40 mb-2">默认禁用 setup(文档 §4 + M8 剪枝)</div>
              <div className="flex flex-wrap gap-2">
                {c.default_disabled_setups.map(s => (
                  <StatusPill key={s} tone="rose">{s}</StatusPill>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <MetricCard label="系统模式" value={mode ?? '—'} trend={mode === 'LIVE' ? 'down' : 'neutral'} hint={mode === 'LIVE' ? '实盘 — 真实资金' : '影子盘 — 仅记录'} />
        <MetricCard label="AI 健康" value={aiHealthy ? '在线' : '离线'} trend={aiHealthy ? 'up' : 'down'} hint={ai.data?.healthy_ratio_24h != null ? `24h ${Math.round(ai.data.healthy_ratio_24h * 100)}% healthy` : '—'} />
        <MetricCard label="活仓 / 槽位" value={`${positions.length} / 3`} hint={positions.length === 3 ? '满仓' : `${3 - positions.length} 空闲`} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="订单生命周期" subtitle={`最近 ${lifecycleRows.length} 个事件`} className="!p-0" bodyClassName="!p-0">
          {lifecycleRows.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-ivory-40">无订单事件</div>
          ) : (
            <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-bg-surface/95">
                  <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wider text-ivory-40">
                    <th className="py-2.5 pl-5 pr-2">时间</th>
                    <th className="py-2.5 px-2">币种</th>
                    <th className="py-2.5 px-2">方向</th>
                    <th className="py-2.5 px-2">事件</th>
                    <th className="py-2.5 pl-2 pr-5">来源</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline/60">
                  {lifecycleRows.map(r => (
                    <tr key={r.id} className="hover:bg-bg-surface/40">
                      <td className="py-2.5 pl-5 pr-2 font-mono text-xs text-ivory-70 whitespace-nowrap">
                        {r.time ? new Date(r.time).toLocaleString('zh-CN', { hour12: false }).slice(5) : '—'}
                      </td>
                      <td className="py-2.5 px-2 font-mono text-ivory">{r.symbol}</td>
                      <td className="py-2.5 px-2"><StatusPill tone={r.side === 'LONG' ? 'emerald' : 'rose'}>{r.side}</StatusPill></td>
                      <td className="py-2.5 px-2">
                        <span className={cn(
                          'text-xs',
                          r.action === 'OPEN' ? 'text-ink' :
                          r.action === 'TP_HIT' ? 'text-sage' :
                          r.action === 'SL_HIT' ? 'text-oxblood' :
                          'text-brass',
                        )}>{r.action}</span>
                      </td>
                      <td className="py-2.5 pl-2 pr-5">
                        <StatusPill tone={r.source === 'manual' ? 'indigo' : 'zinc'}>
                          {r.source === 'manual' ? '手动' : '自动'}
                        </StatusPill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="安全事件 / 风险信号" subtitle={`funding 极端 + WS 队列`} className="!p-0" bodyClassName="!p-0">
          <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-bg-surface/95">
                <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wider text-ivory-40">
                  <th className="py-2.5 pl-5 pr-2">类型</th>
                  <th className="py-2.5 px-2">对象</th>
                  <th className="py-2.5 px-2">值</th>
                  <th className="py-2.5 pl-2 pr-5">严重性</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline/60">
                {fundingExtremes.length === 0 && wsEvents.length === 0 ? (
                  <tr><td colSpan={4} className="px-4 py-10 text-center text-sm text-ivory-40">无安全事件</td></tr>
                ) : (
                  <>
                    {fundingExtremes.slice(0, 20).map(f => (
                      <tr key={f.symbol} className="hover:bg-bg-surface/40">
                        <td className="py-2.5 pl-5 pr-2 text-xs text-brass">FUNDING_EXTREME</td>
                        <td className="py-2.5 px-2 font-mono text-ivory">{f.symbol}</td>
                        <td className="py-2.5 px-2 font-mono text-xs text-ivory-70">
                          z={(f.zscore_30d ?? 0).toFixed(2)} · {f.extreme_direction === 'long_crowded' ? '多头拥挤' : '空头拥挤'}
                        </td>
                        <td className="py-2.5 pl-2 pr-5">
                          <StatusPill tone={Math.abs(f.zscore_30d ?? 0) >= 3 ? 'rose' : 'amber'}>
                            {Math.abs(f.zscore_30d ?? 0) >= 3 ? 'HIGH' : 'MED'}
                          </StatusPill>
                        </td>
                      </tr>
                    ))}
                    {wsEvents.slice(-10).reverse().map((e, i) => (
                      <tr key={`ws-${i}`} className="hover:bg-bg-surface/40">
                        <td className="py-2.5 pl-5 pr-2 text-xs text-ink">{e.type}</td>
                        <td className="py-2.5 px-2 font-mono text-ivory">{(e as any).symbol ?? '—'}</td>
                        <td className="py-2.5 px-2 font-mono text-xs text-ivory-70 truncate max-w-[200px]">{JSON.stringify(e).slice(0, 80)}</td>
                        <td className="py-2.5 pl-2 pr-5"><StatusPill tone="zinc">INFO</StatusPill></td>
                      </tr>
                    ))}
                  </>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}

function Iron({ label, value, hint, tone }: {
  label: string;
  value: string;
  hint?: string;
  tone?: 'emerald' | 'rose';
}) {
  return (
    <div className="rounded-2xl border border-hairline bg-bg-base/60 p-3">
      <div className="text-[10px] uppercase tracking-wider text-ivory-40">{label}</div>
      <div className={cn(
        'mt-1 font-mono text-lg font-semibold tabular-nums',
        tone === 'emerald' && 'text-sage',
        tone === 'rose' && 'text-oxblood',
        !tone && 'text-ivory',
      )}>{value}</div>
      {hint && <div className="text-[11px] text-ivory-40 mt-0.5">{hint}</div>}
    </div>
  );
}
