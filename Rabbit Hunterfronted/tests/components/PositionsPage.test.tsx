/**
 * PositionsPage 组件测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import PositionsPage from '../../components/PositionsPage';
import { useV43Store } from '../../services/store';

// Mock store
vi.mock('../../services/store', () => ({
  useV43Store: vi.fn(),
}));

// Mock API
vi.mock('../../services/api', () => ({
  positionsAPI: {
    getActive: vi.fn().mockResolvedValue({
      data: {
        active: [
          {
            symbol: 'BTC/USDT',
            entryPrice: 50000,
            currentPrice: 51000,
            size: 0.1,
            pnl: 100,
            pnlPercent: 2,
            side: 'LONG',
          },
        ],
        total: 1,
      },
    }),
  },
  tradeAPI: {
    close: vi.fn().mockResolvedValue({
      success: true,
      message: '平仓成功',
    }),
  },
}));

describe('PositionsPage Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    (useV43Store as any).mockReturnValue({
      positions: [],
      positionsLoading: false,
      setPositions: vi.fn(),
      setPositionsLoading: vi.fn(),
    });
  });

  it('should render positions page', () => {
    render(<PositionsPage />);
    expect(screen.getByText(/作战持仓/i)).toBeInTheDocument();
  });

  it('should load positions on mount', async () => {
    const { positionsAPI } = await import('../../services/api');
    render(<PositionsPage />);
    
    await waitFor(() => {
      expect(positionsAPI.getActive).toHaveBeenCalled();
    });
  });
});

