/**
 * SettingsPage v0.5.3 — 全部配置入口
 *
 * 四个 section：
 *   1) Active Exchange 切换（OKX / Binance segmented）
 *   2) OKX 配置（key/secret/passphrase/testnet/leverage）
 *   3) Binance 配置（key/secret/testnet/leverage）
 *   4) AI 大模型配置（provider/model/api_key/enabled）
 *
 * 所有配置都保存到 system_settings 表（敏感字段 Fernet 加密）。
 * DB 没设时 fallback 到 env（OKX_* / BINANCE_* / OPENAI_API_KEY 等）。
 * UI 上的 "source" 标签提示当前生效的是 db 还是 env。
 *
 * 简约高级风格延续 v0.5.0：单 accent + hairline + 无 emoji。
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Check, Eye, EyeOff, Save, Trash2, RefreshCw } from 'lucide-react';
import { exchangeConfigAPI, aiConfigAPI } from '../services/api';
import { toast } from './Toast';
import { Card, Pill, SectionHeader, StatTile } from './ui/Primitives';

// ─── 类型 ─────────────────────────────────────────────────────────────

interface ExchangeStatus {
  configured:       boolean;
  api_key_masked?:  string;
  testnet?:         boolean;
  leverage?:        number;
  source?:          'db' | 'env' | 'unknown';
  has_passphrase?:  boolean;
}
interface ExchangeStatusResp {
  active:    'okx' | 'binance';
  exchanges: { okx: ExchangeStatus; binance: ExchangeStatus };
}
interface AIStatusResp {
  provider:            'openai' | 'deepseek' | 'anthropic' | 'disabled';
  model:               string;
  enabled:             boolean;
  api_key_masked:      string;
  source:              'db' | 'env' | 'default';
  available_providers: string[];
}

// ─── 主组件 ────────────────────────────────────────────────────────────

export const SettingsPage: React.FC = () => {
  const qc = useQueryClient();

  const { data: exStatusResp, isLoading: exLoading } = useQuery({
    queryKey: ['exchangeStatus'],
    queryFn:  () => exchangeConfigAPI.getStatus(),
    refetchOnWindowFocus: true,
  });
  const exStatus: ExchangeStatusResp | null = exStatusResp?.data ?? null;

  const { data: aiStatusResp, isLoading: aiLoading } = useQuery({
    queryKey: ['aiConfig'],
    queryFn:  () => aiConfigAPI.get(),
    refetchOnWindowFocus: true,
  });
  const aiStatus: AIStatusResp | null = aiStatusResp?.data ?? null;

  const setActive = useMutation({
    mutationFn: (ex: 'okx' | 'binance') => exchangeConfigAPI.setActive(ex),
    onSuccess: (_d, ex) => {
      toast.success(`已切换到 ${ex.toUpperCase()}`);
      qc.invalidateQueries({ queryKey: ['exchangeStatus'] });
      qc.invalidateQueries({ queryKey: ['activeExchange'] });
    },
    onError: (e: any) => toast.error(`切换失败: ${e?.message ?? e}`),
  });

  return (
    <div className="space-y-8 max-w-3xl">
      {/* hero */}
      <header>
        <div className="label-sm mb-1">系统设置</div>
        <h1 className="text-[22px] font-medium text-text-primary tracking-tight">
          交易所与 AI 模型
        </h1>
        <p className="text-[12px] text-text-muted mt-2 max-w-xl">
          所有配置存入本机 SQLite，敏感字段（secret / passphrase / api_key）经 Fernet 加密。
          DB 未配置的字段会回退到 .env，UI 上用 "source" 标签区分来源。
        </p>
      </header>

      {/* 1) Active Exchange */}
      <Card inset>
        <SectionHeader
          title="当前活跃交易所"
          subtitle="决定信号源、订单执行、持仓同步走哪家"
          right={
            exStatus && (
              <Pill tone={exStatus.active === 'okx' ? 'accent' : 'neutral'} size="md">
                {exStatus.active.toUpperCase()}
              </Pill>
            )
          }
        />
        <div className="mt-3">
          {exLoading || !exStatus ? (
            <div className="text-[12px] text-text-muted">加载中…</div>
          ) : (
            <div className="inline-flex rounded border border-terminal-border overflow-hidden">
              {(['okx', 'binance'] as const).map((ex) => {
                const active = exStatus.active === ex;
                const configured = exStatus.exchanges[ex].configured;
                return (
                  <button
                    key={ex}
                    onClick={() => !active && setActive.mutate(ex)}
                    disabled={setActive.isPending}
                    className={`px-4 py-2 text-[12px] uppercase tracking-micro transition-colors ${
                      active
                        ? 'bg-primary/15 text-primary'
                        : 'text-text-secondary hover:bg-terminal-hover hover:text-text-primary'
                    } ${ex === 'binance' ? 'border-l border-terminal-border' : ''}`}
                  >
                    {ex.toUpperCase()}
                    {!configured && (
                      <span className="ml-1 text-warn text-[10px]">未配置</span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </Card>

      {/* 2) OKX */}
      {exStatus && (
        <ExchangeForm
          exchange="okx"
          title="OKX 配置"
          status={exStatus.exchanges.okx}
          requirePassphrase
        />
      )}

      {/* 3) Binance */}
      {exStatus && (
        <ExchangeForm
          exchange="binance"
          title="Binance 配置"
          status={exStatus.exchanges.binance}
        />
      )}

      {/* 4) AI Model */}
      <AIConfigForm status={aiStatus} loading={aiLoading} />
    </div>
  );
};

// ─── Exchange config form ──────────────────────────────────────────────

interface ExchangeFormProps {
  exchange:           'okx' | 'binance';
  title:              string;
  status:             ExchangeStatus;
  requirePassphrase?: boolean;
}

const ExchangeForm: React.FC<ExchangeFormProps> = ({ exchange, title, status, requirePassphrase }) => {
  const qc = useQueryClient();
  const [editing, setEditing]       = useState(false);
  const [apiKey, setApiKey]         = useState('');
  const [apiSecret, setApiSecret]   = useState('');
  const [passphrase, setPassphrase] = useState('');
  const [testnet, setTestnet]       = useState(status.testnet ?? false);
  const [leverage, setLeverage]     = useState(String(status.leverage ?? 10));
  const [showSecret, setShowSecret] = useState(false);

  const save = useMutation({
    mutationFn: () => exchangeConfigAPI.save(exchange, {
      api_key:        apiKey,
      api_secret:     apiSecret,
      api_passphrase: passphrase,
      testnet,
      leverage:       parseInt(leverage, 10) || 10,
    }),
    onSuccess: () => {
      toast.success(`${title} 已保存`);
      setEditing(false);
      setApiKey(''); setApiSecret(''); setPassphrase('');
      qc.invalidateQueries({ queryKey: ['exchangeStatus'] });
      qc.invalidateQueries({ queryKey: ['activeExchange'] });
    },
    onError: (e: any) => toast.error(`保存失败: ${e?.message ?? e}`),
  });

  const remove = useMutation({
    mutationFn: () => exchangeConfigAPI.remove(exchange),
    onSuccess: () => {
      toast.success(`${title} 已删除（回退 env）`);
      qc.invalidateQueries({ queryKey: ['exchangeStatus'] });
    },
    onError: (e: any) => toast.error(`删除失败: ${e?.message ?? e}`),
  });

  return (
    <Card inset>
      <SectionHeader
        title={title}
        subtitle={
          status.configured
            ? `已配置 · ${status.api_key_masked} · ${status.testnet ? '测试网' : '实盘'}`
            : '未配置'
        }
        right={
          status.configured && (
            <Pill tone={status.source === 'db' ? 'bull' : 'neutral'}>
              {status.source === 'db' ? '来源: DB' : 'env'}
            </Pill>
          )
        }
      />

      {!editing ? (
        <div className="mt-4 flex items-center gap-2">
          <button onClick={() => setEditing(true)} className="btn-ghost">
            <Save size={14} strokeWidth={1.7} />
            {status.configured ? '编辑' : '配置'}
          </button>
          {status.configured && status.source === 'db' && (
            <button
              onClick={() => { if (confirm(`确定删除 ${title}？`)) remove.mutate(); }}
              disabled={remove.isPending}
              className="btn-ghost text-bear hover:text-bear"
            >
              <Trash2 size={14} strokeWidth={1.7} />
              删除（回退 env）
            </button>
          )}
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          <Field label="API Key">
            <input
              type="text" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
              placeholder={status.api_key_masked || ''}
              autoComplete="off"
            />
          </Field>
          <Field label="API Secret">
            <div className="relative">
              <input
                type={showSecret ? 'text' : 'password'} value={apiSecret}
                onChange={(e) => setApiSecret(e.target.value)} autoComplete="new-password"
                className="w-full pr-10"
              />
              <button
                type="button" onClick={() => setShowSecret((s) => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary"
              >
                {showSecret ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </Field>
          {requirePassphrase && (
            <Field label="API Passphrase（OKX 必填，创建 API 时设的字符串）">
              <input
                type="password" value={passphrase} onChange={(e) => setPassphrase(e.target.value)}
                autoComplete="new-password"
              />
            </Field>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label="杠杆 (1–125)">
              <input
                type="text" inputMode="numeric" value={leverage}
                onChange={(e) => setLeverage(e.target.value)} className="w-full"
              />
            </Field>
            <Field label="网络">
              <div className="inline-flex w-full rounded border border-terminal-border overflow-hidden">
                {[false, true].map((isTestnet) => (
                  <button
                    key={String(isTestnet)} onClick={() => setTestnet(isTestnet)}
                    className={`flex-1 px-3 py-2 text-[12px] ${
                      testnet === isTestnet
                        ? (isTestnet ? 'bg-warn/15 text-warn' : 'bg-primary/12 text-primary')
                        : 'text-text-secondary hover:bg-terminal-hover'
                    } ${isTestnet ? 'border-l border-terminal-border' : ''}`}
                  >
                    {isTestnet ? '测试网' : '实盘'}
                  </button>
                ))}
              </div>
            </Field>
          </div>

          {testnet === false && (
            <div className="flex items-center gap-2 text-[12px] text-warn">
              <AlertTriangle size={12} strokeWidth={1.6} />
              即将连接实盘 — 请确认账户已分隔好资金，杠杆不要过高
            </div>
          )}

          <div className="flex items-center gap-2 pt-2">
            <button onClick={() => save.mutate()} disabled={save.isPending || !apiKey || !apiSecret} className="btn-primary">
              <Check size={14} strokeWidth={1.7} />
              {save.isPending ? '保存中…' : '保存'}
            </button>
            <button onClick={() => setEditing(false)} className="btn-ghost">取消</button>
          </div>
        </div>
      )}
    </Card>
  );
};

// ─── AI Provider config form ───────────────────────────────────────────

const AIConfigForm: React.FC<{ status: AIStatusResp | null; loading: boolean }> = ({ status, loading }) => {
  const qc = useQueryClient();
  const [editing, setEditing]   = useState(false);
  const [provider, setProvider] = useState<string>(status?.provider || 'openai');
  const [apiKey, setApiKey]     = useState('');
  const [model, setModel]       = useState<string>(status?.model || '');
  const [enabled, setEnabled]   = useState<boolean>(status?.enabled ?? true);
  const [showKey, setShowKey]   = useState(false);

  React.useEffect(() => {
    if (status && !editing) {
      setProvider(status.provider);
      setModel(status.model);
      setEnabled(status.enabled);
    }
  }, [status, editing]);

  const save = useMutation({
    mutationFn: () => aiConfigAPI.save({ provider, api_key: apiKey, model, enabled }),
    onSuccess: () => {
      toast.success('AI 模型配置已保存');
      setEditing(false); setApiKey('');
      qc.invalidateQueries({ queryKey: ['aiConfig'] });
    },
    onError: (e: any) => toast.error(`保存失败: ${e?.message ?? e}`),
  });

  const remove = useMutation({
    mutationFn: () => aiConfigAPI.remove(),
    onSuccess: () => {
      toast.success('AI 配置已删除（回退 env）');
      qc.invalidateQueries({ queryKey: ['aiConfig'] });
    },
    onError: (e: any) => toast.error(`删除失败: ${e?.message ?? e}`),
  });

  if (loading || !status) {
    return (
      <Card inset>
        <SectionHeader title="AI 大模型" subtitle="加载中…" />
      </Card>
    );
  }

  return (
    <Card inset>
      <SectionHeader
        title="AI 大模型"
        subtitle={
          status.enabled
            ? `${status.provider} · ${status.model || '默认模型'} · ${status.api_key_masked || '无 key'}`
            : `已禁用 (provider=${status.provider})`
        }
        right={
          <Pill tone={status.source === 'db' ? 'bull' : status.source === 'env' ? 'neutral' : 'warn'}>
            来源: {status.source}
          </Pill>
        }
      />

      {!editing ? (
        <div className="mt-4 flex items-center gap-2">
          <button onClick={() => setEditing(true)} className="btn-ghost">
            <Save size={14} strokeWidth={1.7} />
            {status.source === 'db' ? '编辑' : '配置'}
          </button>
          {status.source === 'db' && (
            <button
              onClick={() => { if (confirm('确定删除 AI 配置？将回退到 env。')) remove.mutate(); }}
              disabled={remove.isPending}
              className="btn-ghost text-bear hover:text-bear"
            >
              <Trash2 size={14} strokeWidth={1.7} />
              删除（回退 env）
            </button>
          )}
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          <Field label="提供商">
            <div className="inline-flex rounded border border-terminal-border overflow-hidden flex-wrap">
              {(status.available_providers || []).map((p) => (
                <button
                  key={p} onClick={() => setProvider(p)}
                  className={`px-3 py-2 text-[12px] tracking-micro ${
                    provider === p
                      ? 'bg-primary/12 text-primary'
                      : 'text-text-secondary hover:bg-terminal-hover'
                  } border-l border-terminal-border first:border-l-0`}
                >
                  {p.toUpperCase()}
                </button>
              ))}
            </div>
          </Field>

          {provider !== 'disabled' && (
            <>
              <Field label="模型名（留空用默认）">
                <input
                  type="text" value={model} onChange={(e) => setModel(e.target.value)}
                  placeholder={
                    provider === 'openai' ? 'gpt-4o' :
                    provider === 'deepseek' ? 'deepseek-chat' :
                    provider === 'anthropic' ? 'claude-sonnet-4-5' : ''
                  }
                />
              </Field>

              <Field label="API Key">
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'} value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)} autoComplete="new-password"
                    placeholder={status.api_key_masked || ''}
                    className="w-full pr-10"
                  />
                  <button
                    type="button" onClick={() => setShowKey((s) => !s)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary"
                  >
                    {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </Field>

              <Field label="状态">
                <div className="inline-flex rounded border border-terminal-border overflow-hidden">
                  {[true, false].map((on) => (
                    <button
                      key={String(on)} onClick={() => setEnabled(on)}
                      className={`px-4 py-2 text-[12px] uppercase tracking-micro ${
                        enabled === on
                          ? on ? 'bg-bull/15 text-bull' : 'bg-bear/10 text-bear'
                          : 'text-text-secondary'
                      } ${!on ? 'border-l border-terminal-border' : ''}`}
                    >
                      {on ? '启用' : '禁用'}
                    </button>
                  ))}
                </div>
              </Field>
            </>
          )}

          <div className="flex items-center gap-2 pt-2">
            <button
              onClick={() => save.mutate()}
              disabled={save.isPending || (provider !== 'disabled' && !apiKey)}
              className="btn-primary"
            >
              <Check size={14} strokeWidth={1.7} />
              {save.isPending ? '保存中…' : '保存'}
            </button>
            <button onClick={() => setEditing(false)} className="btn-ghost">取消</button>
          </div>
        </div>
      )}
    </Card>
  );
};

// ─── 小工具 ─────────────────────────────────────────────────────────────

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <label className="label-sm block mb-1.5">{label}</label>
    {children}
  </div>
);

export default SettingsPage;
