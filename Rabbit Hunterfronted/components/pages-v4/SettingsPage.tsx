import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle, XCircle } from 'lucide-react';
import { useV5Settings } from '../../hooks/api/useV5Settings';
import { useV5StrategyConfig } from '../../hooks/api/useV5StrategyConfig';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Modal } from '../primitives/Modal';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { FormField, TextInput, PrimaryButton, SecondaryButton } from '../primitives-v3/FormField';
import { Alert } from '../primitives-v3/Alert';
import { Slider } from '../primitives/Slider';
import { NumberInput } from '../primitives/NumberInput';
import { cn } from '../primitives-v3/cn';

export function SettingsPage() {
  const { query, patch, testAi } = useV5Settings();
  const strategy = useV5StrategyConfig();
  const [confirmLive, setConfirmLive] = useState(false);
  const [deepseekKey, setDeepseekKey] = useState('');
  const [openaiKey, setOpenaiKey] = useState('');
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<import('../../types').TestAIResponse | null>(null);
  const [testedAt, setTestedAt] = useState<number | null>(null);
  const [dirty, setDirty] = useState<Record<string, number>>({});

  useEffect(() => { setDirty({}); }, [strategy.query.data]);

  if (query.isLoading) return <LoadingSkeleton message="拉取设置…" />;
  const s = query.data;
  if (!s) return <div className="text-sm text-zinc-500">无数据</div>;

  const params = strategy.query.data?.params ?? [];
  const dirtyCount = Object.keys(dirty).length;
  const effective = (key: string, current: number) =>
    Object.prototype.hasOwnProperty.call(dirty, key) ? dirty[key] : current;

  return (
    <div className="space-y-6">
      <SectionTitle
        title="系统设置"
        subtitle="凭据保存和自动交易运行参数"
        action={
          <StatusPill tone={s.system_mode === 'LIVE' ? 'rose' : 'amber'}>
            {s.system_mode === 'LIVE' ? '⬤ LIVE' : '◐ SHADOW'}
          </StatusPill>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
        <Card title="凭据" subtitle="OKX + AI 提供方">
          <div className="grid gap-4 md:grid-cols-2">
            <FormField label="DeepSeek API Key">
              <TextInput type="password" placeholder={s.deepseek_api_key_masked || '未配置'} value={deepseekKey} onChange={e => setDeepseekKey(e.target.value)} />
            </FormField>
            <FormField label="OpenAI API Key">
              <TextInput type="password" placeholder={s.openai_api_key_masked || '未配置'} value={openaiKey} onChange={e => setOpenaiKey(e.target.value)} />
            </FormField>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className="text-sm text-zinc-400">
              活跃:<span className="text-indigo-300 ml-1">{s.active_ai_provider ?? '无'}</span>
              <span className="text-zinc-600 mx-2">·</span>
              <span className="text-zinc-200">{s.active_chat_model}</span>
            </span>
            <div className="ml-auto flex gap-2">
              <SecondaryButton
                disabled={testAi.isPending}
                onClick={() => testAi.mutate(
                  {
                    ...(deepseekKey ? { deepseek_api_key: deepseekKey } : {}),
                    ...(openaiKey ? { openai_api_key: openaiKey } : {}),
                  },
                  {
                    onSuccess: (r) => { setTestResult(r); setTestedAt(Date.now()); },
                    onError: () => { setTestResult(null); setTestedAt(Date.now()); },
                  },
                )}
              >
                {testAi.isPending ? '测试中…' : '测试连接'}
              </SecondaryButton>
              <PrimaryButton
                disabled={patch.isPending || (!deepseekKey && !openaiKey)}
                onClick={() => patch.mutate(
                  {
                    ...(deepseekKey ? { deepseek_api_key: deepseekKey } : {}),
                    ...(openaiKey ? { openai_api_key: openaiKey } : {}),
                  },
                  { onSuccess: () => { setDeepseekKey(''); setOpenaiKey(''); setSavedAt(Date.now()); } },
                )}
              >
                {patch.isPending ? '保存中…' : '保存'}
              </PrimaryButton>
            </div>
          </div>
          {savedAt && Date.now() - savedAt < 4000 && <Alert tone="success" className="mt-4">✓ 已保存,新 key 已写入</Alert>}
          {testedAt && Date.now() - testedAt < 8000 && testResult && (
            <Alert tone={testResult.ok ? 'success' : 'error'} className="mt-4">
              <div className="flex items-start gap-2">
                {testResult.ok ? <CheckCircle className="h-4 w-4 mt-0.5" /> : <XCircle className="h-4 w-4 mt-0.5" />}
                <div>
                  {testResult.message}
                  {testResult.provider && <span className="ml-2 opacity-75">· {testResult.provider}/{testResult.model}</span>}
                </div>
              </div>
            </Alert>
          )}
        </Card>

        <Card title="自动交易参数" subtitle="安全旋钮 + 模式切换">
          <div className="space-y-3">
            <CheckboxRow checked={s.ai_fail_open} onChange={c => patch.mutate({ ai_fail_open: c })} label="AI 不可用时 fail-open" hint="LIVE 默认 fail-closed,勾选 = 允许跳过 AI" />
            <CheckboxRow checked={s.sl_tp_fail_open} onChange={c => patch.mutate({ sl_tp_fail_open: c })} label="SL/TP 异常 fail-open" hint="止损/止盈计算异常时允许通过" />
            <CheckboxRow checked={s.enable_auto_trading} onChange={c => patch.mutate({ enable_auto_trading: c })} label="启用自动交易" hint="关闭后扫描仍跑,但不会真正开仓" />
          </div>

          <div className="mt-5 flex items-center gap-3 rounded-2xl border border-zinc-800 bg-zinc-950/60 p-4">
            <div className="flex-1">
              <div className="text-xs uppercase tracking-wider text-zinc-500 mb-1">系统模式</div>
              <div className={cn('font-mono text-sm font-semibold', s.system_mode === 'LIVE' ? 'text-rose-300' : 'text-amber-300')}>
                {s.system_mode === 'LIVE' ? '⬤ LIVE — 真实资金' : '◐ SHADOW — 模拟开仓'}
              </div>
            </div>
            <SecondaryButton onClick={() => {
              if (s.system_mode === 'SHADOW') setConfirmLive(true);
              else patch.mutate({ system_mode: 'SHADOW' });
            }}>
              切到 {s.system_mode === 'SHADOW' ? 'LIVE' : 'SHADOW'}
            </SecondaryButton>
          </div>
        </Card>
      </div>

      <Card
        title="策略参数"
        subtitle="拖动滑条或直接输入,带 ● 标记为本次修改"
        actions={
          <div className="flex gap-2">
            <SecondaryButton onClick={() => setDirty({})} disabled={dirtyCount === 0}>撤销</SecondaryButton>
            <PrimaryButton disabled={!dirtyCount || strategy.patch.isPending} onClick={() => strategy.patch.mutate(dirty)}>
              {strategy.patch.isPending ? '保存中…' : `保存 (${dirtyCount})`}
            </PrimaryButton>
          </div>
        }
      >
        <div className="divide-y divide-zinc-800/60">
          {params.map(p => {
            const eff = effective(p.key, p.value);
            const changed = eff !== p.value;
            return (
              <div key={p.key} className="grid grid-cols-1 md:grid-cols-12 items-center gap-3 py-3">
                <div className="md:col-span-3">
                  <div className="flex items-center gap-1.5 font-mono text-sm text-zinc-100">
                    {changed && <span className="text-indigo-400">●</span>}
                    {p.key}
                  </div>
                  <div className="text-xs text-zinc-500 mt-0.5">{p.description}</div>
                </div>
                <div className="md:col-span-6">
                  <Slider value={eff} min={p.min} max={p.max} step={(p.max - p.min) / 100}
                          onChange={(v) => setDirty(d => ({ ...d, [p.key]: v }))} />
                </div>
                <div className="md:col-span-2">
                  <NumberInput value={eff} min={p.min} max={p.max} step={(p.max - p.min) / 100}
                               onChange={(v) => setDirty(d => ({ ...d, [p.key]: v }))} />
                </div>
                <div className={cn('md:col-span-1 text-right text-xs', changed ? 'text-indigo-300' : 'text-zinc-500')}>{p.unit}</div>
              </div>
            );
          })}
        </div>
      </Card>

      <Modal open={confirmLive} onClose={() => setConfirmLive(false)} title="切换到 LIVE 模式">
        <div className="space-y-4">
          <Alert tone="error">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 mt-0.5" />
              <div>LIVE 模式将使用真实资金开仓。请确认账户余额和当前活仓状态。</div>
            </div>
          </Alert>
          <div className="flex justify-end gap-3">
            <SecondaryButton onClick={() => setConfirmLive(false)}>取消</SecondaryButton>
            <button
              type="button"
              onClick={() => { patch.mutate({ system_mode: 'LIVE' }); setConfirmLive(false); }}
              className="rounded-2xl border border-rose-500 bg-rose-500/15 px-4 py-2 text-sm text-rose-200 transition hover:bg-rose-500 hover:text-zinc-50"
            >
              确认切到 LIVE
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function CheckboxRow({ checked, onChange, label, hint }: { checked: boolean; onChange: (c: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="flex items-start gap-3 rounded-2xl border border-zinc-800 bg-zinc-950/60 px-4 py-3 cursor-pointer hover:border-zinc-700 transition">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} className="accent-indigo-500 mt-1 h-4 w-4" />
      <div className="flex-1">
        <div className={cn('text-sm', checked ? 'text-zinc-100' : 'text-zinc-300')}>{label}</div>
        {hint && <div className="text-xs text-zinc-500 mt-0.5">{hint}</div>}
      </div>
    </label>
  );
}
