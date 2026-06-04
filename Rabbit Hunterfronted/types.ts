
export enum SystemState {
  SHADOW = 'SHADOW',
  LIVE = 'LIVE'
}

export enum TradePhase {
  P1_NO_WHALE = 'P1_NO_WHALE',
  P2_ACCUMULATION = 'P2_ACCUMULATION',
  P3A_PUMP_START = 'P3A_PUMP_START',
  P3B_PUMP_LATE = 'P3B_PUMP_LATE',
  P4_DISTRIBUTION = 'P4_DISTRIBUTION',
  P3A = 'P3A',
  P4 = 'P4',
  EARLY = 'Early',
  MATURE = 'Mature'
}

export type ViewType = 'KILL_BOARD' | 'DASHBOARD' | 'ORDER' | 'POSITIONS' | 'SETTINGS' | 'WEIGHT_HISTORY' | 'TRADE_SCORES' | 'STRATEGY_CONFIG' | 'AI_STATUS';

export type RiskLabel = 'BLOCK' | 'WATCH' | 'TRADE';

export interface CoinData {
  symbol: string;
  price: number;
  change24h: number;
  aiScore: number;
  phase: TradePhase;
  age: string;
  reason: string;
  weights: {
    structure: number;
    sentiment: number;
    volatility: number;
    manipulation: number;
  };
}

/**
 * V4.3 Kill Board 币种数据
 * 包含完整的决策信息，用于"市场决策 / Kill Board"页面
 */
export interface KillBoardItem {
  symbol: string;
  
  // 核心字段（必须显示）
  score: number;              // Raw Score (0-100, 永不归零)
  riskLabel: RiskLabel;       // BLOCK / WATCH / TRADE
  phase: string;              // 市场阶段 (P1_NO_WHALE, P2_ACCUMULATION, etc.)
  edgeReason: string;         // 人能看懂的原因
  aiConfidence: number;       // AI 信心分 (0-1)
  // V4.4 策略路由信息（可选）
  strategyId?: string;        // 策略 ID: SNIFFER / SNIPER / VULTURE / WAIT
  strategySide?: 'LONG' | 'SHORT' | 'NONE'; // 策略方向
  
  // 价格信息
  price: number;
  change24h: number;
  changePercent: number;
  
  // 四维评分（展开后显示）
  dimensionScores: {
    structure: number;         // 结构分数 (0-100)
    volatility: number;        // 波动分数 (0-100)
    sentiment: number;         // 情绪分数 (0-100)
    manipulation: number;      // 操控分数 (0-100)
  };
  
  // ATR / 止损逻辑（展开后显示）
  atrInfo?: {
    entry: number;             // 入场价
    atr1h: number;             // 1H ATR
    trailingSL: number;        // 动态止损价
    expectedRR: number;        // 预期风险回报比
    atrK: number;              // ATR 倍数 k
  };
  
  // OpenAI AI 决策信息（可选，有数据才显示）
  aiReasoning?: string | null;     // AI 决策理由
  aiSlMultiplier?: number | null;  // AI 建议 SL ATR 倍数
  aiTpMultiplier?: number | null;  // AI 建议 TP ATR 倍数

  // 其他信息
  phaseAge?: number;           // 阶段年龄（K线数）
  ageInMinutes?: number;       // 年龄（分钟）
  blockReason?: string;        // 拦截原因（如果有）
  shouldTrade?: boolean;       // 是否应该交易
  positionSizeMultiplier?: number; // 仓位倍数
  
  // 时间戳
  timestamp: string;
  lastUpdated: string;
  
  // 唯一标识符（用于 React key，可选）
  id?: string;
}

export interface Position {
  id?: string;
  symbol: string;
  entryPrice?: number;
  currentPrice?: number;
  atrStop?: number;
  takeProfit?: number;
  leverage?: number;
  size: number;
  pnl?: number;
  pnlPercent?: number;
  realizedPnl?: number;
  status?: 'SAFE' | 'DANGER';
  side: 'LONG' | 'SHORT';
}

export interface EvolutionEvent {
  date: string;
  type: 'WIN' | 'LOSS';
  mode: 'Sniper' | 'Scavenger';
  decision: string;
  atrK: number;
}
