/**
 * API 服务层
 * 负责与后端 V4.3 API 的所有通信
 * 
 * 使用统一的请求拦截器处理错误、重试、超时
 */

import { apiGet, apiPost, apiDelete } from './apiInterceptor';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

// ============== Kill Queue API ==============

export const killQueueAPI = {
  /**
   * 获取实时猎杀队列
   */
  getQueue: async (limit: number = 20, minScore: number = 60) => {
    try {
      const url = `${API_BASE}/v43/kill-queue?limit=${limit}&minScore=${minScore}`;
      console.log(`[killQueueAPI] 请求 URL: ${url}`);
      
      const result = await apiGet(url);
      
      // 处理不同的响应格式
      if (result && result.data && Array.isArray(result.data)) {
        console.log(`[killQueueAPI] ✅ 成功获取 ${result.data.length} 条数据`);
        return result; // 标准格式: { status, code, data: [...], pagination, metadata }
      } else if (Array.isArray(result)) {
        // 直接数组格式（兼容处理）
        console.log(`[killQueueAPI] ✅ 成功获取 ${result.length} 条数据（直接数组格式）`);
        return { status: 'success', code: 200, data: result, pagination: {}, metadata: {} };
      } else {
        console.warn('[killQueueAPI] ⚠️ 意外的响应格式:', result);
        return { status: 'success', code: 200, data: [], pagination: {}, metadata: {} };
      }
    } catch (error: any) {
      console.error('[killQueueAPI] ❌ 获取猎杀队列失败:', error);
      
      // 如果是 404 错误，提供更详细的提示
      if (error.status === 404) {
        console.error('[killQueueAPI] 404 错误 - API 端点不存在，请检查：');
        console.error('  1. 后端服务是否已启动？');
        console.error('  2. API 路径是否正确？应该是 /api/v43/kill-queue');
        console.error('  3. 后端路由是否已注册？');
      }
      
      throw error;
    }
  }
};

// ============== Anatomy API ==============

export const anatomyAPI = {
  /**
   * 获取币种深度分析
   */
  analyze: async (symbol: string, timeframe: string = '15m') => {
    // 对 symbol 进行 URL 编码，因为可能包含 / 字符（如 1000PEPE/USDT）
    return apiGet(`${API_BASE}/v43/anatomy/${encodeURIComponent(symbol)}?timeframe=${timeframe}`);
  },

  /**
   * 获取图表数据 (TradingView 格式)
   */
  getChartData: async (symbol: string, limit: number = 100) => {
    // 对 symbol 进行 URL 编码，因为可能包含 / 字符（如 1000PEPE/USDT）
    return apiGet(`${API_BASE}/v43/anatomy/${encodeURIComponent(symbol)}/chart-data?limit=${limit}`);
  },

  /**
   * 使用 DeepSeek 获取深度解剖 AI 解释
   */
  explain: async (
    symbol: string,
    score: number,
    reason: string,
    context?: {
      atr?: number;
      stopLoss?: number;
      takeProfit?: number;
      rewardRiskRatio?: number;
      phase?: string;
    }
  ): Promise<string> => {
    const payload: any = { symbol, score, reason };
    if (context) {
      if (context.atr !== undefined) payload.atr = context.atr;
      if (context.stopLoss !== undefined) payload.stop_loss = context.stopLoss;
      if (context.takeProfit !== undefined) payload.take_profit = context.takeProfit;
      if (context.rewardRiskRatio !== undefined) payload.reward_risk_ratio = context.rewardRiskRatio;
      if (context.phase !== undefined) payload.phase = context.phase;
    }
    const result = await apiPost(
      `${API_BASE}/v43/anatomy/${encodeURIComponent(symbol)}/ai-explain`,
      payload,
    );
    if (result?.data?.text) return result.data.text as string;
    if (result?.text) return result.text as string;
    return 'AI: 当前市场结构复杂，建议先降低仓位或继续观察。';
  },
};

// ============== Entry Validation API ==============

export const entryValidationAPI = {
  /**
   * 验证交易进场条件
   */
  validate: async (symbol: string, leverage: number, risk: number) => {
    const result = await apiPost(`${API_BASE}/v43/validate-entry`, {
      symbol,
      leverage,
      risk,
    });
    return result.data || result;
  }
};

// ============== Trade Execution API ==============

export const tradeAPI = {
  /**
   * 执行新交易（开仓）
   */
  execute: async (tradeData: {
    symbol: string;
    side: 'LONG' | 'SHORT';
    leverage: number;
    riskPercentage: number;
    orderType: 'MARKET' | 'LIMIT';
    limitPrice?: number;
    validateWithAI?: boolean;
    quantity?: number; // 可选：直接指定数量
  }) => {
    // 后端期望的格式
    const requestBody: any = {
      symbol: tradeData.symbol,
      side: tradeData.side,
      leverage: tradeData.leverage,
      risk_percentage: tradeData.riskPercentage,
      order_type: tradeData.orderType,
    };
    
    if (tradeData.quantity) {
      requestBody.quantity = tradeData.quantity;
    }
    
    if (tradeData.limitPrice) {
      requestBody.limit_price = tradeData.limitPrice;
    }
    
    const result = await apiPost(`${API_BASE}/v43/trade/open`, requestBody);
    return result.data || result;
  },

  /**
   * 平仓持仓
   */
  close: async (positionIdOrSymbol: string, closeType: string = 'MARKET') => {
    // 后端期望的格式：TradeCloseRequest { symbol, quantity?, order_type }
    const result = await apiPost(`${API_BASE}/v43/trade/close`, {
      symbol: positionIdOrSymbol, // 后端需要 symbol
      order_type: closeType,
    });
    return result.data || result;
  }
};

// ============== Strategy Config API ==============

export const strategyConfigAPI = {
  /**
   * 获取策略路由配置
   */
  getConfig: async () => {
    // TODO: 实现 API 端点
    // return apiGet(`${API_BASE}/v44/strategy-router-config`);
    return { data: null };
  },

  /**
   * 保存策略路由配置
   */
  saveConfig: async (config: any) => {
    // TODO: 实现 API 端点
    // return apiPost(`${API_BASE}/v44/strategy-router-config`, config);
    return { success: true };
  },
};

// ============== AI Status API ==============

export const aiStatusAPI = {
  getStatus: async () => {
    return apiGet(`${API_BASE}/v43/openai-status`);
  },
  uploadMemory: async () => {
    return apiPost(`${API_BASE}/v43/openai-memory/upload`, {});
  },
};

// ============== Positions API ==============

export const positionsAPI = {
  /**
   * 获取所有活跃持仓
   */
  getActive: async () => {
    const result = await apiGet(`${API_BASE}/v43/positions`);
    // 后端返回格式: { status, code, data: { active: [...], total: N } }
    // 或者直接返回数组（兼容处理）
    if (result.data && result.data.active) {
      return result;
    } else if (Array.isArray(result)) {
      return { data: { active: result, total: result.length } };
    } else if (Array.isArray(result.data)) {
      return { data: { active: result.data, total: result.data.length } };
    }
    return result;
  }
};

// ============== AI Evolution API ==============

export const aiEvolutionAPI = {
  /**
   * 获取 AI 进化日志
   */
  getHistory: async (days: number = 30) => {
    return apiGet(`${API_BASE}/v43/ai-evolution?days=${days}`);
  },

  /**
   * 获取准确率热力图
   */
  getAccuracyHeatmap: async (days: number = 28) => {
    return apiGet(`${API_BASE}/v43/accuracy-heatmap?days=${days}`);
  }
};

// ============== System API ==============

export const systemAPI = {
  /**
   * 获取系统状态
   */
  getState: async () => {
    return apiGet(`${API_BASE}/v43/system-state`);
  },

  /**
   * 切换 SHADOW/LIVE 模式
   */
  toggleMode: async (newMode: 'SHADOW' | 'LIVE') => {
    return apiPost(`${API_BASE}/v43/system-state/toggle-mode`, {
      newMode,
      confirmation: true,
    });
  },

  /**
   * v0.5.2: 当前 active exchange — 顶栏徽章用
   * 返回 { exchange: 'okx' | 'binance', label: 'OKX' | 'BINANCE', testnet: bool }
   */
  getExchange: async () => {
    return apiGet(`${API_BASE}/v43/system/exchange`);
  },
};


// ============== Exchange Config API (v0.5.3) ==============

export const exchangeConfigAPI = {
  /** 一次拉两个 exchange 的配置状态 + active */
  getStatus: async () => {
    return apiGet(`${API_BASE}/v43/exchange-config/status`);
  },
  /** 保存某 exchange 配置（OKX 必须带 passphrase；Binance 传空字符串）*/
  save: async (
    exchange: 'okx' | 'binance',
    payload: { api_key: string; api_secret: string; api_passphrase?: string; testnet: boolean; leverage: number }
  ) => {
    return apiPost(`${API_BASE}/v43/exchange-config/${exchange}`, {
      api_passphrase: '',
      ...payload,
    });
  },
  /** 删除某 exchange 配置（DB 删空 → 回退到 env 兜底）*/
  remove: async (exchange: 'okx' | 'binance') => {
    return apiDelete(`${API_BASE}/v43/exchange-config/${exchange}`);
  },
  /** 切换 active exchange（OKX <-> Binance）*/
  setActive: async (exchange: 'okx' | 'binance') => {
    return apiPost(`${API_BASE}/v43/exchange-config/active`, { exchange });
  },
};


// ============== AI Provider Config API (v0.5.3) ==============

export const aiConfigAPI = {
  get: async () => {
    return apiGet(`${API_BASE}/v43/ai-config`);
  },
  save: async (payload: { provider: string; api_key: string; model: string; enabled: boolean }) => {
    return apiPost(`${API_BASE}/v43/ai-config`, payload);
  },
  remove: async () => {
    return apiDelete(`${API_BASE}/v43/ai-config`);
  },
};

// ============== 权重管理 API ==============

export const weightsAPI = {
  /**
   * 获取当前权重配置
   */
  async getCurrent(): Promise<any> {
    const result = await apiGet(`${API_BASE}/v43/weights`);
    return result.data || result;
  },

  /**
   * 获取权重历史
   */
  async getHistory(limit: number = 50, offset: number = 0): Promise<any[]> {
    const result = await apiGet(
      `${API_BASE}/v43/weight-history?limit=${limit}&offset=${offset}`
    );
    const data = Array.isArray(result) ? result : result.data || [];
    
    // 处理数据：添加 updated_at 字段（用于判断自动应用）
    return data.map((item: any) => ({
      ...item,
      updated_at: item.updated_at || (item.applied ? item.created_at : undefined),
    }));
  },

  /**
   * 触发 AI 权重调整
   */
  async adjust(force: boolean = false): Promise<any> {
    const result = await apiPost(`${API_BASE}/v43/weights/adjust?force=${force}`, {});
    return result.data || result;
  },

  /**
   * 应用权重配置
   */
  async apply(weightId: number): Promise<any> {
    const result = await apiPost(`${API_BASE}/v43/weights/apply/${weightId}`, {});
    return result.data || result;
  },
};

// ============== 交易分数 API ==============

export const tradeScoresAPI = {
  /**
   * 获取交易分数列表
   */
  async getScores(params?: {
    limit?: number;
    offset?: number;
    symbol?: string;
    executed?: boolean;
  }): Promise<any> {
    const queryParams = new URLSearchParams();
    if (params?.limit) queryParams.append('limit', params.limit.toString());
    if (params?.offset) queryParams.append('offset', params.offset.toString());
    if (params?.symbol) queryParams.append('symbol', params.symbol);
    if (params?.executed !== undefined) queryParams.append('executed', params.executed.toString());

    const result = await apiGet(`${API_BASE}/v43/trade-scores?${queryParams}`);
    return Array.isArray(result) ? result : result.data || [];
  },

  /**
   * 获取单个币种的交易分数
   */
  async getScoreBySymbol(symbol: string): Promise<any> {
    const result = await apiGet(`${API_BASE}/v43/trade-score/${encodeURIComponent(symbol)}`);
    return result.data || result;
  },
};

// ============== Binance Config API ==============

export const binanceConfigAPI = {
  /**
   * 获取币安 API 配置状态
   */
  getStatus: async () => {
    return apiGet(`${API_BASE}/v43/binance-config`);
  },

  /**
   * 保存币安 API 配置
   * V4.5: 支持杠杆设置
   */
  save: async (config: {
    api_key: string;
    api_secret: string;
    testnet: boolean;
    leverage?: number;  // V4.5: 杠杆倍数（1-125）
  }) => {
    return apiPost(`${API_BASE}/v43/binance-config`, config);
  },

  /**
   * 删除币安 API 配置
   */
  delete: async () => {
    return apiDelete(`${API_BASE}/v43/binance-config`);
  }
};

// ============== Account API ==============

export const accountAPI = {
  /**
   * 获取账户余额和保证金信息
   */
  getBalance: async () => {
    try {
      const result = await apiGet(`${API_BASE}/v43/account/balance`);
      return result.data || result;
    } catch (error: any) {
      console.warn('[accountAPI] 账户余额获取失败:', error?.message ?? error);
      return null;
    }
  }
};

// ============== Market Depth API ==============

export const marketDepthAPI = {
  /**
   * 获取市场深度数据
   */
  getDepth: async (symbol: string, limit: number = 20) => {
    try {
      const result = await apiGet(`${API_BASE}/v43/market-depth/${encodeURIComponent(symbol)}?limit=${limit}`);
      return result.data || result;
    } catch (error: any) {
      // 如果 API 不存在，返回 null（前端会显示加载中）
      if (error.status === 404) {
        console.warn('[marketDepthAPI] 市场深度 API 未实现，返回 null');
        return null;
      }
      throw error;
    }
  }
};

// ============== 错误处理工具 ==============

export const handleAPIError = (error: any): string => {
  if (error.message) return error.message;
  if (error.response?.data?.message) return error.response.data.message;
  return 'Unknown error occurred';
};

