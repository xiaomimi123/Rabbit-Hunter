/**
 * SettingsPage — UI 原型 2026-06-27 落地版本。
 *
 * 4 个区: AI 接入 / OKX 交易所 / 交易模式 (LIVE 二次确认) / 风控参数 (宪法锁)
 */
import { useEffect, useState } from 'react';
import { Settings as SettingsIcon, TrendingUp, AlertTriangle, ShieldCheck } from 'lucide-react';
import { useV5Settings } from '../../hooks/api/useV5Settings';

function Section({ icon, title, danger, children }: {
  icon: React.ReactNode; title: string; danger?: boolean; children: React.ReactNode;
}) {
  return (
    <section className="rounded-[10px] border border-line-soft bg-panel p-5">
      <div className={`flex items-center gap-2 mb-4 text-[11px] uppercase tracking-[0.08em] font-semibold ${danger ? 'text-loss' : 'text-amber'}`}>
        {icon}<span>{title}</span>
      </div>
      <div className="flex flex-col">{children}</div>
    </section>
  );
}

function Field({ title, hint, control, locked }: {
  title: string; hint?: string; control: React.ReactNode; locked?: boolean;
}) {
  return (
    <div className={`flex items-center justify-between gap-4 py-3 border-b border-line-soft last:border-b-0 ${locked ? 'opacity-60' : ''}`}>
      <div className="min-w-0">
        <div className="text-[13px] text-v3text">{title}</div>
        {hint && <div className="text-[11px] text-v3faint mt-0.5">{hint}</div>}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  );
}

function Pill({ tone, children }: { tone: 'ok' | 'warn' | 'off'; children: React.ReactNode }) {
  const cls = tone === 'ok'
    ? 'text-gain bg-gain/10 border-gain/30'
    : tone === 'warn'
    ? 'text-amber bg-amber-soft border-amber/30'
    : 'text-v3faint bg-[#1a232d] border-line';
  return (
    <span className={`text-[10.5px] px-2 py-0.5 rounded border font-semibold tracking-[0.02em] ${cls}`}>
      {children}
    </span>
  );
}

function Toggle({ on, onClick, tone = 'amber', disabled }: {
  on: boolean; onClick: () => void; tone?: 'amber' | 'loss'; disabled?: boolean;
}) {
  const bg = on ? (tone === 'loss' ? 'bg-loss' : 'bg-amber') : 'bg-line';
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`relative w-[42px] h-[22px] rounded-full transition disabled:opacity-50 disabled:cursor-not-allowed ${bg}`}
    >
      <span className={`absolute top-[2px] h-[18px] w-[18px] rounded-full bg-v3text transition-transform ${on ? 'translate-x-[22px]' : 'translate-x-[2px]'}`} />
    </button>
  );
}

function TextInput({ value, type = 'text', onChange, onBlur, placeholder, disabled }: {
  value: string | number; type?: 'text' | 'password';
  onChange?: (v: string) => void; onBlur?: () => void;
  placeholder?: string; disabled?: boolean;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
      onBlur={onBlur}
      placeholder={placeholder}
      disabled={disabled}
      className="rounded-md border border-line bg-[#0E141A] px-3 py-1.5 font-mono text-[12px] text-v3text placeholder:text-v3faint focus:border-amber focus:outline-none transition w-[200px] disabled:opacity-60"
    />
  );
}

function LiveConfirmModal({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: () => void }) {
  const [text, setText] = useState('');
  const canConfirm = text === 'CONFIRM';
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md mx-6 rounded-lg border border-loss/40 bg-panel2 p-6 shadow-2xl">
        <div className="flex items-center gap-2 mb-3 text-loss">
          <AlertTriangle className="h-5 w-5" />
          <h3 className="text-base font-semibold">切换到 LIVE 实盘交易</h3>
        </div>
        <p className="text-[13px] text-v3text leading-[1.6] mb-4">
          切到 LIVE 后,新信号会用 OKX <b className="text-loss">真实账户</b>下单。请确认:
        </p>
        <ul className="text-[12px] text-v3muted leading-[1.7] mb-4 pl-5 list-disc">
          <li>已设 OKX API key/secret/passphrase</li>
          <li>已检查风控参数 (单笔风险 / 杠杆 / 熔断)</li>
          <li>已用 paper 验证过当前策略 ≥ 30 笔</li>
        </ul>
        <div className="mb-4">
          <div className="text-[11px] text-v3muted mb-1.5">
            输入 <code className="text-amber font-mono">CONFIRM</code> 确认切换:
          </div>
          <input
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="CONFIRM"
            className="w-full rounded-md border border-line bg-ink px-3 py-2 font-mono text-sm text-v3text focus:border-loss focus:outline-none"
            autoFocus
          />
        </div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-md border border-line text-v3muted text-sm hover:border-v3text hover:text-v3text transition"
          >
            取消
          </button>
          <button
            type="button"
            disabled={!canConfirm}
            onClick={onConfirm}
            className={`px-4 py-2 rounded-md text-sm font-semibold transition ${
              canConfirm ? 'bg-loss text-v3text hover:bg-loss/80' : 'bg-loss/30 text-v3faint cursor-not-allowed'
            }`}
          >
            切换到 LIVE
          </button>
        </div>
      </div>
    </div>
  );
}

export function SettingsPage() {
  const { query, patch } = useV5Settings();
  const settings = query.data;
  const [showLiveModal, setShowLiveModal] = useState(false);
  const [openaiKey, setOpenaiKey] = useState('');
  const [deepseekKey, setDeepseekKey] = useState('');
  const [okxKey, setOkxKey] = useState('');
  const [okxSecret, setOkxSecret] = useState('');
  const [okxPassphrase, setOkxPassphrase] = useState('');
  const [maxConcurrentDraft, setMaxConcurrentDraft] = useState<string>('');
  useEffect(() => {
    if (settings?.v5_max_concurrent != null) {
      setMaxConcurrentDraft(String(settings.v5_max_concurrent));
    }
  }, [settings?.v5_max_concurrent]);
  const commitMaxConcurrent = () => {
    const n = Number(maxConcurrentDraft);
    if (Number.isInteger(n) && n >= 1 && n <= 10 && n !== settings?.v5_max_concurrent) {
      patch.mutate({ v5_max_concurrent: n } as any);
    }
  };

  // AI API Key onBlur commit — 提交后清空 input 避免明文停留
  const commitOpenaiKey = () => {
    const v = openaiKey.trim();
    if (!v) return;
    patch.mutate({ openai_api_key: v } as any);
    setOpenaiKey('');
  };
  const commitDeepseekKey = () => {
    const v = deepseekKey.trim();
    if (!v) return;
    patch.mutate({ deepseek_api_key: v } as any);
    setDeepseekKey('');
  };

  const isLive = settings?.system_mode === 'LIVE';
  const autoOn = settings?.enable_auto_trading ?? false;

  const handleLiveToggle = () => {
    if (isLive) {
      patch.mutate({ system_mode: 'SHADOW' } as any);
    } else {
      setShowLiveModal(true);
    }
  };

  return (
    <div className="px-6 pb-10 pt-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
        <div className="flex flex-col gap-3.5">
          <Section icon={<SettingsIcon className="h-3.5 w-3.5" />} title="AI 接入">
            <Field title="OpenAI Assistant" hint="主决策 · GPT-4o · 二次判断与反思"
              control={<Pill tone={settings?.active_ai_provider === 'openai' ? 'ok' : 'off'}>
                {settings?.active_ai_provider === 'openai' ? '已激活' : '未启用'}</Pill>} />
            <Field title="OpenAI API Key" hint={`已存: ${settings?.openai_api_key_masked || '(空)'} · 输入后离开输入框自动保存`}
              control={<TextInput type="password" value={openaiKey}
                onChange={setOpenaiKey} onBlur={commitOpenaiKey} placeholder="sk-..." />} />
            <Field title="DeepSeek 备用" hint="主模型故障时兜底"
              control={<Toggle on={settings?.deepseek_enabled ?? false}
                onClick={() => patch.mutate({ deepseek_enabled: !settings?.deepseek_enabled } as any)} />} />
            <Field title="DeepSeek API Key" hint={`已存: ${settings?.deepseek_api_key_masked || '(空)'} · 输入后离开输入框自动保存`}
              control={<TextInput type="password" value={deepseekKey}
                onChange={setDeepseekKey} onBlur={commitDeepseekKey} placeholder="sk-..." />} />
            <Field title="AI 故障时下单 (fail-open)" hint="关闭 = AI 不可用时拒绝交易 (推荐 fail-closed)"
              control={<Toggle on={settings?.ai_fail_open ?? false}
                onClick={() => patch.mutate({ ai_fail_open: !settings?.ai_fail_open } as any)} />} />
          </Section>

          <Section icon={<TrendingUp className="h-3.5 w-3.5" />} title="OKX 交易所">
            <Field title="连接状态" hint="永续合约 · 密钥仅存本地"
              control={<Pill tone={settings?.exchange === 'okx' ? 'ok' : 'off'}>
                {settings?.exchange === 'okx' ? '已连接' : '未配置'}</Pill>} />
            <Field title="API Key"
              control={<TextInput type="password" value={okxKey} onChange={setOkxKey} placeholder="OKX key" />} />
            <Field title="Secret"
              control={<TextInput type="password" value={okxSecret} onChange={setOkxSecret} placeholder="OKX secret" />} />
            <Field title="Passphrase"
              control={<TextInput type="password" value={okxPassphrase} onChange={setOkxPassphrase} placeholder="passphrase" />} />
          </Section>
        </div>

        <div className="flex flex-col gap-3.5">
          <Section icon={<AlertTriangle className="h-3.5 w-3.5" />} title="交易模式 · 高风险" danger>
            <Field title="实盘自动交易 (LIVE)"
              hint={`当前: ${isLive ? 'LIVE 真钱' : 'SHADOW 纸面'}`}
              control={
                <div className="flex items-center gap-3">
                  <Pill tone={isLive ? 'warn' : 'ok'}>{isLive ? 'LIVE' : 'SHADOW'}</Pill>
                  <Toggle on={isLive} onClick={handleLiveToggle} tone="loss" />
                </div>
              } />
            <Field title="启动信号扫描"
              hint="关闭 = 不开新仓 (LIVE 也不开)"
              control={<Toggle on={autoOn}
                onClick={() => patch.mutate({ enable_auto_trading: !autoOn } as any)} />} />
            <Field title="纸面初始资金" hint="SHADOW 模拟账户起始"
              control={<TextInput value="10,000 USDT" disabled />} />
            <Field title="做空 (VULTURE)" hint="宪法 §6 · 默认关闭"
              control={<Toggle on={false} onClick={() => {}} disabled />} locked />
          </Section>

          <Section icon={<ShieldCheck className="h-3.5 w-3.5" />} title="风控参数 · 宪法约束">
            <Field title="单笔风险" hint="宪法 §1 · 硬上限 1%"
              control={<TextInput value="1.0 %" disabled />} locked />
            <Field title="日内熔断" hint="宪法 §3 · 锁定"
              control={<TextInput value="-3.0 %" disabled />} locked />
            <Field title="杠杆上限" hint="宪法 §4 · 系统再反推压低"
              control={<TextInput value="5x" disabled />} locked />
            <Field title="同时活仓上限" hint="v5_max_concurrent · 范围 1-10"
              control={<TextInput
                value={maxConcurrentDraft}
                onChange={setMaxConcurrentDraft}
                onBlur={commitMaxConcurrent}
              />} />
            <Field title="SL/TP 失败保留仓" hint="关闭 = SL/TP 挂单失败立即平仓回滚"
              control={<Toggle on={settings?.sl_tp_fail_open ?? false}
                onClick={() => patch.mutate({ sl_tp_fail_open: !settings?.sl_tp_fail_open } as any)} />} />
          </Section>
        </div>
      </div>

      {showLiveModal && (
        <LiveConfirmModal
          onCancel={() => setShowLiveModal(false)}
          onConfirm={() => {
            patch.mutate({ system_mode: 'LIVE' } as any);
            setShowLiveModal(false);
          }}
        />
      )}
    </div>
  );
}
