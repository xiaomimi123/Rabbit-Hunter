/**
 * 交易分数组件
 * 显示交易分数列表、各维度分数详情、决策策略详情
 */

import React, { useEffect, useState } from 'react';
import { Search, Filter, TrendingUp, TrendingDown, CheckCircle, XCircle, BarChart3 } from 'lucide-react';
import { tradeScoresAPI } from '../services/api';
import { COLORS } from '../constants';

interface TradeScoreItem {
  id: number;
  symbol: string;
  created_at: string;
  structure_score: number;
  volatility_score: number;
  sentiment_score: number;
  manipulation_score: number;
  final_score: number;
  decision_policy?: {
    should_trade?: boolean;
    position_size_multiplier?: number;
    reason?: string;
  };
  executed: boolean;
  reason?: string;
}

export const TradeScores: React.FC = () => {
  const [scores, setScores] = useState<TradeScoreItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    symbol: '',
    executed: undefined as boolean | undefined,
  });

  useEffect(() => {
    loadScores();
  }, [filters]);

  const loadScores = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await tradeScoresAPI.getScores({
        limit: 50,
        offset: 0,
        symbol: filters.symbol || undefined,
        executed: filters.executed,
      });
      setScores(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load trade scores:', err);
      setError(err instanceof Error ? err.message : '加载交易分数失败');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.8) return 'text-green-400';
    if (score >= 0.6) return 'text-yellow-400';
    return 'text-red-400';
  };

  const getScoreBgColor = (score: number) => {
    if (score >= 0.8) return 'bg-green-400/20';
    if (score >= 0.6) return 'bg-yellow-400/20';
    return 'bg-red-400/20';
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
    <div className="space-y-4">
      <div className="glass rounded-2xl p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <BarChart3 className="w-5 h-5" />
            交易分数记录
          </h2>
          <button
            onClick={loadScores}
            className="px-4 py-2 bg-[#7B61FF] hover:bg-[#6B51EF] rounded-lg text-white text-sm transition-colors"
          >
            刷新
          </button>
        </div>

        {/* 筛选器 */}
        <div className="flex flex-col md:flex-row items-stretch md:items-center gap-4 mb-6">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-white/40" />
            <input
              type="text"
              placeholder="搜索币种..."
              value={filters.symbol}
              onChange={(e) => setFilters({ ...filters, symbol: e.target.value })}
              className="w-full pl-10 pr-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/40 focus:outline-none focus:border-[#7B61FF]"
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setFilters({ ...filters, executed: undefined })}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                filters.executed === undefined
                  ? 'bg-[#7B61FF] text-white'
                  : 'bg-white/5 text-white/60 hover:bg-white/10'
              }`}
            >
              全部
            </button>
            <button
              onClick={() => setFilters({ ...filters, executed: true })}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                filters.executed === true
                  ? 'bg-[#7B61FF] text-white'
                  : 'bg-white/5 text-white/60 hover:bg-white/10'
              }`}
            >
              已执行
            </button>
            <button
              onClick={() => setFilters({ ...filters, executed: false })}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                filters.executed === false
                  ? 'bg-[#7B61FF] text-white'
                  : 'bg-white/5 text-white/60 hover:bg-white/10'
              }`}
            >
              未执行
            </button>
          </div>
        </div>

        {scores.length === 0 ? (
          <div className="text-center py-12 text-white/40">
            暂无交易分数记录
          </div>
        ) : (
          <div className="space-y-3">
            {scores.map((item) => (
              <div
                key={item.id}
                className="border border-white/10 rounded-xl p-4 hover:border-white/20 transition-colors"
              >
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="flex items-center gap-3">
                      <span className="text-white font-bold text-lg">{item.symbol}</span>
                      {item.executed ? (
                        <CheckCircle className="w-4 h-4 text-green-400" />
                      ) : (
                        <XCircle className="w-4 h-4 text-gray-400" />
                      )}
                      <span className={`text-xs ${item.executed ? 'text-green-400' : 'text-gray-400'}`}>
                        {item.executed ? '已执行' : '未执行'}
                      </span>
                    </div>
                    <div className="text-white/40 text-xs mt-1">
                      {formatDate(item.created_at)}
                    </div>
                  </div>
                  <div className={`px-3 py-1 rounded-lg ${getScoreBgColor(item.final_score)}`}>
                    <span className={`font-mono font-bold ${getScoreColor(item.final_score)}`}>
                      {(item.final_score * 100).toFixed(1)}
                    </span>
                  </div>
                </div>

                {/* 各维度分数 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <div className="space-y-1">
                    <div className="text-white/60 text-xs">结构分</div>
                    <div className={`font-mono ${getScoreColor(item.structure_score)}`}>
                      {(item.structure_score * 100).toFixed(1)}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-white/60 text-xs">波动率分</div>
                    <div className={`font-mono ${getScoreColor(item.volatility_score)}`}>
                      {(item.volatility_score * 100).toFixed(1)}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-white/60 text-xs">情绪分</div>
                    <div className={`font-mono ${getScoreColor(item.sentiment_score)}`}>
                      {(item.sentiment_score * 100).toFixed(1)}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-white/60 text-xs">操纵分</div>
                    <div className={`font-mono ${getScoreColor(item.manipulation_score)}`}>
                      {(item.manipulation_score * 100).toFixed(1)}
                    </div>
                  </div>
                </div>

                {/* 决策策略 */}
                {item.decision_policy && (
                  <div className="p-3 bg-white/5 rounded-lg mb-2">
                    <div className="text-white/60 text-xs mb-1">决策策略</div>
                    <div className="flex items-center gap-4">
                      {item.decision_policy.should_trade !== undefined && (
                        <div className="flex items-center gap-2">
                          {item.decision_policy.should_trade ? (
                            <TrendingUp className="w-4 h-4 text-green-400" />
                          ) : (
                            <TrendingDown className="w-4 h-4 text-red-400" />
                          )}
                          <span className="text-white text-sm">
                            {item.decision_policy.should_trade ? '建议交易' : '不建议交易'}
                          </span>
                        </div>
                      )}
                      {item.decision_policy.position_size_multiplier !== undefined && (
                        <div className="text-white/60 text-sm">
                          仓位倍数: {item.decision_policy.position_size_multiplier.toFixed(2)}x
                        </div>
                      )}
                    </div>
                    {item.decision_policy.reason && (
                      <div className="text-white/80 text-xs mt-2">
                        {item.decision_policy.reason}
                      </div>
                    )}
                  </div>
                )}

                {/* 原因 */}
                {item.reason && (
                  <div className="text-white/60 text-xs">
                    {item.reason}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default TradeScores;

