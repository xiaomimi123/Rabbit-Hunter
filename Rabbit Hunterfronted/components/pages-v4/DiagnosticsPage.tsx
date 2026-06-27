import { useEffect, useMemo, useState } from 'react';
import { useV5AIDecisions, useV5AIStatus } from '../../hooks/api/useV5AIStatus';
import { useV5Signals } from '../../hooks/api/useV5Signals';
import { useV5ActivePositions } from '../../hooks/api/useV5ActivePositions';
import { useV5OrderHistory } from '../../hooks/api/useV5OrderHistory';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { MetricCard } from '../primitives-v3/MetricCard';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { blockReasonZh } from '../pages/_signal_helpers';
import { cn } from '../primitives-v3/cn';

export function DiagnosticsPage() {
  const decisions = useV5AIDecisions(50);
  const aiStatus = useV5AIStatus();
  const signals = useV5Signals(100, { side: null, showExecutedOnly: false });
  const active = useV5ActivePositions();
  const closed = useV5OrderHistory(50);

  const [selectedTraceId, setSelectedTraceId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [selectedShadowOrderId, setSelectedShadowOrderId] = useState<number | null>(null);

  const sigList = signals.data?.data ?? [];
  const decisionList = decisions.data?.decisions ?? [];
  const positions = active.data?.combined ?? [];
  const closedList = closed.data ?? [];

  const lastCycle = sigList[0];
  const cycleSymbols = new Set(sigList.map(s => s.symbol)).size;

  const pages = Math.max(1, Math.ceil(sigList.length / 10));
  const visibleSigs = useMemo(() => sigList.slice((page - 1) * 10, page * 10), [sigList, page]);

  useEffect(() => {
    if (!visibleSigs.length) { setSelectedTraceId(null); return; }
    if (!visibleSigs.some(s => s.id === selectedTraceId)) setSelectedTraceId(visibleSigs[0].id);
  }, [visibleSigs, selectedTraceId]);

  const selectedTrace = sigList.find(s => s.id === selectedTraceId) ?? null;
  const matchedDecision = selectedTrace ? decisionList.find(d => d.symbol === selectedTrace.symbol) : null;

  const allShadow = useMemo(() => [...positions, ...closedList], [positions, closedList]);
  useEffect(() => {
    if (!allShadow.length) { setSelectedShadowOrderId(null); return; }
    if (!allShadow.some(o => o.id === selectedShadowOrderId)) setSelectedShadowOrderId(allShadow[0].id);
  }, [allShadow, selectedShadowOrderId]);
  const selectedShadowOrder = allShadow.find(o => o.id === selectedShadowOrderId) ?? null;

  return (
    <div className="space-y-6">
      <SectionTitle
        title="策略诊断"
        subtitle="信号漏斗、阻断明细、影子持仓与平仓记录"
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="最近周期" value={lastCycle ? new Date(lastCycle.created_at).toLocaleTimeString('zh-CN', { hour12: false }) : '—'} />
        <MetricCard label="本批扫描" value={String(cycleSymbols)} hint="独立 symbol" />
        <MetricCard label="过滤通过" value={String(sigList.filter(s => s.should_trade === 1).length)} hint={`${sigList.length} 总信号`} />
        <MetricCard label="AI 健康" value={aiStatus.data?.healthy ? '在线' : '离线'} trend={aiStatus.data?.healthy ? 'up' : 'down'} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.5fr_420px]">
        <Card title="信号扫描追踪" subtitle="点击行查看 AI 决策步骤" className="!p-0" bodyClassName="!p-0">
          {signals.isLoading ? <div className="p-6"><LoadingSkeleton message="拉取信号…" /></div> : sigList.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-ivory-40">无追踪</div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-bg-base/80">
                    <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wider text-ivory-40">
                      <th className="py-2.5 pl-5 pr-2">时间</th>
                      <th className="py-2.5 px-2">币种</th>
                      <th className="py-2.5 px-2">方向</th>
                      <th className="py-2.5 px-2 text-right">RSI</th>
                      <th className="py-2.5 px-2 text-right">MACD h</th>
                      <th className="py-2.5 pl-2 pr-5">结果</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline/60">
                    {visibleSigs.map(s => (
                      <tr
                        key={s.id}
                        onClick={() => setSelectedTraceId(s.id)}
                        className={cn(
                          'cursor-pointer transition',
                          selectedTraceId === s.id ? 'bg-brass-soft text-indigo-100' : 'hover:bg-bg-surface/40',
                        )}
                      >
                        <td className="py-2 pl-5 pr-2 font-mono text-xs">{new Date(s.created_at).toLocaleTimeString('zh-CN', { hour12: false })}</td>
                        <td className="py-2 px-2 font-mono">{s.symbol}</td>
                        <td className="py-2 px-2"><StatusPill tone={s.side === 'LONG' ? 'emerald' : s.side === 'SHORT' ? 'rose' : 'zinc'}>{s.side ?? '—'}</StatusPill></td>
                        <td className="py-2 px-2 text-right font-mono tabular-nums">{s.rsi_15m.toFixed(1)}</td>
                        <td className="py-2 px-2 text-right font-mono tabular-nums">{s.macd_hist_15m.toFixed(4)}</td>
                        <td className="py-2 pl-2 pr-5">
                          {s.executed === 1 ? <StatusPill tone="emerald">执行</StatusPill>
                            : s.block_reason ? <span className="text-xs text-ivory-70">{blockReasonZh(s.block_reason)}</span>
                            : <span className="text-xs text-ivory-40">—</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="border-t border-hairline flex items-center justify-between px-5 py-3 text-xs text-ivory-70">
                <span>每页 10 条 · 共 {sigList.length} 条</span>
                <div className="flex items-center gap-2">
                  <button type="button" disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="rounded-lg border border-hairline-strong px-3 py-1 disabled:opacity-40 disabled:cursor-not-allowed hover:border-brass">上一页</button>
                  <span>{page} / {pages}</span>
                  <button type="button" disabled={page >= pages} onClick={() => setPage(p => p + 1)} className="rounded-lg border border-hairline-strong px-3 py-1 disabled:opacity-40 disabled:cursor-not-allowed hover:border-brass">下一页</button>
                </div>
              </div>
            </>
          )}
        </Card>

        <Card title="追踪明细" subtitle={selectedTrace?.symbol ?? '点击行查看'} className="xl:sticky xl:top-[120px] self-start max-h-[calc(100vh-160px)] overflow-hidden">
          {selectedTrace ? (
            <div className="space-y-3 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 240px)' }}>
              <Step name="数据拉取" status="pass" detail={`RSI 15m=${selectedTrace.rsi_15m.toFixed(1)} · MACD hist=${selectedTrace.macd_hist_15m.toFixed(4)}`} />
              <Step name="规则过滤" status={selectedTrace.should_trade === 1 ? 'pass' : 'fail'} detail={selectedTrace.reasoning} />
              <Step name="AI 二审" status={selectedTrace.executed === 1 ? 'pass' : selectedTrace.block_reason === 'AI_REJECTED' ? 'fail' : 'skip'} detail={selectedTrace.ai_reasoning ?? '—'} />
              <Step name="风险闸门" status={selectedTrace.block_reason && !selectedTrace.block_reason.startsWith('AI_') && !selectedTrace.block_reason.startsWith('NOT_') ? 'fail' : 'pass'} detail={selectedTrace.block_reason ? blockReasonZh(selectedTrace.block_reason) : '通过所有门'} />
              <Step name="入场" status={selectedTrace.executed === 1 ? 'pass' : 'skip'} detail={selectedTrace.executed === 1 ? `paper trade #${selectedTrace.position_id ?? '—'}` : '未入场'} />
              {matchedDecision && (
                <div className="rounded-2xl border border-hairline bg-bg-base/60 p-3">
                  <div className="text-xs uppercase tracking-wider text-ivory-40 mb-2">关联 AI 决策</div>
                  <div className="text-xs text-ivory-70">置信 {Math.round((matchedDecision.confidence ?? 0) * 100)}% · top1 距 {matchedDecision.top1_distance?.toFixed(2) ?? '—'}</div>
                  <div className="text-xs text-ivory-70 mt-1 leading-relaxed">{matchedDecision.reasoning.slice(0, 200)}</div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-sm text-ivory-40 text-center py-6">点击左侧行</div>
          )}
        </Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="持仓中" value={String(positions.length)} />
        <MetricCard label="已平仓" value={String(closedList.length)} />
        <MetricCard label="未实现 PnL" value={`${positions.reduce((a, p) => a + (p.pnl_usdt ?? 0), 0).toFixed(2)}`} hint="USDT" />
        <MetricCard label="已实现 PnL" value={`${closedList.reduce((a, p) => a + (p.pnl_usdt ?? 0), 0).toFixed(2)}`} hint="USDT" />
        <MetricCard label="胜率" value={`${closedList.length ? Math.round(closedList.filter(p => (p.pnl_pct ?? 0) > 0).length / closedList.length * 100) : 0}%`} />
        <MetricCard label="平均持仓" value={`${closedList.length ? Math.round(closedList.reduce((a, p) => { if (!p.entry_time || !p.exit_time) return a; return a + (new Date(p.exit_time).getTime() - new Date(p.entry_time).getTime()) / 60_000; }, 0) / closedList.length) : 0} min`} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.5fr_420px]">
        <Card title="影子订单" subtitle={`${positions.length} 持仓 + ${closedList.length} 已平仓`} className="!p-0" bodyClassName="!p-0">
          <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-bg-base/80">
                <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wider text-ivory-40">
                  <th className="py-2.5 pl-5 pr-2">时间</th>
                  <th className="py-2.5 px-2">币种</th>
                  <th className="py-2.5 px-2">方向</th>
                  <th className="py-2.5 px-2">状态</th>
                  <th className="py-2.5 pl-2 pr-5 text-right">PnL</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline/60">
                {allShadow.map(o => {
                  const closed = o.exit_time != null;
                  return (
                    <tr
                      key={o.id}
                      onClick={() => setSelectedShadowOrderId(o.id)}
                      className={cn(
                        'cursor-pointer transition',
                        selectedShadowOrderId === o.id ? 'bg-brass-soft text-indigo-100' : 'hover:bg-bg-surface/40',
                      )}
                    >
                      <td className="py-2.5 pl-5 pr-2 font-mono text-xs text-ivory-70">{closed ? new Date(o.exit_time!).toLocaleString('zh-CN', { hour12: false }).slice(5) : new Date(o.entry_time!).toLocaleString('zh-CN', { hour12: false }).slice(5)}</td>
                      <td className="py-2.5 px-2 font-mono text-ivory">{o.symbol}</td>
                      <td className="py-2.5 px-2"><StatusPill tone={o.side === 'LONG' ? 'emerald' : 'rose'}>{o.side}</StatusPill></td>
                      <td className="py-2.5 px-2"><StatusPill tone={closed ? 'zinc' : 'indigo'}>{closed ? 'CLOSED' : 'OPEN'}</StatusPill></td>
                      <td className={cn('py-2.5 pl-2 pr-5 text-right font-mono tabular-nums', (o.pnl_pct ?? 0) >= 0 ? 'text-sage' : 'text-oxblood')}>
                        {(o.pnl_pct ?? 0) >= 0 ? '+' : ''}{(o.pnl_pct ?? 0).toFixed(2)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="订单明细" subtitle={selectedShadowOrder?.symbol ?? '点击行查看'} className="xl:sticky xl:top-[120px] self-start max-h-[calc(100vh-160px)] overflow-hidden">
          {selectedShadowOrder ? (
            <div className="space-y-3 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 240px)' }}>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <KV label="入场" value={selectedShadowOrder.entry_price?.toFixed(4)} />
                <KV label="出场" value={selectedShadowOrder.exit_price?.toFixed(4) ?? '—'} />
                <KV label="止损" value={selectedShadowOrder.sl_price?.toFixed(4)} tone="rose" />
                <KV label="止盈" value={selectedShadowOrder.tp_price?.toFixed(4)} tone="emerald" />
                <KV label="杠杆" value={`×${selectedShadowOrder.leverage}`} />
                <KV label="策略" value={selectedShadowOrder.strategy_id ?? '—'} />
                <KV label="PnL %" value={`${(selectedShadowOrder.pnl_pct ?? 0).toFixed(2)}%`} tone={(selectedShadowOrder.pnl_pct ?? 0) >= 0 ? 'emerald' : 'rose'} />
                <KV label="PnL USDT" value={`${(selectedShadowOrder.pnl_usdt ?? 0).toFixed(2)}`} tone={(selectedShadowOrder.pnl_usdt ?? 0) >= 0 ? 'emerald' : 'rose'} />
              </div>
              {selectedShadowOrder.exit_reason && (
                <div className="rounded-2xl border border-hairline bg-bg-base/60 p-3">
                  <div className="text-xs uppercase tracking-wider text-ivory-40 mb-1">退出原因</div>
                  <div className="text-sm text-ivory">{selectedShadowOrder.exit_reason}</div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-sm text-ivory-40 text-center py-6">点击左侧行</div>
          )}
        </Card>
      </div>
    </div>
  );
}

function Step({ name, status, detail }: { name: string; status: 'pass' | 'fail' | 'skip'; detail: string }) {
  return (
    <div className="rounded-2xl border border-hairline bg-bg-base/60 p-3">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-sm font-medium text-ivory">{name}</span>
        <StatusPill tone={status === 'pass' ? 'emerald' : status === 'fail' ? 'rose' : 'zinc'} className="ml-auto">{status === 'pass' ? '通过' : status === 'fail' ? '失败' : '跳过'}</StatusPill>
      </div>
      <div className="text-xs text-ivory-70 leading-relaxed">{detail}</div>
    </div>
  );
}

function KV({ label, value, tone }: { label: string; value: any; tone?: 'emerald' | 'rose' }) {
  return (
    <div className="rounded-xl border border-hairline bg-bg-base/60 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-ivory-40">{label}</div>
      <div className={cn('font-mono text-sm tabular-nums',
        tone === 'emerald' && 'text-sage',
        tone === 'rose' && 'text-oxblood',
        !tone && 'text-ivory',
      )}>{value ?? '—'}</div>
    </div>
  );
}
