/**
 * V4.5 权重历史组件
 * 显示 AI 权重调整历史、性能指标对比、机会密度分数
 * 
 * V4.5 新功能：
 * - 自动应用状态提示
 * - 区分自动应用和手动应用
 * - 自适应布局优化
 */

import React, { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Clock, CheckCircle, XCircle, BrainCircuit, Activity, Zap, Play, Loader2, Info, Sparkles, User } from 'lucide-react';
import { weightsAPI } from '../services/api';
import { COLORS } from '../constants';
import { toast } from './Toast';

interface WeightHistoryItem {
  id: number;
  created_at: string;
  updated_at?: string;
  weights: {
    structure: number;
    volatility: number;
    sentiment: number;
    manipulation: number;
  };
  weights_version: string;
  performance_metrics?: {
    win_rate?: number;
    avg_profit?: number;
    total_trades?: number;
  };
  opportunity_density_score?: number;
  ai_reason?: string;
  applied: boolean;
  applied_at?: string; // 应用时间（如果有）
  is_auto_applied?: boolean; // 是否自动应用（V4.5）
}

export const WeightHistory: React.FC = () => {
  const [history, setHistory] = useState<WeightHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adjusting, setAdjusting] = useState(false);
  const [applying, setApplying] = useState<number | null>(null);
  const [hasAutoApplied, setHasAutoApplied] = useState(false);
  const [lastAutoAppliedTime, setLastAutoAppliedTime] = useState<string | null>(null);

  useEffect(() => {
    loadHistory();
    checkAutoAppliedStatus();
  }, []);

  const loadHistory = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await weightsAPI.getHistory(50, 0);
      
      // 处理数据：判断是否自动应用
      const processedData = data.map((item: any) => {
        // 判断是否自动应用：如果创建时间和更新时间很接近（5分钟内），可能是自动应用
        const createdTime = new Date(item.created_at).getTime();
        const updatedTime = item.updated_at ? new Date(item.updated_at).getTime() : createdTime;
        const timeDiff = Math.abs(updatedTime - createdTime) / 1000 / 60; // 分钟
        
        // 如果已应用且时间差小于 5 分钟，可能是自动应用
        const isAutoApplied = item.applied && timeDiff < 5;
        
        return {
          ...item,
          is_auto_applied: isAutoApplied,
          applied_at: item.updated_at || (item.applied ? item.created_at : undefined),
        };
      });
      
      setHistory(processedData);
      
      // 检查是否有自动应用的记录
      const autoApplied = processedData.find((item: WeightHistoryItem) => item.is_auto_applied);
      if (autoApplied) {
        setHasAutoApplied(true);
        setLastAutoAppliedTime(autoApplied.applied_at || autoApplied.created_at);
      }
    } catch (err) {
      console.error('Failed to load weight history:', err);
      setError(err instanceof Error ? err.message : '加载权重历史失败');
      toast.error('加载权重历史失败');
    } finally {
      setLoading(false);
    }
  };

  const checkAutoAppliedStatus = async () => {
    // 检查是否有自动应用的通知（从 notifications 表）
    // TODO: 如果实现了 notifications API，可以调用
    // 目前通过时间差判断
  };

  const handleAdjust = async (force: boolean = false) => {
    try {
      setAdjusting(true);
      setError(null);
      
      const result = await weightsAPI.adjust(force);
      
      toast.success('AI 权重调整已触发，正在处理...');
      
      // 等待 2 秒后刷新列表
      setTimeout(() => {
        loadHistory();
      }, 2000);
    } catch (err: any) {
      console.error('Failed to trigger weight adjustment:', err);
      const errorMessage = err?.response?.detail || err?.message || '触发权重调整失败';
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setAdjusting(false);
    }
  };

  const handleApply = async (weightId: number) => {
    if (!confirm('确定要应用此权重配置吗？这将替换当前使用的权重。')) {
      return;
    }

    try {
      setApplying(weightId);
      setError(null);
      
      const result = await weightsAPI.apply(weightId);
      
      toast.success('权重配置已应用');
      
      // 刷新列表
      await loadHistory();
    } catch (err: any) {
      console.error('Failed to apply weight configuration:', err);
      const errorMessage = err?.response?.detail || err?.message || '应用权重配置失败';
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setApplying(null);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getWeightChange = (current: number, previous?: number) => {
    if (!previous) return null;
    const change = current - previous;
    return {
      value: change,
      percent: ((change / previous) * 100).toFixed(1),
      isPositive: change > 0,
    };
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-white/40">加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass rounded-2xl p-6">
        <div className="text-red-400">{error}</div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col gap-4 min-h-0 overflow-hidden">
      {/* 标题栏 */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white mb-1 flex items-center gap-2">
            <BrainCircuit className="w-6 h-6 text-[#7B61FF]" />
            AI 权重调整历史
          </h1>
          <p className="text-xs text-white/40 font-mono">
            V4.5 自动应用模式 | 通过脚本运行会自动应用，无需手动确认
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleAdjust(false)}
            disabled={adjusting}
            className="px-4 py-2 bg-[#00FF9D] hover:bg-[#00E68A] disabled:bg-gray-600 disabled:cursor-not-allowed text-black font-semibold rounded-lg text-sm transition-colors flex items-center gap-2"
          >
            {adjusting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                调整中...
              </>
            ) : (
              <>
                <Zap className="w-4 h-4" />
                AI 调整
              </>
            )}
          </button>
          <button
            onClick={loadHistory}
            disabled={loading}
            className="px-4 py-2 bg-[#7B61FF] hover:bg-[#6B51EF] disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg text-white text-sm transition-colors flex items-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                加载中...
              </>
            ) : (
              '刷新'
            )}
          </button>
        </div>
      </div>

      {/* V4.5 自动应用提示 */}
      {hasAutoApplied && lastAutoAppliedTime && (
        <div className="glass rounded-xl border border-green-400/30 bg-green-400/5 p-4 flex items-start gap-3">
          <Sparkles className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="text-sm font-semibold text-green-400 mb-1">V4.5 自动应用已启用</div>
            <div className="text-xs text-white/60 mb-2">
              最近一次自动应用: {formatDate(lastAutoAppliedTime)}
            </div>
            <div className="text-xs text-white/40">
              💡 提示：通过 <code className="px-1.5 py-0.5 bg-white/5 rounded text-[#7B61FF]">run_ai_weight_adjustment.py</code> 脚本或定时任务运行时，权重调整会自动应用，无需手动确认。
            </div>
          </div>
        </div>
      )}

      {/* 使用说明提示 */}
      <div className="glass rounded-xl border border-[#7B61FF]/30 bg-[#7B61FF]/5 p-4 flex items-start gap-3">
        <Info className="w-5 h-5 text-[#7B61FF] flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <div className="text-sm font-semibold text-[#7B61FF] mb-1">使用说明</div>
          <div className="text-xs text-white/60 space-y-1">
            <div>• <strong>自动应用</strong>：通过脚本运行会自动应用（显示 <Sparkles className="w-3 h-3 inline text-green-400" /> 图标）</div>
            <div>• <strong>手动应用</strong>：通过前端触发需要手动应用（显示 <User className="w-3 h-3 inline text-blue-400" /> 图标）</div>
            <div>• <strong>应用按钮</strong>：可用于回退到旧配置或手动应用新配置</div>
          </div>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="glass rounded-xl border border-red-400/30 bg-red-400/5 p-4 flex items-center gap-3">
          <XCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <div className="text-sm text-red-400">{error}</div>
        </div>
      )}

      {/* 权重历史列表 */}
      <div className="flex-1 glass rounded-xl border border-white/10 p-6 min-h-0 overflow-hidden flex flex-col">

        {history.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-white/40">
            <div className="text-center">
              <BrainCircuit className="w-12 h-12 mx-auto mb-3 text-white/20" />
              <div className="text-sm">暂无权重历史记录</div>
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto space-y-4 pr-2">
            {history.map((item, index) => {
              const previous = index < history.length - 1 ? history[index + 1] : null;
              const isAutoApplied = item.is_auto_applied || false;
              
              return (
                <div
                  key={item.id}
                  className={`border rounded-xl p-4 hover:border-opacity-50 transition-all ${
                    item.applied
                      ? isAutoApplied
                        ? 'border-green-400/30 bg-green-400/5'
                        : 'border-blue-400/30 bg-blue-400/5'
                      : 'border-white/10 bg-white/5'
                  }`}
                >
                  {/* 头部：版本信息 + 应用状态 */}
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        item.applied 
                          ? isAutoApplied 
                            ? 'bg-green-400' 
                            : 'bg-blue-400'
                          : 'bg-gray-400'
                      }`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-white font-medium font-mono">
                            {item.weights_version || 'v4.3.0'}
                          </span>
                          {isAutoApplied && item.applied && (
                            <span className="px-2 py-0.5 bg-green-400/20 border border-green-400/30 rounded text-[10px] font-mono text-green-400 flex items-center gap-1">
                              <Sparkles className="w-3 h-3" />
                              自动应用
                            </span>
                          )}
                          {!isAutoApplied && item.applied && (
                            <span className="px-2 py-0.5 bg-blue-400/20 border border-blue-400/30 rounded text-[10px] font-mono text-blue-400 flex items-center gap-1">
                              <User className="w-3 h-3" />
                              手动应用
                            </span>
                          )}
                        </div>
                        <div className="text-white/40 text-xs flex items-center gap-2">
                          <Clock className="w-3 h-3" />
                          <span>创建: {formatDate(item.created_at)}</span>
                          {item.applied_at && item.applied && (
                            <>
                              <span className="text-white/20">•</span>
                              <span>应用: {formatDate(item.applied_at)}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {item.applied ? (
                        <div className="flex items-center gap-2">
                          <CheckCircle className="w-4 h-4 text-green-400" />
                          <span className="text-xs text-green-400 font-mono">已应用</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <XCircle className="w-4 h-4 text-gray-400" />
                          <span className="text-xs text-gray-400 font-mono">未应用</span>
                          <button
                            onClick={() => handleApply(item.id)}
                            disabled={applying === item.id}
                            className="ml-2 px-3 py-1.5 bg-[#00FF9D] hover:bg-[#00E68A] disabled:bg-gray-600 disabled:cursor-not-allowed text-black text-xs font-semibold rounded transition-colors flex items-center gap-1.5"
                          >
                            {applying === item.id ? (
                              <>
                                <Loader2 className="w-3 h-3 animate-spin" />
                                应用中...
                              </>
                            ) : (
                              <>
                                <Play className="w-3 h-3" />
                                应用
                              </>
                            )}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* 权重值 */}
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
                    {Object.entries(item.weights).map(([key, value]) => {
                      const change = getWeightChange(value, previous?.weights?.[key as keyof typeof previous.weights]);
                      return (
                        <div key={key} className="p-3 bg-white/5 rounded-lg space-y-1">
                          <div className="text-white/60 text-xs uppercase font-mono">{key}</div>
                          <div className="flex items-center gap-2">
                            <span className="text-white font-mono text-sm font-bold">{(value * 100).toFixed(1)}%</span>
                            {change && (
                              <span className={`text-xs flex items-center gap-1 font-mono ${
                                change.isPositive ? 'text-green-400' : 'text-red-400'
                              }`}>
                                {change.isPositive ? (
                                  <TrendingUp className="w-3 h-3" />
                                ) : (
                                  <TrendingDown className="w-3 h-3" />
                                )}
                                {change.percent}%
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* 性能指标 */}
                  {item.performance_metrics && (
                    <div className="grid grid-cols-3 gap-3 mb-4">
                      {item.performance_metrics.win_rate !== undefined && (
                        <div className="p-3 bg-white/5 rounded-lg">
                          <div className="text-white/60 text-xs mb-1">胜率</div>
                          <div className="text-white font-mono text-lg font-bold">
                            {(item.performance_metrics.win_rate * 100).toFixed(1)}%
                          </div>
                        </div>
                      )}
                      {item.performance_metrics.avg_profit !== undefined && (
                        <div className="p-3 bg-white/5 rounded-lg">
                          <div className="text-white/60 text-xs mb-1">平均收益</div>
                          <div className={`font-mono text-lg font-bold ${
                            item.performance_metrics.avg_profit > 0 ? 'text-green-400' : 'text-red-400'
                          }`}>
                            {(item.performance_metrics.avg_profit * 100).toFixed(2)}%
                          </div>
                        </div>
                      )}
                      {item.performance_metrics.total_trades !== undefined && (
                        <div className="p-3 bg-white/5 rounded-lg">
                          <div className="text-white/60 text-xs mb-1">交易次数</div>
                          <div className="text-white font-mono text-lg font-bold">
                            {item.performance_metrics.total_trades}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* 机会密度分数和 AI 调整理由 */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                    {/* 机会密度分数 */}
                    {item.opportunity_density_score !== undefined && (
                      <div className="p-3 bg-white/5 rounded-lg">
                        <div className="flex items-center gap-2 mb-1">
                          <Activity className="w-4 h-4 text-[#7B61FF]" />
                          <div className="text-white/60 text-xs">机会密度分数 (ODS)</div>
                        </div>
                        <div className="text-white font-mono text-lg font-bold">
                          {(item.opportunity_density_score * 100).toFixed(1)}%
                        </div>
                      </div>
                    )}

                    {/* AI 调整理由 */}
                    {item.ai_reason && (
                      <div className="p-3 bg-white/5 rounded-lg">
                        <div className="text-white/60 text-xs mb-1">AI 调整理由</div>
                        <div className="text-white/80 text-sm line-clamp-2">{item.ai_reason}</div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default WeightHistory;

