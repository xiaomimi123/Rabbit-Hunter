/**
 * V4.5 策略配置页面
 * 
 * 功能：
 * 1. 显示当前策略路由配置（SNIPER, VULTURE, SNIFFER）
 * 2. 编辑策略参数（门槛、持仓限制等）
 * 3. 保存配置到后端
 */

import React, { useState, useEffect } from 'react';
import { Save, RefreshCw, AlertCircle, CheckCircle, Zap, Crosshair, Skull, Search, Eye } from 'lucide-react';
import { toast } from './Toast';

interface StrategyConfig {
  SNIPER: {
    min_structure_score: number;
    min_confidence: number;
    position_size: number;
    stop_loss_atr_multiplier: number;
  };
  SNIFFER: {
    enabled: boolean;
    min_oi_growth: number;
    min_volume_spike: number;
    min_whale_activity: number;
    position_size: number;
    stop_loss_atr_multiplier: number;
  };
  VULTURE: {
    min_oi_drop: number;
    min_score_boost: number;
    min_score_boost_threshold: number;
    position_size: number;
    stop_loss_atr_multiplier: number;
    confidence_high_oi_drop: number;
    confidence_normal: number;
    high_oi_drop_threshold: number;
  };
  WHALE_ACTIVITY_WEIGHTS: {
    oi_score: number;
    volume_score: number;
    funding_score: number;
    ls_score: number;
  };
  WHALE_ACTIVITY_THRESHOLDS: {
    oi_max: number;
    volume_max: number;
    funding_max: number;
    ls_max: number;
  };
  VULTURE_SCORE: {
    oi_contribution_max: number;
    structure_weight: number;
    oi_weight: number;
  };
}

const DEFAULT_CONFIG: StrategyConfig = {
  SNIPER: {
    min_structure_score: 60.0,
    min_confidence: 0.8,
    position_size: 1.0,
    stop_loss_atr_multiplier: 2.0,
  },
  SNIFFER: {
    enabled: false,
    min_oi_growth: 0.05,
    min_volume_spike: 3.0,
    min_whale_activity: 0.7,
    position_size: 0.5,
    stop_loss_atr_multiplier: 3.0,
  },
  VULTURE: {
    min_oi_drop: -0.03,
    min_score_boost: 60.0,
    min_score_boost_threshold: 50.0,
    position_size: 0.5,
    stop_loss_atr_multiplier: 1.5,
    confidence_high_oi_drop: 0.7,
    confidence_normal: 0.6,
    high_oi_drop_threshold: 0.10,
  },
  WHALE_ACTIVITY_WEIGHTS: {
    oi_score: 0.4,
    volume_score: 0.3,
    funding_score: 0.2,
    ls_score: 0.1,
  },
  WHALE_ACTIVITY_THRESHOLDS: {
    oi_max: 0.10,
    volume_max: 3.0,
    funding_max: 0.001,
    ls_max: 2.0,
  },
  VULTURE_SCORE: {
    oi_contribution_max: 0.10,
    structure_weight: 0.5,
    oi_weight: 0.5,
  },
};

const StrategyConfig: React.FC = () => {
  const [config, setConfig] = useState<StrategyConfig>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // TODO: 调用 API 获取配置
      // const response = await strategyConfigAPI.getConfig();
      // setConfig(response.data || DEFAULT_CONFIG);
      
      // 临时：使用默认配置
      setConfig(DEFAULT_CONFIG);
    } catch (err) {
      console.error('Failed to load strategy config:', err);
      setError(err instanceof Error ? err.message : '加载配置失败');
      toast.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      
      // TODO: 调用 API 保存配置
      // await strategyConfigAPI.saveConfig(config);
      
      toast.success('策略配置已保存');
    } catch (err) {
      console.error('Failed to save strategy config:', err);
      setError(err instanceof Error ? err.message : '保存配置失败');
      toast.error('保存配置失败');
    } finally {
      setSaving(false);
    }
  };

  const updateConfig = (path: string[], value: any) => {
    setConfig((prev) => {
      const newConfig = { ...prev };
      let current: any = newConfig;
      
      for (let i = 0; i < path.length - 1; i++) {
        current = current[path[i]] = { ...current[path[i]] };
      }
      
      current[path[path.length - 1]] = value;
      return newConfig;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-white/40 font-mono">加载中...</div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col gap-6 min-h-0 overflow-hidden">
      {/* 标题栏 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white mb-1">策略配置</h1>
          <p className="text-xs text-white/40 font-mono">
            V4.5 策略路由动态配置 | 修改后需要重启采集器生效
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadConfig}
            className="px-4 py-2 bg-white/5 text-white/80 border border-white/10 rounded-lg text-xs font-mono hover:bg-white/10 transition-colors flex items-center gap-2"
          >
            <RefreshCw size={14} />
            刷新
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 bg-[#7B61FF]/20 text-[#7B61FF] border border-[#7B61FF]/30 rounded-lg text-xs font-mono hover:bg-[#7B61FF]/30 transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            {saving ? (
              <>
                <RefreshCw size={14} className="animate-spin" />
                保存中...
              </>
            ) : (
              <>
                <Save size={14} />
                保存配置
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm flex items-center gap-2">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {/* 配置内容 */}
      <div className="flex-1 overflow-y-auto space-y-6">
        {/* SNIPER 策略 */}
        <ConfigSection
          title="SNIPER 策略（P3A 主升浪）"
          icon={Crosshair}
          iconColor="text-emerald-400"
          description="狙击手：只有确认突破（P3A）才开多"
        >
          <ConfigField
            label="最低结构分"
            value={config.SNIPER.min_structure_score}
            onChange={(v) => updateConfig(['SNIPER', 'min_structure_score'], v)}
            type="number"
            step="1"
            min="0"
            max="100"
            help="结构分必须 >= 此值才能触发 SNIPER"
          />
          <ConfigField
            label="最低置信度"
            value={config.SNIPER.min_confidence}
            onChange={(v) => updateConfig(['SNIPER', 'min_confidence'], v)}
            type="number"
            step="0.1"
            min="0"
            max="1"
            help="策略置信度（0-1）"
          />
          <ConfigField
            label="仓位大小"
            value={config.SNIPER.position_size}
            onChange={(v) => updateConfig(['SNIPER', 'position_size'], v)}
            type="number"
            step="0.1"
            min="0.1"
            max="2.0"
            help="标准仓位倍数"
          />
          <ConfigField
            label="止损 ATR 倍数"
            value={config.SNIPER.stop_loss_atr_multiplier}
            onChange={(v) => updateConfig(['SNIPER', 'stop_loss_atr_multiplier'], v)}
            type="number"
            step="0.1"
            min="1.0"
            max="5.0"
            help="标准止损距离（ATR 倍数）"
          />
        </ConfigSection>

        {/* SNIFFER 策略 */}
        <ConfigSection
          title="SNIFFER 策略（P2 观察者）"
          icon={Search}
          iconColor="text-sky-400"
          description="观察者：V4.5 已禁用交易，只保留观察功能"
        >
          <ConfigField
            label="启用交易"
            value={config.SNIFFER.enabled}
            onChange={(v) => updateConfig(['SNIFFER', 'enabled'], v)}
            type="checkbox"
            help="V4.5 默认禁用，仅观察"
          />
          <ConfigField
            label="OI 增长阈值"
            value={config.SNIFFER.min_oi_growth}
            onChange={(v) => updateConfig(['SNIFFER', 'min_oi_growth'], v)}
            type="number"
            step="0.01"
            min="0"
            max="0.5"
            help="OI 增长 > 此值才触发观察（小数形式，0.05 = 5%）"
          />
          <ConfigField
            label="爆量阈值"
            value={config.SNIFFER.min_volume_spike}
            onChange={(v) => updateConfig(['SNIFFER', 'min_volume_spike'], v)}
            type="number"
            step="0.5"
            min="1.0"
            max="10.0"
            help="成交量倍数 > 此值才触发观察"
          />
          <ConfigField
            label="庄家活动强度阈值"
            value={config.SNIFFER.min_whale_activity}
            onChange={(v) => updateConfig(['SNIFFER', 'min_whale_activity'], v)}
            type="number"
            step="0.1"
            min="0"
            max="1"
            help="庄家活动强度 > 此值才触发观察（0-1）"
          />
        </ConfigSection>

        {/* VULTURE 策略 */}
        <ConfigSection
          title="VULTURE 策略（P3B/P4 做空）"
          icon={Skull}
          iconColor="text-rose-400"
          description="秃鹫：做空是当前的主力，给它足够的空间"
        >
          <ConfigField
            label="OI 下降阈值"
            value={config.VULTURE.min_oi_drop}
            onChange={(v) => updateConfig(['VULTURE', 'min_oi_drop'], v)}
            type="number"
            step="0.01"
            min="-0.5"
            max="0"
            help="OI 下降 < 此值才触发（负数，-0.03 = -3%）"
          />
          <ConfigField
            label="分数提升阈值"
            value={config.VULTURE.min_score_boost}
            onChange={(v) => updateConfig(['VULTURE', 'min_score_boost'], v)}
            type="number"
            step="1"
            min="50"
            max="100"
            help="如果分数接近此值，自动提升到 60"
          />
          <ConfigField
            label="触发提升的阈值"
            value={config.VULTURE.min_score_boost_threshold}
            onChange={(v) => updateConfig(['VULTURE', 'min_score_boost_threshold'], v)}
            type="number"
            step="1"
            min="40"
            max="70"
            help="分数 > 此值才触发提升"
          />
          <ConfigField
            label="仓位大小"
            value={config.VULTURE.position_size}
            onChange={(v) => updateConfig(['VULTURE', 'position_size'], v)}
            type="number"
            step="0.1"
            min="0.1"
            max="1.0"
            help="轻仓（做空风险大）"
          />
          <ConfigField
            label="止损 ATR 倍数"
            value={config.VULTURE.stop_loss_atr_multiplier}
            onChange={(v) => updateConfig(['VULTURE', 'stop_loss_atr_multiplier'], v)}
            type="number"
            step="0.1"
            min="1.0"
            max="3.0"
            help="极窄止损，破前高即跑"
          />
          <ConfigField
            label="高 OI 下降置信度"
            value={config.VULTURE.confidence_high_oi_drop}
            onChange={(v) => updateConfig(['VULTURE', 'confidence_high_oi_drop'], v)}
            type="number"
            step="0.1"
            min="0"
            max="1"
            help="OI 下降 > 10% 时的置信度"
          />
          <ConfigField
            label="正常置信度"
            value={config.VULTURE.confidence_normal}
            onChange={(v) => updateConfig(['VULTURE', 'confidence_normal'], v)}
            type="number"
            step="0.1"
            min="0"
            max="1"
            help="正常情况下的置信度"
          />
        </ConfigSection>

        {/* 庄家活动强度配置 */}
        <ConfigSection
          title="庄家活动强度计算"
          icon={Zap}
          iconColor="text-yellow-400"
          description="用于 SNIFFER 观察和策略路由的庄家活动强度计算"
        >
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h4 className="text-sm font-bold text-white/80 mb-3">权重配置</h4>
              <div className="space-y-3">
                <ConfigField
                  label="OI 变化权重"
                  value={config.WHALE_ACTIVITY_WEIGHTS.oi_score}
                  onChange={(v) => updateConfig(['WHALE_ACTIVITY_WEIGHTS', 'oi_score'], v)}
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                />
                <ConfigField
                  label="成交量权重"
                  value={config.WHALE_ACTIVITY_WEIGHTS.volume_score}
                  onChange={(v) => updateConfig(['WHALE_ACTIVITY_WEIGHTS', 'volume_score'], v)}
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                />
                <ConfigField
                  label="资金费率权重"
                  value={config.WHALE_ACTIVITY_WEIGHTS.funding_score}
                  onChange={(v) => updateConfig(['WHALE_ACTIVITY_WEIGHTS', 'funding_score'], v)}
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                />
                <ConfigField
                  label="多空比权重"
                  value={config.WHALE_ACTIVITY_WEIGHTS.ls_score}
                  onChange={(v) => updateConfig(['WHALE_ACTIVITY_WEIGHTS', 'ls_score'], v)}
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                />
              </div>
            </div>
            <div>
              <h4 className="text-sm font-bold text-white/80 mb-3">阈值配置</h4>
              <div className="space-y-3">
                <ConfigField
                  label="OI 上升最大值"
                  value={config.WHALE_ACTIVITY_THRESHOLDS.oi_max}
                  onChange={(v) => updateConfig(['WHALE_ACTIVITY_THRESHOLDS', 'oi_max'], v)}
                  type="number"
                  step="0.01"
                  min="0"
                  max="0.5"
                />
                <ConfigField
                  label="爆量最大值"
                  value={config.WHALE_ACTIVITY_THRESHOLDS.volume_max}
                  onChange={(v) => updateConfig(['WHALE_ACTIVITY_THRESHOLDS', 'volume_max'], v)}
                  type="number"
                  step="0.5"
                  min="1"
                  max="10"
                />
                <ConfigField
                  label="资金费率最大值"
                  value={config.WHALE_ACTIVITY_THRESHOLDS.funding_max}
                  onChange={(v) => updateConfig(['WHALE_ACTIVITY_THRESHOLDS', 'funding_max'], v)}
                  type="number"
                  step="0.0001"
                  min="0"
                  max="0.01"
                />
                <ConfigField
                  label="多空比最大值"
                  value={config.WHALE_ACTIVITY_THRESHOLDS.ls_max}
                  onChange={(v) => updateConfig(['WHALE_ACTIVITY_THRESHOLDS', 'ls_max'], v)}
                  type="number"
                  step="0.1"
                  min="1"
                  max="5"
                />
              </div>
            </div>
          </div>
        </ConfigSection>

        {/* Vulture 分数计算配置 */}
        <ConfigSection
          title="Vulture 分数计算"
          icon={Zap}
          iconColor="text-rose-400"
          description="VULTURE 策略的分数计算参数"
        >
          <ConfigField
            label="OI 贡献最大值"
            value={config.VULTURE_SCORE.oi_contribution_max}
            onChange={(v) => updateConfig(['VULTURE_SCORE', 'oi_contribution_max'], v)}
            type="number"
            step="0.01"
            min="0.05"
            max="0.5"
            help="OI 下降此值 = 100分（小数形式，0.10 = 10%）"
          />
          <ConfigField
            label="结构分数权重"
            value={config.VULTURE_SCORE.structure_weight}
            onChange={(v) => updateConfig(['VULTURE_SCORE', 'structure_weight'], v)}
            type="number"
            step="0.1"
            min="0"
            max="1"
            help="结构分数在综合分数中的权重"
          />
          <ConfigField
            label="OI 贡献权重"
            value={config.VULTURE_SCORE.oi_weight}
            onChange={(v) => updateConfig(['VULTURE_SCORE', 'oi_weight'], v)}
            type="number"
            step="0.1"
            min="0"
            max="1"
            help="OI 贡献在综合分数中的权重"
          />
        </ConfigSection>
      </div>
    </div>
  );
};

// 配置区块组件
interface ConfigSectionProps {
  title: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  iconColor: string;
  description: string;
  children: React.ReactNode;
}

const ConfigSection: React.FC<ConfigSectionProps> = ({ title, icon: Icon, iconColor, description, children }) => {
  return (
    <div className="glass rounded-xl border border-white/10 p-6">
      <div className="flex items-center gap-3 mb-4">
        <Icon size={20} className={iconColor} />
        <div>
          <h3 className="text-lg font-bold text-white">{title}</h3>
          <p className="text-xs text-white/40 font-mono">{description}</p>
        </div>
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  );
};

// 配置字段组件
interface ConfigFieldProps {
  label: string;
  value: any;
  onChange: (value: any) => void;
  type: 'number' | 'checkbox';
  step?: number;
  min?: number;
  max?: number;
  help?: string;
}

const ConfigField: React.FC<ConfigFieldProps> = ({ label, value, onChange, type, step, min, max, help }) => {
  if (type === 'checkbox') {
    return (
      <div className="flex items-center justify-between">
        <div>
          <label className="text-sm font-medium text-white/80">{label}</label>
          {help && <p className="text-xs text-white/40 mt-1">{help}</p>}
        </div>
        <input
          type="checkbox"
          checked={value}
          onChange={(e) => onChange(e.target.checked)}
          className="w-5 h-5 rounded border-white/20 bg-white/5 checked:bg-[#7B61FF] checked:border-[#7B61FF]"
        />
      </div>
    );
  }

  return (
    <div>
      <label className="text-sm font-medium text-white/80 mb-1 block">{label}</label>
      {help && <p className="text-xs text-white/40 mb-2">{help}</p>}
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        step={step}
        min={min}
        max={max}
        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm font-mono focus:outline-none focus:border-[#7B61FF]/50 focus:ring-1 focus:ring-[#7B61FF]/20"
      />
    </div>
  );
};

export default StrategyConfig;

