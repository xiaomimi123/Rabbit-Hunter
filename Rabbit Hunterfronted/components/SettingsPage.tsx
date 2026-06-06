/**
 * 设置页面 - 币安 API 配置
 * 允许用户在前端配置币安 API Key 和 Secret
 */

import React, { useEffect, useState } from 'react';
import { Save, Trash2, Eye, EyeOff, CheckCircle, XCircle, AlertTriangle, Key, Shield } from 'lucide-react';
import { binanceConfigAPI } from '../services/api';

interface BinanceConfig {
  api_key: string;
  api_secret: string;
  testnet: boolean;
  leverage?: number;  // V4.5: 杠杆倍数（1-125）
}

interface ConfigStatus {
  configured: boolean;
  testnet: boolean;
  api_key_masked?: string;  // API Key 的部分信息（前5位+后5位）
  leverage?: number;  // 杠杆倍数
}

export const SettingsPage: React.FC = () => {
  const [config, setConfig] = useState<BinanceConfig>({
    api_key: '',
    api_secret: '',
    testnet: false,
    leverage: 10,
  });
  const [showSecret, setShowSecret] = useState(false);
  const [status, setStatus] = useState<ConfigStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 加载当前配置状态
  useEffect(() => {
    loadConfigStatus();
  }, []);

  const loadConfigStatus = async () => {
    try {
      setLoading(true);
      const data = await binanceConfigAPI.getStatus();
      setStatus(data);
      
      // 如果已配置，显示部分信息（不显示完整 Secret）
      if (data.configured) {
        setConfig(prev => ({
          ...prev,
          api_key: data.api_key_masked || '', // 显示部分 API Key（前5位+后5位）
          api_secret: '', // 不显示已保存的 Secret（安全考虑）
          testnet: data.testnet,
          leverage: data.leverage || 10,
        }));
      }
    } catch (err) {
      console.error('Failed to load config:', err);
      setError(err instanceof Error ? err.message : '加载配置状态失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!config.api_key || !config.api_secret) {
      setError('请填写 API Key 和 Secret');
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      const data = await binanceConfigAPI.save({
        api_key: config.api_key,
        api_secret: config.api_secret,
        testnet: config.testnet,
        leverage: config.leverage || 10,  // V4.5: 包含杠杆设置
      });

      setSuccess(data.message || '配置已保存并验证成功');
      setStatus({ configured: true, testnet: config.testnet });
      
      // 清空输入框（安全考虑）
      setConfig({
        api_key: '',
        api_secret: '',
        testnet: config.testnet,
        leverage: config.leverage || 10,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存配置失败');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('确定要删除币安 API 配置吗？删除后需要重新配置才能使用交易功能。')) {
      return;
    }

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      await binanceConfigAPI.delete();

      setSuccess('配置已删除');
      setStatus({ configured: false, testnet: false });
      setConfig({
        api_key: '',
        api_secret: '',
        testnet: false,
        leverage: 10,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除配置失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6">
        {/* 页面标题 */}
        <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Key size={28} className="text-[#7B61FF]" />
            系统设置
          </h1>
          <p className="text-sm text-white/40 mt-2">配置币安 API 以启用交易功能</p>
        </div>
      </div>

      {/* 币安 API 配置卡片 */}
      <div className="glass rounded-2xl p-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Shield size={20} className="text-[#00FF9D]" />
              币安 API 配置
            </h2>
            <p className="text-xs text-white/40 mt-1">
              配置币安 API Key 和 Secret 以启用自动交易功能
            </p>
          </div>
          
          {status && (
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${
              status.configured 
                ? 'bg-[#00FF9D]/10 border border-[#00FF9D]/20' 
                : 'bg-white/5 border border-white/10'
            }`}>
              {status.configured ? (
                <>
                  <CheckCircle size={14} className="text-[#00FF9D]" />
                  <span className="text-xs font-mono text-[#00FF9D]">已配置</span>
                </>
              ) : (
                <>
                  <XCircle size={14} className="text-white/40" />
                  <span className="text-xs font-mono text-white/40">未配置</span>
                </>
              )}
            </div>
          )}
        </div>

        {/* 配置状态提示 */}
        {status?.configured && (
          <div className="bg-[#00FF9D]/5 border border-[#00FF9D]/20 rounded-lg p-4 flex items-start gap-3">
            <CheckCircle size={18} className="text-[#00FF9D] mt-0.5" />
            <div className="flex-1">
              <p className="text-sm text-[#00FF9D] font-medium">API 配置已生效</p>
              <p className="text-xs text-white/40 mt-1 inline-flex items-center gap-1.5">
                {status.testnet
                  ? '当前使用测试网模式'
                  : (
                    <>
                      <AlertTriangle size={11} strokeWidth={1.6} className="text-warn" />
                      <span>当前使用实盘模式 — 注意风险</span>
                    </>
                  )}
              </p>
            </div>
          </div>
        )}

        {/* 错误提示 */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 flex items-start gap-3">
            <AlertTriangle size={18} className="text-red-500 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm text-red-500 font-medium">配置失败</p>
              <p className="text-xs text-white/60 mt-1 whitespace-pre-line">{error}</p>
              {(error.includes("Invalid Api-Key") || error.includes("API Key 无效") || error.includes("-2008")) ? (
                <div className="mt-3 p-3 bg-yellow-400/10 border border-yellow-400/30 rounded text-xs text-yellow-400">
                  <p className="font-medium mb-2">📝 如何获取正确的 API Key：</p>
                  <ul className="list-disc list-inside space-y-1 text-yellow-300/80">
                    <li>
                      <strong>测试网</strong>：访问{" "}
                      <a
                        href="https://testnet.binancefuture.com/"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline hover:text-yellow-400"
                      >
                        https://testnet.binancefuture.com/
                      </a>{" "}
                      创建测试网 API Key
                    </li>
                    <li>
                      <strong>实盘</strong>：访问{" "}
                      <a
                        href="https://www.binance.com/"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline hover:text-yellow-400"
                      >
                        https://www.binance.com/
                      </a>{" "}
                      创建实盘 API Key
                    </li>
                    <li className="mt-2 inline-flex items-start gap-1.5">
                      <AlertTriangle size={11} strokeWidth={1.6} className="text-warn mt-[3px] shrink-0" />
                      <span><strong>重要</strong>：测试网和实盘的 API Key 不能混用</span>
                    </li>
                  </ul>
                </div>
              ) : null}
            </div>
          </div>
        )}

        {/* 成功提示 */}
        {success && (
          <div className="bg-[#00FF9D]/10 border border-[#00FF9D]/20 rounded-lg p-4 flex items-start gap-3">
            <CheckCircle size={18} className="text-[#00FF9D] mt-0.5" />
            <div className="flex-1">
              <p className="text-sm text-[#00FF9D] font-medium">操作成功</p>
              <p className="text-xs text-white/60 mt-1">{success}</p>
            </div>
          </div>
        )}

        {/* 配置表单 */}
        <div className="space-y-4">
          {/* API Key */}
          <div>
            <label className="block text-xs font-mono text-white/60 uppercase tracking-wider mb-2">
              API Key
              {status?.configured && status?.api_key_masked && (
                <span className="ml-2 text-xs text-white/50 normal-case">
                  (已配置: {status.api_key_masked})
                </span>
              )}
            </label>
            <input
              type="text"
              value={config.api_key}
              onChange={(e) => setConfig(prev => ({ ...prev, api_key: e.target.value }))}
              placeholder={status?.configured && status?.api_key_masked 
                ? `当前: ${status.api_key_masked} (输入新值以更新)` 
                : "输入币安 API Key"}
              className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-[#7B61FF] transition-colors font-mono text-sm"
              disabled={loading || saving}
            />
            {status?.configured && status?.api_key_masked && (
              <p className="mt-1 text-xs text-white/50">
                💡 已保存的 API Key: <span className="font-mono">{status.api_key_masked}</span>（输入新值可更新配置）
              </p>
            )}
          </div>

          {/* API Secret */}
          <div>
            <label className="block text-xs font-mono text-white/60 uppercase tracking-wider mb-2">
              API Secret
            </label>
            <div className="relative">
              <input
                type={showSecret ? "text" : "password"}
                value={config.api_secret}
                onChange={(e) => setConfig(prev => ({ ...prev, api_secret: e.target.value }))}
                placeholder="输入币安 API Secret"
                className="w-full px-4 py-3 pr-12 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-[#7B61FF] transition-colors font-mono text-sm"
                disabled={loading || saving}
              />
              <button
                type="button"
                onClick={() => setShowSecret(!showSecret)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/60 transition-colors"
                disabled={loading || saving}
              >
                {showSecret ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            <p className="text-[10px] text-white/30 mt-1.5 inline-flex items-center gap-1">
              <AlertTriangle size={10} strokeWidth={1.6} className="text-warn" />
              <span>Secret 只显示一次，请妥善保管</span>
            </p>
          </div>

          {/* 杠杆设置 - V4.5 */}
          <div>
            <label className="block text-xs font-mono text-white/60 uppercase tracking-wider mb-2">
              杠杆倍数 (1-125)
            </label>
            <input
              type="number"
              min="1"
              max="125"
              value={config.leverage || 10}
              onChange={(e) => {
                const value = parseInt(e.target.value) || 10;
                const clamped = Math.max(1, Math.min(125, value));
                setConfig(prev => ({ ...prev, leverage: clamped }));
              }}
              placeholder="10"
              className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-[#7B61FF] transition-colors font-mono text-sm"
              disabled={loading || saving}
            />
            <p className="text-[10px] text-white/30 mt-1.5">
              默认 10x，建议根据风险承受能力设置（1-125）
            </p>
          </div>

          {/* 测试网开关 */}
          <div className="flex items-center justify-between p-4 bg-white/5 rounded-lg border border-white/10">
            <div>
              <label className="text-sm font-medium text-white">测试网模式</label>
              <p className="text-xs text-white/40 mt-1">
                启用后使用币安测试网，不会产生真实交易
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={config.testnet}
                onChange={(e) => setConfig(prev => ({ ...prev, testnet: e.target.checked }))}
                className="sr-only peer"
                disabled={loading || saving}
              />
              <div className="w-11 h-6 bg-white/10 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-[#7B61FF] rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#00FF9D]" />
            </label>
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center gap-3 pt-4 border-t border-white/10">
          <button
            onClick={handleSave}
            disabled={loading || saving || !config.api_key || !config.api_secret}
            className="flex items-center gap-2 px-6 py-3 bg-[#7B61FF] hover:bg-[#7B61FF]/80 disabled:bg-white/10 disabled:text-white/30 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
          >
            <Save size={16} />
            {saving ? '保存中...' : '保存配置'}
          </button>

          {status?.configured && (
            <button
              onClick={handleDelete}
              disabled={loading || saving}
              className="flex items-center gap-2 px-6 py-3 bg-red-500/10 hover:bg-red-500/20 disabled:bg-white/5 disabled:text-white/30 disabled:cursor-not-allowed text-red-500 border border-red-500/20 font-medium rounded-lg transition-colors"
            >
              <Trash2 size={16} />
              删除配置
            </button>
          )}

          <button
            onClick={loadConfigStatus}
            disabled={loading || saving}
            className="ml-auto px-4 py-2 text-white/60 hover:text-white text-sm font-mono disabled:opacity-50"
          >
            {loading ? '加载中...' : '刷新状态'}
          </button>
        </div>

        {/* 安全提示 */}
        <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4 space-y-2">
          <div className="flex items-start gap-2">
            <AlertTriangle size={16} className="text-yellow-500 mt-0.5" />
            <div className="flex-1">
              <p className="text-xs font-medium text-yellow-500">安全提示</p>
              <ul className="text-[10px] text-white/50 mt-1.5 space-y-1 list-disc list-inside">
                <li>API Secret 只会显示一次，请妥善保管</li>
                <li>建议使用只读权限的 API Key（如果只采集数据）</li>
                <li>生产环境建议启用 IP 白名单</li>
                <li>配置会加密存储在数据库中</li>
              </ul>
            </div>
          </div>
        </div>

        {/* 帮助链接 */}
        <div className="text-center pt-4 border-t border-white/10">
          <a
            href="https://www.binance.com/zh-CN/my/settings/api-management"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-[#7B61FF] hover:text-[#7B61FF]/80 font-mono"
          >
            如何申请币安 API Key？ →
          </a>
        </div>
      </div>
      </div>
    </div>
  );
};

export default SettingsPage;


