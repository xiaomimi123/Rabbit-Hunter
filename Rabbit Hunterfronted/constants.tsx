
import React from 'react';
import { TradePhase, CoinData, Position, EvolutionEvent } from './types';

// v45: 调色板和 tailwind.config.js 对齐 — 单 accent，去 neon
export const COLORS = {
  bg: '#0a0a0a',
  glass: '#111111',
  primary: '#d4a256', // soft amber accent
  ai: '#d4a256',      // 与 primary 同源（旧 quantum purple 已弃）
  warning: '#f43f5e',
};

export const MOCK_KILL_QUEUE: CoinData[] = [
  {
    symbol: 'BTC/USDT',
    price: 64231.5,
    change24h: 2.4,
    aiScore: 87.5,
    phase: TradePhase.P3A,
    age: '00:12:45',
    reason: '检测到黄金影线 + 资金费率背离',
    weights: { structure: 40, sentiment: 20, volatility: 30, manipulation: 10 }
  },
  {
    symbol: 'SOL/USDT',
    price: 145.22,
    change24h: 5.1,
    aiScore: 72.1,
    phase: TradePhase.P3A,
    age: '02:05:11',
    reason: 'ATR 突破 + 强结构性空间',
    weights: { structure: 50, sentiment: 15, volatility: 25, manipulation: 10 }
  },
  {
    symbol: 'PEPE/USDT',
    price: 0.0000085,
    change24h: -1.2,
    aiScore: 68.4,
    phase: TradePhase.P4,
    age: '00:45:00',
    reason: '巨鲸操纵扫描 + 流动性掠夺',
    weights: { structure: 20, sentiment: 10, volatility: 40, manipulation: 30 }
  }
];

export const MOCK_POSITIONS: Position[] = [
  { 
    symbol: 'ETH/USDT', 
    entryPrice: 3200, 
    currentPrice: 3450, 
    atrStop: 3320, 
    takeProfit: 3800,
    leverage: 10,
    size: 1.5,
    pnl: 375, 
    pnlPercent: 7.8, 
    status: 'SAFE',
    side: 'LONG'
  },
  { 
    symbol: 'LINK/USDT', 
    entryPrice: 18.5, 
    currentPrice: 19.1, 
    atrStop: 18.95, 
    takeProfit: 22.0,
    leverage: 5,
    size: 200,
    pnl: 120, 
    pnlPercent: 3.2, 
    status: 'DANGER',
    side: 'LONG'
  },
  { 
    symbol: 'WIF/USDT', 
    entryPrice: 3.5, 
    currentPrice: 3.2, 
    atrStop: 3.35, 
    takeProfit: 2.5,
    leverage: 3,
    size: 1000,
    pnl: 300, 
    pnlPercent: 8.5, 
    status: 'SAFE',
    side: 'SHORT'
  }
];

export const MOCK_EVOLUTION: EvolutionEvent[] = [
  { date: '2024-05-18', type: 'WIN', mode: 'Sniper', decision: '将 ATR 因子提高至 2.5', atrK: 2.5 },
  { date: '2024-05-17', type: 'LOSS', mode: 'Scavenger', decision: '由于低波动率降低了 Scavenger 权重', atrK: 2.2 },
];
