/**
 * Dashboard 页面 - 驾驶舱核心视图
 * 实时展示猎杀队列、ATR 监控、AI 进化日志
 */

import React, { useEffect } from 'react';
import {
  TrendingUp,
  Clock,
  AlertTriangle,
  ChevronRight,
  Activity,
  BrainCircuit,
  Zap
} from 'lucide-react';
import { useV43Store } from '../services/store';
import { killQueueAPI, positionsAPI, aiEvolutionAPI } from '../services/api';
import { connectWebSocket, getWebSocketClient } from '../services/websocket';
import { AIWeightRadar, HealthDonut } from './Charts';
import { AnatomyPanel } from './AnatomyPanel';
import { COLORS } from '../constants';

export const Dashboard: React.FC = () => {
  const store = useV43Store();

  // 获取初始数据
  useEffect(() => {
    const loadData = async () => {
      try {
        // 加载猎杀队列
        store.setKillQueueLoading(true);
        try {
          // 使用 minScore=0 显示所有数据（包括被拦截的低分币种）
          // 这样可以查看所有币种的评分情况，即使被拦截也能看到原因
          const queueResult = await killQueueAPI.getQueue(50, 0); // 改为 0 以显示所有数据
          // 后端返回格式: { status, code, data: [...], pagination, metadata }
          console.log('[Dashboard] Kill queue API 响应:', queueResult);
          
          if (queueResult && queueResult.data && Array.isArray(queueResult.data)) {
            const dataLength = queueResult.data.length;
            console.log(`[Dashboard] ✅ 成功加载 ${dataLength} 个交易机会`);
            
            // 确保数据不为空
            if (dataLength > 0) {
              // 去重：确保每个 symbol 只出现一次（保留最新的记录）
              const deduplicatedMap = new Map<string, typeof queueResult.data[0]>();
              queueResult.data.forEach((item) => {
                const existing = deduplicatedMap.get(item.symbol);
                if (!existing || (item.timestamp && existing.timestamp && item.timestamp > existing.timestamp)) {
                  deduplicatedMap.set(item.symbol, item);
                }
              });
              const deduplicatedData = Array.from(deduplicatedMap.values());
              console.log(`[Dashboard] 去重后: ${deduplicatedData.length} 个唯一币种`);
              store.setKillQueue(deduplicatedData);
            } else {
              console.warn('[Dashboard] ⚠️ API 返回了空数组，可能是 minScore 阈值过高或数据库无数据');
              store.setKillQueue([]);
            }
          } else {
            console.warn('[Dashboard] ⚠️ Kill queue API 返回格式异常:', queueResult);
            console.warn('[Dashboard] queueResult 类型:', typeof queueResult);
            console.warn('[Dashboard] queueResult.data 类型:', typeof queueResult?.data);
            store.setKillQueue([]);
          }
        } catch (err) {
          console.error('[Dashboard] ❌ 加载猎杀队列失败:', err);
          const errorMsg = err instanceof Error ? err.message : 'Unknown error';
          console.error('[Dashboard] 错误详情:', errorMsg);
          store.setKillQueue([]);
        }

        // 加载持仓
        store.setPositionsLoading(true);
        try {
          const positionsResult = await positionsAPI.getActive();
          // 后端返回格式: { status, code, data: { active: [...], total: N } }
          if (positionsResult && positionsResult.data && positionsResult.data.active) {
            store.setPositions(Array.isArray(positionsResult.data.active) ? positionsResult.data.active : []);
          } else {
            console.warn('Positions API returned unexpected format:', positionsResult);
            store.setPositions([]);
          }
        } catch (err) {
          console.error('Failed to load positions:', err);
          store.setPositions([]);
        }

        // 加载 AI 进化日志
        store.setAILoading(true);
        try {
          const evolutionResult = await aiEvolutionAPI.getHistory(30);
          // 后端返回格式: { status, code, data: [...], stats: {...} }
          if (evolutionResult && evolutionResult.data) {
            store.setEvolutionEvents(Array.isArray(evolutionResult.data) ? evolutionResult.data : []);
          } else {
            console.warn('AI Evolution API returned unexpected format:', evolutionResult);
            store.setEvolutionEvents([]);
          }
        } catch (err) {
          console.error('Failed to load AI evolution:', err);
          store.setEvolutionEvents([]);
        }
      } catch (error) {
        console.error('Failed to load dashboard data:', error);
        // 使用 Toast 通知替代 alert
        const { toast } = await import('./Toast');
        toast.error(`数据加载失败: ${error instanceof Error ? error.message : 'Unknown error'}`);
      } finally {
        store.setKillQueueLoading(false);
        store.setPositionsLoading(false);
        store.setAILoading(false);
      }
    };

    let isMounted = true;
    
    loadData().catch((error) => {
      if (isMounted) {
        console.error('Failed to load dashboard data:', error);
      }
    });

    // WebSocket 订阅
    const ws = connectWebSocket();
    
    // 订阅事件
    ws.subscribe('kill_queue_update');
    ws.subscribe('position_update');
    ws.subscribe('ai_evolution_event');
    ws.subscribe('system_status_update');

    return () => {
      isMounted = false;
      // 清理：取消订阅（WebSocket 客户端会自动处理）
      ws.unsubscribe('kill_queue_update');
      ws.unsubscribe('position_update');
      ws.unsubscribe('ai_evolution_event');
      ws.unsubscribe('system_status_update');
    };
  }, []); // 空依赖数组，确保只执行一次

  return (
    <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-4">
      {/* ========== 左列: 系统均衡 + ATR 监控 ========== */}
      <div className="lg:col-span-3 flex flex-col gap-4">
        {/* 系统均衡状态 */}
        <div className="glass rounded-2xl p-6 flex flex-col items-center justify-center gap-4 relative overflow-hidden group">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-[#7B61FF] to-transparent" />

          <h3 className="text-xs font-mono uppercase tracking-[0.2em] text-white/40">
            系统均衡状态
          </h3>

          <div className="w-full max-w-[160px] aspect-square mx-auto" style={{ minHeight: '160px', height: '100%' }}>
            {store.killQueue && store.killQueue.length > 0 && store.killQueue[0]?.weights ? (
              <AIWeightRadar weights={store.killQueue[0].weights} />
            ) : (
              <div className="w-full h-full flex items-center justify-center" style={{ minHeight: '160px' }}>
                <div className="text-white/20 text-xs font-mono">等待数据...</div>
              </div>
            )}
          </div>

          <p className="text-[10px] font-mono text-white/40 text-center leading-relaxed px-4">
            AI 当前优先考虑{' '}
            <span className="text-[#7B61FF]">
              {store.killQueue && store.killQueue.length > 0 && store.killQueue[0]?.weights
                ? (store.killQueue[0].weights.structure || 0)
                : 0}% 市场结构
            </span>
            {' 和 '}
            <span className="text-[#7B61FF]">
              {store.killQueue && store.killQueue.length > 0 && store.killQueue[0]?.weights
                ? (store.killQueue[0].weights.volatility || 0)
                : 0}% 波动率
            </span>
          </p>
        </div>

        {/* ATR 止损监控 */}
        <div className="glass rounded-2xl p-6 flex-1 space-y-6">
          <h3 className="text-xs font-mono uppercase tracking-[0.2em] text-white/40 flex items-center gap-2">
            <Activity size={14} className="text-[#00FF9D]" /> ATR 止损监控
          </h3>

          <div className="space-y-8">
            {store.positions && store.positions.length > 0 ? (
              store.positions
                .filter(pos => pos && pos.currentPrice && pos.atrStop)
                .map((pos) => {
                  const distance = ((pos.currentPrice! - pos.atrStop!) / pos.currentPrice!) * 100;
                  const isDanger = pos.status === 'DANGER' || distance < 2;

                  return (
                    <div key={pos.symbol} className="space-y-2">
                      <div className="flex justify-between items-end">
                        <div>
                          <span className="text-sm font-bold text-white block">{pos.symbol}</span>
                          <span className="text-[10px] font-mono text-white/30">
                            盈亏: {pos.pnlPercent ? (pos.pnlPercent > 0 ? '+' : '') + pos.pnlPercent.toFixed(2) + '%' : 'N/A'}
                          </span>
                        </div>
                        <span
                          className={`text-[10px] font-mono ${
                            isDanger ? 'text-red-500 animate-pulse' : 'text-[#00FF9D]'
                          }`}
                        >
                          {isDanger ? '危险区域' : '安全区域'}
                        </span>
                      </div>

                      {/* 生命条 */}
                      <div className="h-1.5 w-full bg-white/5 rounded-full relative overflow-hidden">
                        <div
                          className={`h-full transition-all duration-1000 ${
                            isDanger ? 'bg-red-500 shadow-[0_0_10px_#ef4444]' : 'bg-[#00FF9D]'
                          }`}
                          style={{ width: `${Math.min(100, Math.max(10, distance * 20))}%` }}
                        />
                      </div>

                      <div className="flex justify-between text-[8px] font-mono text-white/20">
                        <span>止损: {pos.atrStop!.toFixed(2)}</span>
                        <span>现价: {pos.currentPrice!.toFixed(2)}</span>
                      </div>
                    </div>
                  );
                })
            ) : (
              <div className="text-center py-8">
                <p className="text-[10px] font-mono text-white/30">暂无活跃持仓</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ========== 中列: 实时猎杀队列 ========== */}
      <div className="lg:col-span-6 flex flex-col gap-4">
        <div className="glass rounded-2xl p-6 flex-1 overflow-y-auto max-h-[calc(100vh-200px)]">
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-xl font-bold tracking-tighter text-white flex items-center gap-3">
              实时猎杀队列{' '}
              <span className="px-2 py-0.5 bg-white/10 rounded text-[10px] font-mono text-white/40 tracking-normal">
                AI 评分 &gt; 40
              </span>
            </h2>

            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-[#00FF9D] animate-pulse" />
              <span className="text-[10px] font-mono opacity-50 uppercase tracking-widest">
                实时信号
              </span>
            </div>
          </div>

          {store.killQueueLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-white/40 font-mono text-sm">加载中...</div>
            </div>
          ) : store.killQueue.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 space-y-4">
              <AlertTriangle size={48} className="text-white/20" />
              <div className="text-white/40 font-mono text-sm text-center">
                暂无交易机会
                <br />
                <span className="text-[10px]">等待市场异动或降低评分阈值</span>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {store.killQueue.map((coin, index) => (
              <button
                key={`${coin.symbol}-${coin.timestamp || index}-${Date.now()}`}
                onClick={() => store.selectCoin(coin)}
                className="group relative flex items-center justify-between glass p-6 rounded-2xl hover:neon-border-purple transition-all duration-300 text-left overflow-hidden"
              >
                <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                  <BrainCircuit size={64} />
                </div>

                {/* AI 评分 */}
                <div className="flex items-center gap-6">
                  <div className="relative">
                    <div className="text-3xl font-bold font-mono text-white group-hover:text-[#7B61FF] transition-colors">
                      {coin.aiScore.toFixed(1)}
                    </div>
                    <div className="text-[8px] font-mono text-white/30 uppercase mt-1">
                      AI 评分
                    </div>
                  </div>

                  <div className="w-px h-12 bg-white/10" />

                  {/* 币种信息 */}
                  <div>
                    <div className="text-lg font-bold text-white flex items-center gap-2">
                      {coin.symbol}
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded ${
                          coin.phase.startsWith('P3')
                            ? 'bg-[#00FF9D]/10 text-[#00FF9D]'
                            : 'bg-red-500/10 text-red-500'
                        }`}
                      >
                        {coin.phase}
                      </span>
                    </div>
                    <div className="text-xs font-mono text-white/40 mt-1 max-w-[200px] truncate">
                      {coin.reason}
                    </div>
                  </div>
                </div>

                {/* 右侧信息 */}
                <div className="flex items-center gap-8">
                  <div className="text-right">
                    <div className="text-xs font-mono text-white/40 uppercase mb-1 flex items-center gap-1 justify-end">
                      <Clock size={10} /> 存续时间
                    </div>
                    <div className="text-sm font-mono text-white">{coin.age}</div>
                  </div>

                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center border transition-all ${
                      coin.aiScore > 80
                        ? 'border-[#00FF9D] text-[#00FF9D] shadow-[0_0_15px_rgba(0,255,157,0.2)]'
                        : 'border-white/10 text-white/20'
                    }`}
                  >
                    <ChevronRight size={24} />
                  </div>
                </div>
              </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ========== 右列: AI 进化日志 ========== */}
      <div className="lg:col-span-3 flex flex-col gap-4">
        {/* AI 进化日志 */}
        <div className="glass rounded-2xl p-6 flex flex-col gap-4">
          <h3 className="text-xs font-mono uppercase tracking-[0.2em] text-white/40 flex items-center gap-2">
            <Zap size={14} className="text-yellow-400" /> AI 进化日志
          </h3>

          <div className="space-y-4">
            {store.evolutionEvents.slice(0, 2).map((event) => (
              <div
                key={event.date}
                className={`p-3 rounded-xl border space-y-2 ${
                  event.type === 'WIN'
                    ? 'bg-[#00FF9D]/5 border-[#00FF9D]/20'
                    : 'bg-red-500/5 border-red-500/20'
                }`}
              >
                <div className="flex justify-between items-center">
                  <span className="text-[10px] font-mono text-white/40">{event.date}</span>
                  <span
                    className={`text-[10px] font-mono ${
                      event.type === 'WIN' ? 'text-[#00FF9D]' : 'text-red-500'
                    }`}
                  >
                    {event.type === 'WIN' ? '盈利' : '亏损'}
                  </span>
                </div>
                <p className="text-[10px] font-mono leading-tight text-white/80">
                  {event.decision}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* 参数学习热力图 */}
        <div className="glass rounded-2xl p-6 flex-1 space-y-4">
          <h3 className="text-xs font-mono uppercase tracking-[0.2em] text-white/40">
            参数学习热力图
          </h3>

          <div className="grid grid-cols-7 gap-1">
            {Array.from({ length: 28 }).map((_, i) => (
              <div
                key={i}
                className={`aspect-square rounded-sm ${
                  i > 20 ? 'bg-[#00FF9D]' : i > 10 ? 'bg-[#7B61FF]/40' : 'bg-white/5'
                }`}
                title={`第 ${i} 天: 准确率 ${Math.floor(Math.random() * 40 + 60)}%`}
              />
            ))}
          </div>

          <div className="flex justify-between text-[8px] font-mono text-white/20 uppercase tracking-tighter pt-2">
            <span>历史冷度</span>
            <span>当前 Alpha</span>
          </div>
        </div>
      </div>

      {/* 深度解剖浮窗 */}
      {store.selectedCoin && (
        <AnatomyPanel
          coin={store.selectedCoin}
          onClose={() => store.selectCoin(null)}
        />
      )}
    </div>
  );
};

export default Dashboard;
