import { ReactNode, useState } from 'react';
import { useV5Settings } from '../../hooks/api/useV5Settings';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Modal } from '../primitives/Modal';
import { Aperture } from '../primitives/Aperture';

export function V5SettingsPage() {
  const { query, patch } = useV5Settings();
  const [confirmLive, setConfirmLive] = useState(false);
  const [deepseekKey, setDeepseekKey] = useState('');
  const [openaiKey, setOpenaiKey] = useState('');
  const [savedAt, setSavedAt] = useState<number | null>(null);

  if (query.isLoading) return <LoadingSkeleton message="拉取系统设置…" />;
  const s = query.data;
  if (!s) return <div className="px-8 py-7 font-body italic text-ivory-40">无数据</div>;

  return (
    <div className="px-8 py-7 pb-16 flex flex-col gap-7 max-w-[1000px]">
      <PageHead mode={s.system_mode} />

      <SettingsSection title="交易所" meta="exchange">
        <Field label="Current">
          <span className="inline-block font-mono text-[0.8rem] tracking-wider2 px-2.5 py-0.5 border border-ink text-ink bg-ink-soft uppercase">
            {s.exchange}
          </span>
        </Field>
      </SettingsSection>

      <SettingsSection title="AI 配置" meta="model + keys">
        <div className="grid grid-cols-2 max-[768px]:grid-cols-1 gap-4">
          <Field label="DeepSeek API Key">
            <input
              type="password"
              placeholder={s.deepseek_api_key_masked || '未配置'}
              value={deepseekKey}
              onChange={e => setDeepseekKey(e.target.value)}
              className="w-full font-mono text-[0.85rem] bg-bg-base border border-hairline-strong px-3 py-2 text-ivory focus:border-brass focus:outline-none placeholder:text-ivory-40"
            />
          </Field>
          <Field label="OpenAI API Key">
            <input
              type="password"
              placeholder={s.openai_api_key_masked || '未配置'}
              value={openaiKey}
              onChange={e => setOpenaiKey(e.target.value)}
              className="w-full font-mono text-[0.85rem] bg-bg-base border border-hairline-strong px-3 py-2 text-ivory focus:border-brass focus:outline-none placeholder:text-ivory-40"
            />
          </Field>
        </div>
        <div className="flex items-center gap-3 mt-4">
          <span className="font-mono text-[0.78rem] text-ivory-40">
            活跃: <span className="text-brass">{s.active_ai_provider ?? '无'}</span>
            <span className="text-ivory-25 mx-2">·</span>
            模型 <span className="text-ivory">{s.active_chat_model}</span>
          </span>
          <button
            type="button"
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
            className="ml-auto font-mono text-[0.78rem] tracking-wider px-4 py-1.5 border border-brass text-brass bg-brass-soft uppercase disabled:opacity-40 hover:bg-brass hover:text-bg-base"
          >
            {patch.isPending ? '保存中…' : '保存 AI 配置'}
          </button>
        </div>
        {savedAt && Date.now() - savedAt < 4000 && (
          <div className="border border-sage-soft bg-sage-soft px-4 py-2 font-mono text-[0.78rem] text-sage">
            <span className="mr-2">▌</span>✓ 已保存,新 key 已写入数据库
          </div>
        )}
        {patch.isError && (
          <div className="border border-oxblood-soft bg-oxblood-soft px-4 py-2 font-mono text-[0.78rem] text-oxblood">
            <span className="mr-2">▌</span>保存失败:{(patch.error as any)?.detail ?? (patch.error as any)?.message ?? 'unknown'}
          </div>
        )}
      </SettingsSection>

      <SettingsSection title="系统模式" meta={s.system_mode === 'LIVE' ? '⚠ live trading' : 'paper trading'}>
        <div className="flex items-center gap-3">
          <span className={`inline-block font-mono text-[0.8rem] tracking-wider2 px-2.5 py-0.5 border uppercase ${
            s.system_mode === 'LIVE'
              ? 'border-alarm/40 text-alarm bg-alarm/10'
              : 'border-brass-soft text-brass bg-brass-soft'
          }`}>
            {s.system_mode === 'LIVE' ? '⬤ LIVE' : '◐ SHADOW'}
          </span>
          <button
            type="button"
            onClick={() => {
              if (s.system_mode === 'SHADOW') setConfirmLive(true);
              else patch.mutate({ system_mode: 'SHADOW' });
            }}
            className="font-mono text-[0.78rem] tracking-wider px-4 py-1.5 border border-hairline-strong text-ivory-70 hover:border-brass hover:text-brass uppercase"
          >
            切换到 {s.system_mode === 'SHADOW' ? 'LIVE' : 'SHADOW'}
          </button>
        </div>
      </SettingsSection>

      <SettingsSection title="Fail-closed 旋钮" meta="safety overrides">
        <div className="flex flex-col gap-3">
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
            hint="关闭后扫描仍跑、但不会真正开仓"
          />
        </div>
      </SettingsSection>

      <Modal open={confirmLive} onClose={() => setConfirmLive(false)} title="切换到 LIVE 模式">
        <div className="flex flex-col gap-4">
          <div className="font-mono text-[0.85rem] text-alarm bg-alarm/10 border border-alarm/40 px-4 py-3">
            ⚠ LIVE 模式将使用真实资金开仓。请确认账户余额和当前活仓状态。
          </div>
          <div className="flex justify-end gap-3 pt-3 border-t border-hairline">
            <button
              type="button"
              onClick={() => setConfirmLive(false)}
              className="font-mono text-[0.78rem] tracking-wider px-4 py-1.5 border border-hairline-strong text-ivory-70 hover:border-ivory hover:text-ivory uppercase"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => { patch.mutate({ system_mode: 'LIVE' }); setConfirmLive(false); }}
              className="font-mono text-[0.78rem] tracking-wider px-4 py-1.5 border border-alarm text-alarm bg-alarm/15 hover:bg-alarm hover:text-ivory uppercase"
            >
              确认切到 LIVE
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function PageHead({ mode }: { mode: string }) {
  return (
    <header className="grid grid-cols-[1fr_auto] items-end gap-6 pb-4 border-b border-hairline-strong">
      <div className="flex items-center gap-4">
        <Aperture size={34} rotate className="text-brass" />
        <div>
          <h1 className="font-display text-[2.6rem] leading-none tracking-tight">Settings</h1>
          <p className="font-cn text-ivory-40 text-[0.85rem] mt-1.5">系统配置 · field calibration</p>
        </div>
      </div>
      <div className="text-right font-mono text-[0.72rem] text-ivory-40 leading-relaxed">
        <div className="tracking-wider2 uppercase">Current Mode</div>
        <div className={`font-mono text-[1.4rem] tabular-nums ${mode === 'LIVE' ? 'text-alarm' : 'text-brass'}`}>
          {mode}
        </div>
      </div>
    </header>
  );
}

function SettingsSection({ title, meta, children }: { title: string; meta: string; children: ReactNode }) {
  return (
    <section className="border border-hairline p-6 flex flex-col gap-4">
      <header className="flex items-center gap-3.5 pb-3 border-b border-hairline">
        <Aperture size={18} className="text-brass" />
        <h2 className="font-display text-[1.4rem] tracking-tight leading-none">{title}</h2>
        <span className="ml-auto font-mono text-[0.7rem] text-ivory-40 tracking-wide">{meta}</span>
      </header>
      {children}
    </section>
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

function CheckboxRow({ checked, onChange, label, hint }: { checked: boolean; onChange: (c: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        className="accent-brass mt-1"
      />
      <div className="flex flex-col gap-0.5">
        <span className="font-cn text-[0.9rem] text-ivory">{label}</span>
        {hint && <span className="font-body italic text-[0.78rem] text-ivory-40">{hint}</span>}
      </div>
    </label>
  );
}
