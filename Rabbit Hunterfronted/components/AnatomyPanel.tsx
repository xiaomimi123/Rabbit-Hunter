/**
 * AnatomyPanel 组件 - 深度解剖浮窗
 * 显示币种详细分析、AI 权重、Gemini 解释
 */

import React, { useEffect, useState } from 'react';
import { X, Target, Zap, MessageSquare, ChevronRight } from 'lucide-react';
import { CoinData } from '../types';
import { AIWeightRadar } from './Charts';
import { anatomyAPI } from '../services/api';

interface AnatomyPanelProps {
  coin: CoinData | null;
  onClose: () => void;
}

export const AnatomyPanel: React.FC<AnatomyPanelProps> = ({ coin, onClose }) => {
  const [explanation, setExplanation] = useState<string>('量子大脑正在分析...');
  const [loading, setLoading] = useState(true);
  const [anatomyData, setAnatomyData] = useState<any>(null);

  useEffect(() => {
    if (!coin) return;

    const loadData = async () => {
      try {
        setLoading(true);

        // 获取深度分析
        const result = await anatomyAPI.analyze(coin.symbol);
        const data = result.data;
        setAnatomyData(data);

        // 使用 DeepSeek 生成 AI 解释（带 ATR / 止损 / 盈亏比 / 阶段上下文）
        try {
          const text = await anatomyAPI.explain(
            coin.symbol,
            coin.aiScore,
            coin.reason,
            {
              atr: data?.technicalAnalysis?.atr,
              stopLoss: data?.recommendedExecution?.stopLoss,
              takeProfit: data?.recommendedExecution?.takeProfit,
              rewardRiskRatio: data?.recommendedExecution?.rewardRiskRatio,
              phase: data?.phase,
            }
          );
          setExplanation(text);
        } catch (e) {
          console.error('[AnatomyPanel] AI 解释失败:', e);
          setExplanation('AI 分析失败，请稍后重试');
        }
      } catch (error) {
        console.error('Failed to load anatomy data:', error);
        setExplanation('AI 分析失败，请稍后重试');
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [coin]);

  if (!coin) return null;

  return (
    <div className="fixed inset-y-4 right-4 w-[calc(100vw-2rem)] max-w-[450px] glass rounded-2xl flex flex-col z-50 border border-white/10 animate-in slide-in-from-right duration-300">
      {/* 标题栏 */}
      <div className="p-6 border-b border-white/5 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            深度解剖台 <span className="text-xs font-mono text-white/40">V4.3</span>
          </h2>
          <p className="text-xs font-mono text-[#00FF9D]">
            {coin.symbol} • AI 评分 {coin.aiScore.toFixed(1)}
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-2 hover:bg-white/10 rounded-lg transition-colors"
        >
          <X size={20} />
        </button>
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto p-6 space-y-8">
        {/* 结构化扫描 */}
        <section>
          <h3 className="text-xs font-mono uppercase tracking-widest text-white/40 mb-4 flex items-center gap-2">
            <Target size={14} /> 结构化扫描 (Visual Confirmation)
          </h3>

          <div className="aspect-video w-full bg-black/60 rounded-xl border border-white/5 p-4 flex flex-col justify-between relative overflow-hidden">
            <div className="flex justify-between items-start z-10">
              <span className="text-[10px] font-mono text-[#00FF9D]">
                缺口: {anatomyData?.structuralAnalysis?.gap?.percentage?.toFixed(2) || '0'}%
              </span>
              <span className="text-[10px] font-mono text-white/30">
                ATR: {anatomyData?.technicalAnalysis?.atr?.toFixed(0) || '0'}
              </span>
            </div>

            {/* 蜡烛图可视化 */}
            <div className="absolute inset-x-0 bottom-4 h-16 flex items-end justify-center gap-2">
              {[20, 35, 25, 60, 45, 80, 70].map((h, i) => (
                <div
                  key={i}
                  className={`w-3 rounded-t-sm transition-all ${
                    i === 5 ? 'bg-[#00FF9D] shadow-[0_0_10px_#00FF9D]' : 'bg-white/10'
                  }`}
                  style={{ height: `${h}%` }}
                >
                  {i === 5 && (
                    <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-8 bg-[#00FF9D] text-black text-[8px] px-1 font-bold rounded">
                      黄金影线
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* AI 权重雷达 */}
        <section>
          <h3 className="text-xs font-mono uppercase tracking-widest text-white/40 mb-4 flex items-center gap-2">
            <Zap size={14} /> AI 决策权重 (Spider Chart)
          </h3>

          <div className="glass rounded-xl p-2 min-h-[256px] min-w-0" style={{ minHeight: '256px', height: '256px' }}>
            <AIWeightRadar weights={coin.weights} />
          </div>
        </section>

        {/* AI 解释 */}
        <section>
          <h3 className="text-xs font-mono uppercase tracking-widest text-white/40 mb-4 flex items-center gap-2">
            <MessageSquare size={14} /> 神经脉冲 (AI 心声)
          </h3>

          <div className="p-4 bg-white/5 border border-[#7B61FF]/20 rounded-xl italic text-sm text-white/80 leading-relaxed font-mono min-h-[80px] flex items-center">
            <div className="w-1.5 h-1.5 bg-[#7B61FF] rounded-full inline-block mr-2 animate-pulse" />
            {loading ? '正在分析...' : explanation}
          </div>
        </section>

        {/* 执行参数 */}
        <section className="space-y-3">
          <div className="flex justify-between p-3 bg-black/40 border border-white/5 rounded-lg">
            <span className="text-xs font-mono text-white/40">ATR 止损位</span>
            <span className="text-xs font-mono text-[#FF2E2E]">
              {anatomyData?.recommendedExecution?.stopLoss?.toFixed(2) || '-'}
            </span>
          </div>

          <div className="flex justify-between p-3 bg-black/40 border border-white/5 rounded-lg">
            <span className="text-xs font-mono text-white/40">盈亏比</span>
            <span className="text-xs font-mono text-white">
              1 : {anatomyData?.recommendedExecution?.rewardRiskRatio?.toFixed(1) || '-'}
            </span>
          </div>

          <div className="flex justify-between p-3 bg-black/40 border border-white/5 rounded-lg">
            <span className="text-xs font-mono text-white/40">推荐杠杆</span>
            <span className="text-xs font-mono text-white">
              {anatomyData?.recommendedExecution?.suggestedLeverage || '-'}x
            </span>
          </div>
        </section>
      </div>

      {/* 操作按钮 */}
      <div className="p-6 border-t border-white/5">
        <button className="w-full py-4 bg-[#00FF9D] text-black font-bold tracking-tighter rounded-xl hover:brightness-110 transition-all shadow-[0_0_20px_rgba(0,255,157,0.3)] flex items-center justify-center gap-2 uppercase">
          初始化猎杀 <ChevronRight size={18} />
        </button>
      </div>
    </div>
  );
};

export default AnatomyPanel;
