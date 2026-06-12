import React, { useState } from 'react';
import { useV5Settings } from '../../hooks/api/useV5Settings';
import { Card } from '../primitives/Card';
import { LoadingSkeleton } from '../primitives/LoadingSkeleton';
import { Modal } from '../primitives/Modal';
import { Badge } from '../primitives/Badge';

export function V5SettingsPage() {
  const { query, patch } = useV5Settings();
  const [confirmLive, setConfirmLive] = useState(false);
  const [deepseekKey, setDeepseekKey] = useState('');
  const [openaiKey, setOpenaiKey] = useState('');

  if (query.isLoading) return <LoadingSkeleton rows={6} />;
  const s = query.data;
  if (!s) return <div className="text-white/40">无数据</div>;

  return (
    <div className="space-y-4">
      <Card title="交易所">
        <div className="text-sm">当前: <Badge variant="info">{s.exchange}</Badge></div>
      </Card>

      <Card title="AI 配置">
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-white/50 mb-1">DeepSeek API Key</div>
              <input
                type="password"
                placeholder={s.deepseek_api_key_masked || '未配置'}
                value={deepseekKey}
                onChange={(e) => setDeepseekKey(e.target.value)}
                className="w-full rounded-sm border border-white/10 bg-bg-base px-2 py-1 font-mono text-white"
              />
            </div>
            <div>
              <div className="text-xs text-white/50 mb-1">OpenAI API Key</div>
              <input
                type="password"
                placeholder={s.openai_api_key_masked || '未配置'}
                value={openaiKey}
                onChange={(e) => setOpenaiKey(e.target.value)}
                className="w-full rounded-sm border border-white/10 bg-bg-base px-2 py-1 font-mono text-white"
              />
            </div>
          </div>
          <div className="text-xs text-white/50">
            活跃: <Badge variant="info">{s.active_ai_provider ?? '无'}</Badge> · 模型 {s.active_chat_model}
          </div>
          <button
            type="button"
            disabled={patch.isPending || (!deepseekKey && !openaiKey)}
            onClick={() => patch.mutate({
              ...(deepseekKey ? { deepseek_api_key: deepseekKey } : {}),
              ...(openaiKey ? { openai_api_key: openaiKey } : {}),
            })}
            className="rounded-sm border border-accent-info/40 px-3 py-1 text-xs text-accent-info disabled:opacity-40"
          >
            保存 AI 配置
          </button>
        </div>
      </Card>

      <Card title="系统模式">
        <div className="flex items-center gap-3">
          <Badge variant={s.system_mode === 'LIVE' ? 'short' : 'info'}>
            {s.system_mode === 'LIVE' ? '🔴 LIVE' : '🟡 SHADOW'}
          </Badge>
          <button
            type="button"
            onClick={() => {
              if (s.system_mode === 'SHADOW') setConfirmLive(true);
              else patch.mutate({ system_mode: 'SHADOW' });
            }}
            className="rounded-sm border border-white/15 px-3 py-1 text-xs"
          >
            切换到 {s.system_mode === 'SHADOW' ? 'LIVE' : 'SHADOW'}
          </button>
        </div>
      </Card>

      <Card title="Fail-closed 旋钮">
        <div className="space-y-2 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={s.ai_fail_open} onChange={(e) => patch.mutate({ ai_fail_open: e.target.checked })} />
            <span>AI 不可用时 fail-open (LIVE 默认 fail-closed,勾选 = 允许跳过 AI)</span>
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={s.sl_tp_fail_open} onChange={(e) => patch.mutate({ sl_tp_fail_open: e.target.checked })} />
            <span>SL/TP 异常 fail-open</span>
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={s.enable_auto_trading} onChange={(e) => patch.mutate({ enable_auto_trading: e.target.checked })} />
            <span>启用自动交易</span>
          </label>
        </div>
      </Card>

      <Modal
        open={confirmLive}
        onClose={() => setConfirmLive(false)}
        title="切换到 LIVE 模式"
      >
        <div className="space-y-3 text-sm">
          <div className="text-accent-warn">
            ⚠️ LIVE 模式将使用真实资金开仓。请确认账户余额和当前活仓状态。
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setConfirmLive(false)} className="rounded-sm border border-white/15 px-3 py-1 text-xs">取消</button>
            <button
              type="button"
              onClick={() => { patch.mutate({ system_mode: 'LIVE' }); setConfirmLive(false); }}
              className="rounded-sm border border-accent-short/40 bg-accent-short/10 px-3 py-1 text-xs text-accent-short"
            >
              确认切到 LIVE
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
