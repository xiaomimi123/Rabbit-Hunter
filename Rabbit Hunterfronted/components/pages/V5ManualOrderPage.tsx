import { ReactNode, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { CheckCircle, AlertTriangle, ChevronRight, ChevronLeft, TrendingUp, TrendingDown } from 'lucide-react';
import { useV5ManualOrder } from '../../hooks/api/useV5ManualOrder';
import { useSystemMode } from '../../hooks/useSystemMode';
import { NumberInput } from '../primitives/NumberInput';
import { IndicatorGauges } from '../shared/IndicatorGauges';
import { Term } from '../shared/Term';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { Alert } from '../primitives-v3/Alert';
import { FormField, TextInput, PrimaryButton, SecondaryButton } from '../primitives-v3/FormField';
import { cn } from '../primitives-v3/cn';
import type { Side, ManualOrderPreviewResponse } from '../../types';

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
      <div className="mx-auto w-full max-w-3xl px-6 py-6">
        <Alert tone="warning">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            <span>手动开单仅在 SHADOW 模式可用。</span>
          </div>
        </Alert>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-6 space-y-6">
      <SectionTitle
        title="手动开单"
        subtitle={`paper-trade · Step ${step}/3`}
        action={<StatusPill tone="amber">SHADOW</StatusPill>}
      />

      <StepIndicator current={step} />

      {step === 1 && (
        <Step1
          symbol={symbol} onSymbolChange={setSymbol}
          side={side} onSideChange={setSide}
          size={size} onSizeChange={setSize}
          isPending={preview.isPending}
          error={(preview.error as any)?.detail ?? (preview.error as any)?.message ?? null}
          onSubmit={async () => {
            const r = await preview.mutateAsync({ symbol, side, size_usdt: size });
            setPreviewData(r);
            setSlMult(r.ai_result.sl_multiplier);
            setTpMult(r.ai_result.tp_multiplier);
            setSizeMult(r.ai_result.size_multiplier);
            setStep(2);
          }}
        />
      )}

      {step === 2 && previewData && (
        <Step2
          data={previewData}
          slMult={slMult} setSlMult={setSlMult}
          tpMult={tpMult} setTpMult={setTpMult}
          sizeMult={sizeMult} setSizeMult={setSizeMult}
          onBack={() => setStep(1)}
          executePending={execute.isPending}
          onConfirm={async () => {
            const out = await execute.mutateAsync({
              symbol, side, size_usdt: size,
              sl_multiplier: slMult, tp_multiplier: tpMult, size_multiplier: sizeMult,
            });
            setStep(3);
            setTimeout(() => navigate(`/v5/active?just=${out.position_id}`), 800);
          }}
        />
      )}

      {step === 3 && (
        <Card>
          <div className="py-10 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-sage-soft">
              <CheckCircle className="h-7 w-7 text-sage" />
            </div>
            <p className="text-2xl font-semibold text-sage">模拟开仓成功</p>
            <p className="mt-2 text-sm text-ivory-70">即将跳转到活仓监控…</p>
          </div>
        </Card>
      )}
    </div>
  );
}

function StepIndicator({ current }: { current: Step }) {
  const steps: { id: Step; label: string }[] = [
    { id: 1, label: '参数' },
    { id: 2, label: '评估' },
    { id: 3, label: '完成' },
  ];
  return (
    <div className="flex items-center gap-0">
      {steps.map((s, i) => (
        <div key={s.id} className="flex items-center gap-3 flex-1">
          <div className={cn(
            'flex h-10 w-10 items-center justify-center rounded-2xl font-mono text-base font-medium',
            current === s.id && 'bg-brass text-bg-base shadow-lg shadow-brass/30',
            current > s.id && 'bg-sage-soft text-sage border border-sage/40',
            current < s.id && 'border border-hairline bg-bg-base text-ivory-40',
          )}>
            {current > s.id ? '✓' : s.id}
          </div>
          <span className={cn(
            'text-sm',
            current === s.id && 'text-ink',
            current > s.id && 'text-sage',
            current < s.id && 'text-ivory-40',
          )}>
            {s.label}
          </span>
          {i < steps.length - 1 && (
            <div className={cn('flex-1 h-px mx-2', current > s.id ? 'bg-sage-soft' : 'bg-bg-elevated')} />
          )}
        </div>
      ))}
    </div>
  );
}

function Step1({ symbol, onSymbolChange, side, onSideChange, size, onSizeChange, onSubmit, isPending, error }: {
  symbol: string; onSymbolChange: (s: string) => void;
  side: Side; onSideChange: (s: Side) => void;
  size: number; onSizeChange: (n: number) => void;
  onSubmit: () => void;
  isPending: boolean;
  error: string | null;
}) {
  return (
    <Card title="参数">
      <div className="grid gap-5 md:grid-cols-3">
        <FormField label="Symbol">
          <TextInput value={symbol} onChange={e => onSymbolChange(e.target.value)} />
        </FormField>
        <FormField label="方向">
          <div className="flex rounded-2xl border border-hairline p-1">
            {(['LONG', 'SHORT'] as Side[]).map(opt => (
              <button
                key={opt}
                type="button"
                onClick={() => onSideChange(opt)}
                className={cn(
                  'flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl py-2 text-sm font-medium transition',
                  side === opt
                    ? opt === 'LONG'
                      ? 'bg-sage-soft text-sage'
                      : 'bg-oxblood-soft text-oxblood'
                    : 'text-ivory-70 hover:text-ivory',
                )}
              >
                {opt === 'LONG' ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                {opt}
              </button>
            ))}
          </div>
        </FormField>
        <FormField label="Size (USDT)">
          <NumberInput value={size} min={5} max={500} step={1} onChange={onSizeChange} />
        </FormField>
      </div>

      {error && (
        <Alert tone="error" className="mt-4">评估失败:{error}</Alert>
      )}

      <PrimaryButton
        disabled={isPending || !symbol}
        onClick={onSubmit}
        className="mt-5 inline-flex items-center gap-1.5"
      >
        {isPending ? '评估中…' : '模拟评估'}
        <ChevronRight className="h-4 w-4" />
      </PrimaryButton>
    </Card>
  );
}

function Step2({ data, slMult, setSlMult, tpMult, setTpMult, sizeMult, setSizeMult, onBack, onConfirm, executePending }: {
  data: ManualOrderPreviewResponse;
  slMult: number; setSlMult: (n: number) => void;
  tpMult: number; setTpMult: (n: number) => void;
  sizeMult: number; setSizeMult: (n: number) => void;
  onBack: () => void;
  onConfirm: () => void;
  executePending: boolean;
}) {
  return (
    <>
      <Card title="评估" subtitle="指标 + 规则 + AI 二审">
        <div className="grid gap-4 md:grid-cols-3">
          <SubCard title="指标">
            <IndicatorGauges
              rsi_15m={data.indicators.rsi_15m}
              rsi_4h={data.indicators.rsi_4h ?? null}
              macd_hist_15m={data.indicators.macd_hist_15m}
              macd_hist_prev_15m={data.indicators.macd_hist_prev_15m}
              atr_15m={data.indicators.atr_15m}
            />
          </SubCard>

          <SubCard title="规则决策">
            <div className="space-y-3">
              <div>
                {data.decision.should_trade
                  ? <StatusPill tone="emerald">✓ {data.decision.side}</StatusPill>
                  : <StatusPill tone="rose">✗ 不建议</StatusPill>
                }
              </div>
              <div className="text-sm text-ivory-70 leading-relaxed">{data.decision.reasoning}</div>
              <div className="text-xs font-mono text-ivory-70 pt-2 border-t border-hairline">
                SL <span className="text-oxblood">${data.risk_plan.sl_price.toFixed(4)}</span>
                <span className="text-ivory-40 mx-2">·</span>
                TP <span className="text-sage">${data.risk_plan.tp_price.toFixed(4)}</span>
              </div>
            </div>
          </SubCard>

          <SubCard title="AI 二审">
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                {data.ai_result.execute
                  ? <StatusPill tone="emerald">✓ execute</StatusPill>
                  : <StatusPill tone="rose">✗ reject</StatusPill>
                }
                <span className="text-xs text-ink">置信 {Math.round((data.ai_result.confidence ?? 0) * 100)}%</span>
              </div>
              <div className="text-sm text-ivory-70 leading-relaxed">{data.ai_result.reasoning}</div>
              <div className="grid grid-cols-3 gap-2 pt-2 border-t border-hairline">
                <MultField label="SL ×" value={slMult} min={0.5} max={3} step={0.1} onChange={setSlMult} />
                <MultField label="TP ×" value={tpMult} min={0.5} max={5} step={0.1} onChange={setTpMult} />
                <MultField label="Size ×" value={sizeMult} min={0.1} max={2} step={0.1} onChange={setSizeMult} />
              </div>
            </div>
          </SubCard>
        </div>
      </Card>

      <Card title={<><Term k="RAG">RAG</Term> 历史相似 top-{data.rag_cases.length}</>}>
        {data.rag_cases.length === 0 ? (
          <div className="py-6 text-center text-sm text-ivory-40">RAG 冷启动期,无相似 case</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wider text-ivory-40">
                  <th className="py-2 px-2 font-medium text-right">RSI</th>
                  <th className="py-2 px-2 font-medium text-right">MACD hist</th>
                  <th className="py-2 px-2 font-medium">结果</th>
                  <th className="py-2 px-2 font-medium text-right">PnL</th>
                  <th className="py-2 px-2 font-medium">原因</th>
                  <th className="py-2 px-2 font-medium text-right">距离</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline/60">
                {data.rag_cases.map((c, i) => (
                  <tr key={i} className="hover:bg-bg-surface/40">
                    <td className="py-2 px-2 text-right font-mono tabular-nums text-ivory-70">{c.entry_rsi_15m.toFixed(1)}</td>
                    <td className="py-2 px-2 text-right font-mono tabular-nums text-ivory-70">{c.entry_macd_hist_15m.toFixed(4)}</td>
                    <td className={cn('py-2 px-2 font-medium', c.outcome === 'WIN' ? 'text-sage' : c.outcome === 'LOSS' ? 'text-oxblood' : 'text-ivory-70')}>{c.outcome}</td>
                    <td className={cn('py-2 px-2 text-right font-mono tabular-nums', c.pnl_pct >= 0 ? 'text-sage' : 'text-oxblood')}>{(c.pnl_pct * 100).toFixed(2)}%</td>
                    <td className="py-2 px-2 text-ivory-70">{c.exit_reason ?? '—'}</td>
                    <td className="py-2 px-2 text-right font-mono tabular-nums text-ivory-40">{c.distance.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data.rag_summary && (
          <div className="mt-3 text-sm text-ivory-70 leading-relaxed italic">{data.rag_summary}</div>
        )}
      </Card>

      <div className="flex justify-between">
        <SecondaryButton onClick={onBack} className="inline-flex items-center gap-1.5">
          <ChevronLeft className="h-4 w-4" />
          回到 Step 1
        </SecondaryButton>
        <PrimaryButton
          disabled={executePending}
          onClick={onConfirm}
          className="bg-sage hover:bg-sage/80 inline-flex items-center gap-1.5"
        >
          {executePending ? '开仓中…' : '确认模拟开仓'}
          <ChevronRight className="h-4 w-4" />
        </PrimaryButton>
      </div>
    </>
  );
}

function SubCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-hairline bg-bg-base/60 p-4">
      <div className="text-[10px] uppercase tracking-wider text-ivory-40 pb-2 border-b border-hairline mb-3">{title}</div>
      {children}
    </div>
  );
}

function MultField({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step: number; onChange: (n: number) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] uppercase tracking-wider text-ivory-40">{label}</span>
      <NumberInput value={value} min={min} max={max} step={step} onChange={onChange} />
    </label>
  );
}
