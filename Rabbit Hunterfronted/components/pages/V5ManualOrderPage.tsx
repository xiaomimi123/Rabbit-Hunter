import { ReactNode, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useV5ManualOrder } from '../../hooks/api/useV5ManualOrder';
import { useSystemMode } from '../../hooks/useSystemMode';
import { NumberInput } from '../primitives/NumberInput';
import { IndicatorGauges } from '../shared/IndicatorGauges';
import { Aperture } from '../primitives/Aperture';
import { Term } from '../shared/Term';
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
      <div className="px-8 py-7 pb-16 max-w-[800px]">
        <div className="border border-alarm/40 bg-alarm/10 px-4 py-3 font-mono text-[0.85rem] text-alarm">
          ⚠ 手动开单仅在 SHADOW 模式可用。
        </div>
      </div>
    );
  }

  return (
    <div className="px-8 py-7 pb-16 flex flex-col gap-7 max-w-[1400px]">
      <PageHead step={step} />
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
        <div className="py-14 text-center">
          <Aperture size={56} className="text-sage mx-auto block mb-4" />
          <p className="font-display text-[2.2rem] text-sage leading-tight">✓ 模拟开仓成功</p>
          <p className="font-cn text-ivory-40 text-[0.85rem] mt-2">即将跳转到活仓监控…</p>
        </div>
      )}
    </div>
  );
}

function PageHead({ step }: { step: Step }) {
  return (
    <header className="grid grid-cols-[1fr_auto] items-end gap-6 pb-4 border-b border-hairline-strong">
      <div className="flex items-center gap-4">
        <Aperture size={34} rotate className="text-brass" />
        <div>
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight">Manual Order</h1>
          <p className="font-cn text-ivory-40 text-[0.85rem] mt-1.5">手动开单 · paper-trade · Step {step}/3</p>
        </div>
      </div>
    </header>
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
          <div className={`w-9 h-9 grid place-items-center border-2 font-display text-[1.1rem] ${
            current === s.id
              ? 'border-brass text-brass bg-brass-soft'
              : current > s.id
              ? 'border-sage text-sage bg-sage-soft'
              : 'border-hairline-strong text-ivory-40'
          }`}>
            {current > s.id ? '✓' : s.id}
          </div>
          <span className={`font-cn text-[0.85rem] ${
            current === s.id ? 'text-brass' : current > s.id ? 'text-sage' : 'text-ivory-40'
          }`}>
            {s.label}
          </span>
          {i < steps.length - 1 && (
            <div className={`flex-1 h-px ${current > s.id ? 'bg-sage' : 'bg-hairline'} mx-2`} />
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
    <section className="border border-hairline p-6 flex flex-col gap-5">
      <header className="flex items-center gap-3.5 pb-3 border-b border-hairline">
        <Aperture size={18} className="text-brass" />
        <h2 className="font-display text-[1.4rem] tracking-tight leading-none">参数</h2>
      </header>

      <div className="grid grid-cols-3 max-[768px]:grid-cols-1 gap-5">
        <Field label="Symbol">
          <input
            value={symbol}
            onChange={e => onSymbolChange(e.target.value)}
            className="w-full font-mono text-[0.95rem] bg-bg-base border border-hairline-strong px-3 py-2 text-ivory focus:border-brass focus:outline-none"
          />
        </Field>
        <Field label="Side">
          <div className="inline-flex border border-hairline-strong">
            {(['LONG', 'SHORT'] as Side[]).map(opt => (
              <button
                key={opt}
                type="button"
                onClick={() => onSideChange(opt)}
                className={`font-mono text-[0.8rem] tracking-wider2 px-4 py-2 border-r border-hairline-strong last:border-r-0 ${
                  side === opt
                    ? opt === 'LONG'
                      ? 'bg-sage-soft text-sage'
                      : 'bg-oxblood-soft text-oxblood'
                    : 'text-ivory-70 hover:bg-white/[0.04]'
                }`}
              >
                {opt}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Size (USDT)">
          <NumberInput value={size} min={5} max={500} step={1} onChange={onSizeChange} />
        </Field>
      </div>

      {error && (
        <div className="border border-oxblood-soft bg-oxblood-soft px-3 py-2 font-mono text-[0.85rem] text-oxblood">
          评估失败:{error}
        </div>
      )}

      <button
        type="button"
        disabled={isPending || !symbol}
        onClick={onSubmit}
        className="self-start font-mono text-[0.85rem] tracking-wider px-5 py-2 border border-brass text-brass bg-brass-soft uppercase hover:bg-brass hover:text-bg-base disabled:opacity-40"
      >
        {isPending ? '评估中…' : '模拟评估 →'}
      </button>
    </section>
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
      <section className="border border-hairline p-6 flex flex-col gap-5">
        <header className="flex items-center gap-3.5 pb-3 border-b border-hairline">
          <Aperture size={18} className="text-brass" />
          <h2 className="font-display text-[1.4rem] tracking-tight leading-none">评估</h2>
        </header>

        <div className="grid grid-cols-3 max-[1100px]:grid-cols-1 gap-px bg-hairline border border-hairline">
          <SubCard title="Indicators">
            <IndicatorGauges
              rsi_15m={data.indicators.rsi_15m}
              rsi_4h={data.indicators.rsi_4h ?? null}
              macd_hist_15m={data.indicators.macd_hist_15m}
              macd_hist_prev_15m={data.indicators.macd_hist_prev_15m}
              atr_15m={data.indicators.atr_15m}
            />
          </SubCard>

          <SubCard title="Rule Decision">
            <div className="flex flex-col gap-2 font-mono text-[0.85rem]">
              <div>
                {data.decision.should_trade
                  ? <span className="inline-block border border-sage text-sage bg-sage-soft px-2 py-0.5 text-[0.78rem] tracking-wider2 uppercase">✓ {data.decision.side}</span>
                  : <span className="inline-block border border-oxblood text-oxblood bg-oxblood-soft px-2 py-0.5 text-[0.78rem] tracking-wider2 uppercase">✗ 不建议</span>
                }
              </div>
              <div className="font-body italic text-[0.85rem] text-ivory-70 leading-relaxed">{data.decision.reasoning}</div>
              <div className="font-mono text-[0.78rem] text-ivory-70">
                SL <span className="text-oxblood">${data.risk_plan.sl_price.toFixed(4)}</span>
                <span className="text-ivory-25 mx-2">·</span>
                TP <span className="text-sage">${data.risk_plan.tp_price.toFixed(4)}</span>
              </div>
            </div>
          </SubCard>

          <SubCard title="AI Review">
            <div className="flex flex-col gap-3">
              <div>
                {data.ai_result.execute
                  ? <span className="inline-block border border-sage text-sage bg-sage-soft px-2 py-0.5 text-[0.78rem] tracking-wider2 uppercase">✓ execute</span>
                  : <span className="inline-block border border-oxblood text-oxblood bg-oxblood-soft px-2 py-0.5 text-[0.78rem] tracking-wider2 uppercase">✗ reject</span>
                }
                <span className="font-mono text-[0.78rem] text-brass ml-3">conf {Math.round((data.ai_result.confidence ?? 0) * 100)}%</span>
              </div>
              <div className="font-body italic text-[0.85rem] text-ivory-70 leading-relaxed">{data.ai_result.reasoning}</div>
              <div className="grid grid-cols-3 gap-2 font-mono text-[0.78rem] pt-2 border-t border-hairline">
                <MultField label="SL ×" value={slMult} min={0.5} max={3} step={0.1} onChange={setSlMult} />
                <MultField label="TP ×" value={tpMult} min={0.5} max={5} step={0.1} onChange={setTpMult} />
                <MultField label="Size ×" value={sizeMult} min={0.1} max={2} step={0.1} onChange={setSizeMult} />
              </div>
            </div>
          </SubCard>
        </div>
      </section>

      <section className="border border-hairline p-6 flex flex-col gap-4">
        <header className="flex items-center gap-3.5 pb-3 border-b border-hairline">
          <Aperture size={18} className="text-brass" />
          <h2 className="font-display text-[1.4rem] tracking-tight leading-none">
            <Term k="RAG">RAG</Term> 历史相似 top-{data.rag_cases.length}
          </h2>
        </header>
        {data.rag_cases.length === 0 ? (
          <div className="py-6 text-center font-body italic text-ivory-40">
            <span className="opacity-60 mr-2">▌</span>RAG 冷启动期,无相似 case
          </div>
        ) : (
          <table className="w-full text-[0.78rem] border-collapse">
            <thead>
              <tr>
                <Th align="right">RSI</Th>
                <Th align="right">MACD hist</Th>
                <Th>结果</Th>
                <Th align="right">PnL</Th>
                <Th>原因</Th>
                <Th align="right">距离</Th>
              </tr>
            </thead>
            <tbody>
              {data.rag_cases.map((c, i) => (
                <tr key={i} className="border-b border-hairline hover:bg-brass/[0.04]">
                  <Td align="right">{c.entry_rsi_15m.toFixed(1)}</Td>
                  <Td align="right">{c.entry_macd_hist_15m.toFixed(4)}</Td>
                  <Td className={c.outcome === 'WIN' ? 'text-sage' : c.outcome === 'LOSS' ? 'text-oxblood' : 'text-ivory-70'}>{c.outcome}</Td>
                  <Td align="right" className={c.pnl_pct >= 0 ? 'text-sage' : 'text-oxblood'}>{(c.pnl_pct * 100).toFixed(2)}%</Td>
                  <Td className="text-ivory-70">{c.exit_reason ?? '—'}</Td>
                  <Td align="right" className="text-ivory-40">{c.distance.toFixed(3)}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {data.rag_summary && (
          <div className="mt-2 font-body italic text-[0.85rem] text-ivory-70 leading-relaxed">{data.rag_summary}</div>
        )}
      </section>

      <div className="flex justify-between">
        <button
          type="button"
          onClick={onBack}
          className="font-mono text-[0.85rem] tracking-wider px-4 py-2 border border-hairline-strong text-ivory-70 hover:border-brass hover:text-brass uppercase"
        >
          ↩ 回到 Step 1
        </button>
        <button
          type="button"
          disabled={executePending}
          onClick={onConfirm}
          className="font-mono text-[0.85rem] tracking-wider px-5 py-2 border border-sage text-sage bg-sage-soft uppercase hover:bg-sage hover:text-bg-base disabled:opacity-40"
        >
          {executePending ? '开仓中…' : '确认模拟开仓 →'}
        </button>
      </div>
    </>
  );
}

function SubCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="bg-bg-base p-4 flex flex-col gap-3">
      <div className="font-mono text-[0.66rem] tracking-wider3 text-ivory-40 uppercase pb-2 border-b border-hairline">{title}</div>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase">{label}</div>
      <div>{children}</div>
    </div>
  );
}

function MultField({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step: number; onChange: (n: number) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[0.62rem] tracking-wider3 text-ivory-40 uppercase">{label}</span>
      <NumberInput value={value} min={min} max={max} step={step} onChange={onChange} />
    </label>
  );
}

function Th({ children, align = 'left' }: { children: ReactNode; align?: 'left' | 'right' }) {
  return (
    <th className={`text-${align} font-mono text-[0.62rem] tracking-wider3 text-ivory-40 uppercase font-normal px-3.5 py-2.5 border-b border-hairline`}>
      {children}
    </th>
  );
}

function Td({ children, align = 'left', className = '' }: { children: ReactNode; align?: 'left' | 'right'; className?: string }) {
  return (
    <td className={`px-3.5 py-2.5 font-mono text-[0.78rem] tabular-nums ${align === 'right' ? 'text-right' : ''} ${className}`}>
      {children}
    </td>
  );
}
