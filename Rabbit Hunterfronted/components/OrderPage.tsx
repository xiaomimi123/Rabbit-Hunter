
/**
 * OrderPage 组件 - 战术下单页面
 * 
 * 功能：
 * - 币种选择和交易参数配置
 * - 进场验证（4D 评分）
 * - TradingView K 线图表显示
 * - 交易执行
 * 
 * @component
 * @example
 * ```tsx
 * <OrderPage />
 * ```
 */

import React, { useState, useEffect } from 'react';
import { Target, ShieldCheck, Zap, AlertCircle, ChevronDown, Binary, Loader2, CheckCircle, XCircle, RefreshCw } from 'lucide-react';
import { COLORS } from '../constants';
import { useV43Store } from '../services/store';
import { killQueueAPI, tradeAPI, entryValidationAPI, anatomyAPI, positionsAPI, accountAPI, marketDepthAPI } from '../services/api';
import TradingViewChart from './TradingViewChart';
import { CandlestickData, Time } from 'lightweight-charts';
import { toast } from './Toast';

const OrderPage: React.FC = () => {
  const store = useV43Store();
  const [symbol, setSymbol] = useState<string>('');
  const [side, setSide] = useState<'LONG' | 'SHORT'>('LONG');
  const [type, setType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [leverage, setLeverage] = useState(10);
  const [risk, setRisk] = useState(2); // 2% risk
  const [limitPrice, setLimitPrice] = useState<number | null>(null);
  
  // 验证和交易状态
  const [validating, setValidating] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [validationResult, setValidationResult] = useState<any>(null);
  const [executionResult, setExecutionResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  
  // 图表数据
  const [chartData, setChartData] = useState<CandlestickData[]>([]);
  const [loadingChart, setLoadingChart] = useState(false);
  
  // AI 止损推荐
  const [aiStopLoss, setAiStopLoss] = useState<number | null>(null);
  const [estimatedPosition, setEstimatedPosition] = useState<number | null>(null);
  
  // 账户余额
  const [accountBalance, setAccountBalance] = useState<{ balance: number; freeMargin: number } | null>(null);
  const [loadingBalance, setLoadingBalance] = useState(false);
  
  // 市场深度
  const [marketDepth, setMarketDepth] = useState<Array<{ price: number; quantity: number; side: 'bid' | 'ask' }>>([]);
  const [loadingDepth, setLoadingDepth] = useState(false);

  // 加载币种列表（从数据库获取最新真实数据）
  const loadKillQueue = async (forceRefresh: boolean = false) => {
    // 如果不是强制刷新，且 store 中已有数据，直接使用
    if (!forceRefresh && store.killQueue.length > 0) {
      if (!symbol) {
        setSymbol(store.killQueue[0].symbol);
      }
      return;
    }

    // 从数据库获取最新真实数据
    try {
      store.setKillQueueLoading(true);
      console.log('[OrderPage] 🔄 正在从数据库加载最新币种数据...');
      
      // 使用 minScore=0 获取所有数据（包括低分币种），确保获取真实数据
      const queueResult = await killQueueAPI.getQueue(50, 0);
      
      if (queueResult && queueResult.data && Array.isArray(queueResult.data)) {
        if (queueResult.data.length > 0) {
          // 过滤出有效的 symbol（确保不是空字符串或 undefined）
          const validData = queueResult.data.filter(item => 
            item && item.symbol && typeof item.symbol === 'string' && item.symbol.trim() !== ''
          );
          
          // 去重：每个 symbol 只保留最新的记录（避免重复 key 警告）
          const symbolMap = new Map<string, any>();
          validData.forEach((item: any) => {
            const itemSymbol = item.symbol;
            const itemTimestamp = item.timestamp || item.created_at || item.lastUpdated || item.updated_at || '';
            
            // 如果该 symbol 还没有记录，或者当前记录更新，则保留
            if (!symbolMap.has(itemSymbol)) {
              symbolMap.set(itemSymbol, item);
            } else {
              const existing = symbolMap.get(itemSymbol);
              const existingTimestamp = existing.timestamp || existing.created_at || existing.lastUpdated || existing.updated_at || '';
              
              // 比较时间戳，保留最新的
              if (itemTimestamp > existingTimestamp) {
                symbolMap.set(itemSymbol, item);
              }
            }
          });
          
          // 转换为数组并排序（按分数降序，或按 symbol 字母顺序）
          const uniqueData = Array.from(symbolMap.values()).sort((a: any, b: any) => {
            // 优先按分数排序，如果分数相同则按 symbol 排序
            const scoreA = (a.final_score || 0) * 100;
            const scoreB = (b.final_score || 0) * 100;
            if (scoreB !== scoreA) {
              return scoreB - scoreA;
            }
            return (a.symbol || '').localeCompare(b.symbol || '');
          });
          
          if (uniqueData.length > 0) {
            console.log(`[OrderPage] ✅ 成功加载 ${uniqueData.length} 个唯一币种（原始数据: ${validData.length} 条）`);
            store.setKillQueue(uniqueData);
            
            // 设置默认币种（如果当前没有选择或当前选择的币种不在新数据中）
            if (!symbol || !uniqueData.find(item => item.symbol === symbol)) {
              setSymbol(uniqueData[0].symbol);
              console.log(`[OrderPage] 📌 设置默认币种: ${uniqueData[0].symbol}`);
            }
          } else {
            console.warn('[OrderPage] ⚠️ 去重后没有有效数据');
            toast.error('币种数据无效，请检查数据库');
            store.setKillQueue([]);
          }
        } else {
          console.warn('[OrderPage] ⚠️ Kill queue 数据为空（数据库可能没有数据）');
          toast.warning('数据库中没有币种数据，请确保采集器正在运行');
          store.setKillQueue([]);
        }
      } else {
        console.warn('[OrderPage] ⚠️ Kill queue API 返回格式异常:', queueResult);
        toast.error('数据格式错误，请检查后端 API');
        store.setKillQueue([]);
      }
    } catch (err) {
      console.error('[OrderPage] ❌ 加载币种列表失败:', err);
      const errorMsg = err instanceof Error ? err.message : '加载失败';
      toast.error(`加载币种列表失败: ${errorMsg}`);
      store.setKillQueue([]);
    } finally {
      store.setKillQueueLoading(false);
    }
  };

  // 组件挂载时加载数据
  useEffect(() => {
    loadKillQueue(true); // 强制刷新，确保获取最新数据
  }, []); // 只在组件挂载时执行一次

  // 当 killQueue 数据加载完成后，设置默认币种
  useEffect(() => {
    if (store.killQueue.length > 0 && !symbol) {
      setSymbol(store.killQueue[0].symbol);
    }
  }, [store.killQueue, symbol]);

  // 加载账户余额
  const loadAccountBalance = async () => {
    try {
      setLoadingBalance(true);
      const result = await accountAPI.getBalance();
      if (result && result.balance !== undefined) {
        setAccountBalance({
          balance: result.balance || 0,
          freeMargin: result.freeMargin || result.availableBalance || 0,
        });
      }
    } catch (err) {
      console.error('[OrderPage] 加载账户余额失败:', err);
      // 不显示错误，保持 null 状态（显示加载中）
    } finally {
      setLoadingBalance(false);
    }
  };

  // 加载市场深度
  const loadMarketDepth = async () => {
    if (!symbol) return;
    try {
      setLoadingDepth(true);
      const result = await marketDepthAPI.getDepth(symbol, 12);
      if (result && Array.isArray(result)) {
        setMarketDepth(result);
      } else if (result && result.bids && result.asks) {
        // 处理标准格式 { bids: [...], asks: [...] }
        const depth: Array<{ price: number; quantity: number; side: 'bid' | 'ask' }> = [];
        // 添加卖单（asks，红色）
        if (Array.isArray(result.asks)) {
          result.asks.slice(0, 6).forEach((item: any) => {
            depth.push({
              price: typeof item === 'number' ? item : (item.price || item[0] || 0),
              quantity: typeof item === 'number' ? 0 : (item.quantity || item[1] || 0),
              side: 'ask',
            });
          });
        }
        // 添加买单（bids，绿色）
        if (Array.isArray(result.bids)) {
          result.bids.slice(0, 6).forEach((item: any) => {
            depth.push({
              price: typeof item === 'number' ? item : (item.price || item[0] || 0),
              quantity: typeof item === 'number' ? 0 : (item.quantity || item[1] || 0),
              side: 'bid',
            });
          });
        }
        setMarketDepth(depth);
      }
    } catch (err) {
      console.error('[OrderPage] 加载市场深度失败:', err);
      // 不显示错误，保持空数组（显示加载中）
    } finally {
      setLoadingDepth(false);
    }
  };

  // 组件挂载时加载账户余额
  useEffect(() => {
    loadAccountBalance();
    // 每 30 秒刷新一次余额
    const interval = setInterval(loadAccountBalance, 30000);
    return () => clearInterval(interval);
  }, []);

  // 加载图表数据和市场深度
  useEffect(() => {
    if (symbol) {
      loadChartData();
      validateEntry();
      loadMarketDepth();
    }
  }, [symbol]); // 移除 leverage 和 risk 依赖，避免不必要的重新加载

  // 当 leverage 或 risk 变化时，只重新验证（不重新加载图表）
  useEffect(() => {
    if (symbol) {
      validateEntry();
    }
  }, [leverage, risk]);

  const loadChartData = async () => {
    if (!symbol) return;
    try {
      setLoadingChart(true);
      console.log('[OrderPage] 开始加载图表数据:', symbol);
      
      const response = await anatomyAPI.getChartData(symbol, 100);
      console.log('[OrderPage] API 响应:', response);
      
      // 处理不同的响应格式
      let data: CandlestickData[] = [];
      if (Array.isArray(response)) {
        data = response;
      } else if (response && Array.isArray(response.data)) {
        data = response.data;
      } else if (response && response.data && Array.isArray(response.data)) {
        data = response.data;
      }
      
      console.log('[OrderPage] 处理后的数据长度:', data.length);
      
      if (data.length > 0) {
        // 确保时间戳格式正确（秒级）
        const processedData: CandlestickData<Time>[] = data.map(item => {
          let timestamp: Time = item.time as Time;
          if (typeof timestamp === 'number') {
            // 如果是毫秒级（> 1e10），转换为秒级
            timestamp = (timestamp > 1e10 ? Math.floor(timestamp / 1000) : timestamp) as Time;
          }
          
          return {
            time: timestamp,
            open: Number(item.open),
            high: Number(item.high),
            low: Number(item.low),
            close: Number(item.close),
          } as CandlestickData<Time>;
        });
        console.log('[OrderPage] 第一条数据:', processedData[0]);
        setChartData(processedData);
      } else {
        console.warn('[OrderPage] 未获取到图表数据');
        setChartData([]);
      }
    } catch (err) {
      console.error('[OrderPage] 加载图表数据失败:', err);
      toast.error('加载图表数据失败，请检查后端服务');
      setChartData([]);
    } finally {
      setLoadingChart(false);
    }
  };

  const validateEntry = async () => {
    if (!symbol) return;
    try {
      setValidating(true);
      setError(null);
      const result = await entryValidationAPI.validate(symbol, leverage, risk);
      setValidationResult(result);
      
      // 提取 AI 止损推荐
      if (result.aiStopLoss) {
        setAiStopLoss(result.aiStopLoss);
      }
      
      // 计算预估仓位
      if (result.estimatedPosition) {
        setEstimatedPosition(result.estimatedPosition);
      }
    } catch (err) {
      console.error('Validation failed:', err);
      const errorMsg = err instanceof Error ? err.message : '验证失败';
      setError(errorMsg);
      toast.error(`验证失败: ${errorMsg}`);
    } finally {
      setValidating(false);
    }
  };

  // 参数验证函数
  const validateTradeParams = (): { valid: boolean; error?: string } => {
    // 验证币种
    if (!symbol || symbol.trim() === '') {
      return { valid: false, error: '请选择交易对' };
    }

    // 验证杠杆倍数（1-125）
    if (isNaN(leverage) || leverage < 1 || leverage > 125) {
      return { valid: false, error: '杠杆倍数必须在 1-125 之间' };
    }

    // 验证风险比例（0.1-10%）
    if (isNaN(risk) || risk < 0.1 || risk > 10) {
      return { valid: false, error: '风险比例必须在 0.1%-10% 之间' };
    }

    // 验证限价（如果是限价单）
    if (type === 'LIMIT') {
      if (limitPrice === null || limitPrice === undefined) {
        return { valid: false, error: '限价单必须指定限价' };
      }
      if (isNaN(limitPrice) || limitPrice <= 0) {
        return { valid: false, error: '限价必须大于 0' };
      }
    }

    return { valid: true };
  };

  const handleExecute = async () => {
    // 参数验证
    const validation = validateTradeParams();
    if (!validation.valid) {
      setError(validation.error || '参数验证失败');
      toast.error(validation.error || '参数验证失败');
      return;
    }

    try {
      setExecuting(true);
      setError(null);
      setExecutionResult(null);

      const result = await tradeAPI.execute({
        symbol,
        side,
        leverage,
        riskPercentage: risk,
        orderType: type,
        limitPrice: type === 'LIMIT' ? limitPrice : undefined,
        validateWithAI: true,
      });

      setExecutionResult(result);
      toast.success('交易执行成功');
      
      // 刷新持仓列表和账户余额
      if (store.setPositions) {
        try {
          const positions = await positionsAPI.getActive();
          store.setPositions(positions);
        } catch (err) {
          console.error('[OrderPage] 刷新持仓列表失败:', err);
        }
      }
      
      // 刷新账户余额
      await loadAccountBalance();
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '交易执行失败';
      setError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-4 animate-in fade-in duration-500">
      {/* Left: Tactical Input */}
      <div className="lg:col-span-4 flex flex-col gap-4">
        <div className="glass rounded-2xl p-6 flex flex-col gap-6 relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-[#7B61FF] to-transparent opacity-50" />
          
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold flex items-center gap-2">
              <Binary size={18} className="text-[#7B61FF]" /> 战术指令台
            </h2>
            <span className="text-[10px] font-mono text-white/20">CMD_INIT_V4.3</span>
          </div>

          <div className="space-y-4">
            {/* Symbol Selector */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-[10px] font-mono text-white/40 uppercase tracking-widest">目标币种</label>
                <button
                  onClick={() => loadKillQueue(true)}
                  disabled={store.killQueueLoading}
                  className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  title="刷新币种列表（从数据库获取最新真实数据）"
                >
                  <RefreshCw 
                    size={12} 
                    className={`text-white/40 ${store.killQueueLoading ? 'animate-spin' : ''}`} 
                  />
                </button>
              </div>
              <div className="relative group">
                <select 
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-sm font-mono appearance-none focus:outline-none focus:border-[#7B61FF]/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={store.killQueueLoading}
                >
                  {store.killQueueLoading ? (
                    <option value="">加载中...</option>
                  ) : store.killQueue.length === 0 ? (
                    <option value="">暂无数据（点击刷新）</option>
                  ) : (
                    store.killQueue
                      .filter(item => item && item.symbol && typeof item.symbol === 'string' && item.symbol.trim() !== '')
                      .map(item => (
                        <option key={item.symbol} value={item.symbol}>
                          {item.symbol}
                        </option>
                      ))
                  )}
                </select>
                <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 text-white/20 pointer-events-none" size={16} />
              </div>
              {store.killQueue.length > 0 && (
                <p className="text-[9px] font-mono text-white/20">
                  共 {store.killQueue.filter(item => item && item.symbol && typeof item.symbol === 'string' && item.symbol.trim() !== '').length} 个币种（实时数据）
                </p>
              )}
            </div>
            
            {/* Limit Price (if LIMIT order) */}
            {type === 'LIMIT' && (
              <div className="space-y-2">
                <label className="text-[10px] font-mono text-white/40 uppercase tracking-widest">限价</label>
                <input
                  type="number"
                  min="0"
                  step="0.000001"
                  value={limitPrice || ''}
                  onChange={(e) => {
                    const value = e.target.value ? Number(e.target.value) : null;
                    if (value === null || (!isNaN(value) && value > 0)) {
                      setLimitPrice(value);
                    }
                  }}
                  placeholder="输入限价"
                  className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-sm font-mono focus:outline-none focus:border-[#7B61FF]/50 transition-colors"
                />
                {limitPrice !== null && (isNaN(limitPrice) || limitPrice <= 0) ? (
                  <p className="text-[9px] text-red-500 font-mono">限价必须大于 0</p>
                ) : null}
              </div>
            )}

            {/* Side Switcher */}
            <div className="flex gap-2">
              <button 
                onClick={() => setSide('LONG')}
                className={`flex-1 py-3 rounded-xl text-xs font-bold transition-all ${side === 'LONG' ? 'bg-[#00FF9D] text-black shadow-[0_0_15px_rgba(0,255,157,0.3)]' : 'bg-white/5 text-white/40'}`}
              >
                多头 (LONG)
              </button>
              <button 
                onClick={() => setSide('SHORT')}
                className={`flex-1 py-3 rounded-xl text-xs font-bold transition-all ${side === 'SHORT' ? 'bg-[#FF2E2E] text-white shadow-[0_0_15px_rgba(255,46,46,0.3)]' : 'bg-white/5 text-white/40'}`}
              >
                空头 (SHORT)
              </button>
            </div>

            {/* Order Type */}
            <div className="grid grid-cols-2 gap-2">
              <button onClick={() => setType('MARKET')} className={`py-2 rounded-lg text-[10px] font-mono border ${type === 'MARKET' ? 'border-[#7B61FF] text-[#7B61FF]' : 'border-white/5 text-white/20'}`}>市价单</button>
              <button onClick={() => setType('LIMIT')} className={`py-2 rounded-lg text-[10px] font-mono border ${type === 'LIMIT' ? 'border-[#7B61FF] text-[#7B61FF]' : 'border-white/5 text-white/20'}`}>限价单</button>
            </div>

            {/* Leverage & Risk */}
            <div className="grid grid-cols-2 gap-4 pt-2">
              <div className="space-y-2">
                <label className="text-[10px] font-mono text-white/40">杠杆倍数</label>
                <div className="flex items-center bg-black/40 border border-white/5 rounded-lg px-3 py-2">
                  <input type="number" value={leverage} onChange={(e) => setLeverage(Number(e.target.value))} className="bg-transparent w-full text-sm font-mono focus:outline-none" />
                  <span className="text-[10px] text-white/20">x</span>
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-mono text-white/40">风险比例</label>
                <div className="flex items-center bg-black/40 border border-white/5 rounded-lg px-3 py-2">
                  <input type="number" value={risk} onChange={(e) => setRisk(Number(e.target.value))} className="bg-transparent w-full text-sm font-mono focus:outline-none" />
                  <span className="text-[10px] text-white/20">%</span>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-auto pt-6 border-t border-white/5 space-y-4">
             <div className="flex justify-between text-[10px] font-mono">
               <span className="text-white/40">AI 推荐止损 (ATR)</span>
               <span className="text-[#FF2E2E]">
                 {aiStopLoss ? aiStopLoss.toFixed(2) : '计算中...'}
               </span>
             </div>
             <div className="flex justify-between text-[10px] font-mono">
               <span className="text-white/40">预估仓位价值</span>
               <span className="text-white">
                 {estimatedPosition ? `${estimatedPosition.toFixed(2)} USDT` : '计算中...'}
               </span>
             </div>
             
             {/* 错误提示 */}
             {error && (
               <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 flex items-start gap-2">
                 <XCircle size={14} className="text-red-500 mt-0.5" />
                 <p className="text-[10px] text-red-500 font-mono">{error}</p>
               </div>
             )}
             
             {/* 执行结果 */}
             {executionResult && (
               <div className="bg-[#00FF9D]/10 border border-[#00FF9D]/20 rounded-lg p-3 flex items-start gap-2">
                 <CheckCircle size={14} className="text-[#00FF9D] mt-0.5" />
                 <div className="flex-1">
                   <p className="text-[10px] text-[#00FF9D] font-mono font-bold">交易执行成功</p>
                   <p className="text-[9px] text-white/60 mt-1">
                     订单ID: {executionResult.orderId || executionResult.id}
                   </p>
                 </div>
               </div>
             )}
             
             <button 
               onClick={handleExecute}
               disabled={executing || !symbol || validating || store.systemState === 'SHADOW'}
               className="w-full py-4 bg-[#7B61FF] disabled:bg-white/10 disabled:text-white/30 disabled:cursor-not-allowed text-white font-bold tracking-tighter rounded-xl hover:brightness-110 transition-all shadow-[0_0_20px_rgba(123,97,255,0.3)] flex items-center justify-center gap-2 uppercase"
             >
               {executing ? (
                 <>
                   <Loader2 size={16} className="animate-spin" />
                   执行中...
                 </>
               ) : (
                 <>
                   执行战术指令 <Zap size={16} fill="white" />
                 </>
               )}
             </button>
             
             {store.systemState === 'SHADOW' && (
               <p className="text-[9px] text-yellow-500/60 font-mono text-center">
                 ⚠️ 当前为影子模式，交易不会真实执行
               </p>
             )}
          </div>
        </div>
      </div>

      {/* Right: Market Context & AI Analysis */}
      <div className="lg:col-span-8 flex flex-col gap-4">
        <div className="glass rounded-2xl p-6 flex-1 flex flex-col gap-6 min-h-0">
           <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <h3 className="text-xs font-mono uppercase tracking-widest text-white/40 flex items-center gap-2">
                <Target size={14} className="text-[#00FF9D]" /> 神经确认分析 (Neural Confirmation)
              </h3>
              <div className="flex flex-col md:flex-row items-start md:items-center gap-2 md:gap-4 text-[10px] font-mono">
                {loadingBalance ? (
                  <>
                    <span className="text-white/20 flex items-center gap-1">
                      <Loader2 size={10} className="animate-spin" />
                      BALANCE: 加载中...
                    </span>
                    <span className="text-white/20">FREE MARGIN: 加载中...</span>
                  </>
                ) : accountBalance ? (
                  <>
                    <span className="text-white/20">BALANCE: {accountBalance.balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT</span>
                    <span className="text-white/20">FREE MARGIN: {accountBalance.freeMargin.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT</span>
                  </>
                ) : (
                  <>
                    <span className="text-white/20 opacity-50">BALANCE: N/A</span>
                    <span className="text-white/20 opacity-50">FREE MARGIN: N/A</span>
                  </>
                )}
              </div>
           </div>

           <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-6 min-h-0">
              <div className="bg-black/40 border border-white/5 rounded-2xl p-6 space-y-6">
                <h4 className="text-[10px] font-mono text-[#7B61FF] uppercase tracking-widest">进场逻辑验证</h4>
                {validating ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 size={20} className="animate-spin text-[#7B61FF]" />
                    <span className="ml-2 text-xs text-white/40 font-mono">验证中...</span>
                  </div>
                ) : validationResult ? (
                  <>
                    <div className="space-y-4">
                      {validationResult.scores?.map((item: any) => (
                        <div key={item.label} className="flex items-center justify-between">
                          <span className="text-xs text-white/60">{item.label}</span>
                          <div className="flex items-center gap-3">
                            <div className="w-24 h-1 bg-white/5 rounded-full overflow-hidden">
                              <div 
                                className={`h-full ${item.status === 'PASS' ? 'bg-[#00FF9D]' : item.status === 'WAIT' ? 'bg-yellow-500' : 'bg-red-500'}`} 
                                style={{ width: `${item.score}%` }} 
                              />
                            </div>
                            <span className={`text-[10px] font-mono ${item.status === 'PASS' ? 'text-[#00FF9D]' : item.status === 'WAIT' ? 'text-yellow-500' : 'text-red-500'}`}>
                              {item.status}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                    {validationResult.aiReason && (
                      <div className="pt-4 border-t border-white/5">
                        <p className="text-[11px] font-mono text-white/40 leading-relaxed italic">
                          "AI: {validationResult.aiReason}"
                        </p>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-center py-8 text-white/20 text-xs font-mono">
                    选择币种后自动验证
                  </div>
                )}
              </div>

              <div className="bg-black/40 border border-white/5 rounded-2xl p-6 flex flex-col min-h-[300px]">
                <h4 className="text-[10px] font-mono text-[#00FF9D] uppercase tracking-widest mb-6">实时市场深度</h4>
                <div className="flex-1 flex flex-col justify-center gap-2 min-h-0">
                  {loadingDepth ? (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 size={16} className="animate-spin text-[#00FF9D]" />
                      <span className="ml-2 text-xs text-white/40 font-mono">加载中...</span>
                    </div>
                  ) : marketDepth.length > 0 ? (
                    marketDepth.map((item, i) => {
                      // 计算宽度（基于数量，相对最大数量）
                      const maxQuantity = Math.max(...marketDepth.map(d => d.quantity));
                      const widthPercent = maxQuantity > 0 ? (item.quantity / maxQuantity) * 80 + 20 : 20;
                      const isAsk = item.side === 'ask';
                      
                      return (
                        <div key={`${item.side}-${i}-${item.price}`} className="flex items-center gap-2 h-2">
                          <div 
                            className={`h-full rounded-r-sm ${isAsk ? 'bg-red-500/20' : 'bg-[#00FF9D]/20'}`} 
                            style={{ width: `${widthPercent}%` }} 
                          />
                          <span className={`text-[8px] font-mono ${isAsk ? 'text-red-500' : 'text-[#00FF9D]'}`}>
                            {item.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 })}
                          </span>
                          <span className="text-[7px] font-mono text-white/30 ml-auto">
                            {item.quantity.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 4 })}
                          </span>
                        </div>
                      );
                    })
                  ) : symbol ? (
                    <div className="text-center py-8 text-white/20 text-xs font-mono">
                      暂无市场深度数据
                    </div>
                  ) : (
                    <div className="text-center py-8 text-white/20 text-xs font-mono">
                      选择币种后显示市场深度
                    </div>
                  )}
                </div>
              </div>
           </div>
        </div>
        
        <div className="flex-1 min-h-[400px] glass rounded-2xl p-6 flex flex-col border border-white/10">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-[10px] font-mono text-white/40 uppercase tracking-widest">战术图表</h4>
            {loadingChart && (
              <Loader2 size={14} className="animate-spin text-[#7B61FF]" />
            )}
          </div>
          {chartData.length > 0 ? (
            <div className="flex-1 min-h-0">
              <TradingViewChart 
                chartId={`order-chart-${symbol}`}
                data={chartData}
                options={{
                  layout: {
                    background: { type: 'solid', color: '#050505' },
                    textColor: '#D1D4DC',
                  },
                }}
              />
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center border-dashed border-white/10 border-2 rounded-lg">
              <div className="text-center space-y-2 opacity-30">
                <AlertCircle className="mx-auto" size={24} />
                <p className="text-[10px] font-mono uppercase tracking-[0.3em]">
                  {loadingChart ? '加载中...' : '等待图表数据...'}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default OrderPage;
