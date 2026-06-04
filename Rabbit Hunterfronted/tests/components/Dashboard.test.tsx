/**
 * Dashboard 组件测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import Dashboard from '../../components/Dashboard';
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
  positionsAPI: {
    getActive: vi.fn().mockResolvedValue([]),
  },
  aiEvolutionAPI: {
    getHistory: vi.fn().mockResolvedValue([]),
  },
}));

// Mock WebSocket
vi.mock('../../services/websocket', () => ({
  getWebSocketClient: vi.fn().mockReturnValue({
    connect: vi.fn(),
    subscribe: vi.fn(),
    isConnected: vi.fn().mockReturnValue(true),
  }),
}));

describe('Dashboard Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    (useV43Store as any).mockReturnValue({
      killQueue: [],
      positions: [],
      evolutionEvents: [],
      killQueueLoading: false,
      positionsLoading: false,
      setKillQueue: vi.fn(),
      setPositions: vi.fn(),
      setEvolutionEvents: vi.fn(),
      setKillQueueLoading: vi.fn(),
      setPositionsLoading: vi.fn(),
    });
  });

  it('should render dashboard', () => {
    render(<Dashboard />);
    expect(screen.getByText(/实时猎杀队列/i)).toBeInTheDocument();
  });

  it('should load kill queue on mount', async () => {
    render(<Dashboard />);
    
    await waitFor(() => {
      expect(useV43Store().setKillQueue).toHaveBeenCalled();
    });
  });
});

