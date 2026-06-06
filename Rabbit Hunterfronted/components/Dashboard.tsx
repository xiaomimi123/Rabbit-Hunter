/**
 * Dashboard v45 — 重写
 *
 * 之前的 Dashboard：414 行，调 useV43Store 的 noop shim，
 * 所有 server data setter 都是 _noop，相当于一个永远空的页面。
 * 还含一个 Math.random() 假热力图——每次渲染就跳一次。
 *
 * 重写后只展示真实数据，无 mock：
 *   - 4 个 KPI 瓦：模式 / 活跃持仓 / 浮动盈亏 / 今日信号
 *   - 双栏：最新信号 / 活跃持仓
 */

import React, { useMemo } from 'react';
import { CircleDot, Activity, Layers } from 'lucide-react';
import { useUIStore } from '../services/store';
import { useKillQueue } from '../hooks/useKillQueue';
import { usePositions } from '../hooks/usePositions';
import { useSystemStatus } from '../hooks/useSystemStatus';
import { SystemState } from '../types';
import { Card, EmptyState, NumberCell, Pill, SectionHeader, StatTile } from './ui/Primitives';

const Dashboard: React.FC = () => {
  const systemState = useUIStore((s) => s.systemState);
  const setActiveView = useUIStore((s) => s.setActiveView);

  const { data: signals = [], isLoading: signalsLoading } = useKillQueue(50, 0);
  const { data: positions = [], isLoading: positionsLoading } = usePositions();
  const { data: sysStatus } = useSystemStatus();

  // ── 聚合指标 ──────────────────────────────────────────────────
  const totalPnl = useMemo(
    () => positions.reduce((acc, p) => acc + (p.pnl ?? 0), 0),
    [positions],
  );

  const todayCount = signals.length;
  const liveOrShadow = systemState === SystemState.LIVE ? '实盘' : '影子';
  const liveTone: 'up' | 'down' | 'flat' =
    systemState === SystemState.LIVE ? 'down' : 'flat';

  return (
    <div className="space-y-8">
      {/* Hero — 概览 */}
      <header>
        <div className="label-sm mb-1">概览</div>
        <h1 className="text-[22px] font-medium text-text-primary tracking-tight">
          Rabbit Hunter
          <span className="ml-3 text-text-muted text-base font-mono">/ 控制台</span>
        </h1>
      </header>

      {/* KPI tiles */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile
          label="运行模式"
          value={liveOrShadow}
          trend={liveTone}
          hint={sysStatus?.testnet ? 'Binance Testnet' : 'Binance 实盘'}
        />
        <StatTile
          label="活跃持仓"
          value={positions.length.toString()}
          loading={positionsLoading}
          hint={
            positions.length
              ? `多 ${positions.filter((p) => p.side === 'LONG').length} · 空 ${
                  positions.filter((p) => p.side === 'SHORT').length
                }`
              : '无持仓'
          }
        />
        <StatTile
          label="浮动盈亏"
          value={
            <NumberCell
              value={totalPnl}
              decimals={2}
              suffix=" USDT"
              signColor
              className="text-2xl"
            />
          }
          loading={positionsLoading}
        />
        <StatTile
          label="今日信号"
          value={todayCount.toString()}
          loading={signalsLoading}
          hint={`最近一次更新: ${new Date().toLocaleTimeString('zh-CN', { hour12: false })}`}
        />
      </section>

      {/* 双栏 */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {/* 信号 */}
        <Card className="lg:col-span-2">
          <div className="p-5 pb-3">
            <SectionHeader
              title="最新信号"
              subtitle={`Kill Board · 显示前 ${Math.min(signals.length, 12)} 条`}
              right={
                <button
                  onClick={() => setActiveView('KILL_BOARD')}
                  className="text-[11px] text-text-muted hover:text-primary transition-colors tracking-micro uppercase"
                >
                  查看全部 →
                </button>
              }
            />
          </div>
          <SignalsTable rows={signals.slice(0, 12)} loading={signalsLoading} />
        </Card>

        {/* 持仓 */}
        <Card>
          <div className="p-5 pb-3">
            <SectionHeader
              title="活跃持仓"
              subtitle={positionsLoading ? '加载中…' : `${positions.length} 条`}
              right={
                <button
                  onClick={() => setActiveView('POSITIONS')}
                  className="text-[11px] text-text-muted hover:text-primary transition-colors tracking-micro uppercase"
                >
                  管理 →
                </button>
              }
            />
          </div>
          <PositionsList positions={positions} loading={positionsLoading} />
        </Card>
      </section>
    </div>
  );
};

// ─── signals table ────────────────────────────────────────────────────────────

const SignalsTable: React.FC<{ rows: any[]; loading: boolean }> = ({ rows, loading }) => {
  if (loading) {
    return <EmptyState title="加载中…" icon={<Activity size={20} strokeWidth={1.5} />} />;
  }
  if (!rows.length) {
    return (
      <EmptyState
        title="暂无信号"
        hint="采集器还在等待第一条满足阈值的市场信号"
        icon={<CircleDot size={20} strokeWidth={1.5} />}
      />
    );
  }
  return (
    <div className="overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>币种</th>
            <th>方向</th>
            <th className="text-right">评分</th>
            <th className="text-right">价格</th>
            <th>阶段</th>
            <th>策略</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const side = (r.side || '').toUpperCase();
            const score = Number(r.final_score ?? 0);
            return (
              <tr key={r.symbol + (r.created_at || '')}>
                <td className="text-text-primary font-medium">{r.symbol}</td>
                <td>
                  <Pill tone={side === 'SHORT' ? 'bear' : 'bull'}>
                    {side || 'LONG'}
                  </Pill>
                </td>
                <td className="text-right">
                  <NumberCell value={score > 1 ? score : score * 100} decimals={1} />
                </td>
                <td className="text-right">
                  <NumberCell value={r.price} decimals={r.price > 10 ? 2 : 6} />
                </td>
                <td className="text-[11px] text-text-secondary tracking-micro uppercase">
                  {(r.phase || '—').replace(/_/g, ' ')}
                </td>
                <td className="text-[11px] text-text-secondary">
                  {r.strategy_id || '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// ─── positions list (compact) ─────────────────────────────────────────────────

const PositionsList: React.FC<{ positions: any[]; loading: boolean }> = ({ positions, loading }) => {
  if (loading) {
    return <EmptyState title="加载中…" icon={<Activity size={20} strokeWidth={1.5} />} />;
  }
  if (!positions.length) {
    return (
      <EmptyState
        title="无活跃持仓"
        hint="尚未有信号触发开仓"
        icon={<Layers size={20} strokeWidth={1.5} />}
      />
    );
  }
  return (
    <div className="px-5 pb-5 space-y-2">
      {positions.slice(0, 8).map((p) => {
        const pnl = Number(p.pnl ?? 0);
        const pnlPct = Number(p.pnlPercent ?? p.pnl_percent ?? 0);
        const side = (p.side || 'LONG').toUpperCase();
        return (
          <div
            key={p.id ?? `${p.symbol}-${side}`}
            className="flex items-center justify-between py-2 px-3 rounded border border-terminal-border bg-terminal-bg"
          >
            <div className="flex items-center gap-3 min-w-0">
              <Pill tone={side === 'SHORT' ? 'bear' : 'bull'}>{side}</Pill>
              <span className="text-[13px] text-text-primary truncate">{p.symbol}</span>
            </div>
            <div className="text-right shrink-0">
              <NumberCell value={pnl} decimals={2} signColor className="text-[13px]" />
              <div className="text-[10px] text-text-muted num">
                <NumberCell value={pnlPct} decimals={2} suffix="%" signColor />
              </div>
            </div>
          </div>
        );
      })}
      {positions.length > 8 && (
        <div className="text-[11px] text-text-muted text-center pt-1">
          还有 {positions.length - 8} 条 — 切到持仓页查看
        </div>
      )}
    </div>
  );
};

export default Dashboard;
