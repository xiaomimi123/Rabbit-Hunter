/**
 * Kill Board — market opportunity list.
 * Data fetched via React Query (10 s interval, no setInterval needed).
 */

import React, { useState, useMemo } from 'react';
import {
  ChevronDown, ChevronUp, AlertCircle, Eye, CheckCircle,
  TrendingUp, TrendingDown, Search, Crosshair, Skull, Info,
} from 'lucide-react';
import { KillBoardItem, RiskLabel } from '../types';
import { useKillQueue } from '../hooks/useKillQueue';
import { DimensionScores } from '../ui/ScoreBar';
import { LoadingSkeleton } from '../ui/LoadingSkeleton';

// ─── pure helpers ────────────────────────────────────────────────────────────

const PHASE_LABEL: Record<string, string> = {
  P1_NO_WHALE:    'P1 无主力',
  P2_ACCUMULATION:'P2 积累',
  P3A_PUMP_START: 'P3A 启动',
  P3B_PUMP_LATE:  'P3B 后期',
  P4_DISTRIBUTION:'P4 派发',
};
const fmtPhase = (p: string) => PHASE_LABEL[p] ?? p;

function calcRiskLabel(item: any): RiskLabel {
  if (item.block_reason || item.blockReason) return 'BLOCK';
  if (item.should_trade === false) return 'BLOCK';
  const s = (item.final_score ?? 0) * 100;
  if (s >= 70) return 'TRADE';
  if (s >= 40) return 'WATCH';
  return 'BLOCK';
}

function extractEdgeReason(item: any): string {
  const reason = item.block_reason || item.blockReason;
  if (reason) return reason;
  if (item.reason) return item.reason;
  const phase = item.phase ?? '';
  const score = (item.final_score ?? 0) * 100;
  if (phase === 'P2_ACCUMULATION') return score >= 40 ? 'P2 阶段，等待启动' : 'P2 阶段，空间不足';
  if (phase === 'P3A_PUMP_START') return 'P3A 启动，机会良好';
  if (phase === 'P3B_PUMP_LATE') return 'P3B 后期，风险较高';
  if (phase === 'P4_DISTRIBUTION') return 'P4 派发，避免参与';
  if (phase === 'P1_NO_WHALE') return 'P1 阶段，无主力信号';
  return '等待更多信号';
}

function extractATRInfo(item: any) {
  const f = item.features ?? {};
  const dp = item.decision_policy ?? {};
  const entry = item.price || f.current_price || 0;
  const atr1h = f.atr_1h || f.atr || 0;
  const atrK = dp.atr_k || f.atr_k || 2.0;
  if (entry <= 0 || atr1h <= 0) return undefined;
  return {
    entry,
    atr1h,
    trailingSL: entry - atr1h * atrK,
    expectedRR: Math.max(0, (f.range_left ?? 0) / (atr1h * atrK)),
    atrK,
  };
}

function transformRaw(raw: any[]): KillBoardItem[] {
  return raw.map((item: any) => {
    const price =
      item.price || item.features?.current_price || item.features?.price || 0;
    return {
      symbol: item.symbol,
      score: (item.final_score ?? 0) * 100,
      riskLabel: calcRiskLabel(item),
      phase: item.phase ?? 'UNKNOWN',
      edgeReason: extractEdgeReason(item),
      aiConfidence: item.confidence ?? item.final_score ?? 0,
      strategyId: item.strategy_id || item.strategyId || item.features?.strategy_id,
      strategySide: item.side || item.features?.side || 'LONG',
      price: typeof price === 'number' ? price : parseFloat(String(price)) || 0,
      change24h: item.change24h ?? 0,
      changePercent: item.changePercent ?? item.change24h ?? 0,
      dimensionScores: {
        structure:    (item.structure_score ?? 0) * 100,
        volatility:   (item.volatility_score ?? 0) * 100,
        sentiment:    (item.sentiment_score ?? 0) * 100,
        manipulation: (item.manipulation_score ?? 0) * 100,
      },
      atrInfo: extractATRInfo(item),
      phaseAge: item.phaseAge,
      blockReason: item.block_reason || item.blockReason,
      shouldTrade: item.should_trade !== false,
      positionSizeMultiplier: item.position_size_multiplier ?? 0,
      aiReasoning: item.ai_reasoning ?? item.aiReasoning ?? null,
      aiSlMultiplier: item.ai_sl_multiplier ?? null,
      aiTpMultiplier: item.ai_tp_multiplier ?? null,
      timestamp: item.timestamp ?? item.created_at ?? new Date().toISOString(),
      lastUpdated: item.lastUpdated ?? item.updated_at ?? item.timestamp ?? new Date().toISOString(),
      id: item.symbol,
    } satisfies KillBoardItem;
  });
}

// risk label → style
const RISK_STYLE = {
  BLOCK: { color: 'text-bear', bg: 'bg-bear-dim', border: 'border-bear/30', icon: AlertCircle },
  WATCH: { color: 'text-warn', bg: 'bg-warn/10',  border: 'border-warn/30', icon: Eye },
  TRADE: { color: 'text-bull', bg: 'bg-bull-dim', border: 'border-bull/30', icon: CheckCircle },
} as const;

const STRATEGY_STYLE: Record<string, { color: string; bg: string; border: string; icon: any; label: string }> = {
  SNIFFER: { color: 'text-info',    bg: 'bg-info/10',    border: 'border-info/30',    icon: Search,   label: 'P2 潜伏' },
  SNIPER:  { color: 'text-bull',    bg: 'bg-bull-dim',   border: 'border-bull/30',    icon: Crosshair, label: 'P3A 狙击' },
  VULTURE: { color: 'text-bear',    bg: 'bg-bear-dim',   border: 'border-bear/30',    icon: Skull,    label: '反杀' },
};

// ─── component ───────────────────────────────────────────────────────────────

export default function KillBoard() {
  const [minScore, setMinScore] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const { data: rawData = [], isLoading, isFetching, refetch } = useKillQueue(50, minScore);

  const items = useMemo(() => transformRaw(rawData as any[]), [rawData]);

  const toggle = (sym: string) =>
    setExpanded((prev) => {
      const s = new Set(prev);
      s.has(sym) ? s.delete(sym) : s.add(sym);
      return s;
    });

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-lg font-bold text-text-primary font-mono">
            Kill Board
            <span className="ml-2 text-sm text-text-muted font-normal">
              {items.length} 个币种
            </span>
            {isFetching && (
              <span className="ml-2 inline-block w-3 h-3 border border-primary/40 border-t-primary rounded-full animate-spin align-middle" />
            )}
          </h1>
          <div className="flex gap-3 mt-1 text-[10px] text-text-muted">
            <span><span className="text-bull">■</span> TRADE</span>
            <span><span className="text-warn">■</span> WATCH</span>
            <span><span className="text-bear">■</span> BLOCK</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-text-secondary">
            <span>Min Score</span>
            <input
              type="number" min="0" max="100" value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              className="w-16 px-2 py-1 bg-terminal-card border border-terminal-border rounded text-text-primary text-xs font-mono"
            />
          </label>
          <button
            onClick={() => refetch()}
            className="px-3 py-1.5 text-xs font-mono bg-primary-dim text-primary border border-primary/30 rounded hover:bg-primary/20 transition-colors"
          >
            刷新
          </button>
        </div>
      </div>

      {/* List */}
      {isLoading && items.length === 0 ? (
        <LoadingSkeleton rows={8} />
      ) : items.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-text-muted font-mono text-sm">
          暂无数据
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
          {items.map((item) => {
            const rs = RISK_STYLE[item.riskLabel] ?? RISK_STYLE['BLOCK'];
            const RiskIcon = rs.icon;
            const ss = item.strategyId ? STRATEGY_STYLE[item.strategyId] : null;
            const isExp = expanded.has(item.symbol);

            return (
              <div
                key={item.symbol}
                className={`rounded-lg border ${rs.border} bg-terminal-card overflow-hidden`}
              >
                {/* Main row */}
                <div
                  className="flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-terminal-hover transition-colors"
                  onClick={() => toggle(item.symbol)}
                >
                  {/* Symbol + Phase */}
                  <div className="w-36 shrink-0">
                    <div className="text-sm font-bold text-text-primary font-mono">{item.symbol}</div>
                    <div className="text-[10px] text-text-muted truncate">{fmtPhase(item.phase)}</div>
                  </div>

                  {/* Score */}
                  <div className="w-20 shrink-0 text-right">
                    <div className="text-xs text-text-muted">Score</div>
                    <div className="text-base font-bold text-text-primary font-mono">
                      {item.score.toFixed(1)}
                    </div>
                  </div>

                  {/* Risk badge */}
                  <div className={`shrink-0 flex items-center gap-1 px-2 py-0.5 rounded ${rs.bg} border ${rs.border}`}>
                    <RiskIcon size={10} className={rs.color} />
                    <span className={`text-[10px] font-mono font-bold ${rs.color}`}>{item.riskLabel}</span>
                  </div>

                  {/* Strategy badge */}
                  {ss ? (
                    <div className={`shrink-0 flex items-center gap-1 px-2 py-0.5 rounded ${ss.bg} border ${ss.border}`}>
                      <ss.icon size={10} className={ss.color} />
                      <span className={`text-[10px] font-mono font-bold ${ss.color}`}>{item.strategyId}</span>
                    </div>
                  ) : (
                    <div className="w-16 shrink-0" />
                  )}

                  {/* Edge reason */}
                  <div className="flex-1 min-w-0 text-xs text-text-secondary font-mono truncate">
                    {item.edgeReason}
                  </div>

                  {/* Price + change */}
                  <div className="w-28 shrink-0 text-right">
                    <div className="text-xs font-mono text-text-primary">
                      {item.price > 0 ? `$${item.price < 1 ? item.price.toFixed(6) : item.price.toFixed(4)}` : '—'}
                    </div>
                    {item.changePercent !== 0 && (
                      <div className={`flex items-center justify-end gap-0.5 text-[10px] font-mono ${item.changePercent >= 0 ? 'text-bull' : 'text-bear'}`}>
                        {item.changePercent >= 0 ? <TrendingUp size={9} /> : <TrendingDown size={9} />}
                        {Math.abs(item.changePercent).toFixed(2)}%
                      </div>
                    )}
                  </div>

                  {/* AI confidence */}
                  <div className="w-16 shrink-0 text-right font-mono text-xs text-text-secondary">
                    {(item.aiConfidence * 100).toFixed(0)}%
                  </div>

                  {/* Expand toggle */}
                  <div className="text-text-muted">
                    {isExp ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </div>
                </div>

                {/* Expanded details */}
                {isExp && (
                  <div className="border-t border-terminal-border px-4 py-3 space-y-3 animate-slide-down bg-terminal-bg/50">
                    {/* 4D Scores */}
                    <div>
                      <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2 font-mono">四维评分</div>
                      <DimensionScores scores={item.dimensionScores} />
                    </div>

                    {/* ATR info */}
                    {item.atrInfo && (
                      <div>
                        <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2 font-mono">ATR / 止损</div>
                        <div className="grid grid-cols-5 gap-3 text-xs font-mono">
                          {[
                            { label: 'Entry',       val: `$${item.atrInfo.entry.toFixed(4)}`,       cls: 'text-text-primary' },
                            { label: 'ATR 1H',      val: `$${item.atrInfo.atr1h.toFixed(6)}`,       cls: 'text-text-primary' },
                            { label: 'Trailing SL', val: `$${item.atrInfo.trailingSL.toFixed(4)}`,  cls: 'text-bear' },
                            { label: 'Exp. RR',     val: `${item.atrInfo.expectedRR.toFixed(2)}R`,  cls: 'text-bull' },
                            { label: 'ATR K',       val: `${item.atrInfo.atrK.toFixed(1)}x`,        cls: 'text-text-secondary' },
                          ].map(({ label, val, cls }) => (
                            <div key={label}>
                              <div className="text-text-muted text-[10px]">{label}</div>
                              <div className={`font-bold ${cls}`}>{val}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* AI decision block */}
                    {(item.aiConfidence > 0 || item.aiReasoning) && (
                      <div>
                        <div className="text-[10px] text-text-muted uppercase tracking-widest mb-2 font-mono flex items-center gap-1.5">
                          <span className="w-3.5 h-3.5 rounded-full bg-primary/20 text-primary flex items-center justify-center text-[8px] font-bold">AI</span>
                          OpenAI 决策
                        </div>
                        <div className="flex flex-wrap gap-3 text-xs font-mono">
                          {item.aiConfidence > 0 && (
                            <div>
                              <div className="text-text-muted text-[10px]">置信度</div>
                              <div className={`font-bold ${item.aiConfidence >= 0.7 ? 'text-bull' : item.aiConfidence >= 0.5 ? 'text-warn' : 'text-bear'}`}>
                                {(item.aiConfidence * 100).toFixed(0)}%
                              </div>
                            </div>
                          )}
                          {item.aiSlMultiplier && (
                            <div>
                              <div className="text-text-muted text-[10px]">SL</div>
                              <div className="text-bear font-bold">{item.aiSlMultiplier.toFixed(1)}× ATR</div>
                            </div>
                          )}
                          {item.aiTpMultiplier && (
                            <div>
                              <div className="text-text-muted text-[10px]">TP</div>
                              <div className="text-bull font-bold">{item.aiTpMultiplier.toFixed(1)}× ATR</div>
                            </div>
                          )}
                          {item.aiSlMultiplier && item.aiTpMultiplier && (
                            <div>
                              <div className="text-text-muted text-[10px]">R:R</div>
                              <div className="text-text-primary font-bold">
                                1:{(item.aiTpMultiplier / item.aiSlMultiplier).toFixed(1)}
                              </div>
                            </div>
                          )}
                        </div>
                        {item.aiReasoning && (
                          <div className="mt-2 text-[11px] text-text-secondary font-mono bg-primary/5 border border-primary/15 rounded px-3 py-2 leading-relaxed">
                            {item.aiReasoning}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Footer meta */}
                    <div className="flex items-center gap-3 text-[10px] text-text-muted flex-wrap">
                      {item.blockReason && (
                        <span className="flex items-center gap-1 text-bear">
                          <AlertCircle size={10} />拦截: {item.blockReason}
                        </span>
                      )}
                      {item.positionSizeMultiplier !== undefined && item.positionSizeMultiplier > 0 && (
                        <span className="flex items-center gap-1 text-warn">
                          <Info size={10} />仓位倍数: {item.positionSizeMultiplier.toFixed(2)}x
                        </span>
                      )}
                      <span className="ml-auto">
                        更新: {new Date(item.lastUpdated).toLocaleTimeString()}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
