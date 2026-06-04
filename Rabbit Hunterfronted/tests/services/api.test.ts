/**
 * API 服务测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { killQueueAPI, positionsAPI, tradeAPI } from '../../services/api';
import { apiGet, apiPost } from '../../services/apiInterceptor';

// Mock apiInterceptor
vi.mock('../../services/apiInterceptor', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
}));

describe('API Services', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('killQueueAPI', () => {
    it('should fetch kill queue', async () => {
      const mockData = {
        status: 'success',
        code: 200,
        data: [{ symbol: 'BTC/USDT', aiScore: 85 }],
      };
      (apiGet as any).mockResolvedValue(mockData);

      const result = await killQueueAPI.getQueue(20, 60);
      expect(result).toEqual(mockData);
      expect(apiGet).toHaveBeenCalledWith(
        expect.stringContaining('/v43/kill-queue')
      );
    });
  });

  describe('positionsAPI', () => {
    it('should fetch active positions', async () => {
      const mockData = {
        status: 'success',
        code: 200,
        data: {
          active: [{ symbol: 'BTC/USDT', entryPrice: 50000 }],
          total: 1,
        },
      };
      (apiGet as any).mockResolvedValue(mockData);

      const result = await positionsAPI.getActive();
      expect(result.data.active).toBeDefined();
      expect(apiGet).toHaveBeenCalledWith(
        expect.stringContaining('/v43/positions')
      );
    });
  });

  describe('tradeAPI', () => {
    it('should execute trade', async () => {
      const mockData = {
        success: true,
        message: '交易执行成功',
      };
      (apiPost as any).mockResolvedValue(mockData);

      const result = await tradeAPI.execute({
        symbol: 'BTC/USDT',
        side: 'LONG',
        leverage: 10,
        riskPercentage: 2,
        orderType: 'MARKET',
      });

      expect(result).toBeDefined();
      expect(apiPost).toHaveBeenCalled();
    });
  });
});

