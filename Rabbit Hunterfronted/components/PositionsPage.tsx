/**
 * Positions Page — active positions management.
 * Uses React Query for data (no manual setInterval).
 */

import React, { useState } from 'react';
import {
  Activity, ShieldAlert, Target, Loader2, AlertTriangle,
  RotateCcw, ArrowUpRight, ArrowDownRight, FlaskConical,
} from 'lucide-react';
import { usePositions, useInvalidatePositions } from '../hooks/usePositions';
import { positionsAPI, tradeAPI, accountAPI } from '../services/api';
import { useQuery } from '@tanstack/react-query';
import { Position } from '../types';
import { PnlDisplay } from '../ui/PnlDisplay';
import { SideBadge } from '../ui/Badge';
import { LoadingSkeleton } from '../ui/LoadingSkeleton';
import { toast } from './Toast';
import ConfirmModal from './ui/ConfirmModal';
import { useSystemMode } from '../hooks/useSystemMode';
import { usePaperTrades } from '../hooks/usePaperTrades';
import { useExchange } from '../hooks/useExchange';
import { Card, EmptyState, NumberCell, Pill, StatTile } from './ui/Primitives';

// ─── account balance sub-query ────────────────────────────────────────────────

function useAccountBalance() {
  return useQuery({
    queryKey: ['accountBalance'],
    queryFn: () => accountAPI.getBalance(),
    refetchInterval: 30_000,
    staleTime: 20_000,
  });
}

// ─── component ───────────────────────────────────────────────────────────────

export default function PositionsPage() {
  // v0.5.4: tab 切换 实盘 / 试盘（虚拟仓位）
  const [activeTab, setActiveTab] = useState<'real' | 'paper'>('paper');

  const [closing, setClosing] = useState<string | null>(null);
  const [closingAll, setClosingAll] = useState(false);
  const [confirmTarget, setConfirmTarget] = useState<
    | { kind: 'single'; pos: Position }
    | { kind: 'all' }
    | { kind: 'emergency' }
    | null
  >(null);

  const invalidatePositions = useInvalidatePositions();
  const { isLive } = useSystemMode();
  const { data: exchangeInfo } = useExchange();
  const exLabel = exchangeInfo?.label || 'broker';

  const { data: positions = [], isLoading, error } = usePositions();
  const { data: accountBalance } = useAccountBalance();

  const totalUnrealized = positions.reduce((s, p) => s + (p.pnl ?? 0), 0);
  const totalRealized   = positions.reduce((s, p) => s + (p.realizedPnl ?? 0), 0);

  async function executeClose() {
    if (!confirmTarget) return;
    try {
      if (confirmTarget.kind === 'single') {
        const pos = confirmTarget.pos;
        const key = pos.id ?? pos.symbol;
        setClosing(key);
        await tradeAPI.close(pos.symbol, 'MARKET');
        toast.success(`平仓成功: ${pos.symbol}`);
      } else {
        setClosingAll(true);
        await Promise.all(positions.map((p) => tradeAPI.close(p.symbol, 'MARKET')));
        toast.success(confirmTarget.kind === 'emergency' ? '紧急全平已执行' : '批量平仓成功');
      }
      await invalidatePositions();
      setConfirmTarget(null);
    } catch (err: any) {
      toast.error(`操作失败: ${err?.message ?? err}`);
    } finally {
      setClosing(null);
      setClosingAll(false);
    }
  }

  const handleClose = (pos: Position) => setConfirmTarget({ kind: 'single', pos });
  const handleCloseAll = () => setConfirmTarget({ kind: 'all' });
  const handleEmergencyClose = () => setConfirmTarget({ kind: 'emergency' });

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Tab switcher — 实盘 / 试盘 */}
      <div className="flex items-center justify-between">
        <div className="inline-flex rounded border border-terminal-border overflow-hidden">
          <button
            onClick={() => setActiveTab('paper')}
            className={`px-4 py-2 text-[12px] uppercase tracking-micro transition-colors inline-flex items-center gap-1.5 ${
              activeTab === 'paper'
                ? 'bg-primary/12 text-primary'
                : 'text-text-secondary hover:bg-terminal-hover hover:text-text-primary'
            }`}
          >
            <FlaskConical size={12} strokeWidth={1.6} />
            试盘
          </button>
          <button
            onClick={() => setActiveTab('real')}
            className={`px-4 py-2 text-[12px] uppercase tracking-micro transition-colors border-l border-terminal-border ${
              activeTab === 'real'
                ? 'bg-bear/15 text-bear'
                : 'text-text-secondary hover:bg-terminal-hover hover:text-text-primary'
            }`}
          >
            实盘
          </button>
        </div>
        <div className="text-[11px] text-text-muted">
          {activeTab === 'paper'
            ? '虚拟仓位 — 信号触发后由 paper_monitor 跟踪 OKX 实时价 + 自动结算'
            : '真实下单到 OKX'}
        </div>
      </div>

      {activeTab === 'paper' && <PaperPositionsView />}

      {activeTab === 'real' && (
        <RealPositionsContent
          positions={positions}
          isLoading={isLoading}
          error={error}
          accountBalance={accountBalance}
          totalUnrealized={totalUnrealized}
          totalRealized={totalRealized}
          closing={closing}
          closingAll={closingAll}
          handleClose={handleClose}
          handleCloseAll={handleCloseAll}
          handleEmergencyClose={handleEmergencyClose}
        />
      )}

      {/* Confirm modals (single / batch / emergency) */}
      <ConfirmModal
        open={confirmTarget?.kind === 'single'}
        title="确认平仓"
        description={isLive
          ? `此操作将立即向 ${exLabel} 提交反向市价单。`
          : '当前为影子模式，操作不会真实成交（仅更新虚拟仓位状态）。'}
        details={confirmTarget?.kind === 'single' ? [
          { label: '交易对', value: confirmTarget.pos.symbol },
          { label: '方向',   value: confirmTarget.pos.side === 'LONG' ? '做多' : '做空',
            tone: confirmTarget.pos.side === 'LONG' ? 'bull' : 'bear' },
          { label: '当前盈亏', value: (confirmTarget.pos.pnl ?? 0).toFixed(2) + ' USDT',
            tone: (confirmTarget.pos.pnl ?? 0) >= 0 ? 'bull' : 'bear' },
        ] : []}
        confirmLabel="确认平仓"
        destructive={isLive}
        loading={closing != null}
        onConfirm={executeClose}
        onCancel={() => setConfirmTarget(null)}
      />
      <ConfirmModal
        open={confirmTarget?.kind === 'all' || confirmTarget?.kind === 'emergency'}
        title={confirmTarget?.kind === 'emergency' ? '紧急全平' : '批量平仓'}
        description={confirmTarget?.kind === 'emergency'
          ? '立刻市价关闭所有持仓。请确认你已检查市场流动性。'
          : '将依次以市价单关闭每一个活跃持仓。'}
        details={[
          { label: '将关闭', value: `${positions.length} 个持仓` },
          { label: '未实现盈亏', value: totalUnrealized.toFixed(2) + ' USDT',
            tone: totalUnrealized >= 0 ? 'bull' : 'bear' },
          { label: '模式', value: isLive ? '实盘' : '影子', tone: isLive ? 'bear' : 'warn' },
        ]}
        confirmLabel={confirmTarget?.kind === 'emergency' ? '紧急执行' : '全部平仓'}
        destructive
        loading={closingAll}
        onConfirm={executeClose}
        onCancel={() => setConfirmTarget(null)}
      />
    </div>
  );
}

// ─── 把原来的实盘视图抽成一个子组件 ──────────────────────────────────────────

interface RealPositionsContentProps {
  positions: Position[];
  isLoading: boolean;
  error: any;
  accountBalance: any;
  totalUnrealized: number;
  totalRealized: number;
  closing: string | null;
  closingAll: boolean;
  handleClose: (pos: Position) => void;
  handleCloseAll: () => void;
  handleEmergencyClose: () => void;
}

const RealPositionsContent: React.FC<RealPositionsContentProps> = ({
  positions, isLoading, error, accountBalance, totalUnrealized, totalRealized,
  closing, closingAll, handleClose, handleCloseAll, handleEmergencyClose,
}) => {
  return (
    <>
      {/* Stats bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-terminal-card border border-terminal-border rounded-lg px-4 py-3">
        <div className="flex flex-wrap gap-6">
          <Stat label="已实现" value={<PnlDisplay value={totalRealized} />} />
          <Stat label="未实现 UPNL" value={<PnlDisplay value={totalUnrealized} />} />
          <Stat label="活跃头寸" value={<span className="font-mono text-text-primary">{positions.length}</span>} />
          {accountBalance && (
            <>
              <Stat
                label="账户余额"
                value={
                  <span className="font-mono text-text-primary">
                    {accountBalance.balance?.toFixed(2)} {accountBalance.asset ?? 'USDT'}
                    {accountBalance.testnet && <span className="ml-1 text-warn text-[10px]">测试网</span>}
                  </span>
                }
              />
              <Stat
                label="可用余额"
                value={<span className="font-mono text-bull">{accountBalance.availableBalance?.toFixed(2)}</span>}
              />
            </>
          )}
        </div>

        <div className="flex gap-2">
          <button
            onClick={handleCloseAll}
            disabled={closingAll || positions.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono bg-terminal-card border border-terminal-border rounded hover:bg-terminal-hover transition-colors disabled:opacity-40"
          >
            {closingAll ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />}
            全部平仓
          </button>
          <button
            onClick={handleEmergencyClose}
            disabled={closingAll || positions.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono bg-bear-dim text-bear border border-bear/30 rounded hover:bg-bear/20 transition-colors disabled:opacity-40"
          >
            {closingAll ? <Loader2 size={12} className="animate-spin" /> : <ShieldAlert size={12} />}
            紧急全平
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 bg-bear-dim border border-bear/30 rounded-lg p-3 text-xs text-bear">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          {String(error)}
        </div>
      )}

      {/* Table */}
      <div className="flex-1 bg-terminal-card border border-terminal-border rounded-lg overflow-hidden flex flex-col">
        <div className="px-4 py-3 border-b border-terminal-border flex items-center gap-2">
          <Activity size={14} className="text-bull" />
          <span className="text-sm font-mono text-text-primary">实时作战头寸</span>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading && positions.length === 0 ? (
            <div className="p-4"><LoadingSkeleton rows={4} /></div>
          ) : positions.length === 0 ? (
            <div className="flex items-center justify-center h-40 text-text-muted text-sm font-mono">
              暂无活跃持仓
            </div>
          ) : (
            <table className="w-full text-left border-collapse">
              <thead className="sticky top-0 bg-terminal-card border-b border-terminal-border z-10">
                <tr>
                  {['交易对', '规模 / 杠杆', '开仓 / 现价', '止损 / 止盈', '盈亏', '操作'].map((h) => (
                    <th key={h} className="px-4 py-2.5 text-[10px] font-mono text-text-muted uppercase tracking-wider">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => {
                  const posKey = pos.id ?? pos.symbol;
                  const cur = pos.currentPrice ?? pos.entryPrice ?? 0;
                  const entry = pos.entryPrice ?? 0;
                  const sl = pos.atrStop;
                  const tp = pos.takeProfit;

                  // Price change from entry
                  const priceDelta = entry > 0 ? ((cur - entry) / entry) * 100 : 0;
                  const priceUp = pos.side === 'LONG' ? priceDelta >= 0 : priceDelta <= 0;

                  // SL distance %
                  const slDist = sl && cur > 0
                    ? Math.abs(((cur - sl) / cur) * 100) : 0;
                  const slDanger = slDist < 2;

                  // TP distance %
                  const tpDist = tp && cur > 0
                    ? Math.abs(((tp - cur) / cur) * 100) : 0;

                  // Progress bar: position of current price between SL and TP
                  let slTpPct = 50;
                  if (sl && tp && tp !== sl) {
                    const range = Math.abs(tp - sl);
                    const fromSl = Math.abs(cur - sl);
                    slTpPct = Math.min(100, Math.max(0, (fromSl / range) * 100));
                    if (pos.side === 'SHORT') slTpPct = 100 - slTpPct;
                  }

                  return (
                    <tr key={posKey} className="border-b border-terminal-border hover:bg-terminal-hover transition-colors">
                      {/* Symbol */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className={`w-0.5 h-10 rounded-full ${pos.side === 'LONG' ? 'bg-bull' : 'bg-bear'}`} />
                          <div>
                            <div className="text-sm font-bold text-text-primary font-mono">{pos.symbol}</div>
                            <SideBadge side={pos.side} />
                            {(pos as any).strategy_id && (
                              <div className="text-[10px] font-mono text-primary/70 mt-0.5">
                                {(pos as any).strategy_id}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Size / leverage */}
                      <td className="px-4 py-3 font-mono text-xs">
                        <div className="text-text-primary">{pos.size ?? '—'} <span className="text-text-muted">张</span></div>
                        <div className="text-text-muted mt-0.5">
                          {pos.leverage ?? 1}x 杠杆
                        </div>
                        <div className="text-text-muted">
                          保证金{' '}
                          <span className="text-text-secondary">
                            {pos.entryPrice && pos.leverage && pos.size
                              ? ((Number(pos.size) * pos.entryPrice) / (pos.leverage ?? 1)).toFixed(2)
                              : '—'} USDT
                          </span>
                        </div>
                      </td>

                      {/* Entry / current price */}
                      <td className="px-4 py-3 font-mono text-xs">
                        <div className="text-text-muted text-[10px] mb-0.5">开仓</div>
                        <div className="text-text-secondary">{entry > 0 ? entry.toFixed(4) : '—'}</div>
                        <div className="text-text-muted text-[10px] mt-1 mb-0.5">现价</div>
                        <div className={`flex items-center gap-1 font-bold ${priceUp ? 'text-bull' : 'text-bear'}`}>
                          {priceUp ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}
                          {cur > 0 ? cur.toFixed(4) : '—'}
                          {entry > 0 && (
                            <span className="text-[10px] font-normal ml-0.5">
                              ({priceDelta >= 0 ? '+' : ''}{priceDelta.toFixed(2)}%)
                            </span>
                          )}
                        </div>
                      </td>

                      {/* SL / TP */}
                      <td className="px-4 py-3">
                        {/* SL row */}
                        <div className="flex items-center justify-between text-[10px] font-mono">
                          <span className="text-bear">SL</span>
                          <span className="text-text-secondary">{sl ? sl.toFixed(4) : '—'}</span>
                          <span className={`ml-1 ${slDanger ? 'text-bear font-bold' : 'text-text-muted'}`}>
                            {sl ? `-${slDist.toFixed(1)}%` : ''}
                          </span>
                        </div>

                        {/* Progress bar: SL ← current → TP (monotone, no gradient) */}
                        {sl && tp && (
                          <div className="relative my-1.5 h-[2px] w-full bg-terminal-border">
                            <div
                              className="absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-text-primary"
                              style={{ left: `calc(${slTpPct}% - 3px)` }}
                            />
                          </div>
                        )}

                        {/* TP row */}
                        <div className="flex items-center justify-between text-[10px] font-mono">
                          <span className="text-bull">TP</span>
                          <span className="text-text-secondary">{tp ? tp.toFixed(4) : '—'}</span>
                          <span className="text-text-muted ml-1">
                            {tp ? `+${tpDist.toFixed(1)}%` : ''}
                          </span>
                        </div>
                      </td>

                      {/* PnL */}
                      <td className="px-4 py-3">
                        {pos.pnl !== undefined ? (
                          <PnlDisplay value={pos.pnl} percent={pos.pnlPercent} />
                        ) : (
                          <span className="text-text-muted font-mono text-xs">—</span>
                        )}
                      </td>

                      {/* Action */}
                      <td className="px-4 py-3">
                        <button
                          onClick={() => handleClose(pos)}
                          disabled={closing === posKey || closingAll}
                          className="flex items-center gap-1 px-2.5 py-1 text-xs font-mono bg-bear-dim text-bear border border-bear/30 rounded hover:bg-bear/20 transition-colors disabled:opacity-40"
                        >
                          {closing === posKey ? <Loader2 size={10} className="animate-spin" /> : <Target size={10} />}
                          平仓
                        </button>
                        {(pos as any).ai_confidence && (
                          <div className="mt-1.5 text-[10px] font-mono text-primary/70">
                            AI {Math.round((pos as any).ai_confidence * 100)}%
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
};

// ─── PaperPositionsView：试盘 tab 的内容 ─────────────────────────────────────

const PaperPositionsView: React.FC = () => {
  const { data, isLoading } = usePaperTrades('all', 200);
  const rows: any[] = data?.data ?? [];
  const kpi = data?.kpi ?? null;

  const openRows = rows.filter((r) => (r.status || '').toUpperCase() === 'OPEN');
  const closedRows = rows.filter((r) => (r.status || '').toUpperCase() === 'CLOSED');

  return (
    <div className="space-y-3">
      {/* KPI 4 瓦 */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile
          label="累计虚拟 PnL"
          value={kpi ? (
            <NumberCell value={kpi.total_pnl_usdt} decimals={2} suffix=" USDT" signColor className="text-2xl" />
          ) : '—'}
          loading={isLoading}
          hint="基于已结算的虚拟交易"
        />
        <StatTile
          label="胜率"
          value={kpi ? `${kpi.win_rate_pct.toFixed(1)}%` : '—'}
          loading={isLoading}
          hint={kpi ? `胜 ${kpi.wins} · 败 ${kpi.losses}` : ''}
        />
        <StatTile
          label="试盘交易数"
          value={kpi ? `${kpi.total_closed + kpi.total_open}` : '—'}
          loading={isLoading}
          hint={kpi ? `已结算 ${kpi.total_closed} · 进行中 ${kpi.total_open}` : ''}
        />
        <StatTile
          label="平均持仓"
          value={kpi ? `${kpi.avg_holding_hours.toFixed(1)} h` : '—'}
          loading={isLoading}
          hint="已结算的平均时长"
        />
      </section>

      {/* 进行中的虚拟仓位 */}
      <Card>
        <div className="px-4 py-3 border-b border-terminal-border flex items-center gap-2">
          <FlaskConical size={14} className="text-primary" />
          <span className="text-sm text-text-primary">进行中（{openRows.length}）</span>
          <span className="ml-auto text-[11px] text-text-muted">paper_monitor 每 30s 跟踪 OKX 实时价</span>
        </div>
        {openRows.length === 0 ? (
          <EmptyState
            title="没有进行中的虚拟仓位"
            hint="等待 scorer 触发下一个信号 — 当前为 SHADOW 时会自动开虚拟仓"
            icon={<FlaskConical size={20} strokeWidth={1.5} />}
          />
        ) : (
          <div className="overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th>币种</th>
                  <th>方向</th>
                  <th className="text-right">开仓价</th>
                  <th className="text-right">现价</th>
                  <th className="text-right">SL</th>
                  <th className="text-right">TP</th>
                  <th className="text-right">浮动 PnL%</th>
                  <th className="text-right">size USDT</th>
                </tr>
              </thead>
              <tbody>
                {openRows.map((r) => {
                  const entry = Number(r.entry_price ?? 0);
                  const cur   = Number(r.current_price ?? entry);
                  const side  = (r.side || 'LONG').toUpperCase();
                  const pnlPct = entry > 0 ? ((cur - entry) / entry * 100) * (side === 'LONG' ? 1 : -1) : 0;
                  return (
                    <tr key={r.id}>
                      <td className="text-text-primary font-medium">{r.symbol}</td>
                      <td><Pill tone={side === 'SHORT' ? 'bear' : 'bull'}>{side}</Pill></td>
                      <td className="text-right"><NumberCell value={entry} decimals={entry < 1 ? 6 : 4} /></td>
                      <td className="text-right"><NumberCell value={cur} decimals={cur < 1 ? 6 : 4} /></td>
                      <td className="text-right"><NumberCell value={r.stop_loss} decimals={6} className="text-bear" /></td>
                      <td className="text-right"><NumberCell value={r.take_profit} decimals={6} className="text-bull" /></td>
                      <td className="text-right"><NumberCell value={pnlPct} decimals={2} suffix="%" signColor /></td>
                      <td className="text-right"><NumberCell value={r.position_size_usdt} decimals={2} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* 已结算的虚拟交易 */}
      <Card>
        <div className="px-4 py-3 border-b border-terminal-border flex items-center gap-2">
          <Activity size={14} className="text-text-muted" />
          <span className="text-sm text-text-primary">已结算（{closedRows.length}）</span>
        </div>
        {closedRows.length === 0 ? (
          <EmptyState
            title="还没有已结算的虚拟交易"
            hint="第一笔虚拟仓位触 SL/TP 或超时（24h）后会出现在这里"
          />
        ) : (
          <div className="overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th>币种</th>
                  <th>方向</th>
                  <th className="text-right">开仓 → 平仓</th>
                  <th>退出原因</th>
                  <th className="text-right">PnL USDT</th>
                  <th className="text-right">收益率</th>
                  <th className="text-right">持仓 h</th>
                  <th>开仓时间</th>
                </tr>
              </thead>
              <tbody>
                {closedRows.slice(0, 100).map((r) => {
                  const side = (r.side || 'LONG').toUpperCase();
                  const pnl = Number(r.pnl ?? 0);
                  return (
                    <tr key={r.id}>
                      <td className="text-text-primary font-medium">{r.symbol}</td>
                      <td><Pill tone={side === 'SHORT' ? 'bear' : 'bull'}>{side}</Pill></td>
                      <td className="text-right num">
                        {Number(r.entry_price ?? 0).toPrecision(5)} → {Number(r.exit_price ?? 0).toPrecision(5)}
                      </td>
                      <td>
                        <Pill tone={r.exit_reason === 'TP_HIT' ? 'bull' : r.exit_reason === 'SL_HIT' ? 'bear' : 'neutral'}>
                          {r.exit_reason || '?'}
                        </Pill>
                      </td>
                      <td className="text-right">
                        <NumberCell value={pnl} decimals={2} signColor />
                      </td>
                      <td className="text-right"><NumberCell value={r.pnl_percent} decimals={2} suffix="%" signColor /></td>
                      <td className="text-right num">{Number(r.holding_hours ?? 0).toFixed(1)}</td>
                      <td className="text-[10px] text-text-muted num">
                        {r.entry_time ? new Date(r.entry_time).toLocaleString('zh-CN', { hour12: false }) : '—'}
                      </td>
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
};

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] font-mono text-text-muted uppercase mb-0.5">{label}</div>
      <div className="text-sm font-bold">{value}</div>
    </div>
  );
}
