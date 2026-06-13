import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useV5Signals } from '../../hooks/api/useV5Signals';
import { useUIStore } from '../../services/store';
import type { Side } from '../../types';
import { Card } from '../primitives/Card';
import { Badge } from '../primitives/Badge';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Select } from '../primitives/Select';
import { IndicatorGauges } from '../shared/IndicatorGauges';
import { signalScore, dotStateFor, formatSideBadgeTone, blockReasonZh } from './_signal_helpers';
import { ChevronDown, ChevronUp, LineChart, Hand } from 'lucide-react';
import { Term } from '../shared/Term';

export function V5SignalsPage() {
  const [side, setSide] = useState<Side | 'ALL'>('ALL');
  const [executedOnly, setExecutedOnly] = useState(false);
  const filter = {
    side: side === 'ALL' ? null : side,
    showExecutedOnly: executedOnly,
  };
  const q = useV5Signals(50, filter);
  const navigate = useNavigate();
  const expanded = useUIStore(s => s.expandedSignalIds);
  const toggle = useUIStore(s => s.toggleSignalExpanded);

  const signals = q.data?.data ?? [];
  const passedAnd = signals.filter(s => s.should_trade === 1).length;
  const executed = signals.filter(s => s.executed === 1).length;

  return (
    <div className="space-y-4">
      <Card
        title={
          <div className="flex items-center gap-3">
            <span>实时信号</span>
            <span className="text-xs text-white/50 font-mono">
              过去窗口: {signals.length} 个扫到 → {passedAnd} 通过 AND → {executed} 入场
            </span>
          </div>
        }
        actions={
          <>
            <Select
              value={side}
              options={[
                { value: 'ALL', label: '方向: 全部' },
                { value: 'SHORT', label: '仅做空' },
                { value: 'LONG', label: '仅做多' },
              ]}
              onChange={(v) => setSide(v as any)}
            />
            <label className="flex items-center gap-1 text-xs text-white/60">
              <input type="checkbox" checked={executedOnly} onChange={(e) => setExecutedOnly(e.target.checked)} />
              仅已入场
            </label>
            <button type="button" onClick={() => q.refetch()} className="rounded-sm border border-white/15 px-2 py-1 text-xs text-white/70 hover:bg-white/5">⟳</button>
          </>
        }
      >
        {q.isLoading && <LoadingSkeleton rows={4} />}
        {q.isError && <div className="text-accent-short text-sm">数据获取失败:{(q.error as any)?.detail || (q.error as any)?.message}</div>}
        {!q.isLoading && !q.isError && signals.length === 0 && (
          <div className="py-12 text-center text-white/40">等待行情出现 RSI/MACD 合谋信号...</div>
        )}
        <div className="space-y-2">
          {signals.map(s => {
            const isOpen = expanded.has(s.id);
            return (
              <div key={s.id} className="rounded-md border border-white/10 bg-bg-base">
                <button
                  type="button"
                  onClick={() => toggle(s.id)}
                  className="flex w-full items-center justify-between px-4 py-3 hover:bg-white/5"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-base font-medium text-white">{s.symbol}</span>
                    <Badge variant={formatSideBadgeTone(s.side)}>{s.side ?? '—'}</Badge>
                    <span className={`font-mono text-sm ${s.delta_15m_pct >= 0 ? 'text-accent-long' : 'text-accent-short'}`}>
                      <Term k="ΔP15m">ΔP15m</Term>: {s.delta_15m_pct >= 0 ? '+' : ''}{(s.delta_15m_pct * 100).toFixed(2)}%
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs font-mono text-white/60">
                    <span><Term k="score">score</Term> {signalScore(s)}</span>
                    <span className="text-base">{dotStateFor(s)}</span>
                    <span>{new Date(s.created_at).toLocaleTimeString('zh-CN', { hour12: false })}</span>
                    {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </div>
                </button>
                {isOpen && (
                  <div className="border-t border-white/10 px-4 py-4 space-y-3">
                    <IndicatorGauges
                      rsi_15m={s.rsi_15m} rsi_4h={s.rsi_4h}
                      macd_hist_15m={s.macd_hist_15m} macd_hist_prev_15m={s.macd_hist_prev_15m}
                      atr_15m={s.atr_15m}
                    />
                    {s.block_reason && (
                      <div className="text-sm text-accent-warn">拦截:{blockReasonZh(s.block_reason)}</div>
                    )}
                    {s.ai_reasoning && (
                      <div className="text-sm text-white/70">AI: {s.ai_reasoning}</div>
                    )}
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => navigate(`/v5/chart/${s.symbol}`)}
                        className="flex items-center gap-1 rounded-sm border border-white/15 px-2 py-1 text-xs text-white/70 hover:bg-white/5"
                      >
                        <LineChart size={12} /> 查看图表
                      </button>
                      <button
                        type="button"
                        onClick={() => navigate(`/v5/manual?symbol=${encodeURIComponent(s.symbol)}&side=${s.side ?? ''}`)}
                        className="flex items-center gap-1 rounded-sm border border-accent-info/40 px-2 py-1 text-xs text-accent-info hover:bg-accent-info/10"
                      >
                        <Hand size={12} /> 此参数模拟开单
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
