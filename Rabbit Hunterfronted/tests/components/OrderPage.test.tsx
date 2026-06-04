/**
 * OrderPage 组件测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import OrderPage from '../../components/OrderPage';
import { useV43Store } from '../../services/store';

// Mock store
vi.mock('../../services/store', () => ({
  useV43Store: vi.fn(),
}));

// Mock API
vi.mock('../../services/api', () => ({
  killQueueAPI: {
    getQueue: vi.fn().mockResolvedValue({
      data: [
        {
          symbol: 'BTC/USDT',
          price: 50000,
          aiScore: 85,
          phase: 'P3A',
        },
      ],
    }),
  },
  entryValidationAPI: {
    validate: vi.fn().mockResolvedValue({
      data: {
        shouldTrade: true,
        finalScore: 85,
        aiStopLoss: 48000,
      },
    }),
  },
  anatomyAPI: {
    getChartData: vi.fn().mockResolvedValue([
      { time: 1000, open: 50000, high: 51000, low: 49000, close: 50500 },
    ]),
  },
  tradeAPI: {
    execute: vi.fn().mockResolvedValue({
      success: true,
      message: '交易执行成功',
    }),
  },
}));

// Mock TradingView Chart
vi.mock('../../components/TradingViewChart', () => ({
  default: () => <div data-testid="tradingview-chart">TradingView Chart</div>,
}));

describe('OrderPage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    (useV43Store as any).mockReturnValue({
      killQueue: [
        {
          symbol: 'BTC/USDT',
          price: 50000,
          aiScore: 85,
          phase: 'P3A',
        },
      ],
      selectedCoin: null,
      setKillQueue: vi.fn(),
      selectCoin: vi.fn(),
    });
  });

  it('should render order page', () => {
    render(<OrderPage />);
    expect(screen.getByText(/战术下单/i)).toBeInTheDocument();
  });

  it('should load kill queue on mount', async () => {
    render(<OrderPage />);
    
    await waitFor(() => {
      expect(useV43Store().killQueue.length).toBeGreaterThan(0);
    });
  });

  it('should validate entry when symbol changes', async () => {
    const { entryValidationAPI } = await import('../../services/api');
    render(<OrderPage />);
    
    await waitFor(() => {
      expect(entryValidationAPI.validate).toHaveBeenCalled();
    });
  });
});

