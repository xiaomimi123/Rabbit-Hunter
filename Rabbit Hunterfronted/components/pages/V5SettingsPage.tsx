import { useState } from 'react';
import { AlertTriangle, CheckCircle, XCircle } from 'lucide-react';
import { useV5Settings } from '../../hooks/api/useV5Settings';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Modal } from '../primitives/Modal';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { Card } from '../primitives-v3/Card';
import { StatusPill } from '../primitives-v3/StatusPill';
import { FormField, TextInput, PrimaryButton, SecondaryButton } from '../primitives-v3/FormField';
import { Alert } from '../primitives-v3/Alert';
import { cn } from '../primitives-v3/cn';

export function V5SettingsPage() {
  const { query, patch, testAi } = useV5Settings();
  const [confirmLive, setConfirmLive] = useState(false);
  const [deepseekKey, setDeepseekKey] = useState('');
  const [openaiKey, setOpenaiKey] = useState('');
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<import('../../types').TestAIResponse | null>(null);
  const [testedAt, setTestedAt] = useState<number | null>(null);

  if (query.isLoading) return <LoadingSkeleton message="拉取系统设置…" />;
  const s = query.data;
  if (!s) return <div className="mx-auto w-full max-w-7xl px-6 py-6 text-sm text-zinc-500">无数据</div>;

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-6 space-y-6">
      <SectionTitle
        title="系统设置"
        subtitle="系统配置 · 凭证 · 自动交易开关"
        action={
          <StatusPill tone={s.system_mode === 'LIVE' ? 'rose' : 'amber'}>
            {s.system_mode === 'LIVE' ? '⬤ LIVE' : '◐ SHADOW'}
          </StatusPill>
        }
      />

      <Card title="交易所" subtitle="exchange">
        <div className="rounded-2xl border border-zinc-800 bg-zinc-950/60 px-4 py-3">
          <div className="text-xs uppercase tracking-wider text-zinc-500">当前</div>
          <div className="mt-1 inline-block rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-sm uppercase text-indigo-200">
            {s.exchange}
          </div>
        </div>
      </Card>

      <Card title="AI 配置" subtitle="model + keys">
        <div className="grid gap-4 md:grid-cols-2">
          <FormField label="DeepSeek API Key">
            <TextInput
              type="password"
              placeholder={s.deepseek_api_key_masked || '未配置'}
              value={deepseekKey}
              onChange={e => setDeepseekKey(e.target.value)}
            />
          </FormField>
          <FormField label="OpenAI API Key">
            <TextInput
              type="password"
              placeholder={s.openai_api_key_masked || '未配置'}
              value={openaiKey}
              onChange={e => setOpenaiKey(e.target.value)}
            />
          </FormField>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <span className="text-sm text-zinc-400">
            活跃:<span className="text-indigo-300 ml-1">{s.active_ai_provider ?? '无'}</span>
            <span className="text-zinc-600 mx-2">·</span>
            模型 <span className="text-zinc-200">{s.active_chat_model}</span>
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
                {
                  onSuccess: () => {
                    setDeepseekKey('');
                    setOpenaiKey('');
                    setSavedAt(Date.now());
                  },
                },
              )}
            >
              {patch.isPending ? '保存中…' : '保存 AI 配置'}
            </PrimaryButton>
          </div>
        </div>

        {savedAt && Date.now() - savedAt < 4000 && (
          <Alert tone="success" className="mt-4">✓ 已保存,新 key 已写入数据库</Alert>
        )}
        {patch.isError && (
          <Alert tone="error" className="mt-4">
            保存失败:{(patch.error as any)?.detail ?? (patch.error as any)?.message ?? 'unknown'}
          </Alert>
        )}
        {testedAt && Date.now() - testedAt < 8000 && testResult && (
          <Alert tone={testResult.ok ? 'success' : 'error'} className="mt-4">
            <div className="flex items-start gap-2">
              {testResult.ok ? <CheckCircle className="h-4 w-4 mt-0.5" /> : <XCircle className="h-4 w-4 mt-0.5" />}
              <div>
                {testResult.message}
                {testResult.provider && <span className="ml-2 opacity-75">· {testResult.provider}/{testResult.model}</span>}
                {testResult.response_text && (
                  <div className="mt-1 text-xs opacity-75">回应:"{testResult.response_text}"</div>
                )}
              </div>
            </div>
          </Alert>
        )}
        {testAi.isError && testedAt && Date.now() - testedAt < 8000 && (
          <Alert tone="error" className="mt-4">
            测试请求失败:{(testAi.error as any)?.detail ?? (testAi.error as any)?.message ?? 'unknown'}
          </Alert>
        )}
      </Card>

      <Card
        title="系统模式"
        subtitle={s.system_mode === 'LIVE' ? '⚠ live trading — 真实资金' : 'paper trading — 模拟开仓'}
      >
        <div className="flex flex-wrap items-center gap-3">
          <StatusPill tone={s.system_mode === 'LIVE' ? 'rose' : 'amber'}>
            {s.system_mode === 'LIVE' ? '⬤ LIVE' : '◐ SHADOW'}
          </StatusPill>
          <SecondaryButton
            onClick={() => {
              if (s.system_mode === 'SHADOW') setConfirmLive(true);
              else patch.mutate({ system_mode: 'SHADOW' });
            }}
          >
            切换到 {s.system_mode === 'SHADOW' ? 'LIVE' : 'SHADOW'}
          </SecondaryButton>
        </div>
      </Card>

      <Card title="Fail-closed 旋钮" subtitle="safety overrides">
        <div className="space-y-3">
          <CheckboxRow
            checked={s.ai_fail_open}
            onChange={c => patch.mutate({ ai_fail_open: c })}
            label="AI 不可用时 fail-open"
            hint="LIVE 默认 fail-closed,勾选 = 允许跳过 AI"
          />
          <CheckboxRow
            checked={s.sl_tp_fail_open}
            onChange={c => patch.mutate({ sl_tp_fail_open: c })}
            label="SL/TP 异常 fail-open"
            hint="止损/止盈计算异常时允许通过"
          />
          <CheckboxRow
            checked={s.enable_auto_trading}
            onChange={c => patch.mutate({ enable_auto_trading: c })}
            label="启用自动交易"
            hint="关闭后扫描仍跑,但不会真正开仓"
          />
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
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        className="accent-indigo-500 mt-1 h-4 w-4"
      />
      <div className="flex-1">
        <div className={cn('text-sm', checked ? 'text-zinc-100' : 'text-zinc-300')}>{label}</div>
        {hint && <div className="text-xs text-zinc-500 mt-0.5">{hint}</div>}
      </div>
    </label>
  );
}
