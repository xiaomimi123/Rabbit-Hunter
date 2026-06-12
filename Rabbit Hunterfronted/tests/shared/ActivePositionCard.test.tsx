import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ActivePositionCard } from '@/components/shared/ActivePositionCard';
import type { V5Position } from '@/types';

const POS: V5Position = {
  id: 7, symbol: 'HUSDT', side: 'SHORT', status: 'OPEN',
  entry_price: 0.1665,
  sl_price: 0.1715, tp_price: 0.1592,
  size_usdt: 15, position_size_coins: null, leverage: 10,
  entry_time: '2026-06-12T09:48:00+00:00',
  exit_time: null, exit_price: null, exit_reason: null,
  pnl_pct: 1.44, pnl_usdt: 0.22,
  entry_rsi_15m: 72, entry_macd_hist_15m: -0.0006,
  entry_rsi_4h: null, entry_atr_15m: null,
  extension_count: 0, target_close_at: null,
  holding_minutes: null, created_at: null, updated_at: null,
};

describe('ActivePositionCard', () => {
  it('renders symbol, side, entry, sl, tp', () => {
    render(<ActivePositionCard position={POS} onClose={() => {}} onChart={() => {}} />);
    expect(screen.getByText('HUSDT')).toBeInTheDocument();
    expect(screen.getByText(/SHORT/)).toBeInTheDocument();
    expect(screen.getByText(/0\.1665/)).toBeInTheDocument();
    expect(screen.getByText(/0\.1715/)).toBeInTheDocument();
    expect(screen.getByText(/0\.1592/)).toBeInTheDocument();
  });

  it('positive PnL displays in long tone for SHORT going down', () => {
    render(<ActivePositionCard position={POS} onClose={() => {}} onChart={() => {}} />);
    expect(screen.getByText(/\+1\.44%/)).toBeInTheDocument();
  });

  it('calls onClose when 立即平 clicked', () => {
    const cb = vi.fn();
    render(<ActivePositionCard position={POS} onClose={cb} onChart={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /立即平/ }));
    expect(cb).toHaveBeenCalledWith(POS);
  });
});
