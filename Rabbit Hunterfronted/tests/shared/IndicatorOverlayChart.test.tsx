import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IndicatorOverlayChart } from '@/components/shared/IndicatorOverlayChart';
import type { Kline } from '@/types';

// Lightweight Charts uses canvas; jsdom doesn't render it so we mock to test props plumbing
vi.mock('lightweight-charts', () => {
  const series = {
    setData: vi.fn(),
    createPriceLine: vi.fn(),
    setMarkers: vi.fn(),
  };
  const chart = {
    addCandlestickSeries: vi.fn(() => series),
    addLineSeries: vi.fn(() => series),
    addHistogramSeries: vi.fn(() => series),
    timeScale: () => ({
      subscribeVisibleLogicalRangeChange: vi.fn(),
      setVisibleLogicalRange: vi.fn(),
      fitContent: vi.fn(),
    }),
    remove: vi.fn(),
    applyOptions: vi.fn(),
    resize: vi.fn(),
    subscribeCrosshairMove: vi.fn(),
    setCrosshairPosition: vi.fn(),
    clearCrosshairPosition: vi.fn(),
  };
  return {
    createChart: vi.fn(() => chart),
    ColorType: { Solid: 'Solid' },
    LineStyle: { Dashed: 1, Solid: 0 },
    CrosshairMode: { Normal: 1, Magnet: 2 },
  };
});

const KLINES: Kline[] = Array.from({ length: 50 }, (_, i) => ({
  ts: 1717200000000 + i * 900_000,
  open: 0.165, high: 0.168, low: 0.164, close: 0.166, volume: 1000,
}));

describe('IndicatorOverlayChart', () => {
  it('renders interval selector', () => {
    const onChange = vi.fn();
    render(<IndicatorOverlayChart
      klines={KLINES} events={[]} interval="15m" onIntervalChange={onChange}
      currentPrice={0.166} />);
    expect(screen.getByText('15m')).toBeInTheDocument();
    expect(screen.getByText('1h')).toBeInTheDocument();
    expect(screen.getByText('4h')).toBeInTheDocument();
  });

  it('renders hover data row with placeholders', () => {
    render(<IndicatorOverlayChart
      klines={KLINES} events={[]} interval="15m" onIntervalChange={() => {}}
      currentPrice={0.166} />);
    expect(screen.getByText(/移动鼠标查看历史时点/)).toBeInTheDocument();
    // The hover row has "RSI" and "MACD hist" labels; sub-chart labels may also match.
    // Assert at least one of each exists.
    expect(screen.getAllByText(/RSI/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/MACD hist/).length).toBeGreaterThan(0);
  });
});
