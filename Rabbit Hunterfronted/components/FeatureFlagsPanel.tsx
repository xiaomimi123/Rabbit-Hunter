/**
 * 功能开关管理面板（仅开发环境）
 * 用于管理和测试功能开关
 */

import React, { useState, useEffect } from 'react';
import { Settings, ToggleLeft, ToggleRight, AlertCircle, CheckCircle, X } from 'lucide-react';
import { getAllFeatureFlags, setFeatureFlag, isFeatureEnabled, FeatureFlag } from '../services/featureFlags';

export const FeatureFlagsPanel: React.FC = () => {
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const [isDev, setIsDev] = useState(false);
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    setIsDev(import.meta.env.VITE_ENVIRONMENT === 'development');
    setFlags(getAllFeatureFlags());
  }, []);

  const handleToggle = (flagName: string, enabled: boolean) => {
    if (!isDev) return;
    
    const flag = flags.find(f => f.name === flagName);
    if (flag) {
      setFeatureFlag(flagName, enabled, flag.rolloutPercentage);
      setFlags([...getAllFeatureFlags()]);
    }
  };

  const handleRolloutChange = (flagName: string, percentage: number) => {
    if (!isDev) return;
    
    const flag = flags.find(f => f.name === flagName);
    if (flag) {
      setFeatureFlag(flagName, flag.enabled, percentage);
      setFlags([...getAllFeatureFlags()]);
    }
  };

  if (!isDev || !isVisible) {
    return null; // 非开发环境不显示，或已关闭
  }

  return (
    <div className="fixed bottom-4 right-4 w-96 glass rounded-2xl p-6 border border-white/10 z-50 max-h-[80vh] overflow-y-auto shadow-2xl">
      <div className="flex items-center gap-2 mb-4">
        <Settings size={18} className="text-[#7B61FF]" />
        <h3 className="text-sm font-bold text-white">功能开关</h3>
        <span className="ml-auto text-[10px] font-mono text-white/40">DEV ONLY</span>
        <button
          onClick={() => setIsVisible(false)}
          className="ml-2 p-1 hover:bg-white/10 rounded transition-colors"
          title="关闭面板"
        >
          <X size={16} className="text-white/60 hover:text-white" />
        </button>
      </div>
      
      <div className="mb-4 p-3 bg-[#7B61FF]/10 border border-[#7B61FF]/20 rounded-lg">
        <p className="text-[10px] font-mono text-white/60 leading-relaxed">
          <strong className="text-[#7B61FF]">灰度发布</strong>：逐步向用户推出新功能，降低风险。
          <br />
          例如：50% 表示只有 50% 的用户能看到此功能。
        </p>
      </div>

      <div className="space-y-3">
        {flags.map(flag => {
          const enabled = isFeatureEnabled(flag.name);
          
          return (
            <div key={flag.name} className="bg-black/40 rounded-lg p-3 border border-white/5">
              <div className="flex items-center justify-between mb-2">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-bold text-white">{flag.name}</span>
                    {enabled ? (
                      <CheckCircle size={12} className="text-[#00FF9D]" />
                    ) : (
                      <AlertCircle size={12} className="text-white/40" />
                    )}
                  </div>
                  {flag.description && (
                    <p className="text-[10px] text-white/40 mt-1">{flag.description}</p>
                  )}
                </div>
                <button
                  onClick={() => handleToggle(flag.name, !flag.enabled)}
                  className="ml-2"
                >
                  {flag.enabled ? (
                    <ToggleRight size={20} className="text-[#00FF9D]" />
                  ) : (
                    <ToggleLeft size={20} className="text-white/40" />
                  )}
                </button>
              </div>
              
              {flag.enabled && (
                <div className="mt-2 pt-2 border-t border-white/5">
                  <label className="text-[10px] font-mono text-white/40 block mb-1">
                    灰度发布: {flag.rolloutPercentage}%
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="10"
                    value={flag.rolloutPercentage}
                    onChange={(e) => handleRolloutChange(flag.name, Number(e.target.value))}
                    className="w-full"
                  />
                  <div className="flex justify-between text-[9px] text-white/30 mt-1">
                    <span>0%</span>
                    <span>50%</span>
                    <span>100%</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default FeatureFlagsPanel;

