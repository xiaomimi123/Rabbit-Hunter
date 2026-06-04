/**
 * 功能开关/灰度发布系统
 * 用于控制新功能的启用/禁用，支持灰度发布
 */

export interface FeatureFlag {
  name: string;
  enabled: boolean;
  rolloutPercentage: number; // 0-100，灰度发布百分比
  description?: string;
}

// 功能开关配置
const FEATURE_FLAGS: Record<string, FeatureFlag> = {
  // 新前端 UI 功能
  NEW_DASHBOARD: {
    name: 'NEW_DASHBOARD',
    enabled: true,
    rolloutPercentage: 100,
    description: '新 Dashboard 界面',
  },
  NEW_ORDER_PAGE: {
    name: 'NEW_ORDER_PAGE',
    enabled: true,
    rolloutPercentage: 100,
    description: '新订单页面',
  },
  NEW_POSITIONS_PAGE: {
    name: 'NEW_POSITIONS_PAGE',
    enabled: true,
    rolloutPercentage: 100,
    description: '新持仓页面',
  },
  TRADINGVIEW_CHARTS: {
    name: 'TRADINGVIEW_CHARTS',
    enabled: true,
    rolloutPercentage: 100,
    description: 'TradingView 图表集成',
  },
  
  // AI 功能
  GEMINI_AI_EXPLANATION: {
    name: 'GEMINI_AI_EXPLANATION',
    enabled: true,
    rolloutPercentage: 100,
    description: 'Gemini AI 智能解释',
  },
  
  // 交易功能
  REAL_TIME_TRADING: {
    name: 'REAL_TIME_TRADING',
    enabled: false, // 默认关闭，需要手动启用
    rolloutPercentage: 0,
    description: '实时交易功能（需要币安 API 配置）',
  },
  
  // WebSocket 功能
  WEBSOCKET_REALTIME: {
    name: 'WEBSOCKET_REALTIME',
    enabled: true,
    rolloutPercentage: 100,
    description: 'WebSocket 实时数据推送',
  },
  
  // 高级功能
  ADVANCED_ANALYTICS: {
    name: 'ADVANCED_ANALYTICS',
    enabled: true,
    rolloutPercentage: 50, // 50% 灰度
    description: '高级分析功能',
  },
  AI_WEIGHT_OPTIMIZATION: {
    name: 'AI_WEIGHT_OPTIMIZATION',
    enabled: true,
    rolloutPercentage: 30, // 30% 灰度
    description: 'AI 权重自动优化',
  },
};

/**
 * 获取功能开关状态
 */
export const getFeatureFlag = (flagName: string): FeatureFlag | null => {
  return FEATURE_FLAGS[flagName] || null;
};

/**
 * 检查功能是否启用
 */
export const isFeatureEnabled = (flagName: string): boolean => {
  const flag = FEATURE_FLAGS[flagName];
  if (!flag) return false;
  
  if (!flag.enabled) return false;
  
  // 如果 rolloutPercentage 是 100，直接返回 true
  if (flag.rolloutPercentage >= 100) return true;
  
  // 灰度发布：基于用户 ID 或随机数决定
  // 这里使用简单的随机数方法，实际生产环境应该基于用户 ID
  const userHash = getUserIdHash();
  const threshold = flag.rolloutPercentage;
  
  return (userHash % 100) < threshold;
};

/**
 * 获取用户 ID 的哈希值（用于灰度发布）
 * 实际生产环境应该从后端获取用户 ID
 */
const getUserIdHash = (): number => {
  // 使用 localStorage 存储一个稳定的用户标识
  let userId = localStorage.getItem('rabbit_hunter_user_id');
  if (!userId) {
    userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    localStorage.setItem('rabbit_hunter_user_id', userId);
  }
  
  // 简单的哈希函数
  let hash = 0;
  for (let i = 0; i < userId.length; i++) {
    const char = userId.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  
  return Math.abs(hash);
};

/**
 * 设置功能开关（仅开发环境）
 */
export const setFeatureFlag = (flagName: string, enabled: boolean, rolloutPercentage: number = 100): void => {
  if (import.meta.env.VITE_ENVIRONMENT !== 'development') {
    console.warn('Feature flags can only be modified in development mode');
    return;
  }
  
  if (FEATURE_FLAGS[flagName]) {
    FEATURE_FLAGS[flagName].enabled = enabled;
    FEATURE_FLAGS[flagName].rolloutPercentage = rolloutPercentage;
  }
};

/**
 * 获取所有功能开关
 */
export const getAllFeatureFlags = (): FeatureFlag[] => {
  return Object.values(FEATURE_FLAGS);
};

/**
 * React Hook: 使用功能开关
 * 注意：需要在 React 组件中使用，需要单独导入 React
 */
export const useFeatureFlag = (flagName: string): boolean => {
  // 这个 Hook 需要在组件文件中使用，这里只提供类型定义
  // 实际使用示例：
  // import { useFeatureFlag } from '../services/featureFlags';
  // const enabled = useFeatureFlag('NEW_DASHBOARD');
  return isFeatureEnabled(flagName);
};

