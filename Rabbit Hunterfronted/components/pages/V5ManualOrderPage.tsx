import React, { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useV5ManualOrder } from '../../hooks/api/useV5ManualOrder';
import { useSystemMode } from '../../hooks/useSystemMode';
import { Card } from '../primitives/Card';
import { Select } from '../primitives/Select';
import { NumberInput } from '../primitives/NumberInput';
import { Badge } from '../primitives/Badge';
import { IndicatorGauges } from '../shared/IndicatorGauges';
import type { Side, ManualOrderPreviewResponse } from '../../types';
import { Term } from '../shared/Term';

type Step = 1 | 2 | 3;

export function V5ManualOrderPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { mode } = useSystemMode();
  const { preview, execute } = useV5ManualOrder();

  const [step, setStep] = useState<Step>(1);
  const [symbol, setSymbol] = useState(params.get('symbol') ?? 'BTC/USDT');
  const [side, setSide] = useState<Side>((params.get('side') as Side) || 'SHORT');
  const [size, setSize] = useState(15);
  const [previewData, setPreviewData] = useState<ManualOrderPreviewResponse | null>(null);
  const [slMult, setSlMult] = useState(1);
  const [tpMult, setTpMult] = useState(1);
  const [sizeMult, setSizeMult] = useState(1);

  if (mode === 'LIVE') {
    return (
      <Card title="手动开单">
        <div className="text-accent-warn">手动开单仅在 SHADOW 模式可用。</div>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card title={`手动开单 — Step ${step}/3`}>
        {step === 1 && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <div>
                <div className="text-xs text-white/50 mb-1">Symbol</div>
                <input
                  className="w-full rounded-sm border border-white/10 bg-bg-base px-2 py-1 font-mono text-white"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                />
              </div>
              <div>
                <div className="text-xs text-white/50 mb-1">Side</div>
                <Select
                  value={side}
                  options={[{ value: 'SHORT', label: 'SHORT' }, { value: 'LONG', label: 'LONG' }]}
                  onChange={(v) => setSide(v as Side)}
                />
              </div>
              <div>
                <div className="text-xs text-white/50 mb-1">Size (USDT)</div>
                <NumberInput value={size} min={5} max={500} step={1} onChange={setSize} />
              </div>
            </div>
            <button
              type="button"
              disabled={preview.isPending || !symbol}
              onClick={async () => {
                const r = await preview.mutateAsync({ symbol, side, size_usdt: size });
                setPreviewData(r);
                setSlMult(r.ai_result.sl_multiplier);
                setTpMult(r.ai_result.tp_multiplier);
                setSizeMult(r.ai_result.size_multiplier);
                setStep(2);
              }}
              className="rounded-sm border border-accent-info/40 bg-accent-info/10 px-3 py-1 text-sm text-accent-info disabled:opacity-50"
            >
              {preview.isPending ? '评估中…' : '模拟评估 →'}
            </button>
            {preview.isError && (
              <div className="text-sm text-accent-short">评估失败:{(preview.error as any)?.detail ?? (preview.error as any)?.message}</div>
            )}
          </div>
        )}

        {step === 2 && previewData && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <Card title="当前指标">
                <IndicatorGauges
                  rsi_15m={previewData.indicators.rsi_15m}
                  rsi_4h={previewData.indicators.rsi_4h ?? null}
                  macd_hist_15m={previewData.indicators.macd_hist_15m}
                  macd_hist_prev_15m={previewData.indicators.macd_hist_prev_15m}
                  atr_15m={previewData.indicators.atr_15m}
                />
              </Card>
              <Card title="规则决策">
                <div className="text-sm space-y-1">
                  <div>
                    {previewData.decision.should_trade
                      ? <Badge variant="long">✓ {previewData.decision.side}</Badge>
                      : <Badge variant="short">✗ 不建议</Badge>}
                  </div>
                  <div className="text-xs text-white/60">{previewData.decision.reasoning}</div>
                  <div className="font-mono text-xs text-white/70">
                    SL ${previewData.risk_plan.sl_price.toFixed(4)} ·
                    TP ${previewData.risk_plan.tp_price.toFixed(4)}
                  </div>
                </div>
              </Card>
              <Card title="AI 二次审查">
                <div className="text-sm space-y-1">
                  <div>
                    {previewData.ai_result.execute
                      ? <Badge variant="long">✓ execute=true</Badge>
                      : <Badge variant="short">✗ 拒</Badge>}
                  </div>
                  <div className="text-xs text-white/60">{previewData.ai_result.reasoning}</div>
                  <div className="grid grid-cols-3 gap-2 text-xs font-mono">
                    <label><Term k="SL Multiplier">SL ×</Term> <NumberInput value={slMult} min={0.5} max={3} step={0.1} onChange={setSlMult} /></label>
                    <label><Term k="TP Multiplier">TP ×</Term> <NumberInput value={tpMult} min={0.5} max={5} step={0.1} onChange={setTpMult} /></label>
                    <label><Term k="Size Multiplier">Size ×</Term> <NumberInput value={sizeMult} min={0.1} max={2} step={0.1} onChange={setSizeMult} /></label>
                  </div>
                </div>
              </Card>
            </div>

            <Card title={<span><Term k="RAG">RAG</Term> 历史相似 top-{previewData.rag_cases.length}</span>}>
              {previewData.rag_cases.length === 0 ? (
                <div className="text-xs text-white/40">RAG 冷启动期,无相似 case</div>
              ) : (
                <table className="w-full text-xs">
                  <thead><tr className="text-left text-white/50">
                    <th>RSI</th><th>MACD hist</th><th>结果</th><th className="text-right">PnL</th><th>原因</th><th className="text-right">距离</th>
                  </tr></thead>
                  <tbody>
                    {previewData.rag_cases.map((c, i) => (
                      <tr key={i} className="border-t border-white/5 font-mono">
                        <td>{c.entry_rsi_15m.toFixed(1)}</td>
                        <td>{c.entry_macd_hist_15m.toFixed(4)}</td>
                        <td className={c.outcome === 'WIN' ? 'text-accent-long' : c.outcome === 'LOSS' ? 'text-accent-short' : 'text-white/60'}>{c.outcome}</td>
                        <td className="text-right">{(c.pnl_pct * 100).toFixed(2)}%</td>
                        <td>{c.exit_reason ?? '—'}</td>
                        <td className="text-right">{c.distance.toFixed(3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {previewData.rag_summary && <div className="mt-2 text-xs text-white/60">{previewData.rag_summary}</div>}
            </Card>

            <div className="flex justify-between">
              <button type="button" onClick={() => setStep(1)} className="rounded-sm border border-white/15 px-3 py-1 text-xs">↩ 回到 Step 1</button>
              <button
                type="button"
                disabled={execute.isPending}
                onClick={async () => {
                  const out = await execute.mutateAsync({
                    symbol, side, size_usdt: size,
                    sl_multiplier: slMult, tp_multiplier: tpMult, size_multiplier: sizeMult,
                  });
                  setStep(3);
                  setTimeout(() => navigate(`/v5/active?just=${out.position_id}`), 800);
                }}
                className="rounded-sm border border-accent-long/40 bg-accent-long/10 px-3 py-1 text-xs text-accent-long disabled:opacity-50"
              >
                {execute.isPending ? '开仓中…' : '确认模拟开仓 →'}
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="py-12 text-center">
            <div className="text-accent-long text-xl">✓ 模拟开仓成功</div>
            <div className="text-xs text-white/50 mt-2">即将跳转到活仓监控…</div>
          </div>
        )}
      </Card>
    </div>
  );
}
